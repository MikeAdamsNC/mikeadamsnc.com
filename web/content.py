"""Reads the site's words from content/*.yaml. Edit those files, not the templates."""
import pathlib
from functools import lru_cache

import yaml

CONTENT = pathlib.Path(__file__).resolve().parent.parent / "content"
VERDICTS = {"worked": "Worked", "meh": "Meh", "flop": "Flop"}
STATUSES = {"running": "Running", "done": "Done", "retired": "Retired"}


@lru_cache
def site() -> dict:
    return yaml.safe_load((CONTENT / "site.yaml").read_text())


@lru_cache
def projects() -> list[dict]:
    return yaml.safe_load((CONTENT / "projects.yaml").read_text())


@lru_cache
def experiments() -> list[dict]:
    items = yaml.safe_load((CONTENT / "experiments.yaml").read_text())
    for n, e in enumerate(items, 1):
        e["number"] = f"EXP {n:02d}"
        e["verdict_label"] = VERDICTS[e["verdict"]]
        e["status_label"] = STATUSES[e["status"]]
    return items


def find(items: list[dict], slug: str) -> dict | None:
    return next((i for i in items if i["slug"] == slug), None)
