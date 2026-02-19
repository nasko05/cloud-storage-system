import unittest
from unittest.mock import patch

from lambda_test_utils import json_body, load_lambda_handler


class _TableStub:
    def __init__(self, items):
        self.items = items

    def query(self, **kwargs):
        return {'Items': self.items}


class V2FolderListFlagsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_lambda_handler('v2_folders')

    def test_list_children_exposes_denormalized_file_flags(self):
        table_stub = _TableStub([
            {
                'itemType': 'FILE',
                'fileId': 'file-1',
                'filename': 'shared.txt',
                'parentFolderId': 'root',
                'size': 123,
                'contentType': 'text/plain',
                'status': 'ready',
                'shareCount': 2,
                'publicLinkCount': 1,
                'createdAt': '2026-02-18T00:00:00Z',
                'updatedAt': '2026-02-18T00:00:00Z',
            },
            {
                'itemType': 'FILE',
                'fileId': 'file-2',
                'filename': 'private.txt',
                'parentFolderId': 'root',
                'size': 321,
                'contentType': 'text/plain',
                'status': 'ready',
                'shareCount': 0,
                'publicLinkCount': 0,
                'createdAt': '2026-02-18T00:00:00Z',
                'updatedAt': '2026-02-18T00:00:00Z',
            },
        ])
        event = {'queryStringParameters': {'limit': '200'}}

        with patch.object(self.module, 'table', table_stub):
            with patch.object(self.module, '_folder_exists_for_owner', return_value=True):
                result = self.module._list_children(event, 'user-1', 'root', 'test-corr')

        self.assertEqual(result['statusCode'], 200)
        body = json_body(result)
        self.assertEqual(len(body.get('items', [])), 2)
        first = body['items'][0]
        second = body['items'][1]

        self.assertTrue(first.get('isShared'))
        self.assertTrue(first.get('hasPublicLink'))
        self.assertFalse(second.get('isShared'))
        self.assertFalse(second.get('hasPublicLink'))


if __name__ == '__main__':
    unittest.main()
