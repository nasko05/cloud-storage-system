#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / 'backend'
SHARED_DIR = BACKEND_DIR / 'lambdas' / 'shared_v2'


def _set_env():
    os.environ.setdefault('AWS_EC2_METADATA_DISABLED', 'true')
    os.environ.setdefault('AWS_DEFAULT_REGION', 'eu-central-1')
    os.environ.setdefault('BUCKET_NAME', 'bench-bucket')
    os.environ.setdefault('METADATA_TABLE_NAME', 'bench-metadata-table')
    os.environ.setdefault('PRESIGNED_URL_EXPIRY', '3600')
    os.environ.setdefault('SHARE_EXPIRY_DAYS', '30')
    os.environ.setdefault('IDEMPOTENCY_TTL_SECONDS', '86400')
    os.environ.setdefault('ARCHIVE_JOB_TTL_DAYS', '1')
    os.environ.setdefault('ARCHIVE_QUEUE_URL', 'https://sqs.example.com/bench')


def _load_lambda_module(lambda_dir_name):
    _set_env()
    lambda_dir = BACKEND_DIR / 'lambdas' / lambda_dir_name

    for mod_name in ('common', 'db', 'keys', 'logging_utils', 'pagination', 'permissions', 'principal', 'idempotency'):
        sys.modules.pop(mod_name, None)

    sys.path.insert(0, str(SHARED_DIR))
    sys.path.insert(0, str(lambda_dir))
    try:
        module_path = lambda_dir / 'handler.py'
        spec = importlib.util.spec_from_file_location(f'bench_{lambda_dir_name}_handler', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
    finally:
        sys.path = [p for p in sys.path if p not in (str(SHARED_DIR), str(lambda_dir))]


class _StreamingBody:
    def __init__(self, payload, chunk_size):
        self.payload = payload
        self.chunk_size = chunk_size
        self.offset = 0

    def read(self, amount):
        if self.offset >= len(self.payload):
            return b''
        size = min(self.chunk_size, len(self.payload) - self.offset)
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += size
        return chunk

    def close(self):
        return None


class _ArchiveS3Stub:
    def __init__(self, file_bytes, chunk_size):
        self.file_bytes = file_bytes
        self.chunk_size = chunk_size
        self.uploaded_bytes = 0

    def get_object(self, **kwargs):
        return {'Body': _StreamingBody(self.file_bytes, self.chunk_size)}

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        data = fileobj.read()
        self.uploaded_bytes += len(data)


class _PagedTableStub:
    def __init__(self, items):
        self.items = items

    def query(self, **kwargs):
        limit = int(kwargs.get('Limit', len(self.items)))
        start = 0
        eks = kwargs.get('ExclusiveStartKey')
        if isinstance(eks, dict):
            start = int(eks.get('_idx', 0))

        page_items = self.items[start:start + limit]
        result = {'Items': page_items}
        if start + limit < len(self.items):
            result['LastEvaluatedKey'] = {'_idx': start + limit}
        return result


def benchmark_archive_zip_build(files_count, file_size_kb):
    module = _load_lambda_module('v2_archive_worker')

    files = []
    for idx in range(files_count):
        files.append({
            'fileId': f'file-{idx}',
            'filename': f'payload-{idx}.bin',
            'parentFolderId': 'root',
            's3Key': f'v2/files/bench/file-{idx}.bin',
            'ownerId': 'bench-user',
            'size': file_size_kb * 1024,
        })

    payload = b'a' * (file_size_kb * 1024)
    s3_stub = _ArchiveS3Stub(payload, module.CHUNK_SIZE)
    module.s3 = s3_stub

    started = time.perf_counter()
    zip_key = module._build_archive_zip('bench-user', 'bench-job', files)
    elapsed = time.perf_counter() - started

    input_mb = (files_count * file_size_kb) / 1024
    uploaded_mb = s3_stub.uploaded_bytes / (1024 * 1024)

    return {
        'name': 'archive_zip_build',
        'elapsed_s': elapsed,
        'input_mb': input_mb,
        'uploaded_zip_mb': uploaded_mb,
        'files_count': files_count,
        'zip_key': zip_key,
    }


def benchmark_folder_listing(items_count, page_size):
    module = _load_lambda_module('v2_folders')

    items = []
    for idx in range(items_count):
        if idx % 5 == 0:
            items.append({
                'itemType': 'FOLDER',
                'folderId': f'folder-{idx}',
                'name': f'Folder {idx}',
                'parentFolderId': 'root',
                'createdAt': '2026-02-18T00:00:00Z',
                'updatedAt': '2026-02-18T00:00:00Z',
            })
            continue
        items.append({
            'itemType': 'FILE',
            'fileId': f'file-{idx}',
            'filename': f'File {idx}.txt',
            'parentFolderId': 'root',
            'size': 1024 + idx,
            'contentType': 'text/plain',
            'status': 'ready',
            'shareCount': idx % 3,
            'publicLinkCount': idx % 4,
            'createdAt': '2026-02-18T00:00:00Z',
            'updatedAt': '2026-02-18T00:00:00Z',
        })

    module.table = _PagedTableStub(items)
    module._folder_exists_for_owner = lambda user_id, folder_id: True
    module.log = lambda *args, **kwargs: None

    total_items = 0
    cursor = None
    started = time.perf_counter()

    while True:
        query = {'limit': str(page_size)}
        if cursor:
            query['cursor'] = cursor

        event = {'queryStringParameters': query}
        response = module._list_children(event, 'bench-user', 'root', 'bench-correlation')
        if response.get('statusCode') != 200:
            raise RuntimeError(f'Unexpected response status: {response.get("statusCode")}')

        body = json.loads(response['body'])
        page_items = body.get('items', [])
        total_items += len(page_items)

        cursor = body.get('nextCursor')
        if not cursor:
            break

    elapsed = time.perf_counter() - started

    return {
        'name': 'folder_children_listing',
        'elapsed_s': elapsed,
        'items_count': items_count,
        'items_returned': total_items,
        'page_size': page_size,
    }


def _print_result(result):
    if result['name'] == 'archive_zip_build':
        throughput = 0.0
        if result['elapsed_s'] > 0:
            throughput = result['input_mb'] / result['elapsed_s']
        print(
            f"[archive_zip_build] files={result['files_count']} input={result['input_mb']:.2f}MB "
            f"zip={result['uploaded_zip_mb']:.2f}MB elapsed={result['elapsed_s']:.3f}s "
            f"throughput={throughput:.2f}MB/s"
        )
        return

    print(
        f"[folder_children_listing] items={result['items_count']} returned={result['items_returned']} "
        f"page_size={result['page_size']} elapsed={result['elapsed_s']:.3f}s"
    )


def main():
    parser = argparse.ArgumentParser(description='Run backend performance benchmarks.')
    parser.add_argument('--smoke', action='store_true', help='Run reduced benchmark sizes for CI smoke checks.')
    parser.add_argument('--assert-max-seconds', type=float, default=0.0, help='Fail if any benchmark exceeds this threshold.')
    args = parser.parse_args()

    if args.smoke:
        archive_files = 80
        archive_file_size_kb = 24
        listing_items = 1200
        listing_page_size = 200
    else:
        archive_files = 400
        archive_file_size_kb = 64
        listing_items = 10000
        listing_page_size = 500

    results = [
        benchmark_folder_listing(listing_items, listing_page_size),
        benchmark_archive_zip_build(archive_files, archive_file_size_kb),
    ]

    print('Backend benchmark results:')
    for item in results:
        _print_result(item)

    if args.assert_max_seconds and args.assert_max_seconds > 0:
        too_slow = [item for item in results if item['elapsed_s'] > args.assert_max_seconds]
        if too_slow:
            names = ', '.join(item['name'] for item in too_slow)
            raise SystemExit(f'Benchmarks exceeded threshold ({args.assert_max_seconds}s): {names}')


if __name__ == '__main__':
    main()
