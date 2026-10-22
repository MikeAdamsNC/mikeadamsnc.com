"""MikeAdamsNC.com: the web server.

Pages: home, the Lab (experiments), project pages, the idea form, privacy, and Mike's
private dashboard. Words come from content/*.yaml; pitches go to Firestore; every page
view and interaction goes to our own analytics (web/analytics.py).
"""
import hmac
import logging
import os
import pathlib
import time

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analytics, auth, clock, content, moderate, ranking
from .store import make_store

ROOT = pathlib.Path(__file__).resolve().parent.parent
logging.basicConfig(level=logging.INFO)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/brand", StaticFiles(directory=ROOT / "brand"), name="brand")
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "web" / "templates")
store = make_store()
recorder = analytics.make_recorder()

SKIP = ("/static", "/brand", "/health", "/e", "/favicon", "/admin", "/auth", "/api", "/login", "/logout", "/vote", "/robots.txt")
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
        if not is_bot:
            try:
                recorder.record(analytics.row(
                    "page_view", path=path, visitor=visitor(request), device=device, browser=browser,
                    referrer_host=analytics.referrer_host(request.headers.get("referer")),
                    version=request.query_params.get("v", "classic"), server_ms=round(ms, 1), status=response.status_code))
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


def safe_tallies() -> dict:
    try:
        return store.tallies()
    except Exception as e:
        logging.warning("tallies unavailable: %s", e)
        return {}


@app.get("/")
def home(request: Request):
    tallies = safe_tallies()
    return page(request, "home.html", projects=content.projects(), tallies=tallies,
                experiments=ranking.order(content.experiments(), tallies, "hot"))


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
    """The scheduler pings this every 10 minutes so the site stays warm.
    (Not /healthz: Cloud Run reserves paths ending in z.)"""
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
