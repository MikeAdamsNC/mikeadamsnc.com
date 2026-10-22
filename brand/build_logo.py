"""Builds every MikeAdamsNC logo and icon file from one definition.

Run: python brand/build_logo.py   (needs fonttools and uharfbuzz)
The letters come from Manrope ExtraBold, turned into shapes so the files need no font.
The M and the A are custom peaks: the "mountains" in Mountains to Sea.
"""
import io, pathlib
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

HERE = pathlib.Path(__file__).parent
INK, WATER, AQUA, WHITE = "#0B1620", "#0B6E7A", "#7FD6CF", "#FFFFFF"

# The peaks, drawn in a box 100 tall (0 = summit line, 100 = baseline).
PEAK_M = (128, [(0,100),(32,0),(64,64),(96,0),(128,100),(105,100),(96,34),(70,88),(58,88),(32,34),(23,100)])
PEAK_A = (100, [(0,100),(50,0),(100,100),(76,100),(50,32),(24,100)])
PEAK_HEIGHT = 1.116      # peaks stand this much taller than the capital letters
SMALL_PEAK_HEIGHT = 1.04 # for tiny uses (email signatures), peaks closer to the letters
SIDE = 0.0128            # space on each side of a peak, in em
TRACK = -0.02            # letter spacing, in em

def load_font():
    f = TTFont(HERE / "fonts" / "Manrope-Variable.ttf")
    f = instancer.instantiateVariableFont(f, {"wght": 800})
    buf = io.BytesIO(); f.save(buf)
    return f, buf.getvalue()

FONT, FONT_BYTES = load_font()
UPEM = FONT["head"].unitsPerEm
CAP = FONT["OS/2"].sCapHeight
GLYPHS = FONT.getGlyphSet()
HB_FONT = hb.Font(hb.Face(FONT_BYTES))

def run_text(text, x, color):
    """Shapes a run of text with kerning; returns (svg paths, new x, bounds)."""
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(HB_FONT, buf, {"kern": True, "liga": True})
    order = FONT.getGlyphOrder()
    out, lo, hi = [], None, None
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = order[info.codepoint]
        pen = SVGPathPen(GLYPHS)
        GLYPHS[name].draw(TransformPen(pen, (1, 0, 0, -1, x + pos.x_offset, 0)))
        bp = BoundsPen(GLYPHS); GLYPHS[name].draw(bp)
        if bp.bounds:
            lo = min(lo, bp.bounds[3]) if lo is not None else bp.bounds[3]
        out.append(f'<path fill="{color}" d="{pen.getCommands()}"/>')
        x += pos.x_advance + TRACK * UPEM
    return out, x, lo

def peak(shape, x, color, ratio):
    w, pts = shape
    h = ratio * CAP
    s = h / 100
    x += SIDE * UPEM
    d = "M" + " L".join(f"{x + px*s:.1f} {-(100-py)*s:.1f}" for px, py in pts) + " Z"
    x += w * s + SIDE * UPEM + TRACK * UPEM
    return [f'<path fill="{color}" d="{d}"/>'], x, h

def wordmark(main, accent, ratio=PEAK_HEIGHT, pad=0.06):
    parts, x, top = [], 0.0, 0.0
    for kind, val, col in [("p", PEAK_M, main), ("t", "ike", main), ("p", PEAK_A, main),
                           ("t", "dams", main), ("t", "NC", accent)]:
        if kind == "p":
            p, x, h = peak(val, x, col, ratio); top = max(top, h)
        else:
            p, x, h = run_text(val, x, col); top = max(top, h or 0)
        parts += p
    width = x - TRACK * UPEM
    padu = pad * UPEM
    vb = f"{-padu:.0f} {-(top + padu):.0f} {width + 2*padu:.0f} {top + 2*padu:.0f}"
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">' + "".join(parts) + "</svg>"

def icon(bg=WATER, fg=WHITE, size=512):
    """The peak M alone, centered in a rounded square."""
    w, pts = PEAK_M
    mw = size * 0.62
    s = mw / w
    ox, oy = (size - mw) / 2, (size - 100 * s) / 2 + size * 0.01
    d = "M" + " L".join(f"{ox + px*s:.1f} {oy + py*s:.1f}" for px, py in pts) + " Z"
    r = size * 0.225
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">'
            f'<rect width="{size}" height="{size}" rx="{r:.0f}" fill="{bg}"/><path fill="{fg}" d="{d}"/></svg>')

def mark(color=WATER, size=512):
    """The peak M alone, no square (for places that supply their own background)."""
    w, pts = PEAK_M
    s = size / w
    d = "M" + " L".join(f"{px*s:.1f} {py*s:.1f}" for px, py in pts) + " Z"
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {100*s:.1f}"><path fill="{color}" d="{d}"/></svg>'

FILES = {
    "logo/mikeadamsnc.svg":            wordmark(INK, WATER),
    "logo/mikeadamsnc-reversed.svg":   wordmark(WHITE, AQUA),
    "logo/mikeadamsnc-ink.svg":        wordmark(INK, INK),
    "logo/mikeadamsnc-white.svg":      wordmark(WHITE, WHITE),
    "logo/mikeadamsnc-small.svg":      wordmark(INK, WATER, SMALL_PEAK_HEIGHT),
    "icon/icon.svg":                   icon(),
    "icon/mark.svg":                   mark(),
    "icon/mark-white.svg":             mark(WHITE),
}

if __name__ == "__main__":
    for rel, svg in FILES.items():
        (HERE / rel).write_text(svg)
        print("wrote", rel)
