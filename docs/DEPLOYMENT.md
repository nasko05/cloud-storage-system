# Deploying on a VPS

This guide sets up the Personal Cloud Storage system on any fresh Linux VPS
(Ubuntu/Debian shown). The whole stack — API, database, file storage and the
web UI — runs from a single Docker image. **All persistent state lives on a
mounted volume, so rebuilding or redeploying the image never erases your data.**

- [1. Install Docker](#1-install-docker)
- [2. Get the code](#2-get-the-code)
- [3. Configure secrets](#3-configure-secrets)
- [4a. Run as a single image (embedded PostgreSQL)](#4a-run-as-a-single-image-embedded-postgresql)
- [4b. Run with docker compose (separate DB)](#4b-run-with-docker-compose-separate-db)
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

Generate a strong secret (used to sign login tokens and download URLs):

```bash
echo "DRIVE_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" > .env
echo "DRIVE_PG_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')" >> .env
cat .env
```

## 4a. Run as a single image (embedded PostgreSQL)

This is the literal "one image on a server" deployment. PostgreSQL runs inside
the same container; the host directory `./data` holds both the database and the
uploaded files.

```bash
# Build the image
docker build -t personal-drive .

# Create a host directory for persistent data
mkdir -p data

# Run it
docker run -d --name drive \
  --restart unless-stopped \
  -p 8000:8000 \
  -v "$(pwd)/data:/data" \
  --env-file .env \
  personal-drive
```

Open `http://<server-ip>:8000`, register an account and you're in. Because
`./data` is a bind mount, the database and files persist across `docker rm` /
rebuilds.

## 4b. Run with docker compose (separate DB)

Preferred for production: the database runs as its own container with its own
named volume, which is easier to back up and upgrade independently.

```bash
docker compose up -d --build
docker compose ps
```

The app is published on `http://<server-ip>:8000` (override with `DRIVE_PORT`).
Data lives in the named volumes `db_data` and `blob_data`.

## 5. Put it behind HTTPS

Run a reverse proxy (Caddy is the simplest) on the host and point it at
`127.0.0.1:8000`. Example `Caddyfile`:

```
drive.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then restrict the app's CORS to your domain by adding to `.env`:

```
DRIVE_CORS_ALLOW_ORIGINS=https://drive.example.com
```

## 6. Updates / redeploys (data is preserved)

```bash
git pull

# single-image:
docker build -t personal-drive .
docker stop drive && docker rm drive
docker run -d --name drive --restart unless-stopped \
  -p 8000:8000 -v "$(pwd)/data:/data" --env-file .env personal-drive

# compose:
docker compose up -d --build
```

Database tables are created/updated automatically on startup. The `./data`
volume (or named volumes) is untouched by rebuilds, so accounts, files, shares
and links survive every redeploy.

## 7. Backups & migration (export / import)

A built-in CLI produces a single portable JSON snapshot of all metadata
(accounts, folders, files, shares, public links). File **bytes** live under the
storage volume and are migrated by copying that directory.

**Export** (single-image deployment):

```bash
docker exec drive /usr/local/bin/entrypoint.sh manage export -o /data/backup.json
# copy it off the server
docker cp drive:/data/backup.json ./backup.json
# and grab the file bytes
tar czf blobs.tar.gz -C ./data blobs
```

With docker compose, run the management command in the app container:

```bash
docker compose exec app /usr/local/bin/entrypoint.sh manage export -o /data/blobs/backup.json
```

**Import** on a new server (after step 4):

```bash
docker cp ./backup.json drive:/data/backup.json
docker exec drive /usr/local/bin/entrypoint.sh manage import -i /data/backup.json --replace
# restore file bytes
tar xzf blobs.tar.gz -C ./data
```

> `--replace` clears existing rows before importing. Omit it to merge into an
> empty database. The snapshot round-trips between SQLite and PostgreSQL, so you
> can develop locally on SQLite and restore into PostgreSQL in production.
