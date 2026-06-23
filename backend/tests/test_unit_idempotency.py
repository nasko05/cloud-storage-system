from datetime import timedelta

from app.config import settings
from app.database import SessionLocal
from app.idempotency import run_idempotent
from app.models import IdempotencyRecord
from app.utils import now_utc


def test_no_key_runs_action_each_time(client):
    db = SessionLocal()
    calls = []
    try:
        for _ in range(2):
            run_idempotent(db, "u", "scope", None, lambda: (calls.append(1), (200, {"n": len(calls)}))[1])
    finally:
        db.close()
    assert len(calls) == 2


def test_key_replays_first_response(client):
    db = SessionLocal()
    calls = []

    def action():
        calls.append(1)
        return 201, {"id": "first"}

    try:
        s1, b1 = run_idempotent(db, "u", "scope", "key-1", action)
        db.commit()
        s2, b2 = run_idempotent(db, "u", "scope", "key-1", action)
    finally:
        db.close()

    assert (s1, b1) == (201, {"id": "first"})
    assert (s2, b2) == (201, {"id": "first"})
    assert len(calls) == 1  # second call replayed, action not re-run


def test_expired_record_is_ignored(client):
    db = SessionLocal()
    try:
        # Pre-seed an expired record; the action should run again.
        rid_calls = []

        def action():
            rid_calls.append(1)
            return 200, {"ok": True}

        run_idempotent(db, "u", "scope", "k2", action)
        db.commit()
        # Expire it.
        rec = db.query(IdempotencyRecord).first()
        rec.expires_at = now_utc() - timedelta(seconds=settings.idempotency_ttl_seconds + 1)
        db.commit()

        run_idempotent(db, "u", "scope", "k2", action)
    finally:
        db.close()
    assert len(rid_calls) == 2
