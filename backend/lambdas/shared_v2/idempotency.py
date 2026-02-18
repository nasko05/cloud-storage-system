from botocore.exceptions import ClientError

from common import IDEMPOTENCY_TTL_SECONDS, table, utc_epoch
from keys import idempotency_pk, idempotency_sk


def _get_header(event, name):
    headers = event.get('headers') or {}
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _normalize_response(value):
    if not isinstance(value, dict):
        return None
    out = dict(value)
    try:
        out['statusCode'] = int(out.get('statusCode', 500))
    except Exception:
        out['statusCode'] = 500
    if not isinstance(out.get('headers'), dict):
        out['headers'] = {'Content-Type': 'application/json'}
    if not isinstance(out.get('body'), str):
        out['body'] = '{}'
    return out


def run_idempotent(event, user_id, scope, action_fn):
    idem_key = _get_header(event, 'Idempotency-Key')
    if not idem_key:
        return action_fn()

    pk = idempotency_pk(user_id)
    sk = idempotency_sk(scope, str(idem_key))

    existing = table.get_item(Key={'pk': pk, 'sk': sk}).get('Item')
    now = utc_epoch()
    if existing and int(existing.get('ttl', 0)) > now:
        cached = _normalize_response(existing.get('response'))
        if cached:
            return cached

    result = action_fn()
    normalized = _normalize_response(result)
    if not normalized:
        return result

    item = {
        'pk': pk,
        'sk': sk,
        'itemType': 'IDEMPOTENCY',
        'response': normalized,
        'ttl': now + IDEMPOTENCY_TTL_SECONDS,
    }

    try:
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(pk) AND attribute_not_exists(sk)'
        )
    except ClientError as error:
        code = error.response.get('Error', {}).get('Code')
        if code == 'ConditionalCheckFailedException':
            latest = table.get_item(Key={'pk': pk, 'sk': sk}).get('Item')
            if latest:
                cached = _normalize_response(latest.get('response'))
                if cached:
                    return cached

    return normalized
