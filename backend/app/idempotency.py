"""Idempotency-Key support for mutating routes.

When a client sends an ``Idempotency-Key`` header, the first successful
response is persisted and replayed for retries within the TTL window. Without
the header, the action simply runs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from .config import settings
from .models import IdempotencyRecord
from .utils import now_utc

ActionResult = tuple[int, dict]


def _record_id(user_id: str, scope: str, key: str) -> str:
    digest = hashlib.sha256(f"{user_id}:{scope}:{key}".encode()).hexdigest()
    return f"{scope}:{digest}"


def run_idempotent(
    db: Session,
    user_id: str,
    scope: str,
    idempotency_key: str | None,
    action: Callable[[], ActionResult],
) -> ActionResult:
    if not idempotency_key:
        return action()

    record_id = _record_id(user_id, scope, idempotency_key)
    now = now_utc()

    existing = db.get(IdempotencyRecord, record_id)
    if existing and existing.expires_at > now:
        return existing.status_code, existing.response_body

    status_code, body = action()

    record = IdempotencyRecord(
        id=record_id,
        status_code=status_code,
        response_body=body,
        expires_at=now + timedelta(seconds=settings.idempotency_ttl_seconds),
    )
    db.merge(record)
    db.flush()
    return status_code, body
