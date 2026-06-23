# Deploying on a VPS

This guide sets up the Personal Cloud Storage system on any fresh Linux VPS
(Ubuntu/Debian shown). The stack runs as two containers via Docker Compose: the
**app** and a dedicated **PostgreSQL** database. **All persistent state lives on
named volumes, so rebuilding or redeploying never erases your data.**

- [1. Install Docker](#1-install-docker)
- [2. Get the code](#2-get-the-code)
- [3. Configure secrets](#3-configure-secrets)
- [4. Run it](#4-run-it)
- [5. Put it behind HTTPS](#5-put-it-behind-https)
- [6. Updates / redeploys (data is preserved)](#6-updates--redeploys-data-is-preserved)
- [7. Backups & migration (export / import)](#7-backups--migration-export--import)

---

## 1. Install Docker

```bash
# Docker Engine + Compose plugin (official convenience script)
curl -fsSL https://get.docker.com | sh

# (optional) run docker without sudo
sudo usermod -aG docker "$USER" && newgrp docker

docker --version
docker compose version
```

## 2. Get the code

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/nasko05/cloud-storage-system.git
cd cloud-storage-system
```

## 3. Configure secrets

Create a `.env` file (read automatically by `docker compose`):

```bash
{
  echo "DRIVE_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  echo "DRIVE_PG_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
} > .env
cat .env
```

- `DRIVE_SECRET_KEY` signs login tokens and download URLs (required).
- `DRIVE_PG_PASSWORD` is the PostgreSQL password used by both containers.
- Optional: `DRIVE_PORT` (host port, default `8000`) and
  `DRIVE_CORS_ALLOW_ORIGINS` (default `*`).

## 4. Run it

```bash
docker compose up -d --build
docker compose ps
```

The app starts only after the database is healthy, creates its tables
automatically, and is published on `http://<server-ip>:8000`. Open it, register
an account, and start uploading. Data lives in the named volumes `db_data`
(database) and `blob_data` (uploaded files).

## 5. Put it behind HTTPS

Run a reverse proxy (Caddy is simplest) on the host pointing at
`127.0.0.1:8000`. Example `Caddyfile`:

```
drive.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then lock CORS to your domain in `.env` and re-up:

```
DRIVE_CORS_ALLOW_ORIGINS=https://drive.example.com
```

```bash
docker compose up -d
```

## 6. Updates / redeploys (data is preserved)

```bash
git pull
docker compose up -d --build
```

Schema is created/updated on startup. The `db_data` and `blob_data` volumes are
untouched by rebuilds, so accounts, files, shares and links survive every
redeploy.

## 7. Backups (automatic + on demand)

The app runs an **automatic daily backup**: a verified `backup-<timestamp>.tar.gz`
(database JSON + all file bytes) is written to the `backup_data` volume
(`/data/backups`), and only the **most recent 10** are kept. Each bundle has a
`.sha256` sidecar so corruption is detectable. Tune with `DRIVE_BACKUP_INTERVAL_HOURS`
and `DRIVE_BACKUP_RETENTION`.

Run one **on demand**, copy it off the server, and verify it:

```bash
docker compose exec app python -m app.cli backup
docker compose exec app python -m app.cli verify-backup -i /data/backups/<bundle>.tar.gz
# copy bundles off the host (do this on a schedule to a different machine)
docker run --rm -v cloud-storage-system_backup_data:/b -v "$(pwd)":/out \
  busybox cp -r /b /out/backups
```

**Restore** (e.g. on a new server, after step 4):

```bash
docker compose cp ./backup-<timestamp>.tar.gz app:/data/backups/restore.tar.gz
docker compose exec app python -m app.cli restore -i /data/backups/restore.tar.gz
```

`restore` replaces existing rows and copies file bytes back (use `--merge` to keep
existing rows). The bundle round-trips between SQLite and PostgreSQL.

> A backup carries both metadata and file bytes, so it is also the migration
> artifact. (Adjust the `cloud-storage-system_backup_data` volume name to match
> `docker volume ls` if your project directory differs.)

## 8. Storage quota (optional)

Set a per-user limit (bytes) to keep disk usage bounded; `0` (default) is unlimited:

```bash
echo "DRIVE_USER_QUOTA_BYTES=5368709120" >> .env   # 5 GiB/user
docker compose up -d
```

Uploads that would exceed the quota are rejected with HTTP 413.

## 9. Antivirus (optional)

Enable ClamAV so uploads are scanned and infected files are rejected before they
are stored (and therefore never enter a backup). It runs as an extra container
behind the `antivirus` profile:

```bash
echo "DRIVE_CLAMAV_ENABLED=true" >> .env
docker compose --profile antivirus up -d
```

The first start downloads virus definitions (a few minutes). When disabled
(default), uploads are not scanned.

## 10. Security hardening notes

- **HTTPS:** terminate TLS at the reverse proxy (step 5); the app speaks plain
  HTTP behind it.
- **Brute force:** repeated failed logins are rate-limited and temporarily locked
  out (`DRIVE_LOGIN_MAX_ATTEMPTS` / `DRIVE_LOGIN_LOCKOUT_SECONDS`).
- **Housekeeping:** expired shares, public links, archive jobs and idempotency
  records are purged automatically by a background sweep.
- **CORS:** lock `DRIVE_CORS_ALLOW_ORIGINS` to your domain once HTTPS is set up.
- **Secret rotation:** changing `DRIVE_SECRET_KEY` invalidates all existing
  sessions and outstanding download links (everyone must log in again).
