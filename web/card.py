"""The pitch card: a visitor's idea drawn as an App Store style listing with a phone screen.

The AI writes the words (rules in content/card.md) and picks an icon and a screen layout from
fixed lists; the page and the share image are always drawn by our own code, never by the AI.
The share image (1200 x 630, the size link previews use) is drawn here with Pillow.
"""
import functools
import hashlib
import io
import logging
import os
import pathlib
import re

from PIL import Image, ImageDraw, ImageFont

from . import gemini

log = logging.getLogger("card")
ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = ROOT / "content" / "card.md"
ICON_DIR = ROOT / "web" / "static" / "icons"
FONT = ROOT / "brand" / "fonts" / "Manrope-Variable.ttf"
ICONS = sorted(p.stem for p in ICON_DIR.glob("*.svg"))
HEROES = ["map", "chart", "calendar", "photo", "list"]
LIMITS = {"name": 22, "tagline": 90, "feature": 40, "title": 18, "row_title": 24, "row_sub": 34, "button": 16}
KIND_WORDS = {"App": "App", "Website": "Website"}
PURPOSE_WORDS = {"Personal use": "for personal use", "Business": "for a business", "Something to sell": "to sell"}
# Flat on purpose: with the screen as a nested object, 3.8 Flash often ran on inside it until it
# hit its length limit. The icon list goes in the instructions (Vertex refuses a 96-name enum).
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "tagline": {"type": "STRING"},
        "features": {"type": "ARRAY", "items": {"type": "STRING"}},
        "icon": {"type": "STRING"},
        "screen_title": {"type": "STRING"},
        "hero": {"type": "STRING", "enum": HEROES},
        "rows": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "sub": {"type": "STRING"}},
                                             "required": ["title", "sub"]}},
        "button": {"type": "STRING"},
    },
    "required": ["name", "tagline", "features", "icon", "screen_title", "hero", "rows", "button"],
    "propertyOrdering": ["name", "tagline", "features", "icon", "screen_title", "hero", "rows", "button"],
}


class Unavailable(Exception):
    pass


def _cut(s, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def tidy(card: dict | None) -> dict:
    """Only the fields we draw, each trimmed to fit; anything missing gets a plain default."""
    c = card or {}
    sc = c.get("screen") if isinstance(c.get("screen"), dict) else {}
    feats = [_cut(f, LIMITS["feature"]) for f in (c.get("features") or []) if isinstance(f, str) and f.strip()][:3]
    hero = sc.get("hero") if sc.get("hero") in HEROES else "list"
    rows = [{"title": _cut(r.get("title"), LIMITS["row_title"]), "sub": _cut(r.get("sub"), LIMITS["row_sub"])}
            for r in (sc.get("rows") or []) if isinstance(r, dict) and str(r.get("title") or "").strip()]
    rows = rows[:5 if hero == "list" else 3]
    return {
        "name": _cut(c.get("name"), LIMITS["name"]) or "Your idea",
        "tagline": _cut(c.get("tagline"), LIMITS["tagline"]),
        "features": feats,
        "icon": c.get("icon") if c.get("icon") in ICONS else "lightbulb",
        "screen": {
            "title": _cut(sc.get("title"), LIMITS["title"]) or "Home",
            "hero": hero,
            "rows": rows,
            "button": _cut(sc.get("button"), LIMITS["button"]),
        },
    }


def label(pitch: dict) -> str:
    """'App · for a business', from what the visitor actually said (never a guess)."""
    words = [KIND_WORDS.get(pitch.get("kind", ""), "Idea")]
    if pitch.get("purpose") in PURPOSE_WORDS:
        words.append(PURPOSE_WORDS[pitch["purpose"]])
    return " · ".join(words)


def first_name(name: str) -> str:
    return _cut((name or "").split(" ")[0], 20)


def text_of(card: dict) -> str:
    """Every word on the card, for the AI check before it gets a public link."""
    sc = card["screen"]
    parts = [card["name"], card["tagline"], *card["features"], sc["title"], sc["button"]]
    parts += [f"{r['title']} {r['sub']}" for r in sc["rows"]]
    return "\n".join(p for p in parts if p)


def _fake(pitch: dict) -> dict:
    """Local and test stand-in."""
    words = re.findall(r"[A-Za-z]+", pitch.get("what", "")) or ["Idea"]
    return {"name": words[0].capitalize() + "ly", "tagline": _cut(pitch.get("what"), 80),
            "features": ["Does the main thing", "Tells you when it matters", "Easy to share"], "icon": "sparkles",
            "screen": {"title": "Today", "hero": "map", "button": "Get started",
                       "rows": [{"title": "First thing", "sub": "0.3 mi · open now"}, {"title": "Second thing", "sub": "1.1 mi · in 20 min"},
                                {"title": "Third thing", "sub": "2 mi · tomorrow"}]}}


def make(pitch: dict) -> dict:
    """Ask the AI for a card for this pitch. Raises Unavailable if it can't be reached."""
    if os.environ.get("SITE_BACKEND") != "cloud":
        return tidy(_fake(pitch))
    facts = "\n".join(f"{k}: {pitch[k]}" for k in ("what", "kind", "purpose", "features", "marketing") if pitch.get(k))
    system = RULES.read_text().split("---", 1)[1].strip() + "\n\nIcons: " + ", ".join(ICONS)
    last = None
    for _ in range(2):  # now and then an answer hangs; a second try usually comes right back
        try:
            out = gemini.json_reply([{"role": "user", "parts": [{"text": "The pitch:\n" + facts}]}], system=system,
                                    schema=SCHEMA, max_tokens=1200, temperature=0.5, timeout=25)
            break
        except Exception as e:
            last = e
    else:
        log.warning("card unavailable: %s", last)
        raise Unavailable from last
    out["screen"] = {"title": out.get("screen_title"), "hero": out.get("hero"), "rows": out.get("rows"), "button": out.get("button")}
    return tidy(out)


@functools.cache
def icon_svg(name: str) -> str:
    """The icon's SVG for the page, sized by CSS."""
    svg = (ICON_DIR / f"{name if name in ICONS else 'lightbulb'}.svg").read_text()
    svg = re.sub(r"<!--.*?-->\s*", "", svg, flags=re.S)
    return re.sub(r'class="[^"]*"\s+xmlns', 'class="ico" aria-hidden="true" xmlns', svg).replace('width="24"', "").replace('height="24"', "")


# ---------- the share image ----------
FOAM, INK, WATER, AQUA, GREY, BODY, FRAME = "#F2F6F6", "#0B1620", "#0B6E7A", "#7FD6CF", "#5A6B76", "#33434F", "#1A2A37"


@functools.cache
def _font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_axes([weight])
    return f


@functools.cache
def _mask(name: str, size: int) -> Image.Image:
    m = Image.open(ICON_DIR / "mask" / f"{name if name in ICONS else 'lightbulb'}.png").getchannel("A")
    return m.resize((size, size), Image.LANCZOS)


def _icon(img: Image.Image, name: str, box: tuple[int, int, int], color: str) -> None:
    x, y, size = box
    img.paste(Image.new("RGB", (size, size), color), (x, y), _mask(name, size))


def _wrap(d: ImageDraw.ImageDraw, text: str, font, width: int, lines: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = w
    out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(".,;: ") + "…"
    return [line for line in out if line]


def _fit(d, text: str, font, width: int) -> str:
    while d.textlength(text, font=font) > width and len(text) > 2:
        text = text[:-2].rstrip() + "…"
    return text


def _hero(img, d, card: dict, x: int, y: int, w: int, h: int) -> None:
    kind = card["screen"]["hero"]
    seed = hashlib.sha256(card["name"].encode()).digest()
    if kind == "map":
        d.rounded_rectangle((x, y, x + w, y + h), 16, fill="#CDEBE8")
        d.line((x, y + h * 0.62, x + w, y + h * 0.38), fill="#E8F6F4", width=8)
        d.line((x + w * 0.3, y, x + w * 0.42, y + h), fill="#E8F6F4", width=6)
        cx, cy = x + w * 0.62, y + h * 0.42
        d.ellipse((cx - 17, cy - 17, cx + 17, cy + 17), fill="#A9D9D4")
        d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=WATER)
    elif kind == "chart":
        d.rounded_rectangle((x, y, x + w, y + h), 16, fill="#E6EFEF")
        n, gap = 7, 8
        bw = (w - 28 - gap * (n - 1)) / n
        for i in range(n):
            bh = (0.3 + 0.1 * i + (seed[i] % 20) / 100) * (h - 30)
            bx = x + 14 + i * (bw + gap)
            d.rounded_rectangle((bx, y + h - 14 - bh, bx + bw, y + h - 14), 4, fill=WATER if i == n - 1 else AQUA)
    elif kind == "calendar":
        d.rounded_rectangle((x, y, x + w, y + h), 16, fill="#E6EFEF")
        cols, rws, gap = 7, 4, 6
        cw, ch = (w - 24 - gap * (cols - 1)) / cols, (h - 24 - gap * (rws - 1)) / rws
        hot = {seed[0] % 28, seed[1] % 28, seed[2] % 28}
        for i in range(cols * rws):
            cx, cy = x + 12 + (i % cols) * (cw + gap), y + 12 + (i // cols) * (ch + gap)
            fill = WATER if i == min(hot) else AQUA if i in hot else "#FFFFFF"
            d.rounded_rectangle((cx, cy, cx + cw, cy + ch), 5, fill=fill)
    elif kind == "photo":
        d.rounded_rectangle((x, y, x + w, y + h), 16, fill=WATER)
        _icon(img, card["icon"], (int(x + w / 2 - 32), int(y + h / 2 - 32), 64), "#BFE8E4")


def png(card: dict, label_text: str, by: str) -> bytes:
    img = Image.new("RGB", (1200, 630), FOAM)
    d = ImageDraw.Draw(img)
    # the listing
    tile = Image.new("RGB", (150, 150))
    td = ImageDraw.Draw(tile)
    for i in range(150):  # top to bottom, a little deeper at the foot
        t = i / 149
        td.line((0, i, 150, i), fill=(int(14 - 3 * t), int(132 - 38 * t), int(146 - 42 * t)))
    rmask = Image.new("L", (150, 150), 0)
    ImageDraw.Draw(rmask).rounded_rectangle((0, 0, 149, 149), 36, fill=255)
    img.paste(tile, (64, 60), rmask)
    _icon(img, card["icon"], (93, 89, 92), "#FFFFFF")
    size = 76
    while size > 44 and d.textlength(card["name"], font=_font(size, 800)) > 470:
        size -= 4
    d.text((242, 135), card["name"], font=_font(size, 800), fill=INK, anchor="ls")
    d.text((244, 178), label_text, font=_font(22, 600), fill=WATER, anchor="ls")
    y = 262
    for line in _wrap(d, card["tagline"], _font(32, 600), 650, 2):
        d.text((64, y), line, font=_font(32, 600), fill=INK, anchor="ls")
        y += 42
    y += 22
    for f in card["features"]:
        d.ellipse((64, y - 22, 90, y + 4), fill=AQUA)
        d.line((71, y - 9, 76, y - 4, 84, y - 15), fill=INK, width=3, joint="curve")
        d.text((106, y), _fit(d, f, _font(24, 500), 600), font=_font(24, 500), fill=BODY, anchor="ls")
        y += 44
    x = 64
    for text, weight, color in (("pitched by ", 500, GREY), (by, 800, INK), (" on ", 500, GREY), ("MikeAdamsNC.com", 800, INK)) \
            if by else (("pitched on ", 500, GREY), ("MikeAdamsNC.com", 800, INK)):
        d.text((x, 572), text, font=_font(19, weight), fill=color, anchor="ls")
        x += d.textlength(text, font=_font(19, weight))
    # the phone
    d.rectangle((780, 0, 1200, 630), fill=INK)
    px, py, pw, ph = 865, 60, 250, 510
    d.rounded_rectangle((px, py, px + pw, py + ph), 42, fill=FRAME)
    d.rounded_rectangle((px + 10, py + 10, px + pw - 10, py + ph - 10), 33, fill="#FFFFFF")
    ix, iw = px + 26, pw - 52
    sc = card["screen"]
    d.text((ix, py + 52), _fit(d, sc["title"], _font(21, 800), iw), font=_font(21, 800), fill=INK, anchor="ls")
    y = py + 68
    if sc["hero"] != "list":
        _hero(img, d, card, ix, y, iw, 150)
        y += 162
    for r in sc["rows"]:
        d.rounded_rectangle((ix, y, ix + iw, y + 50), 12, fill=FOAM)
        d.text((ix + 12, y + 21), _fit(d, r["title"], _font(14, 700), iw - 24), font=_font(14, 700), fill=INK, anchor="ls")
        d.text((ix + 12, y + 39), _fit(d, r["sub"], _font(12, 500), iw - 24), font=_font(12, 500), fill=GREY, anchor="ls")
        y += 58
    if sc["button"]:
        by0 = py + ph - 66
        d.rounded_rectangle((ix, by0, ix + iw, by0 + 40), 12, fill=WATER)
        d.text((ix + iw / 2, by0 + 20), sc["button"], font=_font(15, 700), fill="#FFFFFF", anchor="mm")
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
