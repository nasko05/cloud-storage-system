"""Database query helpers shared across routers.

Centralising ownership checks, name-conflict detection and the derived
``isShared`` / ``hasPublicLink`` flags keeps the route handlers thin and free
of duplicated query logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .errors import ApiError
from .models import File, Folder, PublicLink, Share
from .utils import now_utc

ROOT_FOLDER_ID = "root"


# --- Lookups ----------------------------------------------------------------

def get_file(db: Session, file_id: str) -> File | None:
    return db.get(File, file_id)


def get_folder(db: Session, folder_id: str) -> Folder | None:
    return db.get(Folder, folder_id)


def require_owned_file(db: Session, user_id: str, file_id: str) -> File:
    file = db.get(File, file_id)
    if file is None:
        raise ApiError(404, "File not found")
    if file.owner_id != user_id:
        raise ApiError(403, "Access denied")
    return file


def require_owned_folder(db: Session, user_id: str, folder_id: str) -> Folder:
    if folder_id == ROOT_FOLDER_ID:
        raise ApiError(400, "Root folder cannot be modified")
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise ApiError(404, "Folder not found")
    if folder.owner_id != user_id:
        raise ApiError(403, "Access denied")
    return folder


def folder_exists_for_owner(db: Session, user_id: str, folder_id: str) -> bool:
    if folder_id == ROOT_FOLDER_ID:
        return True
    folder = db.get(Folder, folder_id)
    return folder is not None and folder.owner_id == user_id


def user_storage_usage(db: Session, user_id: str, *, exclude_file_id: str | None = None) -> int:
    """Total bytes stored by a user (sum of file sizes)."""
    stmt = select(func.coalesce(func.sum(File.size), 0)).where(File.owner_id == user_id)
    if exclude_file_id is not None:
        stmt = stmt.where(File.id != exclude_file_id)
    return int(db.scalar(stmt) or 0)


# --- Invariants -------------------------------------------------------------

def name_conflict(
    db: Session,
    owner_id: str,
    parent_folder_id: str,
    model: type[File] | type[Folder],
    name: str,
    *,
    exclude_id: str | None = None,
) -> bool:
    name_column = getattr(model, "filename" if model is File else "name")
    stmt = select(model.id).where(
        model.owner_id == owner_id,
        model.parent_folder_id == parent_folder_id,
        func.lower(name_column) == name.strip().lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    return db.execute(stmt.limit(1)).first() is not None


def is_descendant_folder(
    db: Session, owner_id: str, candidate_parent_id: str, source_folder_id: str
) -> bool:
    """True if ``candidate_parent_id`` is ``source_folder_id`` or below it."""
    current = candidate_parent_id
    seen: set[str] = set()
    while current and current != ROOT_FOLDER_ID:
        if current == source_folder_id or current in seen:
            return True
        seen.add(current)
        folder = db.get(Folder, current)
        if folder is None or folder.owner_id != owner_id:
            return False
        current = folder.parent_folder_id
    return False


# --- Shares -----------------------------------------------------------------

def active_share(
    db: Session, file_id: str, principals: Iterable[tuple[str, str]]
) -> Share | None:
    clauses = [
        (Share.principal_type == ptype) & (Share.principal_value == pvalue)
        for ptype, pvalue in principals
    ]
    if not clauses:
        return None
    now = now_utc()
    stmt = select(Share).where(
        Share.file_id == file_id,
        or_(*clauses),
        _active_window(Share.expires_at, now),
    )
    return db.execute(stmt).scalars().first()


def derive_file_flags(db: Session, file_ids: list[str]) -> dict[str, dict[str, bool]]:
    """Return ``{file_id: {isShared, hasPublicLink}}`` for a page of files."""
    flags = {fid: {"isShared": False, "hasPublicLink": False} for fid in file_ids}
    if not file_ids:
        return flags

    now = now_utc()
    shared_ids = db.execute(
        select(Share.file_id)
        .where(Share.file_id.in_(file_ids), _active_window(Share.expires_at, now))
        .distinct()
    ).scalars()
    for fid in shared_ids:
        flags[fid]["isShared"] = True

    linked_ids = db.execute(
        select(PublicLink.file_id)
        .where(PublicLink.file_id.in_(file_ids), _active_window(PublicLink.expires_at, now))
        .distinct()
    ).scalars()
    for fid in linked_ids:
        flags[fid]["hasPublicLink"] = True

    return flags


def _active_window(column, now: datetime):
    return or_(column.is_(None), column > now)
