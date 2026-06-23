# Deploying on a Contabo VPS (with automatic deployment)

This guide takes you from an empty Contabo account to a hardened,
HTTPS-secured Personal Cloud Storage server **with antivirus scanning enabled**,
plus a GitHub Actions pipeline that **auto-deploys every push to `main`**.

The app runs as Docker containers (FastAPI app + PostgreSQL, plus a ClamAV
container for antivirus). All persistent state — database, uploaded files,
backups — lives on named Docker volumes, so rebuilds and redeploys never erase
your data.

> This is the Contabo-specific companion to the generic [DEPLOYMENT.md](DEPLOYMENT.md).
> Where they overlap, this file wins for Contabo.

- [1. Order the VPS](#1-order-the-vps)
- [2. First login & basic hardening](#2-first-login--basic-hardening)
- [3. Install Docker](#3-install-docker)
- [4. Get the code & configure secrets](#4-get-the-code--configure-secrets)
- [5. Run it (with antivirus)](#5-run-it-with-antivirus)
- [6. HTTPS with Caddy](#6-https-with-caddy)
- [7. Firewall](#7-firewall)
- [8. Off-site backups](#8-off-site-backups)
- [9. Automatic deployment pipeline](#9-automatic-deployment-pipeline)
- [10. Day-2 operations](#10-day-2-operations)

---

## 1. Order the VPS

In the Contabo control panel order a **Storage VPS** (or any VPS) sized for the
antivirus workload:

- **RAM: at least 4 GB (8 GB comfortable).** ClamAV loads its signature
  database into memory (~1.5 GB); on top of the app + PostgreSQL a 2 GB box will
  get OOM-killed. At 4 GB add swap (see step 2); at 8 GB you have headroom even
  while the pipeline rebuilds the frontend with ClamAV running.
- **Storage: this is the VPS's local SSD/HDD, and it is the *only* space the app
  stores files in.** Size it for your actual file needs (512 GB – 1 TB). A
  separately-billed **Object Storage** add-on is **not** app storage — the app
  writes uploads to the local disk, never to an S3 bucket. Object Storage is
  still worth adding as the off-site **backup** target (see step 8).
  > For reference, a Storage VPS 20 exposes roughly **~387 GB usable** on `/`
  > (check yours with `df -h /`); that local disk is your entire file capacity.
- **Image: Ubuntu 24.04 LTS (64-bit).**
- **Region:** pick the datacenter closest to you.
- **Login:** set an SSH key if offered; otherwise Contabo emails you a **root
  password**. (Contabo provisioning is not instant — it can take from minutes to
  a few hours, and arrives by email.)

When it is ready you will have a **public IP**. If you want HTTPS (you do), add
a DNS **A record** for e.g. `drive.example.com` pointing at that IP now, so it
has time to propagate.

## 2. First login & basic hardening

```bash
ssh root@<vps-ip>      # use the password Contabo emailed, if no key was set
apt-get update && apt-get upgrade -y
```

Create a non-root user you will use day to day and for deploys, and give it your
SSH key:

```bash
adduser deploy                       # set a password when prompted
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy root's authorized_keys
# OR, if you logged in with a password, add your public key manually:
#   su - deploy; mkdir -p ~/.ssh; nano ~/.ssh/authorized_keys  (paste key)
```

Then lock SSH down (disable root + password login) and restart it:

```bash
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

From now on log in as `ssh deploy@<vps-ip>`.

**Optional — add swap (recommended on 4 GB; nice insurance on 8 GB).** A swapfile
prevents an out-of-memory kill if ClamAV and the frontend rebuild peak at the
same time:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # persist across reboots
free -h
```

## 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker deploy        # run docker without sudo
newgrp docker                         # apply the group in this session
docker --version && docker compose version
```

## 4. Get the code & configure secrets

Clone into the `deploy` user's home directory — the pipeline expects it at
`~/cloud-storage-system`:

```bash
sudo apt-get install -y git
cd ~
git clone https://github.com/nasko05/cloud-storage-system.git
cd cloud-storage-system
```

Create `.env`. This enables antivirus and locks CORS to your domain:

```bash
{
  echo "DRIVE_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  echo "DRIVE_PG_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
  echo "DRIVE_CLAMAV_ENABLED=true"
  echo "DRIVE_CORS_ALLOW_ORIGINS=https://drive.example.com"
  # Optional per-user quota (bytes); 0 = unlimited. Example: 50 GiB.
  # echo "DRIVE_USER_QUOTA_BYTES=53687091200"
} > .env
```

- `DRIVE_SECRET_KEY` signs login tokens and download URLs — keep it stable
  (changing it logs everyone out).
- `DRIVE_PG_PASSWORD` is the database password shared by both containers.
- `DRIVE_CLAMAV_ENABLED=true` turns on upload scanning; infected files are
  rejected before they are stored (and so never enter a backup).

## 5. Run it (with antivirus)

The ClamAV container lives behind the `antivirus` Compose profile, so you must
pass `--profile antivirus`:

```bash
docker compose --profile antivirus up -d --build
docker compose ps
```

The **first ClamAV start downloads virus definitions (a few minutes)** before it
reports healthy. A **Caddy reverse proxy** comes up automatically as part of the
stack and is the only publicly exposed service: the app itself is bound to
localhost and reached only through Caddy. Data lives in the `db_data`,
`blob_data` and `backup_data` volumes.

## 6. How the app is served (Caddy + HTTPS)

Caddy runs as a container (defined in `docker-compose.yml`, config in
`Caddyfile`) and publishes ports 80/443. What it serves is controlled by
`DRIVE_SITE_ADDRESS`. **The deploy pipeline sets this automatically** (see
`.github/workflows/deploy.yml`), so a normal deploy already serves the app on the
project domain over HTTPS — no manual step.

- **Default (pipeline):** the workflow injects `DRIVE_SITE_ADDRESS` (the project
  domain) and the matching CORS origin, and Caddy **auto-provisions and renews a
  Let's Encrypt certificate**. To change the domain, set a repository *variable*
  `DRIVE_SITE_ADDRESS` (and `DRIVE_CORS_ALLOW_ORIGINS`) — no workflow edit needed.
- **The one external prerequisite is DNS:** a DNS **A record** for the domain
  must point at the VPS IPv4. Caddy validates the domain over port 80, so the
  cert is issued once DNS resolves (it retries automatically until then).
- **Manual / no-pipeline deploys:** put the same values in `.env` instead:
  ```bash
  echo "DRIVE_SITE_ADDRESS=personal-drive-io.com" >> .env
  echo "DRIVE_CORS_ALLOW_ORIGINS=https://personal-drive-io.com" >> .env
  docker compose --profile antivirus up -d
  ```
- **No domain at all:** leave it unset; Caddy falls back to `:80` and serves
  plain HTTP on the server IP (`http://<vps-ip>`).
  > ⚠️ Plain HTTP sends login passwords in cleartext — use a domain for anything
  > beyond a quick trial.

## 7. Firewall

Contabo VPSes have **no cloud firewall by default**, so configure `ufw` on the
host. Allow SSH + HTTP + HTTPS:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Port 8000 is already bound to localhost only (see `docker-compose.yml`), so the
app is never directly reachable from outside — all traffic goes through Caddy on
80/443. `ufw` then blocks anything else.

## 8. Off-site backups

The app already writes a **verified daily backup** (database + file bytes, with
a `.sha256` checksum) to the `backup_data` volume and keeps the last 10. But
those bundles sit on the **same disk** as your data — useless if the VPS dies.
Copy them off-box on a schedule.

The **Contabo Object Storage** add-on is exactly the right home for these
bundles (and it is the *only* thing that add-on is used for here — the app's
live files stay on the VPS's local disk). Install `rclone`, configure an S3
remote once, then add a nightly cron that syncs the backup volume off the
server:

```bash
sudo apt-get install -y rclone
rclone config        # create an "s3" remote pointing at Contabo Object Storage

# nightly sync at 03:30 — adjust the volume name to `docker volume ls`
( crontab -l 2>/dev/null; echo '30 3 * * * docker run --rm -v cloud-storage-system_backup_data:/b -v /tmp/bk:/out busybox cp -r /b/. /out/ && rclone sync /tmp/bk remote:drive-backups' ) | crontab -
```

To **restore** on a fresh box (after step 5), copy a bundle back and run:

```bash
docker compose cp ./backup-<timestamp>.tar.gz app:/data/backups/restore.tar.gz
docker compose exec app python -m app.cli restore -i /data/backups/restore.tar.gz
```

## 9. Automatic deployment pipeline

The repo includes `.github/workflows/deploy.yml`. It runs **only after the CI
workflow passes on `main`**, then SSHes into the VPS and runs
`git reset --hard origin/main` + `docker compose --profile antivirus up -d --build`.
Because data is on volumes and the schema migrates on startup, every push to
`main` redeploys safely.

**One-time setup:**

1. **Generate a dedicated deploy SSH key** on your laptop (no passphrase, so CI
   can use it non-interactively):

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/drive_deploy -N "" -C "github-actions-deploy"
   ```

2. **Authorise it on the VPS** for the `deploy` user:

   ```bash
   ssh-copy-id -i ~/.ssh/drive_deploy.pub deploy@<vps-ip>
   ```

3. **Add three GitHub repository secrets**
   (Settings → Secrets and variables → Actions → New repository secret):

   | Secret | Value |
   |---|---|
   | `DEPLOY_HOST` | your VPS IP or `drive.example.com` |
   | `DEPLOY_USER` | `deploy` |
   | `DEPLOY_SSH_KEY` | the **contents of the private key** `~/.ssh/drive_deploy` |

4. **Merge to `main`.** The deploy workflow lives on `main`, so it activates once
   merged. From then on: push to `main` → CI runs → on green, the VPS updates
   itself.

> The pipeline uses TOFU (`ssh-keyscan`) to trust the host on first contact. For
> stronger security, store the VPS host key as a secret and write it to
> `known_hosts` instead — see the comment in `deploy.yml`.

**Alternative (lower server load):** instead of building on the VPS, have CI
build the image and push it to a registry (GHCR or Contabo's registry), change
the `app` service in `docker-compose.yml` from `build: .` to `image: <registry>/...`,
and make the deploy step `docker compose pull && up -d`. Worth it if the on-VPS
React build (HDD, modest CPU) feels slow; the SSH-build flow above is simpler and
fine for low-frequency deploys.

## 10. Day-2 operations

```bash
# manual update (the pipeline does this for you)
git pull && docker compose --profile antivirus up -d --build

# logs
docker compose logs -f app
docker compose logs -f clamav

# on-demand backup + verify
docker compose exec app python -m app.cli backup
docker compose exec app python -m app.cli verify-backup -i /data/backups/<bundle>.tar.gz
```

**HDD note:** these Storage VPS plans are spinning disk. For low traffic that is
fine; the only HDD-sensitive part is PostgreSQL under heavy concurrency, which a
personal/low-traffic drive will not hit.
