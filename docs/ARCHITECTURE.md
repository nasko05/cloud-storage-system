# Architecture

The system is a single FastAPI application that serves a React UI, a JSON API,
and file bytes — backed by PostgreSQL and the local filesystem. It runs as two
containers (the app and a PostgreSQL database) on a single server via Docker
Compose.

```
              ┌─────────────────────────────────────────────┐
   browser ──▶│  FastAPI app (uvicorn)                       │
              │                                               │
              │  /            → static React build            │
              │  /v2/auth/*   → register / confirm / login    │
              │  /v2/files/*  → file lifecycle                │
              │  /v2/folders/*→ folder tree                   │
              │  /v2/shares/* → per-user sharing              │
              │  /v2/public-links, /v2/download, /v2/blob/*   │
              │  /v2/download/archives → async ZIP jobs       │
              │                                               │
              │  ┌────────────┐   ┌────────────────────────┐ │
              │  │ archive     │   │ SQLAlchemy ORM         │ │
              │  │ worker      │   └───────────┬────────────┘ │
              │  │ (thread)    │               │              │
              └──┴────┬────────┴───────────────┼──────────────┘
                      │                         │
                 local FS (blob volume)    PostgreSQL (separate container)
```

## What replaced the old AWS stack

This project began as an AWS serverless app. Each managed service was replaced
with a self-contained equivalent so the whole thing runs from one image:

| Concern            | Before (AWS)                    | Now                                      |
|--------------------|---------------------------------|------------------------------------------|
| Compute / routing  | 8 Lambdas + API Gateway         | One FastAPI app, one router per domain   |
| Auth               | Cognito User Pool + JWT authorizer | Built-in email/password + signed JWT  |
| Metadata / ACL     | DynamoDB single-table + GSIs    | PostgreSQL via SQLAlchemy (normalised)   |
| File bytes         | S3 + presigned URLs             | Local filesystem + HMAC-signed URLs      |
| Async ZIP worker   | SQS + worker Lambda             | In-process worker thread + job table     |
| Frontend hosting   | S3 + CloudFront (OAC)           | Served as static files by the app        |

## Key design points

- **Signed blob URLs.** The two-step upload (init → PUT bytes → finalize) and
  download flows are preserved. Instead of S3 presigned URLs, the app issues
  short-lived HMAC-signed same-origin URLs to `/v2/blob/{upload,download}`,
  which stream to/from local storage. The React client is essentially unchanged.
- **Derived flags.** `isShared` / `hasPublicLink` are computed from existence
  queries at list time instead of denormalised counters, eliminating drift.
- **Idempotency.** Mutating routes honour the `Idempotency-Key` header, backed
  by an `idempotency_records` table with TTL.
- **Naive-UTC datetimes.** All stored timestamps are naive UTC for unambiguous
  comparison on both SQLite (tests) and PostgreSQL (production).
- **Portability.** The data layer is plain SQLAlchemy, so the same code runs on
  SQLite (local dev / tests) and PostgreSQL (production), and the export/import
  CLI snapshot round-trips between them.

## Layout

```
backend/app/
  main.py            # app wiring, static frontend, lifespan startup
  config.py          # env-driven settings (DRIVE_* prefix)
  database.py        # engine + session + Base
  models.py          # SQLAlchemy ORM models
  schemas.py         # Pydantic request models
  security.py        # password hashing, JWT, signed blob tokens
  storage.py         # local filesystem blob store
  services.py        # shared queries (ownership, conflicts, flags)
  idempotency.py     # Idempotency-Key support
  archive.py         # in-process ZIP worker
  cli.py             # export / import management commands
  routers/           # auth, files, folders, shares, public_links,
                     # download, public_download, archive, blobs
```
