import json
import uuid

from boto3.dynamodb.conditions import Key

from common import BUCKET, EXPIRY, response, extract_user, parse_json_body, s3, table, utc_now_iso
from db import get_file_by_id, get_folder_by_id, query_all
from idempotency import run_idempotent
from keys import (
    file_entity_pk,
    file_sk,
    owner_parent_gsi_pk,
    owner_parent_gsi_sk,
    reverse_file_gsi_pk,
    user_pk,
)
from logging_utils import correlation_id_from_event, log


def _is_valid_filename(value):
    if not value or not isinstance(value, str):
        return False
    name = value.strip()
    if not name:
        return False
    if '/' in name or '..' in name:
        return False
    if len(name) > 255:
        return False
    if '\x00' in name:
        return False
    return True


def _parent_folder_id(body):
    value = body.get('parentFolderId')
    if not value:
        return 'root'
    return str(value).strip() or 'root'


def _folder_exists_for_owner(user_id, folder_id):
    if folder_id == 'root':
        return True
    folder = get_folder_by_id(folder_id)
    return bool(folder and folder.get('ownerId') == user_id)


def _name_conflict(user_id, parent_folder_id, item_type, name, exclude_id=None):
    prefix = f'TYPE#{item_type}#NAME#{name.strip().lower()}#'
    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(owner_parent_gsi_pk(user_id, parent_folder_id)) & Key('gsi1sk').begins_with(prefix)
    )
    for item in result.get('Items', []):
        if item_type == 'FILE':
            item_id = item.get('fileId')
        else:
            item_id = item.get('folderId')
        if exclude_id and item_id == exclude_id:
            continue
        return True
    return False


def _require_owner_file(user_id, file_id):
    file_item = get_file_by_id(file_id)
    if not file_item:
        return None, response(404, {'error': 'File not found'})
    if file_item.get('ownerId') != user_id:
        return None, response(403, {'error': 'Access denied'})
    return file_item, None


def _create_upload(event, user_id, user_email, corr_id):
    body = parse_json_body(event)
    filename = body.get('filename')
    if not _is_valid_filename(filename):
        return response(400, {'error': 'Valid filename required'})

    parent_folder_id = _parent_folder_id(body)
    if not _folder_exists_for_owner(user_id, parent_folder_id):
        return response(404, {'error': 'Parent folder not found'})

    if _name_conflict(user_id, parent_folder_id, 'FILE', filename):
        return response(409, {'error': 'A file with that name already exists in destination folder'})

    file_id = str(uuid.uuid4())
    content_type = body.get('contentType') or 'application/octet-stream'
    raw_size = body.get('size') or 0
    try:
        size = int(raw_size)
    except (TypeError, ValueError):
        return response(400, {'error': 'size must be an integer'})
    if size < 0:
        return response(400, {'error': 'size must be non-negative'})
    s3_key = f'v2/files/{user_id}/{file_id}/{filename}'
    now = utc_now_iso()

    item = {
        'pk': user_pk(user_id),
        'sk': file_sk(file_id),
        'gsi1pk': owner_parent_gsi_pk(user_id, parent_folder_id),
        'gsi1sk': owner_parent_gsi_sk('FILE', filename, file_id),
        'gsi2pk': reverse_file_gsi_pk(file_id),
        'gsi2sk': 'FILE',
        'itemType': 'FILE',
        'fileId': file_id,
        'filename': filename,
        'parentFolderId': parent_folder_id,
        'ownerId': user_id,
        'ownerEmail': user_email,
        's3Key': s3_key,
        'contentType': content_type,
        'size': size,
        'status': 'pending',
        'createdAt': now,
        'updatedAt': now,
    }

    table.put_item(Item=item, ConditionExpression='attribute_not_exists(pk) AND attribute_not_exists(sk)')

    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': BUCKET, 'Key': s3_key},
        ExpiresIn=EXPIRY,
    )

    log('info', 'v2_file_upload_created', correlation_id=corr_id, userId=user_id, fileId=file_id)
    return response(201, {
        'fileId': file_id,
        'uploadUrl': upload_url,
        'expiresIn': EXPIRY,
        'status': 'pending',
    })


def _patch_file(event, user_id, file_id, corr_id):
    body = parse_json_body(event)
    new_name = body.get('newName')
    destination_folder_id = body.get('destinationFolderId')

    if new_name is None and destination_folder_id is None:
        return response(400, {'error': 'At least one of newName or destinationFolderId is required'})

    file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    target_name = file_item['filename'] if new_name is None else str(new_name).strip()
    if not _is_valid_filename(target_name):
        return response(400, {'error': 'Valid newName required'})

    target_parent = file_item.get('parentFolderId', 'root')
    if destination_folder_id is not None:
        target_parent = str(destination_folder_id).strip() or 'root'

    if not _folder_exists_for_owner(user_id, target_parent):
        return response(404, {'error': 'Destination folder not found'})

    if _name_conflict(user_id, target_parent, 'FILE', target_name, exclude_id=file_id):
        return response(409, {'error': 'A file with that name already exists in destination folder'})

    if target_name == file_item['filename'] and target_parent == file_item.get('parentFolderId', 'root'):
        return response(200, {'message': 'No changes'})

    now = utc_now_iso()
    table.update_item(
        Key={'pk': file_item['pk'], 'sk': file_item['sk']},
        UpdateExpression='SET #fn = :fn, #pf = :pf, #g1pk = :g1pk, #g1sk = :g1sk, #ua = :ua',
        ExpressionAttributeNames={
            '#fn': 'filename',
            '#pf': 'parentFolderId',
            '#g1pk': 'gsi1pk',
            '#g1sk': 'gsi1sk',
            '#ua': 'updatedAt',
        },
        ExpressionAttributeValues={
            ':fn': target_name,
            ':pf': target_parent,
            ':g1pk': owner_parent_gsi_pk(user_id, target_parent),
            ':g1sk': owner_parent_gsi_sk('FILE', target_name, file_id),
            ':ua': now,
        },
    )

    log('info', 'v2_file_patched', correlation_id=corr_id, userId=user_id, fileId=file_id)
    return response(200, {
        'message': 'File updated',
        'fileId': file_id,
        'filename': target_name,
        'parentFolderId': target_parent,
    })


def _delete_file(_event, user_id, file_id, corr_id):
    file_item, err = _require_owner_file(user_id, file_id)
    if err:
        return err

    # Best-effort S3 delete
    try:
        s3.delete_object(Bucket=BUCKET, Key=file_item['s3Key'])
    except Exception:
        pass

    related_items = query_all(
        KeyConditionExpression=Key('pk').eq(file_entity_pk(file_id))
    )

    with table.batch_writer() as batch:
        batch.delete_item(Key={'pk': file_item['pk'], 'sk': file_item['sk']})
        for rel in related_items:
            batch.delete_item(Key={'pk': rel['pk'], 'sk': rel['sk']})

    log('info', 'v2_file_deleted', correlation_id=corr_id, userId=user_id, fileId=file_id)
    return response(200, {'message': 'File deleted', 'fileId': file_id})


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
        if route_key == 'POST /v2/files/uploads':
            return run_idempotent(
                event,
                user_id,
                'v2-files-upload-create',
                lambda: _create_upload(event, user_id, user_email, corr_id),
            )

        if route_key == 'PATCH /v2/files/{fileId}' or (method == 'PATCH' and 'fileId' in path_params):
            file_id = path_params.get('fileId')
            if not file_id:
                return response(400, {'error': 'fileId required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-files-patch-{file_id}',
                lambda: _patch_file(event, user_id, file_id, corr_id),
            )

        if route_key == 'DELETE /v2/files/{fileId}' or (method == 'DELETE' and 'fileId' in path_params):
            file_id = path_params.get('fileId')
            if not file_id:
                return response(400, {'error': 'fileId required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-files-delete-{file_id}',
                lambda: _delete_file(event, user_id, file_id, corr_id),
            )

        return response(404, {'error': 'Route not found'})
    except Exception as err:
        log('error', 'v2_files_handler_failed', correlation_id=corr_id, error=str(err))
        return response(500, {'error': 'Internal server error'})
