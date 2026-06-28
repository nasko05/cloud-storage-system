"""Transactional apply of an approved reorganization plan (POST /v2/agent/apply)."""

from conftest import auth_header, register_and_login, upload_file


def _children(client, headers, folder_id="root"):
    return client.get(f"/v2/folders/{folder_id}/children", headers=headers).json()["items"]


def _mk_folder(client, headers, name, parent="root"):
    return client.post(f"/v2/folders/{parent}/folders", json={"name": name}, headers=headers).json()["folderId"]


def test_apply_create_folder_then_move_file(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    fid = upload_file(client, token, "beach.jpg")

    ops = [
        {"tool": "create_folder", "parentPath": "/", "name": "Photos"},
        {"tool": "move_node", "nodeType": "file", "id": fid, "path": "/beach.jpg", "destinationPath": "/Photos"},
    ]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["applied"] == 2

    root = _children(client, h)
    assert not any(i.get("name") == "beach.jpg" for i in root)
    photos_id = next(i["folderId"] for i in root if i["type"] == "folder" and i["name"] == "Photos")
    assert any(i["name"] == "beach.jpg" for i in _children(client, h, photos_id))


def test_apply_nested_create_then_move(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    fid = upload_file(client, token, "img.png")

    ops = [
        {"tool": "create_folder", "parentPath": "/", "name": "Photos"},
        {"tool": "create_folder", "parentPath": "/Photos", "name": "2026"},
        {"tool": "move_node", "nodeType": "file", "id": fid, "destinationPath": "/Photos/2026"},
    ]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 200 and resp.json()["applied"] == 3

    photos_id = next(i["folderId"] for i in _children(client, h) if i["name"] == "Photos")
    y2026_id = next(i["folderId"] for i in _children(client, h, photos_id) if i["name"] == "2026")
    assert any(i["name"] == "img.png" for i in _children(client, h, y2026_id))


def test_apply_move_folder(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    dest = _mk_folder(client, h, "Archive")
    src = _mk_folder(client, h, "Old")

    ops = [{"tool": "move_node", "nodeType": "folder", "id": src, "destinationPath": "/Archive"}]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 200
    assert any(i["name"] == "Old" for i in _children(client, h, dest))


def test_apply_rename_file_and_folder(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    fid = upload_file(client, token, "old.txt")
    folder = _mk_folder(client, h, "OldFolder")

    ops = [
        {"tool": "rename_node", "nodeType": "file", "id": fid, "newName": "new.txt"},
        {"tool": "rename_node", "nodeType": "folder", "id": folder, "newName": "NewFolder"},
    ]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 200
    names = {i["name"] for i in _children(client, h)}
    assert "new.txt" in names and "NewFolder" in names


def test_apply_empty_plan_is_noop(client):
    token, _, _ = register_and_login(client)
    resp = client.post("/v2/agent/apply", json={"operations": []}, headers=auth_header(token))
    assert resp.status_code == 200 and resp.json()["applied"] == 0


# --- failure / rollback -----------------------------------------------------

def test_apply_name_conflict_rolls_back_whole_plan(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    _mk_folder(client, h, "Docs")

    ops = [
        {"tool": "create_folder", "parentPath": "/", "name": "New"},
        {"tool": "create_folder", "parentPath": "/", "name": "Docs"},  # conflict
    ]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 409

    names = {i["name"] for i in _children(client, h)}
    assert "Docs" in names and "New" not in names  # op 1 was rolled back


def test_apply_midbatch_failure_rolls_back(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)

    ops = [
        {"tool": "create_folder", "parentPath": "/", "name": "Keep"},
        {"tool": "move_node", "nodeType": "file", "id": "does-not-exist", "destinationPath": "/"},
    ]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 404
    assert not any(i["name"] == "Keep" for i in _children(client, h))


def test_apply_move_folder_into_descendant_rejected(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    a = _mk_folder(client, h, "A")
    _mk_folder(client, h, "B", parent=a)

    ops = [{"tool": "move_node", "nodeType": "folder", "id": a, "destinationPath": "/A/B"}]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 400


def test_apply_rejects_parent_traversal(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    fid = upload_file(client, token, "a.txt")
    ops = [{"tool": "move_node", "nodeType": "file", "id": fid, "destinationPath": "/../etc"}]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 400


def test_apply_too_many_operations(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    ops = [{"tool": "create_folder", "parentPath": "/", "name": f"F{i}"} for i in range(201)]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=h)
    assert resp.status_code == 400


def test_apply_foreign_node_denied(client):
    token_a, _, _ = register_and_login(client)
    fid = upload_file(client, token_a, "secret.txt")
    token_b, _, _ = register_and_login(client)

    ops = [{"tool": "rename_node", "nodeType": "file", "id": fid, "newName": "x.txt"}]
    resp = client.post("/v2/agent/apply", json={"operations": ops}, headers=auth_header(token_b))
    assert resp.status_code == 403


def test_apply_validation_errors(client):
    token, _, _ = register_and_login(client)
    h = auth_header(token)
    fid = upload_file(client, token, "a.txt")

    bad_plans = [
        [{"tool": "delete_node", "nodeType": "file", "id": fid}],  # unknown tool
        [{"tool": "move_node", "nodeType": "thing", "id": fid, "destinationPath": "/"}],  # bad nodeType
        [{"tool": "move_node", "nodeType": "file", "destinationPath": "/"}],  # missing id
        [{"tool": "move_node", "nodeType": "file", "id": fid}],  # missing destinationPath
        [{"tool": "rename_node", "nodeType": "file", "id": fid}],  # missing newName
    ]
    for plan in bad_plans:
        resp = client.post("/v2/agent/apply", json={"operations": plan}, headers=h)
        assert resp.status_code == 400, plan
