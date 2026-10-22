from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


def test_home_shows_logo_and_message():
    r = client.get("/")
    assert r.status_code == 200
    assert 'src="/brand/logo/mikeadamsnc.svg"' in r.text
    assert "alt=\"MikeAdamsNC\"" in r.text
    assert "Something new is on the way." in r.text


def test_brand_files_are_served():
    for path in ["/brand/logo/mikeadamsnc.svg", "/brand/icon/icon.svg",
                 "/brand/icon/apple-touch-icon.png", "/favicon.ico"]:
        assert client.get(path).status_code == 200, path


def test_health_for_keep_warm_ping():
    r = client.get("/health")
    assert r.status_code == 200 and r.text == "ok"


def test_no_api_docs_exposed():
    assert client.get("/docs").status_code == 404
