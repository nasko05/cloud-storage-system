import json
import time
from boto3.dynamodb.conditions import Key
from common import s3, table, BUCKET, EXPIRY, response


def handler(event, context):
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
        user_id = claims.get('sub')

        if not user_id:
            return response(401, {'error': 'Unauthorized'})

        body = json.loads(event.get('body') or '{}')
        file_id = body.get('fileId')

        if not file_id:
            return response(400, {'error': 'fileId required'})

        # Find file by fileId
        result = table.query(
            IndexName='GSI1',
            KeyConditionExpression=Key('gsi1pk').eq(f'FILE#{file_id}') & Key('gsi1sk').eq(f'FILE#{file_id}')
        )

        items = result.get('Items', [])
        if not items:
            return response(404, {'error': 'File not found'})

        file = items[0]
        is_owner = file.get('ownerId') == user_id
        is_shared = False
        share_info = None

        # Check share access if not owner
        if not is_owner:
            share_result = table.get_item(
                Key={'pk': f'SHARED#{user_id}', 'sk': f'FILE#{file_id}'}
            )
            share = share_result.get('Item')
            if share:
                now = int(time.time())
                ttl = share.get('ttl')
                if not ttl or ttl > now:
                    is_shared = True
                    share_info = {
                        'sharedBy': share.get('sharedBy'),
                        'permission': share.get('permission'),
                        'expiresAt': share.get('expiresAt')
                    }

        if not is_owner and not is_shared:
            print(json.dumps({
                'action': 'download-denied',
                'userId': user_id,
                'fileId': file_id,
                'ownerId': file.get('ownerId')
            }))
            return response(403, {'error': 'Access denied'})

        # Verify file exists in S3
        try:
            s3.head_object(Bucket=BUCKET, Key=file['s3Key'])
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                return response(404, {'error': 'File not found in storage'})
            raise

        # Generate presigned download URL
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BUCKET,
                'Key': file['s3Key'],
                'ResponseContentDisposition': f'attachment; filename="{file["filename"]}"'
            },
            ExpiresIn=EXPIRY
        )

        print(json.dumps({
            'action': 'download',
            'userId': user_id,
            'fileId': file_id,
            'isOwner': is_owner,
            'isShared': is_shared
        }))

        result = {
            'downloadUrl': download_url,
            'filename': file['filename'],
            'contentType': file['contentType'],
            'size': file['size'],
            'expiresIn': EXPIRY,
            'accessType': 'owner' if is_owner else 'shared'
        }
        if share_info:
            result['shareInfo'] = share_info
        return response(200, result)

    except Exception as e:
        print(f'Download error: {e}')
        return response(500, {'error': 'Internal server error'})
