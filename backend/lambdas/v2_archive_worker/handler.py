import json
import os
import tempfile
import zipfile
from collections import deque
from os.path import splitext

from boto3.dynamodb.conditions import Key

from common import BUCKET, s3, table, utc_now_iso
from db import get_file_by_id, get_folder_by_id
from keys import archive_job_sk, owner_parent_gsi_pk, user_pk
from logging_utils import log

MAX_FILES = 1000
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2GB
CHUNK_SIZE = 1024 * 1024


def _job_key(user_id, archive_job_id):
    return {'pk': user_pk(user_id), 'sk': archive_job_sk(archive_job_id)}


def _update_job(user_id, archive_job_id, status, **fields):
    names = {'#st': 'status', '#ua': 'updatedAt'}
    values = {':st': status, ':ua': utc_now_iso()}
    updates = ['#st = :st', '#ua = :ua']

    idx = 0
    for key, value in fields.items():
        name_token = f'#f{idx}'
        value_token = f':v{idx}'
        names[name_token] = key
        values[value_token] = value
        updates.append(f'{name_token} = {value_token}')
        idx += 1

    table.update_item(
        Key=_job_key(user_id, archive_job_id),
        UpdateExpression='SET ' + ', '.join(updates),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def _collect_folder_files(user_id, folder_ids, files_by_id):
    for folder_id in folder_ids:
        normalized = str(folder_id).strip() or 'root'
        if normalized != 'root':
            folder_item = get_folder_by_id(normalized)
            if not folder_item or folder_item.get('ownerId') != user_id:
                raise ValueError(f'Folder not found: {normalized}')

        queue = deque([normalized])
        while queue:
            current_parent = queue.popleft()
            kwargs = {
                'IndexName': 'GSI1',
                'KeyConditionExpression': Key('gsi1pk').eq(owner_parent_gsi_pk(user_id, current_parent)),
            }
            while True:
                page = table.query(**kwargs)
                for item in page.get('Items', []):
                    if item.get('ownerId') != user_id:
                        continue
                    if item.get('itemType') == 'FOLDER':
                        queue.append(item.get('folderId'))
                    elif item.get('itemType') == 'FILE':
                        file_id = item.get('fileId')
                        if file_id and file_id not in files_by_id:
                            files_by_id[file_id] = item
                lek = page.get('LastEvaluatedKey')
                if not lek:
                    break
                kwargs['ExclusiveStartKey'] = lek


def _collect_requested_files(user_id, file_ids, folder_ids):
    files_by_id = {}

    for raw_file_id in file_ids:
        file_id = str(raw_file_id).strip()
        if not file_id:
            continue
        file_item = get_file_by_id(file_id)
        if not file_item or file_item.get('ownerId') != user_id:
            raise ValueError(f'File not found: {file_id}')
        files_by_id[file_id] = file_item

    _collect_folder_files(user_id, folder_ids, files_by_id)

    files = list(files_by_id.values())
    if not files:
        raise ValueError('No files resolved for archive job')

    if len(files) > MAX_FILES:
        raise ValueError(f'Too many files selected (max: {MAX_FILES})')

    total_bytes = 0
    for item in files:
        total_bytes += int(item.get('size', 0) or 0)
    if total_bytes > MAX_TOTAL_BYTES:
        raise ValueError('Total selected data is too large')

    return files


def _folder_relative_path(user_id, folder_id, cache):
    if not folder_id or folder_id == 'root':
        return ''
    if folder_id in cache:
        return cache[folder_id]

    folder = get_folder_by_id(folder_id)
    if not folder or folder.get('ownerId') != user_id:
        cache[folder_id] = ''
        return ''

    parent_path = _folder_relative_path(user_id, folder.get('parentFolderId', 'root'), cache)
    own_name = folder.get('name', '').strip('/')
    if parent_path:
        path = f'{parent_path}/{own_name}'.strip('/')
    else:
        path = own_name

    cache[folder_id] = path
    return path


def _unique_arcname(base_name, used_names):
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name

    root, ext = splitext(base_name)
    counter = 1
    candidate = f'{root} ({counter}){ext}'
    while candidate in used_names:
        counter += 1
        candidate = f'{root} ({counter}){ext}'
    used_names.add(candidate)
    return candidate


def _file_arcname(user_id, file_item, path_cache, used_names):
    folder_path = _folder_relative_path(user_id, file_item.get('parentFolderId', 'root'), path_cache)
    filename = file_item.get('filename', 'file')
    if folder_path:
        base_name = f'{folder_path}/{filename}'
    else:
        base_name = filename
    return _unique_arcname(base_name, used_names)


def _build_archive_zip(user_id, archive_job_id, files):
    used_names = set()
    path_cache = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, f'{archive_job_id}.zip')

        with zipfile.ZipFile(zip_path, mode='w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for file_item in files:
                s3_key = file_item.get('s3Key')
                if not s3_key:
                    continue

                arcname = _file_arcname(user_id, file_item, path_cache, used_names)
                obj = s3.get_object(Bucket=BUCKET, Key=s3_key)
                body = obj['Body']
                try:
                    with archive.open(arcname, mode='w') as out_file:
                        while True:
                            chunk = body.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            out_file.write(chunk)
                finally:
                    body.close()

        zip_key = f'v2/zips/{user_id}/{archive_job_id}.zip'
        with open(zip_path, 'rb') as zip_file:
            s3.upload_fileobj(
                zip_file,
                BUCKET,
                zip_key,
                ExtraArgs={
                    'ContentType': 'application/zip',
                    'ContentDisposition': 'attachment; filename="archive.zip"',
                },
            )

    return zip_key


def _process_record(record):
    message = json.loads(record.get('body', '{}'))
    user_id = message.get('userId')
    archive_job_id = message.get('archiveJobId')
    correlation_id = message.get('correlationId', 'archive-worker')

    if not user_id or not archive_job_id:
        raise ValueError('Missing userId or archiveJobId in queue message')

    file_ids = message.get('fileIds') or []
    folder_ids = message.get('folderIds') or []

    _update_job(user_id, archive_job_id, 'processing')

    try:
        files = _collect_requested_files(user_id, file_ids, folder_ids)
        zip_key = _build_archive_zip(user_id, archive_job_id, files)
        _update_job(
            user_id,
            archive_job_id,
            'ready',
            zipKey=zip_key,
            fileCount=len(files),
            completedAt=utc_now_iso(),
            errorMessage='',
        )
        log(
            'info',
            'v2_archive_job_ready',
            correlation_id=correlation_id,
            userId=user_id,
            archiveJobId=archive_job_id,
            fileCount=len(files),
        )
    except Exception as err:
        _update_job(
            user_id,
            archive_job_id,
            'failed',
            errorMessage=str(err)[:1000],
            completedAt=utc_now_iso(),
        )
        log(
            'error',
            'v2_archive_job_failed',
            correlation_id=correlation_id,
            userId=user_id,
            archiveJobId=archive_job_id,
            error=str(err),
        )


def handler(event, context):
    records = event.get('Records') or []
    for record in records:
        _process_record(record)
    return {'processed': len(records)}
