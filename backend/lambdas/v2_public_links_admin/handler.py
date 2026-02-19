import hashlib
import secrets
import time
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from common import SHARE_EXPIRY_DAYS, extract_user, parse_json_body, response, table, utc_now_iso
from db import get_file_by_id, get_public_link_by_token
from idempotency import run_idempotent
from keys import file_entity_pk, file_sk, public_link_sk, public_token_gsi_pk, public_token_gsi_sk, user_pk
from logging_utils import correlation_id_from_event, log
from pagination import decode_cursor, encode_cursor, normalize_limit

_PBKDF2_ITERATIONS = 260_000


def _hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def _expiry(expiry_days):
    try:
        days = int(expiry_days)
    except (TypeError, ValueError):
        return None, None, response(400, {'error': 'expiryDays must be an integer'})
    if days < 1 or days > 365:
        return None, None, response(400, {'error': 'expiryDays must be between 1 and 365'})

    ttl = int(time.time()) + (days * 86400)
    expires_at = datetime.fromtimestamp(ttl, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
    return ttl, expires_at, None


def _require_owner_file(user_id, file_id):
    file_item = get_file_by_id(file_id)
    if not file_item:
        return None, response(404, {'error': 'File not found'})
    if file_item.get('ownerId') != user_id:
        return None, response(403, {'error': 'Access denied'})
    return file_item, None


def _adjust_public_link_count(owner_id, file_id, delta):
    table.update_item(
        Key={'pk': user_pk(owner_id), 'sk': file_sk(file_id)},
        UpdateExpression='SET #pl = if_not_exists(#pl, :zero) + :delta, #ua = :ua',
        ExpressionAttributeNames={'#pl': 'publicLinkCount', '#ua': 'updatedAt'},
        ExpressionAttributeValues={':zero': 0, ':delta': int(delta), ':ua': utc_now_iso()},
    )


def _create_link(event, user_id, user_email, file_id, corr_id):
    file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    body = parse_json_body(event)
    ttl, expires_at, expiry_err = _expiry(body.get('expiryDays', SHARE_EXPIRY_DAYS))
    if expiry_err:
        return expiry_err

    token = str(uuid.uuid4())
    now = utc_now_iso()
    item = {
        'pk': file_entity_pk(file_id),
        'sk': public_link_sk(token),
        'gsi4pk': public_token_gsi_pk(token),
        'gsi4sk': public_token_gsi_sk(file_id),
        'itemType': 'PUBLIC_LINK',
        'token': token,
        'fileId': file_id,
        'filename': file_item.get('filename'),
        's3Key': file_item.get('s3Key'),
        'contentType': file_item.get('contentType', 'application/octet-stream'),
        'size': int(file_item.get('size', 0)),
        'ownerId': user_id,
        'ownerEmail': user_email,
        'downloadCount': 0,
        'createdAt': now,
        'updatedAt': now,
        'expiresAt': expires_at,
        'ttl': ttl,
    }

    password = body.get('password')
    if password:
        pw_hash, pw_salt = _hash_password(str(password))
        item['passwordHash'] = pw_hash
        item['passwordSalt'] = pw_salt

    table.put_item(Item=item, ConditionExpression='attribute_not_exists(pk) AND attribute_not_exists(sk)')
    _adjust_public_link_count(user_id, file_id, 1)
    log('info', 'v2_public_link_created', correlation_id=corr_id, userId=user_id, fileId=file_id, token=token)

    return response(201, {
        'token': token,
        'fileId': file_id,
        'filename': file_item.get('filename'),
        'hasPassword': bool(password),
        'downloadCount': 0,
        'expiresAt': expires_at,
    })


def _list_links(event, user_id, file_id, corr_id):
    _file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    query_params = event.get('queryStringParameters') or {}
    limit = normalize_limit(query_params.get('limit'), default=50, max_value=200)
    cursor_raw = query_params.get('cursor')
    cursor = decode_cursor(cursor_raw) if cursor_raw else None
    if cursor_raw and not cursor:
        return response(400, {'error': 'Invalid cursor'})

    kwargs = {
        'KeyConditionExpression': Key('pk').eq(file_entity_pk(file_id)) & Key('sk').begins_with('PUBLIC_LINK#'),
        'Limit': limit,
    }
    if cursor:
        kwargs['ExclusiveStartKey'] = cursor

    now_epoch = int(time.time())
    result = table.query(**kwargs)

    items = []
    for item in result.get('Items', []):
        if item.get('itemType') != 'PUBLIC_LINK':
            continue
        ttl = item.get('ttl')
        if ttl is not None:
            try:
                if int(ttl) <= now_epoch:
                    continue
            except (TypeError, ValueError):
                continue
        items.append({
            'token': item.get('token'),
            'fileId': item.get('fileId'),
            'filename': item.get('filename'),
            'hasPassword': bool(item.get('passwordHash')),
            'downloadCount': int(item.get('downloadCount', 0)),
            'createdAt': item.get('createdAt'),
            'updatedAt': item.get('updatedAt'),
            'expiresAt': item.get('expiresAt'),
        })

    next_cursor = encode_cursor(result.get('LastEvaluatedKey'))
    log('info', 'v2_public_links_listed', correlation_id=corr_id, userId=user_id, fileId=file_id, count=len(items))
    return response(200, {'items': items, 'nextCursor': next_cursor})


def _patch_link(event, user_id, token, corr_id):
    existing = get_public_link_by_token(token)
    if not existing:
        return response(404, {'error': 'Public link not found'})
    if existing.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    body = parse_json_body(event)
    updated = dict(existing)

    changed = False
    if 'password' in body and body.get('password'):
        pw_hash, pw_salt = _hash_password(str(body.get('password')))
        updated['passwordHash'] = pw_hash
        updated['passwordSalt'] = pw_salt
        changed = True

    if body.get('removePassword'):
        updated.pop('passwordHash', None)
        updated.pop('passwordSalt', None)
        changed = True

    if 'expiryDays' in body:
        ttl, expires_at, expiry_err = _expiry(body.get('expiryDays'))
        if expiry_err:
            return expiry_err
        updated['ttl'] = ttl
        updated['expiresAt'] = expires_at
        changed = True

    if not changed:
        return response(400, {'error': 'Nothing to update'})

    updated['updatedAt'] = utc_now_iso()
    table.put_item(Item=updated)

    log('info', 'v2_public_link_patched', correlation_id=corr_id, userId=user_id, token=token)
    return response(200, {
        'token': token,
        'hasPassword': bool(updated.get('passwordHash')),
        'expiresAt': updated.get('expiresAt'),
    })


def _delete_link(_event, user_id, token, corr_id):
    existing = get_public_link_by_token(token)
    if not existing:
        return response(404, {'error': 'Public link not found'})
    if existing.get('ownerId') != user_id:
        return response(403, {'error': 'Access denied'})

    table.delete_item(Key={'pk': existing['pk'], 'sk': existing['sk']})
    file_id = existing.get('fileId')
    if file_id:
        _adjust_public_link_count(user_id, file_id, -1)
    log('info', 'v2_public_link_deleted', correlation_id=corr_id, userId=user_id, token=token)
    return response(200, {'message': 'Public link deleted', 'token': token})


def handler(event, context):
    corr_id = correlation_id_from_event(event)
    route_key = event.get('requestContext', {}).get('routeKey', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    path_params = event.get('pathParameters') or {}

    try:
        user_id, user_email = extract_user(event)
    except ValueError:
        return response(401, {'error': 'Unauthorized'})

    try:
        file_id = path_params.get('fileId')
        token = path_params.get('token')

        if route_key == 'POST /v2/files/{fileId}/public-links' or (method == 'POST' and file_id and 'public-links' in route_key):
            if not file_id:
                return response(400, {'error': 'fileId required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-public-links-create-{file_id}',
                lambda: _create_link(event, user_id, user_email, file_id, corr_id),
            )

        if route_key == 'GET /v2/files/{fileId}/public-links' or (method == 'GET' and file_id and 'public-links' in route_key):
            if not file_id:
                return response(400, {'error': 'fileId required'})
            return _list_links(event, user_id, file_id, corr_id)

        if route_key == 'PATCH /v2/public-links/{token}' or (method == 'PATCH' and token):
            if not token:
                return response(400, {'error': 'token required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-public-links-patch-{token}',
                lambda: _patch_link(event, user_id, token, corr_id),
            )

        if route_key == 'DELETE /v2/public-links/{token}' or (method == 'DELETE' and token):
            if not token:
                return response(400, {'error': 'token required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-public-links-delete-{token}',
                lambda: _delete_link(event, user_id, token, corr_id),
            )

        return response(404, {'error': 'Route not found'})
    except Exception as err:
        log('error', 'v2_public_links_admin_handler_failed', correlation_id=corr_id, error=str(err))
        return response(500, {'error': 'Internal server error'})
