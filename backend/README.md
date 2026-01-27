# Backend - Personal Cloud Storage

Serverless AWS backend for the personal cloud storage system.

## Architecture

- API Gateway HTTP API with JWT authentication
- Cognito for user management
- Lambda functions (Python 3.11)
- S3 with Intelligent-Tiering
- DynamoDB with TTL for share expiration

## Deploy

```bash
chmod +x deploy.sh
./deploy.sh              # dev environment, eu-central-1
./deploy.sh prod eu-west-1  # custom environment and region
```

## After Deployment

Save these outputs for frontend configuration:
- `ApiEndpoint` - API URL
- `UserPoolId` - Cognito User Pool ID
- `UserPoolClientId` - Cognito Client ID

## API Endpoints

All require `Authorization: Bearer <token>` header.

| Method | Path | Description |
|--------|------|-------------|
| POST | /upload | Get presigned upload URL |
| POST | /download | Get presigned download URL |
| POST | /files | List files (action: list) |

## Cost Estimate (~1TB)

~$25-30/month total (S3 Intelligent-Tiering + DynamoDB on-demand + Lambda free tier)
