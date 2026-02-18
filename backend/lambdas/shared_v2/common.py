import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.config import Config

BUCKET = os.environ['BUCKET_NAME']
TABLE_NAME = os.environ['METADATA_TABLE_NAME']
EXPIRY = int(os.environ.get('PRESIGNED_URL_EXPIRY', 3600))
SHARE_EXPIRY_DAYS = int(os.environ.get('SHARE_EXPIRY_DAYS', 30))
IDEMPOTENCY_TTL_SECONDS = int(os.environ.get('IDEMPOTENCY_TTL_SECONDS', 86400))
ARCHIVE_JOB_TTL_DAYS = int(os.environ.get('ARCHIVE_JOB_TTL_DAYS', 1))
ARCHIVE_QUEUE_URL = os.environ.get('ARCHIVE_QUEUE_URL', '')

region = os.environ.get('AWS_REGION', 'eu-central-1')
s3_config = Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})
s3 = boto3.client('s3', region_name=region, config=s3_config)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)
sqs = boto3.client('sqs', region_name=region)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def response(status_code, body, headers=None):
    out_headers = {'Content-Type': 'application/json'}
    if headers:
        out_headers.update(headers)
    return {
        'statusCode': status_code,
        'headers': out_headers,
        'body': json.dumps(body, cls=DecimalEncoder)
    }


def extract_user(event):
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
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def utc_epoch():
    return int(datetime.now(timezone.utc).timestamp())


def parse_json_body(event):
    raw = event.get('body')
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)
