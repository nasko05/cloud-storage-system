import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from lambda_test_utils import json_body, load_lambda_handler


class _S3Stub:
    class _ClientError(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {'Error': {'Code': code}}

    exceptions = SimpleNamespace(ClientError=_ClientError)

    def head_object(self, **kwargs):
        return {}

    def generate_presigned_url(self, *args, **kwargs):
        return 'https://example.com/download'


class V2DownloadPermissionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_lambda_handler('v2_download')
        self.event = {
            'requestContext': {
                'routeKey': 'POST /v2/download/files/{fileId}',
                'http': {'method': 'POST'},
            },
            'pathParameters': {'fileId': 'file-1'},
        }
        self.file_item = {
            'pk': 'USER#owner-1',
            'sk': 'FILE#file-1',
            'fileId': 'file-1',
            'ownerId': 'owner-1',
            'filename': 'document.txt',
            's3Key': 'v2/files/owner-1/file-1/document.txt',
            'contentType': 'text/plain',
            'size': 12,
            'status': 'ready',
        }

    def test_denies_read_only_share_for_download(self):
        with patch.object(self.module, 'extract_user', return_value=('shared-user', 'shared@example.com')):
            with patch.object(self.module, 'get_file_by_id', return_value=self.file_item):
                with patch.object(self.module, '_find_share', return_value={'permission': 'read'}):
                    result = self.module.handler(self.event, None)

        self.assertEqual(result['statusCode'], 403)
        self.assertIn('Insufficient share permission', json_body(result).get('error', ''))

    def test_allows_download_share_and_returns_url(self):
        table_mock = MagicMock()
        with patch.object(self.module, 'extract_user', return_value=('shared-user', 'shared@example.com')):
            with patch.object(self.module, 'get_file_by_id', return_value=self.file_item):
                with patch.object(self.module, '_find_share', return_value={
                    'permission': 'download',
                    'principalType': 'email',
                    'principalValue': 'shared@example.com',
                    'expiresAt': '2099-01-01T00:00:00Z',
                }):
                    with patch.object(self.module, 's3', _S3Stub()):
                        with patch.object(self.module, 'table', table_mock):
                            result = self.module.handler(self.event, None)

        self.assertEqual(result['statusCode'], 200)
        body = json_body(result)
        self.assertEqual(body.get('accessType'), 'shared')
        self.assertEqual(body.get('downloadUrl'), 'https://example.com/download')
        self.assertEqual(body.get('fileId'), 'file-1')


if __name__ == '__main__':
    unittest.main()
