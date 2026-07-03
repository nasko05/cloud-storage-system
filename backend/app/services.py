"""Database query helpers shared across routers.

Centralising ownership checks, name-conflict detection and the derived
``isShared`` / ``hasPublicLink`` flags keeps the route handlers thin and free
of duplicated query logic.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .errors import ApiError
from .models import File, Folder, PublicLink, Share
from .utils import now_utc
from .validation import is_valid_name, normalize_folder_id

ROOT_FOLDER_ID = "root"


# --- Lookups ----------------------------------------------------------------

def get_file(db: Session, file_id: str) -> File | None:
    return db.get(File, file_id)


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


def collect_subtree(db: Session, owner_id: str, root_id: str) -> tuple[list[Folder], list[File]]:
    """BFS the folder tree under ``root_id`` (exclusive of the root itself),
    returning every owned descendant folder and file. Shared by recursive
    folder delete and archive collection."""
    folders: list[Folder] = []
    files: list[File] = []
    queue = deque([root_id])
    while queue:
        parent_id = queue.popleft()
        child_folders = db.execute(
            select(Folder).where(Folder.owner_id == owner_id, Folder.parent_folder_id == parent_id)
        ).scalars().all()
        for child in child_folders:
            folders.append(child)
            queue.append(child.id)
        files.extend(
            db.execute(
                select(File).where(File.owner_id == owner_id, File.parent_folder_id == parent_id)
            ).scalars().all()
        )
    return folders, files


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

def expiry_from_days(days: int | None) -> datetime:
    """Resolve an ``expiryDays`` payload value (``None`` means the configured
    default) into an absolute naive-UTC expiry, enforcing the 1–365 range.
    Shared by the share and public-link routers."""
    resolved = settings.share_expiry_days if days is None else days
    try:
        resolved = int(resolved)
    except (TypeError, ValueError):
        raise ApiError(400, "expiryDays must be an integer") from None
    if resolved < 1 or resolved > 365:
        raise ApiError(400, "expiryDays must be between 1 and 365")
    return now_utc() + timedelta(days=resolved)


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
        active_window(Share.expires_at, now),
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
        .where(Share.file_id.in_(file_ids), active_window(Share.expires_at, now))
        .distinct()
    ).scalars()
    for fid in shared_ids:
        flags[fid]["isShared"] = True

    linked_ids = db.execute(
        select(PublicLink.file_id)
        .where(PublicLink.file_id.in_(file_ids), active_window(PublicLink.expires_at, now))
        .distinct()
    ).scalars()
    for fid in linked_ids:
        flags[fid]["hasPublicLink"] = True

    return flags


def active_window(column, now: datetime):
    """SQL predicate for "not expired": a null expiry never expires."""
    return or_(column.is_(None), column > now)


# --- Operation cores --------------------------------------------------------
#
# The create / move / rename logic lives here as the single source of truth for
# the invariant checks, so the file/folder routers AND the AI agent's apply
# endpoint share identical behaviour. Each core validates and mutates within the
# caller's transaction (the routers wrap them in run_idempotent; the agent runs
# a batch of them under one get_db session). They never commit — that is the
# caller's job — so a failure mid-batch rolls the whole plan back.


def create_folder_core(db: Session, owner_id: str, parent_folder_id: str, name: str | None) -> Folder:
    """Create a folder under ``parent_folder_id``. Mirrors the checks in
    ``routers/folders.py:create_folder``."""
    if not folder_exists_for_owner(db, owner_id, parent_folder_id):
        raise ApiError(404, "Parent folder not found")
    if not is_valid_name(name) or name is None:
        raise ApiError(400, "Valid folder name required")
    clean = name.strip()
    if name_conflict(db, owner_id, parent_folder_id, Folder, clean):
        raise ApiError(409, "A folder with that name already exists in destination folder")
    folder = Folder(owner_id=owner_id, name=clean, parent_folder_id=parent_folder_id)
    db.add(folder)
    db.flush()
    return folder


def move_or_rename_file_core(
    db: Session,
    owner_id: str,
    file_id: str,
    *,
    new_name: str | None = None,
    dest_folder_id: str | None = None,
) -> tuple[File, bool]:
    """Rename and/or move a file. Returns ``(file, changed)`` so callers can
    report a no-op without re-deriving the target. Mirrors
    ``routers/files.py:patch_file``."""
    file = require_owned_file(db, owner_id, file_id)

    target_name = file.filename if new_name is None else new_name.strip()
    if not is_valid_name(target_name):
        raise ApiError(400, "Valid newName required")

    target_parent = file.parent_folder_id
    if dest_folder_id is not None:
        target_parent = normalize_folder_id(dest_folder_id)
    if not folder_exists_for_owner(db, owner_id, target_parent):
        raise ApiError(404, "Destination folder not found")
    if name_conflict(db, owner_id, target_parent, File, target_name, exclude_id=file_id):
        raise ApiError(409, "A file with that name already exists in destination folder")

    if target_name == file.filename and target_parent == file.parent_folder_id:
        return file, False

    file.filename = target_name
    file.parent_folder_id = target_parent
    db.flush()
    return file, True


def move_or_rename_folder_core(
    db: Session,
    owner_id: str,
    folder_id: str,
    *,
    new_name: str | None = None,
    dest_folder_id: str | None = None,
) -> tuple[Folder, bool]:
    """Rename and/or move a folder (carrying its subtree). Returns
    ``(folder, changed)``. Mirrors ``routers/folders.py:patch_folder``."""
    folder = require_owned_folder(db, owner_id, folder_id)

    target_name = folder.name if new_name is None else new_name.strip()
    if not is_valid_name(target_name):
        raise ApiError(400, "Valid newName required")

    target_parent = folder.parent_folder_id
    if dest_folder_id is not None:
        target_parent = normalize_folder_id(dest_folder_id)

    if target_parent == folder_id:
        raise ApiError(400, "Folder cannot be moved into itself")
    if not folder_exists_for_owner(db, owner_id, target_parent):
        raise ApiError(404, "Destination folder not found")
    if is_descendant_folder(db, owner_id, target_parent, folder_id):
        raise ApiError(400, "Cannot move folder into its own subfolder")
    if name_conflict(db, owner_id, target_parent, Folder, target_name, exclude_id=folder_id):
        raise ApiError(409, "A folder with that name already exists in destination folder")

    if target_name == folder.name and target_parent == folder.parent_folder_id:
        return folder, False

    folder.name = target_name
    folder.parent_folder_id = target_parent
    db.flush()
    return folder, True
