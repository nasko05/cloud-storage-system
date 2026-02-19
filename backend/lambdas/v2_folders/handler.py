import uuid
from collections import deque
from boto3.dynamodb.conditions import Key

from common import BUCKET, extract_user, parse_json_body, response, s3, table, utc_now_iso
from db import get_folder_by_id, query_all
from idempotency import run_idempotent
from keys import (
    file_entity_pk,
    folder_sk,
    owner_parent_gsi_pk,
    owner_parent_gsi_sk,
    reverse_folder_gsi_pk,
    user_pk,
)
from logging_utils import correlation_id_from_event, log
from pagination import decode_cursor, encode_cursor, normalize_limit


def _is_valid_folder_name(value):
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


def _folder_exists_for_owner(user_id, folder_id):
    if folder_id == 'root':
        return True
    folder = get_folder_by_id(folder_id)
    return bool(folder and folder.get('ownerId') == user_id)


def _require_owner_folder(user_id, folder_id):
    if folder_id == 'root':
        return None, response(400, {'error': 'Root folder cannot be modified'})
    folder = get_folder_by_id(folder_id)
    if not folder:
        return None, response(404, {'error': 'Folder not found'})
    if folder.get('ownerId') != user_id:
        return None, response(403, {'error': 'Access denied'})
    return folder, None


def _name_conflict(user_id, parent_folder_id, item_type, name, exclude_id=None):
    prefix = f'TYPE#{item_type}#NAME#{name.strip().lower()}#'
    result = table.query(
        IndexName='GSI1',
        KeyConditionExpression=Key('gsi1pk').eq(owner_parent_gsi_pk(user_id, parent_folder_id)) & Key('gsi1sk').begins_with(prefix)
    )
    for item in result.get('Items', []):
        if item_type == 'FOLDER':
            item_id = item.get('folderId')
        else:
            item_id = item.get('fileId')
        if exclude_id and item_id == exclude_id:
            continue
        return True
    return False


def _is_descendant_folder(user_id, candidate_parent_id, source_folder_id):
    current = candidate_parent_id
    seen = set()
    while current and current != 'root':
        if current == source_folder_id:
            return True
        if current in seen:
            return True
        seen.add(current)
        current_folder = get_folder_by_id(current)
        if not current_folder or current_folder.get('ownerId') != user_id:
            return False
        current = current_folder.get('parentFolderId', 'root')
    return False


def _list_children(event, user_id, folder_id, corr_id):
    if not _folder_exists_for_owner(user_id, folder_id):
        return response(404, {'error': 'Folder not found'})

    query_params = event.get('queryStringParameters') or {}
    limit = normalize_limit(query_params.get('limit'), default=100, max_value=200)
    cursor_raw = query_params.get('cursor')
    cursor = decode_cursor(cursor_raw)
    if cursor_raw and not cursor:
        return response(400, {'error': 'Invalid cursor'})

    kwargs = {
        'IndexName': 'GSI1',
        'KeyConditionExpression': Key('gsi1pk').eq(owner_parent_gsi_pk(user_id, folder_id)),
        'Limit': limit,
    }
    if cursor:
        kwargs['ExclusiveStartKey'] = cursor

    result = table.query(**kwargs)

    items = []
    for item in result.get('Items', []):
        item_type = item.get('itemType')
        if item_type == 'FILE':
            share_count = int(item.get('shareCount', 0) or 0)
            public_link_count = int(item.get('publicLinkCount', 0) or 0)
            items.append({
                'type': 'file',
                'fileId': item.get('fileId'),
                'name': item.get('filename'),
                'parentFolderId': item.get('parentFolderId', 'root'),
                'size': int(item.get('size', 0)),
                'contentType': item.get('contentType', 'application/octet-stream'),
                'status': item.get('status', 'ready'),
                'isShared': share_count > 0,
                'hasPublicLink': public_link_count > 0,
                'createdAt': item.get('createdAt'),
                'updatedAt': item.get('updatedAt'),
            })
        elif item_type == 'FOLDER':
            items.append({
                'type': 'folder',
                'folderId': item.get('folderId'),
                'name': item.get('name'),
                'parentFolderId': item.get('parentFolderId', 'root'),
                'createdAt': item.get('createdAt'),
                'updatedAt': item.get('updatedAt'),
            })

    next_cursor = encode_cursor(result.get('LastEvaluatedKey'))
    log('info', 'v2_folder_children_listed', correlation_id=corr_id, userId=user_id, folderId=folder_id, count=len(items))
    return response(200, {'items': items, 'nextCursor': next_cursor})


def _create_folder(event, user_id, parent_folder_id, corr_id):
    if not _folder_exists_for_owner(user_id, parent_folder_id):
        return response(404, {'error': 'Parent folder not found'})

    body = parse_json_body(event)
    name = body.get('name') or body.get('folderName')
    if not _is_valid_folder_name(name):
        return response(400, {'error': 'Valid folder name required'})

    if _name_conflict(user_id, parent_folder_id, 'FOLDER', name):
        return response(409, {'error': 'A folder with that name already exists in destination folder'})

    folder_id = str(uuid.uuid4())
    now = utc_now_iso()
    item = {
        'pk': user_pk(user_id),
        'sk': folder_sk(folder_id),
        'gsi1pk': owner_parent_gsi_pk(user_id, parent_folder_id),
        'gsi1sk': owner_parent_gsi_sk('FOLDER', name, folder_id),
        'gsi2pk': reverse_folder_gsi_pk(folder_id),
        'gsi2sk': 'FOLDER',
        'itemType': 'FOLDER',
        'folderId': folder_id,
        'name': name,
        'parentFolderId': parent_folder_id,
        'ownerId': user_id,
        'createdAt': now,
        'updatedAt': now,
    }

    table.put_item(Item=item, ConditionExpression='attribute_not_exists(pk) AND attribute_not_exists(sk)')
    log('info', 'v2_folder_created', correlation_id=corr_id, userId=user_id, folderId=folder_id)
    return response(201, {
        'folderId': folder_id,
        'name': name,
        'parentFolderId': parent_folder_id,
    })


def _patch_folder(event, user_id, folder_id, corr_id):
    body = parse_json_body(event)
    new_name = body.get('newName')
    destination_folder_id = body.get('destinationFolderId')

    if new_name is None and destination_folder_id is None:
        return response(400, {'error': 'At least one of newName or destinationFolderId is required'})

    folder_item, err = _require_owner_folder(user_id, folder_id)
    if err:
        return err

    target_name = folder_item['name'] if new_name is None else str(new_name).strip()
    if not _is_valid_folder_name(target_name):
        return response(400, {'error': 'Valid newName required'})

    target_parent = folder_item.get('parentFolderId', 'root')
    if destination_folder_id is not None:
        target_parent = str(destination_folder_id).strip() or 'root'

    if target_parent == folder_id:
        return response(400, {'error': 'Folder cannot be moved into itself'})

    if not _folder_exists_for_owner(user_id, target_parent):
        return response(404, {'error': 'Destination folder not found'})

    if _is_descendant_folder(user_id, target_parent, folder_id):
        return response(400, {'error': 'Cannot move folder into its own subfolder'})

    if _name_conflict(user_id, target_parent, 'FOLDER', target_name, exclude_id=folder_id):
        return response(409, {'error': 'A folder with that name already exists in destination folder'})

    if target_name == folder_item['name'] and target_parent == folder_item.get('parentFolderId', 'root'):
        return response(200, {'message': 'No changes'})

    now = utc_now_iso()
    table.update_item(
        Key={'pk': folder_item['pk'], 'sk': folder_item['sk']},
        UpdateExpression='SET #nm = :nm, #pf = :pf, #g1pk = :g1pk, #g1sk = :g1sk, #ua = :ua',
        ExpressionAttributeNames={
            '#nm': 'name',
            '#pf': 'parentFolderId',
            '#g1pk': 'gsi1pk',
            '#g1sk': 'gsi1sk',
            '#ua': 'updatedAt',
        },
        ExpressionAttributeValues={
            ':nm': target_name,
            ':pf': target_parent,
            ':g1pk': owner_parent_gsi_pk(user_id, target_parent),
            ':g1sk': owner_parent_gsi_sk('FOLDER', target_name, folder_id),
            ':ua': now,
        },
    )

    log('info', 'v2_folder_patched', correlation_id=corr_id, userId=user_id, folderId=folder_id)
    return response(200, {
        'message': 'Folder updated',
        'folderId': folder_id,
        'name': target_name,
        'parentFolderId': target_parent,
    })


def _delete_folder(event, user_id, folder_id, corr_id):
    folder_item, err = _require_owner_folder(user_id, folder_id)
    if err:
        return err

    query_params = event.get('queryStringParameters') or {}
    recursive = str(query_params.get('recursive', 'false')).lower() in ('1', 'true', 'yes')

    folders_to_delete = [folder_item]
    files_to_delete = []

    if recursive:
        queue = deque([folder_id])
        while queue:
            parent_id = queue.popleft()
            query_kwargs = {
                'IndexName': 'GSI1',
                'KeyConditionExpression': Key('gsi1pk').eq(owner_parent_gsi_pk(user_id, parent_id)),
            }
            while True:
                page = table.query(**query_kwargs)
                for child in page.get('Items', []):
                    if child.get('ownerId') != user_id:
                        continue
                    if child.get('itemType') == 'FOLDER':
                        folders_to_delete.append(child)
                        queue.append(child.get('folderId'))
                    elif child.get('itemType') == 'FILE':
                        files_to_delete.append(child)
                lek = page.get('LastEvaluatedKey')
                if not lek:
                    break
                query_kwargs['ExclusiveStartKey'] = lek
    else:
        children_result = table.query(
            IndexName='GSI1',
            KeyConditionExpression=Key('gsi1pk').eq(owner_parent_gsi_pk(user_id, folder_id)),
            Limit=1,
        )
        if children_result.get('Items'):
            return response(409, {'error': 'Folder is not empty', 'hint': 'Retry with ?recursive=true to cascade delete'})

    for file_item in files_to_delete:
        s3_key = file_item.get('s3Key')
        if not s3_key:
            continue
        try:
            s3.delete_object(Bucket=BUCKET, Key=s3_key)
        except Exception:
            pass

    related_items = []
    for file_item in files_to_delete:
        file_id = file_item.get('fileId')
        if not file_id:
            continue
        related_items.extend(
            query_all(KeyConditionExpression=Key('pk').eq(file_entity_pk(file_id)))
        )

    with table.batch_writer() as batch:
        for item in files_to_delete:
            batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})
        for item in folders_to_delete:
            batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})
        for item in related_items:
            batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

    log(
        'info',
        'v2_folder_deleted',
        correlation_id=corr_id,
        userId=user_id,
        folderId=folder_id,
        recursive=recursive,
        deletedFolders=len(folders_to_delete),
        deletedFiles=len(files_to_delete),
    )
    return response(200, {
        'message': 'Folder deleted',
        'folderId': folder_id,
        'recursive': recursive,
        'deletedFolders': len(folders_to_delete),
        'deletedFiles': len(files_to_delete),
    })


def handler(event, context):
    corr_id = correlation_id_from_event(event)
    route_key = event.get('requestContext', {}).get('routeKey', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    path_params = event.get('pathParameters') or {}

    try:
        user_id, _ = extract_user(event)
    except ValueError:
        return response(401, {'error': 'Unauthorized'})

    try:
        folder_id = path_params.get('folderId')

        if route_key == 'GET /v2/folders/{folderId}/children' or (method == 'GET' and folder_id and route_key.endswith('/children')):
            if not folder_id:
                return response(400, {'error': 'folderId required'})
            return _list_children(event, user_id, folder_id, corr_id)

        if route_key == 'POST /v2/folders/{folderId}/folders' or (method == 'POST' and folder_id and route_key.endswith('/folders')):
            if not folder_id:
                return response(400, {'error': 'folderId required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-folders-create-{folder_id}',
                lambda: _create_folder(event, user_id, folder_id, corr_id),
            )

        if route_key == 'PATCH /v2/folders/{folderId}' or (method == 'PATCH' and folder_id):
            if not folder_id:
                return response(400, {'error': 'folderId required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-folders-patch-{folder_id}',
                lambda: _patch_folder(event, user_id, folder_id, corr_id),
            )

        if route_key == 'DELETE /v2/folders/{folderId}' or (method == 'DELETE' and folder_id):
            if not folder_id:
                return response(400, {'error': 'folderId required'})
            return run_idempotent(
                event,
                user_id,
                f'v2-folders-delete-{folder_id}',
                lambda: _delete_folder(event, user_id, folder_id, corr_id),
            )

        return response(404, {'error': 'Route not found'})
    except Exception as err:
        log('error', 'v2_folders_handler_failed', correlation_id=corr_id, error=str(err))
        return response(500, {'error': 'Internal server error'})
