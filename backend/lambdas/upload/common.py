import json
import os
import boto3
from botocore.config import Config
from decimal import Decimal

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
