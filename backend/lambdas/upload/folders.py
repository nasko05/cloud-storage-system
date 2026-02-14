import json
import time
import random
import string
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from common import table, response

def _debug_log(message, data, hypothesis_id):
    """Log to stdout for CloudWatch (backend runs in AWS Lambda)."""
    payload = {
        'timestamp': int(time.time() * 1000),
        'location': 'folders.py:create_folder',
        'message': message,
        'data': data,
        'hypothesisId': hypothesis_id
    }
    print(json.dumps(payload))

# Path validation limits
MAX_PATH_LENGTH = 2048
MAX_SEGMENT_LENGTH = 255
MAX_DEPTH = 128


def _normalize_path(path):
    """Normalize path to a single leading slash, no trailing slash (except root)."""
    if not path or not str(path).strip():
        return '/'
    parts = [p for p in str(path).strip().split('/') if p and p != '.' and p != '..']
    if not parts:
        return '/'
    return '/' + '/'.join(parts)


def _validate_path_segment(segment, field_name='path'):
    """Validate a single path segment (no slashes). Returns (True, None) or (False, error_response)."""
    if not segment or not segment.strip():
        return False, response(400, {'error': f'{field_name} segment cannot be empty'})
    s = segment.strip()
    if len(s) > MAX_SEGMENT_LENGTH:
        return False, response(400, {'error': f'{field_name} segment too long (max {MAX_SEGMENT_LENGTH})'})
    if '\x00' in s:
        return False, response(400, {'error': f'{field_name} contains invalid characters'})
    return True, None


def _validate_path(path, allow_root=True):
    """
    Validate a full path. Returns (normalized_path, None) or (None, error_response).
    Rejects '..', empty segments, and enforces length/depth limits.
    """
    if path is None:
        return ('/', None) if allow_root else (None, response(400, {'error': 'path required'}))
    raw = str(path).strip()
    if not raw:
        return ('/', None) if allow_root else (None, response(400, {'error': 'path required'}))

    if '..' in raw:
        return None, response(400, {'error': 'path must not contain ..'})
    if raw.startswith('//') or '//' in raw:
        return None, response(400, {'error': 'path must not contain empty segments'})

    normalized = _normalize_path(path)
    if len(normalized) > MAX_PATH_LENGTH:
        return None, response(400, {'error': f'path too long (max {MAX_PATH_LENGTH})'})

    parts = [p for p in normalized.split('/') if p]
    if len(parts) > MAX_DEPTH:
        return None, response(400, {'error': f'path too deep (max {MAX_DEPTH} levels)'})

    for part in parts:
        ok, err = _validate_path_segment(part, 'path')
        if not ok:
            return None, err

    return normalized, None


def create_folder(user_id, folder_name, parent_path=None):
    if not folder_name or not str(folder_name).strip():
        return response(400, {'error': 'folderName required'})

    name = str(folder_name).strip().strip('/')
    if not name:
        return response(400, {'error': 'folderName required'})

    ok, err = _validate_path_segment(name, 'folderName')
    if not ok:
        return err
    if '/' in name:
        return response(400, {'error': 'folderName must not contain /'})

    # Validate and normalize parent path
    parent, err = _validate_path(parent_path, allow_root=True)
    if err is not None:
        return err

    full_path = f'/{name}' if parent == '/' else f'{parent}/{name}'
    if len(full_path) > MAX_PATH_LENGTH:
        return response(400, {'error': f'path too long (max {MAX_PATH_LENGTH})'})

    sk_folder = f'FOLDER#{full_path}'

    # #region agent log
    _debug_log('create_folder computed path', {
        'folder_name_raw': folder_name,
        'parent_path_raw': parent_path,
        'parent_normalized': parent,
        'name': name,
        'full_path': full_path,
        'sk_folder': sk_folder
    }, 'A')
    _debug_log('before get_item existing check', {'sk_folder': sk_folder}, 'D')
    # #endregion

    # For nested folders, ensure parent folder exists
    if parent != '/':
        try:
            parent_sk = f'FOLDER#{parent}'
            parent_item = table.get_item(
                Key={'pk': f'USER#{user_id}', 'sk': parent_sk}
            )
            if not parent_item.get('Item'):
                return response(404, {'error': 'Parent folder not found', 'path': parent})
        except Exception as e:
            print(f'get_item parent failed: {e}')
            return response(500, {'error': 'Internal server error'})

    folder_id = f'{int(time.time() * 1000)}-{"".join(random.choices(string.ascii_lowercase + string.digits, k=8))}'
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    folder_item = {
        'pk': f'USER#{user_id}',
        'sk': sk_folder,
        'gsi1pk': f'FOLDER#{folder_id}',
        'gsi1sk': f'FOLDER#{folder_id}',
        'folderId': folder_id,
        'name': name,
        'path': full_path,
        'ownerId': user_id,
        'createdAt': now,
        'updatedAt': now,
        'itemType': 'FOLDER'
    }

    # Conditional put: only create if key does not exist (idempotent, avoids race with duplicate requests)
    try:
        table.put_item(
            Item=folder_item,
            ConditionExpression='attribute_not_exists(#sk)',
            ExpressionAttributeNames={'#sk': 'sk'}
        )
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            # #region agent log
            _debug_log('put_item conditional check failed (folder already exists)', {
                'sk_folder': sk_folder,
                'full_path': full_path,
                'runId': 'post-fix'
            }, 'B')
            # #endregion
            return response(409, {'error': 'Folder already exists', 'path': full_path})
        raise

    return response(200, {
        'message': 'Folder created',
        'folderId': folder_id,
        'folderName': name,
        'path': full_path
    })


def delete_folder(user_id, path):
    """Delete a folder. Fails if path is root or folder is not empty (has files or subfolders)."""
    normalized, err = _validate_path(path, allow_root=False)
    if err is not None:
        return err

    sk_folder = f'FOLDER#{normalized}'
    pk = f'USER#{user_id}'

    try:
        folder_item = table.get_item(Key={'pk': pk, 'sk': sk_folder}).get('Item')
    except Exception as e:
        print(f'get_item folder failed: {e}')
        return response(500, {'error': 'Internal server error'})

    if not folder_item or folder_item.get('itemType') != 'FOLDER':
        return response(404, {'error': 'Folder not found', 'path': normalized})

    # Reject if folder contains files
    file_prefix = f'FILE#{normalized}/'
    file_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(file_prefix),
        Limit=1
    )
    if file_result.get('Items'):
        return response(400, {'error': 'Folder is not empty (contains files)', 'path': normalized})

    # Reject if folder contains subfolders
    folder_prefix = f'FOLDER#{normalized}/'
    subfolder_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(folder_prefix),
        Limit=1
    )
    if subfolder_result.get('Items'):
        return response(400, {'error': 'Folder is not empty (contains subfolders)', 'path': normalized})

    try:
        table.delete_item(Key={'pk': pk, 'sk': sk_folder})
    except Exception as e:
        print(f'delete_item folder failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'Folder deleted', 'path': normalized})


def _collect_nested_items(user_id, folder_path):
    """Return all DynamoDB items nested under folder_path (folders + files)."""
    pk = f'USER#{user_id}'
    all_items = []

    # Subfolders (includes the folder itself via exact match, plus children via prefix)
    folder_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(f'FOLDER#{folder_path}')
    )
    all_items.extend(folder_result.get('Items', []))

    # Files inside this folder and all subfolders
    file_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(f'FILE#{folder_path}/')
    )
    all_items.extend(file_result.get('Items', []))

    return all_items


def _rekey_items(items, old_path_prefix, new_path_prefix, now):
    """Create copies of items with path prefixes swapped. Returns list of new items."""
    new_items = []
    for item in items:
        new_item = dict(item)
        sk = item['sk']
        item_type = item.get('itemType')

        # Replace old path prefix with new one in sk
        if item_type == 'FOLDER':
            old_sk_prefix = f'FOLDER#{old_path_prefix}'
            new_sk_prefix = f'FOLDER#{new_path_prefix}'
            new_item['sk'] = sk.replace(old_sk_prefix, new_sk_prefix, 1)
            new_item['path'] = item['path'].replace(old_path_prefix, new_path_prefix, 1)
            # Update name only for the moved folder itself (top level)
            if item['path'] == old_path_prefix:
                new_item['name'] = new_path_prefix.rsplit('/', 1)[-1]
        elif item_type == 'FILE':
            old_sk_prefix = f'FILE#{old_path_prefix}/'
            new_sk_prefix = f'FILE#{new_path_prefix}/'
            new_item['sk'] = sk.replace(old_sk_prefix, new_sk_prefix, 1)
            new_item['path'] = item['path'].replace(old_path_prefix, new_path_prefix, 1)

        new_item['updatedAt'] = now
        new_items.append(new_item)

    return new_items


def move_folder(user_id, folder_path, destination_path):
    """Move a folder (and all nested contents) to a new parent location."""
    source, err = _validate_path(folder_path, allow_root=False)
    if err is not None:
        return err

    dest, err = _validate_path(destination_path, allow_root=True)
    if err is not None:
        return err

    pk = f'USER#{user_id}'

    # Verify source folder exists
    source_item = table.get_item(Key={'pk': pk, 'sk': f'FOLDER#{source}'}).get('Item')
    if not source_item or source_item.get('itemType') != 'FOLDER':
        return response(404, {'error': 'Source folder not found', 'path': source})

    if source_item.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    # Verify destination exists (unless root)
    if dest != '/':
        dest_item = table.get_item(Key={'pk': pk, 'sk': f'FOLDER#{dest}'}).get('Item')
        if not dest_item:
            return response(404, {'error': 'Destination folder not found', 'path': dest})

    # Prevent circular move: destination must not be inside source
    if dest == source or dest.startswith(f'{source}/'):
        return response(400, {'error': 'Cannot move a folder into itself or its subfolder'})

    folder_name = source.rsplit('/', 1)[-1]
    new_path = f'/{folder_name}' if dest == '/' else f'{dest}/{folder_name}'

    if source == new_path:
        return response(200, {'message': 'Folder already in destination', 'oldPath': source, 'newPath': new_path})

    # Check destination doesn't already have a folder with same name
    existing = table.get_item(Key={'pk': pk, 'sk': f'FOLDER#{new_path}'}).get('Item')
    if existing:
        return response(409, {'error': 'A folder with that name already exists in the destination', 'path': new_path})

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Collect all nested items
    all_items = _collect_nested_items(user_id, source)
    new_items = _rekey_items(all_items, source, new_path, now)

    try:
        # Delete old items, write new items
        with table.batch_writer() as batch:
            for item in all_items:
                batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})
        with table.batch_writer() as batch:
            for item in new_items:
                batch.put_item(Item=item)
    except Exception as e:
        print(f'move_folder batch failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'Folder moved', 'oldPath': source, 'newPath': new_path})


def rename_folder(user_id, folder_path, new_name):
    """Rename a folder by replacing its last path segment. Updates all nested items."""
    source, err = _validate_path(folder_path, allow_root=False)
    if err is not None:
        return err

    if not new_name or not str(new_name).strip():
        return response(400, {'error': 'newName required'})

    name = str(new_name).strip()
    ok, err = _validate_path_segment(name, 'newName')
    if not ok:
        return err
    if '/' in name:
        return response(400, {'error': 'newName must not contain /'})

    pk = f'USER#{user_id}'

    # Verify source exists
    source_item = table.get_item(Key={'pk': pk, 'sk': f'FOLDER#{source}'}).get('Item')
    if not source_item or source_item.get('itemType') != 'FOLDER':
        return response(404, {'error': 'Folder not found', 'path': source})

    if source_item.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    # Compute new path: replace the last segment
    parent = source.rsplit('/', 1)[0] or '/'
    new_path = f'/{name}' if parent == '/' else f'{parent}/{name}'

    if source == new_path:
        return response(200, {'message': 'Name unchanged', 'oldPath': source, 'newPath': new_path})

    # Check no conflict at destination
    existing = table.get_item(Key={'pk': pk, 'sk': f'FOLDER#{new_path}'}).get('Item')
    if existing:
        return response(409, {'error': 'A folder with that name already exists', 'path': new_path})

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    all_items = _collect_nested_items(user_id, source)
    new_items = _rekey_items(all_items, source, new_path, now)

    try:
        with table.batch_writer() as batch:
            for item in all_items:
                batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})
        with table.batch_writer() as batch:
            for item in new_items:
                batch.put_item(Item=item)
    except Exception as e:
        print(f'rename_folder batch failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'Folder renamed', 'oldPath': source, 'newPath': new_path})
