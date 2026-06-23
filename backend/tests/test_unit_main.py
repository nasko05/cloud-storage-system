from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import main as main_mod
from app.config import settings
from app.errors import ApiError, api_error_handler


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_mount_frontend_serves_spa(tmp_path, monkeypatch):
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>app shell</html>")
    monkeypatch.setattr(settings, "frontend_dir", tmp_path)

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    main_mod.mount_frontend(app)
    c = TestClient(app)

    assert "<html>app shell</html>" in c.get("/").text          # index at root
    assert "<html>app shell</html>" in c.get("/s/token").text   # SPA fallback
    assert c.get("/static/app.js").status_code == 200           # real asset
    assert c.get("/v2/unknown").status_code == 404              # API prefix -> 404
