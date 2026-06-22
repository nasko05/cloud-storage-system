"""Local filesystem blob store (replacement for S3).

File bytes live under ``settings.storage_dir`` keyed exactly like the old S3
object keys (``v2/files/<user>/<file>/<name>``), so the rest of the system is
oblivious to the swap. All keys are server-generated, but every path is still
resolved underneath the storage root to defend against traversal.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import settings


def file_key(user_id: str, file_id: str, filename: str) -> str:
    return f"v2/files/{user_id}/{file_id}/{filename}"


def archive_key(user_id: str, archive_job_id: str) -> str:
    return f"v2/zips/{user_id}/{archive_job_id}.zip"


def resolve(key: str) -> Path:
    root = settings.storage_dir.resolve()
    target = (root / key).resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"Refusing to access path outside storage root: {key}")
    return target


def open_write(key: str) -> Path:
    path = resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def exists(key: str) -> bool:
    return resolve(key).is_file()


def size(key: str) -> int:
    return resolve(key).stat().st_size


def open_read(key: str):
    return resolve(key).open("rb")


def delete(key: str) -> None:
    try:
        resolve(key).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def remove_user_tree() -> None:  # pragma: no cover - maintenance helper
    shutil.rmtree(settings.storage_dir, ignore_errors=True)
