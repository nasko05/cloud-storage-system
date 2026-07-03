"""Authenticated download URL issuance (owner or permitted share)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import storage
from ..blob_links import build_download_url
from ..config import settings
from ..deps import CurrentUser, get_current_user, get_db
from ..errors import ApiError
from ..permissions import can_download
from ..principals import user_principals
from ..services import active_share, get_file
from ..utils import iso

router = APIRouter(prefix="/v2/download", tags=["download"])


@router.post("/files/{file_id}")
def issue_download_url(
    file_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    file = get_file(db, file_id)
    if file is None:
        raise ApiError(404, "File not found")

    is_owner = file.owner_id == user.id
    share = None
    if not is_owner:
        share = active_share(db, file_id, user_principals(user))
        if share is None:
            raise ApiError(403, "Access denied")
        if not can_download(share.permission):
            raise ApiError(403, "Insufficient share permission for download")

    if not storage.exists(file.storage_key):
        raise ApiError(404, "File not found in storage")
    if file.status != "ready":
        file.status = "ready"
        db.flush()

    out = {
        "downloadUrl": build_download_url(request, file.storage_key, file.filename),
        "fileId": file.id,
        "filename": file.filename,
        "contentType": file.content_type,
        "size": file.size,
        "expiresIn": settings.signed_url_expiry_seconds,
        "accessType": "owner" if is_owner else "shared",
    }
    if share is not None:
        out["share"] = {
            "principalType": share.principal_type,
            "principalValue": share.principal_value,
            "permission": share.permission,
            "expiresAt": iso(share.expires_at),
        }
    return out
