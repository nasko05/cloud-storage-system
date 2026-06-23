import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from app import database
from app.config import settings


def test_upgrade_to_head_creates_schema(tmp_path, monkeypatch):
    db_file = tmp_path / "mig.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    database._upgrade_to_head()

    con = sqlite3.connect(db_file)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert {"users", "files", "folders", "alembic_version"} <= tables


def test_init_db_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "run_migrations", True)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("stmt", {}, Exception("not ready"))

    monkeypatch.setattr(database, "_upgrade_to_head", flaky)
    monkeypatch.setattr(database.time, "sleep", lambda _s: None)
    database.init_db(retries=5, delay=0)
    assert calls["n"] == 3


def test_init_db_gives_up(monkeypatch):
    monkeypatch.setattr(settings, "run_migrations", True)

    def always_fail():
        raise OperationalError("stmt", {}, Exception("never ready"))

    monkeypatch.setattr(database, "_upgrade_to_head", always_fail)
    monkeypatch.setattr(database.time, "sleep", lambda _s: None)
    with pytest.raises(RuntimeError):
        database.init_db(retries=2, delay=0)
