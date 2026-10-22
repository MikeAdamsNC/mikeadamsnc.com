"""How the Lab orders experiments: hot, new or top."""
import math
from datetime import date, datetime

from . import clock

EPOCH = datetime(2026, 1, 1, tzinfo=clock.EASTERN).timestamp()


def hot(up: int, down: int, added: str) -> float:
    """Reddit's idea: votes count on a log scale, and newer things get a steady head start
    (every 12.5 hours of newness is worth ten times the votes). Unlike Reddit's, a single
    vote counts (log of score + 1), since a small site lives on a handful of votes."""
    score = up - down
    order = math.log10(abs(score) + 1)
    sign = 1 if score > 0 else -1 if score < 0 else 0
    when = datetime.combine(date.fromisoformat(str(added)), datetime.min.time(), tzinfo=clock.EASTERN).timestamp()
    return round(sign * order + (when - EPOCH) / 45000, 7)


def order(experiments: list[dict], tallies: dict[str, dict], how: str) -> list[dict]:
    def t(e):
        return tallies.get(e["slug"], {"up": 0, "down": 0})
    if how == "new":
        return sorted(experiments, key=lambda e: str(e.get("added", "")), reverse=True)
    if how == "top":
        return sorted(experiments, key=lambda e: t(e)["up"] - t(e)["down"], reverse=True)
    return sorted(experiments, key=lambda e: hot(t(e)["up"], t(e)["down"], e.get("added", "2026-10-22")), reverse=True)
