# App-only image for the Personal Cloud Storage system.
#
# Stage 1 builds the React frontend; stage 2 produces a slim, non-root runtime
# image containing only the FastAPI app and the static UI. The database is a
# separate PostgreSQL container (see docker-compose.yml). Uploaded file bytes
# live on the /data volume.

# ---- Stage 1: build the frontend ----
FROM node:24-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: runtime ----
FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DRIVE_FRONTEND_DIR=/app/static \
    DRIVE_STORAGE_DIR=/data/blobs

WORKDIR /app

# psycopg2-binary bundles its own libpq, so no system packages are required.
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY --from=frontend /frontend/build ./static

RUN useradd -r -u 10001 -m appuser \
    && mkdir -p /data/blobs /data/backups \
    && chown -R appuser:appuser /data /app
USER appuser

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
