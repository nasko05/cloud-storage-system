import time
import random
import string
from datetime import datetime
from common import table, response


def _normalize_path(path):
    """Normalize path to a single leading slash, no trailing slash (except root)."""
    if not path or not path.strip():
        return '/'
    parts = [p for p in path.strip().split('/') if p and p != '.' and p != '..']
    if not parts:
        return '/'
    return '/' + '/'.join(parts)


def create_folder(user_id, folder_name, parent_path=None):
    if not folder_name or not str(folder_name).strip():
        return response(400, {'error': 'folderName required'})

    name = str(folder_name).strip().strip('/')
    if not name:
        return response(400, {'error': 'folderName required'})

    if '/' in name:
        return response(400, {'error': 'folderName must not contain /'})

    parent = _normalize_path(parent_path or '')
    full_path = parent if parent == '/' else f'{parent}/{name}'
    sk_folder = f'FOLDER#{full_path}'

    # Check if folder already exists at this path
    try:
        existing = table.get_item(
            Key={'pk': f'USER#{user_id}', 'sk': sk_folder}
        )
        if existing.get('Item'):
            return response(409, {'error': 'Folder already exists', 'path': full_path})
    except Exception as e:
        print(f'get_item failed: {e}')
        return response(500, {'error': 'Internal server error'})

    folder_id = f'{int(time.time() * 1000)}-{"".join(random.choices(string.ascii_lowercase + string.digits, k=8))}'
    now = datetime.utcnow().isoformat() + 'Z'

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
    table.put_item(Item=folder_item)

    return response(200, {
        'message': 'Folder created',
        'folderId': folder_id,
        'folderName': name,
        'path': full_path
    })
