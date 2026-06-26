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
workflow passes on `main`**, then **renders the server's `.env` from GitHub
Secrets + Variables**, SSHes into the VPS, runs `git reset --hard origin/main` +
`docker compose --profile antivirus up -d --build`, and health-checks the app.
Because data is on volumes and the schema migrates on startup, every push to
`main` redeploys safely.

**Configuration lives entirely in GitHub** — there is no manual editing of files
on the server. To change a setting, edit the Secret/Variable in the GitHub UI and
re-run the Deploy workflow.

### One-time setup

1. **Generate a dedicated deploy SSH key** on your laptop (no passphrase, so CI
   can use it non-interactively):

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/drive_deploy -N "" -C "github-actions-deploy"
   ```

2. **Authorise it on the VPS** for the `deploy` user:

   ```bash
   ssh-copy-id -i ~/.ssh/drive_deploy.pub deploy@<vps-ip>
   ```

3. **Add the repository Secrets** (Settings → Secrets and variables → Actions →
   *Secrets*). These are sensitive and must stay **stable** — changing
   `DRIVE_SECRET_KEY` logs everyone out, and `DRIVE_PG_PASSWORD` must match the
   password the existing database volume was created with. Copy the latter two
   from the server's current `.env` (`cat ~/cloud-storage-system/.env`):

   | Secret | Value |
   |---|---|
   | `DEPLOY_HOST` | your VPS IPv4 address |
   | `DEPLOY_USER` | `deploy` |
   | `DEPLOY_SSH_KEY` | contents of the private key `~/.ssh/drive_deploy` |
   | `DRIVE_SECRET_KEY` | the current value from the server `.env` |
   | `DRIVE_PG_PASSWORD` | the current value from the server `.env` |

4. **(Optional) Add repository Variables** (same page → *Variables*) to override
   defaults — all are non-sensitive:

   | Variable | Default if unset |
   |---|---|
   | `DRIVE_SITE_ADDRESS` | `personal-drive-io.com www.personal-drive-io.com` |
   | `DRIVE_CORS_ALLOW_ORIGINS` | `https://personal-drive-io.com,https://www.personal-drive-io.com` |
   | `DRIVE_CLAMAV_ENABLED` | `true` |
   | `DRIVE_USER_QUOTA_BYTES` | `0` (unlimited) |
   | `DRIVE_BACKUP_INTERVAL_HOURS` | `24` |
   | `DRIVE_BACKUP_RETENTION` | `10` |

5. **Merge to `main`.** From then on: push to `main` → CI runs → on green, the
   VPS updates itself and rewrites its `.env` from the values above.

> **Safety:** if `DRIVE_SECRET_KEY` or `DRIVE_PG_PASSWORD` are missing, the deploy
> aborts before touching the server, so a working `.env` is never clobbered.
> Because the `.env` is now pipeline-managed, manual edits on the server are
> overwritten on the next deploy — change config in GitHub instead.

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

### Cleaning up partial uploads

An upload that never finishes (the browser dies, or the byte PUT is blocked)
leaves a `pending` file record — it clutters the drive and can cause "name
already exists" (409) errors on retry. The housekeeping sweep purges `pending`
uploads older than `DRIVE_PARTIAL_UPLOAD_MAX_AGE_HOURS` (default 24, set to 0 to
disable). To clean up on demand:

```bash
# preview what would be removed (no changes)
docker compose exec app python -m app.cli cleanup-partial-uploads --dry-run

# remove all pending uploads regardless of age (e.g. after a failed batch)
docker compose exec app python -m app.cli cleanup-partial-uploads --older-than-hours 0
```

Finalized files are never touched. In the UI, deleting a non-empty folder now
prompts to cascade-delete its contents.

**HDD note:** these Storage VPS plans are spinning disk. For low traffic that is
fine; the only HDD-sensitive part is PostgreSQL under heavy concurrency, which a
personal/low-traffic drive will not hit.

## 11. Troubleshooting

### Caddy can't get an HTTPS certificate (DNS / systemd-resolved)

Symptom — `docker compose logs caddy` shows ACME failing with:

```
lookup acme-v02.api.letsencrypt.org on 127.0.0.53:53: ... connection refused
```

Cause: Ubuntu runs **systemd-resolved**, whose stub resolver lives at
`127.0.0.53`. That address only exists on the host, not inside a container, so
the container can't resolve anything externally and cert issuance fails.

The Compose file already pins public resolvers (`dns: [1.1.1.1, 8.8.8.8]`) on the
`caddy` and `clamav` services, which fixes this for normal deploys. If you still
hit it (e.g. other containers, or an older daemon), fix it globally at the Docker
daemon level:

```bash
echo '{"dns": ["1.1.1.1", "8.8.8.8"]}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
cd ~/cloud-storage-system
docker compose --profile antivirus up -d
docker compose logs -f caddy        # watch the cert get issued
```

### "Site doesn't load" but the deploy succeeded

The deploy health check probes the **app** (`localhost:8000`), so it can go green
while **Caddy** (the public entry point) is still failing — almost always the DNS
issue above, or a missing/late DNS A record for your domain. Check
`docker compose logs caddy`, confirm `dig +short <domain>` returns the VPS IP, and
make sure ports 80/443 are open and published (`docker compose ps` should show
`0.0.0.0:80->80/tcp` on caddy).

### Port 80/443 "address already in use"

A host web server (often a previously apt-installed Caddy) is holding the port.
Find and disable it, then redeploy:

```bash
sudo ss -tlnp 'sport = :80'
sudo systemctl disable --now caddy   # or nginx / apache2
```

## 12. Co-hosting another app behind this proxy

This Caddy can front additional apps on the same VPS (two HTTPS domains can't each
own ports 80/443, so they share one proxy). Caddy joins a shared external Docker
network named `web` and routes each domain to the right container.

One-time, on the host:

```bash
docker network create web        # idempotent; the deploy also ensures this
```

Then, for each co-hosted app:

1. In the sibling app's `docker-compose.yml`, attach its app container to the
   external `web` network and give it a stable name/alias (e.g. `hearth-app`).
   It must **not** publish ports 80/443.
2. Add two repository **Variables** here (Settings → Secrets and variables →
   Actions → Variables) and re-run this app's Deploy once:

   | Variable | Example |
   |---|---|
   | `HEARTH_SITE_ADDRESS` | `hearth.example.com` |
   | `HEARTH_UPSTREAM` | `hearth-app:8000` |

Caddy then serves the sibling domain over HTTPS (auto Let's Encrypt) and proxies
to its container. Until both Variables are set they default to an inert internal
listener, so CI and a Hearth-less deploy are unaffected. The sibling's domain
needs its own DNS A record at the VPS.
