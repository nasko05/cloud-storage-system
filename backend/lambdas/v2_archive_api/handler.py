import json
import time
import uuid

from common import (
    ARCHIVE_JOB_TTL_DAYS,
    ARCHIVE_QUEUE_URL,
    BUCKET,
    EXPIRY,
    extract_user,
    parse_json_body,
    response,
    s3,
    sqs,
    table,
    utc_epoch,
    utc_now_iso,
)
from idempotency import run_idempotent
from keys import archive_job_sk, user_pk
from logging_utils import correlation_id_from_event, log


def _normalize_id_list(value):
    if not isinstance(value, list):
        return []
    deduped = []
    seen = set()
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _queue_archive_job(event, user_id, corr_id):
    if not ARCHIVE_QUEUE_URL:
        return response(500, {'error': 'Archive queue is not configured'})

    body = parse_json_body(event)
    file_ids = _normalize_id_list(body.get('fileIds'))
    folder_ids = _normalize_id_list(body.get('folderIds'))

    if not file_ids and not folder_ids:
        return response(400, {'error': 'At least one fileId or folderId is required'})

    archive_job_id = str(uuid.uuid4())
    now_iso = utc_now_iso()
    now_epoch = utc_epoch()
    ttl = now_epoch + (ARCHIVE_JOB_TTL_DAYS * 86400)

    item = {
        'pk': user_pk(user_id),
        'sk': archive_job_sk(archive_job_id),
        'itemType': 'ARCHIVE_JOB',
        'archiveJobId': archive_job_id,
        'ownerId': user_id,
        'status': 'queued',
        'requestedFileIds': file_ids,
        'requestedFolderIds': folder_ids,
        'createdAt': now_iso,
        'updatedAt': now_iso,
        'ttl': ttl,
    }
    table.put_item(Item=item, ConditionExpression='attribute_not_exists(pk) AND attribute_not_exists(sk)')

    message = {
        'archiveJobId': archive_job_id,
        'userId': user_id,
        'fileIds': file_ids,
        'folderIds': folder_ids,
        'requestedAt': now_iso,
        'correlationId': corr_id,
    }
    sqs.send_message(QueueUrl=ARCHIVE_QUEUE_URL, MessageBody=json.dumps(message))

    log('info', 'v2_archive_job_queued', correlation_id=corr_id, userId=user_id, archiveJobId=archive_job_id)
    return response(202, {
        'archiveJobId': archive_job_id,
        'status': 'queued',
    })


def _get_archive_status(user_id, archive_job_id, corr_id):
    key = {'pk': user_pk(user_id), 'sk': archive_job_sk(archive_job_id)}
    item = table.get_item(Key=key).get('Item')
    if not item or item.get('itemType') != 'ARCHIVE_JOB':
        return response(404, {'error': 'Archive job not found'})

    now_epoch = int(time.time())
    ttl = item.get('ttl')
    status = item.get('status', 'queued')
    if ttl is not None:
        try:
            if int(ttl) <= now_epoch and status in ('ready', 'failed'):
                status = 'expired'
        except (TypeError, ValueError):
            pass

    out = {
        'archiveJobId': archive_job_id,
        'status': status,
        'createdAt': item.get('createdAt'),
        'updatedAt': item.get('updatedAt'),
    }

    if status == 'ready' and item.get('zipKey'):
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BUCKET,
                'Key': item['zipKey'],
                'ResponseContentDisposition': 'attachment; filename="archive.zip"',
            },
            ExpiresIn=EXPIRY,
        )
        out['downloadUrl'] = download_url
        out['expiresIn'] = EXPIRY

    if item.get('errorMessage'):
        out['errorMessage'] = item.get('errorMessage')

    if item.get('fileCount') is not None:
        out['fileCount'] = int(item.get('fileCount', 0))

    log('info', 'v2_archive_job_polled', correlation_id=corr_id, userId=user_id, archiveJobId=archive_job_id, status=status)
    return response(200, out)


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
        if route_key == 'POST /v2/download/archives' or (method == 'POST' and route_key.endswith('/archives')):
            return run_idempotent(
                event,
                user_id,
                'v2-archive-queue',
                lambda: _queue_archive_job(event, user_id, corr_id),
            )

        if route_key == 'GET /v2/download/archives/{archiveJobId}' or (method == 'GET' and path_params.get('archiveJobId')):
            archive_job_id = path_params.get('archiveJobId')
            if not archive_job_id:
                return response(400, {'error': 'archiveJobId required'})
            return _get_archive_status(user_id, archive_job_id, corr_id)

        return response(404, {'error': 'Route not found'})
    except Exception as err:
        log('error', 'v2_archive_api_handler_failed', correlation_id=corr_id, error=str(err))
        return response(500, {'error': 'Internal server error'})
