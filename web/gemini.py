"""One door to Gemini on Vertex AI (global endpoint; it isn't offered in us-east1).

Uses the site's own Google identity on Cloud Run, so there's no API key to keep.
"""
import json
import time

import httpx

# Gemini 4 Hydrogen since 2026-11-12 (GA that day; replaces the 3.x Flash line).
# To go back, swap the two lines below for: MODEL, MODEL_NAME = "gemini-3.5-flash", "Gemini 3.5 Flash"
# (3.5 was picked over 3.8 on 2026-10-23, when 3.8 Flash on Vertex stalled 15-90s on every project.)
MODEL = "gemini-4-hydrogen"
MODEL_NAME = "Gemini 4 Hydrogen"  # shown on the site's x-ray labels
# Hydrogen has no "off" for thinking: thinkingBudget and thinkingLevel MINIMAL are both a 400, so
# its lightest setting is LOW. 3.5 Flash could turn thinking off with a zero budget.
_THINK_OFF = {"thinkingBudget": 0} if MODEL == "gemini-3.5-flash" else {"thinkingLevel": "LOW"}
URL = f"https://aiplatform.googleapis.com/v1/projects/macmanager-home/locations/global/publishers/google/models/{MODEL}:generateContent"


def _token() -> str:
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def json_reply(contents: list[dict], system: str | None = None, schema: dict | None = None,
               max_tokens: int = 600, temperature: float = 0.4, timeout: float = 30, think: bool = True) -> dict:
    """Ask for a JSON answer; returns the parsed object. Raises on any failure.

    Thinking is LOW by default; think=False asks for the least the model allows (off on 3.5 Flash,
    which halved the pitch card's time; Hydrogen's floor is LOW, so there it's the same as think=True). A rate-limit (429), a Google-side error, or an answer that ran on past its length
    gets up to two more tries."""
    config = {"maxOutputTokens": max_tokens, "responseMimeType": "application/json", "temperature": temperature,
              "thinkingConfig": {"thinkingLevel": "LOW"} if think else _THINK_OFF}
    if schema:
        config["responseSchema"] = schema
    body = {"contents": contents, "generationConfig": config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    last = None
    for attempt in range(3):
        r = httpx.post(URL, json=body, headers={"Authorization": f"Bearer {_token()}"}, timeout=timeout)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        r.raise_for_status()
        cand = r.json()["candidates"][0]
        if cand.get("finishReason") in (None, "STOP"):
            break
        last = cand.get("finishReason")  # now and then it runs on repeating itself: try again
    else:
        raise RuntimeError(f"Gemini stopped early: {last}")
    return json.loads(cand["content"]["parts"][0]["text"])


def stream_json(contents: list[dict], system: str | None = None, schema: dict | None = None,
                max_tokens: int = 600, temperature: float = 0.4, wait: float = 90):
    """Like json_reply, but yields the answer's text as Gemini writes it (server-sent events).

    The caller joins the pieces and parses the JSON at the end. Only a failure before the first
    piece is retried (a 429 or a Google-side error); `wait` caps the gap between pieces."""
    config = {"maxOutputTokens": max_tokens, "responseMimeType": "application/json", "temperature": temperature,
              "thinkingConfig": {"thinkingLevel": "LOW"}}
    if schema:
        config["responseSchema"] = schema
    body = {"contents": contents, "generationConfig": config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    url = URL.replace(":generateContent", ":streamGenerateContent") + "?alt=sse"
    for attempt in range(3):
        with httpx.stream("POST", url, json=body, headers={"Authorization": f"Bearer {_token()}"},
                          timeout=httpx.Timeout(wait, connect=10)) as r:
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                cand = (json.loads(line[5:]).get("candidates") or [{}])[0]
                for part in (cand.get("content") or {}).get("parts") or []:
                    if part.get("text") and not part.get("thought"):
                        yield part["text"]
                if cand.get("finishReason") not in (None, "STOP"):
                    raise RuntimeError(f"Gemini stopped early: {cand['finishReason']}")
            return
