"""Share principal parsing (email vs. Cognito-style user sub)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .deps import CurrentUser

PrincipalType = str  # "email" | "user_sub"
_VALID_TYPES = ("email", "user_sub")


def _infer_principal_type(value: str) -> PrincipalType:
    return "email" if "@" in value else "user_sub"


def user_principals(user: CurrentUser) -> list[tuple[str, str]]:
    """The share principals the current user matches: their stable id, plus
    their email when it differs. The single definition of that rule, shared by
    the download check and the inbound-shares listing."""
    principals = [("user_sub", user.id)]
    if user.email and user.email != user.id:
        principals.append(("email", user.email))
    return principals


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
    return _infer_principal_type(raw), raw
