"""
Zip download Lambda – builds a ZIP from selected files and/or folders,
uploads to S3, returns a presigned download URL. JWT required.
"""

import json
import os
import tempfile
import traceback
import uuid
import zipfile
from boto3.dynamodb.conditions import Key

from common import BUCKET, EXPIRY, response, extract_user, table, s3

# Deploy copies shared into this dir
from db_helpers import user_pk, file_sk_prefix, find_file_by_id, get_folder_or_404

MAX_FILES = 500
MAX_TOTAL_BYTES = 500 * 1024 * 1024  # 500 MB




def _resolve_files_for_folders(user_id, folder_paths):
    """Return list of file items (s3Key, path, filename, fileId, size) under the given folder paths.
    Each folder_path is normalized (e.g. '/', '/Docs'). Uses DynamoDB prefix query; paginates.
    """
    seen_ids = set()
    files = []
    pk = user_pk(user_id)

    for folder_path in folder_paths:
        if not folder_path or not isinstance(folder_path, str):
            continue
        path = folder_path if folder_path.startswith('/') else '/' + folder_path
        prefix = file_sk_prefix(path)
        kwargs = {
            'KeyConditionExpression': Key('pk').eq(pk) & Key('sk').begins_with(prefix),
        }
        while True:
            resp = table.query(**kwargs)
            for item in resp.get('Items', []):
                if item.get('itemType') != 'FILE':
                    continue
                if item.get('ownerId') != user_id:
                    continue
                fid = item.get('fileId')
                if fid in seen_ids:
                    continue
                seen_ids.add(fid)
                files.append({
                    'fileId': fid,
                    's3Key': item['s3Key'],
                    'path': item.get('path', '/'),
                    'filename': item['filename'],
                    'size': int(item.get('size', 0)),
                })
            if 'LastEvaluatedKey' not in resp:
                break
            kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']

    return files


def _resolve_files_by_ids(user_id, file_ids):
    """Return list of file items for the given file IDs; all must be owned by user_id."""
    files = []
    for fid in file_ids:
        if not fid:
            continue
        file_item, _, err = find_file_by_id(user_id, fid)
        if err:
            return None, err
        files.append({
            'fileId': file_item['fileId'],
            's3Key': file_item['s3Key'],
            'path': file_item.get('path', '/'),
            'filename': file_item['filename'],
            'size': int(file_item.get('size', 0)),
        })
    return files, None


def _arcname(path, filename, used_names):
    """Produce a unique arcname for the ZIP entry; path is e.g. '/' or '/Docs/Sub'."""
    if path == '/' or not path.strip('/'):
        base = filename
    else:
        base = path.strip('/') + '/' + filename
    if base not in used_names:
        used_names.add(base)
        return base
    stem = base
    i = 1
    while base in used_names:
        if '.' in filename:
            part = filename.rsplit('.', 1)
            base = (path.strip('/') + '/' + part[0] + f' ({i}).' + part[1]) if path != '/' and path.strip('/') else part[0] + f' ({i}).' + part[1]
        else:
            base = (path.strip('/') + '/' + filename + f' ({i})') if path != '/' and path.strip('/') else filename + f' ({i})'
        i += 1
    used_names.add(base)
    return base


def handler(event, context):
    try:
        user_id, _ = extract_user(event)
    except ValueError:
        return response(401, {'error': 'Unauthorized'})

    try:
        body = json.loads(event.get('body') or '{}')
        file_ids = body.get('fileIds') or []
        folder_paths = body.get('folderPaths') or []

        if not file_ids and not folder_paths:
            return response(400, {'error': 'Select at least one file or folder.'})

        if not isinstance(file_ids, list):
            file_ids = []
        if not isinstance(folder_paths, list):
            folder_paths = []
        file_ids = list(dict.fromkeys([f for f in file_ids if f]))

        # Resolve folders: ensure each path exists and is owned
        for path in folder_paths:
            if path == '/' or path == '':
                continue
            norm = path if path.startswith('/') else '/' + path
            _, err = get_folder_or_404(user_id, norm)
            if err:
                return err

        # Collect files from explicit file IDs
        list_files, err = _resolve_files_by_ids(user_id, file_ids)
        if err:
            return err

        # Collect files from folders (recursive)
        seen = {f['fileId'] for f in list_files}
        for path in folder_paths:
            norm = path if isinstance(path, str) and path.startswith('/') else '/' + (path or '')
            resolved = _resolve_files_for_folders(user_id, [norm])
            for f in resolved:
                if f['fileId'] not in seen:
                    seen.add(f['fileId'])
                    list_files.append(f)

        if not list_files:
            return response(400, {'error': 'No files to download.'})

        if len(list_files) > MAX_FILES:
            return response(400, {'error': 'Too many items; reduce selection.', 'max': MAX_FILES})

        total_size = sum(f['size'] for f in list_files)
        if total_size > MAX_TOTAL_BYTES:
            return response(400, {'error': 'Total size too large; reduce selection.', 'maxMB': MAX_TOTAL_BYTES // (1024 * 1024)})

        # Build ZIP to temp file
        zip_path = os.path.join(tempfile.gettempdir(), f'zip-{uuid.uuid4().hex}.zip')
        used_arcnames = set()
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in list_files:
                    arcname = _arcname(f['path'], f['filename'], used_arcnames)
                    try:
                        obj = s3.get_object(Bucket=BUCKET, Key=f['s3Key'])
                        data = obj['Body'].read()
                    except Exception as e:
                        print(json.dumps({'error': 's3_get_failed', 'key': f['s3Key'], 'message': str(e)}))
                        continue
                    zf.writestr(arcname, data)
            zip_size = os.path.getsize(zip_path)
        except Exception as e:
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
            print(json.dumps({'error': str(e), 'traceback': traceback.format_exc()}))
            return response(500, {'error': 'Failed to create ZIP.'})

        # Upload ZIP to S3
        zip_key = f'zips/{user_id}/{uuid.uuid4().hex}.zip'
        try:
            with open(zip_path, 'rb') as fh:
                s3.put_object(
                    Bucket=BUCKET,
                    Key=zip_key,
                    Body=fh,
                    ContentType='application/zip',
                    ContentDisposition='attachment; filename="download.zip"',
                )
        finally:
            try:
                os.remove(zip_path)
            except OSError:
                pass

        download_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BUCKET,
                'Key': zip_key,
                'ResponseContentDisposition': 'attachment; filename="download.zip"',
            },
            ExpiresIn=EXPIRY,
        )

        print(json.dumps({'action': 'zip-download', 'userId': user_id, 'fileCount': len(list_files), 'zipKey': zip_key}))
        return response(200, {'downloadUrl': download_url, 'expiresIn': EXPIRY})
    except Exception as e:
        print(json.dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        return response(500, {'error': 'Internal server error'})
