"""Our own analytics: one row per page view or interaction, written to BigQuery.

No cookies. A visitor id is a hash of the day's random salt, the IP address and the
browser, so the same person is one visitor today and a stranger tomorrow.
"""
import hashlib
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

from . import clock

log = logging.getLogger("analytics")
TABLE = "macmanager-home.site_analytics.events"
BOTS = re.compile(r"bot|crawl|spider|slurp|preview|scheduler|monitor|curl|wget|python-|httpx|headless", re.I)
EVENT_KINDS = {"scroll", "xray_open", "xray_close", "outbound", "pitch_start", "cta", "version_pick", "terminal_command", "card_share"}


def visitor_id(salt: bytes, ip: str, ua: str) -> str:
    return hashlib.sha256(salt + ip.encode() + b"|" + ua.encode()).hexdigest()[:16]


def describe(ua: str) -> tuple[str, str, bool]:
    """(device, browser, is_bot) from a user-agent string."""
    is_bot = bool(BOTS.search(ua or "")) or not ua
    device = "tablet" if re.search(r"iPad|Tablet", ua or "") else "phone" if re.search(r"Mobi|iPhone|Android", ua or "") else "computer"
    browser = next((b for b, pat in [("Edge", "Edg/"), ("Chrome", "Chrome/"), ("Firefox", "Firefox/"), ("Safari", "Safari/")] if pat in (ua or "")), "other")
    return device, browser, is_bot


def referrer_host(ref: str | None, own: str = "mikeadamsnc.com") -> str | None:
    host = urlparse(ref or "").hostname
    if not host or host.endswith(own) or host.endswith(".run.app"):
        return None
    return host.removeprefix("www.")


def row(kind: str, **f) -> dict:
    return {"ts": datetime.now(timezone.utc).isoformat(), "ts_eastern": clock.stamp(), "kind": kind, **f}


class MemoryRecorder:
    def __init__(self):
        self.rows: list[dict] = []

    def record(self, r: dict) -> None:
        self.rows.append(r)

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        return []

    def pages_today(self) -> int:
        today = clock.today()
        return sum(1 for r in self.rows if r["kind"] == "page_view" and r["ts_eastern"].startswith(today))


class BigQueryRecorder:
    def __init__(self):
        from google.cloud import bigquery

        self.bq = bigquery
        self.client = bigquery.Client(project="macmanager-home")
        self.pool = ThreadPoolExecutor(max_workers=2)
        self._today: tuple[str, float, int] | None = None

    def record(self, r: dict) -> None:
        def send():
            errors = self.client.insert_rows_json(TABLE, [r])
            if errors:
                log.warning("analytics insert failed: %s", errors)

        self.pool.submit(send)

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        qp = [self.bq.ScalarQueryParameter(k, "INT64" if isinstance(v, int) else "STRING", v) for k, v in (params or {}).items()]
        job = self.client.query(sql, job_config=self.bq.QueryJobConfig(query_parameters=qp))
        return [dict(r) for r in job.result()]

    def pages_today(self) -> int:
        """Cached for five minutes; the X-ray panel shows it."""
        import time

        day = clock.today()
        if self._today and self._today[0] == day and time.time() - self._today[1] < 300:
            return self._today[2]
        rows = self.query(
            f"SELECT COUNT(*) n FROM `{TABLE}` WHERE kind='page_view' AND ts >= TIMESTAMP(@day, 'America/New_York')",
            {"day": day},
        )
        n = rows[0]["n"] if rows else 0
        self._today = (day, time.time(), n)
        return n


def make_recorder():
    return BigQueryRecorder() if os.environ.get("SITE_BACKEND") == "cloud" else MemoryRecorder()
