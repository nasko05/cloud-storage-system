"""
Public link CRUD operations (authenticated – called from the upload handler).

Public links allow unauthenticated users to download a file via a unique token.
Optional features: password protection, download-count tracking, TTL expiry.
"""

import hashlib
import json
import os
import secrets
import time
import uuid
from datetime import datetime

from boto3.dynamodb.conditions import Key
from common import table, SHARE_EXPIRY_DAYS, response, utc_now_iso
from db_helpers import file_gsi, find_file_by_id, public_link_pk

# ---------------------------------------------------------------------------
# Password helpers (stdlib only – no external deps)
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 260_000  # OWASP recommendation for SHA-256


def _hash_password(password):
    """Return (hex_hash, hex_salt) for *password* using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, _PBKDF2_ITERATIONS)
    return dk.hex(), salt.hex()


def _verify_password(password, stored_hash, stored_salt):
    """Return True if *password* matches the stored hash+salt."""
    salt = bytes.fromhex(stored_salt)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, _PBKDF2_ITERATIONS)
    return secrets.compare_digest(dk.hex(), stored_hash)


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def create_public_link(user_id, user_email, body):
    """Create a new public link for a file owned by the caller."""
    file_id = body.get('fileId')
    password = body.get('password')  # optional
    expiry_days = body.get('expiryDays', SHARE_EXPIRY_DAYS)

    if not file_id:
        return response(400, {'error': 'fileId required'})

    file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return err

    token = str(uuid.uuid4())
    ttl = int(time.time()) + (int(expiry_days) * 86_400)
    now = utc_now_iso()

    item = {
        'pk': public_link_pk(token),
        'sk': 'META',
        'gsi1pk': file_gsi(file_id),
        'gsi1sk': public_link_pk(token),
        'token': token,
        'fileId': file_id,
        'filename': file_item['filename'],
        's3Key': file_item['s3Key'],
        'contentType': file_item.get('contentType', 'application/octet-stream'),
        'size': file_item.get('size', 0),
        'ownerId': user_id,
        'ownerEmail': user_email,
        'downloadCount': 0,
        'createdAt': now,
        'expiresAt': datetime.utcfromtimestamp(ttl).isoformat() + 'Z',
        'ttl': ttl,
        'itemType': 'PUBLIC_LINK',
    }

    if password:
        pw_hash, pw_salt = _hash_password(password)
        item['passwordHash'] = pw_hash
        item['passwordSalt'] = pw_salt

    table.put_item(Item=item)

    print(json.dumps({
        'action': 'create-public-link',
        'userId': user_id,
        'fileId': file_id,
        'token': token,
    }))

    return response(200, {
        'message': 'Public link created',
        'token': token,
        'fileId': file_id,
        'filename': file_item['filename'],
        'hasPassword': bool(password),
        'downloadCount': 0,
        'createdAt': now,
        'expiresAt': item['expiresAt'],
    })


def list_public_links(user_id, body):
    """List all active public links for a file owned by the caller."""
    file_id = body.get('fileId')
    if not file_id:
        return response(400, {'error': 'fileId required'})

    _file_item, _items, err = find_file_by_id(user_id, file_id)
    if err:
        return err

    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=(
            Key('gsi1pk').eq(file_gsi(file_id))
            & Key('gsi1sk').begins_with('PUBLIC_LINK#')
        ),
    )
    items = [i for i in result.get('Items', []) if i.get('itemType') == 'PUBLIC_LINK']

    now = int(time.time())
    links = []
    for item in items:
        ttl = item.get('ttl')
        if ttl and int(ttl) <= now:
            continue
        links.append({
            'token': item['token'],
            'fileId': item['fileId'],
            'filename': item['filename'],
            'hasPassword': bool(item.get('passwordHash')),
            'downloadCount': int(item.get('downloadCount', 0)),
            'createdAt': item.get('createdAt', ''),
            'expiresAt': item.get('expiresAt', ''),
        })

    return response(200, {'links': links})


def delete_public_link(user_id, body):
    """Delete a public link. Only the file owner may do this."""
    token = body.get('token')
    if not token:
        return response(400, {'error': 'token required'})

    key = {'pk': public_link_pk(token), 'sk': 'META'}
    existing = table.get_item(Key=key).get('Item')

    if not existing or existing.get('itemType') != 'PUBLIC_LINK':
        return response(404, {'error': 'Public link not found'})

    if existing.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    table.delete_item(Key=key)

    print(json.dumps({
        'action': 'delete-public-link',
        'userId': user_id,
        'token': token,
    }))

    return response(200, {'message': 'Public link deleted', 'token': token})


def update_public_link(user_id, body):
    """Update password and/or expiry of an existing public link."""
    token = body.get('token')
    if not token:
        return response(400, {'error': 'token required'})

    key = {'pk': public_link_pk(token), 'sk': 'META'}
    existing = table.get_item(Key=key).get('Item')

    if not existing or existing.get('itemType') != 'PUBLIC_LINK':
        return response(404, {'error': 'Public link not found'})

    if existing.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    update_parts = []
    attr_values = {}
    attr_names = {}

    # --- password update ---
    new_password = body.get('password')          # set / change password
    remove_password = body.get('removePassword')  # explicitly remove password

    if new_password:
        pw_hash, pw_salt = _hash_password(new_password)
        update_parts.append('passwordHash = :ph')
        update_parts.append('passwordSalt = :ps')
        attr_values[':ph'] = pw_hash
        attr_values[':ps'] = pw_salt
    elif remove_password:
        update_parts.append('passwordHash = :ph')
        update_parts.append('passwordSalt = :ps')
        attr_values[':ph'] = None
        attr_values[':ps'] = None

    # --- expiry update ---
    expiry_days = body.get('expiryDays')
    if expiry_days is not None:
        new_ttl = int(time.time()) + (int(expiry_days) * 86_400)
        new_expires = datetime.utcfromtimestamp(new_ttl).isoformat() + 'Z'
        update_parts.append('expiresAt = :ea')
        update_parts.append('#t = :ttl')
        attr_values[':ea'] = new_expires
        attr_values[':ttl'] = new_ttl
        attr_names['#t'] = 'ttl'

    if not update_parts:
        return response(400, {'error': 'Nothing to update'})

    update_expr = 'SET ' + ', '.join(update_parts)
    kwargs = {
        'Key': key,
        'UpdateExpression': update_expr,
        'ExpressionAttributeValues': attr_values,
    }
    if attr_names:
        kwargs['ExpressionAttributeNames'] = attr_names

    table.update_item(**kwargs)

    return response(200, {'message': 'Public link updated', 'token': token})
