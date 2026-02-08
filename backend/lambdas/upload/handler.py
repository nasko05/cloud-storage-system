import json
from common import response
from files import list_files, upload_file, delete_file
from folders import create_folder
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
    'shared-with-me': lambda ctx: list_shared_with_me(ctx['user_id']),
    'share': lambda ctx: share_file(ctx['user_id'], ctx['user_email'], ctx['body']),
    'unshare': lambda ctx: unshare_file(ctx['user_id'], ctx['body']),
}


def handler(event, context):
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
        user_id = claims.get('sub')
        
        if not user_id:
            return response(401, {'error': 'Unauthorized'})

        body = json.loads(event.get('body') or '{}')
        ctx = {
            'user_id': user_id,
            'user_email': claims.get('email', user_id),
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
