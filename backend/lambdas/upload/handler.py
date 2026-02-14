import json
from common import response, extract_user
from files import list_files, upload_file, delete_file, move_file, rename_file
from folders import create_folder, delete_folder, move_folder, rename_folder
from sharing import list_shared_with_me, share_file, unshare_file

# Action handlers registry
ACTIONS = {
    'list': lambda ctx: list_files(ctx['user_id'], ctx['body'].get('folder')),
    'delete': lambda ctx: delete_file(ctx['user_id'], ctx['body'].get('fileId')),
    'create-folder': lambda ctx: create_folder(
        ctx['user_id'],
        ctx['body'].get('folderName'),
        ctx['body'].get('path')
    ),
    'delete-folder': lambda ctx: delete_folder(ctx['user_id'], ctx['body'].get('path')),
    'move-file': lambda ctx: move_file(
        ctx['user_id'],
        ctx['body'].get('fileId'),
        ctx['body'].get('destinationPath')
    ),
    'rename-file': lambda ctx: rename_file(
        ctx['user_id'],
        ctx['body'].get('fileId'),
        ctx['body'].get('newName')
    ),
    'move-folder': lambda ctx: move_folder(
        ctx['user_id'],
        ctx['body'].get('folderPath'),
        ctx['body'].get('destinationPath')
    ),
    'rename-folder': lambda ctx: rename_folder(
        ctx['user_id'],
        ctx['body'].get('folderPath'),
        ctx['body'].get('newName')
    ),
    'shared-with-me': lambda ctx: list_shared_with_me(ctx['user_id']),
    'share': lambda ctx: share_file(ctx['user_id'], ctx['user_email'], ctx['body']),
    'unshare': lambda ctx: unshare_file(ctx['user_id'], ctx['body']),
}


def handler(event, context):
    try:
        user_id, user_email = extract_user(event)
    except ValueError:
        return response(401, {'error': 'Unauthorized'})

    try:
        body = json.loads(event.get('body') or '{}')
        ctx = {
            'user_id': user_id,
            'user_email': user_email,
            'body': body
        }
        
        action = body.get('action')
        handler_fn = ACTIONS.get(action)
        
        if handler_fn:
            return handler_fn(ctx)
        return upload_file(ctx['user_id'], ctx['user_email'], body)

    except Exception as e:
        print(f'Error: {e}')
        return response(500, {'error': 'Internal server error'})
