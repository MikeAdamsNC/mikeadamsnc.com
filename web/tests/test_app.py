import time

import pytest
from markupsafe import escape
from fastapi.testclient import TestClient

from web import app as site
from web import auth, content

BROWSER = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit Safari/604.1"}


@pytest.fixture
def client(monkeypatch):
    site.store.__init__()
    site.recorder.__init__()
    return TestClient(site.app, headers=BROWSER)


def views(path=None):
    return [r for r in site.recorder.rows if r["kind"] == "page_view" and (path is None or r["path"] == path)]


def test_every_page_renders(client):
    for path in ["/", "/lab", "/pitch", "/pitch/thanks", "/privacy", "/admin"]:
        assert client.get(path).status_code == 200, path
    for p in content.projects():
        assert client.get(f"/projects/{p['slug']}").status_code == 200
    for e in content.experiments():
        r = client.get(f"/lab/{e['slug']}")
        assert r.status_code == 200 and str(escape(e["question"])) in r.text


def test_home_has_real_content(client):
    r = client.get("/")
    s = content.site()
    assert str(escape(s["headline"])) in r.text
    assert "MikeAdamsNC" in r.text
    assert all(soc["url"] in r.text for soc in s["socials"])
    assert all(str(escape(e["title"])) in r.text for e in content.experiments())


def test_unknown_pages_are_404_with_the_site_look(client):
    r = client.get("/lab/nope")
    assert r.status_code == 404 and "doesn't exist. Yet." in r.text


def test_page_views_are_recorded_without_cookies(client):
    r = client.get("/lab?v=classic", headers={**BROWSER, "referer": "https://news.ycombinator.com/item"})
    assert "set-cookie" not in r.headers
    v = views("/lab")[0]
    assert v["device"] == "phone" and v["referrer_host"] == "news.ycombinator.com" and v["visitor"] and v["status"] == 200


def test_bots_and_assets_are_not_counted(client):
    client.get("/", headers={"user-agent": "Googlebot/2.1"})
    client.get("/health")
    client.get("/static/site.css")
    assert views() == []


def test_same_browser_same_day_is_one_visitor(client):
    client.get("/")
    client.get("/lab")
    assert len({v["visitor"] for v in views()}) == 1


def test_events_endpoint_accepts_known_kinds_only(client):
    assert client.post("/e", json={"kind": "xray_open", "path": "/"}).status_code == 200
    assert client.post("/e", json={"kind": "scroll", "path": "/", "value": 75}).status_code == 200
    assert client.post("/e", json={"kind": "drop table"}).status_code == 204
    kinds = [r["kind"] for r in site.recorder.rows]
    assert kinds == ["xray_open", "scroll"]


def pitch(client, **over):
    data = {"what": "An app that tells me when my favorite food truck is nearby.", "kind": "App",
            "started": int(time.time() * 1000) - 10_000, **over}
    return client.post("/pitch", data=data, follow_redirects=False)


def test_a_real_pitch_is_saved(client):
    r = pitch(client, email="a@b.com", name="Sam")
    assert r.status_code == 303 and r.headers["location"] == "/pitch/thanks"
    saved = site.store.list_pitches()
    assert len(saved) == 1 and saved[0]["status"] == "new" and saved[0]["email"] == "a@b.com"
    assert saved[0]["created_at"].endswith(("-04:00", "-05:00"))   # Eastern, with offset


def test_spam_trap_and_too_fast_are_dropped_quietly(client):
    assert pitch(client, website="http://spam").status_code == 303
    assert pitch(client, started=int(time.time() * 1000)).status_code == 303
    assert pitch(client, started=1).status_code == 303          # a faked start time
    assert pitch(client, started=0).status_code == 303
    assert site.store.list_pitches() == []


def test_pitch_needs_a_real_description_and_a_real_email(client):
    assert pitch(client, what="hi").status_code == 400
    assert pitch(client, email="not-an-email").status_code == 400
    assert site.store.list_pitches() == []


def test_five_pitches_a_day_per_visitor(client):
    for _ in range(5):
        assert pitch(client).status_code == 303
    assert pitch(client).status_code == 400
    assert len(site.store.list_pitches()) == 5


def test_dashboard_is_locked(client, monkeypatch):
    assert "isn't set up yet" in client.get("/admin").text
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ADMIN_EMAILS", "mike@example.com")
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"
    client.cookies.set(auth.COOKIE, auth.make_cookie("someone@else.com"))
    assert client.get("/admin", follow_redirects=False).status_code == 303
    client.cookies.set(auth.COOKIE, auth.make_cookie("mike@example.com"))
    r = client.get("/admin")
    assert r.status_code == 200 and "Dashboard" in r.text
    assert client.post("/admin/pitches/x", data={"status": "nope"}).status_code == 400


def test_only_mike_can_change_a_pitch(client):
    assert client.post("/admin/pitches/x", data={"status": "maybe"}).status_code == 403


def test_xray_markup_is_on_every_page(client):
    for path in ["/", "/lab", "/pitch"]:
        r = client.get(path)
        assert 'class="lam"' in r.text and "data-x=" in r.text and "How this page works" in r.text


def test_health_for_keep_warm_ping(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.text == "ok"


def test_no_api_docs_exposed(client):
    assert client.get("/docs").status_code == 404


def test_archer_door_needs_the_token(client, monkeypatch):
    monkeypatch.setenv("ARCHER_TOKEN", "t0ken")
    assert client.get("/api/pitches/unsent").status_code == 403
    assert client.get("/api/pitches/unsent", headers={"authorization": "Bearer wrong"}).status_code == 403
    monkeypatch.delenv("ARCHER_TOKEN")
    assert client.get("/api/pitches/unsent", headers={"authorization": "Bearer "}).status_code == 403


def test_archer_gets_each_pitch_once(client, monkeypatch):
    monkeypatch.setenv("ARCHER_TOKEN", "t0ken")
    h = {"authorization": "Bearer t0ken"}
    pitch(client)
    unsent = client.get("/api/pitches/unsent", headers=h).json()["pitches"]
    assert len(unsent) == 1
    assert client.post(f"/api/pitches/{unsent[0]['id']}/told", headers=h).status_code == 200
    assert client.get("/api/pitches/unsent", headers=h).json()["pitches"] == []
    assert views() == [v for v in views() if not v["path"].startswith("/api")]
