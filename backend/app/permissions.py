"""Share permission vocabulary."""

from __future__ import annotations

VALID_SHARE_PERMISSIONS = ("read", "download", "edit")
_DOWNLOADABLE = ("download", "edit")


def is_valid_permission(value: object) -> bool:
    return value in VALID_SHARE_PERMISSIONS


def can_download(permission: str | None) -> bool:
    return permission in _DOWNLOADABLE
