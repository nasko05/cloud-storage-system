"""
Shared path normalization, validation, and segment helpers.
Single source of truth -- replaces private copies in files.py and folders.py.
"""
from common import response

# Path validation limits
MAX_PATH_LENGTH = 2048
MAX_SEGMENT_LENGTH = 255
MAX_DEPTH = 128


def normalize_path(path, allow_none=False):
    """Normalize path: single leading slash, no trailing slash (except root).

    Filters out empty, '.', and '..' segments.
    If *allow_none* is True and *path* is None/empty, returns None instead of '/'.
    """
    if path is None or (isinstance(path, str) and not path.strip()):
        return None if allow_none else '/'
    parts = [p for p in str(path).strip().split('/') if p and p != '.' and p != '..']
    if not parts:
        return None if allow_none else '/'
    return '/' + '/'.join(parts)


def normalize_list_path(folder):
    """Normalize a folder argument for the file-listing endpoint.

    Returns None for root, otherwise a path with leading slash and no trailing slash.
    """
    if folder is None or (isinstance(folder, str) and not folder.strip()):
        return None
    path = folder.strip().rstrip('/')
    return path if path.startswith('/') else f'/{path}'


def validate_path_segment(segment, field_name='path'):
    """Validate a single path segment (no slashes).

    Returns (True, None) on success or (False, error_response) on failure.
    """
    if not segment or not segment.strip():
        return False, response(400, {'error': f'{field_name} segment cannot be empty'})
    s = segment.strip()
    if len(s) > MAX_SEGMENT_LENGTH:
        return False, response(400, {'error': f'{field_name} segment too long (max {MAX_SEGMENT_LENGTH})'})
    if '\x00' in s:
        return False, response(400, {'error': f'{field_name} contains invalid characters'})
    return True, None


def validate_path(path, allow_root=True):
    """Validate a full path.

    Returns (normalized_path, None) on success or (None, error_response) on failure.
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

    normalized = normalize_path(path)
    if len(normalized) > MAX_PATH_LENGTH:
        return None, response(400, {'error': f'path too long (max {MAX_PATH_LENGTH})'})

    parts = [p for p in normalized.split('/') if p]
    if len(parts) > MAX_DEPTH:
        return None, response(400, {'error': f'path too deep (max {MAX_DEPTH} levels)'})

    for part in parts:
        ok, err = validate_path_segment(part, 'path')
        if not ok:
            return None, err

    return normalized, None
