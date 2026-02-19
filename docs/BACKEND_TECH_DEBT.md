# Backend Tech Debt Register

## Document Control

| Field | Value |
|---|---|
| Status | done |
| Last updated | 2026-02-18 |
| Owner | Backend |
| Reviewers | Platform, Security |
| Historical backfill | not planned |

## Status Legend

- `planned`: accepted debt, not started
- `in-progress`: partially mitigated
- `done`: mitigation implemented and validated

## P0 Reliability/Security

| ID | Debt | Source | Owner | Status | Remediation |
|---|---|---|---|---|---|
| P0-1 | Share permission enforcement in download path | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_download/handler.py` | Backend | done | Download URL issuance requires owner access or active share with permission `download/edit`. |
| P0-2 | Move/rename consistency guarantees | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_files/handler.py`, `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_folders/handler.py` | Backend | done | v2 uses stable IDs and in-place metadata updates instead of path-key delete/reinsert behavior. |
| P0-3 | Pagination safety for recursive operations | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_folders/handler.py`, `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_archive_worker/handler.py` | Backend | done | Recursive traversal loops paginate and now use deque-based BFS queues for lower overhead. |
| P0-4 | Upload metadata before object existence | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_files/handler.py`, `/Users/adonev/workspace/cloud-storage-system/frontend/src/api.ts` | Backend + Frontend | done | Explicit finalize flow (`POST /v2/files/{fileId}/finalize`) marks file `ready` only after S3 object confirmation. |
| P0-5 | CORS origin safety | `/Users/adonev/workspace/cloud-storage-system/backend/cloudformation_stack.yaml` | Platform | done | CORS origins are environment-parameterized via `AllowedOrigins`. |

## P1 Maintainability

| ID | Debt | Source | Owner | Status | Remediation |
|---|---|---|---|---|---|
| P1-1 | Monolithic action router | v1 backend design | Backend | done | Removed with domain-based v2 lambdas. |
| P1-2 | Opaque action payload API contracts | v1 API design | Backend | done | Replaced with explicit route-based v2 API. |
| P1-3 | Duplicated utility logic across lambdas | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/shared_v2/` | Backend | done | Shared core modules are extracted and used by v2 handlers. |
| P1-4 | Placeholder lambda code + post-deploy code update drift | `/Users/adonev/workspace/cloud-storage-system/backend/cloudformation_stack.yaml`, `/Users/adonev/workspace/cloud-storage-system/backend/deploy.sh` | Platform | done | Stack now receives artifact bucket/code-key parameters and deploys Lambda code through CloudFormation only. |
| P1-5 | Missing formal backend test suite | `/Users/adonev/workspace/cloud-storage-system/backend/tests/`, `/Users/adonev/workspace/cloud-storage-system/.github/workflows/backend-ci.yml` | Backend + Platform | done | Unit/contract tests added and wired into CI workflow. |

## P2 Performance/Cost

| ID | Debt | Source | Owner | Status | Remediation |
|---|---|---|---|---|---|
| P2-1 | List enrichment (`isShared`, `hasPublicLink`) not denormalized | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_files/handler.py`, `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_folders/handler.py`, `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_shares/handler.py`, `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_public_links_admin/handler.py` | Backend | done | File-level counters are maintained and returned directly in list responses (`isShared`, `hasPublicLink`) without extra list-time lookups. |
| P2-2 | Large-folder listing pressure tuning | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_folders/handler.py`, `/Users/adonev/workspace/cloud-storage-system/backend/benchmarks/run_benchmarks.py` | Backend | done | Listing path tuned and benchmark coverage added for high-cardinality pagination scenarios. |
| P2-3 | Archive worker throughput/cost tuning | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_archive_worker/handler.py`, `/Users/adonev/workspace/cloud-storage-system/backend/benchmarks/run_benchmarks.py` | Backend | done | Worker traversal queue optimized and benchmark harness added for archive zip throughput tracking. |
| P2-4 | Principal display metadata strategy | `/Users/adonev/workspace/cloud-storage-system/backend/lambdas/v2_shares/handler.py` | Backend | done | Canonical principal display field persisted on share records (`principalDisplay`) and returned by share-list APIs. |

## Active Remediation Queue

No open items in this debt register.
