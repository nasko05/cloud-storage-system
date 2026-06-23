# Backend — Personal Cloud Storage

Self-contained FastAPI backend. Replaces the former AWS stack (8 Lambdas + API
Gateway + Cognito + DynamoDB + S3 + SQS) with one process backed by PostgreSQL
and the local filesystem.

## Run locally

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# SQLite + local storage, no frontend (API only)
DRIVE_SECRET_KEY=dev DRIVE_SERVE_FRONTEND=false uvicorn app.main:app --reload
```

Configuration is environment-driven with the `DRIVE_` prefix — see
`.env.example`. The only value that matters in production is `DRIVE_SECRET_KEY`.

## Tests

```bash
python -m pytest tests/ -q
```

Tests run against an isolated SQLite database and a temp storage dir, using
FastAPI's `TestClient`.

## Management CLI

```bash
python -m app.cli init                       # create tables
python -m app.cli export -o backup.json      # snapshot all tables to JSON
python -m app.cli import -i backup.json --replace
```

The JSON snapshot round-trips between SQLite and PostgreSQL (see
`docs/DEPLOYMENT.md` for migration). File bytes are migrated by copying the
storage directory.

## API surface (v2)

### Auth (no JWT)

| Method | Path                | Purpose                  |
|--------|---------------------|--------------------------|
| POST   | `/v2/auth/register` | Create account           |
| POST   | `/v2/auth/confirm`  | Confirm (if enabled)     |
| POST   | `/v2/auth/login`    | Get a JWT access token   |

### Private (JWT)

| Method | Path |
|--------|------|
| POST | `/v2/files/uploads` |
| POST | `/v2/files/{fileId}/finalize` |
| PATCH | `/v2/files/{fileId}` |
| DELETE | `/v2/files/{fileId}` |
| GET | `/v2/folders/{folderId}/children` |
| POST | `/v2/folders/{folderId}/folders` |
| PATCH | `/v2/folders/{folderId}` |
| DELETE | `/v2/folders/{folderId}` |
| GET | `/v2/shares/inbound` |
| GET | `/v2/files/{fileId}/shares` |
| PUT | `/v2/files/{fileId}/shares/{principal}` |
| PATCH | `/v2/files/{fileId}/shares/{principal}` |
| DELETE | `/v2/files/{fileId}/shares/{principal}` |
| POST | `/v2/files/{fileId}/public-links` |
| GET | `/v2/files/{fileId}/public-links` |
| PATCH | `/v2/public-links/{token}` |
| DELETE | `/v2/public-links/{token}` |
| POST | `/v2/download/files/{fileId}` |
| POST | `/v2/download/archives` |
| GET | `/v2/download/archives/{archiveJobId}` |

### Public (no JWT)

| Method | Path |
|--------|------|
| GET | `/v2/public-links/{token}` |
| POST | `/v2/public-links/{token}/download` |
| PUT | `/v2/blob/upload?token=…` (signed) |
| GET | `/v2/blob/download?token=…` (signed) |

## Notes

- Upload is two-step: init (`pending`) → PUT bytes to the signed URL → finalize
  (`ready`) after the object is confirmed on disk.
- Share / public-link expiry is enforced in-code against stored `expires_at`.
- Archive ZIPs are built by an in-process worker thread; clients poll the job
  status endpoint. Jobs left mid-flight are re-enqueued on restart.
- `Idempotency-Key` is honoured on all mutating routes.
