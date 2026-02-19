# Backend Lambda Refactor Plan (v2 Only)

## Document Control

| Field | Value |
|---|---|
| Status | done |
| Last updated | 2026-02-18 |
| Owner | Backend |
| Reviewers | Platform, Frontend |
| Migration scope | v2-only redesign |
| Historical backfill | out of scope by decision |

## Status Legend

- `planned`: accepted work, not started
- `in-progress`: partially implemented
- `done`: implemented and validated

## Program Status

| Workstream | Owner | Status | Notes |
|---|---|---|---|
| v2 domain lambda split | Backend | done | Domain lambdas are active for files, folders, shares, public links, download, public download, and archive API/worker. |
| v2 infrastructure | Platform | done | `MetadataTableV2`, GSIs, SQS queue/DLQ, IAM scopes, routes, and permissions are active in template. |
| frontend cutover to v2 | Frontend | done | Frontend API client uses `/v2/*` endpoints only. |
| v1 decommission | Backend | done | v1 handlers/routes removed from active backend stack. |
| deploy hardening | Platform | done | Artifact-native CloudFormation deployment implemented; no post-deploy `update-function-code` step. |
| reliability hardening | Backend | done | Upload finalize flow (`POST /v2/files/{fileId}/finalize`) enforces `pending -> ready` transition after object confirmation. |
| test and CI baseline | Backend + Platform | done | Backend unit tests and benchmark smoke checks are wired into CI workflow. |
| perf benchmark suite | Backend | done | Local benchmark harness added for large listing and archive zip worker paths. |

## Target Lambda Topology (v2)

| Lambda | Responsibility | Auth | Runtime |
|---|---|---|---|
| `drive-files-fn` | upload init/finalize, file rename/move/delete | JWT | 30s / 256MB |
| `drive-folders-fn` | folder create/list/move/rename/delete | JWT | 30s / 256MB |
| `drive-shares-fn` | share create/list/update/revoke, inbound shares | JWT | 30s / 256MB |
| `drive-public-links-admin-fn` | owner public-link CRUD | JWT | 30s / 256MB |
| `drive-download-fn` | private/shared download URL issuance | JWT | 30s / 256MB |
| `drive-public-download-fn` | public token metadata/download | none | 30s / 256MB |
| `drive-archive-api-fn` | archive enqueue + status | JWT | 30s / 256MB |
| `drive-archive-worker-fn` | archive job processing | async (SQS) | 300s / 1024MB |

## API Surface (v2)

### Private routes (JWT)

- `POST /v2/files/uploads`
- `POST /v2/files/{fileId}/finalize`
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

### Public routes (no JWT)

- `GET /v2/public-links/{token}`
- `POST /v2/public-links/{token}/download`

## Validation Snapshot

| Check | Status | Evidence |
|---|---|---|
| Backend python compile | done | `python3 -m py_compile backend/lambdas/shared_v2/*.py backend/lambdas/v2_*/*.py` |
| Backend unit/contract tests | done | `python3 -m unittest discover -s backend/tests -p 'test_*.py'` |
| Backend benchmark smoke run | done | `python3 backend/benchmarks/run_benchmarks.py --smoke --assert-max-seconds 20` |
| Frontend build against v2 API client | done | `npm --prefix frontend run build` |
| Template parse validation | done | YAML parse check on `backend/cloudformation_stack.yaml` |

## Remaining Work

No open migration or debt-remediation work from this plan scope.
