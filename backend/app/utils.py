"""Small shared helpers for time handling and active-window checks.

All persisted datetimes are *naive UTC*. Storing naive-UTC keeps comparisons
unambiguous across SQLite (tests) and PostgreSQL (production) without timezone
coercion surprises; :func:`iso` re-attaches the ``Z`` suffix on the way out.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc() -> datetime:
    """Current time as a naive UTC datetime (the canonical stored form)."""
    return datetime.utcnow()


def iso(value: datetime | None) -> str | None:
    """Serialise a (naive UTC) datetime as RFC3339 with a ``Z`` suffix."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.isoformat() + "Z"


def is_active(expires_at: datetime | None, *, reference: datetime | None = None) -> bool:
    """A null expiry never expires; otherwise it must be in the future."""
    if expires_at is None:
        return True
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
    return expires_at > (reference or now_utc())
