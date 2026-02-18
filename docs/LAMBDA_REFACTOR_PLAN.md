# Backend Lambda Refactor Plan (v2 Dual-Run)

## Document Control
| Field | Value |
|---|---|
| Status | in-progress |
| Last updated | 2026-02-18 |
| Owner | Backend |
| Reviewers | Platform, Frontend |

## Status Legend
- `planned`: not started
- `in-progress`: partially implemented
- `done`: implemented and validated

## Program Status
| Workstream | Owner | Status | Notes |
|---|---|---|---|
| v2 domain lambda split | Backend | in-progress | v2 handlers created for files, folders, shares, public links, download, public download, archive API/worker |
| v2 infrastructure | Platform | in-progress | v2 table, GSIs, SQS queue, IAM roles, functions, routes, and permissions added in stack |
| shared backend core | Backend | in-progress | shared_v2 modules added (auth extraction, pagination, idempotency, permissions, structured logs, key helpers) |
| dual-run enablement | Backend + Frontend | planned | v1/v2 can coexist; frontend canary switch and parity controls pending |
| parity migration jobs | Data | planned | backfill + parity checker not yet implemented |
| v1 decommission | Backend | planned | remove v1 routes/table only after parity and soak period |

## Target Lambda Topology (v2)
| Lambda | Responsibility | Auth | Runtime |
|---|---|---|---|
| `drive-files-fn` | file upload-init, rename/move, delete | JWT | 30s / 256MB |
| `drive-folders-fn` | folder create/list/move/rename/delete | JWT | 30s / 256MB |
| `drive-shares-fn` | share create/list/update/revoke, inbound shares | JWT | 30s / 256MB |
| `drive-public-links-admin-fn` | owner public-link CRUD | JWT | 30s / 256MB |
| `drive-download-fn` | private/shared file download URL | JWT | 30s / 256MB |
| `drive-public-download-fn` | public token metadata + token download | none | 30s / 256MB |
| `drive-archive-api-fn` | archive job enqueue + status polling | JWT | 30s / 256MB |
| `drive-archive-worker-fn` | archive ZIP job worker | async (SQS) | 300s / 1024MB |

## v2 API Surface
### Private (JWT)
- `POST /v2/files/uploads`
- `PATCH /v2/files/{fileId}`
- `DELETE /v2/files/{fileId}`
- `GET /v2/folders/{folderId}/children`
- `POST /v2/folders/{folderId}/folders`
- `PATCH /v2/folders/{folderId}`
- `DELETE /v2/folders/{folderId}`
- `GET /v2/shares/inbound`
- `GET /v2/files/{fileId}/shares`
- `PUT /v2/files/{fileId}/shares/{principal}`
- `PATCH /v2/files/{fileId}/shares/{principal}`
- `DELETE /v2/files/{fileId}/shares/{principal}`
- `POST /v2/files/{fileId}/public-links`
- `GET /v2/files/{fileId}/public-links`
- `PATCH /v2/public-links/{token}`
- `DELETE /v2/public-links/{token}`
- `POST /v2/download/files/{fileId}`
- `POST /v2/download/archives`
- `GET /v2/download/archives/{archiveJobId}`

### Public (no JWT)
- `GET /v2/public-links/{token}`
- `POST /v2/public-links/{token}/download`

## Data Model (v2)
| Area | Design | Status |
|---|---|---|
| Primary table | `MetadataTableV2` (new table, dual-run safe) | done |
| Parent-child index | `GSI1` (`owner+parentFolderId`) | done |
| Reverse id lookup | `GSI2` (file/folder id lookup) | done |
| Inbound shares | `GSI3` (`principal -> file`) | done |
| Public token lookup | `GSI4` (`token -> link`) | done |

## Phase Plan
| Phase | Owner | Status | Exit criteria |
|---|---|---|---|
| 0. Baseline + safety rails | Backend | planned | contract tests + SLO baseline + correlation id standard |
| 1. Shared core extraction | Backend | in-progress | shared_v2 core and unit tests completed |
| 2. v2 infra + lambdas | Backend + Platform | in-progress | all v2 handlers deployed with least privilege IAM |
| 3. Dual-run + parity | Backend + Frontend + Data | planned | backfill/parity pass and canary ramp complete |
| 4. Cutover + cleanup | Backend | planned | v1 frozen, route removal, table retirement after soak |

## Implemented in this repo revision
- Added `backend/lambdas/shared_v2/*` core modules.
- Added v2 handlers:
  - `backend/lambdas/v2_files/handler.py`
  - `backend/lambdas/v2_folders/handler.py`
  - `backend/lambdas/v2_shares/handler.py`
  - `backend/lambdas/v2_public_links_admin/handler.py`
  - `backend/lambdas/v2_download/handler.py`
  - `backend/lambdas/v2_public_download/handler.py`
  - `backend/lambdas/v2_archive_api/handler.py`
  - `backend/lambdas/v2_archive_worker/handler.py`
- Added v2 infra in `backend/cloudformation_stack.yaml` (table/indexes, queue, roles, functions, integrations, routes, permissions, outputs).
- Updated `backend/deploy.sh` to package/deploy all v1 + v2 lambdas.

## Remaining high-value tasks
| Task | Owner | Status |
|---|---|---|
| v1->v2 backfill job | Data | planned |
| parity verifier job + SLO thresholds | Data + Backend | planned |
| backend integration and contract test suite | Backend | planned |
| frontend canary + progressive traffic ramp | Frontend + Backend | planned |
| v1 deprecation messaging + hard removal | Backend | planned |
