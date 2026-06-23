"""Share principal parsing (email vs. Cognito-style user sub)."""

from __future__ import annotations

PrincipalType = str  # "email" | "user_sub"
_VALID_TYPES = ("email", "user_sub")


def infer_principal_type(value: str) -> PrincipalType:
    return "email" if "@" in value else "user_sub"


def parse_principal_path(value: str | None) -> tuple[str | None, str | None]:
    """Parse a ``principal`` path segment.

    Accepts ``email:user@example.com``, ``user_sub:<uuid>`` or a bare value
    (type inferred from the presence of ``@``).
    """
    if not value:
        return None, None
    if ":" in value:
        ptype, _, pvalue = value.partition(":")
        ptype, pvalue = ptype.strip(), pvalue.strip()
        if ptype not in _VALID_TYPES or not pvalue:
            return None, None
        return ptype, pvalue

    raw = value.strip()
    if not raw:
        return None, None
    return infer_principal_type(raw), raw
