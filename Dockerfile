# Single-image build for the Personal Cloud Storage system.
#
# Stage 1 builds the React frontend; stage 2 produces a self-contained runtime
# image bundling the FastAPI app, an embedded PostgreSQL, and the static UI.
# All persistent state lives under /data, which should be a mounted volume.

# ---- Stage 1: build the frontend ----
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --legacy-peer-deps --no-audit --no-fund
COPY frontend/ ./
RUN CI=false npm run build

# ---- Stage 2: runtime ----
FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/usr/lib/postgresql/15/bin:${PATH}" \
    DRIVE_FRONTEND_DIR=/app/static \
    DRIVE_DATA_ROOT=/data \
    DRIVE_STORAGE_DIR=/data/blobs \
    PGDATA=/data/pgdata

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql postgresql-client gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /frontend/build ./static
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
