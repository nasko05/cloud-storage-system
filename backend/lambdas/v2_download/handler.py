import time

from common import BUCKET, EXPIRY, extract_user, response, s3, table, utc_now_iso
from db import get_file_by_id
from keys import file_entity_pk, share_sk
from logging_utils import correlation_id_from_event, log
from permissions import can_download


def _active_share(item):
    if not item:
        return False
    ttl = item.get('ttl')
    if ttl is None:
        return True
    try:
        return int(ttl) > int(time.time())
    except (TypeError, ValueError):
        return False


def _find_share(file_id, user_id, user_email):
    candidates = [('user_sub', user_id)]
    if user_email and user_email != user_id:
        candidates.append(('email', user_email))

    for principal_type, principal_value in candidates:
        result = table.get_item(
            Key={
                'pk': file_entity_pk(file_id),
                'sk': share_sk(principal_type, principal_value),
            }
        )
        item = result.get('Item')
        if item and _active_share(item):
            return item
    return None


def _presign(file_item):
    return s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': BUCKET,
            'Key': file_item['s3Key'],
            'ResponseContentDisposition': f'attachment; filename="{file_item["filename"]}"',
        },
        ExpiresIn=EXPIRY,
    )


def handler(event, context):
    corr_id = correlation_id_from_event(event)
    path_params = event.get('pathParameters') or {}

    try:
        user_id, user_email = extract_user(event)
    except ValueError:
        return response(401, {'error': 'Unauthorized'})

    try:
        file_id = path_params.get('fileId')
        if not file_id:
            return response(400, {'error': 'fileId required'})

        file_item = get_file_by_id(file_id)
        if not file_item:
            return response(404, {'error': 'File not found'})

        is_owner = file_item.get('ownerId') == user_id
        share = None
        if not is_owner:
            share = _find_share(file_id, user_id, user_email)
            if not share:
                return response(403, {'error': 'Access denied'})
            permission = share.get('permission', 'read')
            if not can_download(permission):
                return response(403, {'error': 'Insufficient share permission for download'})

        try:
            s3.head_object(Bucket=BUCKET, Key=file_item['s3Key'])
        except s3.exceptions.ClientError as error:
            code = error.response.get('Error', {}).get('Code')
            if code in ('404', 'NoSuchKey', 'NotFound'):
                return response(404, {'error': 'File not found in storage'})
            raise

        if file_item.get('status') != 'ready':
            table.update_item(
                Key={'pk': file_item['pk'], 'sk': file_item['sk']},
                UpdateExpression='SET #st = :st, #ua = :ua',
                ExpressionAttributeNames={'#st': 'status', '#ua': 'updatedAt'},
                ExpressionAttributeValues={':st': 'ready', ':ua': utc_now_iso()},
            )

        download_url = _presign(file_item)
        access_type = 'owner' if is_owner else 'shared'
        out = {
            'downloadUrl': download_url,
            'fileId': file_id,
            'filename': file_item.get('filename'),
            'contentType': file_item.get('contentType', 'application/octet-stream'),
            'size': int(file_item.get('size', 0)),
            'expiresIn': EXPIRY,
            'accessType': access_type,
        }

        if share:
            out['share'] = {
                'principalType': share.get('principalType'),
                'principalValue': share.get('principalValue'),
                'permission': share.get('permission'),
                'expiresAt': share.get('expiresAt'),
            }

        log('info', 'v2_download_issued', correlation_id=corr_id, userId=user_id, fileId=file_id, accessType=access_type)
        return response(200, out)
    except Exception as err:
        log('error', 'v2_download_handler_failed', correlation_id=corr_id, error=str(err))
        return response(500, {'error': 'Internal server error'})
