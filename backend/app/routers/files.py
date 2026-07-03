"""File lifecycle: upload init/finalize, rename/move, delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import antivirus, storage
from ..blob_links import build_upload_url
from ..config import settings
from ..deps import CurrentUser, IdempotencyKey, get_current_user, get_db
from ..errors import ApiError
from ..idempotency import idempotent_response
from ..models import File
from ..schemas import CreateUploadRequest, PatchFileRequest
from ..services import (
    folder_exists_for_owner,
    move_or_rename_file_core,
    name_conflict,
    require_owned_file,
    user_storage_usage,
)
from ..validation import is_valid_name, normalize_folder_id

router = APIRouter(prefix="/v2/files", tags=["files"])


def _discard(db: Session, file: File) -> None:
    """Remove a rejected upload's bytes and row, committing so the deletion
    survives the request even though the handler then raises an error."""
    storage.delete(file.storage_key)
    db.delete(file)
    db.commit()


@router.post("/uploads")
def create_upload(
    payload: CreateUploadRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        if not is_valid_name(payload.filename):
            raise ApiError(400, "Valid filename required")

        parent_folder_id = normalize_folder_id(payload.parentFolderId)
        if not folder_exists_for_owner(db, user.id, parent_folder_id):
            raise ApiError(404, "Parent folder not found")
        if name_conflict(db, user.id, parent_folder_id, File, payload.filename):
            raise ApiError(409, "A file with that name already exists in destination folder")

        try:
            size = int(payload.size or 0)
        except (TypeError, ValueError):
            raise ApiError(400, "size must be an integer") from None
        if size < 0:
            raise ApiError(400, "size must be non-negative")

        quota = settings.user_quota_bytes
        if quota and user_storage_usage(db, user.id) + size > quota:
            raise ApiError(413, "Storage quota exceeded")

        file = File(
            owner_id=user.id,
            owner_email=user.email,
            filename=payload.filename,
            parent_folder_id=parent_folder_id,
            content_type=payload.contentType or "application/octet-stream",
            size=size,
            status="pending",
            storage_key="",
        )
        db.add(file)
        db.flush()
        file.storage_key = storage.file_key(user.id, file.id, file.filename)
        db.flush()

        return 201, {
            "fileId": file.id,
            "uploadUrl": build_upload_url(request, file.storage_key),
            "expiresIn": settings.signed_url_expiry_seconds,
            "status": "pending",
        }

    return idempotent_response(db, user.id, "files-upload-create", idempotency_key, action)


@router.post("/{file_id}/finalize")
def finalize_upload(
    file_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        file = require_owned_file(db, user.id, file_id)
        if not storage.exists(file.storage_key):
            raise ApiError(409, "File bytes are not uploaded yet")

        actual_size = storage.size(file.storage_key)

        quota = settings.user_quota_bytes
        if quota and user_storage_usage(db, user.id, exclude_file_id=file_id) + actual_size > quota:
            _discard(db, file)
            raise ApiError(413, "Storage quota exceeded")

        # Reject malware before the file is marked ready (and before it can be
        # captured in a backup). No-op unless ClamAV is enabled.
        clean, signature = antivirus.scan_file(storage.resolve(file.storage_key))
        if not clean:
            _discard(db, file)
            raise ApiError(422, f"File failed virus scan: {signature}")

        if file.status != "ready":
            file.status = "ready"
            file.size = actual_size
            db.flush()

        return 200, {
            "fileId": file.id,
            "status": "ready",
            "size": actual_size,
            "contentType": file.content_type,
        }

    return idempotent_response(db, user.id, f"files-finalize-{file_id}", idempotency_key, action)


@router.patch("/{file_id}")
def patch_file(
    file_id: str,
    payload: PatchFileRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        if payload.newName is None and payload.destinationFolderId is None:
            raise ApiError(400, "At least one of newName or destinationFolderId is required")

        file, changed = move_or_rename_file_core(
            db,
            user.id,
            file_id,
            new_name=payload.newName,
            dest_folder_id=payload.destinationFolderId,
        )
        if not changed:
            return 200, {"message": "No changes"}
        return 200, {
            "message": "File updated",
            "fileId": file.id,
            "filename": file.filename,
            "parentFolderId": file.parent_folder_id,
        }

    return idempotent_response(db, user.id, f"files-patch-{file_id}", idempotency_key, action)


@router.delete("/{file_id}")
def delete_file(
    file_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        file = require_owned_file(db, user.id, file_id)
        storage.delete(file.storage_key)
        db.delete(file)  # cascades to shares + public links
        db.flush()
        return 200, {"message": "File deleted", "fileId": file_id}

    return idempotent_response(db, user.id, f"files-delete-{file_id}", idempotency_key, action)
