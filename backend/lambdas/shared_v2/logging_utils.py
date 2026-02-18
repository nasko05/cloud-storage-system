import json


def correlation_id_from_event(event):
    headers = event.get('headers') or {}
    for key, value in headers.items():
        if key.lower() == 'x-correlation-id' and value:
            return str(value)
    return (
        event.get('requestContext', {})
        .get('requestId')
        or event.get('requestContext', {}).get('http', {}).get('requestId')
        or 'unknown'
    )


def log(level, message, correlation_id='unknown', **fields):
    payload = {
        'level': level,
        'message': message,
        'correlationId': correlation_id,
    }
    if fields:
        payload.update(fields)
    print(json.dumps(payload))
