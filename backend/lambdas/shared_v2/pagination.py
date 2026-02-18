import base64
import json


def normalize_limit(raw_limit, default=100, max_value=200):
    if raw_limit is None:
        return default
    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        return default
    if value < 1:
        return default
    return min(value, max_value)


def encode_cursor(last_evaluated_key):
    if not last_evaluated_key:
        return None
    raw = json.dumps(last_evaluated_key)
    return base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii')


def decode_cursor(cursor):
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode('ascii')).decode('utf-8')
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        return None
    return None
