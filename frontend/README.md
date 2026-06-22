# Frontend — Personal Cloud Storage

React + TypeScript web client. In production it is built and served by the
FastAPI backend (same origin); for development it can run standalone against a
local backend.

## Tech stack

- React 18 + TypeScript
- MUI + MUI X Data Grid
- Built-in email/password auth (JWT stored in `localStorage`)

## Implemented UX

- Login / register (email confirmation optional, off by default)
- My files + Shared with me tabs
- Folder tree navigation
- Grid and list views (persisted preference)
- Multi-select, context menu, rename, move, delete
- Drag/drop move into folders
- Drag/drop upload (files and folders) with progress + cancel
- Share dialog (user shares + public links)
- Public link page at `/s/{token}` for unauthenticated downloads
- Recent and frequent files (localStorage)

## Local development

```bash
cp .env.example .env        # REACT_APP_API_ENDPOINT=http://localhost:8000
npm install --legacy-peer-deps
npm start                   # http://localhost:3000
```

`REACT_APP_API_ENDPOINT` is the only setting; leave it empty for same-origin
(production) and point it at your backend for dev.

## Build

```bash
CI=false npm run build      # output in build/ (copied into the Docker image)
```

## Key source files

- App shell: `src/App.tsx`
- API client: `src/api.ts`
- Auth client: `src/auth.ts`
- Business services: `src/service/driveService.ts`
- Upload engine: `src/hooks/useUploadManager.ts`
- Share/public-link UI: `src/components/ShareDialog.tsx`
- Public download page: `src/components/PublicDownloadPage.tsx`
