"""
Public download Lambda – handles **unauthenticated** access to public share links.

Routes (determined by HTTP method from API Gateway):
  GET  /public/{token}  →  Return link metadata (filename, size, hasPassword …)
  POST /public/{token}  →  Verify optional password, increment download count,
                            return presigned S3 download URL.
"""

import hashlib
import json
import os
import secrets
import time
import traceback

import boto3
from botocore.config import Config
from decimal import Decimal

# ---------------------------------------------------------------------------
# Environment / AWS clients
# ---------------------------------------------------------------------------

BUCKET = os.environ['BUCKET_NAME']
TABLE_NAME = os.environ['METADATA_TABLE_NAME']
EXPIRY = int(os.environ.get('PRESIGNED_URL_EXPIRY', 3600))

region = os.environ.get('AWS_REGION', 'eu-central-1')
s3_config = Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})
s3 = boto3.client('s3', region_name=region, config=s3_config)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

_PBKDF2_ITERATIONS = 260_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def _response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body, cls=DecimalEncoder),
    }


def _verify_password(password, stored_hash, stored_salt):
    salt = bytes.fromhex(stored_salt)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, _PBKDF2_ITERATIONS)
    return secrets.compare_digest(dk.hex(), stored_hash)


def _extract_token(event):
    """Extract the {token} path parameter from the API Gateway event."""
    return (event.get('pathParameters') or {}).get('token')


def _get_link_item(token):
    """Fetch the PUBLIC_LINK item from DynamoDB. Returns (item, error_response)."""
    if not token:
        return None, _response(400, {'error': 'Token required'})

    pk = f'PUBLIC_LINK#{token}'
    result = table.get_item(Key={'pk': pk, 'sk': 'META'})
    item = result.get('Item')

    if not item or item.get('itemType') != 'PUBLIC_LINK':
        return None, _response(404, {'error': 'Link not found'})

    # Check expiry (DynamoDB TTL is eventually consistent – enforce in code)
    ttl = item.get('ttl')
    if ttl and int(ttl) <= int(time.time()):
        return None, _response(410, {'error': 'Link has expired'})

    return item, None


# ---------------------------------------------------------------------------
# GET  /public/{token}  – return metadata (no download)
# ---------------------------------------------------------------------------

def _handle_get(event):
    token = _extract_token(event)
    item, err = _get_link_item(token)
    if err:
        return err

    return _response(200, {
        'filename': item['filename'],
        'size': item.get('size', 0),
        'contentType': item.get('contentType', 'application/octet-stream'),
        'hasPassword': bool(item.get('passwordHash')),
        'downloadCount': int(item.get('downloadCount', 0)),
        'expiresAt': item.get('expiresAt', ''),
    })


# ---------------------------------------------------------------------------
# POST /public/{token}  – verify password → presigned download URL
# ---------------------------------------------------------------------------

def _handle_post(event):
    token = _extract_token(event)
    item, err = _get_link_item(token)
    if err:
        return err

    # Password check
    stored_hash = item.get('passwordHash')
    if stored_hash:
        body = json.loads(event.get('body') or '{}')
        password = body.get('password', '')
        stored_salt = item.get('passwordSalt', '')
        if not password or not _verify_password(password, stored_hash, stored_salt):
            return _response(403, {'error': 'Incorrect password'})

    # Verify file still exists in S3
    s3_key = item['s3Key']
    try:
        s3.head_object(Bucket=BUCKET, Key=s3_key)
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return _response(404, {'error': 'File not found in storage'})
        raise

    # Atomically increment download count
    pk = f'PUBLIC_LINK#{token}'
    table.update_item(
        Key={'pk': pk, 'sk': 'META'},
        UpdateExpression='ADD downloadCount :one',
        ExpressionAttributeValues={':one': 1},
    )

    # Generate presigned download URL
    download_url = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': BUCKET,
            'Key': s3_key,
            'ResponseContentDisposition': f'attachment; filename="{item["filename"]}"',
        },
        ExpiresIn=EXPIRY,
    )

    print(json.dumps({
        'action': 'public-download',
        'token': token,
        'fileId': item.get('fileId'),
    }))

    return _response(200, {
        'downloadUrl': download_url,
        'filename': item['filename'],
        'contentType': item.get('contentType', 'application/octet-stream'),
        'size': item.get('size', 0),
        'expiresIn': EXPIRY,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def handler(event, context):
    try:
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        if method == 'GET':
            return _handle_get(event)
        elif method == 'POST':
            return _handle_post(event)
        else:
            return _response(405, {'error': 'Method not allowed'})
    except Exception as e:
        print(json.dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        return _response(500, {'error': 'Internal server error'})
