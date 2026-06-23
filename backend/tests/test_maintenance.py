from datetime import timedelta

from conftest import register_and_login, upload_file

from app import storage
from app.database import SessionLocal
from app.maintenance import cleanup, run_cleanup_partial_uploads
from app.models import ArchiveJob, File, IdempotencyRecord, PublicLink, Share
from app.utils import now_utc


def _make_file(db, user_id, *, name, status, age_hours, storage_key="") -> str:
    file = File(
        owner_id=user_id,
        owner_email="o@o.com",
        filename=name,
        parent_folder_id="root",
        content_type="application/octet-stream",
        size=0,
        status=status,
        storage_key=storage_key,
        created_at=now_utc() - timedelta(hours=age_hours),
    )
    db.add(file)
    db.commit()
    return file.id


def test_cleanup_removes_expired_rows(client):
    token, user_id, _ = register_and_login(client)
    file_id = upload_file(client, token, "f.txt")

    past = now_utc() - timedelta(days=1)
    db = SessionLocal()
    try:
        db.add(Share(
            file_id=file_id, principal_type="email", principal_value="x@y.com",
            principal_display="x@y.com", permission="read", shared_by=user_id,
            shared_by_email="owner@y.com", expires_at=past,
        ))
        db.add(PublicLink(file_id=file_id, owner_id=user_id, owner_email="owner@y.com", expires_at=past))
        db.add(ArchiveJob(
            owner_id=user_id, status="ready", requested_file_ids=[], requested_folder_ids=[],
            expires_at=past,
        ))
        db.add(IdempotencyRecord(id="expired-1", status_code=200, response_body={}, expires_at=past))
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        counts = cleanup(db)
    finally:
        db.close()

    assert counts["shares"] >= 1
    assert counts["public_links"] >= 1
    assert counts["archive_jobs"] >= 1
    assert counts["idempotency"] >= 1


def test_cleanup_keeps_active_rows(client):
    token, user_id, _ = register_and_login(client)
    file_id = upload_file(client, token, "g.txt")
    future = now_utc() + timedelta(days=1)

    db = SessionLocal()
    try:
        db.add(PublicLink(file_id=file_id, owner_id=user_id, owner_email="o@o.com", expires_at=future))
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        counts = cleanup(db)
    finally:
        db.close()
    assert counts["public_links"] == 0


def test_cleanup_removes_stale_pending_uploads(client):
    token, user_id, _ = register_and_login(client)
    # A finalized upload that should never be touched.
    ready_id = upload_file(client, token, "keep.txt")

    # Stale pending upload with bytes already on disk.
    key = storage.file_key(user_id, "abandoned-id", "ghost.bin")
    storage.open_write(key).write_bytes(b"partial bytes")

    db = SessionLocal()
    try:
        stale_id = _make_file(db, user_id, name="ghost.bin", status="pending",
                              age_hours=48, storage_key=key)
        recent_id = _make_file(db, user_id, name="inflight.bin", status="pending",
                               age_hours=1)
    finally:
        db.close()

    db = SessionLocal()
    try:
        counts = cleanup(db)
    finally:
        db.close()

    assert counts["partial_uploads"] == 1
    db = SessionLocal()
    try:
        assert db.get(File, stale_id) is None       # old pending removed
        assert db.get(File, recent_id) is not None  # within 24h grace, kept
        assert db.get(File, ready_id) is not None    # finalized never touched
    finally:
        db.close()
    assert not storage.exists(key)                   # leftover bytes removed


def test_run_cleanup_partial_uploads_dry_run(client):
    token, user_id, _ = register_and_login(client)
    db = SessionLocal()
    try:
        fid = _make_file(db, user_id, name="abandoned.bin", status="pending", age_hours=48)
    finally:
        db.close()

    # Dry run reports the row but does not delete it.
    reported = run_cleanup_partial_uploads(0, dry_run=True)
    assert any(rid == fid for rid, _ in reported)
    db = SessionLocal()
    try:
        assert db.get(File, fid) is not None
    finally:
        db.close()

    # Real run removes it.
    removed = run_cleanup_partial_uploads(0)
    assert any(rid == fid for rid, _ in removed)
    db = SessionLocal()
    try:
        assert db.get(File, fid) is None
    finally:
        db.close()
