"""End-to-end passkey tests driven by a software authenticator.

``soft_webauthn`` performs real attestation/assertion crypto, so these exercise
the full ceremony through the four endpoints (not mocked verification). The two
helpers below translate between the byte-shaped objects ``soft_webauthn`` speaks
and the base64url JSON the browser (and our endpoints) exchange.
"""

from __future__ import annotations

import base64

from conftest import auth_header, register_and_login
from soft_webauthn import SoftWebauthnDevice

from app.ratelimit import login_rate_limiter
from app.security import create_signed_token

ORIGIN = "http://localhost:5173"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _options_to_device(options: dict) -> dict:
    """Turn the endpoint's JSON options into the byte form soft_webauthn wants."""
    pk = dict(options)
    pk["challenge"] = _b64decode(pk["challenge"])
    if "user" in pk:
        pk = {**pk, "user": {**pk["user"], "id": _b64decode(pk["user"]["id"])}}
    return {"publicKey": pk}


def _attestation_to_json(att: dict) -> dict:
    return {
        "id": att["id"].rstrip(b"=").decode("ascii"),
        "rawId": _b64(att["rawId"]),
        "response": {
            "clientDataJSON": _b64(att["response"]["clientDataJSON"]),
            "attestationObject": _b64(att["response"]["attestationObject"]),
            "transports": ["internal"],
        },
        "type": att["type"],
        "clientExtensionResults": {},
    }


def _assertion_to_json(assn: dict) -> dict:
    return {
        "id": assn["id"].rstrip(b"=").decode("ascii"),
        "rawId": _b64(assn["rawId"]),
        "response": {
            "authenticatorData": _b64(assn["response"]["authenticatorData"]),
            "clientDataJSON": _b64(assn["response"]["clientDataJSON"]),
            "signature": _b64(assn["response"]["signature"]),
            "userHandle": _b64(assn["response"]["userHandle"]),
        },
        "type": assn["type"],
        "clientExtensionResults": {},
    }


def _register_passkey(client, token, device: SoftWebauthnDevice, name: str | None = None):
    opts = client.post("/v2/auth/passkey/register/options", headers=auth_header(token)).json()
    att = device.create(_options_to_device(opts["options"]), ORIGIN)
    return client.post(
        "/v2/auth/passkey/register/verify",
        json={
            "credential": _attestation_to_json(att),
            "challengeToken": opts["challengeToken"],
            "name": name,
        },
        headers=auth_header(token),
    )


def _login_passkey(client, device: SoftWebauthnDevice):
    opts = client.post("/v2/auth/passkey/login/options").json()
    assn = device.get(_options_to_device(opts["options"]), ORIGIN)
    return client.post(
        "/v2/auth/passkey/login/verify",
        json={"credential": _assertion_to_json(assn), "challengeToken": opts["challengeToken"]},
    )


def setup_function() -> None:
    login_rate_limiter.reset()


def test_register_options_requires_auth(client):
    assert client.post("/v2/auth/passkey/register/options").status_code == 401


def test_full_passkey_flow(client):
    token, user_id, email = register_and_login(client)
    device = SoftWebauthnDevice()

    reg = _register_passkey(client, token, device, name="My Laptop")
    assert reg.status_code == 201, reg.text
    assert reg.json()["registered"] is True

    login = _login_passkey(client, device)
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["userId"] == user_id
    assert body["email"] == email

    # The minted token is a real access token usable on protected endpoints.
    resp = client.get("/v2/folders/root/children", headers=auth_header(body["token"]))
    assert resp.status_code == 200


def test_invalid_challenge_token_rejected(client):
    token, _, _ = register_and_login(client)
    device = SoftWebauthnDevice()
    opts = client.post("/v2/auth/passkey/register/options", headers=auth_header(token)).json()
    att = device.create(_options_to_device(opts["options"]), ORIGIN)
    resp = client.post(
        "/v2/auth/passkey/register/verify",
        json={"credential": _attestation_to_json(att), "challengeToken": "not-a-real-token"},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_register_rejects_token_for_other_user(client):
    token_a, _, _ = register_and_login(client)
    _, user_b_id, _ = register_and_login(client)
    device = SoftWebauthnDevice()
    opts = client.post("/v2/auth/passkey/register/options", headers=auth_header(token_a)).json()
    att = device.create(_options_to_device(opts["options"]), ORIGIN)
    # A challenge token minted for a different user must not be accepted.
    forged = create_signed_token(
        {"ch": opts["options"]["challenge"], "uid": user_b_id, "typ": "reg"}, expires_in=300
    )
    resp = client.post(
        "/v2/auth/passkey/register/verify",
        json={"credential": _attestation_to_json(att), "challengeToken": forged},
        headers=auth_header(token_a),
    )
    assert resp.status_code == 400


def test_multiple_passkeys_per_user(client):
    token, user_id, _ = register_and_login(client)
    dev1, dev2 = SoftWebauthnDevice(), SoftWebauthnDevice()
    assert _register_passkey(client, token, dev1).status_code == 201
    assert _register_passkey(client, token, dev2).status_code == 201

    assert _login_passkey(client, dev1).json()["userId"] == user_id
    assert _login_passkey(client, dev2).json()["userId"] == user_id


def test_unknown_credential_rejected(client):
    register_and_login(client)
    # A device that was never registered cannot log in.
    stranger = SoftWebauthnDevice()
    stranger.cred_init("localhost", b"ghost")
    resp = _login_passkey(client, stranger)
    assert resp.status_code == 401


def test_replayed_assertion_rejected(client):
    token, _, _ = register_and_login(client)
    device = SoftWebauthnDevice()
    _register_passkey(client, token, device)

    opts = client.post("/v2/auth/passkey/login/options").json()
    assn = device.get(_options_to_device(opts["options"]), ORIGIN)
    payload = {"credential": _assertion_to_json(assn), "challengeToken": opts["challengeToken"]}

    first = client.post("/v2/auth/passkey/login/verify", json=payload)
    assert first.status_code == 200
    # Replaying the same assertion fails the sign-count (clone) check.
    replay = client.post("/v2/auth/passkey/login/verify", json=payload)
    assert replay.status_code == 401
