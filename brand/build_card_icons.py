"""Draws each pitch-card icon (web/static/icons/*.svg, Lucide, ISC) as a PNG mask for the
server-drawn share image (web/card.py tints them). Run after adding an icon:
    .venv/bin/python brand/build_card_icons.py   (needs: pip install resvg-py)
"""
import pathlib
import re

import resvg_py

ICONS = pathlib.Path(__file__).resolve().parent.parent / "web" / "static" / "icons"
OUT = ICONS / "mask"
OUT.mkdir(exist_ok=True)
for svg in sorted(ICONS.glob("*.svg")):
    text = re.sub(r'width="24"\s+height="24"', 'width="192" height="192"', svg.read_text()).replace("currentColor", "#000")
    (OUT / f"{svg.stem}.png").write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=text)))
print(len(list(OUT.glob("*.png"))), "masks")
