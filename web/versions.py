"""Versions of the site: each is a different home page over the same content."""
import pathlib
from functools import lru_cache

import yaml

FILE = pathlib.Path(__file__).resolve().parent.parent / "content" / "versions.yaml"


@lru_cache
def all() -> list[dict]:  # noqa: A001
    return yaml.safe_load(FILE.read_text())


def slugs() -> set[str]:
    return {v["slug"] for v in all()}
