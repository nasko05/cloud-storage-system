from datetime import timedelta

from conftest import register_and_login, upload_file

from app.database import SessionLocal
from app.maintenance import cleanup
from app.models import ArchiveJob, IdempotencyRecord, PublicLink, Share
from app.utils import now_utc


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
