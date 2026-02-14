import time
import random
import string
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from common import table, response, utc_now_iso
from path_utils import validate_path, validate_path_segment, MAX_PATH_LENGTH
from db_helpers import user_pk, folder_sk, folder_gsi, get_folder_or_404, file_sk_prefix, folder_sk_prefix


def create_folder(user_id, folder_name, parent_path=None):
    if not folder_name or not str(folder_name).strip():
        return response(400, {'error': 'folderName required'})

    name = str(folder_name).strip().strip('/')
    if not name:
        return response(400, {'error': 'folderName required'})

    ok, err = validate_path_segment(name, 'folderName')
    if not ok:
        return err
    if '/' in name:
        return response(400, {'error': 'folderName must not contain /'})

    # Validate and normalize parent path
    parent, err = validate_path(parent_path, allow_root=True)
    if err is not None:
        return err

    full_path = f'/{name}' if parent == '/' else f'{parent}/{name}'
    if len(full_path) > MAX_PATH_LENGTH:
        return response(400, {'error': f'path too long (max {MAX_PATH_LENGTH})'})

    sk_folder = folder_sk(full_path)

    # For nested folders, ensure parent folder exists
    if parent != '/':
        _parent_item, parent_err = get_folder_or_404(user_id, parent)
        if parent_err:
            return response(404, {'error': 'Parent folder not found', 'path': parent})

    folder_id = f'{int(time.time() * 1000)}-{"".join(random.choices(string.ascii_lowercase + string.digits, k=8))}'
    now = utc_now_iso()

    folder_item = {
        'pk': user_pk(user_id),
        'sk': sk_folder,
        'gsi1pk': folder_gsi(folder_id),
        'gsi1sk': folder_gsi(folder_id),
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
    normalized, err = validate_path(path, allow_root=False)
    if err is not None:
        return err

    pk = user_pk(user_id)

    folder_item, folder_err = get_folder_or_404(user_id, normalized)
    if folder_err:
        return response(404, {'error': 'Folder not found', 'path': normalized})

    # Reject if folder contains files
    file_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(file_sk_prefix(normalized)),
        Limit=1
    )
    if file_result.get('Items'):
        return response(400, {'error': 'Folder is not empty (contains files)', 'path': normalized})

    # Reject if folder contains subfolders
    subfolder_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(folder_sk_prefix(normalized)),
        Limit=1
    )
    if subfolder_result.get('Items'):
        return response(400, {'error': 'Folder is not empty (contains subfolders)', 'path': normalized})

    try:
        table.delete_item(Key={'pk': pk, 'sk': folder_sk(normalized)})
    except ClientError as e:
        print(f'delete_item folder failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'Folder deleted', 'path': normalized})


def _collect_nested_items(user_id, folder_path):
    """Return all DynamoDB items nested under folder_path (folders + files)."""
    pk = user_pk(user_id)
    all_items = []

    # Subfolders (includes the folder itself via exact match, plus children via prefix)
    folder_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(folder_sk(folder_path))
    )
    all_items.extend(folder_result.get('Items', []))

    # Files inside this folder and all subfolders
    file_result = table.query(
        KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(file_sk_prefix(folder_path))
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
    source, err = validate_path(folder_path, allow_root=False)
    if err is not None:
        return err

    dest, err = validate_path(destination_path, allow_root=True)
    if err is not None:
        return err

    pk = user_pk(user_id)

    # Verify source folder exists
    source_item, source_err = get_folder_or_404(user_id, source)
    if source_err:
        return response(404, {'error': 'Source folder not found', 'path': source})

    if source_item.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    # Verify destination exists (unless root)
    if dest != '/':
        _dest_item, dest_err = get_folder_or_404(user_id, dest)
        if dest_err:
            return response(404, {'error': 'Destination folder not found', 'path': dest})

    # Prevent circular move: destination must not be inside source
    if dest == source or dest.startswith(f'{source}/'):
        return response(400, {'error': 'Cannot move a folder into itself or its subfolder'})

    folder_name = source.rsplit('/', 1)[-1]
    new_path = f'/{folder_name}' if dest == '/' else f'{dest}/{folder_name}'

    if source == new_path:
        return response(200, {'message': 'Folder already in destination', 'oldPath': source, 'newPath': new_path})

    # Check destination doesn't already have a folder with same name
    existing = table.get_item(Key={'pk': pk, 'sk': folder_sk(new_path)}).get('Item')
    if existing:
        return response(409, {'error': 'A folder with that name already exists in the destination', 'path': new_path})

    now = utc_now_iso()

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
    except ClientError as e:
        print(f'move_folder batch failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'Folder moved', 'oldPath': source, 'newPath': new_path})


def rename_folder(user_id, folder_path, new_name):
    """Rename a folder by replacing its last path segment. Updates all nested items."""
    source, err = validate_path(folder_path, allow_root=False)
    if err is not None:
        return err

    if not new_name or not str(new_name).strip():
        return response(400, {'error': 'newName required'})

    name = str(new_name).strip()
    ok, err = validate_path_segment(name, 'newName')
    if not ok:
        return err
    if '/' in name:
        return response(400, {'error': 'newName must not contain /'})

    pk = user_pk(user_id)

    # Verify source exists
    source_item, source_err = get_folder_or_404(user_id, source)
    if source_err:
        return response(404, {'error': 'Folder not found', 'path': source})

    if source_item.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    # Compute new path: replace the last segment
    parent = source.rsplit('/', 1)[0] or '/'
    new_path = f'/{name}' if parent == '/' else f'{parent}/{name}'

    if source == new_path:
        return response(200, {'message': 'Name unchanged', 'oldPath': source, 'newPath': new_path})

    # Check no conflict at destination
    existing = table.get_item(Key={'pk': pk, 'sk': folder_sk(new_path)}).get('Item')
    if existing:
        return response(409, {'error': 'A folder with that name already exists', 'path': new_path})

    now = utc_now_iso()

    all_items = _collect_nested_items(user_id, source)
    new_items = _rekey_items(all_items, source, new_path, now)

    try:
        with table.batch_writer() as batch:
            for item in all_items:
                batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})
        with table.batch_writer() as batch:
            for item in new_items:
                batch.put_item(Item=item)
    except ClientError as e:
        print(f'rename_folder batch failed: {e}')
        return response(500, {'error': 'Internal server error'})

    return response(200, {'message': 'Folder renamed', 'oldPath': source, 'newPath': new_path})
