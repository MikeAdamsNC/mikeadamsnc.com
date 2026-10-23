"""The pitch bot: a chat that helps a visitor describe an idea, then hands Mike a tidy pitch.

The browser keeps the conversation and sends it each turn; the server keeps nothing until
the visitor confirms the summary. Words and rules live in content/bot.md.
"""
import json
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
        "chips": {"type": "STRING", "enum": ["kind", "purpose", "payment", "none"]},
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
    "required": ["reply", "chips", "ready"],
    "propertyOrdering": ["reply", "chips", "ready", "pitch"],  # reply first, so it can stream to the page
}
# The questions with fixed answers are buttons. The page asks the next one itself (no AI wait)
# after a button is tapped; the AI asks one only right after the visitor types.
CHIPS = {
    "kind": {"ask": "Is it an app, a website, or something else?", "why": "what kind of thing",
             "options": [["An app", "App"], ["A website", "Website"], ["Something else", "Something else"], ["Not sure", "Not sure"]]},
    "purpose": {"ask": "Who's it for?", "why": "who it's for",
                "options": [["Just me", "Personal use"], ["My business", "Business"], ["Something to sell", "Something to sell"], ["Not sure", "Not sure"]]},
    "payment": {"ask": "How would Mike fit in?", "why": "who pays",
                "options": [["I'd pay to have it built", "I'd pay you to build it"], ["Split what it earns", "Split what it earns"],
                            ["Just want it to exist", "Free, I just want it to exist"], ["Not sure", "Not sure"]]},
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
    """Local and test stand-in: asks one button question, then wraps up."""
    said = [m["text"] for m in messages if m["role"] == "user"]
    if len(said) < 2:
        return {"reply": "Love it. Is it an app, a website, or something else?", "chips": "kind", "ready": False}
    return {"reply": "Here's what I've got. Check it and send it to Mike.", "chips": "none", "ready": True,
            "pitch": {"type": "pitch", "what": said[0], "kind": "App" if "app" in said[1].lower() else "Not sure"}}


def partial_reply(buf: str) -> str:
    """The "reply" text so far from a JSON answer that is still arriving."""
    i = buf.find('"reply"')
    if i < 0:
        return ""
    j = buf.find('"', buf.find(":", i) + 1)
    if j < 0:
        return ""
    out, k = [], j + 1
    while k < len(buf):
        c = buf[k]
        if c == '"':
            break
        if c == "\\":
            if k + 1 >= len(buf):
                break
            n = buf[k + 1]
            if n == "u":
                if k + 6 > len(buf):
                    break
                out.append(chr(int(buf[k + 2:k + 6], 16)))
                k += 6
                continue
            out.append({"n": "\n", "t": "\t", "r": ""}.get(n, n))
            k += 2
            continue
        out.append(c)
        k += 1
    return "".join(out)


def _finish(out: dict) -> dict:
    reply = str(out.get("reply", "")).strip()[:1200] or "Tell me a bit more?"
    chips = out.get("chips") if out.get("chips") in CHIPS else None
    return {"reply": reply, "ready": bool(out.get("ready")), "chips": chips, "pitch": tidy(out.get("pitch"))}


def stream(messages: list[dict]):
    """The bot's next reply as it's written: yields ("delta", text) pieces, then ("done", answer).
    Raises Unavailable if the AI can't be reached before anything was said."""
    if not messages or messages[-1]["role"] != "user":
        yield "done", {"reply": GREETING, "ready": False, "chips": None, "pitch": tidy(None)}
        return
    if sum(1 for m in messages if m["role"] == "user") > MAX_TURNS:
        yield "done", {"reply": "We've covered a lot. Let's wrap up: check the summary and send it.", "ready": True,
                       "chips": None, "pitch": tidy(None)}
        return
    if os.environ.get("SITE_BACKEND") != "cloud":
        out = _fake(messages)
        for w in out["reply"].split(" "):
            yield "delta", w + " "
        yield "done", _finish(out)
        return
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["text"]}]} for m in messages]
    buf, said = "", ""
    try:
        for piece in gemini.stream_json(contents, system=rules(), schema=SCHEMA, max_tokens=1500):
            buf += piece
            now = partial_reply(buf)
            if len(now) > len(said):
                yield "delta", now[len(said):]
                said = now
        out = json.loads(buf)
    except Exception as e:
        log.warning("bot unavailable: %s", e)
        raise Unavailable from e
    yield "done", _finish(out)
