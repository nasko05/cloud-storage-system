import time
import random
import string
from datetime import datetime, timezone
from common import table, response

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

    full_path = parent if parent == '/' else f'{parent}/{name}'
    if len(full_path) > MAX_PATH_LENGTH:
        return response(400, {'error': f'path too long (max {MAX_PATH_LENGTH})'})

    sk_folder = f'FOLDER#{full_path}'

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
    table.put_item(Item=folder_item)

    return response(200, {
        'message': 'Folder created',
        'folderId': folder_id,
        'folderName': name,
        'path': full_path
    })
