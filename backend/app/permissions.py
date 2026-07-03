"""Share permission vocabulary."""

from __future__ import annotations

from typing import Literal, get_args

SharePermission = Literal["read", "download", "edit"]

VALID_SHARE_PERMISSIONS: tuple[str, ...] = get_args(SharePermission)
_DOWNLOADABLE = ("download", "edit")


def is_valid_permission(value: object) -> bool:
    return value in VALID_SHARE_PERMISSIONS


def can_download(permission: str | None) -> bool:
    return permission in _DOWNLOADABLE
