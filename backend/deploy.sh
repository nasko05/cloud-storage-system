#!/bin/bash
set -e

# Load env vars from .env (if present)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

PROFILE="${AWS_PROFILE:-adonev-login}"
ENV_NAME="${1:-$ENV_NAME}"
ENV_NAME="${ENV_NAME:-dev}"
REGION="${2:-$AWS_REGION}"
REGION="${REGION:-eu-central-1}"
STACK_NAME="${ENV_NAME}-personal-cloudstorage"
BUILD_DIR="build"

# Check credentials and auto-login if expired
if ! aws sts get-caller-identity --profile "$PROFILE" &>/dev/null; then
  echo "AWS credentials expired. Logging in..."
  aws sso login --profile "$PROFILE"
fi

ACCOUNT_ID=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text)

echo "Deploying Personal Cloud Storage Backend"
echo "  Environment: $ENV_NAME"
echo "  Region: $REGION"
echo "  Stack: $STACK_NAME"
echo "  Account: $ACCOUNT_ID"
echo ""

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

package_lambda() {
  local lambda_dir="$1"
  local zip_name="$2"
  local shared_dir="$3"

  echo "Packaging ${lambda_dir} Lambda..."
  pushd "lambdas/${lambda_dir}" >/dev/null

  local shared_files=()
  if [ -n "$shared_dir" ]; then
    while IFS= read -r -d '' file; do
      shared_files+=("$(basename "$file")")
    done < <(find "../${shared_dir}" -maxdepth 1 -type f -name '*.py' -print0)

    if [ ${#shared_files[@]} -gt 0 ]; then
      cp "../${shared_dir}"/*.py .
    fi
  fi

  zip -rq "../../${BUILD_DIR}/${zip_name}" *.py

  if [ ${#shared_files[@]} -gt 0 ]; then
    for f in "${shared_files[@]}"; do
      rm -f "$f"
    done
  fi

  popd >/dev/null
}

package_lambda "v2_files" "v2-files-lambda.zip" "shared_v2"
package_lambda "v2_folders" "v2-folders-lambda.zip" "shared_v2"
package_lambda "v2_shares" "v2-shares-lambda.zip" "shared_v2"
package_lambda "v2_public_links_admin" "v2-public-links-admin-lambda.zip" "shared_v2"
package_lambda "v2_download" "v2-download-lambda.zip" "shared_v2"
package_lambda "v2_public_download" "v2-public-download-lambda.zip" "shared_v2"
package_lambda "v2_archive_api" "v2-archive-api-lambda.zip" "shared_v2"
package_lambda "v2_archive_worker" "v2-archive-worker-lambda.zip" "shared_v2"

ARTIFACT_BUCKET="${ENV_NAME}-cloudstorage-artifacts-${ACCOUNT_ID}-${REGION}"

artifact_hash() {
  local file_path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file_path" | awk '{print $1}'
    return
  fi
  sha256sum "$file_path" | awk '{print $1}'
}

artifact_key() {
  local file_path="$1"
  local name="$2"
  local hash
  hash="$(artifact_hash "$file_path")"
  echo "lambdas/${name}-${hash:0:16}.zip"
}

echo "Creating artifact bucket: $ARTIFACT_BUCKET"
if ! aws s3 ls "s3://$ARTIFACT_BUCKET" --profile "$PROFILE" 2>/dev/null; then
  aws s3 mb "s3://$ARTIFACT_BUCKET" --region "$REGION" --profile "$PROFILE"
fi

echo "Uploading Lambda packages to S3..."
FILES_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-files-lambda.zip" "v2-files-lambda")"
FOLDERS_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-folders-lambda.zip" "v2-folders-lambda")"
SHARES_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-shares-lambda.zip" "v2-shares-lambda")"
PUBLIC_LINKS_ADMIN_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-public-links-admin-lambda.zip" "v2-public-links-admin-lambda")"
DOWNLOAD_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-download-lambda.zip" "v2-download-lambda")"
PUBLIC_DOWNLOAD_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-public-download-lambda.zip" "v2-public-download-lambda")"
ARCHIVE_API_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-archive-api-lambda.zip" "v2-archive-api-lambda")"
ARCHIVE_WORKER_CODE_KEY="$(artifact_key "$BUILD_DIR/v2-archive-worker-lambda.zip" "v2-archive-worker-lambda")"

aws s3 cp "$BUILD_DIR/v2-files-lambda.zip" "s3://$ARTIFACT_BUCKET/$FILES_CODE_KEY" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/v2-folders-lambda.zip" "s3://$ARTIFACT_BUCKET/$FOLDERS_CODE_KEY" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/v2-shares-lambda.zip" "s3://$ARTIFACT_BUCKET/$SHARES_CODE_KEY" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/v2-public-links-admin-lambda.zip" "s3://$ARTIFACT_BUCKET/$PUBLIC_LINKS_ADMIN_CODE_KEY" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/v2-download-lambda.zip" "s3://$ARTIFACT_BUCKET/$DOWNLOAD_CODE_KEY" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/v2-public-download-lambda.zip" "s3://$ARTIFACT_BUCKET/$PUBLIC_DOWNLOAD_CODE_KEY" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/v2-archive-api-lambda.zip" "s3://$ARTIFACT_BUCKET/$ARCHIVE_API_CODE_KEY" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/v2-archive-worker-lambda.zip" "s3://$ARTIFACT_BUCKET/$ARCHIVE_WORKER_CODE_KEY" --profile "$PROFILE"

echo "Deploying CloudFormation stack..."
aws cloudformation deploy \
  --template-file cloudformation_stack.yaml \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    EnvironmentName="$ENV_NAME" \
    ArtifactBucketName="$ARTIFACT_BUCKET" \
    DriveFilesCodeKey="$FILES_CODE_KEY" \
    DriveFoldersCodeKey="$FOLDERS_CODE_KEY" \
    DriveSharesCodeKey="$SHARES_CODE_KEY" \
    DrivePublicLinksAdminCodeKey="$PUBLIC_LINKS_ADMIN_CODE_KEY" \
    DriveDownloadCodeKey="$DOWNLOAD_CODE_KEY" \
    DrivePublicDownloadCodeKey="$PUBLIC_DOWNLOAD_CODE_KEY" \
    DriveArchiveApiCodeKey="$ARCHIVE_API_CODE_KEY" \
    DriveArchiveWorkerCodeKey="$ARCHIVE_WORKER_CODE_KEY" \
  --no-fail-on-empty-changeset

echo ""
echo "Deployment complete!"
echo ""
echo "Stack Outputs:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
  --output table \
  --no-cli-pager

rm -rf "$BUILD_DIR"

echo ""
echo "Done! Backend is ready."
echo ""
echo "Save these values for frontend configuration:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint` || OutputKey==`UserPoolId` || OutputKey==`UserPoolClientId`].[OutputKey,OutputValue]' \
  --output table \
  --no-cli-pager
