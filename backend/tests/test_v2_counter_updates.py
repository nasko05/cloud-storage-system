import json
import unittest
from unittest.mock import MagicMock, patch

from lambda_test_utils import json_body, load_lambda_handler


class V2CounterUpdateTests(unittest.TestCase):
    def test_share_create_increments_file_share_count(self):
        module = load_lambda_handler('v2_shares')
        table_mock = MagicMock()
        table_mock.get_item.return_value = {}
        file_item = {
            'pk': 'USER#owner-1',
            'sk': 'FILE#file-1',
            'fileId': 'file-1',
            'ownerId': 'owner-1',
            'filename': 'report.txt',
            's3Key': 'v2/files/owner-1/file-1/report.txt',
            'contentType': 'text/plain',
            'size': 10,
        }
        event = {
            'requestContext': {
                'routeKey': 'PUT /v2/files/{fileId}/shares/{principal}',
                'http': {'method': 'PUT'},
            },
            'pathParameters': {'fileId': 'file-1', 'principal': 'email:user@example.com'},
            'headers': {},
            'body': json.dumps({'permission': 'download', 'expiryDays': 30}),
        }

        with patch.object(module, 'extract_user', return_value=('owner-1', 'owner@example.com')):
            with patch.object(module, 'get_file_by_id', return_value=file_item):
                with patch.object(module, 'table', table_mock):
                    result = module.handler(event, None)

        self.assertEqual(result['statusCode'], 200)
        self.assertTrue(table_mock.update_item.called)
        update_values = table_mock.update_item.call_args.kwargs['ExpressionAttributeValues']
        self.assertEqual(update_values[':delta'], 1)

    def test_public_link_create_increments_file_public_link_count(self):
        module = load_lambda_handler('v2_public_links_admin')
        table_mock = MagicMock()
        file_item = {
            'pk': 'USER#owner-1',
            'sk': 'FILE#file-1',
            'fileId': 'file-1',
            'ownerId': 'owner-1',
            'filename': 'report.txt',
            's3Key': 'v2/files/owner-1/file-1/report.txt',
            'contentType': 'text/plain',
            'size': 10,
        }
        event = {
            'requestContext': {
                'routeKey': 'POST /v2/files/{fileId}/public-links',
                'http': {'method': 'POST'},
            },
            'pathParameters': {'fileId': 'file-1'},
            'headers': {},
            'body': json.dumps({'expiryDays': 30}),
        }

        with patch.object(module, 'extract_user', return_value=('owner-1', 'owner@example.com')):
            with patch.object(module, 'get_file_by_id', return_value=file_item):
                with patch.object(module, 'table', table_mock):
                    with patch.object(module.uuid, 'uuid4', return_value='token-1'):
                        result = module.handler(event, None)

        self.assertEqual(result['statusCode'], 201)
        body = json_body(result)
        self.assertEqual(body.get('token'), 'token-1')
        self.assertTrue(table_mock.update_item.called)
        update_values = table_mock.update_item.call_args.kwargs['ExpressionAttributeValues']
        self.assertEqual(update_values[':delta'], 1)


if __name__ == '__main__':
    unittest.main()
