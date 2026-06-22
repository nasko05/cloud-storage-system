#!/usr/bin/env bash
#
# Container entrypoint for the all-in-one image.
#
# By default it starts an embedded PostgreSQL instance whose data lives on a
# persistent volume (so redeploys never erase content) and then launches the
# FastAPI application. Set DRIVE_EMBEDDED_PG=false (see docker-compose.yml) to
# use an external database instead.
set -euo pipefail

DATA_ROOT="${DRIVE_DATA_ROOT:-/data}"
export PGDATA="${PGDATA:-$DATA_ROOT/pgdata}"
export DRIVE_STORAGE_DIR="${DRIVE_STORAGE_DIR:-$DATA_ROOT/blobs}"
EMBEDDED_PG="${DRIVE_EMBEDDED_PG:-true}"

mkdir -p "$DRIVE_STORAGE_DIR"

start_embedded_postgres() {
  local pg_user="${DRIVE_PG_USER:-drive}"
  local pg_password="${DRIVE_PG_PASSWORD:-drive}"
  local pg_db="${DRIVE_PG_DB:-drive}"
  export DRIVE_DATABASE_URL="${DRIVE_DATABASE_URL:-postgresql+psycopg2://${pg_user}:${pg_password}@127.0.0.1:5432/${pg_db}}"

  mkdir -p "$PGDATA" /var/run/postgresql
  chown -R postgres:postgres "$PGDATA" /var/run/postgresql

  if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "Initializing PostgreSQL data directory at $PGDATA"
    gosu postgres initdb -D "$PGDATA" >/dev/null
    echo "host all all 127.0.0.1/32 md5" >> "$PGDATA/pg_hba.conf"
  fi

  echo "Starting PostgreSQL..."
  gosu postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses='127.0.0.1'" -w start

  if ! gosu postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${pg_user}'" | grep -q 1; then
    gosu postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE \"${pg_user}\" LOGIN PASSWORD '${pg_password}'"
  fi
  if ! gosu postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${pg_db}'" | grep -q 1; then
    gosu postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${pg_db}\" OWNER \"${pg_user}\""
  fi
}

if [ "$EMBEDDED_PG" = "true" ]; then
  start_embedded_postgres
fi

if [ -z "${DRIVE_SECRET_KEY:-}" ]; then
  echo "WARNING: DRIVE_SECRET_KEY is not set; using an insecure default. Set it in production!" >&2
fi

# Run a one-off management command (e.g. export/import) and exit.
if [ "${1:-}" = "manage" ]; then
  shift
  exec python -m app.cli "$@"
fi

echo "Starting application server on :8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

shutdown() {
  echo "Shutting down..."
  kill -TERM "$APP_PID" 2>/dev/null || true
  wait "$APP_PID" 2>/dev/null || true
  if [ "$EMBEDDED_PG" = "true" ]; then
    gosu postgres pg_ctl -D "$PGDATA" -m fast -w stop || true
  fi
  exit 0
}
trap shutdown SIGTERM SIGINT

wait "$APP_PID"
