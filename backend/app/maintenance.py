"""Background housekeeping: expired-data cleanup and scheduled backups.

A single daemon thread (mirroring the archive worker) wakes on an interval to
purge expired rows and, once per ``backup_interval_hours``, write a backup. Kept
deliberately simple for a single low-traffic instance.
"""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import delete, select

from . import backup, storage
from .config import settings
from .database import SessionLocal
from .models import ArchiveJob, IdempotencyRecord, PublicLink, Share
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

    db.commit()
    if any(counts.values()):
        logger.info("cleanup removed %s", counts)
    return counts


def run_cleanup() -> dict[str, int]:
    db = SessionLocal()
    try:
        return cleanup(db)
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
