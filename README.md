# Personal Cloud Storage System

Serverless personal cloud storage (Google Drive style) built on AWS.

## What is implemented

- Email/password auth with Amazon Cognito (register, confirm, login)
- File uploads with presigned S3 URLs
- Folder hierarchy (create, move, rename, delete-empty)
- File operations (list, move, rename, delete)
- Sharing to specific users (with permission + expiry)
- Public links with optional password and expiry
- Public download page at `/s/{token}` (no login required)
- Bulk ZIP download for selected files/folders
- Grid/list views, context menu, drag/drop move, drag/drop upload
- Upload progress + cancellation

## Architecture at a glance

- **Frontend:** React + TypeScript + MUI
- **API:** API Gateway HTTP API + JWT authorizer
- **Auth:** Cognito User Pool
- **Compute:** 8 Python Lambdas (domain-split v2 API + async archive worker)
- **Storage:** S3 (encrypted, versioned, lifecycle rules)
- **Metadata/ACL:** DynamoDB `MetadataTableV2` (single-table design with GSIs + TTL)
- **Hosting:** S3 + CloudFront (private origin via OAC)

For full details, see `/Users/adonev/workspace/cloud-storage-system/docs/ARCHITECTURE.md`.

## Repository layout

```text
cloud-storage-system/
|-- .aws/config.example
|-- backend/
|   |-- cloudformation_stack.yaml
|   |-- deploy.sh
|   `-- lambdas/
|-- frontend/
|   |-- cloudformation_hosting.yaml
|   |-- deploy.sh
|   `-- src/
`-- docs/
    |-- ARCHITECTURE.md
    `-- ROADMAP.md
```

## Quick start

### 1. Configure AWS CLI profile

Copy/merge `.aws/config.example` into `~/.aws/config`, then authenticate:

```bash
aws sso login --profile adonev-login
```

### 2. Deploy backend

```bash
cd backend
cp .env.example .env
./deploy.sh
```

Save stack outputs:
- `ApiEndpoint`
- `UserPoolId`
- `UserPoolClientId`

### 3. Run frontend locally

```bash
cd frontend
cp .env.example .env
# fill REACT_APP_API_ENDPOINT / REACT_APP_USER_POOL_ID / REACT_APP_COGNITO_CLIENT_ID
npm install
npm start
```

Open [http://localhost:3000](http://localhost:3000).

### 4. Deploy frontend hosting (optional)

```bash
cd frontend
./deploy.sh
```

## Docs

- Architecture deep dive: `/Users/adonev/workspace/cloud-storage-system/docs/ARCHITECTURE.md`
- Backend details: `/Users/adonev/workspace/cloud-storage-system/backend/README.md`
- Frontend details: `/Users/adonev/workspace/cloud-storage-system/frontend/README.md`

## License

MIT
