"""Pytest fixtures: an isolated SQLite + temp-storage TestClient.

Environment variables are set *before* the app package is imported so the
settings singleton and SQLAlchemy engine bind to throwaway resources.
"""

from __future__ import annotations

import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="drive-tests-")
os.environ.setdefault("DRIVE_SECRET_KEY", "test-secret")
os.environ.setdefault("DRIVE_SERVE_FRONTEND", "false")
os.environ.setdefault("DRIVE_DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("DRIVE_STORAGE_DIR", f"{_TMP}/blobs")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def register_and_login(client: TestClient, email: str | None = None, password: str = "password123"):
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/v2/auth/register", json={"email": email, "password": password})
    resp = client.post("/v2/auth/login", json={"email": email, "password": password})
    body = resp.json()
    return body["token"], body["userId"], email


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def upload_file(client: TestClient, token: str, name: str, content: bytes = b"hello", parent: str | None = None):
    """Run the full init -> PUT bytes -> finalize flow; return the fileId."""
    headers = auth_header(token)
    init = client.post(
        "/v2/files/uploads",
        json={"filename": name, "contentType": "text/plain", "size": len(content), "parentFolderId": parent},
        headers=headers,
    ).json()
    upload_url = init["uploadUrl"].replace("http://testserver", "")
    client.put(upload_url, content=content)
    client.post(f"/v2/files/{init['fileId']}/finalize", json={}, headers=headers)
    return init["fileId"]
