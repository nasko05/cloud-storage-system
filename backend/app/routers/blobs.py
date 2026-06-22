"""Signed blob upload/download endpoints (no JWT; the token authorises).

This is the local-filesystem equivalent of writing to / reading from S3 via
presigned URLs.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from .. import storage
from ..errors import ApiError
from ..security import verify_signed_token

router = APIRouter(prefix="/v2/blob", tags=["blob"])

_CHUNK = 1024 * 1024


@router.put("/upload")
async def upload_blob(request: Request, token: str) -> Response:
    payload = verify_signed_token(token)
    if not payload or payload.get("action") != "upload" or not payload.get("key"):
        raise ApiError(403, "Invalid or expired upload token")

    path = storage.open_write(payload["key"])
    with path.open("wb") as out:
        async for chunk in request.stream():
            out.write(chunk)
    return Response(status_code=200)


@router.get("/download")
def download_blob(token: str) -> StreamingResponse:
    payload = verify_signed_token(token)
    if not payload or payload.get("action") != "download" or not payload.get("key"):
        raise ApiError(403, "Invalid or expired download token")

    key = payload["key"]
    if not storage.exists(key):
        raise ApiError(404, "File not found in storage")

    filename = payload.get("filename", "download")

    def stream():
        with storage.open_read(key) as handle:
            while chunk := handle.read(_CHUNK):
                yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(storage.size(key)),
    }
    return StreamingResponse(stream(), media_type="application/octet-stream", headers=headers)
