"""One door to Gemini 3.8 Flash on Vertex AI (global endpoint; it isn't offered in us-east1).

Uses the site's own Google identity on Cloud Run, so there's no API key to keep.
"""
import json
import time

import httpx

MODEL = "gemini-3.8-flash"
URL = f"https://aiplatform.googleapis.com/v1/projects/macmanager-home/locations/global/publishers/google/models/{MODEL}:generateContent"


def _token() -> str:
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def json_reply(contents: list[dict], system: str | None = None, schema: dict | None = None,
               max_tokens: int = 600, temperature: float = 0.4, timeout: float = 30) -> dict:
    """Ask for a JSON answer; returns the parsed object. Raises on any failure.

    Thinking is set LOW: on 3.8 Flash a zero thinking budget is not honored and answers ran
    long and slow. A rate-limit (429), a Google-side error, or an answer that ran on past its length
    gets up to two more tries."""
    config = {"maxOutputTokens": max_tokens, "responseMimeType": "application/json", "temperature": temperature,
              "thinkingConfig": {"thinkingLevel": "LOW"}}
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
