"""Per-user file sharing with permission and expiry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..deps import CurrentUser, IdempotencyKey, get_current_user, get_db
from ..errors import ApiError
from ..idempotency import idempotent_response
from ..models import File, Share
from ..pagination import page_params, page_response
from ..permissions import is_valid_permission
from ..principals import parse_principal_path, user_principals
from ..schemas import (
    DeleteShareOut,
    FileShareOut,
    InboundShareOut,
    PatchShareRequest,
    PutShareRequest,
    ShareOut,
)
from ..services import active_window, expiry_from_days, require_owned_file
from ..utils import iso, now_utc

router = APIRouter(tags=["shares"])


def _parsed_principal(principal: str) -> tuple[str, str]:
    """Parse the ``{principal}`` path segment or fail with the shared 400."""
    principal_type, principal_value = parse_principal_path(principal)
    if not principal_type or not principal_value:
        raise ApiError(400, "Invalid principal format")
    return principal_type, principal_value


def _find_share(db: Session, file_id: str, principal_type: str, principal_value: str) -> Share | None:
    return db.execute(
        select(Share).where(
            Share.file_id == file_id,
            Share.principal_type == principal_type,
            Share.principal_value == principal_value,
        )
    ).scalars().first()


def _serialize_inbound(share: Share, file: File) -> dict:
    return InboundShareOut(
        fileId=share.file_id,
        filename=file.filename,
        ownerId=file.owner_id,
        ownerEmail=file.owner_email,
        permission=share.permission,
        principalType=share.principal_type,
        principalValue=share.principal_value,
        principalDisplay=share.principal_display,
        sharedAt=iso(share.shared_at),
        expiresAt=iso(share.expires_at),
    ).model_dump()


@router.get("/v2/shares/inbound")
def list_inbound_shares(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
) -> dict:
    page_size, offset = page_params(limit, cursor, default=50)

    principal_clauses = [
        (Share.principal_type == ptype) & (Share.principal_value == pvalue)
        for ptype, pvalue in user_principals(user)
    ]

    rows = db.execute(
        select(Share, File)
        .join(File, Share.file_id == File.id)
        .where(
            or_(*principal_clauses),
            active_window(Share.expires_at, now_utc()),
        )
        .order_by(Share.shared_at.desc(), Share.id)
        .offset(offset)
        .limit(page_size + 1)
    ).all()

    return page_response(rows, page_size, offset, lambda row: _serialize_inbound(row[0], row[1]))


@router.get("/v2/files/{file_id}/shares")
def list_file_shares(
    file_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
) -> dict:
    require_owned_file(db, user.id, file_id)
    page_size, offset = page_params(limit, cursor, default=50)

    shares = db.execute(
        select(Share)
        .where(Share.file_id == file_id, active_window(Share.expires_at, now_utc()))
        .order_by(Share.shared_at, Share.id)
        .offset(offset)
        .limit(page_size + 1)
    ).scalars().all()

    return page_response(
        shares,
        page_size,
        offset,
        lambda s: FileShareOut(
            principalType=s.principal_type,
            principalValue=s.principal_value,
            principalDisplay=s.principal_display,
            permission=s.permission,
            sharedAt=iso(s.shared_at),
            expiresAt=iso(s.expires_at),
        ).model_dump(),
    )


@router.put("/v2/files/{file_id}/shares/{principal}")
def put_share(
    file_id: str,
    principal: str,
    payload: PutShareRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        principal_type, principal_value = _parsed_principal(principal)
        if not is_valid_permission(payload.permission):
            raise ApiError(400, "permission must be read, download, or edit")

        require_owned_file(db, user.id, file_id)
        expires_at = expiry_from_days(payload.expiryDays)

        share = _find_share(db, file_id, principal_type, principal_value)
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

        return 200, ShareOut(
            fileId=file_id,
            principalType=principal_type,
            principalValue=principal_value,
            permission=payload.permission,
            expiresAt=iso(expires_at),
        ).model_dump()

    return idempotent_response(db, user.id, f"shares-put-{file_id}-{principal}", idempotency_key, action)


@router.patch("/v2/files/{file_id}/shares/{principal}")
def patch_share(
    file_id: str,
    principal: str,
    payload: PatchShareRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        principal_type, principal_value = _parsed_principal(principal)
        require_owned_file(db, user.id, file_id)

        share = _find_share(db, file_id, principal_type, principal_value)
        if share is None:
            raise ApiError(404, "Share not found")

        changed = False
        if payload.permission is not None:
            if not is_valid_permission(payload.permission):
                raise ApiError(400, "permission must be read, download, or edit")
            share.permission = payload.permission
            changed = True
        if payload.expiryDays is not None:
            share.expires_at = expiry_from_days(payload.expiryDays)
            changed = True
        if not changed:
            raise ApiError(400, "Nothing to update")
        db.flush()

        return 200, ShareOut(
            fileId=file_id,
            principalType=principal_type,
            principalValue=principal_value,
            permission=share.permission,
            expiresAt=iso(share.expires_at),
        ).model_dump()

    return idempotent_response(db, user.id, f"shares-patch-{file_id}-{principal}", idempotency_key, action)


@router.delete("/v2/files/{file_id}/shares/{principal}")
def delete_share(
    file_id: str,
    principal: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdempotencyKey,
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        principal_type, principal_value = _parsed_principal(principal)
        require_owned_file(db, user.id, file_id)

        share = _find_share(db, file_id, principal_type, principal_value)
        if share is None:
            raise ApiError(404, "Share not found")

        db.delete(share)
        db.flush()
        return 200, DeleteShareOut(
            message="Share revoked",
            fileId=file_id,
            principalType=principal_type,
            principalValue=principal_value,
        ).model_dump()

    return idempotent_response(db, user.id, f"shares-delete-{file_id}-{principal}", idempotency_key, action)
