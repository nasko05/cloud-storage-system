import pytest

import app.maintenance as m


def test_start_scheduler_spawns_once(monkeypatch):
    m._started.clear()
    started = []

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target

        def start(self):
            started.append(self.target)

    monkeypatch.setattr(m.threading, "Thread", FakeThread)
    m.start_scheduler()
    m.start_scheduler()  # idempotent
    assert len(started) == 1
    m._started.clear()


def test_run_one_iteration_with_backup(monkeypatch):
    seq = iter([1000.0, 1000.0 + 10**9, 1000.0 + 10**9])
    monkeypatch.setattr(m.time, "time", lambda: next(seq))
    cleaned, backed = [], []
    monkeypatch.setattr(m, "run_cleanup", lambda: cleaned.append(1))
    monkeypatch.setattr(m.backup, "create_backup", lambda: backed.append(1))
    monkeypatch.setattr(m.settings, "maintenance_interval_minutes", 1)
    monkeypatch.setattr(m.settings, "backup_interval_hours", 24)
    monkeypatch.setattr(m.time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        m._run()
    assert cleaned == [1] and backed == [1]


def test_run_skips_backup_when_disabled(monkeypatch):
    monkeypatch.setattr(m.time, "time", lambda: 1000.0)
    monkeypatch.setattr(m, "run_cleanup", lambda: None)
    called = []
    monkeypatch.setattr(m.backup, "create_backup", lambda: called.append(1))
    monkeypatch.setattr(m.settings, "backup_interval_hours", 0)
    monkeypatch.setattr(m.time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        m._run()
    assert called == []


def test_run_survives_cleanup_error(monkeypatch):
    monkeypatch.setattr(m.time, "time", lambda: 1000.0)
    monkeypatch.setattr(m, "run_cleanup", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(m.settings, "backup_interval_hours", 0)
    monkeypatch.setattr(m.time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        m._run()  # cleanup error is swallowed; loop continues to sleep
