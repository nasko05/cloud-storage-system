import time

from app.config import settings
from app.ratelimit import LoginRateLimiter


def test_lock_after_threshold_and_countdown(monkeypatch):
    limiter = LoginRateLimiter()
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    monkeypatch.setattr(settings, "login_lockout_seconds", 50)

    for _ in range(2):
        limiter.register_failure("a@b.com", "1.1.1.1")
    assert limiter.check_locked("a@b.com", "1.1.1.1") == 0  # not yet

    limiter.register_failure("a@b.com", "1.1.1.1")  # third -> lock
    remaining = limiter.check_locked("a@b.com", "1.1.1.1")
    assert 0 < remaining <= 50


def test_success_resets(monkeypatch):
    limiter = LoginRateLimiter()
    monkeypatch.setattr(settings, "login_max_attempts", 2)
    limiter.register_failure("a@b.com", None)
    limiter.register_success("a@b.com", None)
    limiter.register_failure("a@b.com", None)  # counter restarted
    assert limiter.check_locked("a@b.com", None) == 0


def test_window_expiry_drops_old_failures(monkeypatch):
    limiter = LoginRateLimiter()
    monkeypatch.setattr(settings, "login_max_attempts", 2)
    monkeypatch.setattr(settings, "login_window_seconds", 1)
    limiter.register_failure("a@b.com", None)
    time.sleep(1.1)
    limiter.register_failure("a@b.com", None)  # old one outside window
    assert limiter.check_locked("a@b.com", None) == 0


def test_lockout_expiry_clears(monkeypatch):
    limiter = LoginRateLimiter()
    monkeypatch.setattr(settings, "login_max_attempts", 1)
    monkeypatch.setattr(settings, "login_lockout_seconds", 2)
    limiter.register_failure("a@b.com", None)
    assert limiter.check_locked("a@b.com", None) > 0
    time.sleep(2.2)
    assert limiter.check_locked("a@b.com", None) == 0
