import hashlib
import secrets
import time

from common import BUCKET, EXPIRY, parse_json_body, response, s3, table, utc_now_iso
from db import get_public_link_by_token
from logging_utils import correlation_id_from_event, log

_PBKDF2_ITERATIONS = 260_000


def _verify_password(password, stored_hash, stored_salt):
    salt = bytes.fromhex(stored_salt)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
    return secrets.compare_digest(digest.hex(), stored_hash)


def _active_link(item):
    ttl = item.get('ttl')
    if ttl is None:
        return True
    try:
        return int(ttl) > int(time.time())
    except (TypeError, ValueError):
        return False


def _link_or_error(token):
    if not token:
        return None, response(400, {'error': 'token required'})

    item = get_public_link_by_token(token)
    if not item:
        return None, response(404, {'error': 'Public link not found'})
    if not _active_link(item):
        return None, response(410, {'error': 'Link has expired'})
    return item, None


def _metadata(token, corr_id):
    item, err = _link_or_error(token)
    if err:
        return err

    return response(200, {
        'token': token,
        'fileId': item.get('fileId'),
        'filename': item.get('filename'),
        'size': int(item.get('size', 0)),
        'contentType': item.get('contentType', 'application/octet-stream'),
        'hasPassword': bool(item.get('passwordHash')),
        'downloadCount': int(item.get('downloadCount', 0)),
        'expiresAt': item.get('expiresAt'),
    })


def _download(event, token, corr_id):
    item, err = _link_or_error(token)
    if err:
        return err

    if item.get('passwordHash'):
        body = parse_json_body(event)
        password = str(body.get('password') or '')
        if not password:
            return response(403, {'error': 'Password required'})
        if not _verify_password(password, item.get('passwordHash', ''), item.get('passwordSalt', '')):
            return response(403, {'error': 'Incorrect password'})

    if item.get('status') and item.get('status') != 'ready':
        return response(409, {'error': 'File is not ready for download', 'status': item.get('status')})

    try:
        s3.head_object(Bucket=BUCKET, Key=item['s3Key'])
    except s3.exceptions.ClientError as error:
        code = error.response.get('Error', {}).get('Code')
        if code in ('404', 'NoSuchKey', 'NotFound'):
            return response(404, {'error': 'File not found in storage'})
        raise

    table.update_item(
        Key={'pk': item['pk'], 'sk': item['sk']},
        UpdateExpression='SET #dc = if_not_exists(#dc, :zero) + :one, #ua = :ua',
        ExpressionAttributeNames={'#dc': 'downloadCount', '#ua': 'updatedAt'},
        ExpressionAttributeValues={':zero': 0, ':one': 1, ':ua': utc_now_iso()},
    )

    download_url = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': BUCKET,
            'Key': item['s3Key'],
            'ResponseContentDisposition': f'attachment; filename="{item["filename"]}"',
        },
        ExpiresIn=EXPIRY,
    )

    log('info', 'v2_public_download_issued', correlation_id=corr_id, token=token, fileId=item.get('fileId'))
    return response(200, {
        'downloadUrl': download_url,
        'token': token,
        'fileId': item.get('fileId'),
        'filename': item.get('filename'),
        'contentType': item.get('contentType', 'application/octet-stream'),
        'size': int(item.get('size', 0)),
        'expiresIn': EXPIRY,
    })


def handler(event, context):
    corr_id = correlation_id_from_event(event)
    route_key = event.get('requestContext', {}).get('routeKey', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    path_params = event.get('pathParameters') or {}

    try:
        token = path_params.get('token')

        if route_key == 'GET /v2/public-links/{token}' or (method == 'GET' and token):
            return _metadata(token, corr_id)

        if route_key == 'POST /v2/public-links/{token}/download' or (method == 'POST' and token):
            return _download(event, token, corr_id)

        return response(404, {'error': 'Route not found'})
    except Exception as err:
        log('error', 'v2_public_download_handler_failed', correlation_id=corr_id, error=str(err))
        return response(500, {'error': 'Internal server error'})
