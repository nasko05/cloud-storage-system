"""Folder hierarchy: list children, create, rename/move, delete."""

from __future__ import annotations

from collections import deque

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import storage
from ..deps import CurrentUser, get_current_user, get_db
from ..errors import ApiError
from ..idempotency import run_idempotent
from ..models import File, Folder
from ..pagination import decode_cursor, encode_cursor, normalize_limit
from ..schemas import CreateFolderRequest, PatchFolderRequest
from ..services import (
    derive_file_flags,
    folder_exists_for_owner,
    is_descendant_folder,
    name_conflict,
    require_owned_folder,
)
from ..utils import iso
from ..validation import is_valid_name, normalize_folder_id

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

    page_size = normalize_limit(limit, default=100, max_value=200)
    offset = decode_cursor(cursor)
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

    has_more = len(rows) > page_size
    window = rows[:page_size]

    page_file_ids = [row.id for row in window if isinstance(row, File)]
    flags = derive_file_flags(db, page_file_ids)

    items: list[dict] = []
    for row in window:
        if isinstance(row, Folder):
            items.append({
                "type": "folder",
                "folderId": row.id,
                "name": row.name,
                "parentFolderId": row.parent_folder_id,
                "createdAt": iso(row.created_at),
                "updatedAt": iso(row.updated_at),
            })
        else:
            items.append({
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
            })

    next_cursor = encode_cursor(offset + page_size) if has_more else None
    return {"items": items, "nextCursor": next_cursor}


@router.post("/{folder_id}/folders", status_code=201)
def create_folder(
    folder_id: str,
    payload: CreateFolderRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        if not folder_exists_for_owner(db, user.id, folder_id):
            raise ApiError(404, "Parent folder not found")

        name = payload.name or payload.folderName
        if not is_valid_name(name):
            raise ApiError(400, "Valid folder name required")
        assert name is not None  # narrowed by is_valid_name
        if name_conflict(db, user.id, folder_id, Folder, name):
            raise ApiError(409, "A folder with that name already exists in destination folder")

        folder = Folder(owner_id=user.id, name=name, parent_folder_id=folder_id)
        db.add(folder)
        db.flush()
        return 201, {"folderId": folder.id, "name": folder.name, "parentFolderId": folder_id}

    status, body = run_idempotent(db, user.id, f"folders-create-{folder_id}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)


@router.patch("/{folder_id}")
def patch_folder(
    folder_id: str,
    payload: PatchFolderRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        if payload.newName is None and payload.destinationFolderId is None:
            raise ApiError(400, "At least one of newName or destinationFolderId is required")

        folder = require_owned_folder(db, user.id, folder_id)

        target_name = folder.name if payload.newName is None else payload.newName.strip()
        if not is_valid_name(target_name):
            raise ApiError(400, "Valid newName required")

        target_parent = folder.parent_folder_id
        if payload.destinationFolderId is not None:
            target_parent = normalize_folder_id(payload.destinationFolderId)

        if target_parent == folder_id:
            raise ApiError(400, "Folder cannot be moved into itself")
        if not folder_exists_for_owner(db, user.id, target_parent):
            raise ApiError(404, "Destination folder not found")
        if is_descendant_folder(db, user.id, target_parent, folder_id):
            raise ApiError(400, "Cannot move folder into its own subfolder")
        if name_conflict(db, user.id, target_parent, Folder, target_name, exclude_id=folder_id):
            raise ApiError(409, "A folder with that name already exists in destination folder")

        if target_name == folder.name and target_parent == folder.parent_folder_id:
            return 200, {"message": "No changes"}

        folder.name = target_name
        folder.parent_folder_id = target_parent
        db.flush()
        return 200, {
            "message": "Folder updated",
            "folderId": folder.id,
            "name": target_name,
            "parentFolderId": target_parent,
        }

    status, body = run_idempotent(db, user.id, f"folders-patch-{folder_id}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)


@router.delete("/{folder_id}")
def delete_folder(
    folder_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    recursive: bool = Query(default=False),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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

        folders_to_delete = [folder]
        files_to_delete: list[File] = []
        queue = deque([folder_id])
        while queue:
            parent_id = queue.popleft()
            child_folders = db.execute(
                select(Folder).where(
                    Folder.owner_id == user.id, Folder.parent_folder_id == parent_id
                )
            ).scalars().all()
            for child in child_folders:
                folders_to_delete.append(child)
                queue.append(child.id)
            child_files = db.execute(
                select(File).where(
                    File.owner_id == user.id, File.parent_folder_id == parent_id
                )
            ).scalars().all()
            files_to_delete.extend(child_files)

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

    status, body = run_idempotent(db, user.id, f"folders-delete-{folder_id}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)
