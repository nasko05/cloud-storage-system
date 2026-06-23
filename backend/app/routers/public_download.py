"""Unauthenticated public link metadata + download (token-gated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import storage
from ..blob_links import build_download_url
from ..config import settings
from ..deps import get_db
from ..errors import ApiError
from ..models import PublicLink
from ..schemas import PublicDownloadRequest
from ..security import verify_password
from ..utils import is_active, iso

router = APIRouter(prefix="/v2/public-links", tags=["public-download"])


def _active_link_or_error(db: Session, token: str) -> PublicLink:
    link = db.get(PublicLink, token)
    if link is None:
        raise ApiError(404, "Public link not found")
    if not is_active(link.expires_at):
        raise ApiError(410, "Link has expired")
    return link


@router.get("/{token}")
def public_link_metadata(token: str, db: Session = Depends(get_db)) -> dict:
    link = _active_link_or_error(db, token)
    file = link.file
    return {
        "token": token,
        "fileId": link.file_id,
        "filename": file.filename if file else None,
        "size": file.size if file else 0,
        "contentType": file.content_type if file else "application/octet-stream",
        "hasPassword": bool(link.password_hash),
        "downloadCount": link.download_count,
        "expiresAt": iso(link.expires_at),
    }


@router.post("/{token}/download")
def public_link_download(
    token: str,
    payload: PublicDownloadRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    link = _active_link_or_error(db, token)
    file = link.file
    if file is None:
        raise ApiError(404, "File not found")

    if link.password_hash:
        if not payload.password:
            raise ApiError(403, "Password required")
        if not verify_password(payload.password, link.password_hash):
            raise ApiError(403, "Incorrect password")

    if file.status != "ready":
        raise ApiError(409, "File is not ready for download", status=file.status)
    if not storage.exists(file.storage_key):
        raise ApiError(404, "File not found in storage")

    link.download_count += 1
    db.flush()

    return {
        "downloadUrl": build_download_url(request, file.storage_key, file.filename),
        "token": token,
        "fileId": link.file_id,
        "filename": file.filename,
        "contentType": file.content_type,
        "size": file.size,
        "expiresIn": settings.signed_url_expiry_seconds,
    }
