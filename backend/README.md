# Backend - Personal Cloud Storage

Serverless AWS backend for private file storage, sharing, and public links.

## Stack components

- API Gateway HTTP API (JWT auth for private routes)
- Cognito User Pool + App Client
- Lambda functions (Python 3.11)
  - `upload-fn`
  - `download-fn`
  - `public-download-fn`
  - `zip-download-fn`
- S3 bucket for file bytes + generated ZIP archives
- DynamoDB metadata table (single-table design, GSI1, TTL)

## Deploy

```bash
cp .env.example .env
./deploy.sh                 # defaults: ENV_NAME=dev, AWS_REGION=eu-central-1
./deploy.sh prod eu-west-1 # custom environment and region
```

The deploy script:
- packages Lambda zips from `lambdas/`
- uploads artifacts to an env-specific S3 artifact bucket
- deploys `cloudformation_stack.yaml`
- updates Lambda function code from the artifact bucket

## CloudFormation outputs to keep

- `ApiEndpoint`
- `UserPoolId`
- `UserPoolClientId`
- `S3BucketName`
- `DynamoDBTableName`

## Routes

| Method | Path | Auth | Lambda |
|---|---|---|---|
| `POST` | `/upload` | JWT | `upload-fn` |
| `POST` | `/download` | JWT | `download-fn` |
| `POST` | `/zip` | JWT | `zip-download-fn` |
| `POST` | `/files` | JWT | `upload-fn` (legacy alias route) |
| `GET` | `/public/{token}` | none | `public-download-fn` |
| `POST` | `/public/{token}` | none | `public-download-fn` |

## `/upload` action API

`/upload` is an action router. If `action` is missing, request is treated as file-upload metadata request.

### Actions

| `action` | Required fields | Result |
|---|---|---|
| `list` | optional `folder` | list files + folders in path |
| `delete` | `fileId` | delete file and related metadata |
| `create-folder` | `folderName`, optional `path` | create folder |
| `delete-folder` | `path` | delete empty folder |
| `move-file` | `fileId`, `destinationPath` | move file metadata |
| `rename-file` | `fileId`, `newName` | rename file metadata |
| `move-folder` | `folderPath`, `destinationPath` | move folder subtree |
| `rename-folder` | `folderPath`, `newName` | rename folder subtree |
| `shared-with-me` | none | list files shared with caller |
| `share` | `fileId`, `shareWithEmail` or `shareWithUserId`, optional `permission`, optional `expiryDays` | create share |
| `unshare` | `fileId`, `revokeUserId` | revoke share |
| `list-shares` | `fileId` | list active shares for owned file |
| `update-share` | `fileId`, `targetUserId`, `permission` | update permission |
| `create-public-link` | `fileId`, optional `password`, optional `expiryDays` | create public token link |
| `list-public-links` | `fileId` | list active links for file |
| `delete-public-link` | `token` | delete public link |
| `update-public-link` | `token`, optional `password`, optional `removePassword`, optional `expiryDays` | update link settings |

### Upload metadata request (no `action`)

Body fields:
- `filename` (required)
- `contentType` (optional)
- `size` (optional)
- `path` (optional)

Returns:
- `uploadUrl` (presigned PUT URL)
- `fileId`
- `s3Key`
- `expiresIn`

## Other endpoint contracts

- `POST /download`: requires `fileId`; returns presigned download URL if caller owns file or has a valid share.
- `POST /zip`: accepts `fileIds[]` and `folderPaths[]`; returns presigned ZIP download URL.
- `GET /public/{token}`: metadata for public link.
- `POST /public/{token}`: optional password, increments download count, returns presigned download URL.

## Notes

- Share/public-link expiry uses DynamoDB TTL (`ttl`) plus in-code checks.
- ZIP downloads are stored under `zips/` and auto-expire after 1 day via S3 lifecycle rule.
- S3 object keys remain stable during move/rename; only DynamoDB path/name keys are changed.
