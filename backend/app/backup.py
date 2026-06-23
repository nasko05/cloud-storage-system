"""Backup / restore of the full system state.

A backup is a single timestamped ``.tar.gz`` containing the database as JSON and
all uploaded file bytes, accompanied by a ``.sha256`` sidecar so corruption can
be detected. The daily scheduler and the ``app.cli backup`` command both call
:func:`create_backup`; restoring is :func:`restore_backup`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import dbio
from .config import settings

logger = logging.getLogger("backup")

_DB_MEMBER = "db.json"
_BLOBS_MEMBER = "blobs"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(output_dir: Path | None = None) -> Path:
    """Write a verified backup bundle and return its path."""
    target_dir = Path(output_dir) if output_dir else settings.backup_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bundle = target_dir / f"backup-{stamp}.tar.gz"

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / _DB_MEMBER
        with db_path.open("w", encoding="utf-8") as handle:
            json.dump(dbio.export_to_dict(), handle)

        with tarfile.open(bundle, "w:gz") as tar:
            tar.add(db_path, arcname=_DB_MEMBER)
            if settings.storage_dir.is_dir():
                tar.add(settings.storage_dir, arcname=_BLOBS_MEMBER)

    checksum = _sha256(bundle)
    bundle.with_suffix(bundle.suffix + ".sha256").write_text(f"{checksum}  {bundle.name}\n")
    logger.info("backup created: %s (%s)", bundle.name, checksum[:12])

    prune(settings.backup_retention, target_dir)
    return bundle


def verify(bundle: Path) -> bool:
    """Return True if the bundle matches its recorded checksum."""
    bundle = Path(bundle)
    sidecar = bundle.with_suffix(bundle.suffix + ".sha256")
    if not sidecar.is_file():
        return False
    expected = sidecar.read_text().split()[0]
    return _sha256(bundle) == expected


def restore_backup(bundle: Path, *, replace: bool = True) -> None:
    """Restore database rows and file bytes from a backup bundle."""
    bundle = Path(bundle)
    if not verify(bundle):
        raise ValueError(f"Checksum verification failed for {bundle.name}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(bundle, "r:gz") as tar:
            tar.extractall(tmp_path)

        db_file = tmp_path / _DB_MEMBER
        with db_file.open(encoding="utf-8") as handle:
            dbio.import_from_dict(json.load(handle), replace=replace)

        restored_blobs = tmp_path / _BLOBS_MEMBER
        if restored_blobs.is_dir():
            settings.storage_dir.mkdir(parents=True, exist_ok=True)
            import shutil

            for item in restored_blobs.iterdir():
                dest = settings.storage_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
    logger.info("restored from backup: %s", bundle.name)


def prune(retention: int, directory: Path | None = None) -> list[Path]:
    """Keep only the newest ``retention`` bundles; delete the rest (+ sidecars)."""
    target_dir = Path(directory) if directory else settings.backup_dir
    if retention <= 0 or not target_dir.is_dir():
        return []
    bundles = sorted(
        target_dir.glob("backup-*.tar.gz"), key=lambda p: p.name, reverse=True
    )
    removed = []
    for old in bundles[retention:]:
        old.unlink(missing_ok=True)
        old.with_suffix(old.suffix + ".sha256").unlink(missing_ok=True)
        removed.append(old)
    return removed


def list_backups(directory: Path | None = None) -> list[Path]:
    target_dir = Path(directory) if directory else settings.backup_dir
    if not target_dir.is_dir():
        return []
    return sorted(target_dir.glob("backup-*.tar.gz"), key=lambda p: p.name, reverse=True)
