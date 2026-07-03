"""End-to-end integration journeys spanning many endpoints."""

import time

from conftest import auth_header, register_and_login, upload_file


def _wait_archive(client, token, job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/v2/download/archives/{job_id}", headers=auth_header(token)).json()
        if status["status"] in ("ready", "failed", "expired"):
            return status
        time.sleep(0.2)
    raise AssertionError("archive timed out")


def _display_name(item):
    """Folders expose `name`, files expose `filename`."""
    return item["name"] if item["type"] == "folder" else item["filename"]


def test_full_owner_and_recipient_journey(client):
    owner, owner_id, _ = register_and_login(client)
    recipient, _, recipient_email = register_and_login(client)
    oh = auth_header(owner)

    # Build a nested folder tree and upload files.
    docs = client.post("/v2/folders/root/folders", json={"name": "Docs"}, headers=oh).json()["folderId"]
    sub = client.post(f"/v2/folders/{docs}/folders", json={"name": "2026"}, headers=oh).json()["folderId"]
    report = upload_file(client, owner, "report.txt", content=b"annual report", parent=sub)
    upload_file(client, owner, "root-note.txt", content=b"note")

    # Move + rename the file, then verify listing reflects it.
    assert client.patch(f"/v2/files/{report}", json={"newName": "annual.txt", "destinationFolderId": docs},
                        headers=oh).status_code == 200
    docs_items = client.get(f"/v2/folders/{docs}/children", headers=oh).json()["items"]
    assert any(i.get("filename") == "annual.txt" for i in docs_items)

    # Share with download permission; recipient sees it inbound and downloads it.
    client.put(f"/v2/files/{report}/shares/email:{recipient_email}",
               json={"permission": "download"}, headers=oh)
    inbound = client.get("/v2/shares/inbound", headers=auth_header(recipient)).json()["items"]
    assert inbound and inbound[0]["fileId"] == report
    dl = client.post(f"/v2/download/files/{report}", json={}, headers=auth_header(recipient))
    assert dl.status_code == 200 and dl.json()["accessType"] == "shared"
    body = client.get(dl.json()["downloadUrl"].replace("http://testserver", ""))
    assert body.content == b"annual report"

    # Public link with a password; anonymous flow.
    link = client.post(f"/v2/files/{report}/public-links",
                       json={"password": "open-sesame"}, headers=oh).json()["token"]
    meta = client.get(f"/v2/public-links/{link}").json()
    assert meta["hasPassword"] is True
    assert client.post(f"/v2/public-links/{link}/download", json={}).status_code == 403
    pub = client.post(f"/v2/public-links/{link}/download", json={"password": "open-sesame"})
    assert pub.status_code == 200

    # The file now reports both flags in listings.
    item = next(i for i in client.get(f"/v2/folders/{docs}/children", headers=oh).json()["items"]
                if i.get("fileId") == report)
    assert item["isShared"] and item["hasPublicLink"]

    # Archive the whole Docs tree and download the zip.
    created = client.post("/v2/download/archives", json={"fileIds": [], "folderIds": [docs]}, headers=oh)
    status = _wait_archive(client, owner, created.json()["archiveJobId"])
    assert status["status"] == "ready" and status["fileCount"] == 1
    assert client.get(status["downloadUrl"].replace("http://testserver", "")).status_code == 200

    # Revoke the share; recipient loses access.
    client.delete(f"/v2/files/{report}/shares/email:{recipient_email}", headers=oh)
    assert client.post(f"/v2/download/files/{report}", json={}, headers=auth_header(recipient)).status_code == 404

    # Recursively delete the tree; everything is gone.
    deleted = client.delete(f"/v2/folders/{docs}?recursive=true", headers=oh)
    assert deleted.status_code == 200 and deleted.json()["deletedFiles"] == 1
    remaining = {_display_name(i) for i in client.get("/v2/folders/root/children", headers=oh).json()["items"]}
    assert "Docs" not in remaining and "root-note.txt" in remaining


def test_idempotent_retry_is_safe(client):
    token, _, _ = register_and_login(client)
    headers = {**auth_header(token), "Idempotency-Key": "create-1"}
    first = client.post("/v2/folders/root/folders", json={"name": "Once"}, headers=headers)
    second = client.post("/v2/folders/root/folders", json={"name": "Once"}, headers=headers)
    assert first.json()["folderId"] == second.json()["folderId"]
