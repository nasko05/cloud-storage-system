# Personal Cloud Storage System

A self-hosted, Google-Drive-style file manager that runs as **a single Docker
image on one server**. No cloud account required.

## Features

- Email/password accounts with JWT sessions
- File uploads, folder hierarchy (create / move / rename / delete)
- Sharing to specific users with permission (read / download / edit) + expiry
- Public links with optional password and expiry, plus a no-login download page
- Bulk ZIP download of selected files/folders (async, in-process worker)
- Grid/list views, context menu, drag/drop move, drag/drop upload, progress + cancel

## Stack

- **Frontend:** React + TypeScript + MUI (served by the backend in production)
- **Backend:** FastAPI (Python 3.11), one router per domain
- **Database:** PostgreSQL (SQLite for local dev/tests) via SQLAlchemy
- **Storage:** local filesystem, accessed through short-lived signed URLs
- **Packaging:** one Docker image; all state on a mounted volume

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how this maps from the
original AWS serverless design.

## Quick start (Docker)

```bash
git clone https://github.com/nasko05/cloud-storage-system.git
cd cloud-storage-system

echo "DRIVE_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" > .env

docker build -t personal-drive .
mkdir -p data
docker run -d --name drive --restart unless-stopped \
  -p 8000:8000 -v "$(pwd)/data:/data" --env-file .env personal-drive
```

Open <http://localhost:8000>, register, and start uploading. Data persists in
`./data` across rebuilds. Full server setup, HTTPS, compose, backups and
migration: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

## Local development

Backend (SQLite, auto-reload):

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
DRIVE_SECRET_KEY=dev DRIVE_SERVE_FRONTEND=false uvicorn app.main:app --reload
```

Frontend (against the backend above):

```bash
cd frontend
cp .env.example .env        # REACT_APP_API_ENDPOINT=http://localhost:8000
npm install --legacy-peer-deps
npm start                   # http://localhost:3000
```

## Tests

```bash
cd backend && python -m pytest tests/ -q      # backend API/contract tests
cd frontend && CI=false npm run build         # frontend type-check + build
```

## Repository layout

```text
cloud-storage-system/
├── Dockerfile              # single all-in-one image (app + embedded PostgreSQL)
├── docker-compose.yml      # split app + PostgreSQL alternative
├── docker/entrypoint.sh    # boots embedded DB then the app
├── backend/                # FastAPI application + tests
│   └── app/                # config, models, routers, services, cli, ...
├── frontend/               # React + TypeScript UI
└── docs/                   # ARCHITECTURE.md, DEPLOYMENT.md
```

## License

MIT
