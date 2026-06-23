import pytest

import app.archive as A
from app import storage
from app.config import settings
from app.database import SessionLocal
from app.models import ArchiveJob, File, Folder, User


@pytest.fixture
def db(client):
    s = SessionLocal()
    yield s
    s.close()


def _user(db, uid="u1"):
    db.add(User(id=uid, email=f"{uid}@e.com", password_hash="x", is_confirmed=True))
    db.flush()


def _file(db, fid, owner="u1", name="a.txt", parent="root", size=4, key=None):
    db.add(File(
        id=fid, owner_id=owner, owner_email="o@e.com", filename=name, parent_folder_id=parent,
        storage_key=key or f"v2/files/{owner}/{fid}/{name}", size=size, status="ready",
    ))
    db.flush()


def test_collect_files_errors(db):
    _user(db)
    with pytest.raises(ValueError):  # nothing resolved
        A._collect_files(db, "u1", [], [])
    with pytest.raises(ValueError):  # missing file
        A._collect_files(db, "u1", ["ghost"], [])
    with pytest.raises(ValueError):  # missing folder
        A._collect_files(db, "u1", [], ["ghost"])


def test_collect_files_limits(db, monkeypatch):
    _user(db)
    _file(db, "f1", size=10)
    monkeypatch.setattr(settings, "max_archive_files", 0)
    with pytest.raises(ValueError):
        A._collect_files(db, "u1", ["f1"], [])
    monkeypatch.setattr(settings, "max_archive_files", 1000)
    monkeypatch.setattr(settings, "max_archive_total_bytes", 1)
    with pytest.raises(ValueError):
        A._collect_files(db, "u1", ["f1"], [])


def test_collect_files_folder_traversal(db):
    _user(db)
    db.add(Folder(id="d1", owner_id="u1", name="D", parent_folder_id="root"))
    db.flush()
    _file(db, "f1", parent="d1")
    _file(db, "f2", parent="root")
    files = A._collect_files(db, "u1", ["f2"], ["d1"])
    assert {f.id for f in files} == {"f1", "f2"}


def test_resolve_folder_path_and_arcname(db):
    _user(db)
    db.add(Folder(id="d1", owner_id="u1", name="Parent", parent_folder_id="root"))
    db.add(Folder(id="d2", owner_id="u1", name="Child", parent_folder_id="d1"))
    db.flush()
    cache = {}
    assert A._resolve_folder_path(db, "u1", "root", cache) == ""
    assert A._resolve_folder_path(db, "u1", "d2", cache) == "Parent/Child"
    assert A._resolve_folder_path(db, "u1", "d2", cache) == "Parent/Child"  # cached
    assert A._resolve_folder_path(db, "u1", "ghost", cache) == ""

    _file(db, "f1", name="a.txt", parent="d2")
    used: set[str] = set()
    first = A._arcname(db, db.get(File, "f1"), {}, used)
    assert first == "Parent/Child/a.txt"
    # Same logical name again -> deduplicated suffix.
    f2 = File(id="f2", owner_id="u1", owner_email="o", filename="a.txt", parent_folder_id="d2",
              storage_key="k", size=1, status="ready")
    second = A._arcname(db, f2, {"d2": "Parent/Child"}, used)
    assert second == "Parent/Child/a (1).txt"


def test_requeue_pending_and_start_worker(db, monkeypatch):
    _user(db)
    db.add(ArchiveJob(id="j1", owner_id="u1", status="queued",
                      requested_file_ids=[], requested_folder_ids=[]))
    db.commit()

    # drain any pre-existing queue items
    while not A._job_queue.empty():
        A._job_queue.get_nowait()

    A._requeue_pending()
    assert A._job_queue.get_nowait() == "j1"

    # start_worker spawns one daemon thread
    A._worker_started.clear()
    started = []

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            pass

        def start(self):
            started.append(1)

    monkeypatch.setattr(A.threading, "Thread", FakeThread)
    monkeypatch.setattr(A, "_requeue_pending", lambda: None)
    A.start_worker()
    A.start_worker()
    assert started == [1]
    A._worker_started.clear()


def test_process_success_and_failure(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    _user(db)
    _file(db, "f1", size=5)
    storage.open_write("v2/files/u1/f1/a.txt").write_bytes(b"hello")
    db.add(ArchiveJob(id="ok", owner_id="u1", status="queued",
                      requested_file_ids=["f1"], requested_folder_ids=[]))
    db.add(ArchiveJob(id="bad", owner_id="u1", status="queued",
                      requested_file_ids=["ghost"], requested_folder_ids=[]))
    db.commit()

    A._process("ok")
    A._process("bad")
    A._process("missing-job-id")  # no-op, must not raise

    db.expire_all()
    assert db.get(ArchiveJob, "ok").status == "ready"
    assert db.get(ArchiveJob, "ok").file_count == 1
    assert db.get(ArchiveJob, "bad").status == "failed"
    assert storage.exists(db.get(ArchiveJob, "ok").zip_key)
