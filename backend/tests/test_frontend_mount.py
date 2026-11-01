from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


def make_dist(path):
    (path / "assets").mkdir()
    (path / "index.html").write_text("<html>panel</html>", encoding="utf-8")
    (path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (path / "logo.svg").write_text("<svg/>", encoding="utf-8")
    return path


def test_serves_index_assets_files_and_the_page_fallback(tmp_path):
    application = FastAPI()
    assert mount_frontend(application, make_dist(tmp_path)) is True
    client = TestClient(application)
    assert "panel" in client.get("/").text
    assert client.get("/assets/app.js").text.startswith("console")
    assert "<svg" in client.get("/logo.svg").text
    assert "panel" in client.get("/some/page").text
    assert client.get("/api/unknown").status_code == 404


def test_nothing_is_mounted_without_a_build(tmp_path):
    assert mount_frontend(FastAPI(), tmp_path) is False