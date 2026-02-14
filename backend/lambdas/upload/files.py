import time
import random
import string
from botocore.exceptions import ClientError
from common import s3, table, BUCKET, EXPIRY, response, utc_now_iso
from path_utils import normalize_path, normalize_list_path, validate_path_segment
from db_helpers import user_pk, file_sk, file_gsi, find_file_by_id, get_folder_or_404, file_sk_prefix, folder_sk_prefix
from boto3.dynamodb.conditions import Key


def list_files(user_id, folder=None):
    list_path = normalize_list_path(folder)
    is_root = list_path is None or list_path == '/'

    # Files in current directory
    fp = file_sk_prefix('/') if is_root else file_sk_prefix(list_path)
    file_result = table.query(
        KeyConditionExpression=Key('pk').eq(user_pk(user_id)) & Key('sk').begins_with(fp)
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
    # Root folders have sk like FOLDER#/Name, so prefix must be FOLDER#/
    # (folder_sk_prefix('/') yields FOLDER#// which never matches)
    fldp = 'FOLDER#/' if is_root else folder_sk_prefix(list_path)
    folder_result = table.query(
        KeyConditionExpression=Key('pk').eq(user_pk(user_id)) & Key('sk').begins_with(fldp)
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

    filename = str(filename).strip()
    if '/' in filename or '..' in filename:
        return response(400, {'error': 'filename must not contain / or ..'})
    ok, err = validate_path_segment(filename, 'filename')
    if not ok:
        return err

    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    file_id = f'{int(time.time() * 1000)}-{random_suffix}'

    normalized_path = normalize_path(file_path)

    # Auto-disambiguate: if a file with the same name already exists, append (1), (2), etc.
    filename = _disambiguate_filename(user_id, normalized_path, filename)
    s3_key = f'files/{user_id}/{file_id}/{filename}'

    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': BUCKET, 'Key': s3_key},
        ExpiresIn=EXPIRY
    )

    now = utc_now_iso()
    file_item = {
        'pk': user_pk(user_id),
        'sk': file_sk(normalized_path, filename),
        'gsi1pk': file_gsi(file_id),
        'gsi1sk': file_gsi(file_id),
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
        'filename': filename,
        's3Key': s3_key,
        'expiresIn': EXPIRY
    })


def _file_exists_in_folder(user_id, path, filename):
    """Check if a file with this name already exists at the given path."""
    sk = file_sk(path, filename)
    result = table.get_item(Key={'pk': user_pk(user_id), 'sk': sk})
    return result.get('Item') is not None


def _disambiguate_filename(user_id, path, filename):
    """Return a unique filename in the folder by appending (N) if needed."""
    if not _file_exists_in_folder(user_id, path, filename):
        return filename

    # Split into name and extension
    dot_idx = filename.rfind('.')
    if dot_idx > 0:
        base, ext = filename[:dot_idx], filename[dot_idx:]
    else:
        base, ext = filename, ''

    counter = 1
    while counter < 1000:
        candidate = f'{base} ({counter}){ext}'
        if not _file_exists_in_folder(user_id, path, candidate):
            return candidate
        counter += 1

    # Fallback: use timestamp suffix
    return f'{base} ({int(time.time())}){ext}'


def move_file(user_id, file_id, destination_path):
    """Move a file to a different folder. S3 key stays the same."""
    file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return err

    dest = normalize_path(destination_path)

    # Validate destination folder exists (unless root)
    if dest != '/':
        _folder, folder_err = get_folder_or_404(user_id, dest)
        if folder_err:
            return response(404, {'error': 'Destination folder not found', 'path': dest})

    old_sk = file_item['sk']
    filename = file_item['filename']
    new_sk = file_sk(dest, filename)

    if old_sk == new_sk:
        return response(200, {'message': 'File already in destination', 'fileId': file_id, 'newPath': dest})

    # Check for name conflict at destination
    if _file_exists_in_folder(user_id, dest, filename):
        return response(409, {
            'error': 'A file with that name already exists in the destination folder',
            'filename': filename,
            'path': dest
        })

    now = utc_now_iso()

    # Build new item from old, updating path-related fields
    new_item = dict(file_item)
    new_item['sk'] = new_sk
    new_item['path'] = dest
    new_item['updatedAt'] = now

    try:
        # Delete old, write new (atomic per-item)
        table.delete_item(Key={'pk': file_item['pk'], 'sk': old_sk})
        table.put_item(Item=new_item)
    except ClientError as e:
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

    file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return err

    old_sk = file_item['sk']
    file_path = file_item['path']
    new_sk = file_sk(file_path, name)

    if file_item['filename'] == name:
        return response(200, {'message': 'Name unchanged', 'fileId': file_id, 'newName': name})

    # Check for name conflict
    if _file_exists_in_folder(user_id, file_path, name):
        return response(409, {
            'error': 'A file with that name already exists in this folder',
            'filename': name,
            'path': file_path
        })

    now = utc_now_iso()

    new_item = dict(file_item)
    new_item['sk'] = new_sk
    new_item['filename'] = name
    new_item['updatedAt'] = now

    try:
        table.delete_item(Key={'pk': file_item['pk'], 'sk': old_sk})
        table.put_item(Item=new_item)
    except ClientError as e:
        print(f'rename_file failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'File renamed', 'fileId': file_id, 'newName': name})


def delete_file(user_id, file_id):
    file_item, items, err = find_file_by_id(user_id, file_id)
    if err:
        return err

    try:
        s3.delete_object(Bucket=BUCKET, Key=file_item['s3Key'])
    except ClientError as e:
        print(f'S3 delete failed: {e}')

    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

    return response(200, {'message': 'Deleted', 'fileId': file_id})
