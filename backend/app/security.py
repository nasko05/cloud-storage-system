"""Password hashing, JWT access tokens and HMAC-signed blob URLs.

No third-party crypto beyond PyJWT: password hashing uses PBKDF2-HMAC-SHA256
from the standard library, and signed blob URLs use ``hmac``/``hashlib``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

import jwt

from .config import settings

_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_JWT_ALGORITHM = "HS256"


# --- Password hashing -------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, settings.pbkdf2_iterations
    )
    return f"{_PBKDF2_ALGORITHM}${settings.pbkdf2_iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != _PBKDF2_ALGORITHM:
            return False
        salt = bytes.fromhex(salt_hex)
        computed = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(computed.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# --- JWT access tokens ------------------------------------------------------

def create_access_token(user_id: str, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + settings.access_token_expiry_minutes * 60,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# --- HMAC-signed blob URLs (replacement for S3 presigned URLs) --------------

def create_signed_token(payload: dict, expires_in: int | None = None) -> str:
    ttl = settings.signed_url_expiry_seconds if expires_in is None else expires_in
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = _sign(encoded)
    return f"{encoded.decode('ascii')}.{signature}"


def verify_signed_token(token: str) -> dict | None:
    try:
        encoded, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(encoded.encode("ascii"))):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def _sign(encoded: bytes) -> str:
    digest = hmac.new(settings.secret_key.encode("utf-8"), encoded, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
