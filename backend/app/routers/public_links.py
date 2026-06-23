"""Owner-side public link management (create/list/update/delete)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import CurrentUser, get_current_user, get_db
from ..errors import ApiError
from ..idempotency import run_idempotent
from ..models import PublicLink
from ..pagination import decode_cursor, encode_cursor, normalize_limit
from ..schemas import CreatePublicLinkRequest, PatchPublicLinkRequest
from ..security import hash_password
from ..services import require_owned_file
from ..utils import iso, now_utc

router = APIRouter(tags=["public-links"])


def _expiry_from_days(days: int | None):
    resolved = settings.share_expiry_days if days is None else days
    try:
        resolved = int(resolved)
    except (TypeError, ValueError):
        raise ApiError(400, "expiryDays must be an integer")
    if resolved < 1 or resolved > 365:
        raise ApiError(400, "expiryDays must be between 1 and 365")
    return now_utc() + timedelta(days=resolved)


def _require_owned_link(db: Session, user_id: str, token: str) -> PublicLink:
    link = db.get(PublicLink, token)
    if link is None:
        raise ApiError(404, "Public link not found")
    if link.owner_id != user_id:
        raise ApiError(403, "Access denied")
    return link


@router.post("/v2/files/{file_id}/public-links", status_code=201)
def create_public_link(
    file_id: str,
    payload: CreatePublicLinkRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        file = require_owned_file(db, user.id, file_id)
        expires_at = _expiry_from_days(payload.expiryDays)

        link = PublicLink(
            file_id=file_id,
            owner_id=user.id,
            owner_email=user.email,
            password_hash=hash_password(payload.password) if payload.password else None,
            expires_at=expires_at,
        )
        db.add(link)
        db.flush()
        return 201, {
            "token": link.token,
            "fileId": file_id,
            "filename": file.filename,
            "hasPassword": bool(payload.password),
            "downloadCount": 0,
            "expiresAt": iso(expires_at),
        }

    status, body = run_idempotent(db, user.id, f"public-links-create-{file_id}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)


@router.get("/v2/files/{file_id}/public-links")
def list_public_links(
    file_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
) -> dict:
    require_owned_file(db, user.id, file_id)
    page_size = normalize_limit(limit, default=50, max_value=200)
    offset = decode_cursor(cursor)

    now = now_utc()
    links = db.execute(
        select(PublicLink)
        .where(
            PublicLink.file_id == file_id,
            or_(PublicLink.expires_at.is_(None), PublicLink.expires_at > now),
        )
        .order_by(PublicLink.created_at, PublicLink.token)
        .offset(offset)
        .limit(page_size + 1)
    ).scalars().all()

    has_more = len(links) > page_size
    items = [
        {
            "token": link.token,
            "fileId": link.file_id,
            "filename": link.file.filename if link.file else None,
            "hasPassword": bool(link.password_hash),
            "downloadCount": link.download_count,
            "createdAt": iso(link.created_at),
            "updatedAt": iso(link.updated_at),
            "expiresAt": iso(link.expires_at),
        }
        for link in links[:page_size]
    ]
    next_cursor = encode_cursor(offset + page_size) if has_more else None
    return {"items": items, "nextCursor": next_cursor}


@router.patch("/v2/public-links/{token}")
def patch_public_link(
    token: str,
    payload: PatchPublicLinkRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        link = _require_owned_link(db, user.id, token)
        changed = False
        if payload.password:
            link.password_hash = hash_password(payload.password)
            changed = True
        if payload.removePassword:
            link.password_hash = None
            changed = True
        if payload.expiryDays is not None:
            link.expires_at = _expiry_from_days(payload.expiryDays)
            changed = True
        if not changed:
            raise ApiError(400, "Nothing to update")
        db.flush()
        return 200, {
            "token": token,
            "hasPassword": bool(link.password_hash),
            "expiresAt": iso(link.expires_at),
        }

    status, body = run_idempotent(db, user.id, f"public-links-patch-{token}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)


@router.delete("/v2/public-links/{token}")
def delete_public_link(
    token: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        link = _require_owned_link(db, user.id, token)
        db.delete(link)
        db.flush()
        return 200, {"message": "Public link deleted", "token": token}

    status, body = run_idempotent(db, user.id, f"public-links-delete-{token}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)
