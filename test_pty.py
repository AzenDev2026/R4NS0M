#!/usr/bin/env python3
"""Drive ransom.py through a real pty, pressing keys like a human.
This exercises the cbreak keyboard path that --demo bypasses."""
import os
import pty
import re
import select
import sys
import time

ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")


def clean(buf):
    return ANSI_RE.sub(b"", buf).replace(b"\x07", b"")


pid, fd = pty.fork()
if pid == 0:
    os.environ["TERM"] = "xterm-256color"
    os.execvp("python3", ["python3", "ransom.py",
                          "--time", "15", "--gold", "200", "--rounds", "2",
                          "--vault", "/tmp/rpty"])
    os._exit(127)

log = []
buf = b""
stage = "intro"
attack_until = 0
deadline = time.time() + 45
status = None

try:
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            buf = (buf + data)[-8000:]
        txt = clean(buf).decode(errors="replace")

        if stage == "intro" and "PRESS ANY KEY" in txt:
            os.write(fd, b"\r")
            log.append("intro: ENTER")
            stage = "rounds"
        elif stage == "rounds" and "round 1/2" in txt:
            os.write(fd, b"x")
            log.append("rounds: x -> caught")
            stage = "attack"
            attack_until = time.time() + 12
        elif stage == "attack" and time.time() < attack_until:
            if "press C to close" in txt:
                os.write(fd, b"c")
            elif "PRESS H NOW" in txt:
                os.write(fd, b"h")
                log.append("attack: h (honey)")
            elif "LOOT THE DRAWER" in txt:
                os.write(fd, b" ")
        elif stage not in ("done",) and "PLAY AGAIN" in txt:
            os.write(fd, b"n")
            log.append("end: n")
            stage = "done"
            deadline = time.time() + 5
finally:
    # reap the child, waiting up to 5s for it to exit on its own
    for _ in range(50):
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
            if wpid == pid:
                break
        except ChildProcessError:
            status = "already-reaped"
            break
        time.sleep(0.1)
    else:
        try:
            os.kill(pid, 9)
            _, status = os.waitpid(pid, 0)
            log.append("TEST FAILED: killed after timeout")
        except (ProcessLookupError, ChildProcessError):
            pass

tail = clean(buf).decode(errors="replace")
verdict = "?"
if "RANSOM PAID" in tail:
    verdict = "paid"
elif "YOU GOT RANSOMED" in tail:
    verdict = "failed"
elif "FIREWALL" in tail:
    verdict = "avoided"

print("log:", log)
print("verdict:", verdict)
print("status:", status)
print("--- last 400 chars of screen ---")
print(tail[-400:])
vdir = "/tmp/rpty/victim_files"
files = os.listdir(vdir) if os.path.isdir(vdir) else []
print("vault files:", len(files))
ok = (bool(log) and verdict != "?" and
      any("end: n" in s for s in log))
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
