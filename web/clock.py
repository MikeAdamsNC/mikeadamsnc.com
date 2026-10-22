"""Every time on the site is Eastern, with its offset."""
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def now() -> datetime:
    return datetime.now(EASTERN)


def stamp() -> str:
    return now().isoformat(timespec="seconds")


def today() -> str:
    return now().date().isoformat()
