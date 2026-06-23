import os

import pytest
from conftest import auth_header, register_and_login, upload_file

from app import backup as backup_mod
from app.cli import main


def test_cli_init(client):
    assert main(["init"]) == 0


def test_cli_export_then_import(client, tmp_path):
    token, _, _ = register_and_login(client)
    client.post("/v2/folders/root/folders", json={"name": "Docs"}, headers=auth_header(token))
    out = tmp_path / "dump.json"
    assert main(["export", "-o", str(out)]) == 0
    assert os.path.getsize(out) > 0
    assert main(["import", "-i", str(out), "--replace"]) == 0
    items = client.get("/v2/folders/root/children", headers=auth_header(token)).json()["items"]
    assert {"Docs"} <= {i["name"] for i in items}


def test_cli_backup_verify_restore(client, tmp_path):
    token, _, _ = register_and_login(client)
    upload_file(client, token, "keep.txt", content=b"bytes")

    assert main(["backup", "--output-dir", str(tmp_path)]) == 0
    bundle = backup_mod.list_backups(tmp_path)[0]
    assert main(["verify-backup", "-i", str(bundle)]) == 0
    assert main(["restore", "-i", str(bundle)]) == 0


def test_cli_verify_corrupt_returns_nonzero(client, tmp_path):
    register_and_login(client)
    main(["backup", "--output-dir", str(tmp_path)])
    bundle = backup_mod.list_backups(tmp_path)[0]
    bundle.write_bytes(b"corrupt")
    assert main(["verify-backup", "-i", str(bundle)]) == 1


def test_cli_requires_subcommand(client):
    with pytest.raises(SystemExit):
        main([])
