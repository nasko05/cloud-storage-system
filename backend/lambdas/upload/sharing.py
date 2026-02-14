import json
import os
import time
from datetime import datetime
import boto3
from boto3.dynamodb.conditions import Key
from common import table, SHARE_EXPIRY_DAYS, response, utc_now_iso
from db_helpers import file_gsi, shared_pk, find_file_by_id

_cognito = boto3.client('cognito-idp')
_USER_POOL_ID = os.environ.get('USER_POOL_ID', '')


def _resolve_email(user_sub):
    """Look up a Cognito user's email by their sub (UUID). Returns the email or the sub on failure."""
    if not _USER_POOL_ID or not user_sub:
        return user_sub
    try:
        resp = _cognito.admin_get_user(UserPoolId=_USER_POOL_ID, Username=user_sub)
        for attr in resp.get('UserAttributes', []):
            if attr['Name'] == 'email':
                return attr['Value']
    except Exception:
        pass
    return user_sub


def list_shared_with_me(user_id, user_email=None):
    # Query by Cognito sub (user_id)
    result = table.query(
        KeyConditionExpression=Key('pk').eq(shared_pk(user_id)) & Key('sk').begins_with('FILE#')
    )
    items = result.get('Items', [])

    # Also query by email if it differs from user_id (shares may be keyed by email)
    if user_email and user_email != user_id:
        email_result = table.query(
            KeyConditionExpression=Key('pk').eq(shared_pk(user_email)) & Key('sk').begins_with('FILE#')
        )
        seen = {item['sk'] for item in items}
        for item in email_result.get('Items', []):
            if item['sk'] not in seen:
                items.append(item)

    # Resolve sharedBy UUIDs to emails via Cognito (batch-deduplicated)
    subs = {item['sharedBy'] for item in items}
    resolved = {}
    for sub in subs:
        resolved[sub] = _resolve_email(sub)

    files = [
        {
            'fileId': item['fileId'],
            'sharedBy': item['sharedBy'],
            'sharedByEmail': resolved.get(item['sharedBy'], item['sharedByEmail']),
            'filename': item['filename'],
            'permission': item['permission'],
            'expiresAt': item['expiresAt']
        }
        for item in items
    ]
    return response(200, {'files': files})


def share_file(user_id, user_email, body):
    file_id = body.get('fileId')
    share_with_user_id = body.get('shareWithUserId')
    share_with_email = body.get('shareWithEmail')
    expiry_days = body.get('expiryDays', SHARE_EXPIRY_DAYS)
    permission = body.get('permission', 'read')

    if not file_id or (not share_with_user_id and not share_with_email):
        return response(400, {'error': 'fileId and shareWithUserId or shareWithEmail required'})

    file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return response(403, {'error': 'Access denied - not owner'})

    target_user_id = share_with_user_id or share_with_email
    ttl = int(time.time()) + (expiry_days * 24 * 60 * 60)
    now = utc_now_iso()

    share_item = {
        'pk': shared_pk(target_user_id),
        'sk': f'FILE#{file_id}',
        'gsi1pk': file_gsi(file_id),
        'gsi1sk': shared_pk(target_user_id),
        'fileId': file_id,
        'filename': file_item['filename'],
        's3Key': file_item['s3Key'],
        'sharedBy': user_id,
        'sharedByEmail': user_email,
        'sharedWith': target_user_id,
        'permission': permission,
        'sharedAt': now,
        'expiresAt': datetime.utcfromtimestamp(ttl).isoformat() + 'Z',
        'ttl': ttl,
        'itemType': 'SHARE'
    }
    table.put_item(Item=share_item)
    print(json.dumps({'action': 'share', 'userId': user_id, 'fileId': file_id, 'sharedWith': target_user_id}))
    
    return response(200, {
        'message': 'Shared successfully',
        'fileId': file_id,
        'sharedWith': target_user_id,
        'expiresAt': share_item['expiresAt']
    })


def unshare_file(user_id, body):
    file_id = body.get('fileId')
    revoke_user_id = body.get('revokeUserId')
    if not file_id or not revoke_user_id:
        return response(400, {'error': 'fileId and revokeUserId required'})

    _file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return response(403, {'error': 'Access denied - not owner'})

    table.delete_item(Key={'pk': shared_pk(revoke_user_id), 'sk': f'FILE#{file_id}'})
    return response(200, {'message': 'Share revoked', 'fileId': file_id, 'revokedUser': revoke_user_id})


def list_file_shares(user_id, body):
    """List all active shares for a file owned by the caller."""
    file_id = body.get('fileId')
    if not file_id:
        return response(400, {'error': 'fileId required'})

    _file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return response(403, {'error': 'Access denied - not owner'})

    # Query GSI1 to find all share records for this file
    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(file_gsi(file_id)) & Key('gsi1sk').begins_with('SHARED#')
    )
    items = [i for i in result.get('Items', []) if i.get('itemType') == 'SHARE']

    now = int(time.time())
    shares = []
    for item in items:
        # Skip expired shares
        ttl = item.get('ttl')
        if ttl and int(ttl) <= now:
            continue
        shares.append({
            'sharedWith': item.get('sharedWith', ''),
            'permission': item.get('permission', 'read'),
            'sharedAt': item.get('sharedAt', ''),
            'expiresAt': item.get('expiresAt', ''),
        })

    return response(200, {'shares': shares})


def update_share_permission(user_id, body):
    """Update the permission level of an existing share."""
    file_id = body.get('fileId')
    target_user_id = body.get('targetUserId')
    permission = body.get('permission')

    if not file_id or not target_user_id or not permission:
        return response(400, {'error': 'fileId, targetUserId, and permission required'})

    if permission not in ('read', 'download', 'edit'):
        return response(400, {'error': 'permission must be read, download, or edit'})

    _file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return response(403, {'error': 'Access denied - not owner'})

    # Verify the share record exists
    share_key = {'pk': shared_pk(target_user_id), 'sk': f'FILE#{file_id}'}
    existing = table.get_item(Key=share_key).get('Item')
    if not existing:
        return response(404, {'error': 'Share not found'})

    table.update_item(
        Key=share_key,
        UpdateExpression='SET #perm = :p',
        ExpressionAttributeNames={'#perm': 'permission'},
        ExpressionAttributeValues={':p': permission}
    )

    return response(200, {
        'message': 'Permission updated',
        'fileId': file_id,
        'targetUserId': target_user_id,
        'permission': permission
    })
