"""Builders for short-lived, HMAC-signed blob URLs.

These same-origin URLs replace S3 presigned URLs: the client PUTs bytes to an
upload URL and navigates to a download URL, exactly as before, but the bytes
are served by this app from local storage.
"""

from __future__ import annotations

from fastapi import Request

from .security import create_signed_token


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def build_upload_url(request: Request, storage_key: str) -> str:
    token = create_signed_token({"action": "upload", "key": storage_key})
    return f"{_base(request)}/v2/blob/upload?token={token}"


def build_download_url(request: Request, storage_key: str, filename: str) -> str:
    token = create_signed_token(
        {"action": "download", "key": storage_key, "filename": filename}
    )
    return f"{_base(request)}/v2/blob/download?token={token}"
