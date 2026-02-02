import time
import random
import string
from datetime import datetime
from boto3.dynamodb.conditions import Key
from common import s3, table, BUCKET, EXPIRY, response


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


def upload_file(user_id, user_email, body):
    import json
    
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
        Params={'Bucket': BUCKET, 'Key': s3_key},
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
