"""The drop box: upload links Mike makes, the files sent through them, and what keeps it safe."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from web import app as site
from web import auth, clock, drop

BROWSER = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit Safari/604.1"}
DATA = b"%PDF a file, more or less " * 400  # 10,000 bytes


@pytest.fixture
def client(monkeypatch):
    site.store.__init__()
    site.recorder.__init__()
    monkeypatch.setattr(site, "files", drop.LocalFiles())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ADMIN_EMAILS", "mike@example.com")
    return TestClient(site.app, headers=BROWSER)


def as_mike(client):
    client.cookies.set(auth.COOKIE, auth.make_cookie("mike@example.com"))


def as_nobody(client):
    client.cookies.clear()


def make_link(client, label="Project files", days=7) -> str:
    """Mike makes a link on his dashboard; returns its secret, which the page shows him to copy."""
    as_mike(client)
    before = {link["token"] for link in site.store.list_drops()}
    assert client.post("/admin/drop/links", data={"label": label, "days": days}, follow_redirects=False).status_code == 303
    (token,) = {link["token"] for link in site.store.list_drops()} - before
    assert f'value="https://testserver/drop#{token}"' in client.get("/admin/drop").text
    as_nobody(client)
    return token


def start(client, token, name="report.pdf", size=len(DATA), **more):
    return client.post("/drop/start", json={"token": token, "name": name, "size": size, **more})


def upload(client, token, name="report.pdf", data=DATA, **more) -> str:
    s = start(client, token, name, len(data), **more).json()
    assert client.put(s["url"], content=data).status_code == 200
    assert client.post("/drop/done", json={"token": token, "id": s["id"]}).json() == {"ok": True}
    return s["id"]


# ---------- the upload page and its link ----------

def test_the_page_is_public_but_useless_without_a_link(client):
    r = client.get("/drop")
    assert r.status_code == 200 and 'name="robots" content="noindex"' in r.text and "drop.js" in r.text
    assert "Disallow: /drop\n" in client.get("/robots.txt").text
    assert "/drop" not in client.get("/sitemap.xml").text
    for token in ["", "nope", "x" * 32, None, 7, "a/b" * 10]:
        assert client.post("/drop/open", json={"token": token}).status_code == 404
    assert start(client, "x" * 32).status_code == 404


def test_a_link_opens_until_it_runs_out_or_is_closed(client, monkeypatch):
    token = make_link(client, "Signed contracts", days=1)
    facts = client.post("/drop/open", json={"token": token}).json()
    assert facts["label"] == "Signed contracts" and facts["max_file"] == drop.MAX_FILE and facts["room"] == drop.MAX_LINK_BYTES
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(days=1, minutes=1))
    assert client.post("/drop/open", json={"token": token}).status_code == 404
    assert start(client, token).status_code == 404
    monkeypatch.setattr(clock, "now", real)
    as_mike(client)
    assert client.post("/admin/drop/close", data={"token": token}, follow_redirects=False).status_code == 303
    assert client.post("/drop/open", json={"token": token}).status_code == 404


def test_a_link_lasts_one_seven_or_thirty_days(client):
    for asked, got in [(1, 1), (30, 30), (7, 7), (9999, 7)]:
        site.store.__init__()
        make_link(client, days=asked)
        link = site.store.list_drops()[0]
        left = clock.now().fromisoformat(link["expires_at"]) - clock.now()
        assert timedelta(days=got, minutes=-1) < left <= timedelta(days=got)


# ---------- sending a file ----------

def test_a_file_goes_up_and_mike_gets_it_back(client):
    token = make_link(client)
    fid = upload(client, token, "report.pdf", DATA, **{"from": "Pat Lee", "note": "Final versions"})
    as_mike(client)
    page = client.get("/admin/drop").text
    assert "report.pdf" in page and "Pat Lee" in page and "Final versions" in page and "NEW" in page
    got = client.get(f"/admin/drop/files/{fid}")
    assert got.content == DATA
    assert got.headers["content-type"] == "application/octet-stream"
    assert got.headers["content-disposition"].startswith("attachment")
    assert "· NEW" not in client.get("/admin/drop").text  # downloaded once, no longer new
    assert site.store.get_drop(token)["bytes"] == len(DATA)
    client.post(f"/admin/drop/files/{fid}/delete")
    assert "report.pdf" not in client.get("/admin/drop").text
    assert client.get(f"/admin/drop/files/{fid}").status_code == 404
    assert site.files.size(f"{drop.folder(token)}/{fid}") is None
    assert site.store.get_drop(token)["bytes"] == 0 and site.store.get_drop(token)["files"] == 0


def test_a_dropped_connection_picks_up_where_it_stopped(client):
    token = make_link(client)
    s = start(client, token).json()
    r = client.put(s["url"], content=DATA[:4000], headers={"Content-Range": f"bytes 0-3999/{len(DATA)}"})
    assert r.status_code == 308 and r.headers["range"] == "bytes=0-3999"
    assert client.post("/drop/done", json={"token": token, "id": s["id"]}).status_code == 409  # not whole yet
    assert client.post("/drop/offset", json={"token": token, "id": s["id"]}).json() == {"offset": 4000}
    again = start(client, token).json()  # the page reloaded and the same file was picked again
    assert again == {"id": s["id"], "url": s["url"], "offset": 4000}
    assert site.store.get_drop(token)["files"] == 1  # one file's worth of room, not two
    rest = client.put(s["url"], content=DATA[4000:], headers={"Content-Range": f"bytes 4000-{len(DATA) - 1}/{len(DATA)}"})
    assert rest.status_code == 200
    assert client.post("/drop/offset", json={"token": token, "id": s["id"]}).json() == {"offset": len(DATA)}
    assert client.post("/drop/done", json={"token": token, "id": s["id"]}).json() == {"ok": True}
    as_mike(client)
    assert client.get(f"/admin/drop/files/{s['id']}").content == DATA


def test_bytes_past_the_promised_size_are_refused(client):
    token = make_link(client)
    s = start(client, token, size=100).json()
    assert client.put(s["url"], content=b"x" * 101).status_code == 400
    assert client.put(s["url"], content=b"x" * 50, headers={"Content-Range": "bytes 60-109/100"}).status_code == 400


# ---------- limits ----------

def test_size_and_room_limits(client, monkeypatch):
    token = make_link(client)
    assert start(client, token, size=0).status_code == 400
    assert start(client, token, size="12").status_code == 400
    assert start(client, token, size=True).status_code == 400
    assert start(client, token, size=drop.MAX_FILE + 1).status_code == 413
    monkeypatch.setattr(drop, "MAX_LINK_BYTES", 25_000)
    assert start(client, token, "a.jpg", 10_000).status_code == 200
    assert start(client, token, "b.jpg", 10_000).status_code == 200
    full = start(client, token, "c.jpg", 10_000)
    assert full.status_code == 413 and "storage limit" in full.json()["error"]
    assert site.store.get_drop(token)["bytes"] == 20_000  # the refused one gave its room back
    monkeypatch.setattr(drop, "MAX_LINK_FILES", 2)
    assert start(client, token, "d.jpg", 1).status_code == 413


def test_a_file_that_is_not_the_promised_size_is_deleted(client):
    token = make_link(client)
    s = start(client, token, size=500).json()
    obj = f"{drop.folder(token)}/{s['id']}"
    site.files._path(obj).write_bytes(b"x" * 900)  # storage ended up with something else
    assert client.post("/drop/done", json={"token": token, "id": s["id"]}).status_code == 409
    assert site.files.size(obj) is None and site.store.get_drop_file(s["id"]) is None
    assert site.store.get_drop(token)["bytes"] == 0


def test_visitors_cannot_hammer_it(client):
    token = make_link(client)
    for _ in range(200):
        assert client.post("/drop/open", json={"token": token}).status_code == 200
    assert client.post("/drop/open", json={"token": token}).status_code == 429


# ---------- who can do what ----------

def test_closing_a_link_stops_uploads_still_going(client):
    token = make_link(client)
    s = start(client, token).json()
    client.put(s["url"], content=DATA[:4000], headers={"Content-Range": f"bytes 0-3999/{len(DATA)}"})
    as_mike(client)
    client.post("/admin/drop/close", data={"token": token})
    as_nobody(client)
    assert client.put(s["url"], content=DATA[4000:], headers={"Content-Range": f"bytes 4000-{len(DATA) - 1}/{len(DATA)}"}).status_code == 404
    assert client.post("/drop/offset", json={"token": token, "id": s["id"]}).status_code == 404
    assert site.store.list_drop_files(None, ("pending", "done")) == []


def test_one_links_holder_cannot_touch_another_links_file(client):
    mine, theirs = make_link(client, "Mine"), make_link(client, "Theirs")
    s = start(client, mine).json()
    for path in ["/drop/offset", "/drop/done"]:
        assert client.post(path, json={"token": theirs, "id": s["id"]}).status_code in (404, 409)
    assert site.store.get_drop_file(s["id"])["status"] == "pending"  # untouched


def test_only_mike_sees_links_and_files(client):
    token = make_link(client)
    fid = upload(client, token)
    assert client.get("/admin/drop", follow_redirects=False).headers["location"] == "/login?next=/admin/drop"
    assert client.get(f"/admin/drop/files/{fid}").status_code == 403
    assert client.post("/admin/drop/links", data={"label": "x"}).status_code == 403
    assert client.post("/admin/drop/close", data={"token": token}).status_code == 403
    assert client.post(f"/admin/drop/files/{fid}/delete").status_code == 403
    client.cookies.set(auth.COOKIE, auth.make_cookie("someone@else.com"))
    assert client.get("/admin/drop", follow_redirects=False).status_code == 303
    assert client.get(f"/admin/drop/files/{fid}").status_code == 403
    assert client.post(f"/admin/drop/files/{fid}/delete").status_code == 403
    assert site.store.get_drop_file(fid)["status"] == "done"


def test_another_sites_page_cannot_act(client):
    token = make_link(client)
    evil = {"origin": "https://evil.example"}
    assert client.post("/drop/open", json={"token": token}, headers=evil).status_code == 403
    assert client.post("/drop/open", json={"token": token}, headers={"origin": "https://testserver"}).status_code == 200
    as_mike(client)
    assert client.post("/admin/drop/links", data={"label": "x"}, headers=evil).status_code == 403
    assert client.post("/admin/drop/close", data={"token": token}, headers=evil).status_code == 403
    assert drop.active(site.store.get_drop(token))


def test_the_link_secret_stays_out_of_analytics(client):
    token = make_link(client)
    upload(client, token)
    client.get("/drop")
    client.get(f"/drop/{token}")  # a mangled link: a 404, and still not written down
    rows = site.recorder.rows
    assert any(r["kind"] == "drop_file" and r["value"] == float(len(DATA)) for r in rows)
    assert [r["path"] for r in rows if r["kind"] == "page_view"] == ["/drop"]
    assert token not in repr(rows)


def test_the_drop_box_is_off_without_a_bucket(client, monkeypatch):
    token = make_link(client)
    monkeypatch.setattr(site, "files", None)
    assert client.post("/drop/open", json={"token": token}).status_code == 404
    as_mike(client)
    assert "Not set up yet" in client.get("/admin/drop").text
    assert client.post("/admin/drop/links", data={"label": "x"}).status_code == 404
    assert client.get("/health").status_code == 200


# ---------- housekeeping ----------

def test_unfinished_uploads_are_cleared_after_two_days(client, monkeypatch):
    token = make_link(client, days=30)
    s = start(client, token).json()
    client.put(s["url"], content=DATA[:4000], headers={"Content-Range": f"bytes 0-3999/{len(DATA)}"})
    drop.sweep(site.store, site.files)
    assert site.store.get_drop_file(s["id"])["status"] == "pending"
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + drop.STALE + timedelta(minutes=1))
    drop.sweep(site.store, site.files)
    assert site.store.get_drop_file(s["id"]) is None and site.store.get_drop(token)["bytes"] == 0
    assert client.put(s["url"], content=DATA[4000:], headers={"Content-Range": f"bytes 4000-{len(DATA) - 1}/{len(DATA)}"}).status_code == 404


def test_a_finished_upload_is_kept_even_if_the_page_never_said_so(client):
    token = make_link(client)
    s = start(client, token).json()
    client.put(s["url"], content=DATA)  # the tab was closed right after the last byte
    as_mike(client)
    assert "report.pdf" in client.get("/admin/drop").text  # opening the dashboard settles it
    assert site.store.get_drop_file(s["id"])["status"] == "done"


def test_file_names_are_made_harmless():
    assert drop.clean_name("../../etc/passwd") == "passwd"
    assert drop.clean_name("C:\\Users\\pat\\report.pdf") == "report.pdf"
    assert drop.clean_name("a\x00b\r\nc.jpg") == "abc.jpg"
    assert drop.clean_name(".htaccess") == "htaccess"
    assert drop.clean_name("") == "file" and drop.clean_name(None) == "file"
    long = drop.clean_name("x" * 400 + ".jpeg")
    assert len(long) == 150 and long.endswith(".jpeg")
    header = drop.disposition('la"ke\r\n évé.jpg')
    assert header.startswith("attachment;") and "\r" not in header and "\n" not in header and header.count('"') == 2
    assert header.isascii()


def test_names_are_shown_as_text_never_as_markup(client):
    token = make_link(client, "<b>label</b>")
    upload(client, token, "<img src=x onerror=alert(1)>.jpg", **{"from": "<script>x</script>"})
    as_mike(client)
    page = client.get("/admin/drop").text
    assert "<img src=x" not in page and "<script>x</script>" not in page and "<b>label</b>" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;.jpg" in page


# ---------- the real bucket's client, as far as it can be checked without Google ----------

class _Reply:
    def __init__(self, status, headers=None):
        self.status_code, self.headers = status, headers or {}


def test_how_far_a_cloud_upload_got(monkeypatch):
    cloud = object.__new__(drop.CloudFiles)
    asked = {}

    def fake_put(url, headers, timeout):
        asked.update(url=url, headers=headers)
        return replies.pop(0)

    monkeypatch.setattr(drop.httpx, "put", fake_put)
    replies = [_Reply(308, {"range": "bytes=0-1999"}), _Reply(308), _Reply(200), _Reply(201), _Reply(404), _Reply(410)]
    assert [cloud.persisted("https://session", 5000) for _ in range(6)] == [2000, 0, 5000, 5000, None, None]
    assert asked == {"url": "https://session", "headers": {"Content-Range": "bytes */5000", "Content-Length": "0"}}


def test_a_cloud_upload_is_opened_for_one_fixed_size_object(monkeypatch):
    made = {}

    class Blob:
        def create_resumable_upload_session(self, **kw):
            made.update(kw, disposition=self.content_disposition)
            return "https://session"

    class Bucket:
        def blob(self, name):
            made["name"] = name
            return Blob()

    cloud = object.__new__(drop.CloudFiles)
    cloud.bucket = Bucket()
    assert cloud.start("abc/123", 5000, "report.pdf", "https://mikeadamsnc.com") == "https://session"
    assert made["name"] == "abc/123" and made["size"] == 5000 and made["origin"] == "https://mikeadamsnc.com"
    assert made["content_type"] == "application/octet-stream" and made["if_generation_match"] == 0
    assert made["disposition"].startswith('attachment; filename="report.pdf"')
