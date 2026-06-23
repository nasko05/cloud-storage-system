import sys
import types

import pytest

from app import antivirus
from app.config import settings


def _fake_clamd(result=None, raise_exc=None):
    mod = types.ModuleType("clamd")

    class ClamdNetworkSocket:
        def __init__(self, host=None, port=None):
            pass

        def instream(self, handle):
            if raise_exc:
                raise raise_exc
            return result

    mod.ClamdNetworkSocket = ClamdNetworkSocket
    return mod


def test_disabled_is_noop(tmp_path):
    assert settings.clamav_enabled is False
    f = tmp_path / "x"
    f.write_bytes(b"data")
    assert antivirus.scan_file(f) == (True, None)


def test_clean_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clamav_enabled", True)
    monkeypatch.setitem(sys.modules, "clamd", _fake_clamd(result={"stream": ("OK", None)}))
    f = tmp_path / "x"
    f.write_bytes(b"data")
    assert antivirus.scan_file(f) == (True, None)


def test_infected_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clamav_enabled", True)
    monkeypatch.setitem(sys.modules, "clamd", _fake_clamd(result={"stream": ("FOUND", "Eicar")}))
    f = tmp_path / "x"
    f.write_bytes(b"data")
    assert antivirus.scan_file(f) == (False, "Eicar")


def test_missing_dependency_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clamav_enabled", True)
    monkeypatch.setitem(sys.modules, "clamd", None)  # forces ImportError
    f = tmp_path / "x"
    f.write_bytes(b"data")
    with pytest.raises(antivirus.ScanError):
        antivirus.scan_file(f)


def test_daemon_error_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clamav_enabled", True)
    monkeypatch.setitem(sys.modules, "clamd", _fake_clamd(raise_exc=ConnectionError("down")))
    f = tmp_path / "x"
    f.write_bytes(b"data")
    with pytest.raises(antivirus.ScanError):
        antivirus.scan_file(f)


def test_unexpected_result_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clamav_enabled", True)
    monkeypatch.setitem(sys.modules, "clamd", _fake_clamd(result={"stream": ("HUH", None)}))
    f = tmp_path / "x"
    f.write_bytes(b"data")
    with pytest.raises(antivirus.ScanError):
        antivirus.scan_file(f)
