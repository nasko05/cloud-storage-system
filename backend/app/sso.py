"""Single sign-on cookie helpers.

The access token issued at login is also written to a cookie so a co-hosted
sibling app (the space-io editor on ``personal-area.<domain>``) recognises the
same session. The cookie carries the *same* JWT returned in the JSON body —
the editor verifies it with the shared ``secret_key`` — so there is no second
token format to maintain.

The cookie is ``HttpOnly`` (JS never needs it; only the backends read it) and,
when ``sso_cookie_domain`` is set to the registrable parent domain, is shared
across every subdomain under it.
"""

from __future__ import annotations

from fastapi import Response

from .config import settings


def set_sso_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.sso_cookie_name,
        value=token,
        max_age=settings.access_token_expiry_minutes * 60,
        domain=settings.sso_cookie_domain or None,
        secure=settings.sso_cookie_secure,
        httponly=True,
        samesite=settings.sso_cookie_samesite,
        path="/",
    )


def clear_sso_cookie(response: Response) -> None:
    # Domain/path must match the original for the browser to actually drop it.
    response.delete_cookie(
        key=settings.sso_cookie_name,
        domain=settings.sso_cookie_domain or None,
        path="/",
    )
