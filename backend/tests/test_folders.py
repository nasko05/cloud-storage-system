from conftest import auth_header, register_and_login, upload_file


def _create_folder(client, token, name, parent="root"):
    return client.post(
        f"/v2/folders/{parent}/folders", json={"name": name}, headers=auth_header(token)
    ).json()["folderId"]


def test_create_nested_and_list(client):
    token, _, _ = register_and_login(client)
    headers = auth_header(token)
    parent = _create_folder(client, token, "Documents")
    child = _create_folder(client, token, "Invoices", parent=parent)
    upload_file(client, token, "a.txt", parent=child)

    root_items = client.get("/v2/folders/root/children", headers=headers).json()["items"]
    assert any(i["type"] == "folder" and i["name"] == "Documents" for i in root_items)

    child_items = client.get(f"/v2/folders/{child}/children", headers=headers).json()["items"]
    assert any(i["type"] == "file" and i["filename"] == "a.txt" for i in child_items)


def test_non_recursive_delete_blocks_non_empty(client):
    token, _, _ = register_and_login(client)
    headers = auth_header(token)
    folder = _create_folder(client, token, "Full")
    upload_file(client, token, "inside.txt", parent=folder)

    blocked = client.delete(f"/v2/folders/{folder}", headers=headers)
    assert blocked.status_code == 409

    ok = client.delete(f"/v2/folders/{folder}?recursive=true", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["deletedFiles"] == 1


def test_cannot_move_folder_into_descendant(client):
    token, _, _ = register_and_login(client)
    headers = auth_header(token)
    parent = _create_folder(client, token, "Parent")
    child = _create_folder(client, token, "Child", parent=parent)

    resp = client.patch(f"/v2/folders/{parent}", json={"destinationFolderId": child}, headers=headers)
    assert resp.status_code == 400


def test_share_and_public_link_flags(client):
    token, user_id, _ = register_and_login(client)
    headers = auth_header(token)
    file_id = upload_file(client, token, "flagged.txt")

    client.put(
        f"/v2/files/{file_id}/shares/email:friend@example.com",
        json={"permission": "read"},
        headers=headers,
    )
    client.post(f"/v2/files/{file_id}/public-links", json={}, headers=headers)

    items = client.get("/v2/folders/root/children", headers=headers).json()["items"]
    target = next(i for i in items if i.get("fileId") == file_id)
    assert target["isShared"] is True
    assert target["hasPublicLink"] is True
