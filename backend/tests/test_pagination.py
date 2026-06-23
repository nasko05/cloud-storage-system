from conftest import auth_header, register_and_login, upload_file


def _list_all(client, token, folder_id="root", limit=2):
    """Walk the cursor like the real frontend does, collecting every item."""
    items = []
    cursor = None
    while True:
        url = f"/v2/folders/{folder_id}/children?limit={limit}"
        if cursor:
            url += f"&cursor={cursor}"
        page = client.get(url, headers=auth_header(token)).json()
        items.extend(page["items"])
        cursor = page.get("nextCursor")
        if not cursor:
            break
    return items


def test_lazy_pagination_walks_folders_then_files(client):
    token, _, _ = register_and_login(client)
    headers = auth_header(token)

    folder_names = ["alpha", "bravo", "charlie"]
    for name in folder_names:
        client.post("/v2/folders/root/folders", json={"name": name}, headers=headers)
    file_names = ["a.txt", "b.txt", "c.txt", "d.txt"]
    for name in file_names:
        upload_file(client, token, name)

    items = _list_all(client, token, limit=2)

    # No duplicates or gaps across pages.
    assert len(items) == len(folder_names) + len(file_names)
    folders = [i for i in items if i["type"] == "folder"]
    files = [i for i in items if i["type"] == "file"]
    assert [f["name"] for f in folders] == folder_names              # sorted, all present
    assert [f["name"] for f in files] == file_names
    # Folders are streamed before files.
    assert items[len(folder_names) - 1]["type"] == "folder"
    assert items[len(folder_names)]["type"] == "file"


def test_pagination_single_page_when_under_limit(client):
    token, _, _ = register_and_login(client)
    upload_file(client, token, "only.txt")
    page = client.get("/v2/folders/root/children?limit=50", headers=auth_header(token)).json()
    assert len(page["items"]) == 1
    assert page["nextCursor"] is None
