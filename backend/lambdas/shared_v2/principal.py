
def infer_principal_type(value):
    if '@' in value:
        return 'email'
    return 'user_sub'


def parse_principal_path(value):
    """
    Accepts:
    - "email:user@example.com"
    - "user_sub:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    - legacy fallback without prefix (infers by '@')
    """
    if not value:
        return None, None
    if ':' in value:
        ptype, pvalue = value.split(':', 1)
        ptype = ptype.strip()
        pvalue = pvalue.strip()
        if ptype not in ('email', 'user_sub') or not pvalue:
            return None, None
        return ptype, pvalue

    raw = value.strip()
    if not raw:
        return None, None
    return infer_principal_type(raw), raw
