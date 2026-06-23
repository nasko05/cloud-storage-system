from datetime import timedelta

import pytest

from app import services
from app.database import SessionLocal
from app.errors import ApiError
from app.models import File, Folder, PublicLink, Share, User
from app.utils import now_utc


@pytest.fixture
def db(client):  # client creates the schema
    session = SessionLocal()
    yield session
    session.close()


def _user(db, uid="u1"):
    u = User(id=uid, email=f"{uid}@e.com", password_hash="x", is_confirmed=True)
    db.add(u)
    db.flush()
    return u


def _folder(db, owner, fid, name="F", parent="root"):
    f = Folder(id=fid, owner_id=owner, name=name, parent_folder_id=parent)
    db.add(f)
    db.flush()
    return f


def _file(db, owner, fid, name="a.txt", parent="root", size=10):
    f = File(
        id=fid, owner_id=owner, owner_email="o@e.com", filename=name,
        parent_folder_id=parent, storage_key=f"k/{fid}", size=size, status="ready",
    )
    db.add(f)
    db.flush()
    return f


def test_require_owned_file(db):
    _user(db)
    _file(db, "u1", "f1")
    assert services.require_owned_file(db, "u1", "f1").id == "f1"
    with pytest.raises(ApiError) as e1:
        services.require_owned_file(db, "u1", "missing")
    assert e1.value.status_code == 404
    with pytest.raises(ApiError) as e2:
        services.require_owned_file(db, "other", "f1")
    assert e2.value.status_code == 403


def test_require_owned_folder(db):
    _user(db)
    _folder(db, "u1", "d1")
    with pytest.raises(ApiError) as root_err:
        services.require_owned_folder(db, "u1", "root")
    assert root_err.value.status_code == 400
    with pytest.raises(ApiError) as nf:
        services.require_owned_folder(db, "u1", "nope")
    assert nf.value.status_code == 404
    with pytest.raises(ApiError) as denied:
        services.require_owned_folder(db, "other", "d1")
    assert denied.value.status_code == 403
    assert services.require_owned_folder(db, "u1", "d1").id == "d1"


def test_folder_exists_for_owner(db):
    _user(db)
    _folder(db, "u1", "d1")
    assert services.folder_exists_for_owner(db, "u1", "root") is True
    assert services.folder_exists_for_owner(db, "u1", "d1") is True
    assert services.folder_exists_for_owner(db, "other", "d1") is False
    assert services.folder_exists_for_owner(db, "u1", "ghost") is False


def test_name_conflict(db):
    _user(db)
    _file(db, "u1", "f1", name="dup.txt")
    _folder(db, "u1", "d1", name="Docs")
    assert services.name_conflict(db, "u1", "root", File, "dup.txt") is True
    assert services.name_conflict(db, "u1", "root", File, "DUP.TXT") is True  # case-insensitive
    assert services.name_conflict(db, "u1", "root", File, "dup.txt", exclude_id="f1") is False
    assert services.name_conflict(db, "u1", "root", Folder, "Docs") is True
    assert services.name_conflict(db, "u1", "root", Folder, "Other") is False


def test_is_descendant_folder(db):
    _user(db)
    _folder(db, "u1", "parent", parent="root")
    _folder(db, "u1", "child", parent="parent")
    _folder(db, "u1", "grandchild", parent="child")
    assert services.is_descendant_folder(db, "u1", "grandchild", "parent") is True
    assert services.is_descendant_folder(db, "u1", "parent", "child") is False
    # candidate owned by someone else -> stops, not a descendant
    _user(db, "other")
    _folder(db, "other", "x", parent="root")
    assert services.is_descendant_folder(db, "u1", "x", "parent") is False


def test_active_share_and_flags(db):
    _user(db)
    _file(db, "u1", "f1")
    _file(db, "u1", "f2")
    db.add(Share(
        id="s1", file_id="f1", principal_type="email", principal_value="b@e.com",
        principal_display="b@e.com", permission="download", shared_by="u1",
        shared_by_email="o@e.com", expires_at=now_utc() + timedelta(days=1),
    ))
    db.add(PublicLink(
        token="t1", file_id="f1", owner_id="u1", owner_email="o@e.com",
        expires_at=now_utc() + timedelta(days=1),
    ))
    db.add(Share(  # expired share on f2 -> inactive
        id="s2", file_id="f2", principal_type="email", principal_value="b@e.com",
        principal_display="b@e.com", permission="read", shared_by="u1",
        shared_by_email="o@e.com", expires_at=now_utc() - timedelta(days=1),
    ))
    db.flush()

    assert services.active_share(db, "f1", [("email", "b@e.com")]).permission == "download"
    assert services.active_share(db, "f1", []) is None
    assert services.active_share(db, "f2", [("email", "b@e.com")]) is None

    flags = services.derive_file_flags(db, ["f1", "f2"])
    assert flags["f1"] == {"isShared": True, "hasPublicLink": True}
    assert flags["f2"] == {"isShared": False, "hasPublicLink": False}
    assert services.derive_file_flags(db, []) == {}


def test_user_storage_usage(db):
    _user(db)
    _file(db, "u1", "f1", size=100)
    _file(db, "u1", "f2", size=50)
    assert services.user_storage_usage(db, "u1") == 150
    assert services.user_storage_usage(db, "u1", exclude_file_id="f2") == 100
    assert services.user_storage_usage(db, "nobody") == 0
