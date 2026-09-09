import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time

img = sys.argv[1]
pid, fd = pty.fork()
if pid == 0:
    os.environ["TERM"] = "xterm-256color"
    os.environ["COLORTERM"] = "truecolor"
    os.execvp("python3", ["python3", "ascii_studio.py", img])

# give the pty a real window size so curses gets 120x40
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))

out = b""


def drain(t=0.5):
    global out
    end = time.time() + t
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                d = os.read(fd, 65536)
            except OSError:
                return False
            if not d:
                return False
            out += d
    return True


drain(2.0)
for key, wait in [(b"r", .6), (b"r", .6), (b"]", 1.5), (b"S", 1.5),
                  (b"K", .8), (b"K", .8), (b"e", 2.0), (b"q", .5)]:
    try:
        os.write(fd, key)
    except OSError:
        break
    if not drain(wait):
        break
try:
    _, status = os.waitpid(pid, 0)
except ChildProcessError:
    status = 0
try:
    os.close(fd)
except OSError:
    pass

text = out.decode("utf-8", "replace")
imgdir = os.path.dirname(img)
base = os.path.splitext(img)[0]
txt_p = base + ".txt"
ans_p = base + ".ans"
checks = {
    "drew status bar": "ramp:" in text,
    "256color active": "256color" in text,
    "export msg": "exported" in text,
}

# behavioral: exported .txt must reflect final settings:
# two 'r' presses -> ramp minimal-4 (" .#@"), ']' -> width 130, 'S' sharp 25
ok_txt = False
if os.path.isfile(txt_p):
    rows = open(txt_p, encoding="utf-8").read().splitlines()
    exp_h = round(600 * (130 / 800) / 2.0)
    ok_txt = (len(rows) == exp_h
              and all(len(r) == 130 for r in rows)
              and all(set(r) <= set(" .#@") for r in rows))
checks["txt: width 130, minimal-4 ramp, aspect 2.0"] = ok_txt

ok_ans = os.path.isfile(ans_p) and \
    "\x1b[38;2;" in open(ans_p, encoding="utf-8").read()
checks["ans: truecolor 24-bit escapes present"] = ok_ans

for k, v in checks.items():
    print(("PASS" if v else "FAIL"), k)
print("exit status:", status)
tail = text[-1200:].replace("\x1b", "<ESC>")
print("---- tail of pty output ----")
print(tail)
print("PTY_SMOKE", "OK" if (status == 0 and all(checks.values()))
      else "FAILED")

