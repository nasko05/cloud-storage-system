"""Apply an approved reorganization plan in one transaction.

The browser sends the ordered list of operations the user approved. We execute
them against the live database, reusing the same operation cores as the REST
routers, so every invariant (ownership, name conflicts, move-cycle prevention)
is enforced identically. Folders proposed earlier in the plan are resolvable as
destinations for later moves. Any failure raises ``ApiError``, which the
``get_db`` dependency turns into a full rollback — the plan is all-or-nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Folder
from ..services import (
    ROOT_FOLDER_ID,
    create_folder_core,
    move_or_rename_file_core,
    move_or_rename_folder_core,
)

if TYPE_CHECKING:
    from ..schemas import AgentOperation

MAX_OPERATIONS = 200


def apply_plan(db: Session, owner_id: str, operations: list[AgentOperation]) -> int:
    if len(operations) > MAX_OPERATIONS:
        raise ApiError(400, f"Too many operations in one plan (max {MAX_OPERATIONS})")

    # Normalised path -> folder id, for folders created earlier in this batch.
    created_paths: dict[str, str] = {}
    applied = 0
    for op in operations:
        _apply_one(db, owner_id, op, created_paths)
        applied += 1
    return applied


def _apply_one(db: Session, owner_id: str, op: AgentOperation, created_paths: dict[str, str]) -> None:
    if op.tool == "create_folder":
        parent_id = _resolve_folder_path(db, owner_id, op.parentPath, created_paths)
        folder = create_folder_core(db, owner_id, parent_id, op.name)
        created_paths[_join(op.parentPath, folder.name)] = folder.id
        return

    if op.tool in ("move_node", "rename_node"):
        if op.nodeType not in ("file", "folder"):
            raise ApiError(400, "nodeType must be 'file' or 'folder'")
        if not op.id:
            raise ApiError(400, f"{op.tool} requires an id")

        if op.tool == "move_node":
            if op.destinationPath is None:
                raise ApiError(400, "move_node requires a destinationPath")
            dest_id = _resolve_folder_path(db, owner_id, op.destinationPath, created_paths)
            if op.nodeType == "file":
                move_or_rename_file_core(db, owner_id, op.id, dest_folder_id=dest_id)
            else:
                move_or_rename_folder_core(db, owner_id, op.id, dest_folder_id=dest_id)
            return

        # rename_node
        if not op.newName:
            raise ApiError(400, "rename_node requires a newName")
        if op.nodeType == "file":
            move_or_rename_file_core(db, owner_id, op.id, new_name=op.newName)
        else:
            move_or_rename_folder_core(db, owner_id, op.id, new_name=op.newName)
        return

    raise ApiError(400, f"Unknown operation: {op.tool}")


def _segments(path: str | None) -> list[str]:
    if not path:
        return []
    return [seg for seg in path.replace("\\", "/").split("/") if seg and seg != "."]


def _join(parent_path: str | None, name: str) -> str:
    return "/" + "/".join([*_segments(parent_path), name])


def _resolve_folder_path(db: Session, owner_id: str, path: str | None, created_paths: dict[str, str]) -> str:
    segments = _segments(path)
    if any(seg == ".." for seg in segments):
        raise ApiError(400, "Invalid path (must be relative to the drive root, no '..')")
    if not segments:
        return ROOT_FOLDER_ID
    if ("/" + "/".join(segments)) in created_paths:
        return created_paths["/" + "/".join(segments)]

    current = ROOT_FOLDER_ID
    acc = ""
    for seg in segments:
        acc = f"{acc}/{seg}"
        if acc in created_paths:
            current = created_paths[acc]
            continue
        folder = db.execute(
            select(Folder).where(
                Folder.owner_id == owner_id,
                Folder.parent_folder_id == current,
                func.lower(Folder.name) == seg.lower(),
            )
        ).scalars().first()
        if folder is None:
            raise ApiError(404, f"Destination folder not found: {path}")
        current = folder.id
    return current
