"""Background housekeeping: expired-data cleanup and scheduled backups.

A single daemon thread (mirroring the archive worker) wakes on an interval to
purge expired rows and, once per ``backup_interval_hours``, write a backup. Kept
deliberately simple for a single low-traffic instance.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from . import backup, storage
from .config import settings
from .database import SessionLocal
from .models import ArchiveJob, File, IdempotencyRecord, PublicLink, Share
from .utils import now_utc

logger = logging.getLogger("maintenance")

_started = threading.Event()


def cleanup(db) -> dict[str, int]:
    """Delete expired shares, public links, archive jobs and idempotency rows."""
    now = now_utc()
    counts: dict[str, int] = {}

    # Remove archive zip files from disk before deleting their rows.
    expired_jobs = db.execute(
        select(ArchiveJob).where(ArchiveJob.expires_at.isnot(None), ArchiveJob.expires_at < now)
    ).scalars().all()
    for job in expired_jobs:
        if job.zip_key:
            storage.delete(job.zip_key)

    counts["shares"] = db.execute(
        delete(Share).where(Share.expires_at.isnot(None), Share.expires_at < now)
    ).rowcount or 0
    counts["public_links"] = db.execute(
        delete(PublicLink).where(PublicLink.expires_at.isnot(None), PublicLink.expires_at < now)
    ).rowcount or 0
    counts["archive_jobs"] = db.execute(
        delete(ArchiveJob).where(ArchiveJob.expires_at.isnot(None), ArchiveJob.expires_at < now)
    ).rowcount or 0
    counts["idempotency"] = db.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.expires_at < now)
    ).rowcount or 0

    max_age_hours = settings.partial_upload_max_age_hours
    if max_age_hours > 0:
        counts["partial_uploads"] = _delete_stale_pending(db, now - timedelta(hours=max_age_hours))
    else:
        counts["partial_uploads"] = 0

    db.commit()
    if any(counts.values()):
        logger.info("cleanup removed %s", counts)
    return counts


def _stale_pending(db, cutoff: datetime) -> list[File]:
    """Never-finalized uploads (status 'pending') created before ``cutoff``."""
    return db.execute(
        select(File).where(File.status == "pending", File.created_at < cutoff)
    ).scalars().all()


def _delete_stale_pending(db, cutoff: datetime) -> int:
    """Delete stale pending uploads and any bytes already written. Does not
    commit (the caller does, alongside the rest of the sweep)."""
    stale = _stale_pending(db, cutoff)
    for file in stale:
        if file.storage_key:
            storage.delete(file.storage_key)
        db.delete(file)
    return len(stale)


def run_cleanup() -> dict[str, int]:
    db = SessionLocal()
    try:
        return cleanup(db)
    finally:
        db.close()


def run_cleanup_partial_uploads(
    older_than_hours: int, dry_run: bool = False
) -> list[tuple[str, str]]:
    """On-demand cleanup of abandoned uploads (CLI entry point).

    Returns the ``(file_id, filename)`` pairs that were removed (or, with
    ``dry_run``, that would be removed).
    """
    db = SessionLocal()
    try:
        cutoff = now_utc() - timedelta(hours=max(0, older_than_hours))
        stale = _stale_pending(db, cutoff)
        removed = [(f.id, f.filename) for f in stale]
        if not dry_run and stale:
            for file in stale:
                if file.storage_key:
                    storage.delete(file.storage_key)
                db.delete(file)
            db.commit()
        return removed
    finally:
        db.close()


def start_scheduler() -> None:
    if _started.is_set():
        return
    _started.set()
    thread = threading.Thread(target=_run, name="maintenance", daemon=True)
    thread.start()


def _run() -> None:
    # Skip an immediate startup backup; the first runs one interval in.
    last_backup = time.time()
    interval = max(60, settings.maintenance_interval_minutes * 60)
    backup_every = settings.backup_interval_hours * 3600

    while True:
        try:
            run_cleanup()
        except Exception:  # pragma: no cover - keep the thread alive
            logger.exception("cleanup failed")

        if backup_every > 0 and (time.time() - last_backup) >= backup_every:
            try:
                backup.create_backup()
                last_backup = time.time()
            except Exception:  # pragma: no cover
                logger.exception("scheduled backup failed")

        time.sleep(interval)
