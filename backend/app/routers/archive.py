"""Async ZIP archive enqueue + status polling."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import archive
from ..blob_links import build_download_url
from ..config import settings
from ..deps import CurrentUser, get_current_user, get_db
from ..errors import ApiError
from ..idempotency import run_idempotent
from ..models import ArchiveJob
from ..schemas import CreateArchiveRequest
from ..utils import iso, now_utc

router = APIRouter(prefix="/v2/download/archives", tags=["archive"])


def _dedupe(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


@router.post("", status_code=202)
def create_archive(
    payload: CreateArchiveRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    def action() -> tuple[int, dict]:
        file_ids = _dedupe(payload.fileIds)
        folder_ids = _dedupe(payload.folderIds)
        if not file_ids and not folder_ids:
            raise ApiError(400, "At least one fileId or folderId is required")

        job = ArchiveJob(
            owner_id=user.id,
            status="queued",
            requested_file_ids=file_ids,
            requested_folder_ids=folder_ids,
            expires_at=now_utc() + timedelta(days=settings.archive_job_ttl_days),
        )
        db.add(job)
        db.flush()
        db.commit()  # persist before the worker (separate session) picks it up
        archive.enqueue(job.id)
        return 202, {"archiveJobId": job.id, "status": "queued"}

    status, body = run_idempotent(db, user.id, "archive-queue", idempotency_key, action)
    return JSONResponse(status_code=status, content=body)


@router.get("/{archive_job_id}")
def archive_status(
    archive_job_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = db.get(ArchiveJob, archive_job_id)
    if job is None or job.owner_id != user.id:
        raise ApiError(404, "Archive job not found")

    status = job.status
    if job.expires_at is not None and job.expires_at <= now_utc() and status in ("ready", "failed"):
        status = "expired"

    out = {
        "archiveJobId": job.id,
        "status": status,
        "createdAt": iso(job.created_at),
        "updatedAt": iso(job.updated_at),
    }
    if status == "ready" and job.zip_key:
        out["downloadUrl"] = build_download_url(request, job.zip_key, "archive.zip")
        out["expiresIn"] = settings.signed_url_expiry_seconds
    if job.error_message:
        out["errorMessage"] = job.error_message
    if job.file_count is not None:
        out["fileCount"] = job.file_count
    return out
