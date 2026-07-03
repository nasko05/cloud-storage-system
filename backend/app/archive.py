"""In-process archive (ZIP) worker — replacement for the SQS worker Lambda.

A single daemon thread consumes archive job ids from an in-memory queue, builds
the ZIP on local disk and records the result. On startup any jobs left in a
non-terminal state (e.g. after a restart) are re-enqueued so nothing is lost.
"""

from __future__ import annotations

import logging
import queue
import threading
import zipfile
from os.path import splitext

from sqlalchemy import select

from . import storage
from .config import settings
from .database import SessionLocal
from .models import ArchiveJob, File, Folder
from .services import collect_subtree
from .utils import now_utc

logger = logging.getLogger("archive")

_CHUNK = 1024 * 1024

_job_queue: queue.Queue[str] = queue.Queue()
_worker_started = threading.Event()


# --- Public API -------------------------------------------------------------

def enqueue(job_id: str) -> None:
    _job_queue.put(job_id)


def start_worker() -> None:
    if _worker_started.is_set():
        return
    _worker_started.set()
    thread = threading.Thread(target=_run, name="archive-worker", daemon=True)
    thread.start()
    _requeue_pending()


# --- Worker loop ------------------------------------------------------------

def _run() -> None:
    while True:
        job_id = _job_queue.get()
        try:
            _process(job_id)
        except Exception:  # pragma: no cover - defensive, keep worker alive
            logger.exception("archive job %s crashed", job_id)
        finally:
            _job_queue.task_done()


def _requeue_pending() -> None:
    db = SessionLocal()
    try:
        pending = db.execute(
            select(ArchiveJob.id).where(ArchiveJob.status.in_(["queued", "processing"]))
        ).scalars().all()
    finally:
        db.close()
    for job_id in pending:
        enqueue(job_id)


def _process(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(ArchiveJob, job_id)
        if job is None:
            return
        job.status = "processing"
        db.commit()

        try:
            files = _collect_files(db, job.owner_id, job.requested_file_ids, job.requested_folder_ids)
            zip_key = _build_zip(db, job.owner_id, job_id, files)
            job.status = "ready"
            job.zip_key = zip_key
            job.file_count = len(files)
            job.error_message = None
            job.completed_at = now_utc()
        except Exception as err:  # noqa: BLE001 - surfaced to the client
            job.status = "failed"
            job.error_message = str(err)[:1000]
            job.completed_at = now_utc()
            logger.warning("archive job %s failed: %s", job_id, err)
        db.commit()
    finally:
        db.close()


# --- File collection --------------------------------------------------------

def _collect_files(db, owner_id, file_ids, folder_ids) -> list[File]:
    files_by_id: dict[str, File] = {}

    for raw in file_ids or []:
        file_id = str(raw).strip()
        if not file_id:
            continue
        file = db.get(File, file_id)
        if file is None or file.owner_id != owner_id:
            raise ValueError(f"File not found: {file_id}")
        files_by_id[file_id] = file

    for raw in folder_ids or []:
        normalized = str(raw).strip() or "root"
        if normalized != "root":
            folder = db.get(Folder, normalized)
            if folder is None or folder.owner_id != owner_id:
                raise ValueError(f"Folder not found: {normalized}")
        _collect_folder(db, owner_id, normalized, files_by_id)

    files = list(files_by_id.values())
    if not files:
        raise ValueError("No files resolved for archive job")
    if len(files) > settings.max_archive_files:
        raise ValueError(f"Too many files selected (max: {settings.max_archive_files})")
    if sum(int(f.size or 0) for f in files) > settings.max_archive_total_bytes:
        raise ValueError("Total selected data is too large")
    return files


def _collect_folder(db, owner_id, root_id, files_by_id) -> None:
    _, files = collect_subtree(db, owner_id, root_id)
    for file in files:
        files_by_id.setdefault(file.id, file)


# --- ZIP assembly -----------------------------------------------------------

def _build_zip(db, owner_id: str, job_id: str, files: list[File]) -> str:
    zip_key = storage.archive_key(owner_id, job_id)
    zip_path = storage.open_write(zip_key)
    used_names: set[str] = set()
    path_cache: dict[str, str] = {}

    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for file in files:
            if not file.storage_key or not storage.exists(file.storage_key):
                continue
            arcname = _arcname(db, file, path_cache, used_names)
            with storage.open_read(file.storage_key) as src, archive.open(arcname, mode="w") as dst:
                while chunk := src.read(_CHUNK):
                    dst.write(chunk)
    return zip_key


def _arcname(db, file: File, path_cache: dict[str, str], used_names: set[str]) -> str:
    folder_path = _resolve_folder_path(db, file.owner_id, file.parent_folder_id, path_cache)
    base = f"{folder_path}/{file.filename}" if folder_path else file.filename
    if base not in used_names:
        used_names.add(base)
        return base
    root, ext = splitext(base)
    counter = 1
    candidate = f"{root} ({counter}){ext}"
    while candidate in used_names:
        counter += 1
        candidate = f"{root} ({counter}){ext}"
    used_names.add(candidate)
    return candidate


def _resolve_folder_path(db, owner_id: str, folder_id: str, cache: dict[str, str]) -> str:
    if not folder_id or folder_id == "root":
        return ""
    if folder_id in cache:
        return cache[folder_id]
    folder = db.get(Folder, folder_id)
    if folder is None or folder.owner_id != owner_id:
        cache[folder_id] = ""
        return ""
    parent_path = _resolve_folder_path(db, owner_id, folder.parent_folder_id, cache)
    own = (folder.name or "").strip("/")
    path = f"{parent_path}/{own}".strip("/") if parent_path else own
    cache[folder_id] = path
    return path
