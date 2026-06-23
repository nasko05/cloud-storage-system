"""Input validation shared by file and folder routes."""

from __future__ import annotations

from .config import settings


def is_valid_name(value: object) -> bool:
    """Reject empty names, path separators, traversal and control characters."""
    if not isinstance(value, str):
        return False
    name = value.strip()
    if not name or len(name) > settings.max_filename_length:
        return False
    if "/" in name or "\\" in name or ".." in name or "\x00" in name:
        return False
    return True


def normalize_folder_id(value: object) -> str:
    if not value:
        return "root"
    return str(value).strip() or "root"
