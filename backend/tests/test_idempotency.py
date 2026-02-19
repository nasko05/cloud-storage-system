import unittest
from botocore.exceptions import ClientError
from unittest.mock import patch

from lambda_test_utils import load_shared_module


class _InMemoryTable:
    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        return {'Item': self.items.get((Key['pk'], Key['sk']))}

    def put_item(self, Item, ConditionExpression=None):
        key = (Item['pk'], Item['sk'])
        if ConditionExpression and key in self.items:
            raise ClientError(
                {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'Already exists'}},
                'PutItem',
            )
        self.items[key] = Item
        return {}


class IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.module = load_shared_module('idempotency')

    def test_replays_cached_response_for_same_idempotency_key(self):
        table = _InMemoryTable()
        counter = {'calls': 0}
        event = {'headers': {'Idempotency-Key': 'abc-123'}}

        def action():
            counter['calls'] += 1
            return {
                'statusCode': 201,
                'headers': {'Content-Type': 'application/json'},
                'body': '{"ok": true}',
            }

        with patch.object(self.module, 'table', table):
            with patch.object(self.module, 'utc_epoch', return_value=1000):
                first = self.module.run_idempotent(event, 'user-1', 'create-file', action)
            with patch.object(self.module, 'utc_epoch', return_value=1001):
                second = self.module.run_idempotent(event, 'user-1', 'create-file', action)

        self.assertEqual(counter['calls'], 1)
        self.assertEqual(first['statusCode'], 201)
        self.assertEqual(second['statusCode'], 201)
        self.assertEqual(first['body'], second['body'])

    def test_without_idempotency_header_executes_action_each_time(self):
        event = {'headers': {}}
        counter = {'calls': 0}

        def action():
            counter['calls'] += 1
            return {'statusCode': 200, 'headers': {'Content-Type': 'application/json'}, 'body': '{}'}

        first = self.module.run_idempotent(event, 'user-1', 'any-scope', action)
        second = self.module.run_idempotent(event, 'user-1', 'any-scope', action)

        self.assertEqual(first['statusCode'], 200)
        self.assertEqual(second['statusCode'], 200)
        self.assertEqual(counter['calls'], 2)


if __name__ == '__main__':
    unittest.main()
