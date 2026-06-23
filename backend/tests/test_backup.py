from app import backup
from conftest import auth_header, register_and_login, upload_file


def test_backup_restore_round_trip(client, tmp_path):
    token, _, _ = register_and_login(client)
    client.post("/v2/folders/root/folders", json={"name": "Docs"}, headers=auth_header(token))
    file_id = upload_file(client, token, "keep.txt", content=b"backup-bytes")

    bundle = backup.create_backup(tmp_path)
    assert bundle.is_file()
    assert backup.verify(bundle) is True

    # Simulate data loss: drop the file (row + blob).
    client.delete(f"/v2/files/{file_id}", headers=auth_header(token))
    before = client.get("/v2/folders/root/children", headers=auth_header(token)).json()["items"]
    assert "keep.txt" not in {i["name"] for i in before}

    backup.restore_backup(bundle, replace=True)

    items = client.get("/v2/folders/root/children", headers=auth_header(token)).json()["items"]
    assert {"Docs", "keep.txt"} <= {i["name"] for i in items}

    # Blob bytes came back too.
    dl = client.post(f"/v2/download/files/{file_id}", json={}, headers=auth_header(token)).json()
    fetched = client.get(dl["downloadUrl"].replace("http://testserver", ""))
    assert fetched.content == b"backup-bytes"


def test_verify_detects_corruption(client, tmp_path):
    register_and_login(client)
    bundle = backup.create_backup(tmp_path)
    assert backup.verify(bundle) is True

    bundle.write_bytes(b"corrupted")
    assert backup.verify(bundle) is False


def test_retention_prunes_old_bundles(client, tmp_path, monkeypatch):
    from app.config import settings

    register_and_login(client)
    monkeypatch.setattr(settings, "backup_retention", 2)
    bundles = []
    # Distinct timestamps via the filename are second-resolution; force unique names.
    for i in range(3):
        b = backup.create_backup(tmp_path)
        b_renamed = b.with_name(f"backup-2026010{i}-000000.tar.gz")
        b.rename(b_renamed)
        b.with_suffix(b.suffix + ".sha256").rename(b_renamed.with_suffix(b_renamed.suffix + ".sha256"))
        bundles.append(b_renamed)
    backup.prune(2, tmp_path)
    remaining = backup.list_backups(tmp_path)
    assert len(remaining) == 2
