"""
Shared DynamoDB helpers: key builders, file lookup, folder existence check.
"""
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from common import table, response


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------

def user_pk(user_id):
    return f'USER#{user_id}'


def shared_pk(user_id):
    return f'SHARED#{user_id}'


def file_sk(path, filename):
    return f'FILE#{path}/{filename}'


def folder_sk(path):
    return f'FOLDER#{path}'


def file_gsi(file_id):
    return f'FILE#{file_id}'


def folder_gsi(folder_id):
    return f'FOLDER#{folder_id}'


def file_sk_prefix(path):
    """Prefix for querying all files under a folder path."""
    return f'FILE#{path}/'


def folder_sk_prefix(path):
    """Prefix for querying all subfolders under a folder path."""
    return f'FOLDER#{path}/'


# ---------------------------------------------------------------------------
# File lookup by ID (via GSI1) with ownership check
# ---------------------------------------------------------------------------

def find_file_by_id(user_id, file_id, require_ownership=True):
    """Look up a file via GSI1 and optionally verify ownership.

    Returns (file_item, all_items, error_response).
    When *require_ownership* is True the caller must own the file; otherwise
    the file item is returned regardless of owner (useful for download which
    has its own share-access check).
    """
    if not file_id:
        return None, [], response(400, {'error': 'fileId required'})

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(file_gsi(file_id))
    )
    items = result.get('Items', [])
    file_item = next((i for i in items if i.get('itemType') == 'FILE'), None)

    if not file_item:
        return None, items, response(404, {'error': 'File not found'})

    if require_ownership and file_item.get('ownerId') != user_id:
        return None, items, response(403, {'error': 'Access denied'})

    return file_item, items, None


# ---------------------------------------------------------------------------
# Folder existence check
# ---------------------------------------------------------------------------

def get_folder_or_404(user_id, path):
    """Return the folder DynamoDB item or an HTTP-style error response.

    Returns (folder_item, None) on success or (None, error_response) on failure.
    """
    pk = user_pk(user_id)
    sk = folder_sk(path)
    try:
        result = table.get_item(Key={'pk': pk, 'sk': sk})
        item = result.get('Item')
    except ClientError as e:
        print(f'get_item folder failed: {e}')
        return None, response(500, {'error': 'Internal server error'})

    if not item or item.get('itemType') != 'FOLDER':
        return None, response(404, {'error': 'Folder not found', 'path': path})

    return item, None
