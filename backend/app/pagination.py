"""Opaque offset-based cursor pagination.

The previous DynamoDB implementation exposed ``{items, nextCursor}`` with an
opaque base64 cursor. We keep that exact contract; the cursor now encodes an
integer offset, which is sufficient for the stable orderings used here.
"""

from __future__ import annotations

import base64


def normalize_limit(raw: object, default: int = 100, max_value: int = 200) -> int:
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if value < 1:
        return default
    return min(value, max_value)


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return max(0, int(base64.urlsafe_b64decode(padded).decode("ascii")))
    except (ValueError, TypeError):
        return 0


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).rstrip(b"=").decode("ascii")
