# Backend Tech Debt Register

## Document Control


| Field        | Value              |
| ------------ | ------------------ |
| Status       | in-progress        |
| Last updated | 2026-02-18         |
| Owner        | Backend            |
| Reviewers    | Platform, Security |


## Status Legend

- `planned`: accepted debt, not started
- `in-progress`: partial mitigation implemented
- `done`: mitigation implemented in code

## P0 Reliability/Security


| ID   | Debt                                                    | Source                                                                 | Owner    | Status      | Remediation                                                                                                                                                 |
| ---- | ------------------------------------------------------- | ---------------------------------------------------------------------- | -------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0-1 | Share permission not enforced in download authorization | `backend/lambdas/download/handler.py`                                  | Backend  | done        | Added explicit permission gate (`download`/`edit` only) for shared downloads.                                                                               |
| P0-2 | Non-transactional move/rename risks inconsistency       | `backend/lambdas/upload/files.py`, `backend/lambdas/upload/folders.py` | Backend  | in-progress | v2 model uses immutable ids + parent references; v1 remains until cutover.                                                                                  |
| P0-3 | Folder subtree operations missed pagination             | `backend/lambdas/upload/folders.py`                                    | Backend  | done        | Added pagination loops in nested-item collection and paginated recursion in v2 folder delete traversal.                                                     |
| P0-4 | Upload metadata written before object exists            | `backend/lambdas/upload/files.py`                                      | Backend  | in-progress | v2 creates `pending` file state and upgrades to `ready` on first successful object validation in download flow; explicit finalize event path still pending. |
| P0-5 | Open CORS defaults                                      | `backend/cloudformation_stack.yaml`                                    | Platform | done        | `AllowedOrigins` now defaults to local dev origin and is wired into API + S3 CORS config.                                                                   |


## P1 Maintainability


| ID   | Debt                                             | Source                                                   | Owner    | Status      | Remediation                                                                                                         |
| ---- | ------------------------------------------------ | -------------------------------------------------------- | -------- | ----------- | ------------------------------------------------------------------------------------------------------------------- |
| P1-1 | God lambda multiplexer (`/upload` + `action`)    | `backend/lambdas/upload/handler.py`                      | Backend  | in-progress | New domain-specific v2 lambdas/routes implemented; v1 retained during dual-run.                                     |
| P1-2 | Action-based API contract hard to evolve         | v1 API design                                            | Backend  | in-progress | Introduced explicit REST-like v2 routes under `/v2/*`.                                                              |
| P1-3 | Duplicate utility/bootstrap logic across lambdas | multiple backend lambdas                                 | Backend  | in-progress | Added `backend/lambdas/shared_v2` shared core; migration of all v1 code pending.                                    |
| P1-4 | CFN placeholder code + post-deploy update drift  | `backend/cloudformation_stack.yaml`, `backend/deploy.sh` | Platform | planned     | Move to artifact-based deploy inside template (SAM/CFN package flow) and remove direct `update-function-code` step. |
| P1-5 | No formal backend test suite                     | backend repo                                             | Backend  | planned     | Add unit + integration + contract suites and wire to CI.                                                            |


## P2 Performance/Cost


| ID   | Debt                                                  | Source                                    | Owner   | Status      | Remediation                                                                         |
| ---- | ----------------------------------------------------- | ----------------------------------------- | ------- | ----------- | ----------------------------------------------------------------------------------- |
| P2-1 | N+1 lookups for share/public flags in list operations | `backend/lambdas/upload/files.py`         | Backend | planned     | Replace with denormalized flags/counters in v2 projection model.                    |
| P2-2 | Missing pagination on list endpoints                  | v1 listing handlers                       | Backend | in-progress | v2 endpoints use `limit/cursor`; v1 remains partially unpaged.                      |
| P2-3 | ZIP builder memory/cost profile                       | `backend/lambdas/zip_download/handler.py` | Backend | in-progress | Added async archive worker; stream S3 object chunks into zip output in v2 worker.   |
| P2-4 | Cognito lookup fan-out for sharing display            | `backend/lambdas/upload/sharing.py`       | Backend | planned     | Store principal metadata at write time in v2 and avoid per-request Cognito fan-out. |
| P2-5 | Legacy `/files` alias increases surface area          | `backend/cloudformation_stack.yaml`       | Backend | planned     | Deprecate after v2 cutover and remove in phase 4.                                   |


## Active Remediation Queue


| Item                                        | Owner              | Status  |
| ------------------------------------------- | ------------------ | ------- |
| Backfill from v1 table to `MetadataTableV2` | Data               | planned |
| Parity verifier + drift alarms              | Data + Backend     | planned |
| v2 contract/integration test harness        | Backend            | planned |
| Frontend canary and progressive v2 rollout  | Frontend + Backend | planned |
| Remove v1 routes and retire legacy table    | Backend + Platform | planned |


