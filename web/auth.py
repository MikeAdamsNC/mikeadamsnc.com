"""Sign in with Google for Mike's private pages (/admin). Only ADMIN_EMAILS get in.

Turned on once GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set. The only cookie the
site ever sets is this sign-in cookie, and only for Mike.
"""
import os
import secrets
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE = "mac_admin"
MAX_AGE = 14 * 24 * 3600


def enabled() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def admins() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.environ.get("SESSION_KEY") or "local-only-key", salt="admin")


def login_url(redirect_uri: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(16)
    q = urlencode({"client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": redirect_uri, "response_type": "code",
                   "scope": "openid email", "state": state, "prompt": "select_account"})
    return f"https://accounts.google.com/o/oauth2/v2/auth?{q}", state


def email_from_code(code: str, redirect_uri: str) -> str | None:
    from google.auth.transport import requests as greq
    from google.oauth2 import id_token

    tok = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, timeout=10).json()
    info = id_token.verify_oauth2_token(tok["id_token"], greq.Request(), os.environ["GOOGLE_CLIENT_ID"])
    return info["email"].lower() if info.get("email_verified") else None


def make_cookie(email: str) -> str:
    return _signer().dumps({"email": email})


def who(cookie: str | None) -> str | None:
    if not cookie:
        return None
    try:
        email = _signer().loads(cookie, max_age=MAX_AGE)["email"]
    except (BadSignature, SignatureExpired, KeyError):
        return None
    return email if email in admins() else None
