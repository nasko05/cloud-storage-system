# Frontend - Personal Cloud Storage

Simple React frontend for the personal cloud storage system.

## Setup

1. Copy `.env.example` to `.env` and fill in values from backend deployment:

```bash
cp .env.example .env
```

2. Install dependencies:

```bash
npm install
```

3. Start development server:

```bash
npm start
```

Opens at http://localhost:3000

## Deploy to AWS (S3 + CloudFront)

```bash
chmod +x deploy.sh
./deploy.sh
```

This will:
1. Create S3 bucket for static files
2. Create CloudFront CDN distribution
3. Build the React app
4. Upload to S3
5. Invalidate CloudFront cache

Your site will be available at `https://xxxxxx.cloudfront.net`

Cost: ~$1-2/month (mostly CloudFront requests)

## Features

- Login with Cognito credentials
- Upload files
- Download files
- Delete files
- File list with size display
