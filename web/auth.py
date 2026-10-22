"""Sign in with Google: for commenting, and for Mike's private pages (only ADMIN_EMAILS).

Turned on once GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set. The only cookie the
site sets is this sign-in cookie, and only for people who choose to sign in.
"""
import os
import secrets
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE = "mac_session"
MAX_AGE = 14 * 24 * 3600


def enabled() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def admins() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.environ.get("SESSION_KEY") or "local-only-key", salt="session")


def login_url(redirect_uri: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(16)
    q = urlencode({"client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": redirect_uri, "response_type": "code",
                   "scope": "openid email profile", "state": state, "prompt": "select_account"})
    return f"https://accounts.google.com/o/oauth2/v2/auth?{q}", state


def person_from_code(code: str, redirect_uri: str) -> dict | None:
    from google.auth.transport import requests as greq
    from google.oauth2 import id_token

    tok = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, timeout=10).json()
    info = id_token.verify_oauth2_token(tok["id_token"], greq.Request(), os.environ["GOOGLE_CLIENT_ID"])
    if not info.get("email_verified"):
        return None
    email = info["email"].lower()
    return {"email": email, "name": (info.get("name") or email.split("@")[0])[:60], "sub": info["sub"]}


def make_cookie(person: dict | str) -> str:
    if isinstance(person, str):
        person = {"email": person, "name": person.split("@")[0], "sub": person}
    return _signer().dumps(person)


def person(cookie: str | None) -> dict | None:
    """Whoever is signed in, or None."""
    if not cookie:
        return None
    try:
        p = _signer().loads(cookie, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return p if isinstance(p, dict) and p.get("email") else None


def who(cookie: str | None) -> str | None:
    """Mike's email when Mike is signed in; None for everyone else."""
    p = person(cookie)
    return p["email"] if p and p["email"] in admins() else None
