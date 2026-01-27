# Personal Cloud Storage

A serverless personal cloud storage system (like Google Drive) built on AWS. Designed for ~1TB personal/family use with cost optimization.

## Project Structure

```
personal-drive/
├── backend/          # AWS infrastructure (CloudFormation, Lambda)
│   ├── deploy.sh
│   ├── cloudformation_stack.yaml
│   └── lambdas/
└── frontend/         # React web app
    ├── src/
    └── public/
```

## Quick Start

### 1. Deploy Backend

```bash
cd backend
chmod +x deploy.sh
./deploy.sh
```

Save the outputs: `ApiEndpoint`, `UserPoolId`, `UserPoolClientId`

### 2. Create a User

```bash
USER_POOL_ID=<from-outputs>

aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username your@email.com \
  --user-attributes Name=email,Value=your@email.com Name=email_verified,Value=true \
  --temporary-password "TempPass123!"

aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username your@email.com \
  --password "YourSecurePassword123!" \
  --permanent
```

### 3. Run Frontend

```bash
cd frontend
cp .env.example .env
# Edit .env with values from step 1
npm install
npm start
```

## Architecture

- API Gateway HTTP API with JWT authentication
- Cognito for user management
- Lambda (Python) for business logic
- S3 with Intelligent-Tiering for storage
- DynamoDB for metadata with TTL for share expiration

## Cost Estimate (~1TB)

| Service | Monthly |
|---------|---------|
| S3 Intelligent-Tiering | ~$23 |
| DynamoDB | ~$1-5 |
| Lambda | ~$0 |
| API Gateway | ~$1-3 |
| Total | ~$25-30 |

## Documentation

- [Backend README](backend/README.md) - API details, deployment options
- [Frontend README](frontend/README.md) - Setup, build instructions

## License

MIT
