#!/usr/bin/env python3
"""
ASCII STUDIO — interactive image -> ASCII converter (curses TUI).

  * 16 character ramps: defaults, CP437 (shades/mix/blocks/dense), braille...
  * Sharpness (unsharp mask), brightness, contrast, gamma, cell aspect
  * Output width 16..3000
  * 256-palette color in the TUI + truecolor 24-bit .ans export
  * Pan/zoom preview, invert, file browser, .txt/.ans export

Run:  python3 ascii_studio.py [image]     (--selftest = headless test)
"""

import curses
import glob
import os
import sys
import time

from PIL import Image, ImageEnhance, ImageFilter

# ---------------------------------------------------------------------------
# Character ramps (dark -> light). CP437 glyphs are real CP437 codepoints.
# ---------------------------------------------------------------------------
RAMPS = [
    ("default-10",   " .:-=+*#%@"),
    ("classic-70",   "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "),
    ("minimal-4",    " .#@"),
    ("detailed-12",  " .,:;irsXA253hMHGS#9B&@"),
    ("heavy-14",     " .`^\",:;Il!i~+_-?][}{1)(|/tfjrxnuvczmwqpdbkhao*#MW&8%B@$"),
    ("cp437-shades", " ░▒▓█"),
    ("cp437-mix",    " ·:∙+▒░▓█"),
    ("cp437-blocks", "▁▂▃▄▅▆▇█"),
    ("cp437-dense",  " .·:!i│║░▒▓█"),
    ("braille",      " ⠁⠂⠃⠇⠏⠟⠿⡿⣿"),
    ("binary",       " .01"),
    ("pure-binary",  "01"),
    ("dots",         " ·•●◉█"),
    ("tech",         " .,_-~+=*%#$@"),
    ("greek",        " ·εδξσφψΩ"),
    ("arrows",       " ·:↑↗→↘↓↙←↖█"),
]

MAX_W = 3000
MIN_W = 16
ASPECTS = [1.6, 1.8, 2.0, 2.2, 2.4]   # cell height / cell width
ZOOMS = [1, 2, 3, 4, 6, 8]
IMG_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.webp",
            "*.tif", "*.tiff", "*.ppm", "*.pgm")

# ---------------------------------------------------------------------------
# xterm-256 palette (in-TUI color: 6x6x6 cube + grayscale, NOT just base ANSI)
# ---------------------------------------------------------------------------

def _xterm_table():
    tbl = [(0, 0, 0)] * 256
    base = [0, 95, 135, 175, 215, 255]
    for i in range(16, 232):
        n = i - 16
        tbl[i] = (base[n // 36], base[(n // 6) % 6], base[n % 6])
    for i in range(232, 256):
        v = 8 + 10 * (i - 232)
        tbl[i] = (v, v, v)
    std = [(0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),
           (0,128,128),(192,192,192),(128,128,128),(255,0,0),(0,255,0),
           (255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255)]
    tbl[:16] = std
    return tbl

XTERM = _xterm_table()

def nearest_xterm(rgb):
    r, g, b = rgb
    best, bd = 0, 1 << 30
    for i in range(256):
        tr, tg, tb = XTERM[i]
        d = (r-tr)*(r-tr) + (g-tg)*(g-tg) + (b-tb)*(b-tb)
        if d < bd:
            bd, best = d, i
            if d == 0:
                break
    return best

# ---------------------------------------------------------------------------
# Pipeline: image -> char rows (+ palette-index bytes when color is on)
# ---------------------------------------------------------------------------

class Art:
    __slots__ = ("rows", "pidx", "w", "h", "rgb", "path", "secs")


def build_art(path, o):
    t0 = time.time()
    im = Image.open(path)
    if "A" in im.getbands() or im.mode == "P":
        # Flatten transparency onto the viewing background. This tool draws
        # on a (typical) dark terminal with bright=dense ramps, so "empty"
        # must be BLACK -> ' ' shows the terminal through. convert("RGB")
        # alone would just expose raw (arbitrary) RGB under the alpha.
        rgba = im.convert("RGBA")
        base = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        base.alpha_composite(rgba)
        im = base
    im = im.convert("RGB")
    ow, oh = im.size
    w = max(1, min(MAX_W, o["width"]))
    h = max(1, round(oh * (w / ow) / o["aspect"]))
    im = im.resize((w, h), Image.Resampling.LANCZOS)

    if o["sharp"] > 0:
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=o["sharp"],
                                               threshold=2))
    if o["bright"] != 1.0:
        im = ImageEnhance.Brightness(im).enhance(o["bright"])
    if o["contrast"] != 1.0:
        im = ImageEnhance.Contrast(im).enhance(o["contrast"])
    if o["gamma"] != 1.0:
        lut = [min(255, int(((i / 255.0) ** (1.0 / o["gamma"])) * 255 + .5))
               for i in range(256)]
        im = im.point(lut * 3)

    ramp = RAMPS[o["ramp"]][1]
    if o["invert"]:
        ramp = ramp[::-1]
    n = len(ramp)
    table = {i: ramp[i * n // 256] for i in range(256)}  # C-speed translate
    gray = im.convert("L").tobytes().decode("latin-1")
    rows = [gray[y * w:(y + 1) * w].translate(table) for y in range(h)]

    a = Art()
    a.rows, a.w, a.h, a.rgb, a.path = rows, w, h, im, path
    a.pidx = None
    if o["color"]:
        q = im.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                        dither=Image.Dither.NONE)
        a.pidx = q.tobytes()          # one palette index per pixel
    a.secs = time.time() - t0
    return a


def palette_map(art):
    """Palette index -> xterm-256 color index (computed once per render)."""
    pal = art.rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                           dither=Image.Dither.NONE).getpalette()[:768]
    return [nearest_xterm((pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]))
            for i in range(256)]

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_txt(art, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(art.rows) + "\n")


def export_ans(art, path):
    """Truecolor 24-bit ANSI export using the image's real pixel colors."""
    pal = art.rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                           dither=Image.Dither.NONE).getpalette()[:768]
    pidx, w, h = art.pidx, art.w, art.h
    with open(path, "w", encoding="utf-8") as f:
        for y in range(h):
            row = art.rows[y]
            brow = pidx[y * w:(y + 1) * w]
            last, buf, out = -2, [], []
            for x in range(w):
                c = brow[x] * 3
                if c != last:
                    if buf:
                        out.append("".join(buf))
                        buf = []
                    out.append("\x1b[38;2;%d;%d;%dm" %
                               (pal[c], pal[c + 1], pal[c + 2]))
                    last = c
                buf.append(row[x])
            out.append("".join(buf) + "\x1b[0m\n")
            f.write("".join(out))

# ---------------------------------------------------------------------------
# Curses UI
# ---------------------------------------------------------------------------

class UI:
    def __init__(self, scr, path):
        self.scr = scr
        self.o = dict(width=120, ramp=0, invert=False, bright=1.0,
                      contrast=1.0, gamma=1.0, sharp=0, aspect_idx=2,
                      aspect=2.0, color=True)
        self.path = None
        self.art = None
        self.vx = self.vy = 0
        self.zoom = 0
        self.msg = "O: open  L: browse  H: help"
        self.pair_cache = {}
        self.next_pair = 1
        self.color_ok = False
        self.tc = os.environ.get("COLORTERM", "") in ("truecolor", "24bit")
        if path:
            self.load(path)

    # ---------------- helpers ----------------
    def reload(self):
        if self.path:
            self.o["aspect"] = ASPECTS[self.o["aspect_idx"]]
            try:
                self.art = build_art(self.path, self.o)
                self.msg = "rendered %dx%d in %.2fs" % (self.art.w,
                                                        self.art.h,
                                                        self.art.secs)
            except Exception as e:                          # noqa: BLE001
                self.art = None
                self.msg = "ERROR: %s" % e
        self.clamp_view()

    def clamp_view(self):
        if self.art:
            self.vx = max(0, min(self.art.w - 1, self.vx))
            self.vy = max(0, min(self.art.h - 1, self.vy))

    def pair_for(self, xt):
        p = self.pair_cache.get(xt)
        if p is None:
            if self.next_pair >= 255:        # pair-id space exhausted
                self.pair_cache.clear()
                self.next_pair = 1
            p = self.next_pair
            self.next_pair += 1
            curses.init_pair(p, xt, -1)
            self.pair_cache[xt] = p
        return p

    # ---------------- drawing ----------------
    def draw(self):
        scr = self.scr
        scr.erase()
        H, W = scr.getmaxyx()
        vh, vw = H - 2, W
        z = ZOOMS[self.zoom]
        art = self.art
        if art is None:
            scr.addstr(0, 0, " press O to open an image | H help | Q quit",
                       curses.A_BOLD)
            self.draw_status(H, W)
            return
        use_color = (self.o["color"] and self.color_ok
                     and art.pidx is not None)
        pmap = palette_map(art) if use_color else None
        cs = max(1, vw // z)
        rs = max(1, vh // z)
        for rz in range(0, min(vh, rs * z), z):
            ay = self.vy + rz // z
            if ay >= art.h:
                break
            seg = art.rows[ay][self.vx:self.vx + cs]
            if not seg:
                continue
            if z > 1:
                seg = "".join(ch * z for ch in seg)
            if not use_color:
                safe = seg[:W - 1]
                scr.addstr(rz, 0, safe)
                for dz in range(1, z):
                    if rz + dz < vh:
                        scr.addstr(rz + dz, 0, safe)
            else:
                brow = art.pidx[ay * art.w + self.vx:
                                ay * art.w + self.vx + cs]
                x, n = 0, len(brow)
                while x < n:
                    c = brow[x]
                    x2 = x
                    while x2 < n and brow[x2] == c:
                        x2 += 1
                    chunk = seg[x * z:x2 * z][:W - 1 - x * z]
                    if chunk:
                        attr = curses.color_pair(self.pair_for(pmap[c]))
                        scr.addstr(rz, min(x * z, W - 1), chunk, attr)
                        for dz in range(1, z):
                            if rz + dz < vh:
                                scr.addstr(rz + dz, min(x * z, W - 1),
                                           chunk, attr)
                    x = x2
        self.draw_status(H, W)

    def draw_status(self, H, W):
        scr, o, art = self.scr, self.o, self.art
        if art:
            col = "256color" if (o["color"] and self.color_ok) else "mono"
            info = (" %s | %dx%d | ramp:%s | w:%d sharp:%d br:%.2f "
                    "ct:%.2f gm:%.2f asp:%.1f | %s%s | x%d | [%d,%d]"
                    % (os.path.basename(art.path), art.w, art.h,
                       RAMPS[o["ramp"]][0], o["width"], o["sharp"],
                       o["bright"], o["contrast"], o["gamma"], o["aspect"],
                       col, "+tc" if self.tc else "", ZOOMS[self.zoom],
                       self.vx, self.vy))
        else:
            info = " no image loaded"
        bar2 = (" O:open R:ramp I:inv [/]:width S/s:sharp B/b:bright "
                "C/c:contrast G/g:gamma A:aspect K:color +-:zoom "
                "arrows:pan E:export H:help Q:quit")
        try:
            scr.addstr(H - 2, 0, info[:W - 1], curses.A_REVERSE)
            scr.addstr(H - 1, 0, bar2[:W - 1])
        except curses.error:
            pass
        if self.msg:
            try:
                scr.addstr(H - 2, max(0, W - len(self.msg) - 1),
                           self.msg[:W - 1],
                           curses.A_REVERSE | curses.A_BOLD)
            except curses.error:
                pass

    # ---------------- overlays / helpers ----------------
    def help(self):
        scr = self.scr
        scr.erase()
        lines = [
            "ASCII STUDIO — help",
            "",
            " O        open image (path or glob, e.g. ~/pics/*.png)",
            " L        file browser (images next to current file)",
            " R        cycle character ramp (%d sets: CP437, braille...)" %
            len(RAMPS),
            " I        invert ramp (dark<->light)",
            " [ / ]    output width -/+  (16 .. 3000)",
            " S / s    sharpness + / -  (unsharp mask)",
            " B / b    brightness + / -",
            " C / c    contrast + / -",
            " G / g    gamma + / -",
            " A        cycle cell aspect ratio (1.6 .. 2.4)",
            " K        toggle 256-color mode on/off",
            " + / -    preview zoom (x1..x8)",
            " arrows / hjkl    pan     P: jump to origin",
            " E        export: <image>.txt + truecolor <image>.ans",
            " Q        quit",
            "",
            "press any key to return",
        ]
        for i, ln in enumerate(lines):
            try:
                scr.addstr(i, 0, ln)
            except curses.error:
                break
        scr.refresh()
        scr.getch()

    def prompt(self, title):
        scr = self.scr
        H, W = scr.getmaxyx()
        try:
            scr.addstr(H - 1, 0, " " * (W - 1))
            scr.addstr(H - 1, 0, title)
            scr.refresh()
        except curses.error:
            pass
        curses.echo()
        curses.curs_set(1)
        try:
            inp = scr.getstr(H - 1, len(title), max(1, W - len(title) - 2))
        except curses.error:
            inp = b""
        curses.noecho()
        curses.curs_set(0)
        return inp.decode("utf-8", "replace").strip()

    def load(self, spec):
        p = os.path.expanduser(spec)
        if any(ch in p for ch in "*?["):
            matches = [m for m in sorted(glob.glob(p))
                       if not os.path.isdir(m)]
        else:
            matches = [p] if os.path.isfile(p) else []
        if not matches:
            self.msg = "no match: %s" % spec
            return
        self.path = matches[0]
        self.reload()

    def browser(self):
        cwd = (os.path.dirname(os.path.abspath(self.path))
               if self.path else os.getcwd())
        files = []
        for pat in IMG_EXTS:
            files.extend(glob.glob(os.path.join(cwd, pat)))
        files = sorted(set(files))
        if not files:
            self.msg = "no images in %s" % cwd
            return
        scr, sel, off = self.scr, 0, 0
        while True:
            scr.erase()
            H, W = scr.getmaxyx()
            scr.addstr(0, 0, (" %s  (%d images)  j/k: move  Enter: open  "
                              "q: cancel" % (cwd, len(files)))[:W - 1],
                       curses.A_REVERSE)
            for i in range(off, min(off + H - 2, len(files))):
                mark = ">" if i == sel else " "
                scr.addstr(i - off + 1, 0,
                           (" %s %s" % (mark,
                                        os.path.basename(files[i])))[:W - 1],
                           curses.A_BOLD if i == sel else curses.A_NORMAL)
            scr.refresh()
            k = scr.getch()
            if k in (curses.KEY_UP, ord("k")):
                sel = max(0, sel - 1)
                if sel < off:
                    off = sel
            elif k in (curses.KEY_DOWN, ord("j")):
                sel = min(len(files) - 1, sel + 1)
                if sel >= off + H - 2:
                    off = sel - (H - 3)
            elif k in (curses.KEY_ENTER, 10, 13):
                self.path = files[sel]
                self.reload()
                return
            elif k in (ord("q"), 27):
                return

    # ---------------- main loop ----------------
    def export(self):
        if not self.art:
            self.msg = "nothing to export"
            return
        base = os.path.splitext(os.path.abspath(self.path))[0]
        t0 = time.time()
        try:
            export_txt(self.art, base + ".txt")
            if self.o["color"] and self.art.pidx is not None:
                export_ans(self.art, base + ".ans")
                self.msg = "exported .txt + .ans (truecolor) in %.1fs" % \
                    (time.time() - t0)
            else:
                self.msg = "exported .txt in %.1fs" % (time.time() - t0)
        except Exception as e:                                # noqa: BLE001
            self.msg = "export failed: %s" % e

    def run(self):
        scr = self.scr
        curses.start_color()
        curses.use_default_colors()
        self.color_ok = curses.has_colors() and curses.COLORS >= 256
        if curses.has_colors() and not self.color_ok:
            self.msg = "terminal <256 colors -> mono"
        curses.noecho()
        curses.curs_set(0)
        scr.keypad(True)

        while True:
            self.draw()
            scr.refresh()
            k = scr.getch()
            if k in (ord("q"), ord("Q")):
                return
            elif k == curses.KEY_RESIZE:
                self.clamp_view()
            elif k in (curses.KEY_LEFT, ord("h")):
                self.vx = max(0, self.vx - 10)
            elif k in (curses.KEY_RIGHT, ord("l")):
                self.vx += 10
                self.clamp_view()
            elif k in (curses.KEY_UP, ord("k")):
                self.vy = max(0, self.vy - 5)
            elif k in (curses.KEY_DOWN, ord("j")):
                self.vy += 5
                self.clamp_view()
            elif k == ord("P"):
                self.vx = self.vy = 0
            elif k in (ord("+"), ord("=")):
                self.zoom = min(len(ZOOMS) - 1, self.zoom + 1)
            elif k in (ord("-"), ord("_")):
                self.zoom = max(0, self.zoom - 1)

            elif k in (ord("r"), ord("R")):
                self.o["ramp"] = (self.o["ramp"] + 1) % len(RAMPS)
                self.msg = "ramp: " + RAMPS[self.o["ramp"]][0]
            elif k in (ord("i"), ord("I")):
                self.o["invert"] = not self.o["invert"]
            elif k == ord("["):
                self.o["width"] = max(MIN_W, self.o["width"] - 10)
                self.reload()
            elif k == ord("]"):
                self.o["width"] = min(MAX_W, self.o["width"] + 10)
                self.reload()
            elif k == ord("s"):
                self.o["sharp"] = max(0, self.o["sharp"] - 25)
                self.reload()
            elif k == ord("S"):
                self.o["sharp"] = min(500, self.o["sharp"] + 25)
                self.reload()
            elif k == ord("b"):
                self.o["bright"] = max(.1, round(self.o["bright"] - .1, 2))
                self.reload()
            elif k == ord("B"):
                self.o["bright"] = min(3.0, round(self.o["bright"] + .1, 2))
                self.reload()
            elif k == ord("c"):
                self.o["contrast"] = max(.1,
                                         round(self.o["contrast"] - .1, 2))
                self.reload()
            elif k == ord("C"):
                self.o["contrast"] = min(3.0,
                                         round(self.o["contrast"] + .1, 2))
                self.reload()
            elif k == ord("g"):
                self.o["gamma"] = max(.2, round(self.o["gamma"] - .1, 2))
                self.reload()
            elif k == ord("G"):
                self.o["gamma"] = min(3.0, round(self.o["gamma"] + .1, 2))
                self.reload()
            elif k in (ord("a"), ord("A")):
                self.o["aspect_idx"] = (self.o["aspect_idx"] + 1) % \
                    len(ASPECTS)
                self.reload()
            elif k in (ord("k"), ord("K")):
                self.o["color"] = not self.o["color"]
            elif k in (ord("o"), ord("O")):
                spec = self.prompt("open image: ")
                if spec:
                    self.load(spec)
            elif k in (ord("l"), ord("L")):
                self.browser()
            elif k in (ord("e"), ord("E")):
                self.export()
            elif k == ord("H"):              # H only — hjkl are pan keys
                self.help()


def selftest():
    """Headless pipeline test (no curses)."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ascii_studio_test_")
    p = os.path.join(tmp, "test.png")
    im = Image.new("RGB", (800, 600))
    px = im.load()
    for y in range(600):
        for x in range(800):
            px[x, y] = (x * 255 // 800, y * 255 // 600,
                        (x + y) * 255 // 1400)
    im.save(p)

    o = dict(width=80, ramp=5, invert=False, bright=1.0, contrast=1.2,
             gamma=1.0, sharp=100, aspect=2.0, color=True)
    a = build_art(p, o)
    assert len(a.rows) == a.h and all(len(r) == a.w for r in a.rows)
    print("OK small render: %dx%d in %.2fs" % (a.w, a.h, a.secs))
    print("sample row:", a.rows[0][:60])

    o["width"] = MAX_W
    o["sharp"] = 300
    t0 = time.time()
    big = build_art(p, o)
    print("OK max render:  %dx%d in %.2fs (total %.2fs)"
          % (big.w, big.h, big.secs, time.time() - t0))

    o.update(width=120, sharp=100)
    sm = build_art(p, o)
    export_txt(sm, os.path.join(tmp, "out.txt"))
    export_ans(sm, os.path.join(tmp, "out.ans"))
    ans = open(os.path.join(tmp, "out.ans"), encoding="utf-8").read()
    assert "\x1b[38;2;" in ans and ans.count("\n") >= sm.h
    print("OK exports: out.txt + out.ans (truecolor escapes present)")
    print("artifacts in %s" % tmp)
    for i, (name, _) in enumerate(RAMPS):
        o["ramp"] = i
        r = build_art(p, o)
        print("  ramp %-14s -> %r" % (name, r.rows[r.h // 2][:24]))


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)

    def _wrap(scr):
        UI(scr, argv[0] if argv else None).run()

    curses.wrapper(_wrap)





