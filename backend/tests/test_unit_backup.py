import pytest

from app import backup


def test_verify_false_without_sidecar(client, tmp_path):
    bundle = backup.create_backup(tmp_path)
    sidecar = bundle.with_suffix(bundle.suffix + ".sha256")
    sidecar.unlink()
    assert backup.verify(bundle) is False


def test_restore_rejects_bad_checksum(client, tmp_path):
    bundle = backup.create_backup(tmp_path)
    bundle.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        backup.restore_backup(bundle)


def test_prune_noop_for_zero_retention(client, tmp_path):
    backup.create_backup(tmp_path)
    assert backup.prune(0, tmp_path) == []
    assert backup.prune(5, tmp_path / "does-not-exist") == []


def test_list_backups_empty_dir(tmp_path):
    assert backup.list_backups(tmp_path / "nope") == []


def test_backup_without_blobs_dir(client, tmp_path, monkeypatch):
    # storage dir absent -> bundle still created with just the DB.
    monkeypatch.setattr(backup.settings, "storage_dir", tmp_path / "missing-blobs")
    bundle = backup.create_backup(tmp_path)
    assert bundle.is_file()
    assert backup.verify(bundle)
