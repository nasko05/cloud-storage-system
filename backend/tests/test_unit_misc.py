"""Unit tests for the small pure helper modules."""

from datetime import UTC, datetime, timedelta

import pytest

from app import pagination, permissions, principals, storage, utils, validation
from app.blob_links import build_download_url, build_upload_url
from app.config import Settings
from app.errors import ApiError
from app.security import verify_signed_token

# --- pagination -------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [(None, 100), ("abc", 100), ("0", 100), ("5", 5), ("999", 200)])
def test_normalize_limit(raw, expected):
    assert pagination.normalize_limit(raw, default=100, max_value=200) == expected


def test_cursor_round_trip_and_bad_input():
    assert pagination.decode_cursor(None) == 0
    assert pagination.decode_cursor("!!!not-base64") == 0
    encoded = pagination.encode_cursor(42)
    assert pagination.decode_cursor(encoded) == 42


# --- permissions ------------------------------------------------------------

def test_permissions():
    assert permissions.is_valid_permission("read")
    assert not permissions.is_valid_permission("admin")
    assert permissions.can_download("download")
    assert permissions.can_download("edit")
    assert not permissions.can_download("read")


# --- principals -------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("email:a@b.com", ("email", "a@b.com")),
    ("user_sub:abc", ("user_sub", "abc")),
    ("a@b.com", ("email", "a@b.com")),
    ("plain-id", ("user_sub", "plain-id")),
    ("", (None, None)),
    ("   ", (None, None)),
    ("bogus:val", (None, None)),
    ("email:", (None, None)),
])
def test_parse_principal(value, expected):
    assert principals.parse_principal_path(value) == expected


# --- validation -------------------------------------------------------------

@pytest.mark.parametrize("name,ok", [
    ("good.txt", True), ("", False), ("   ", False), ("a/b", False),
    ("..", False), ("a\\b", False), ("a\x00b", False), (123, False), ("x" * 300, False),
])
def test_is_valid_name(name, ok):
    assert validation.is_valid_name(name) is ok


def test_normalize_folder_id():
    assert validation.normalize_folder_id(None) == "root"
    assert validation.normalize_folder_id("  ") == "root"
    assert validation.normalize_folder_id(" abc ") == "abc"


# --- utils ------------------------------------------------------------------

def test_iso_and_active():
    assert utils.iso(None) is None
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    assert utils.iso(aware) == "2026-01-01T00:00:00Z"
    naive = datetime(2026, 1, 1)
    assert utils.iso(naive).endswith("Z")

    assert utils.is_active(None) is True
    assert utils.is_active(utils.now_utc() + timedelta(hours=1)) is True
    assert utils.is_active(utils.now_utc() - timedelta(hours=1)) is False
    assert utils.is_active(datetime.now(UTC) + timedelta(hours=1)) is True


# --- storage ----------------------------------------------------------------

def test_storage_keys_and_traversal():
    assert storage.file_key("u", "f", "n.txt") == "v2/files/u/f/n.txt"
    assert storage.archive_key("u", "j") == "v2/zips/u/j.zip"
    with pytest.raises(ValueError):
        storage.resolve("../../etc/passwd")


def test_storage_write_read_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    path = storage.open_write("v2/files/u/f/x.bin")
    path.write_bytes(b"data")
    assert storage.exists("v2/files/u/f/x.bin")
    assert storage.size("v2/files/u/f/x.bin") == 4
    with storage.open_read("v2/files/u/f/x.bin") as handle:
        assert handle.read() == b"data"
    storage.delete("v2/files/u/f/x.bin")
    assert not storage.exists("v2/files/u/f/x.bin")
    storage.delete("v2/files/u/f/missing.bin")  # no error


# --- blob_links -------------------------------------------------------------

class _FakeRequest:
    def __init__(self, base):
        self.base_url = base


def test_blob_links_produce_verifiable_tokens():
    req = _FakeRequest("http://host/")
    up = build_upload_url(req, "v2/files/u/f/x")
    assert up.startswith("http://host/v2/blob/upload?token=")
    up_payload = verify_signed_token(up.split("token=", 1)[1])
    assert up_payload["action"] == "upload" and up_payload["key"] == "v2/files/u/f/x"

    down = build_download_url(req, "v2/files/u/f/x", "x.txt")
    payload = verify_signed_token(down.split("token=", 1)[1])
    assert payload["action"] == "download" and payload["filename"] == "x.txt"


# --- errors -----------------------------------------------------------------

def test_api_error_response():
    resp = ApiError(404, "nope", hint="try again").to_response()
    assert resp.status_code == 404


# --- config -----------------------------------------------------------------

def test_cors_origins_split():
    s = Settings(secret_key="x", cors_allow_origins="https://a.com, https://b.com")
    assert s.cors_allow_origins == ["https://a.com", "https://b.com"]
    s2 = Settings(secret_key="x", cors_allow_origins=["https://c.com"])
    assert s2.cors_allow_origins == ["https://c.com"]
