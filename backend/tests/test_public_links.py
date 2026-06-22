from conftest import auth_header, register_and_login, upload_file


def test_public_link_without_password(client):
    token, _, _ = register_and_login(client)
    file_id = upload_file(client, token, "public.txt", content=b"public-bytes")
    created = client.post(f"/v2/files/{file_id}/public-links", json={}, headers=auth_header(token)).json()
    link_token = created["token"]

    meta = client.get(f"/v2/public-links/{link_token}")
    assert meta.status_code == 200
    assert meta.json()["hasPassword"] is False

    dl = client.post(f"/v2/public-links/{link_token}/download", json={})
    assert dl.status_code == 200
    fetched = client.get(dl.json()["downloadUrl"].replace("http://testserver", ""))
    assert fetched.content == b"public-bytes"


def test_public_link_password_required(client):
    token, _, _ = register_and_login(client)
    file_id = upload_file(client, token, "secret.txt")
    created = client.post(
        f"/v2/files/{file_id}/public-links",
        json={"password": "letmein"},
        headers=auth_header(token),
    ).json()
    link_token = created["token"]

    assert client.post(f"/v2/public-links/{link_token}/download", json={}).status_code == 403
    assert client.post(
        f"/v2/public-links/{link_token}/download", json={"password": "wrong"}
    ).status_code == 403
    ok = client.post(f"/v2/public-links/{link_token}/download", json={"password": "letmein"})
    assert ok.status_code == 200


def test_public_link_delete(client):
    token, _, _ = register_and_login(client)
    file_id = upload_file(client, token, "temp.txt")
    headers = auth_header(token)
    link_token = client.post(f"/v2/files/{file_id}/public-links", json={}, headers=headers).json()["token"]

    client.delete(f"/v2/public-links/{link_token}", headers=headers)
    assert client.get(f"/v2/public-links/{link_token}").status_code == 404
