"""The pitch bot: a chat that helps a visitor describe an idea, then hands Mike a tidy pitch.

The browser keeps the conversation and sends it each turn; the server keeps nothing until
the visitor confirms the summary. Words and rules live in content/bot.md.
"""
import logging
import os
import pathlib

from . import gemini

log = logging.getLogger("bot")
RULES = pathlib.Path(__file__).resolve().parent.parent / "content" / "bot.md"
MAX_TURNS = 20
MAX_CHARS = 1500
GREETING = ("Hi! I'm an AI that helps Mike collect ideas. He reads every one himself. "
            "What would you like built? Or, if you have a suggestion for this site, tell me that.")
KINDS = ["App", "Website", "Something else", "Not sure", ""]
PURPOSES = ["Personal use", "Business", "Something to sell", "Not sure", ""]
PAY = ["I'd pay you to build it", "Split what it earns", "Free, I just want it to exist", "Not sure", ""]
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reply": {"type": "STRING"},
        "ready": {"type": "BOOLEAN"},
        "pitch": {"type": "OBJECT", "properties": {
            "type": {"type": "STRING", "enum": ["pitch", "site idea"]},
            "what": {"type": "STRING"},
            "kind": {"type": "STRING", "enum": [k for k in KINDS if k]},
            "purpose": {"type": "STRING", "enum": [k for k in PURPOSES if k]},
            "payment": {"type": "STRING", "enum": [k for k in PAY if k]},
            "features": {"type": "STRING"},
            "marketing": {"type": "STRING"},
            "name": {"type": "STRING"},
            "email": {"type": "STRING"},
        }},
    },
    "required": ["reply", "ready"],
}


class Unavailable(Exception):
    pass


def rules() -> str:
    return RULES.read_text().split("---", 1)[1].strip()


def clean(messages: list) -> list[dict]:
    """Only what the browser may send: alternating user/bot text, trimmed and capped."""
    out = []
    for m in messages[-MAX_TURNS * 2:]:
        if isinstance(m, dict) and m.get("role") in ("user", "bot") and isinstance(m.get("text"), str):
            out.append({"role": m["role"], "text": m["text"].strip()[:MAX_CHARS]})
    return [m for m in out if m["text"]]


def tidy(pitch: dict | None) -> dict:
    p = pitch or {}
    t = {k: str(p.get(k, "") or "").strip()[:4000] for k in ("what", "kind", "purpose", "payment", "features", "marketing", "name", "email")}
    t["type"] = "site idea" if p.get("type") == "site idea" else "pitch"
    for k, allowed in (("kind", KINDS), ("purpose", PURPOSES), ("payment", PAY)):
        if t[k] not in allowed:
            t[k] = ""
    if t["type"] == "site idea":  # these questions are for pitches; don't keep guesses
        t["kind"] = t["purpose"] = t["payment"] = ""
    if t["email"] and "@" not in t["email"]:
        t["email"] = ""
    return t


def _fake(messages: list[dict]) -> dict:
    """Local and test stand-in: asks one follow-up, then wraps up."""
    said = [m["text"] for m in messages if m["role"] == "user"]
    if len(said) < 2:
        return {"reply": "Love it. Is it an app, a website, or something else?", "ready": False}
    return {"reply": "Here's what I've got. Check it and send it to Mike.", "ready": True,
            "pitch": {"type": "pitch", "what": said[0], "kind": "App" if "app" in said[1].lower() else "Not sure"}}


def turn(messages: list[dict]) -> dict:
    """The bot's next reply: {"reply", "ready", "pitch"}."""
    if not messages or messages[-1]["role"] != "user":
        return {"reply": GREETING, "ready": False, "pitch": tidy(None)}
    if sum(1 for m in messages if m["role"] == "user") > MAX_TURNS:
        return {"reply": "We've covered a lot. Let's wrap up: check the summary and send it.", "ready": True,
                "pitch": tidy(None)}
    if os.environ.get("SITE_BACKEND") != "cloud":
        out = _fake(messages)
    else:
        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["text"]}]} for m in messages]
        try:
            out = gemini.json_reply(contents, system=rules(), schema=SCHEMA, max_tokens=1500)
        except Exception as e:
            log.warning("bot unavailable: %s", e)
            raise Unavailable from e
    reply = str(out.get("reply", "")).strip()[:1200] or "Tell me a bit more?"
    return {"reply": reply, "ready": bool(out.get("ready")), "pitch": tidy(out.get("pitch"))}
