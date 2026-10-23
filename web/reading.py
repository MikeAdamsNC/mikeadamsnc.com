"""'What I'm reading': a few AI and tech stories a day from publishers' RSS feeds.

Shown: the headline, the source, a link out, and one line of our own. Feed summaries are
read only to choose; they're never shown. Refreshed about hourly, inside the keep-warm ping's request.
"""
import hashlib
import logging
import os
import pathlib
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache

import httpx
import yaml

from . import clock

log = logging.getLogger("reading")
FILE = pathlib.Path(__file__).resolve().parent.parent / "content" / "reading.yaml"
UA = "MikeAdamsNC.com reader (+https://mikeadamsnc.com)"
REFRESH_MIN = 55
_lock = threading.Lock()


@lru_cache
def config() -> tuple[dict, str]:
    head, prompt = FILE.read_text().split("\n---\n", 1)
    return yaml.safe_load(head), prompt.strip()


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _text(el) -> str:
    return re.sub(r"<[^>]+>", " ", "".join(el.itertext()) if el is not None else "").strip()


def parse(xml: bytes, source: str) -> list[dict]:
    """RSS 2.0 or Atom into [{title, link, source, published, summary}]."""
    root = ET.fromstring(xml)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        get = {c.tag.split("}")[-1]: c for c in it}
        title = _text(get.get("title"))
        link = ""
        if "link" in get:
            ln = get["link"]
            link = (ln.text or "").strip() or ln.get("href", "")
        for c in it:
            if c.tag.split("}")[-1] == "link" and c.get("rel", "alternate") == "alternate" and c.get("href"):
                link = c.get("href")
        first = lambda *names: next((get[n] for n in names if get.get(n) is not None), None)  # noqa: E731
        stamp = first("pubDate", "published", "updated", "date")  # (an element with no children is falsy)
        when = _when(stamp.text if stamp is not None else None)
        summary = _text(first("description", "summary", "content"))[:400]
        if title and link.startswith("http"):
            out.append({"title": " ".join(title.split())[:200], "link": link, "source": source,
                        "published": when, "summary": " ".join(summary.split())})
    return out


def key(link: str) -> str:
    return hashlib.sha1(link.split("?")[0].rstrip("/").encode()).hexdigest()[:16]


def candidates(fetch=None, hours: int = 36) -> list[dict]:
    cfg, _ = config()
    fetch = fetch or (lambda url: httpx.get(url, headers={"User-Agent": UA}, timeout=15, follow_redirects=True).content)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    def one(f):
        try:
            items = parse(fetch(f["url"]), f["name"])
        except Exception as e:
            log.warning("feed %s unreadable: %s", f["name"], e)
            return []
        return [i for i in items if i["published"] and i["published"] >= since][:12]

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [i for batch in pool.map(one, cfg["feeds"]) for i in batch]


def _gemini_pick(cands: list[dict], n: int) -> list[dict]:
    from . import gemini

    _, prompt = config()
    listing = "\n".join(f"{i}. [{c['source']}] {c['title']}: {c['summary'][:220]}" for i, c in enumerate(cands))
    schema = {"type": "OBJECT", "properties": {"picks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "i": {"type": "INTEGER"}, "line": {"type": "STRING"}}, "required": ["i", "line"]}}}, "required": ["picks"]}
    out = gemini.json_reply([{"role": "user", "parts": [{"text": f"N = {n}\n\nCandidates:\n{listing}"}]}],
                            system=prompt, schema=schema, max_tokens=2000, temperature=0.3)
    return out.get("picks", [])


def _fake_pick(cands: list[dict], n: int) -> list[dict]:
    return [{"i": i, "line": "Worth a look for anyone building with new tools."} for i in range(min(n, len(cands)))]


def refresh(store, fetch=None, pick=None) -> str:
    """Pick new stories and save them. Safe to call often; does nothing if one is running."""
    if not _lock.acquire(blocking=False):
        return "already running"
    try:
        cfg, _ = config()
        have = store.reading_keys()
        cands = [c for c in candidates(fetch) if key(c["link"]) not in have]
        seen, fresh = set(), []
        for c in sorted(cands, key=lambda c: c["published"], reverse=True):  # one copy per headline
            k = c["title"].lower()[:60]
            if k not in seen:
                seen.add(k)
                fresh.append(c)
        fresh = fresh[:40]
        store.set_reading_refreshed(time.time())
        if not fresh:
            return "nothing new"
        pick = pick or (_gemini_pick if os.environ.get("SITE_BACKEND") == "cloud" else _fake_pick)
        picks = pick(fresh, cfg["pick_per_refresh"])
        saved = 0
        for p in picks[: cfg["pick_per_refresh"]]:
            i = p.get("i")
            if not isinstance(i, int) or not 0 <= i < len(fresh):
                continue
            c = fresh[i]
            store.add_reading(key(c["link"]), {"title": c["title"], "link": c["link"], "source": c["source"],
                                               "published": c["published"].isoformat(),
                                               "line": str(p.get("line", "")).strip()[:200], "picked_at": clock.stamp()})
            saved += 1
        for c in fresh:  # remember what was passed over so it isn't offered again
            store.skip_reading(key(c["link"]))
        store.prune_reading(cfg["keep_days"])
        return f"{saved} picked from {len(fresh)} new"
    finally:
        _lock.release()


def refresh_if_due(store) -> str:
    """Run inside the keep-warm request: Cloud Run pauses the processor once a request is
    answered, so background threads never finish. The scheduler waits up to 3 minutes."""
    if os.environ.get("SITE_BACKEND") != "cloud":  # only the real site reads the feeds on its own
        return "local"
    try:
        if time.time() - (store.reading_refreshed() or 0) < REFRESH_MIN * 60:
            return "not due"
        out = refresh(store)
    except Exception as e:
        log.warning("reading refresh failed: %s", e)
        return "failed"
    log.info("reading: %s", out)
    return out
