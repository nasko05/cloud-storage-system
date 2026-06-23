import time

import jwt
import pytest

from app import security
from app.config import settings


def test_password_hash_round_trip():
    hashed = security.hash_password("s3cret-password")
    assert hashed.startswith("pbkdf2_sha256$")
    assert security.verify_password("s3cret-password", hashed)
    assert not security.verify_password("wrong", hashed)


@pytest.mark.parametrize("stored", [None, "", "notpbkdf2$1$2$3", "bad$format", "scrypt$1$aa$bb"])
def test_verify_password_rejects_bad_inputs(stored):
    assert security.verify_password("x", stored) is False


def test_access_token_round_trip():
    token = security.create_access_token("user-1", "u@example.com")
    claims = security.decode_access_token(token)
    assert claims["sub"] == "user-1"
    assert claims["email"] == "u@example.com"


def test_decode_rejects_tampered_or_expired():
    assert security.decode_access_token("not-a-jwt") is None
    expired = jwt.encode(
        {"sub": "u", "exp": int(time.time()) - 10}, settings.secret_key, algorithm="HS256"
    )
    assert security.decode_access_token(expired) is None
    wrong_sig = jwt.encode({"sub": "u"}, "other-secret", algorithm="HS256")
    assert security.decode_access_token(wrong_sig) is None


def test_signed_token_round_trip_and_tamper():
    token = security.create_signed_token({"action": "download", "key": "k"}, expires_in=60)
    payload = security.verify_signed_token(token)
    assert payload["action"] == "download" and payload["key"] == "k"

    encoded, sig = token.split(".", 1)
    assert security.verify_signed_token(f"{encoded}.{sig}x") is None
    assert security.verify_signed_token("no-dot") is None
    assert security.verify_signed_token(f"!!!.{sig}") is None


def test_signed_token_expiry():
    token = security.create_signed_token({"action": "upload", "key": "k"}, expires_in=-1)
    assert security.verify_signed_token(token) is None
