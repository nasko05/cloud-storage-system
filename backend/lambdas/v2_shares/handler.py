import time
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from common import SHARE_EXPIRY_DAYS, extract_user, parse_json_body, response, table, utc_now_iso
from db import get_file_by_id
from idempotency import run_idempotent
from keys import (
    file_entity_pk,
    inbound_principal_gsi_pk,
    inbound_principal_gsi_sk,
    share_sk,
)
from logging_utils import correlation_id_from_event, log
from pagination import decode_cursor, encode_cursor, normalize_limit
from permissions import validate_share_permission
from principal import parse_principal_path


def _expiry_from_body(body):
    raw_days = body.get('expiryDays', SHARE_EXPIRY_DAYS)
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        return None, None, response(400, {'error': 'expiryDays must be an integer'})
    if days < 1 or days > 365:
        return None, None, response(400, {'error': 'expiryDays must be between 1 and 365'})

    ttl = int(time.time()) + (days * 86400)
    expires_at = datetime.fromtimestamp(ttl, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
    return ttl, expires_at, None


def _is_active_share(item, now_epoch):
    ttl = item.get('ttl')
    if ttl is None:
        return True
    try:
        return int(ttl) > now_epoch
    except (TypeError, ValueError):
        return False


def _require_owner_file(user_id, file_id):
    file_item = get_file_by_id(file_id)
    if not file_item:
        return None, response(404, {'error': 'File not found'})
    if file_item.get('ownerId') != user_id:
        return None, response(403, {'error': 'Access denied'})
    return file_item, None


def _list_inbound_shares(event, user_id, user_email, corr_id):
    now_epoch = int(time.time())
    query_params = event.get('queryStringParameters') or {}
    limit = normalize_limit(query_params.get('limit'), default=50, max_value=200)

    cursor_raw = query_params.get('cursor')
    cursor = decode_cursor(cursor_raw) if cursor_raw else None
    if cursor_raw and not isinstance(cursor, dict):
        return response(400, {'error': 'Invalid cursor'})

    candidates = [('user_sub', user_id)]
    if user_email and user_email != user_id:
        candidates.append(('email', user_email))

    segment = 0
    last_evaluated = None
    if cursor:
        try:
            segment = int(cursor.get('segment', 0))
        except (TypeError, ValueError):
            return response(400, {'error': 'Invalid cursor'})
        lek = cursor.get('lek')
        if lek is not None and not isinstance(lek, dict):
            return response(400, {'error': 'Invalid cursor'})
        last_evaluated = lek

    if segment < 0 or segment >= len(candidates):
        return response(400, {'error': 'Invalid cursor'})

    seen = set()
    items = []
    next_cursor = None

    for idx in range(segment, len(candidates)):
        principal_type, principal_value = candidates[idx]
        lek = last_evaluated if idx == segment else None

        while len(items) < limit:
            remaining = limit - len(items)
            kwargs = {
                'IndexName': 'GSI3',
                'KeyConditionExpression': Key('gsi3pk').eq(inbound_principal_gsi_pk(principal_type, principal_value)) & Key('gsi3sk').begins_with('FILE#'),
                'Limit': remaining,
            }
            if lek:
                kwargs['ExclusiveStartKey'] = lek

            page = table.query(**kwargs)
            for item in page.get('Items', []):
                if item.get('itemType') != 'SHARE':
                    continue
                if not _is_active_share(item, now_epoch):
                    continue

                dedupe_key = (item.get('fileId'), item.get('principalType'), item.get('principalValue'))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                items.append({
                    'fileId': item.get('fileId'),
                    'filename': item.get('filename'),
                    'ownerId': item.get('ownerId'),
                    'ownerEmail': item.get('ownerEmail', item.get('sharedByEmail')),
                    'permission': item.get('permission', 'read'),
                    'principalType': item.get('principalType'),
                    'principalValue': item.get('principalValue'),
                    'sharedAt': item.get('sharedAt'),
                    'expiresAt': item.get('expiresAt'),
                })

            lek = page.get('LastEvaluatedKey')
            if len(items) >= limit:
                if lek:
                    next_cursor = encode_cursor({'segment': idx, 'lek': lek})
                elif idx + 1 < len(candidates):
                    next_cursor = encode_cursor({'segment': idx + 1, 'lek': None})
                break

            if not lek:
                break

        if len(items) >= limit:
            break

    log('info', 'v2_shares_inbound_listed', correlation_id=corr_id, userId=user_id, count=len(items))
    return response(200, {'items': items, 'nextCursor': next_cursor})


def _list_file_shares(event, user_id, file_id, corr_id):
    _file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    now_epoch = int(time.time())
    query_params = event.get('queryStringParameters') or {}
    limit = normalize_limit(query_params.get('limit'), default=50, max_value=200)

    cursor_raw = query_params.get('cursor')
    cursor = decode_cursor(cursor_raw) if cursor_raw else None
    if cursor_raw and not cursor:
        return response(400, {'error': 'Invalid cursor'})

    kwargs = {
        'KeyConditionExpression': Key('pk').eq(file_entity_pk(file_id)) & Key('sk').begins_with('SHARE#'),
        'Limit': limit,
    }
    if cursor:
        kwargs['ExclusiveStartKey'] = cursor

    result = table.query(**kwargs)

    items = []
    for item in result.get('Items', []):
        if item.get('itemType') != 'SHARE':
            continue
        if not _is_active_share(item, now_epoch):
            continue
        items.append({
            'principalType': item.get('principalType'),
            'principalValue': item.get('principalValue'),
            'permission': item.get('permission', 'read'),
            'sharedAt': item.get('sharedAt'),
            'expiresAt': item.get('expiresAt'),
        })

    next_cursor = encode_cursor(result.get('LastEvaluatedKey'))
    log('info', 'v2_file_shares_listed', correlation_id=corr_id, userId=user_id, fileId=file_id, count=len(items))
    return response(200, {'items': items, 'nextCursor': next_cursor})


def _put_share(event, user_id, user_email, file_id, principal, corr_id):
    principal_type, principal_value = parse_principal_path(principal)
    if not principal_type:
        return response(400, {'error': 'Invalid principal format'})

    body = parse_json_body(event)
    permission = body.get('permission', 'read')
    if not validate_share_permission(permission):
        return response(400, {'error': 'permission must be read, download, or edit'})

    file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    ttl, expires_at, expiry_err = _expiry_from_body(body)
    if expiry_err:
        return expiry_err

    now = utc_now_iso()
    pk = file_entity_pk(file_id)
    sk = share_sk(principal_type, principal_value)

    existing = table.get_item(Key={'pk': pk, 'sk': sk}).get('Item')
    created_at = (existing or {}).get('sharedAt', now)

    item = {
        'pk': pk,
        'sk': sk,
        'gsi3pk': inbound_principal_gsi_pk(principal_type, principal_value),
        'gsi3sk': inbound_principal_gsi_sk(file_id),
        'itemType': 'SHARE',
        'fileId': file_id,
        'filename': file_item.get('filename'),
        's3Key': file_item.get('s3Key'),
        'contentType': file_item.get('contentType', 'application/octet-stream'),
        'size': int(file_item.get('size', 0)),
        'ownerId': file_item.get('ownerId'),
        'ownerEmail': file_item.get('ownerEmail', user_email),
        'principalType': principal_type,
        'principalValue': principal_value,
        'permission': permission,
        'sharedBy': user_id,
        'sharedByEmail': user_email,
        'sharedAt': created_at,
        'updatedAt': now,
        'expiresAt': expires_at,
        'ttl': ttl,
    }
    table.put_item(Item=item)

    log('info', 'v2_share_upserted', correlation_id=corr_id, userId=user_id, fileId=file_id, principal=principal)
    return response(200, {
        'fileId': file_id,
        'principalType': principal_type,
        'principalValue': principal_value,
        'permission': permission,
        'expiresAt': expires_at,
    })


def _patch_share(event, user_id, file_id, principal, corr_id):
    principal_type, principal_value = parse_principal_path(principal)
    if not principal_type:
        return response(400, {'error': 'Invalid principal format'})

    _file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    pk = file_entity_pk(file_id)
    sk = share_sk(principal_type, principal_value)
    existing = table.get_item(Key={'pk': pk, 'sk': sk}).get('Item')
    if not existing or existing.get('itemType') != 'SHARE':
        return response(404, {'error': 'Share not found'})

    body = parse_json_body(event)
    update_parts = ['#ua = :ua']
    names = {'#ua': 'updatedAt'}
    values = {':ua': utc_now_iso()}

    if 'permission' in body:
        permission = body.get('permission')
        if not validate_share_permission(permission):
            return response(400, {'error': 'permission must be read, download, or edit'})
        update_parts.append('#perm = :perm')
        names['#perm'] = 'permission'
        values[':perm'] = permission

    if 'expiryDays' in body:
        ttl, expires_at, expiry_err = _expiry_from_body(body)
        if expiry_err:
            return expiry_err
        update_parts.append('#ttl = :ttl')
        update_parts.append('#ea = :ea')
        names['#ttl'] = 'ttl'
        names['#ea'] = 'expiresAt'
        values[':ttl'] = ttl
        values[':ea'] = expires_at

    if len(update_parts) == 1:
        return response(400, {'error': 'Nothing to update'})

    table.update_item(
        Key={'pk': pk, 'sk': sk},
        UpdateExpression='SET ' + ', '.join(update_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )

    updated = table.get_item(Key={'pk': pk, 'sk': sk}).get('Item') or {}
    log('info', 'v2_share_patched', correlation_id=corr_id, userId=user_id, fileId=file_id, principal=principal)
    return response(200, {
        'fileId': file_id,
        'principalType': principal_type,
        'principalValue': principal_value,
        'permission': updated.get('permission', existing.get('permission')),
        'expiresAt': updated.get('expiresAt', existing.get('expiresAt')),
    })


def _delete_share(_event, user_id, file_id, principal, corr_id):
    principal_type, principal_value = parse_principal_path(principal)
    if not principal_type:
        return response(400, {'error': 'Invalid principal format'})

    _file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    pk = file_entity_pk(file_id)
    sk = share_sk(principal_type, principal_value)
    existing = table.get_item(Key={'pk': pk, 'sk': sk}).get('Item')
    if not existing or existing.get('itemType') != 'SHARE':
        return response(404, {'error': 'Share not found'})

    table.delete_item(Key={'pk': pk, 'sk': sk})
    log('info', 'v2_share_deleted', correlation_id=corr_id, userId=user_id, fileId=file_id, principal=principal)
    return response(200, {
        'message': 'Share revoked',
        'fileId': file_id,
        'principalType': principal_type,
        'principalValue': principal_value,
    })


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
        principal = path_params.get('principal')

        if route_key == 'GET /v2/shares/inbound':
            return _list_inbound_shares(event, user_id, user_email, corr_id)

        if route_key == 'GET /v2/files/{fileId}/shares' or (method == 'GET' and file_id and principal is None):
            if not file_id:
                return response(400, {'error': 'fileId required'})
            return _list_file_shares(event, user_id, file_id, corr_id)

        if route_key == 'PUT /v2/files/{fileId}/shares/{principal}' or (method == 'PUT' and file_id and principal):
            if not file_id or not principal:
                return response(400, {'error': 'fileId and principal required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-shares-put-{file_id}-{principal}',
                lambda: _put_share(event, user_id, user_email, file_id, principal, corr_id),
            )

        if route_key == 'PATCH /v2/files/{fileId}/shares/{principal}' or (method == 'PATCH' and file_id and principal):
            if not file_id or not principal:
                return response(400, {'error': 'fileId and principal required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-shares-patch-{file_id}-{principal}',
                lambda: _patch_share(event, user_id, file_id, principal, corr_id),
            )

        if route_key == 'DELETE /v2/files/{fileId}/shares/{principal}' or (method == 'DELETE' and file_id and principal):
            if not file_id or not principal:
                return response(400, {'error': 'fileId and principal required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-shares-delete-{file_id}-{principal}',
                lambda: _delete_share(event, user_id, file_id, principal, corr_id),
            )

        return response(404, {'error': 'Route not found'})
    except Exception as err:
        log('error', 'v2_shares_handler_failed', correlation_id=corr_id, error=str(err))
        return response(500, {'error': 'Internal server error'})
