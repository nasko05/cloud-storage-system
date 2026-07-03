"""Folder hierarchy: list children, create, rename/move, delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import storage
from ..deps import CurrentUser, IdempotencyKey, get_current_user, get_db
from ..errors import ApiError
from ..idempotency import idempotent_response
from ..models import File, Folder
from ..pagination import page_params, page_response
from ..schemas import CreateFolderRequest, PatchFolderRequest
from ..services import (
    collect_subtree,
    create_folder_core,
    derive_file_flags,
    folder_exists_for_owner,
    move_or_rename_folder_core,
    require_owned_folder,
)
from ..utils import iso

router = APIRouter(prefix="/v2/folders", tags=["folders"])


@router.get("/{folder_id}/children")
def list_children(
    folder_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
) -> dict:
    if not folder_exists_for_owner(db, user.id, folder_id):
        raise ApiError(404, "Folder not found")

    page_size, offset = page_params(limit, cursor, default=100)
    fetch = page_size + 1  # one extra row tells us whether another page exists

    # Folders sort before files in the combined stream. Page across both tables
    # at the DB level (LIMIT/OFFSET) so we never load a whole folder in memory.
    folder_count = db.scalar(
        select(func.count())
        .select_from(Folder)
        .where(Folder.owner_id == user.id, Folder.parent_folder_id == folder_id)
    ) or 0

    rows: list = []
    if offset < folder_count:
        rows.extend(
            db.execute(
                select(Folder)
                .where(Folder.owner_id == user.id, Folder.parent_folder_id == folder_id)
                .order_by(func.lower(Folder.name), Folder.id)
                .offset(offset)
                .limit(fetch)
            ).scalars().all()
        )

    remaining = fetch - len(rows)
    if remaining > 0:
        file_offset = max(0, offset - folder_count)
        rows.extend(
            db.execute(
                select(File)
                .where(File.owner_id == user.id, File.parent_folder_id == folder_id)
                .order_by(func.lower(File.filename), File.id)
                .offset(file_offset)
                .limit(remaining)
            ).scalars().all()
        )

    page_file_ids = [row.id for row in rows[:page_size] if isinstance(row, File)]
    flags = derive_file_flags(db, page_file_ids)

    return page_response(rows, page_size, offset, lambda row: _serialize_child(row, flags))


def _serialize_child(row: Folder | File, flags: dict[str, dict[str, bool]]) -> dict:
    if isinstance(row, Folder):
        return {
            "type": "folder",
            "folderId": row.id,
            "name": row.name,
            "parentFolderId": row.parent_folder_id,
            "createdAt": iso(row.created_at),
            "updatedAt": iso(row.updated_at),
        }
    return {
        "type": "file",
        "fileId": row.id,
        "name": row.filename,
        "parentFolderId": row.parent_folder_id,
        "size": row.size,
        "contentType": row.content_type,
        "status": row.status,
        "isShared": flags[row.id]["isShared"],
        "hasPublicLink": flags[row.id]["hasPublicLink"],
        "createdAt": iso(row.created_at),
        "updatedAt": iso(row.updated_at),
    }


@router.post("/{folder_id}/folders", status_code=201)
def create_folder(
    folder_id: str,
    payload: CreateFolderRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        folder = create_folder_core(db, user.id, folder_id, payload.name or payload.folderName)
        return 201, {"folderId": folder.id, "name": folder.name, "parentFolderId": folder_id}

    return idempotent_response(db, user.id, f"folders-create-{folder_id}", idempotency_key, action)


@router.patch("/{folder_id}")
def patch_folder(
    folder_id: str,
    payload: PatchFolderRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        if payload.newName is None and payload.destinationFolderId is None:
            raise ApiError(400, "At least one of newName or destinationFolderId is required")

        folder, changed = move_or_rename_folder_core(
            db,
            user.id,
            folder_id,
            new_name=payload.newName,
            dest_folder_id=payload.destinationFolderId,
        )
        if not changed:
            return 200, {"message": "No changes"}
        return 200, {
            "message": "Folder updated",
            "folderId": folder.id,
            "name": folder.name,
            "parentFolderId": folder.parent_folder_id,
        }

    return idempotent_response(db, user.id, f"folders-patch-{folder_id}", idempotency_key, action)


@router.delete("/{folder_id}")
def delete_folder(
    folder_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    recursive: bool = Query(default=False),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        folder = require_owned_folder(db, user.id, folder_id)

        if not recursive:
            has_child = db.execute(
                select(Folder.id).where(
                    Folder.owner_id == user.id, Folder.parent_folder_id == folder_id
                ).limit(1)
            ).first() or db.execute(
                select(File.id).where(
                    File.owner_id == user.id, File.parent_folder_id == folder_id
                ).limit(1)
            ).first()
            if has_child:
                raise ApiError(
                    409,
                    "Folder is not empty",
                    hint="Retry with ?recursive=true to cascade delete",
                )
            db.delete(folder)
            db.flush()
            return 200, {
                "message": "Folder deleted",
                "folderId": folder_id,
                "recursive": False,
                "deletedFolders": 1,
                "deletedFiles": 0,
            }

        sub_folders, files_to_delete = collect_subtree(db, user.id, folder_id)
        folders_to_delete = [folder, *sub_folders]

        for file in files_to_delete:
            storage.delete(file.storage_key)
            db.delete(file)
        for fld in folders_to_delete:
            db.delete(fld)
        db.flush()

        return 200, {
            "message": "Folder deleted",
            "folderId": folder_id,
            "recursive": True,
            "deletedFolders": len(folders_to_delete),
            "deletedFiles": len(files_to_delete),
        }

    return idempotent_response(db, user.id, f"folders-delete-{folder_id}", idempotency_key, action)
