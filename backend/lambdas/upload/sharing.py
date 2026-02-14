import json
import time
from datetime import datetime
from boto3.dynamodb.conditions import Key
from common import table, SHARE_EXPIRY_DAYS, response, utc_now_iso
from db_helpers import file_gsi


def list_shared_with_me(user_id):
    result = table.query(
        KeyConditionExpression=Key('pk').eq(f'SHARED#{user_id}') & Key('sk').begins_with('FILE#')
    )
    files = [
        {
            'fileId': item['fileId'],
            'sharedBy': item['sharedBy'],
            'sharedByEmail': item['sharedByEmail'],
            'filename': item['filename'],
            'permission': item['permission'],
            'expiresAt': item['expiresAt']
        }
        for item in result.get('Items', [])
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

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(file_gsi(file_id)) & Key('gsi1sk').eq(file_gsi(file_id))
    )
    items = result.get('Items', [])
    if not items or items[0].get('ownerId') != user_id:
        return response(403, {'error': 'Access denied - not owner'})

    file = items[0]
    target_user_id = share_with_user_id or share_with_email
    ttl = int(time.time()) + (expiry_days * 24 * 60 * 60)
    now = utc_now_iso()

    share_item = {
        'pk': f'SHARED#{target_user_id}',
        'sk': f'FILE#{file_id}',
        'gsi1pk': file_gsi(file_id),
        'gsi1sk': f'SHARED#{target_user_id}',
        'fileId': file_id,
        'filename': file['filename'],
        's3Key': file['s3Key'],
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

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(file_gsi(file_id)) & Key('gsi1sk').eq(file_gsi(file_id))
    )
    items = result.get('Items', [])
    if not items or items[0].get('ownerId') != user_id:
        return response(403, {'error': 'Access denied - not owner'})

    table.delete_item(Key={'pk': f'SHARED#{revoke_user_id}', 'sk': f'FILE#{file_id}'})
    return response(200, {'message': 'Share revoked', 'fileId': file_id, 'revokedUser': revoke_user_id})
