from conftest import auth_header, register_and_login, upload_file

from app import antivirus


def test_infected_upload_is_rejected(client, monkeypatch):
    monkeypatch.setattr(antivirus, "scan_file", lambda path: (False, "Eicar-Test-Signature"))
    token, _, _ = register_and_login(client)
    headers = auth_header(token)

    init = client.post(
        "/v2/files/uploads", json={"filename": "virus.txt", "size": 5}, headers=headers
    ).json()
    upload_url = init["uploadUrl"].replace("http://testserver", "")
    client.put(upload_url, content=b"nasty")

    rejected = client.post(f"/v2/files/{init['fileId']}/finalize", json={}, headers=headers)
    assert rejected.status_code == 422

    # The infected file is gone (row + bytes).
    assert client.get("/v2/folders/root/children", headers=headers).json()["items"] == []


def test_clean_upload_passes_when_disabled(client):
    # Antivirus is disabled by default -> scan is a no-op.
    token, _, _ = register_and_login(client)
    assert upload_file(client, token, "clean.txt")
