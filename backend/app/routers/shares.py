"""Per-user file sharing with permission and expiry."""

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
from ..models import File, Share
from ..pagination import decode_cursor, encode_cursor, normalize_limit
from ..permissions import is_valid_permission
from ..principals import parse_principal_path
from ..schemas import PatchShareRequest, PutShareRequest
from ..services import require_owned_file
from ..utils import iso, now_utc

router = APIRouter(tags=["shares"])


def _expiry_from_days(days: int | None):
    resolved = settings.share_expiry_days if days is None else days
    try:
        resolved = int(resolved)
    except (TypeError, ValueError):
        raise ApiError(400, "expiryDays must be an integer")
    if resolved < 1 or resolved > 365:
        raise ApiError(400, "expiryDays must be between 1 and 365")
    return now_utc() + timedelta(days=resolved)


def _serialize_inbound(share: Share, file: File) -> dict:
    return {
        "fileId": share.file_id,
        "filename": file.filename,
        "ownerId": file.owner_id,
        "ownerEmail": file.owner_email,
        "permission": share.permission,
        "principalType": share.principal_type,
        "principalValue": share.principal_value,
        "principalDisplay": share.principal_display,
        "sharedAt": iso(share.shared_at),
        "expiresAt": iso(share.expires_at),
    }


@router.get("/v2/shares/inbound")
def list_inbound_shares(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
) -> dict:
    page_size = normalize_limit(limit, default=50, max_value=200)
    offset = decode_cursor(cursor)

    principal_clauses = [(Share.principal_type == "user_sub") & (Share.principal_value == user.id)]
    if user.email and user.email != user.id:
        principal_clauses.append((Share.principal_type == "email") & (Share.principal_value == user.email))

    now = now_utc()
    rows = db.execute(
        select(Share, File)
        .join(File, Share.file_id == File.id)
        .where(
            or_(*principal_clauses),
            or_(Share.expires_at.is_(None), Share.expires_at > now),
        )
        .order_by(Share.shared_at.desc(), Share.id)
        .offset(offset)
        .limit(page_size + 1)
    ).all()

    has_more = len(rows) > page_size
    items = [_serialize_inbound(share, file) for share, file in rows[:page_size]]
    next_cursor = encode_cursor(offset + page_size) if has_more else None
    return {"items": items, "nextCursor": next_cursor}


@router.get("/v2/files/{file_id}/shares")
def list_file_shares(
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
    shares = db.execute(
        select(Share)
        .where(Share.file_id == file_id, or_(Share.expires_at.is_(None), Share.expires_at > now))
        .order_by(Share.shared_at, Share.id)
        .offset(offset)
        .limit(page_size + 1)
    ).scalars().all()

    has_more = len(shares) > page_size
    items = [
        {
            "principalType": s.principal_type,
            "principalValue": s.principal_value,
            "principalDisplay": s.principal_display,
            "permission": s.permission,
            "sharedAt": iso(s.shared_at),
            "expiresAt": iso(s.expires_at),
        }
        for s in shares[:page_size]
    ]
    next_cursor = encode_cursor(offset + page_size) if has_more else None
    return {"items": items, "nextCursor": next_cursor}


@router.put("/v2/files/{file_id}/shares/{principal}")
def put_share(
    file_id: str,
    principal: str,
    payload: PutShareRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        principal_type, principal_value = parse_principal_path(principal)
        if not principal_type:
            raise ApiError(400, "Invalid principal format")
        if not is_valid_permission(payload.permission):
            raise ApiError(400, "permission must be read, download, or edit")

        require_owned_file(db, user.id, file_id)
        expires_at = _expiry_from_days(payload.expiryDays)

        share = db.execute(
            select(Share).where(
                Share.file_id == file_id,
                Share.principal_type == principal_type,
                Share.principal_value == principal_value,
            )
        ).scalars().first()

        if share is None:
            share = Share(
                file_id=file_id,
                principal_type=principal_type,
                principal_value=principal_value,
                principal_display=principal_value,
                shared_by=user.id,
                shared_by_email=user.email,
            )
            db.add(share)
        share.permission = payload.permission
        share.expires_at = expires_at
        db.flush()

        return 200, {
            "fileId": file_id,
            "principalType": principal_type,
            "principalValue": principal_value,
            "permission": payload.permission,
            "expiresAt": iso(expires_at),
        }

    status, body = run_idempotent(db, user.id, f"shares-put-{file_id}-{principal}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)


@router.patch("/v2/files/{file_id}/shares/{principal}")
def patch_share(
    file_id: str,
    principal: str,
    payload: PatchShareRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        principal_type, principal_value = parse_principal_path(principal)
        if not principal_type:
            raise ApiError(400, "Invalid principal format")
        require_owned_file(db, user.id, file_id)

        share = db.execute(
            select(Share).where(
                Share.file_id == file_id,
                Share.principal_type == principal_type,
                Share.principal_value == principal_value,
            )
        ).scalars().first()
        if share is None:
            raise ApiError(404, "Share not found")

        changed = False
        if payload.permission is not None:
            if not is_valid_permission(payload.permission):
                raise ApiError(400, "permission must be read, download, or edit")
            share.permission = payload.permission
            changed = True
        if payload.expiryDays is not None:
            share.expires_at = _expiry_from_days(payload.expiryDays)
            changed = True
        if not changed:
            raise ApiError(400, "Nothing to update")
        db.flush()

        return 200, {
            "fileId": file_id,
            "principalType": principal_type,
            "principalValue": principal_value,
            "permission": share.permission,
            "expiresAt": iso(share.expires_at),
        }

    status, body = run_idempotent(db, user.id, f"shares-patch-{file_id}-{principal}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)


@router.delete("/v2/files/{file_id}/shares/{principal}")
def delete_share(
    file_id: str,
    principal: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        principal_type, principal_value = parse_principal_path(principal)
        if not principal_type:
            raise ApiError(400, "Invalid principal format")
        require_owned_file(db, user.id, file_id)

        share = db.execute(
            select(Share).where(
                Share.file_id == file_id,
                Share.principal_type == principal_type,
                Share.principal_value == principal_value,
            )
        ).scalars().first()
        if share is None:
            raise ApiError(404, "Share not found")

        db.delete(share)
        db.flush()
        return 200, {
            "message": "Share revoked",
            "fileId": file_id,
            "principalType": principal_type,
            "principalValue": principal_value,
        }

    status, body = run_idempotent(db, user.id, f"shares-delete-{file_id}-{principal}", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)
