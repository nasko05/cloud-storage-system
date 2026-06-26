"""Passkey (WebAuthn/FIDO2) registration and usernameless login.

Two ceremonies, each split into an ``/options`` call (server issues a challenge)
and a ``/verify`` call (server checks the authenticator's response). The
challenge is carried between the two calls in a short-lived HMAC-signed token
(``create_signed_token``) rather than server-side state, so no new storage is
needed and the flow survives restarts and multiple workers.

A successful login assertion ends by minting the *same* access token as the
password login (``create_access_token``), so everything downstream of auth is
unchanged.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..config import settings
from ..deps import CurrentUser, get_current_user, get_db
from ..errors import ApiError
from ..models import User, WebAuthnCredential
from ..ratelimit import login_rate_limiter
from ..schemas import PasskeyLoginVerifyRequest, PasskeyRegisterVerifyRequest
from ..security import (
    create_access_token,
    create_signed_token,
    verify_signed_token,
)
from ..sso import set_sso_cookie
from ..utils import now_utc

router = APIRouter(prefix="/v2/auth/passkey", tags=["auth"])

# Challenge tokens are valid for five minutes — long enough for the user to
# complete the OS/browser prompt, short enough to limit replay.
_CHALLENGE_TTL = 300


def _resolve_rp(request: Request) -> tuple[str, list[str]]:
    """Determine the WebAuthn RP ID and acceptable origin(s) for this request.

    Explicit config wins (for split-domain / proxy deployments). Otherwise both
    are derived from the browser's ``Origin`` (falling back to ``Referer``)
    header so passkeys work on whatever domain the app is served from without
    any configuration. The final fallback keeps non-browser callers (tests)
    working.
    """
    if settings.webauthn_rp_id:
        origins = list(settings.webauthn_origin)
        return settings.webauthn_rp_id, origins

    for header in ("origin", "referer"):
        value = request.headers.get(header)
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme and parsed.hostname:
            return parsed.hostname, [f"{parsed.scheme}://{parsed.netloc}"]

    return "localhost", ["http://localhost:5173"]


def _user_credentials(db: Session, user_id: str) -> list[WebAuthnCredential]:
    stmt = select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    return list(db.execute(stmt).scalars().all())


def _options_json(options) -> dict:
    return json.loads(options_to_json(options))


@router.post("/register/options")
def register_options(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    rp_id, _ = _resolve_rp(request)
    existing = _user_credentials(db, user.id)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user.id.encode("utf-8"),
        user_name=user.email,
        user_display_name=user.email,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in existing
        ],
        # Discoverable credential so the user can later sign in without typing
        # their email (usernameless / one-tap login).
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    challenge_token = create_signed_token(
        {"ch": bytes_to_base64url(options.challenge), "uid": user.id, "typ": "reg"},
        expires_in=_CHALLENGE_TTL,
    )
    return {"options": _options_json(options), "challengeToken": challenge_token}


@router.post("/register/verify", status_code=201)
def register_verify(
    payload: PasskeyRegisterVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    claims = verify_signed_token(payload.challengeToken)
    if not claims or claims.get("typ") != "reg" or claims.get("uid") != user.id:
        raise ApiError(400, "Invalid or expired challenge")

    rp_id, origins = _resolve_rp(request)
    try:
        verification = verify_registration_response(
            credential=json.dumps(payload.credential),
            expected_challenge=base64url_to_bytes(claims["ch"]),
            expected_rp_id=rp_id,
            expected_origin=origins,
            require_user_verification=False,
        )
    except (InvalidRegistrationResponse, ValueError) as exc:
        raise ApiError(400, f"Passkey registration failed: {exc}") from exc

    credential_id = bytes_to_base64url(verification.credential_id)
    already = db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == credential_id
        )
    ).scalars().first()
    if already is not None:
        raise ApiError(409, "This passkey is already registered")

    transports = payload.credential.get("response", {}).get("transports") or []
    cred = WebAuthnCredential(
        credential_id=credential_id,
        public_key=bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        transports=transports,
        user_id=user.id,
        name=payload.name,
    )
    db.add(cred)
    db.flush()
    return {"registered": True, "credentialId": cred.id}


@router.post("/login/options")
def login_options(request: Request, db: Session = Depends(get_db)) -> dict:
    client_ip = request.client.host if request.client else None
    locked_for = login_rate_limiter.check_locked("passkey", client_ip)
    if locked_for:
        raise ApiError(429, f"Too many attempts. Try again in {locked_for} seconds.")

    rp_id, _ = _resolve_rp(request)
    # Empty allow_credentials => the browser offers any discoverable credential
    # for this RP (usernameless login).
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_token = create_signed_token(
        {"ch": bytes_to_base64url(options.challenge), "typ": "auth"},
        expires_in=_CHALLENGE_TTL,
    )
    return {"options": _options_json(options), "challengeToken": challenge_token}


@router.post("/login/verify")
def login_verify(
    payload: PasskeyLoginVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    client_ip = request.client.host if request.client else None
    claims = verify_signed_token(payload.challengeToken)
    if not claims or claims.get("typ") != "auth":
        raise ApiError(400, "Invalid or expired challenge")

    raw_id = payload.credential.get("id")
    if not isinstance(raw_id, str):
        raise ApiError(400, "Malformed passkey assertion")

    cred = db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == raw_id
        )
    ).scalars().first()
    if cred is None:
        login_rate_limiter.register_failure("passkey", client_ip)
        raise ApiError(401, "Passkey not recognized")

    rp_id, origins = _resolve_rp(request)
    try:
        verification = verify_authentication_response(
            credential=json.dumps(payload.credential),
            expected_challenge=base64url_to_bytes(claims["ch"]),
            expected_rp_id=rp_id,
            expected_origin=origins,
            credential_public_key=base64url_to_bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=False,
        )
    except (InvalidAuthenticationResponse, ValueError) as exc:
        login_rate_limiter.register_failure("passkey", client_ip)
        raise ApiError(401, f"Passkey authentication failed: {exc}") from exc

    user = db.get(User, cred.user_id)
    if user is None:
        raise ApiError(401, "Passkey authentication failed")

    cred.sign_count = verification.new_sign_count
    cred.last_used_at = now_utc()
    db.flush()
    login_rate_limiter.register_success("passkey", client_ip)
    token = create_access_token(user.id, user.email)
    set_sso_cookie(response, token)
    return {
        "token": token,
        "userId": user.id,
        "email": user.email,
    }
