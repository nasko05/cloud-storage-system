from boto3.dynamodb.conditions import Key

from common import table
from keys import public_token_gsi_pk, reverse_file_gsi_pk, reverse_folder_gsi_pk


def query_all(**kwargs):
    items = []
    req = dict(kwargs)
    while True:
        result = table.query(**req)
        items.extend(result.get('Items', []))
        last = result.get('LastEvaluatedKey')
        if not last:
            break
        req['ExclusiveStartKey'] = last
    return items


def get_file_by_id(file_id):
    result = table.query(
        IndexName='GSI2',
        KeyConditionExpression=Key('gsi2pk').eq(reverse_file_gsi_pk(file_id)) & Key('gsi2sk').eq('FILE')
    )
    items = result.get('Items', [])
    return items[0] if items else None


def get_folder_by_id(folder_id):
    result = table.query(
        IndexName='GSI2',
        KeyConditionExpression=Key('gsi2pk').eq(reverse_folder_gsi_pk(folder_id)) & Key('gsi2sk').eq('FOLDER')
    )
    items = result.get('Items', [])
    return items[0] if items else None


def get_public_link_by_token(token):
    result = table.query(
        IndexName='GSI4',
        KeyConditionExpression=Key('gsi4pk').eq(public_token_gsi_pk(token))
    )
    items = [item for item in result.get('Items', []) if item.get('itemType') == 'PUBLIC_LINK']
    return items[0] if items else None
