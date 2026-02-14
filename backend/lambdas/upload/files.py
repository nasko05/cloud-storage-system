import time
import random
import string
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from common import s3, table, BUCKET, EXPIRY, response


def _normalized_list_path(folder):
    if folder is None or (isinstance(folder, str) and not folder.strip()):
        return None
    path = folder.strip().rstrip('/')
    return path if path.startswith('/') else f'/{path}'


def list_files(user_id, folder=None):
    list_path = _normalized_list_path(folder)
    is_root = list_path is None or list_path == '/'

    # Files in current directory
    file_prefix = 'FILE#/' if is_root else f'FILE#{list_path}/'
    file_result = table.query(
        KeyConditionExpression=Key('pk').eq(f'USER#{user_id}') & Key('sk').begins_with(file_prefix)
    )
    target_path = '/' if is_root else list_path
    files = [
        {
            'fileId': item['fileId'],
            'filename': item['filename'],
            'path': item['path'],
            'contentType': item['contentType'],
            'size': item['size'],
            'createdAt': item['createdAt']
        }
        for item in file_result.get('Items', [])
        if item.get('itemType') == 'FILE' and item.get('path') == target_path
    ]

    # Folders in current directory (direct children only)
    folder_prefix = 'FOLDER#/' if is_root else f'FOLDER#{list_path}/'
    folder_result = table.query(
        KeyConditionExpression=Key('pk').eq(f'USER#{user_id}') & Key('sk').begins_with(folder_prefix)
    )
    if is_root:
        folders = [
            {
                'folderId': item['folderId'],
                'name': item['name'],
                'path': item['path'],
                'createdAt': item['createdAt']
            }
            for item in folder_result.get('Items', [])
            if item.get('itemType') == 'FOLDER' and item.get('path', '').count('/') == 1
        ]
    else:
        prefix_with_slash = f'{list_path}/'
        folders = [
            {
                'folderId': item['folderId'],
                'name': item['name'],
                'path': item['path'],
                'createdAt': item['createdAt']
            }
            for item in folder_result.get('Items', [])
            if item.get('itemType') == 'FOLDER'
            and item.get('path', '').startswith(prefix_with_slash)
            and item['path'].replace(prefix_with_slash, '').count('/') == 0
        ]

    return response(200, {'files': files, 'folders': folders})


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


def _normalize_path(path):
    """Normalize path: single leading slash, no trailing slash (except root)."""
    if not path or not str(path).strip():
        return '/'
    parts = [p for p in str(path).strip().split('/') if p and p != '.' and p != '..']
    if not parts:
        return '/'
    return '/' + '/'.join(parts)


def _find_file_by_id(user_id, file_id):
    """Look up a file via GSI1 and verify ownership. Returns (file_item, all_items, error_response)."""
    if not file_id:
        return None, [], response(400, {'error': 'fileId required'})

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(f'FILE#{file_id}')
    )
    items = result.get('Items', [])
    file_item = next((i for i in items if i.get('itemType') == 'FILE'), None)

    if not file_item or file_item.get('ownerId') != user_id:
        return None, items, response(403, {'error': 'Access denied'})

    return file_item, items, None


def move_file(user_id, file_id, destination_path):
    """Move a file to a different folder. S3 key stays the same."""
    file_item, _items, err = _find_file_by_id(user_id, file_id)
    if err:
        return err

    dest = _normalize_path(destination_path)

    # Validate destination folder exists (unless root)
    if dest != '/':
        pk = f'USER#{user_id}'
        folder_check = table.get_item(Key={'pk': pk, 'sk': f'FOLDER#{dest}'})
        if not folder_check.get('Item'):
            return response(404, {'error': 'Destination folder not found', 'path': dest})

    old_sk = file_item['sk']
    filename = file_item['filename']
    new_sk = f'FILE#{dest}/{filename}'

    if old_sk == new_sk:
        return response(200, {'message': 'File already in destination', 'fileId': file_id, 'newPath': dest})

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Build new item from old, updating path-related fields
    new_item = dict(file_item)
    new_item['sk'] = new_sk
    new_item['path'] = dest
    new_item['updatedAt'] = now

    try:
        # Delete old, write new (atomic per-item)
        table.delete_item(Key={'pk': file_item['pk'], 'sk': old_sk})
        table.put_item(Item=new_item)
    except Exception as e:
        print(f'move_file failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'File moved', 'fileId': file_id, 'newPath': dest})


def rename_file(user_id, file_id, new_name):
    """Rename a file. S3 key stays the same; download uses DynamoDB filename for Content-Disposition."""
    if not new_name or not str(new_name).strip():
        return response(400, {'error': 'newName required'})

    name = str(new_name).strip()
    if '/' in name:
        return response(400, {'error': 'newName must not contain /'})
    if len(name) > 255:
        return response(400, {'error': 'newName too long (max 255 characters)'})

    file_item, _items, err = _find_file_by_id(user_id, file_id)
    if err:
        return err

    old_sk = file_item['sk']
    file_path = file_item['path']
    new_sk = f'FILE#{file_path}/{name}'

    if file_item['filename'] == name:
        return response(200, {'message': 'Name unchanged', 'fileId': file_id, 'newName': name})

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    new_item = dict(file_item)
    new_item['sk'] = new_sk
    new_item['filename'] = name
    new_item['updatedAt'] = now

    try:
        table.delete_item(Key={'pk': file_item['pk'], 'sk': old_sk})
        table.put_item(Item=new_item)
    except Exception as e:
        print(f'rename_file failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'File renamed', 'fileId': file_id, 'newName': name})


def delete_file(user_id, file_id):
    file_item, items, err = _find_file_by_id(user_id, file_id)
    if err:
        return err

    try:
        s3.delete_object(Bucket=BUCKET, Key=file_item['s3Key'])
    except Exception as e:
        print(f'S3 delete failed: {e}')

    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

    return response(200, {'message': 'Deleted', 'fileId': file_id})
