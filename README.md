# Personal Cloud Storage

A serverless personal cloud storage system (like Google Drive) built on AWS. Designed for ~1TB personal/family use with cost optimization.

## Project Structure

```
personal-drive/
├── .aws/
│   └── config.example   # AWS CLI SSO profile template
├── backend/              # AWS infrastructure (CloudFormation, Lambda)
│   ├── deploy.sh
│   ├── cloudformation_stack.yaml
│   └── lambdas/
└── frontend/             # React web app
    ├── src/
    └── public/
```

## AWS profile (for deploy scripts)

Backend and frontend `deploy.sh` scripts use the AWS CLI with a named profile (e.g. SSO). Configure it once:

1. **Create or edit your AWS config** (not in this repo):
   ```bash
   mkdir -p ~/.aws
   # Append the example profile block to your config:
   cat .aws/config.example >> ~/.aws/config
   # Or copy and paste the [profile ...] section from .aws/config.example into ~/.aws/config
   ```

2. **Fill in the placeholders** in `~/.aws/config`:
   - `sso_start_url` — Your IAM Identity Center portal URL (e.g. from IAM Identity Center → Settings → AWS access portal URL).
   - `sso_account_id` — 12-digit AWS account ID (Console → account dropdown → Account ID).
   - `sso_role_name` — Permission set name (e.g. `AdministratorAccess`), from IAM Identity Center → Permission sets or the role you pick in the SSO portal.

3. **Log in** when needed:
   ```bash
   aws sso login --profile adonev-login
   ```

Use the same profile name in `frontend/.env` as `AWS_PROFILE` if you use a different name.

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
