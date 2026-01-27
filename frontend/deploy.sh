#!/bin/bash
set -e

ENV_NAME="${1:-dev}"
REGION="${2:-eu-central-1}"
STACK_NAME="${ENV_NAME}-cloudstorage-frontend"

echo "Deploying Frontend (S3 + CloudFront)"
echo "  Environment: $ENV_NAME"
echo "  Region: $REGION"
echo ""

# Deploy CloudFormation stack
echo "Creating S3 bucket and CloudFront distribution..."
aws cloudformation deploy \
  --template-file cloudformation_hosting.yaml \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --parameter-overrides EnvironmentName="$ENV_NAME" \
  --no-fail-on-empty-changeset

# Get bucket name and distribution ID
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendBucketName`].OutputValue' \
  --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
  --output text)

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomain`].OutputValue' \
  --output text)

# Build React app
echo ""
echo "Building React app..."
npm run build

# Upload to S3
echo ""
echo "Uploading to S3..."
aws s3 sync build/ "s3://$BUCKET" --delete

# Invalidate CloudFront cache
echo ""
echo "Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --no-cli-pager

echo ""
echo "Done!"
echo ""
echo "Your frontend is live at:"
echo "  $CLOUDFRONT_URL"
echo ""
echo "Note: CloudFront may take a few minutes to propagate globally."
