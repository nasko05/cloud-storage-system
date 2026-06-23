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

{
  echo "DRIVE_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  echo "DRIVE_PG_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
} > .env

docker compose up -d --build
```

Open <http://localhost:8000>, register, and start uploading. The app and its
PostgreSQL database run as two containers; data persists in the `db_data` and
`blob_data` volumes across rebuilds. Full server setup, HTTPS, backups and
migration: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. For a provider-specific
walkthrough with antivirus and an auto-deploy pipeline, see
**[docs/DEPLOYMENT_CONTABO.md](docs/DEPLOYMENT_CONTABO.md)**.

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
cp .env.example .env        # VITE_API_ENDPOINT=http://localhost:8000
npm install
npm run dev                 # http://localhost:3000 (Vite)
```

## Tests

```bash
cd backend && python -m pytest tests/ -q      # backend API/contract tests
cd frontend && npm run build                   # frontend type-check (tsc) + Vite build
```

## Repository layout

```text
cloud-storage-system/
├── Dockerfile              # slim app-only image
├── docker-compose.yml      # app + PostgreSQL, each with a persistent volume
├── backend/                # FastAPI application + tests
│   └── app/                # config, models, routers, services, cli, ...
├── frontend/               # React + TypeScript UI
└── docs/                   # ARCHITECTURE.md, DEPLOYMENT.md
```

## License

MIT
