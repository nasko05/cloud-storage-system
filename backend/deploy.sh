#!/bin/bash
set -e

PROFILE="adonev-login"
ENV_NAME="${1:-dev}"
REGION="${2:-eu-central-1}"
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

echo "Packaging Upload Lambda..."
cd lambdas/upload
zip -rq "../../$BUILD_DIR/upload-lambda.zip" handler.py
cd ../..

echo "Packaging Download Lambda..."
cd lambdas/download
zip -rq "../../$BUILD_DIR/download-lambda.zip" handler.py
cd ../..

ARTIFACT_BUCKET="${ENV_NAME}-cloudstorage-artifacts-${ACCOUNT_ID}-${REGION}"

echo "Creating artifact bucket: $ARTIFACT_BUCKET"
if ! aws s3 ls "s3://$ARTIFACT_BUCKET" --profile "$PROFILE" 2>/dev/null; then
  aws s3 mb "s3://$ARTIFACT_BUCKET" --region "$REGION" --profile "$PROFILE"
fi

echo "Uploading Lambda packages to S3..."
aws s3 cp "$BUILD_DIR/upload-lambda.zip" "s3://$ARTIFACT_BUCKET/lambdas/upload-lambda.zip" --profile "$PROFILE"
aws s3 cp "$BUILD_DIR/download-lambda.zip" "s3://$ARTIFACT_BUCKET/lambdas/download-lambda.zip" --profile "$PROFILE"

echo "Deploying CloudFormation stack..."
aws cloudformation deploy \
  --template-file cloudformation_stack.yaml \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    EnvironmentName="$ENV_NAME" \
  --no-fail-on-empty-changeset

echo "Updating Lambda functions with packaged code..."

UPLOAD_FN="${ENV_NAME}-upload-fn"
DOWNLOAD_FN="${ENV_NAME}-download-fn"

aws lambda update-function-code \
  --function-name "$UPLOAD_FN" \
  --s3-bucket "$ARTIFACT_BUCKET" \
  --s3-key "lambdas/upload-lambda.zip" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --no-cli-pager

aws lambda update-function-code \
  --function-name "$DOWNLOAD_FN" \
  --s3-bucket "$ARTIFACT_BUCKET" \
  --s3-key "lambdas/download-lambda.zip" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --no-cli-pager

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
