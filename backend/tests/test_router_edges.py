from datetime import timedelta

from conftest import auth_header, register_and_login, upload_file

from app import storage
from app.config import settings
from app.database import SessionLocal
from app.models import File, PublicLink
from app.security import create_signed_token
from app.utils import now_utc

# --- auth -------------------------------------------------------------------

def test_unauthorized_variants(client):
    assert client.get("/v2/folders/root/children").status_code == 401
    assert client.get("/v2/folders/root/children", headers={"Authorization": "Basic x"}).status_code == 401
    assert client.get("/v2/folders/root/children", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_validation_error_returns_400(client):
    assert client.post("/v2/auth/register", json={"email": "not-an-email", "password": "password123"}).status_code == 400
    assert client.post("/v2/auth/login", json={}).status_code == 400


def test_confirmation_flow(client, monkeypatch):
    monkeypatch.setattr(settings, "require_email_confirmation", True)
    reg = client.post("/v2/auth/register", json={"email": "c@e.com", "password": "password123"})
    assert reg.json()["confirmationRequired"] is True

    # Cannot log in before confirming.
    assert client.post("/v2/auth/login", json={"email": "c@e.com", "password": "password123"}).status_code == 403
    # Wrong code rejected.
    assert client.post("/v2/auth/confirm", json={"email": "c@e.com", "code": "000000"}).status_code == 400
    # Unknown account.
    assert client.post("/v2/auth/confirm", json={"email": "nobody@e.com", "code": "1"}).status_code == 404

    db = SessionLocal()
    try:
        from sqlalchemy import select

        from app.models import User
        code = db.execute(select(User.confirmation_code).where(User.email == "c@e.com")).scalar()
    finally:
        db.close()
    assert client.post("/v2/auth/confirm", json={"email": "c@e.com", "code": code}).status_code == 200
    assert client.post("/v2/auth/login", json={"email": "c@e.com", "password": "password123"}).status_code == 200


# --- files ------------------------------------------------------------------

def test_file_patch_edges(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    fid = upload_file(client, token, "a.txt")
    upload_file(client, token, "b.txt")

    assert client.patch(f"/v2/files/{fid}", json={}, headers=h).status_code == 400  # nothing
    assert client.patch(f"/v2/files/{fid}", json={"newName": "a.txt"}, headers=h).json()["message"] == "No changes"
    assert client.patch(f"/v2/files/{fid}", json={"newName": "b.txt"}, headers=h).status_code == 409  # conflict
    assert client.patch(f"/v2/files/{fid}", json={"newName": "../x"}, headers=h).status_code == 400
    assert client.patch(f"/v2/files/{fid}", json={"destinationFolderId": "ghost"}, headers=h).status_code == 404


def test_file_delete_requires_owner(client):
    owner, _, _ = register_and_login(client)
    other, _, _ = register_and_login(client)
    fid = upload_file(client, owner, "x.txt")
    assert client.delete(f"/v2/files/{fid}", headers=auth_header(other)).status_code == 404


# --- folders ----------------------------------------------------------------

def test_folder_edges(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    assert client.post("/v2/folders/root/folders", json={"name": "../bad"}, headers=h).status_code == 400
    assert client.post("/v2/folders/ghost/folders", json={"name": "X"}, headers=h).status_code == 404
    fid = client.post("/v2/folders/root/folders", json={"name": "X"}, headers=h).json()["folderId"]
    assert client.patch(f"/v2/folders/{fid}", json={}, headers=h).status_code == 400
    assert client.patch(f"/v2/folders/{fid}", json={"newName": "X"}, headers=h).json()["message"] == "No changes"
    assert client.patch(f"/v2/folders/{fid}", json={"destinationFolderId": fid}, headers=h).status_code == 400
    assert client.delete("/v2/folders/root", headers=h).status_code == 400
    assert client.get("/v2/folders/ghost/children", headers=h).status_code == 404


# --- shares -----------------------------------------------------------------

def test_share_edges(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    fid = upload_file(client, token, "s.txt")

    assert client.put(f"/v2/files/{fid}/shares/bogus:val", json={"permission": "read"}, headers=h).status_code == 400
    assert client.put(f"/v2/files/{fid}/shares/email:a@b.com", json={"permission": "boss"}, headers=h).status_code == 400
    assert client.put(f"/v2/files/{fid}/shares/email:a@b.com", json={"permission": "read", "expiryDays": 9999}, headers=h).status_code == 400
    assert client.patch(f"/v2/files/{fid}/shares/email:a@b.com", json={}, headers=h).status_code == 404  # no share yet
    client.put(f"/v2/files/{fid}/shares/email:a@b.com", json={"permission": "read"}, headers=h)
    assert client.patch(f"/v2/files/{fid}/shares/email:a@b.com", json={}, headers=h).status_code == 400  # nothing to update
    assert client.delete(f"/v2/files/{fid}/shares/email:nobody@b.com", headers=h).status_code == 404


# --- public links -----------------------------------------------------------

def test_public_link_admin_edges(client):
    owner, _, _ = register_and_login(client)
    other, _, _ = register_and_login(client)
    fid = upload_file(client, owner, "p.txt")
    token = client.post(f"/v2/files/{fid}/public-links", json={}, headers=auth_header(owner)).json()["token"]

    assert client.patch(f"/v2/public-links/{token}", json={}, headers=auth_header(owner)).status_code == 400
    assert client.patch(f"/v2/public-links/{token}", json={"expiryDays": 1}, headers=auth_header(other)).status_code == 404
    assert client.delete("/v2/public-links/ghost", headers=auth_header(owner)).status_code == 404
    assert client.post(f"/v2/files/{fid}/public-links", json={}, headers=auth_header(other)).status_code == 404


def test_public_download_edges(client):
    owner, _, _ = register_and_login(client)
    h = auth_header(owner)
    assert client.get("/v2/public-links/ghost").status_code == 404

    fid = upload_file(client, owner, "pd.txt", content=b"x")
    token = client.post(f"/v2/files/{fid}/public-links", json={}, headers=h).json()["token"]

    # Expire the link in the DB -> 410.
    db = SessionLocal()
    try:
        link = db.get(PublicLink, token)
        link.expires_at = now_utc() - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    assert client.get(f"/v2/public-links/{token}").status_code == 410
    assert client.post(f"/v2/public-links/{token}/download", json={}).status_code == 410


def test_public_download_not_ready(client):
    owner, _, _ = register_and_login(client)
    h = auth_header(owner)
    # Pending file (init only, no finalize) with a public link.
    init = client.post("/v2/files/uploads", json={"filename": "pend.txt", "size": 3}, headers=h).json()
    token = client.post(f"/v2/files/{init['fileId']}/public-links", json={}, headers=h).json()["token"]
    assert client.post(f"/v2/public-links/{token}/download", json={}).status_code == 409


# --- download ---------------------------------------------------------------

def test_download_edges(client):
    owner, _, _ = register_and_login(client)
    other, _, _ = register_and_login(client)
    h = auth_header(owner)

    assert client.post("/v2/download/files/ghost", json={}, headers=h).status_code == 404
    fid = upload_file(client, owner, "d.txt", content=b"data")
    assert client.post(f"/v2/download/files/{fid}", json={}, headers=auth_header(other)).status_code == 404

    # Remove the blob from disk -> 404 from storage.
    db = SessionLocal()
    try:
        key = db.get(File, fid).storage_key
    finally:
        db.close()
    storage.delete(key)
    assert client.post(f"/v2/download/files/{fid}", json={}, headers=h).status_code == 404


def test_download_of_unfinalized_upload_is_conflict(client):
    """Uploaded bytes that never went through finalize (antivirus + quota
    re-check) must not become downloadable as a side effect of asking."""
    owner, _, _ = register_and_login(client)
    h = auth_header(owner)
    init = client.post(
        "/v2/files/uploads",
        json={"filename": "pending.txt", "contentType": "text/plain", "size": 4},
        headers=h,
    ).json()
    assert client.put(init["uploadUrl"].replace("http://testserver", ""), content=b"data").status_code == 200

    resp = client.post(f"/v2/download/files/{init['fileId']}", json={}, headers=h)
    assert resp.status_code == 409


# --- blobs ------------------------------------------------------------------

def test_blob_token_validation(client):
    assert client.put("/v2/blob/upload?token=bad").status_code == 403
    assert client.get("/v2/blob/download?token=bad").status_code == 403
    # Valid signature but the file does not exist on disk -> 404.
    token = create_signed_token({"action": "download", "key": "v2/files/x/y/z", "filename": "z"}, 60)
    assert client.get(f"/v2/blob/download?token={token}").status_code == 404
