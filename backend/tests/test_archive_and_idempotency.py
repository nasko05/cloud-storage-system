import time

from conftest import auth_header, register_and_login, upload_file


def _wait_for_archive(client, token, job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/v2/download/archives/{job_id}", headers=auth_header(token)).json()
        if status["status"] in ("ready", "failed", "expired"):
            return status
        time.sleep(0.2)
    raise AssertionError("archive did not finish in time")


def test_archive_zip_round_trip(client):
    token, _, _ = register_and_login(client)
    headers = auth_header(token)
    folder = client.post("/v2/folders/root/folders", json={"name": "Box"}, headers=headers).json()["folderId"]
    upload_file(client, token, "one.txt", content=b"one", parent=folder)
    file_id = upload_file(client, token, "two.txt", content=b"two")

    created = client.post(
        "/v2/download/archives",
        json={"fileIds": [file_id], "folderIds": [folder]},
        headers=headers,
    )
    assert created.status_code == 202
    job_id = created.json()["archiveJobId"]

    status = _wait_for_archive(client, token, job_id)
    assert status["status"] == "ready"
    assert status["fileCount"] == 2

    zip_url = status["downloadUrl"].replace("http://testserver", "")
    assert client.get(zip_url).status_code == 200


def test_empty_archive_request_rejected(client):
    token, _, _ = register_and_login(client)
    resp = client.post("/v2/download/archives", json={"fileIds": [], "folderIds": []}, headers=auth_header(token))
    assert resp.status_code == 400


def test_idempotency_replays_response(client):
    token, _, _ = register_and_login(client)
    headers = {**auth_header(token), "Idempotency-Key": "folder-key-1"}

    first = client.post("/v2/folders/root/folders", json={"name": "Once"}, headers=headers)
    second = client.post("/v2/folders/root/folders", json={"name": "Once"}, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["folderId"] == second.json()["folderId"]

    # Without the key, the duplicate name now conflicts.
    conflict = client.post("/v2/folders/root/folders", json={"name": "Once"}, headers=auth_header(token))
    assert conflict.status_code == 409
