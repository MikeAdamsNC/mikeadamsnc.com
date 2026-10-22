"""The AI check every comment gets before it posts (Gemini 3.8 Flash on Vertex AI).

"ok" posts at once; "hold" waits for Mike on the dashboard. If the AI can't be reached,
the comment is held, never posted unchecked.
"""
import json
import logging
import os
import re

import httpx

log = logging.getLogger("moderate")
MODEL = "gemini-3.8-flash"
URL = f"https://aiplatform.googleapis.com/v1/projects/macmanager-home/locations/global/publishers/google/models/{MODEL}:generateContent"
PROMPT = """You check comments left on a personal website's experiment pages before they're shown.
Answer "hold" for: spam or ads, links meant to sell or scam, harassment, hate, threats, sexual content,
someone's private information, or gibberish. Answer "ok" for anything else, including criticism,
disagreement, jokes and short reactions. Reply as JSON: {"verdict": "ok" or "hold", "reason": "a few words"}.

Experiment: EXPERIMENT
Comment: COMMENT"""


def _token() -> str:
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _gemini(experiment: str, comment: str) -> tuple[str, str]:
    body = {"contents": [{"role": "user", "parts": [{"text": PROMPT.replace("EXPERIMENT", experiment).replace("COMMENT", comment)}]}],
            "generationConfig": {"maxOutputTokens": 300, "responseMimeType": "application/json", "temperature": 0,
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    r = httpx.post(URL, json=body, headers={"Authorization": f"Bearer {_token()}"}, timeout=20)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    out = json.loads(text)
    verdict = "ok" if out.get("verdict") == "ok" else "hold"
    return verdict, str(out.get("reason", ""))[:120]


def _simple(comment: str) -> tuple[str, str]:
    """Local and test stand-in: hold link-stuffed or shouty comments."""
    if len(re.findall(r"https?://", comment)) >= 2 or "buy now" in comment.lower():
        return "hold", "looks like spam"
    return "ok", "fine"


def check(experiment: str, comment: str) -> tuple[str, str]:
    if os.environ.get("SITE_BACKEND") != "cloud":
        return _simple(comment)
    try:
        return _gemini(experiment, comment)
    except Exception as e:  # never post unchecked
        log.warning("moderation unavailable: %s", e)
        return "hold", "AI check unavailable"
