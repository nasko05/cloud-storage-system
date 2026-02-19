import importlib.util
import json
import os
import sys
from pathlib import Path


_SHARED_MODULES = (
    'common',
    'db',
    'idempotency',
    'keys',
    'logging_utils',
    'pagination',
    'permissions',
    'principal',
)


def _backend_dir():
    return Path(__file__).resolve().parents[1]


def _set_test_env():
    os.environ.setdefault('AWS_EC2_METADATA_DISABLED', 'true')
    os.environ.setdefault('AWS_DEFAULT_REGION', 'eu-central-1')
    os.environ.setdefault('BUCKET_NAME', 'test-bucket')
    os.environ.setdefault('METADATA_TABLE_NAME', 'test-metadata-table')
    os.environ.setdefault('PRESIGNED_URL_EXPIRY', '3600')
    os.environ.setdefault('SHARE_EXPIRY_DAYS', '30')
    os.environ.setdefault('IDEMPOTENCY_TTL_SECONDS', '86400')
    os.environ.setdefault('ARCHIVE_JOB_TTL_DAYS', '1')
    os.environ.setdefault('ARCHIVE_QUEUE_URL', 'https://sqs.example.com/test')


def load_lambda_handler(lambda_dir_name):
    _set_test_env()
    backend_dir = _backend_dir()
    lambda_dir = backend_dir / 'lambdas' / lambda_dir_name
    shared_dir = backend_dir / 'lambdas' / 'shared_v2'

    for module_name in _SHARED_MODULES:
        sys.modules.pop(module_name, None)

    sys.path.insert(0, str(shared_dir))
    sys.path.insert(0, str(lambda_dir))
    try:
        module_path = lambda_dir / 'handler.py'
        spec = importlib.util.spec_from_file_location(f'test_{lambda_dir_name}_handler', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
    finally:
        sys.path = [p for p in sys.path if p not in (str(shared_dir), str(lambda_dir))]


def load_shared_module(module_name):
    _set_test_env()
    backend_dir = _backend_dir()
    shared_dir = backend_dir / 'lambdas' / 'shared_v2'
    for shared_name in _SHARED_MODULES:
        sys.modules.pop(shared_name, None)
    sys.modules.pop(module_name, None)
    sys.path.insert(0, str(shared_dir))
    try:
        module_path = shared_dir / f'{module_name}.py'
        spec = importlib.util.spec_from_file_location(f'test_shared_{module_name}', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
    finally:
        sys.path = [p for p in sys.path if p != str(shared_dir)]


def json_body(lambda_response):
    return json.loads(lambda_response.get('body', '{}'))
