import pytest

from app import dbio
from app.database import SessionLocal
from app.models import User


def test_export_import_dict_round_trip(client):
    db = SessionLocal()
    try:
        db.add(User(id="u1", email="u1@e.com", password_hash="h", is_confirmed=True))
        db.commit()
    finally:
        db.close()

    payload = dbio.export_to_dict()
    assert payload["version"] == dbio.EXPORT_VERSION
    assert len(payload["tables"]["users"]) == 1

    dbio.import_from_dict(payload, replace=True)
    db = SessionLocal()
    try:
        assert db.get(User, "u1").email == "u1@e.com"
    finally:
        db.close()


def test_import_rejects_unknown_version(client):
    with pytest.raises(ValueError):
        dbio.import_from_dict({"version": 999, "tables": {}}, replace=True)


def test_export_db_and_import_db_files(client, tmp_path):
    db = SessionLocal()
    try:
        db.add(User(id="u2", email="u2@e.com", password_hash="h", is_confirmed=True))
        db.commit()
    finally:
        db.close()
    path = tmp_path / "dump.json"
    assert dbio.export_db(str(path)) >= 1
    assert dbio.import_db(str(path), replace=True) >= 1
