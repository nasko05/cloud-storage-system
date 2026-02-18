VALID_SHARE_PERMISSIONS = ('read', 'download', 'edit')


def validate_share_permission(value):
    return value in VALID_SHARE_PERMISSIONS


def can_download(permission):
    return permission in ('download', 'edit')
