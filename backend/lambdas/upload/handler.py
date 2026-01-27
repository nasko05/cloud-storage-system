import json
import os
import time
import random
import string
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

BUCKET = os.environ['BUCKET_NAME']
TABLE_NAME = os.environ['METADATA_TABLE_NAME']
EXPIRY = int(os.environ.get('PRESIGNED_URL_EXPIRY', 3600))
SHARE_EXPIRY_DAYS = int(os.environ.get('SHARE_EXPIRY_DAYS', 30))

table = dynamodb.Table(TABLE_NAME)


def handler(event, context):
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
        user_id = claims.get('sub')
        user_email = claims.get('email', user_id)

        if not user_id:
            return response(401, {'error': 'Unauthorized'})

        body = json.loads(event.get('body') or '{}')
        action = body.get('action')

        if action == 'list':
            return list_files(user_id, body.get('folder'))
        elif action == 'shared-with-me':
            return list_shared_with_me(user_id)
        elif action == 'share':
            return share_file(user_id, user_email, body)
        elif action == 'unshare':
            return unshare_file(user_id, body)
        elif action == 'delete':
            return delete_file(user_id, body.get('fileId'))
        else:
            return upload_file(user_id, user_email, body)

    except Exception as e:
        print(f'Upload error: {e}')
        return response(500, {'error': 'Internal server error'})


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body)
    }


def list_files(user_id, folder=None):
    prefix = f'FILE#{folder}' if folder else 'FILE#'
    result = table.query(
        KeyConditionExpression=Key('pk').eq(f'USER#{user_id}') & Key('sk').begins_with(prefix)
    )
    files = [
        {
            'fileId': item['fileId'],
            'filename': item['filename'],
            'path': item['path'],
            'contentType': item['contentType'],
            'size': item['size'],
            'createdAt': item['createdAt']
        }
        for item in result.get('Items', [])
        if item.get('itemType') == 'FILE'
    ]
    return response(200, {'files': files})


def list_shared_with_me(user_id):
    result = table.query(
        KeyConditionExpression=Key('pk').eq(f'SHARED#{user_id}') & Key('sk').begins_with('FILE#')
    )
    files = [
        {
            'fileId': item['fileId'],
            'sharedBy': item['sharedBy'],
            'sharedByEmail': item['sharedByEmail'],
            'filename': item['filename'],
            'permission': item['permission'],
            'expiresAt': item['expiresAt']
        }
        for item in result.get('Items', [])
    ]
    return response(200, {'files': files})


def share_file(user_id, user_email, body):
    file_id = body.get('fileId')
    share_with_user_id = body.get('shareWithUserId')
    share_with_email = body.get('shareWithEmail')
    expiry_days = body.get('expiryDays', SHARE_EXPIRY_DAYS)
    permission = body.get('permission', 'read')

    if not file_id or (not share_with_user_id and not share_with_email):
        return response(400, {'error': 'fileId and shareWithUserId or shareWithEmail required'})

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(f'FILE#{file_id}') & Key('gsi1sk').eq(f'FILE#{file_id}')
    )
    items = result.get('Items', [])
    if not items or items[0].get('ownerId') != user_id:
        return response(403, {'error': 'Access denied - not owner'})


    file = items[0]
    target_user_id = share_with_user_id or share_with_email
    ttl = int(time.time()) + (expiry_days * 24 * 60 * 60)
    now = datetime.utcnow().isoformat() + 'Z'

    share_item = {
        'pk': f'SHARED#{target_user_id}',
        'sk': f'FILE#{file_id}',
        'gsi1pk': f'FILE#{file_id}',
        'gsi1sk': f'SHARED#{target_user_id}',
        'fileId': file_id,
        'filename': file['filename'],
        's3Key': file['s3Key'],
        'sharedBy': user_id,
        'sharedByEmail': user_email,
        'sharedWith': target_user_id,
        'permission': permission,
        'sharedAt': now,
        'expiresAt': datetime.utcfromtimestamp(ttl).isoformat() + 'Z',
        'ttl': ttl,
        'itemType': 'SHARE'
    }
    table.put_item(Item=share_item)
    print(json.dumps({'action': 'share', 'userId': user_id, 'fileId': file_id, 'sharedWith': target_user_id}))
    return response(200, {
        'message': 'Shared successfully',
        'fileId': file_id,
        'sharedWith': target_user_id,
        'expiresAt': share_item['expiresAt']
    })


def unshare_file(user_id, body):
    file_id = body.get('fileId')
    revoke_user_id = body.get('revokeUserId')
    if not file_id or not revoke_user_id:
        return response(400, {'error': 'fileId and revokeUserId required'})

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(f'FILE#{file_id}') & Key('gsi1sk').eq(f'FILE#{file_id}')
    )
    items = result.get('Items', [])
    if not items or items[0].get('ownerId') != user_id:
        return response(403, {'error': 'Access denied - not owner'})

    table.delete_item(Key={'pk': f'SHARED#{revoke_user_id}', 'sk': f'FILE#{file_id}'})
    return response(200, {'message': 'Share revoked', 'fileId': file_id, 'revokedUser': revoke_user_id})


def delete_file(user_id, file_id):
    if not file_id:
        return response(400, {'error': 'fileId required'})

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(f'FILE#{file_id}')
    )
    items = result.get('Items', [])
    file_item = next((i for i in items if i.get('itemType') == 'FILE'), None)

    if not file_item or file_item.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    try:
        s3.delete_object(Bucket=BUCKET, Key=file_item['s3Key'])
    except Exception as e:
        print(f'S3 delete failed: {e}')

    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

    return response(200, {'message': 'Deleted', 'fileId': file_id})


def upload_file(user_id, user_email, body):
    filename = body.get('filename')
    file_path = body.get('path', '/')
    content_type = body.get('contentType', 'application/octet-stream')
    size = body.get('size', 0)

    if not filename:
        return response(400, {'error': 'filename required'})

    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    file_id = f'{int(time.time() * 1000)}-{random_suffix}'
    s3_key = f'files/{user_id}/{file_id}/{filename}'

    normalized_path = '/'.join(filter(None, file_path.split('/')))
    normalized_path = f'/{normalized_path}' if normalized_path else '/'

    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': BUCKET,
            'Key': s3_key,
            'ContentType': content_type,
            'Metadata': {'owner-id': user_id, 'file-id': file_id}
        },
        ExpiresIn=EXPIRY
    )

    now = datetime.utcnow().isoformat() + 'Z'
    file_item = {
        'pk': f'USER#{user_id}',
        'sk': f'FILE#{normalized_path}/{filename}',
        'gsi1pk': f'FILE#{file_id}',
        'gsi1sk': f'FILE#{file_id}',
        'fileId': file_id,
        'filename': filename,
        'path': normalized_path,
        's3Key': s3_key,
        'contentType': content_type,
        'size': size,
        'ownerId': user_id,
        'ownerEmail': user_email,
        'createdAt': now,
        'updatedAt': now,
        'itemType': 'FILE'
    }
    table.put_item(Item=file_item)
    print(json.dumps({'action': 'upload', 'userId': user_id, 'fileId': file_id, 'filename': filename}))

    return response(200, {
        'uploadUrl': upload_url,
        'fileId': file_id,
        's3Key': s3_key,
        'expiresIn': EXPIRY
    })
