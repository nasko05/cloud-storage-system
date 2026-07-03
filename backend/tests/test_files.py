from conftest import auth_header, register_and_login, upload_file


def test_upload_lifecycle_and_listing(client):
    token, _, _ = register_and_login(client)
    headers = auth_header(token)

    init = client.post(
        "/v2/files/uploads",
        json={"filename": "report.txt", "contentType": "text/plain", "size": 11},
        headers=headers,
    )
    assert init.status_code == 201
    file_id = init.json()["fileId"]

    # Finalize before bytes exist -> 409
    assert client.post(f"/v2/files/{file_id}/finalize", json={}, headers=headers).status_code == 409

    upload_url = init.json()["uploadUrl"].replace("http://testserver", "")
    assert client.put(upload_url, content=b"hello world").status_code == 200

    final = client.post(f"/v2/files/{file_id}/finalize", json={}, headers=headers)
    assert final.status_code == 200
    assert final.json()["status"] == "ready"
    assert final.json()["size"] == 11

    listing = client.get("/v2/folders/root/children", headers=headers).json()
    names = [item["filename"] for item in listing["items"]]
    assert "report.txt" in names


def test_duplicate_filename_conflict(client):
    token, _, _ = register_and_login(client)
    upload_file(client, token, "dup.txt")
    resp = client.post(
        "/v2/files/uploads",
        json={"filename": "dup.txt", "size": 1},
        headers=auth_header(token),
    )
    assert resp.status_code == 409


def test_invalid_filename_rejected(client):
    token, _, _ = register_and_login(client)
    resp = client.post(
        "/v2/files/uploads",
        json={"filename": "../evil.txt", "size": 1},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_rename_and_delete(client):
    token, _, _ = register_and_login(client)
    file_id = upload_file(client, token, "old.txt")
    headers = auth_header(token)

    renamed = client.patch(f"/v2/files/{file_id}", json={"newName": "new.txt"}, headers=headers)
    assert renamed.status_code == 200
    assert renamed.json()["filename"] == "new.txt"

    assert client.delete(f"/v2/files/{file_id}", headers=headers).status_code == 200
    listing = client.get("/v2/folders/root/children", headers=headers).json()
    assert listing["items"] == []


def test_download_url_round_trip(client):
    token, _, _ = register_and_login(client)
    file_id = upload_file(client, token, "data.txt", content=b"payload-bytes")
    headers = auth_header(token)

    resp = client.post(f"/v2/download/files/{file_id}", json={}, headers=headers)
    assert resp.status_code == 200
    download_url = resp.json()["downloadUrl"].replace("http://testserver", "")
    fetched = client.get(download_url)
    assert fetched.status_code == 200
    assert fetched.content == b"payload-bytes"
