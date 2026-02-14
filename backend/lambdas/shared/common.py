import json
import os
import boto3
from botocore.config import Config
from decimal import Decimal
from datetime import datetime, timezone

# Environment
BUCKET = os.environ['BUCKET_NAME']
TABLE_NAME = os.environ['METADATA_TABLE_NAME']
EXPIRY = int(os.environ.get('PRESIGNED_URL_EXPIRY', 3600))
SHARE_EXPIRY_DAYS = int(os.environ.get('SHARE_EXPIRY_DAYS', 30))

# Clients
region = os.environ.get('AWS_REGION', 'eu-central-1')
s3_config = Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})
s3 = boto3.client('s3', region_name=region, config=s3_config)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body, cls=DecimalEncoder)
    }


def extract_user(event):
    """Extract (user_id, user_email) from the JWT authorizer claims.

    Raises ValueError if user_id (sub) is missing.
    """
    claims = (
        event.get('requestContext', {})
        .get('authorizer', {})
        .get('jwt', {})
        .get('claims', {})
    )
    user_id = claims.get('sub')
    if not user_id:
        raise ValueError('Unauthorized: missing sub claim')
    user_email = claims.get('email', user_id)
    return user_id, user_email


def utc_now_iso():
    """Return the current UTC time as an ISO 8601 string ending in 'Z'."""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
