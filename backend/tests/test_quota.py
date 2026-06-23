from conftest import auth_header, register_and_login, upload_file

from app.config import settings


def test_quota_blocks_oversized_upload_at_init(client, monkeypatch):
    monkeypatch.setattr(settings, "user_quota_bytes", 10)
    token, _, _ = register_and_login(client)
    resp = client.post(
        "/v2/files/uploads",
        json={"filename": "big.bin", "size": 100},
        headers=auth_header(token),
    )
    assert resp.status_code == 413


def test_quota_allows_within_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "user_quota_bytes", 1000)
    token, _, _ = register_and_login(client)
    assert upload_file(client, token, "ok.txt", content=b"hello")


def test_quota_disabled_by_default(client):
    token, _, _ = register_and_login(client)
    # Default quota is 0 (unlimited); a large declared size is accepted.
    resp = client.post(
        "/v2/files/uploads",
        json={"filename": "huge.bin", "size": 10_000_000_000},
        headers=auth_header(token),
    )
    assert resp.status_code == 201
