"""Owner-side public link management (create/list/update/delete)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import CurrentUser, IdempotencyKey, get_current_user, get_db
from ..errors import ApiError
from ..idempotency import idempotent_response
from ..models import PublicLink
from ..pagination import page_params, page_response
from ..schemas import (
    CreatePublicLinkRequest,
    DeletePublicLinkOut,
    PatchPublicLinkOut,
    PatchPublicLinkRequest,
    PublicLinkCreatedOut,
    PublicLinkOut,
)
from ..security import hash_password
from ..services import active_window, expiry_from_days, require_owned_file
from ..utils import iso, now_utc

router = APIRouter(tags=["public-links"])


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
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        file = require_owned_file(db, user.id, file_id)
        expires_at = expiry_from_days(payload.expiryDays)

        link = PublicLink(
            file_id=file_id,
            owner_id=user.id,
            owner_email=user.email,
            password_hash=hash_password(payload.password) if payload.password else None,
            expires_at=expires_at,
        )
        db.add(link)
        db.flush()
        return 201, PublicLinkCreatedOut(
            token=link.token,
            fileId=file_id,
            filename=file.filename,
            hasPassword=bool(payload.password),
            downloadCount=0,
            expiresAt=iso(expires_at),
        ).model_dump()

    return idempotent_response(db, user.id, f"public-links-create-{file_id}", idempotency_key, action)


@router.get("/v2/files/{file_id}/public-links")
def list_public_links(
    file_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
) -> dict:
    require_owned_file(db, user.id, file_id)
    page_size, offset = page_params(limit, cursor, default=50)

    links = db.execute(
        select(PublicLink)
        .where(
            PublicLink.file_id == file_id,
            active_window(PublicLink.expires_at, now_utc()),
        )
        .order_by(PublicLink.created_at, PublicLink.token)
        .offset(offset)
        .limit(page_size + 1)
    ).scalars().all()

    return page_response(
        links,
        page_size,
        offset,
        lambda link: PublicLinkOut(
            token=link.token,
            fileId=link.file_id,
            filename=link.file.filename if link.file else None,
            hasPassword=bool(link.password_hash),
            downloadCount=link.download_count,
            createdAt=iso(link.created_at),
            updatedAt=iso(link.updated_at),
            expiresAt=iso(link.expires_at),
        ).model_dump(),
    )


@router.patch("/v2/public-links/{token}")
def patch_public_link(
    token: str,
    payload: PatchPublicLinkRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
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
            link.expires_at = expiry_from_days(payload.expiryDays)
            changed = True
        if not changed:
            raise ApiError(400, "Nothing to update")
        db.flush()
        return 200, PatchPublicLinkOut(
            token=token,
            hasPassword=bool(link.password_hash),
            expiresAt=iso(link.expires_at),
        ).model_dump()

    return idempotent_response(db, user.id, f"public-links-patch-{token}", idempotency_key, action)


@router.delete("/v2/public-links/{token}")
def delete_public_link(
    token: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        link = _require_owned_link(db, user.id, token)
        db.delete(link)
        db.flush()
        return 200, DeletePublicLinkOut(message="Public link deleted", token=token).model_dump()

    return idempotent_response(db, user.id, f"public-links-delete-{token}", idempotency_key, action)
