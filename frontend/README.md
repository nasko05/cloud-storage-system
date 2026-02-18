# Frontend - Personal Cloud Storage

React + TypeScript web client for the cloud storage backend.

## Tech stack

- React 18 + TypeScript
- MUI + MUI X Data Grid
- `amazon-cognito-identity-js` for auth

## Implemented UX

- Login/register/confirm with Cognito
- My files + Shared with me tabs
- Folder tree navigation
- Grid and list views (persisted preference)
- Multi-select, context menu, rename, move, delete
- Drag/drop move into folders
- Drag/drop upload (files and folders) with progress + cancel
- Share dialog (user shares + public links)
- Public link page at `/s/{token}` for unauthenticated downloads
- Image thumbnails with presigned URL cache
- Recent and frequent files (localStorage)

## Local development

### 1. Configure environment

```bash
cp .env.example .env
```

Set at least:
- `REACT_APP_API_ENDPOINT`
- `REACT_APP_USER_POOL_ID`
- `REACT_APP_COGNITO_CLIENT_ID`
- `REACT_APP_REGION`

### 2. Install and run

```bash
npm install
npm start
```

App runs at [http://localhost:3000](http://localhost:3000).

## Build

```bash
npm run build
```

## Deploy (S3 + CloudFront)

```bash
cp .env.example .env
./deploy.sh
```

Deploy script behavior:
- deploys `cloudformation_hosting.yaml`
- builds the app
- syncs `build/` to S3
- invalidates CloudFront cache

## Key source files

- App shell: `/Users/adonev/workspace/cloud-storage-system/frontend/src/App.tsx`
- API client: `/Users/adonev/workspace/cloud-storage-system/frontend/src/api.ts`
- Business services: `/Users/adonev/workspace/cloud-storage-system/frontend/src/service/driveService.ts`
- Upload engine: `/Users/adonev/workspace/cloud-storage-system/frontend/src/hooks/useUploadManager.ts`
- Share/public-link UI: `/Users/adonev/workspace/cloud-storage-system/frontend/src/components/ShareDialog.tsx`
- Public download page: `/Users/adonev/workspace/cloud-storage-system/frontend/src/components/PublicDownloadPage.tsx`
