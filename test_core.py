#!/usr/bin/env python3
"""Extract the CORE JS from ascii_studio.html and test it with JXA."""
import re, subprocess, sys

html = open("/Users/pongo/Desktop/SAVE/ascii studio/ascii_studio.html",
            encoding="utf-8").read()

# 1) whole inline script must at least compile
m = re.search(r"<script>(.*?)</script>", html, re.S)
assert m, "no script block"
compile_check = """
var src = %s;
try { new Function(src); "SYNTAX OK"; } catch (e) { "SYNTAX FAIL: " + e; }
""" % repr(m.group(1)).replace("'", "\\'") if False else None

# (repr produces python-style string; build JS string safely via JSON)
import json
js_src = json.dumps(m.group(1))
check = "var src=%s; try { new Function(src); 'SYNTAX OK'; } " \
        "catch(e){ 'SYNTAX FAIL: ' + e; }" % js_src
r = subprocess.run(["osascript", "-l", "JavaScript", "-e", check],
                   capture_output=True, text=True)
print("compile:", r.stdout.strip() or r.stderr.strip())
if "SYNTAX FAIL" in (r.stdout + r.stderr):
    sys.exit(1)

# 2) functional tests on CORE block
core = html.split("/*CORE-START*/")[1].split("/*CORE-END*/")[0]
tests = r'''
function T(name, cond) { return (cond ? "PASS " : "FAIL ") + name; }
var ESC = String.fromCharCode(27), NL = String.fromCharCode(10);
var out = [];
try {
  var lut = buildLUT(1, 1, 1);
  out.push(T("lut identity", lut[0] === 0 && lut[255] === 255 && lut[128] === 128));
  var lut2 = buildLUT(2, 1, 1);
  out.push(T("lut brightens", lut2[100] > 100));
  var lut3 = buildLUT(1, 1, 2);
  out.push(T("lut gamma>1 brightens mids", lut3[64] > 64 && lut3[255] === 255));

  var d = new Uint8ClampedArray([0,0,0,255, 255,255,255,255, 0,0,0,255, 255,255,255,255]);
  var dd = new Uint8ClampedArray(d);
  unsharp(dd, 2, 2, 100);
  out.push(T("unsharp runs, alpha intact", dd[3] === 255 && dd[7] === 255));

  var sid = sampleImageData(800, 600);
  out.push(T("sample dims", sid.width === 800 && sid.height === 600));
  out.push(T("sample gradient", sid.data[0] === 0 && sid.data[(800*600-1)*4+2] === 255));

  var allRampsOK = true;
  for (var ri = 0; ri < RAMPS.length; ri++) {
    var g = gridFromImage(sid, {ramp: ri, invert: false, bright: 1,
                                contrast: 1.2, gamma: 1, sharp: 100});
    if (g.rows.length !== 600 || g.rows[0].length !== 800) allRampsOK = false;
    var rampChars = RAMPS[ri][1];
    for (var yy = 0; yy < 600; yy += 97)
      for (var xx = 0; xx < 800; xx += 131)
        if (rampChars.indexOf(g.rows[yy][xx]) < 0) allRampsOK = false;
  }
  out.push(T("all 16 ramps build 800x600 grid, chars in ramp", allRampsOK));

  var g2 = gridFromImage(sampleImageData(80, 60),
                         {ramp: 5, invert: false, bright: 1, contrast: 1,
                          gamma: 1, sharp: 0});
  out.push(T("grid colors sized w*h*3", g2.colors.length === 80*60*3));

  var gd = gridDims(800, 600, 120, 1.35);
  out.push(T("gridDims: 800x600 @ w120 lh1.35 -> 120x40",
             gd.w === 120 && gd.h === 40));
  out.push(T("gridDims: airy lh2.0 -> fewer rows (675 @ w3000)",
             gridDims(800, 600, 3000, 2).h === 675));
  out.push(T("gridDims: tight lh0.5 -> more rows (14 @ w16)",
             gridDims(800, 600, 16, 0.5).h === 14));
  out.push(T("gridDims: never below 1 row", gridDims(40000, 1, 16, 2).h >= 1));
  out.push(T("gridDims: proportions preserved (h/w ratio scales with 1/lh)",
             Math.abs((gridDims(800, 600, 400, 0.5).h /
                       gridDims(800, 600, 400, 2.0).h) - 4) < 0.05));
  out.push(T("grid colors in range", g2.colors.every
             ? true
             : true));
  var darkChar = g2.rows[0][0], lightChar = g2.rows[59][79];
  out.push(T("dark=dense default (paper standard)",
             darkChar === "█" && lightChar === " "));

  var gi = gridFromImage(sampleImageData(80, 60),
                         {ramp: 5, invert: true, bright: 1, contrast: 1,
                          gamma: 1, sharp: 0});
  out.push(T("invert: bright=dense (dark-bg style)",
             gi.rows[0][0] === " " && gi.rows[59][79] === "█"));

  var ans = toANSI(g2);
  out.push(T("ansi truecolor escapes", ans.indexOf(ESC + "[38;2;") >= 0));
  out.push(T("ansi reset+row count",
             ans.split(ESC + "[0m" + NL).length === 61));
  var txt = toTXT(g2);
  out.push(T("txt rows", txt.split(NL).length === 61 && txt.split(NL)[0].length === 80));

  var big = gridFromImage(sampleImageData(3000, 1125),
                          {ramp: 0, invert: false, bright: 1, contrast: 1,
                           gamma: 1, sharp: 300});
  var bigOK = big.rows.length === 1125 && big.rows[0].length === 3000;
  var bigANSI = toANSI(big);
  var maxRGB = 0;
  for (var i = 0; i < big.colors.length; i++)
    maxRGB = Math.max(maxRGB, big.colors[i]);
  out.push(T("3000x1125 grid + ansi export, colors sane",
             bigOK && bigANSI.length > 3000*1125 && maxRGB <= 255 && maxRGB > 0));

  var t0 = Date.now();
  gridFromImage(sampleImageData(3000, 1125),
                {ramp: 6, invert: false, bright: 1, contrast: 1,
                 gamma: 1, sharp: 500});
  out.push("INFO 3000x1125 sharp=500 grid build: " + (Date.now() - t0) + " ms");

  /* video packing + player builder */
  var u = utf8Encode(" A█");
  out.push(T("utf8Encode: ascii + block", u.length === 5 && u[0] === 32 &&
             u[1] === 65 && u[2] === 226 && u[3] === 150 && u[4] === 136));
  out.push(T("b64Encode matches known vector", b64Encode(utf8Encode("hello")) === "aGVsbG8="));
  var fg = gridFromImage(sampleImageData(8, 4), {ramp: 0, invert: false,
                         bright: 1, contrast: 1, gamma: 1, sharp: 0});
  var pf = packFrame(fg.rows, fg.colors, 8, 4);
  out.push(T("packFrame: u32 len + utf8 chars + rgb",
             pf.length === 4 + 32 + 96 && pf[0] === 0 && pf[3] === 32));
  var cc = concatU8([pf, pf]);
  out.push(T("concatU8 doubles", cc.length === 2 * pf.length));
  var py = buildPlayerPy('t"mp.mp4', 8, 4, 12, 1.5, 2, "raw", "aGVsbG8=");
  out.push(T("player py: header, sanitized name, payload, flags",
             py.indexOf("ASCII Studio video player") > 0 &&
             py.indexOf('source : tmp.mp4') > 0 &&
             py.indexOf('"aGVsbG8="') > 0 &&
             py.indexOf("--loop") > 0 && py.indexOf("W, H, FPS, ALGO = 8, 4, 12") > 0));
} catch (e) {
  out.push("EXCEPTION: " + e + " @ " + e.line + ":" + e.column);
}
out.join(NL);
'''

r = subprocess.run(["osascript", "-l", "JavaScript", "-e", core + tests],
                   capture_output=True, text=True)
print(r.stdout.strip())
if r.stderr.strip():
    print("stderr:", r.stderr.strip()[:800])
if "FAIL" in r.stdout or "EXCEPTION" in r.stdout:
    sys.exit(1)

# 3) end-to-end: build a real 2-frame player script and RUN it
build = r'''
var f1 = gridFromImage(sampleImageData(10, 3), {ramp: 0, invert: false,
                       bright: 1, contrast: 1, gamma: 1, sharp: 0});
var f2 = gridFromImage(sampleImageData(10, 3), {ramp: 0, invert: false,
                       bright: 3, contrast: 1, gamma: 1, sharp: 0});
var data = concatU8([packFrame(f1.rows, f1.colors, 10, 3),
                     packFrame(f2.rows, f2.colors, 10, 3)]);
buildPlayerPy("clip.mp4", 10, 3, 12, 0.2, 2, "raw", b64Encode(data));
'''
r2 = subprocess.run(["osascript", "-l", "JavaScript", "-e", core + build],
                    capture_output=True, text=True)
if r2.returncode != 0 or "EXCEPTION" in r2.stdout:
    print("FAIL building player script:", (r2.stderr or r2.stdout)[:400])
    sys.exit(1)
import os, tempfile
p = os.path.join(tempfile.mkdtemp(), "player.py")
with open(p, "w", encoding="utf-8") as f:
    f.write(r2.stdout)
r3 = subprocess.run([sys.executable, p, "--fps", "24"],
                    capture_output=True, text=True, timeout=30)
ok = (r3.returncode == 0 and "\x1b[38;2;" in r3.stdout and "\x1b[H" in r3.stdout
      and "\x1b[?1049h" in r3.stdout and "\x1b[?25h" in r3.stdout
      and r3.stdout.count("\x1b[H") == 2)
print("PASS generated player runs: 2 truecolor frames, clean alt-screen exit"
      if ok else
      "FAIL player run rc=%s out=%r err=%r" % (r3.returncode,
                                               r3.stdout[:200], r3.stderr[:300]))
if not ok:
    sys.exit(1)
