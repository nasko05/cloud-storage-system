from conftest import auth_header, register_and_login, upload_file


def test_share_grants_download_by_email(client):
    owner_token, _, _ = register_and_login(client)
    recipient_token, _, recipient_email = register_and_login(client)
    file_id = upload_file(client, owner_token, "shared.txt", content=b"secret")

    # No share yet -> denied
    denied = client.post(f"/v2/download/files/{file_id}", json={}, headers=auth_header(recipient_token))
    assert denied.status_code == 403

    # Read-only share still cannot download
    client.put(
        f"/v2/files/{file_id}/shares/email:{recipient_email}",
        json={"permission": "read"},
        headers=auth_header(owner_token),
    )
    read_only = client.post(f"/v2/download/files/{file_id}", json={}, headers=auth_header(recipient_token))
    assert read_only.status_code == 403

    # Upgrade to download permission
    client.patch(
        f"/v2/files/{file_id}/shares/email:{recipient_email}",
        json={"permission": "download"},
        headers=auth_header(owner_token),
    )
    allowed = client.post(f"/v2/download/files/{file_id}", json={}, headers=auth_header(recipient_token))
    assert allowed.status_code == 200
    assert allowed.json()["accessType"] == "shared"


def test_inbound_shares_listing(client):
    owner_token, _, _ = register_and_login(client)
    recipient_token, _, recipient_email = register_and_login(client)
    file_id = upload_file(client, owner_token, "inbound.txt")
    client.put(
        f"/v2/files/{file_id}/shares/email:{recipient_email}",
        json={"permission": "download"},
        headers=auth_header(owner_token),
    )

    inbound = client.get("/v2/shares/inbound", headers=auth_header(recipient_token)).json()
    assert len(inbound["items"]) == 1
    assert inbound["items"][0]["fileId"] == file_id


def test_revoke_share(client):
    owner_token, _, _ = register_and_login(client)
    _, _, recipient_email = register_and_login(client)
    file_id = upload_file(client, owner_token, "revoke.txt")
    headers = auth_header(owner_token)

    client.put(f"/v2/files/{file_id}/shares/email:{recipient_email}", json={"permission": "read"}, headers=headers)
    shares = client.get(f"/v2/files/{file_id}/shares", headers=headers).json()
    assert len(shares["items"]) == 1

    client.delete(f"/v2/files/{file_id}/shares/email:{recipient_email}", headers=headers)
    shares = client.get(f"/v2/files/{file_id}/shares", headers=headers).json()
    assert shares["items"] == []
