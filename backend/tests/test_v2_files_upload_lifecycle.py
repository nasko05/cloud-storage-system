import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from lambda_test_utils import json_body, load_lambda_handler


class _S3UploadStub:
    class _ClientError(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {'Error': {'Code': code}}

    exceptions = SimpleNamespace(ClientError=_ClientError)

    def __init__(self, *, object_exists=True):
        self.object_exists = object_exists

    def generate_presigned_url(self, *args, **kwargs):
        return 'https://example.com/upload'

    def head_object(self, **kwargs):
        if not self.object_exists:
            raise self._ClientError('NoSuchKey')
        return {'ContentLength': 42, 'ContentType': 'application/pdf'}


class V2FilesUploadLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.module = load_lambda_handler('v2_files')

    def test_upload_init_creates_pending_metadata(self):
        table_mock = MagicMock()
        s3_mock = _S3UploadStub()

        event = {
            'requestContext': {
                'routeKey': 'POST /v2/files/uploads',
                'http': {'method': 'POST'},
            },
            'body': json.dumps({
                'filename': 'report.pdf',
                'contentType': 'application/pdf',
                'size': 42,
                'parentFolderId': 'root',
            }),
            'headers': {},
        }

        with patch.object(self.module, 'extract_user', return_value=('user-1', 'user@example.com')):
            with patch.object(self.module, '_folder_exists_for_owner', return_value=True):
                with patch.object(self.module, '_name_conflict', return_value=False):
                    with patch.object(self.module, 'table', table_mock):
                        with patch.object(self.module, 's3', s3_mock):
                            with patch.object(self.module.uuid, 'uuid4', return_value='file-123'):
                                result = self.module.handler(event, None)

        self.assertEqual(result['statusCode'], 201)
        body = json_body(result)
        self.assertEqual(body.get('status'), 'pending')
        self.assertEqual(body.get('fileId'), 'file-123')
        self.assertEqual(body.get('uploadUrl'), 'https://example.com/upload')

        put_kwargs = table_mock.put_item.call_args.kwargs
        item = put_kwargs['Item']
        self.assertEqual(item['status'], 'pending')
        self.assertEqual(item['fileId'], 'file-123')
        self.assertEqual(item['ownerId'], 'user-1')

    def test_finalize_marks_file_ready_when_object_exists(self):
        table_mock = MagicMock()
        s3_mock = _S3UploadStub(object_exists=True)
        event = {
            'requestContext': {
                'routeKey': 'POST /v2/files/{fileId}/finalize',
                'http': {'method': 'POST'},
            },
            'pathParameters': {'fileId': 'file-123'},
            'headers': {},
        }
        file_item = {
            'pk': 'USER#user-1',
            'sk': 'FILE#file-123',
            'fileId': 'file-123',
            'ownerId': 'user-1',
            'filename': 'report.pdf',
            's3Key': 'v2/files/user-1/file-123/report.pdf',
            'contentType': 'application/octet-stream',
            'size': 0,
            'status': 'pending',
        }

        with patch.object(self.module, 'extract_user', return_value=('user-1', 'user@example.com')):
            with patch.object(self.module, '_require_owner_file', return_value=(file_item, None)):
                with patch.object(self.module, 's3', s3_mock):
                    with patch.object(self.module, 'table', table_mock):
                        result = self.module.handler(event, None)

        self.assertEqual(result['statusCode'], 200)
        body = json_body(result)
        self.assertEqual(body.get('status'), 'ready')
        self.assertEqual(body.get('size'), 42)
        self.assertEqual(body.get('contentType'), 'application/pdf')
        self.assertTrue(table_mock.update_item.called)

    def test_finalize_returns_conflict_when_file_object_is_missing(self):
        s3_mock = _S3UploadStub(object_exists=False)
        event = {
            'requestContext': {
                'routeKey': 'POST /v2/files/{fileId}/finalize',
                'http': {'method': 'POST'},
            },
            'pathParameters': {'fileId': 'file-123'},
            'headers': {},
        }
        file_item = {
            'pk': 'USER#user-1',
            'sk': 'FILE#file-123',
            'fileId': 'file-123',
            'ownerId': 'user-1',
            'filename': 'report.pdf',
            's3Key': 'v2/files/user-1/file-123/report.pdf',
            'status': 'pending',
        }

        with patch.object(self.module, 'extract_user', return_value=('user-1', 'user@example.com')):
            with patch.object(self.module, '_require_owner_file', return_value=(file_item, None)):
                with patch.object(self.module, 's3', s3_mock):
                    result = self.module.handler(event, None)

        self.assertEqual(result['statusCode'], 409)
        self.assertIn('not uploaded yet', json_body(result).get('error', ''))


if __name__ == '__main__':
    unittest.main()
