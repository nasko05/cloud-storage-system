from app.config import settings
from app.ratelimit import login_rate_limiter


def test_lockout_after_max_attempts(client, monkeypatch):
    login_rate_limiter.reset()
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    monkeypatch.setattr(settings, "login_lockout_seconds", 300)
    client.post("/v2/auth/register", json={"email": "rl@test.com", "password": "password123"})

    for _ in range(3):
        bad = client.post("/v2/auth/login", json={"email": "rl@test.com", "password": "wrongpass1"})
        assert bad.status_code == 401

    # Even the correct password is now refused while locked out.
    locked = client.post("/v2/auth/login", json={"email": "rl@test.com", "password": "password123"})
    assert locked.status_code == 429


def test_success_clears_failures(client, monkeypatch):
    login_rate_limiter.reset()
    monkeypatch.setattr(settings, "login_max_attempts", 5)
    client.post("/v2/auth/register", json={"email": "rl2@test.com", "password": "password123"})

    for _ in range(2):
        client.post("/v2/auth/login", json={"email": "rl2@test.com", "password": "wrongpass1"})

    ok = client.post("/v2/auth/login", json={"email": "rl2@test.com", "password": "password123"})
    assert ok.status_code == 200
