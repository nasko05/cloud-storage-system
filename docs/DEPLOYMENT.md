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

## 7. Backups & migration (export / import)

A built-in CLI produces a single portable JSON snapshot of all metadata
(accounts, folders, files, shares, public links). File **bytes** live on the
`blob_data` volume and are migrated by copying that directory.

**Export:**

```bash
# metadata -> JSON (written into the blobs volume so we can copy it out)
docker compose exec app python -m app.cli export -o /data/blobs/backup.json
docker compose cp app:/data/blobs/backup.json ./backup.json

# file bytes
docker run --rm -v cloud-storage-system_blob_data:/data -v "$(pwd)":/out \
  busybox tar czf /out/blobs.tar.gz -C /data .
```

**Import on a new server** (after step 4):

```bash
docker compose cp ./backup.json app:/data/blobs/backup.json
docker compose exec app python -m app.cli import -i /data/blobs/backup.json --replace

docker run --rm -v cloud-storage-system_blob_data:/data -v "$(pwd)":/in \
  busybox tar xzf /in/blobs.tar.gz -C /data
```

> `--replace` clears existing rows before importing. The snapshot round-trips
> between SQLite and PostgreSQL, so you can develop locally on SQLite and restore
> into PostgreSQL in production. (Adjust the `cloud-storage-system_blob_data`
> volume name to match `docker volume ls` if your project directory differs.)
