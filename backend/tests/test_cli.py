import os

from app.cli import export_db, import_db
from conftest import auth_header, register_and_login, upload_file


def test_export_import_round_trip(client, tmp_path):
    token, _, _ = register_and_login(client)
    client.post("/v2/folders/root/folders", json={"name": "Docs"}, headers=auth_header(token))
    upload_file(client, token, "keep.txt", content=b"data")

    backup = tmp_path / "backup.json"
    export_db(str(backup))
    assert backup.is_file() and os.path.getsize(backup) > 0

    # Re-import over the same database; data should remain intact afterwards.
    import_db(str(backup), replace=True)

    items = client.get("/v2/folders/root/children", headers=auth_header(token)).json()["items"]
    names = {item["name"] for item in items}
    assert {"Docs", "keep.txt"} <= names
