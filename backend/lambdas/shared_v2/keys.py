import hashlib


def user_pk(user_id):
    return f'USER#{user_id}'


def file_sk(file_id):
    return f'FILE#{file_id}'


def folder_sk(folder_id):
    return f'FOLDER#{folder_id}'


def file_entity_pk(file_id):
    return f'FILE#{file_id}'


def share_sk(principal_type, principal_value):
    return f'SHARE#{principal_type}#{principal_value}'


def public_link_sk(token):
    return f'PUBLIC_LINK#{token}'


def archive_job_sk(job_id):
    return f'ARCHIVE_JOB#{job_id}'


def owner_parent_gsi_pk(owner_id, parent_folder_id):
    return f'OWNER#{owner_id}#PARENT#{parent_folder_id}'


def owner_parent_gsi_sk(item_type, name, item_id):
    # NAME segment is lower-cased for stable conflict checks.
    safe_name = (name or '').strip().lower()
    return f'TYPE#{item_type}#NAME#{safe_name}#ID#{item_id}'


def reverse_file_gsi_pk(file_id):
    return f'FILE#{file_id}'


def reverse_folder_gsi_pk(folder_id):
    return f'FOLDER#{folder_id}'


def inbound_principal_gsi_pk(principal_type, principal_value):
    return f'PRINCIPAL#{principal_type}#{principal_value}'


def inbound_principal_gsi_sk(file_id):
    return f'FILE#{file_id}'


def public_token_gsi_pk(token):
    return f'TOKEN#{token}'


def public_token_gsi_sk(file_id):
    return f'FILE#{file_id}'


def idempotency_pk(user_id):
    return f'IDEMP#{user_id}'


def idempotency_sk(scope, idempotency_key):
    digest = hashlib.sha256(f'{scope}:{idempotency_key}'.encode('utf-8')).hexdigest()
    return f'REQ#{scope}#{digest}'
