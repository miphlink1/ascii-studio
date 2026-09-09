# ASCII STUDIO

Interactive image → ASCII converter. Two flavors, same pipeline:

- **Web:** `ascii_studio.html` — single self-contained file, zero dependencies.
  Just open it in any browser (double-click). Drag & drop / paste / open an
  image, tweak, then export `.txt`, truecolor `.ans`, or a rendered `.png`.
  Wheel = zoom, drag = pan, `f` = fit, `+`/`-` = zoom, arrows = pan, `⌘V` paste.
  **Line height 0.5–2.0 (default 1.35)** — typographic leading in font-size
  multiples; changing it *resamples the grid* (row count adapts), so the image
  keeps its proportions and only the characters get taller/shorter, never
  squashed.
  **Video:** drop or open a video file to play it as live ASCII (space or
  ▶ play/pause). The **framerate** slider (1–30 fps, default 12) sets how many
  frames per second the export samples. **python ⬇** then downloads a *single
  self-contained Python script* (stdlib only) with the truecolor frames
  embedded (zlib + base64, up to 900 frames): run `python3 clip.py` in any
  24-bit terminal to play the animation — `--fps N` and `--loop` supported.
  It exports with the app's current invert setting, so for a dark terminal
  tick *invert* first. `.txt`/`.ans`/`.png` still export the shown frame.
  Light (paper) UI, and **darker pixel = denser character** by default, so mono
  art reads correctly on the white background; tick *invert* for viewing on
  dark backgrounds. Transparency (PNG/WebP/GIF alpha, palette tRNS) is
  flattened onto the white page — never black.
- **Terminal:** `ascii_studio.py` — pure Python + Pillow + curses TUI.

    python3 ascii_studio.py photo.jpg        # open straight into the TUI
    python3 ascii_studio.py                  # then press O to open / L to browse
    python3 ascii_studio.py --selftest       # headless pipeline test

## Keys (terminal version)

| Key | Action |
|---|---|
| O / L | open image (path or glob) / file browser |
| R | cycle character ramp — 16 sets: default-10, classic-70, cp437-shades, cp437-mix, cp437-blocks, cp437-dense, braille, binary, dots, tech, greek, arrows… |
| I | invert ramp |
| [ / ] | output width −/+ (16 … **3000**) |
| S / s | sharpness +/− (unsharp mask, 0–500) |
| B/b, C/c, G/g | brightness / contrast / gamma |
| A | cell aspect ratio (1.6–2.4, fixes squashiness) |
| K | toggle 256-palette color |
| + / − | preview zoom x1–x8, arrows/hjkl pan, P reset |
| E | export: `<image>.txt` + truecolor 24-bit `<image>.ans` |
| H | help, Q | quit |

## Color

In-TUI rendering uses the full xterm-256 palette (6×6×6 cube + grayscale ramp —
not just the 8 base ANSI colors), mapped via median-cut quantization with no
dithering. Export writes real per-pixel **24-bit truecolor** ANSI (needs a
COLORTERM=truecolor terminal: `cat image.ans` in iTerm2/Warp/Kitty/VS Code).

Transparency is flattened onto black here (the typical dark terminal is the
viewing surface, so alpha-0 areas render as `' '`); `test_alpha.py` is the
regression test.

Requires (terminal version): `pip install Pillow`  (tested: Python 3.9, Pillow 11, macOS Terminal/iTerm)

`pty_smoke.py` is the automated end-to-end test for the TUI (drives the real
curses UI through a pseudo-terminal and verifies renders + exports).
`test_core.py` is the automated test for the HTML version — it extracts the
pure-JS pipeline from `ascii_studio.html` and runs it on macOS's system
JavaScript engine: `python3 test_core.py` (26 checks, no browser needed —
including generating a mini player script and actually executing it).
`check_html.py` verifies the HTML structure/ID wiring.

