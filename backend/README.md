# Backend - Personal Cloud Storage (v2 API)

Serverless AWS backend for private file storage, sharing, public links, and async archive downloads.

## Stack components

- API Gateway HTTP API (JWT auth for private routes)
- Cognito User Pool + App Client
- Lambda functions (Python 3.11)
  - `drive-files-fn`
  - `drive-folders-fn`
  - `drive-shares-fn`
  - `drive-public-links-admin-fn`
  - `drive-download-fn`
  - `drive-public-download-fn`
  - `drive-archive-api-fn`
  - `drive-archive-worker-fn`
- S3 bucket for file bytes + generated archive ZIP files
- DynamoDB metadata table `MetadataTableV2` (single-table design with GSIs + TTL)
- SQS queue for archive jobs

## Deploy

```bash
cp .env.example .env
./deploy.sh                 # defaults: ENV_NAME=dev, AWS_REGION=eu-central-1
./deploy.sh prod eu-west-1 # custom environment and region
```

The deploy script:
- packages v2 Lambda zips from `lambdas/`
- uploads artifacts to an env-specific S3 artifact bucket (hash-versioned keys)
- deploys `cloudformation_stack.yaml` with artifact bucket/code-key parameters
- updates Lambda code through CloudFormation only (no post-deploy `update-function-code` drift step)

## CloudFormation outputs to keep

- `ApiEndpoint`
- `UserPoolId`
- `UserPoolClientId`
- `S3BucketName`
- `MetadataTableV2Name`
- `ArchiveJobQueueUrl`

## Routes

### Private routes (JWT)

| Method | Path | Lambda |
|---|---|---|
| `POST` | `/v2/files/uploads` | `drive-files-fn` |
| `POST` | `/v2/files/{fileId}/finalize` | `drive-files-fn` |
| `PATCH` | `/v2/files/{fileId}` | `drive-files-fn` |
| `DELETE` | `/v2/files/{fileId}` | `drive-files-fn` |
| `GET` | `/v2/folders/{folderId}/children` | `drive-folders-fn` |
| `POST` | `/v2/folders/{folderId}/folders` | `drive-folders-fn` |
| `PATCH` | `/v2/folders/{folderId}` | `drive-folders-fn` |
| `DELETE` | `/v2/folders/{folderId}` | `drive-folders-fn` |
| `GET` | `/v2/shares/inbound` | `drive-shares-fn` |
| `GET` | `/v2/files/{fileId}/shares` | `drive-shares-fn` |
| `PUT` | `/v2/files/{fileId}/shares/{principal}` | `drive-shares-fn` |
| `PATCH` | `/v2/files/{fileId}/shares/{principal}` | `drive-shares-fn` |
| `DELETE` | `/v2/files/{fileId}/shares/{principal}` | `drive-shares-fn` |
| `POST` | `/v2/files/{fileId}/public-links` | `drive-public-links-admin-fn` |
| `GET` | `/v2/files/{fileId}/public-links` | `drive-public-links-admin-fn` |
| `PATCH` | `/v2/public-links/{token}` | `drive-public-links-admin-fn` |
| `DELETE` | `/v2/public-links/{token}` | `drive-public-links-admin-fn` |
| `POST` | `/v2/download/files/{fileId}` | `drive-download-fn` |
| `POST` | `/v2/download/archives` | `drive-archive-api-fn` |
| `GET` | `/v2/download/archives/{archiveJobId}` | `drive-archive-api-fn` |

### Public routes (no JWT)

| Method | Path | Lambda |
|---|---|---|
| `GET` | `/v2/public-links/{token}` | `drive-public-download-fn` |
| `POST` | `/v2/public-links/{token}/download` | `drive-public-download-fn` |

## Notes

- Share/public-link expiry uses DynamoDB TTL (`ttl`) plus in-code checks.
- Upload lifecycle is two-step: init (`pending`) then finalize (`ready`) after object confirmation.
- Archive downloads are async via SQS worker; client polls job status endpoint.
- Legacy v1 routes (`/upload`, `/download`, `/zip`, `/files`, `/public/{token}`) and v1 lambdas were removed.

## Local backend tests

```bash
python3 -m unittest discover -s backend/tests -p 'test_*.py'
```

## Local benchmarks

```bash
python3 backend/benchmarks/run_benchmarks.py --smoke
python3 backend/benchmarks/run_benchmarks.py
```

## CI

- Workflow: `/Users/adonev/workspace/cloud-storage-system/.github/workflows/backend-ci.yml`
- Runs on push/PR:
  - lambda compile checks
  - backend unittest suite
  - benchmark smoke checks
