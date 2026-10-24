"""MikeAdamsNC.com: the web server.

Pages: home, the Lab (experiments), project pages, the idea form, privacy, and Mike's
private dashboard. Words come from content/*.yaml; pitches go to Firestore; every page
view and interaction goes to our own analytics (web/analytics.py).
"""
import functools
import hashlib
import hmac
import json
import logging
import os
import pathlib
import time

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analytics, auth, bot, card, clock, content, moderate, ranking, reading, talk, versions
from .store import make_store

ROOT = pathlib.Path(__file__).resolve().parent.parent
logging.basicConfig(level=logging.INFO)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/brand", StaticFiles(directory=ROOT / "brand"), name="brand")
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "web" / "templates")
templates.env.globals["icon_svg"] = card.icon_svg


@functools.cache
def asset(path: str) -> str:
    """A static file's address with a fingerprint of its contents, so browsers fetch it again
    whenever it changes instead of showing a stale copy (a new chat.js with an old site.css)."""
    digest = hashlib.md5((ROOT / "web" / "static" / path).read_bytes()).hexdigest()[:10]
    return f"/static/{path}?v={digest}"


templates.env.globals["asset"] = asset
store = make_store()
recorder = analytics.make_recorder()

SKIP = ("/static", "/brand", "/lab-photo", "/health", "/e", "/favicon", "/admin", "/auth", "/api", "/login", "/logout", "/vote", "/robots.txt")
PITCH_KINDS = ["App", "Website", "Something else", "Not sure"]
PITCH_PURPOSES = ["Personal use", "Business", "Something to sell", "Not sure"]
PITCH_PAY = ["I'd pay you to build it", "Split what it earns", "Free, I just want it to exist", "Not sure"]


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


def visitor(request: Request) -> str:
    return analytics.visitor_id(store.daily_salt(clock.today()), client_ip(request), request.headers.get("user-agent", ""))


@app.middleware("http")
async def measure(request: Request, call_next):
    request.state.t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - request.state.t0) * 1000
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    path = request.url.path
    if request.method == "GET" and not path.startswith(SKIP) and "text/html" in response.headers.get("content-type", ""):
        ua = request.headers.get("user-agent", "")
        device, browser, is_bot = analytics.describe(ua)
        try:  # bots that say so are kept but labeled, so the dashboard can count them apart
            recorder.record(analytics.row(
                "page_view", path=path, visitor=visitor(request), device=device, browser=browser,
                referrer_host=analytics.referrer_host(request.headers.get("referer")),
                version=request.query_params.get("v", "classic"), server_ms=round(ms, 1), status=response.status_code,
                detail=analytics.BOT if is_bot else None))
        except Exception as e:  # analytics must never break a page
            logging.warning("page_view not recorded: %s", e)
    return response


def page(request: Request, name: str, status: int = 200, **kw) -> HTMLResponse:
    try:
        pages_today = recorder.pages_today()
    except Exception:
        pages_today = None
    facts = {
        "server_ms": round((time.perf_counter() - request.state.t0) * 1000, 1),
        "pages_today": pages_today,
        "revision": os.environ.get("K_REVISION", "local"),
        "deployed": os.environ.get("BUILD_TIME", "not deployed"),
    }
    me = auth.person(request.cookies.get(auth.COOKIE))
    return templates.TemplateResponse(request, name, {"site": content.site(), "xray": facts, "year": clock.now().year,
                                                      "signed_in": me, "signin_on": auth.enabled(), **kw},
                                      status_code=status)


def safe_reading(limit: int) -> list[dict]:
    try:
        return store.list_reading(limit)
    except Exception as e:
        logging.warning("reading unavailable: %s", e)
        return []


@app.get("/reading")
def reading_page(request: Request):
    return page(request, "reading.html", items=safe_reading(40))


def safe_tallies() -> dict:
    try:
        return store.tallies()
    except Exception as e:
        logging.warning("tallies unavailable: %s", e)
        return {}


@app.get("/")
def home(request: Request, v: str = "classic"):
    if v in versions.slugs() and v != "classic":
        return page(request, f"v_{v}.html", version=v, versions=versions.all(), projects=content.projects(),
                    experiments=content.experiments())
    tallies = safe_tallies()
    return page(request, "home.html", projects=content.projects(), tallies=tallies, version="classic", lab=live_lab(), reading=safe_reading(6),
                experiments=ranking.order(content.experiments(), tallies, "hot"))


@app.get("/versions")
def versions_page(request: Request):
    return page(request, "versions.html", versions=versions.all())


@app.get("/api/site.json")
def site_json():
    """Everything public on the site, for the versions that draw it themselves."""
    tallies = safe_tallies()
    return {"site": {k: v for k, v in content.site().items()}, "projects": content.projects(), "lab": live_lab(), "reading": safe_reading(10),
            "experiments": [{**e, "added": str(e.get("added", "")), **tallies.get(e["slug"], {"up": 0, "down": 0})}
                            for e in ranking.order(content.experiments(), tallies, "hot")],
            "versions": [{**v, "added": str(v.get("added", ""))} for v in versions.all()]}


_buoy: dict = {}


@app.get("/api/buoy")
def buoy():
    """Latest waves at NOAA buoy 41025 (Diamond Shoals, off Cape Hatteras), cached 30 minutes."""
    import httpx

    now = time.time()
    if _buoy and now - _buoy["at"] < 1800:
        return _buoy["data"]
    data = {"station": "41025", "name": "Diamond Shoals", "wave_ft": None, "period_s": None, "at": None}
    try:
        lines = httpx.get("https://www.ndbc.noaa.gov/data/realtime2/41025.txt", timeout=10).text.splitlines()
        for line in lines[2:]:
            f = line.split()
            if len(f) > 9 and f[8] != "MM":
                from datetime import datetime, timezone
                utc = datetime(int(f[0]), int(f[1]), int(f[2]), int(f[3]), int(f[4]), tzinfo=timezone.utc)
                data |= {"wave_ft": round(float(f[8]) * 3.281, 1), "period_s": float(f[9]) if f[9] != "MM" else None,
                         "at": utc.astimezone(clock.EASTERN).strftime("%-I:%M %p")}
                break
    except Exception as e:
        logging.warning("buoy unavailable: %s", e)
    _buoy.update(at=now, data=data)
    return data


@app.post("/talk")
async def talk_turn(request: Request):
    try:
        messages = bot.clean((await request.json()).get("messages", []))
    except Exception:
        raise HTTPException(400)
    device, browser, is_bot = analytics.describe(request.headers.get("user-agent", ""))
    if is_bot or not messages:
        raise HTTPException(400)
    vid = visitor(request)
    day = clock.today()
    if store.bump(f"talk-{vid}-{day}") > 40 or store.bump(f"chat-all-{day}") > 600:
        return {"reply": "That's all the talking I can do today. The Classic version has everything.", "links": [{"label": "Classic", "path": "/?v=classic"}], "down": True}
    try:
        out = talk.answer(messages[-12:])
    except bot.Unavailable:
        return {"reply": "My brain is offline for a moment. The Classic version has everything.", "links": [{"label": "Classic", "path": "/?v=classic"}], "down": True}
    recorder.record(analytics.row("talk_message", path="/", visitor=vid, device=device, browser=browser, version="talk",
                                  value=float(sum(1 for m in messages if m["role"] == "user"))))
    return out


@app.get("/lab")
def lab(request: Request, sort: str = "hot"):
    sort = sort if sort in {"hot", "new", "top"} else "hot"
    tallies = safe_tallies()
    vid = visitor(request)
    exps = ranking.order(content.experiments(), tallies, sort)
    mine = {e["slug"]: store.my_vote(e["slug"], vid) for e in exps}
    return page(request, "lab.html", experiments=exps, tallies=tallies, mine=mine, sort=sort)


@app.get("/lab/{slug}")
def experiment(request: Request, slug: str, held: int = 0):
    e = content.find(content.experiments(), slug)
    if not e:
        raise HTTPException(404)
    me = auth.person(request.cookies.get(auth.COOKIE))
    comments = store.list_comments(slug)
    mine_held = [c for c in store.list_comments(slug, ("held",)) if me and c.get("sub") == me.get("sub")]
    return page(request, "experiment.html", e=e, experiments=content.experiments(), tally=store.tally(slug),
                my_vote=store.my_vote(slug, visitor(request)), comments=comments, mine_held=mine_held,
                held=held, error=request.query_params.get("error"))


@app.post("/vote/{slug}")
async def vote(request: Request, slug: str):
    if not content.find(content.experiments(), slug):
        raise HTTPException(404)
    try:
        value = int((await request.json()).get("value", 0))
    except Exception:
        raise HTTPException(400)
    if value not in (-1, 0, 1):
        raise HTTPException(400)
    device, browser, is_bot = analytics.describe(request.headers.get("user-agent", ""))
    if is_bot:
        raise HTTPException(403)
    vid = visitor(request)
    if store.bump(f"votes-{vid}-{clock.today()}") > 100:
        raise HTTPException(429)
    tally = store.vote(slug, vid, value)
    recorder.record(analytics.row("vote", path=f"/lab/{slug}", visitor=vid, device=device, browser=browser,
                                  detail=slug, value=float(value)))
    return {**tally, "mine": value}


@app.post("/lab/{slug}/comments")
def comment(request: Request, slug: str, text: str = Form("")):
    e = content.find(content.experiments(), slug)
    if not e:
        raise HTTPException(404)
    me = auth.person(request.cookies.get(auth.COOKIE))
    if not me:
        return RedirectResponse(f"/login?next=/lab/{slug}%23comments", status_code=303)
    text = text.strip()
    if not 2 <= len(text) <= 2000:
        return RedirectResponse(f"/lab/{slug}?error=length#comments", status_code=303)
    if store.bump(f"comments-{me['sub']}-{clock.today()}") > 10:
        return RedirectResponse(f"/lab/{slug}?error=limit#comments", status_code=303)
    verdict, reason = moderate.check(e["title"], text)
    status = "visible" if verdict == "ok" else "held"
    store.add_comment({"slug": slug, "text": text, "name": me["name"], "email": me["email"], "sub": me["sub"],
                       "created_at": clock.stamp(), "status": status, "reason": reason})
    recorder.record(analytics.row("comment", path=f"/lab/{slug}", visitor=visitor(request), detail=status))
    return RedirectResponse(f"/lab/{slug}{'?held=1' if status == 'held' else ''}#comments", status_code=303)


@app.get("/projects/{slug}")
def project(request: Request, slug: str):
    p = content.find(content.projects(), slug)
    if not p:
        raise HTTPException(404)
    return page(request, "project.html", p=p)


@app.get("/pitch")
def pitch_chat(request: Request):
    return page(request, "chat.html", greeting=bot.GREETING, chips=bot.CHIPS)


@app.post("/pitch/chat")
async def chat_turn(request: Request):
    """One bot reply, streamed to the page as server-sent events: "delta" pieces of the reply as
    the AI writes it, then "done" with the whole answer (or "down" if the AI or a limit is out)."""
    try:
        messages = bot.clean((await request.json()).get("messages", []))
    except Exception:
        raise HTTPException(400)
    device, browser, is_bot = analytics.describe(request.headers.get("user-agent", ""))
    if is_bot:
        raise HTTPException(403)
    vid = visitor(request)
    day = clock.today()
    users = sum(1 for m in messages if m["role"] == "user")

    def event(d: dict) -> str:
        return "data: " + json.dumps(d) + "\n\n"

    def run():
        if store.bump(f"chat-{vid}-{day}") > 30 or store.bump(f"chat-all-{day}") > 600:
            yield event({"t": "down", "reply": "That's all the chatting I can do today. The form still works, and Mike reads those too."})
            return
        try:
            for kind, data in bot.stream(messages):
                if kind == "delta":
                    yield event({"t": "delta", "text": data})
                else:
                    recorder.record(analytics.row("chat_start" if users <= 1 else "chat_message", path="/pitch", visitor=vid,
                                                  device=device, browser=browser, value=float(users), detail="ready" if data["ready"] else ""))
                    yield event({"t": "done", **data})
        except bot.Unavailable:
            yield event({"t": "down", "reply": "My brain is offline for a moment. The form works right now, and Mike reads those too."})

    return StreamingResponse(run(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/pitch/chat/send")
async def chat_send(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400)
    pitch = bot.tidy(data.get("pitch"))
    messages = bot.clean(data.get("messages", []))
    if len(pitch["what"]) < 10:
        return JSONResponse({"ok": False, "error": "Tell me a little more about what it is first."}, status_code=400)
    vid = visitor(request)
    if store.bump(f"pitch-{vid}-{clock.today()}") > 5:
        return JSONResponse({"ok": False, "error": "That's a lot of ideas for one day. Send the rest tomorrow."}, status_code=429)
    device, _, _ = analytics.describe(request.headers.get("user-agent", ""))
    transcript = "\n".join(f"{'Visitor' if m['role'] == 'user' else 'Bot'}: {m['text']}" for m in messages)[:12000]
    made, card_id = None, None
    if pitch["type"] == "pitch" and isinstance(data.get("card"), dict):
        made = card.tidy(data["card"])
        verdict, reason = moderate.check("", card.text_of(made), moderate.CARD_PROMPT)
        if verdict == "ok":
            card_id = store.add_card({"card": made, "label": card.label(pitch), "created_at": clock.stamp(),
                                      "by": card.first_name(pitch["name"]) if data.get("show_name") else ""})
        else:
            logging.info("card held: %s", reason)
    store.add_pitch({**pitch, "status": "new", "source": "chat", "transcript": transcript, "created_at": clock.stamp(),
                     "visitor": vid, "device": device, "card": made, "card_id": card_id})
    recorder.record(analytics.row("pitch_submit", path="/pitch", visitor=vid, device=device, detail="chat+card" if card_id else "chat"))
    return {"ok": True, "card_url": f"/idea/{card_id}?sent=1" if card_id else None}


@app.post("/pitch/card")
async def pitch_card(request: Request):
    """Draft the visitor's pitch card. Nothing is saved until they send the pitch."""
    try:
        data = await request.json()
        pitch = bot.tidy(data.get("pitch"))
    except Exception:
        raise HTTPException(400)
    device, _, is_bot = analytics.describe(request.headers.get("user-agent", ""))
    if is_bot or pitch["type"] != "pitch" or len(pitch["what"]) < 10:
        raise HTTPException(400)
    vid, day = visitor(request), clock.today()
    if store.bump(f"card-{vid}-{day}") > 20 or store.bump(f"card-all-{day}") > 600:  # the card redraws as they talk
        raise HTTPException(429)
    try:
        made = card.make(pitch)
    except card.Unavailable:
        raise HTTPException(503)
    recorder.record(analytics.row("card_made", path="/pitch", visitor=vid, device=device))
    html = templates.env.get_template("_card.html").render(c=made, label=card.label(pitch), by="", editable=bool(data.get("editable")))
    return {"card": made, "html": html}


@app.get("/idea/{cid}.png")
def idea_image(cid: str):
    doc = store.get_card(cid)
    if not doc:
        raise HTTPException(404)
    return Response(card_png(cid, doc), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@functools.lru_cache(maxsize=64)
def _png(cid: str, blob: str) -> bytes:
    doc = json.loads(blob)
    return card.png(doc["card"], doc["label"], doc["by"])


def card_png(cid: str, doc: dict) -> bytes:
    return _png(cid, json.dumps({k: doc.get(k, "") for k in ("card", "label", "by")}, sort_keys=True))


@app.get("/idea/{cid}")
def idea_page(request: Request, cid: str, sent: int = 0):
    doc = store.get_card(cid)
    if not doc:
        raise HTTPException(404)
    return page(request, "idea.html", c=card.tidy(doc["card"]), label=doc.get("label", ""), by=doc.get("by", ""),
                cid=cid, sent=bool(sent))


@app.get("/pitch/form")
def pitch_form(request: Request):
    return page(request, "pitch.html", kinds=PITCH_KINDS, purposes=PITCH_PURPOSES, pay=PITCH_PAY,
                started=int(time.time() * 1000), error=None, form={})


@app.post("/pitch")
def pitch_submit(request: Request, what: str = Form(""), kind: str = Form(""), purpose: str = Form(""),
                 payment: str = Form(""), features: str = Form(""), marketing: str = Form(""),
                 name: str = Form(""), email: str = Form(""), website: str = Form(""), started: int = Form(0)):
    form = {"what": what, "kind": kind, "purpose": purpose, "payment": payment, "features": features,
            "marketing": marketing, "name": name, "email": email}
    def again(error: str):
        return page(request, "pitch.html", status=400, kinds=PITCH_KINDS, purposes=PITCH_PURPOSES, pay=PITCH_PAY,
                    started=int(time.time() * 1000), error=error, form=form)
    elapsed = time.time() * 1000 - started
    if website or not 3_000 <= elapsed <= 86_400_000:   # the hidden trap field, faster than a human, or a faked start
        return RedirectResponse("/pitch/thanks", status_code=303)
    if len(what.strip()) < 10:
        return again("Tell me a little more about what it is (a sentence or two is plenty).")
    if email and "@" not in email:
        return again("That email doesn't look right. Leave it blank if you'd rather not share one.")
    vid = visitor(request)
    if store.bump(f"pitch-{vid}-{clock.today()}") > 5:
        return again("That's a lot of ideas for one day. Send the rest tomorrow.")
    device, _, _ = analytics.describe(request.headers.get("user-agent", ""))
    clean = {k: v.strip()[:4000] for k, v in form.items()}
    store.add_pitch({**clean, "status": "new", "source": "form", "created_at": clock.stamp(), "visitor": vid, "device": device})
    recorder.record(analytics.row("pitch_submit", path="/pitch", visitor=vid, device=device))
    return RedirectResponse("/pitch/thanks", status_code=303)


@app.get("/pitch/thanks")
def pitch_thanks(request: Request):
    return page(request, "pitch_thanks.html")


@app.get("/privacy")
def privacy(request: Request):
    return page(request, "privacy.html")


@app.post("/e")
async def event(request: Request):
    """Small interaction events from the page (scroll depth, X-ray, outbound clicks)."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    kind = str(data.get("kind", ""))
    ua = request.headers.get("user-agent", "")
    device, browser, is_bot = analytics.describe(ua)
    if kind not in analytics.EVENT_KINDS or is_bot:
        return Response(status_code=204)
    value = data.get("value")
    recorder.record(analytics.row(kind, path=str(data.get("path", ""))[:200], visitor=visitor(request), device=device,
                                  browser=browser, detail=str(data.get("detail", ""))[:200],
                                  value=float(value) if isinstance(value, (int, float)) else None))
    return JSONResponse({"ok": True})


@app.get("/health")
def health():
    """The scheduler pings this every 10 minutes so the site stays warm, and the reading
    shelf refreshes off it about hourly. (Not /healthz: Cloud Run reserves paths ending in z.)"""
    reading.refresh_if_due(store)
    return PlainTextResponse("ok")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(ROOT / "brand" / "icon" / "favicon-32.png", media_type="image/png")


@app.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /admin\n")


# ---------- Mike's private pages ----------

def callback_url(request: Request) -> str:
    host = request.headers.get("host", "mikeadamsnc.com")
    return f"https://{host}/auth/callback" if "localhost" not in host and "127.0.0.1" not in host else f"http://{host}/auth/callback"


def require_mike(request: Request) -> str | None:
    return auth.who(request.cookies.get(auth.COOKIE))


@app.get("/admin")
def admin(request: Request, days: int = 7):
    if not auth.enabled():
        return page(request, "admin_off.html")
    me = require_mike(request)
    if not me:
        return RedirectResponse("/admin/login", status_code=303)
    days = 30 if days == 30 else 7
    from . import dashboard
    tallies = safe_tallies()
    votes = sorted(({"slug": k, **v} for k, v in tallies.items()), key=lambda r: r["up"] - r["down"], reverse=True)
    return page(request, "admin.html", me=me, days=days, stats=dashboard.stats(recorder, days),
                pitches=store.list_pitches(), held=store.list_comments(None, ("held",)),
                recent=list(reversed(store.list_comments(None, ("visible",))))[:20], votes=votes)


@app.post("/admin/comments/{cid}")
def comment_status(request: Request, cid: str, status: str = Form(...)):
    if not require_mike(request):
        raise HTTPException(403)
    if status not in {"visible", "removed"}:
        raise HTTPException(400)
    store.set_comment(cid, status)
    return RedirectResponse("/admin#comments", status_code=303)


def safe_next(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"


@app.get("/login")
def login(request: Request, next: str = "/"):
    if not auth.enabled():
        return RedirectResponse(safe_next(next), status_code=303)
    url, state = auth.login_url(callback_url(request))
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, secure=True, samesite="lax")
    resp.set_cookie("oauth_next", safe_next(next), max_age=600, httponly=True, secure=True, samesite="lax")
    return resp


@app.get("/admin/login")
def admin_login():
    return RedirectResponse("/login?next=/admin", status_code=303)


@app.get("/auth/callback")
def auth_callback(request: Request, code: str = "", state: str = ""):
    if not auth.enabled() or not code or state != request.cookies.get("oauth_state"):
        raise HTTPException(400)
    who_ = auth.person_from_code(code, callback_url(request))
    nxt = safe_next(request.cookies.get("oauth_next", "/"))
    if not who_:
        raise HTTPException(400)
    if nxt.startswith("/admin") and who_["email"] not in auth.admins():
        return page(request, "admin_off.html", status=403, denied=True)
    resp = RedirectResponse(nxt, status_code=303)
    resp.set_cookie(auth.COOKIE, auth.make_cookie(who_), max_age=auth.MAX_AGE, httponly=True, secure=True, samesite="lax")
    resp.delete_cookie("oauth_state")
    resp.delete_cookie("oauth_next")
    recorder.record(analytics.row("sign_in", path=nxt, visitor=visitor(request)))
    return resp


@app.get("/logout")
def logout(next: str = "/"):
    resp = RedirectResponse(safe_next(next), status_code=303)
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/admin/logout")
def admin_logout():
    return logout()


@app.post("/admin/pitches/{pid}")
def pitch_status(request: Request, pid: str, status: str = Form(...)):
    if not require_mike(request):
        raise HTTPException(403)
    if status not in {"new", "maybe", "building", "done", "no"}:
        raise HTTPException(400)
    store.set_status(pid, status)
    return RedirectResponse("/admin#pitches", status_code=303)


# ---------- Archer's private door: Archer asks for new pitches and pushes them to Mike ----------

def archer_only(request: Request) -> None:
    want = os.environ.get("ARCHER_TOKEN", "")
    got = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not want or not hmac.compare_digest(want, got):
        raise HTTPException(403)


@app.get("/api/pitches/unsent")
def pitches_unsent(request: Request):
    archer_only(request)
    return {"pitches": [p for p in store.list_pitches() if not p.get("archer_told_at")]}


@app.post("/api/pitches/{pid}/told")
def pitch_told(request: Request, pid: str):
    archer_only(request)
    store.mark_told(pid)
    return {"ok": True}


LAB_STALE_MIN = 30


def live_lab() -> dict | None:
    """The latest summary Archer sent, or None when it's off or older than 30 minutes."""
    try:
        lab = store.get_lab()
    except Exception as e:
        logging.warning("lab unavailable: %s", e)
        return None
    if not lab or lab.get("off"):
        return None
    from datetime import datetime
    age = (clock.now() - datetime.fromisoformat(lab["at"])).total_seconds() / 60
    return {**lab, "age_min": max(0, round(age))} if age <= LAB_STALE_MIN else None


@app.post("/api/lab")
async def lab_in(request: Request):
    """Archer's live lab summary (Archer locked item 31): fixed fields only."""
    import base64

    archer_only(request)
    body = await request.json()
    if body.get("off"):
        store.put_lab({"off": True, "at": clock.stamp()}, None)
        return {"ok": True}
    g, r, t = body.get("grill") or {}, body.get("radar") or {}, body.get("trail_cams") or {}
    num = lambda v: int(v) if isinstance(v, (int, float)) else None  # noqa: E731
    clean = {
        "at": str(body.get("at", clock.stamp()))[:40],
        "grill": {"on": bool(g.get("on")), "cut": str(g.get("cut", ""))[:40], "grill_f": num(g.get("grill_f")),
                  "probe_f": num(g.get("probe_f"))} if g.get("on") else {"on": False},
        "radar": {"call": str(r.get("call", "unknown"))[:20], "readings": num(r.get("readings"))},
        "trail_cams": {"day": str(t.get("day", ""))[:10],
                       "species": [{"name": str(s.get("name", ""))[:40], "count": num(s.get("count")) or 0}
                                   for s in (t.get("species") or [])[:8]]},
    }
    photo = None
    if body.get("photo", {}).get("jpeg_b64"):
        photo = base64.b64decode(body["photo"]["jpeg_b64"])[:400_000]
        if not photo.startswith(b"\xff\xd8"):
            raise HTTPException(400)
        clean["photo"] = {"species": str(body["photo"].get("species", ""))[:40], "count": num(body["photo"].get("count")) or 1,
                          "v": clock.stamp()[:16]}
    else:
        prev = store.get_lab() or {}
        if prev.get("photo"):
            clean["photo"] = prev["photo"]
    store.put_lab(clean, photo)
    return {"ok": True}


@app.get("/lab-photo.jpg")
def lab_photo():
    jpeg = store.get_lab_photo()
    if not jpeg:
        raise HTTPException(404)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/comments/unsent")
def comments_unsent(request: Request):
    archer_only(request)
    out = [c for c in store.list_comments(None, ("visible", "held")) if not c.get("archer_told_at")]
    return {"comments": [{k: c.get(k) for k in ("id", "slug", "name", "text", "status", "reason", "created_at")} for c in out]}


@app.post("/api/comments/{cid}/told")
def comment_told(request: Request, cid: str):
    archer_only(request)
    store.mark_comment_told(cid)
    return {"ok": True}


@app.exception_handler(404)
def not_found(request: Request, exc):
    if not hasattr(request.state, "t0"):
        request.state.t0 = time.perf_counter()
    return page(request, "404.html", status=404)
