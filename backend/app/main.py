"""FastAPI application: the single consolidated backend.

Mounts every domain router (the former 8 Lambdas), serves the built React
frontend as static files with SPA fallback, and starts the in-process archive
worker. One process, one image.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import archive, maintenance
from .config import settings
from .database import init_db
from .errors import ApiError, api_error_handler, unhandled_error_handler
from .routers import (
    archive as archive_router,
)
from .routers import (
    auth,
    blobs,
    download,
    files,
    folders,
    public_download,
    public_links,
    shares,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    archive.start_worker()
    if settings.enable_scheduler:
        maintenance.start_scheduler()
    yield


app = FastAPI(title="Personal Cloud Storage", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    # Auth is via the Authorization header (Bearer), not cookies, so credentials
    # are not needed — which also keeps a wildcard origin list spec-compliant.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API path prefixes that must 404 (not fall through to the SPA index.html).
_API_PREFIXES = ("v2/", "healthz", "docs", "openapi.json", "redoc")

app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_error_handler)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", []) if part not in ("body",))
    message = first.get("msg", "Invalid request")
    return JSONResponse(status_code=400, content={"error": f"{field}: {message}".strip(": ")})


for router in (
    auth.router,
    files.router,
    folders.router,
    shares.router,
    public_links.router,
    download.router,
    public_download.router,
    archive_router.router,
    blobs.router,
):
    app.include_router(router)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}


def mount_frontend(application: FastAPI) -> None:
    """Serve the built React app as static files with SPA fallback.

    Mounted last so API routes win. Unknown API paths still 404 (JSON); any other
    path falls back to ``index.html`` so client-side routes like ``/s/{token}``
    work on a hard refresh.
    """
    frontend_dir = settings.frontend_dir
    assets = frontend_dir / "static"
    if assets.is_dir():
        application.mount("/static", StaticFiles(directory=assets), name="static")

    index = frontend_dir / "index.html"

    @application.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(_API_PREFIXES):
            raise ApiError(404, "Not found")
        candidate = (frontend_dir / full_path).resolve()
        if full_path and candidate.is_file() and frontend_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


# --- Static frontend (mounted last so API routes win) -----------------------

if settings.serve_frontend and settings.frontend_dir.is_dir():
    mount_frontend(app)
