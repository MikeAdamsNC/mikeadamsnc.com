"""'Talk to it': answers questions about the site from the site's own content."""
import json
import logging
import os
import pathlib

from . import bot, content, gemini

log = logging.getLogger("talk")
RULES = pathlib.Path(__file__).resolve().parent.parent / "content" / "talk.md"
SCHEMA = {"type": "OBJECT", "properties": {
    "reply": {"type": "STRING"},
    "links": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"label": {"type": "STRING"}, "path": {"type": "STRING"}}}},
}, "required": ["reply"]}


def known_paths() -> dict[str, str]:
    paths = {"/lab": "The Lab", "/pitch": "Pitch an idea", "/": "Home", "/privacy": "Privacy"}
    paths |= {f"/projects/{p['slug']}": p["name"] for p in content.projects()}
    paths |= {f"/lab/{e['slug']}": e["title"] for e in content.experiments()}
    return paths


def site_facts() -> str:
    s = content.site()
    facts = {
        "about": s["about"], "headline": s["headline"], "experimenting_with": s["experimenting_with"],
        "projects": [{k: p.get(k) for k in ("name", "line", "body", "status", "built_with")} | {"path": f"/projects/{p['slug']}"} for p in content.projects()],
        "experiments": [{k: e.get(k) for k in ("title", "hook", "question", "result", "verdict", "verdict_line", "status", "used")} | {"path": f"/lab/{e['slug']}"} for e in content.experiments()],
        "pages": known_paths(),
    }
    return json.dumps(facts, ensure_ascii=False)


def rules() -> str:
    return RULES.read_text().split("---", 1)[1].strip() + "\n\nSite content:\n" + site_facts()


def _fake(question: str) -> dict:
    q = question.lower()
    for e in content.experiments():
        if any(w in q for w in e["slug"].split("-") if len(w) > 3):
            return {"reply": f"{e['title']} {e['hook']}", "links": [{"label": e["title"], "path": f"/lab/{e['slug']}"}]}
    return {"reply": "I can tell you about Mike's projects and experiments. Try asking about the grill or the radar.",
            "links": [{"label": "The Lab", "path": "/lab"}]}


def answer(messages: list[dict]) -> dict:
    if not messages or messages[-1]["role"] != "user":
        raise ValueError("nothing asked")
    if os.environ.get("SITE_BACKEND") != "cloud":
        out = _fake(messages[-1]["text"])
    else:
        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["text"]}]} for m in messages]
        try:
            out = gemini.json_reply(contents, system=rules(), schema=SCHEMA, max_tokens=1500)
        except Exception as e:
            log.warning("talk unavailable: %s", e)
            raise bot.Unavailable from e
    paths = known_paths()
    links = []
    for link in out.get("links") or []:
        path = str(link.get("path", ""))
        if path in paths and path not in [x["path"] for x in links]:
            links.append({"label": str(link.get("label") or paths[path])[:60], "path": path})
    return {"reply": str(out.get("reply", "")).strip()[:1500] or "Ask me about a project or an experiment.", "links": links[:3]}
