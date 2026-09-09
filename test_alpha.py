"""Transparency regression test: alpha must flatten onto WHITE for both
the Python pipeline and (conceptually) the HTML one."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402
import ascii_studio as A  # noqa: E402

OPTS = {"width": 40, "aspect": 2.0, "sharp": 0, "bright": 1.0,
        "contrast": 1.0, "gamma": 1.0, "ramp": 0, "invert": False,
        "color": False}
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


tmpdir = tempfile.mkdtemp(prefix="alpha_test_")

# 1) RGBA: left 3/4 opaque red, right 1/4 fully transparent with raw
#    RGB white stored underneath (common in real PNGs; with the old
#    alpha-dropping path this rendered as a dense '@' wall)
p1 = os.path.join(tmpdir, "rgba.png")
im = Image.new("RGBA", (160, 40), (255, 0, 0, 255))
px = im.load()
for y in range(40):
    for x in range(120, 160):
        px[x, y] = (255, 255, 255, 0)
im.save(p1)

art = A.build_art(p1, dict(OPTS))
left = {art.rows[y][x] for y in range(art.h) for x in range(10)}
right = {art.rows[y][x] for y in range(art.h) for x in range(35, art.w)}
check("RGBA: opaque red side renders as ':' (lum 76, default-10)",
      left == {":"})
check("RGBA: transparent side flattens to terminal bg -> ' ' (raw was black)",
      right == {" "})

# 2) Palette PNG with a tRNS entry: every pixel is the transparent index,
#    whose palette color is white
p2 = os.path.join(tmpdir, "pal.png")
pal = Image.new("P", (80, 40), 0)                 # idx 0 everywhere
pal.putpalette([255, 255, 255, 0, 0, 0] + [0, 0, 0] * 254)
pal.save(p2, transparency=0)                      # idx 0 transparent

art2 = A.build_art(p2, dict(OPTS))
allchars = set("".join(art2.rows))
check("palette+tRNS: fully transparent image -> all ' '", allchars == {" "})

print("ALPHA TEST " + ("FAILED" if fails else "OK"))
sys.exit(1 if fails else 0)
