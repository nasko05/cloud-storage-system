from conftest import auth_header, register_and_login


def test_register_login_and_authenticated_access(client):
    token, user_id, _ = register_and_login(client)
    assert token and user_id

    resp = client.get("/v2/folders/root/children", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "nextCursor": None}


def test_duplicate_registration_rejected(client):
    client.post("/v2/auth/register", json={"email": "dup@example.com", "password": "password123"})
    resp = client.post("/v2/auth/register", json={"email": "dup@example.com", "password": "password123"})
    assert resp.status_code == 409


def test_login_wrong_password(client):
    client.post("/v2/auth/register", json={"email": "x@example.com", "password": "password123"})
    resp = client.post("/v2/auth/login", json={"email": "x@example.com", "password": "wrongpass1"})
    assert resp.status_code == 401


def test_missing_token_is_unauthorized(client):
    assert client.get("/v2/folders/root/children").status_code == 401


def test_short_password_is_rejected(client):
    resp = client.post("/v2/auth/register", json={"email": "s@example.com", "password": "short"})
    assert resp.status_code == 400
