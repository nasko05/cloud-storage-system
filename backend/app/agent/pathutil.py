"""Drive-path helpers shared by the agent's read-only tools and the apply
endpoint, so both sides split and resolve '/'-relative paths identically."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Folder


def path_segments(path: str | None) -> list[str]:
    """Split a '/'-relative drive path into clean segments (empty and ``.``
    segments dropped; backslashes normalised)."""
    if not path:
        return []
    return [seg for seg in path.replace("\\", "/").split("/") if seg and seg != "."]


def find_child_folder(db: Session, owner_id: str, parent_id: str, name: str) -> Folder | None:
    """Case-insensitive lookup of an owned child folder by name."""
    return db.execute(
        select(Folder).where(
            Folder.owner_id == owner_id,
            Folder.parent_folder_id == parent_id,
            func.lower(Folder.name) == name.lower(),
        )
    ).scalars().first()
