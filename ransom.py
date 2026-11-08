#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R4NS0M — a 100% FAKE ransomware simulator.

Inspired by "Ransom", the entity from Roblox DOORS (by LSPLASH).
In DOORS, Ransom shows you his glitched face and a red STOP sign:
if you move, he "encrypts" your items and you must pay 500 Gold
within 90 seconds or he deletes them.

Everything in this program is theatre:

  * it NEVER touches your real files,
  * it only creates / renames / deletes a few fake files inside its
    own sandbox folder (~/.ransom_sim by default),
  * it has no network code at all,
  * it can be stopped at any time with Ctrl+C or Q.

Run:
    python3 ransom.py
    python3 ransom.py --time 60 --gold 300 --rounds 4
    python3 ransom.py --demo caught|avoid|fail
"""

import argparse
import os
import random
import re
import select
import signal
import sys
import termios
import time
import tty

# ============================================================
#  Constants & data
# ============================================================

VAULT_DEFAULT = "~/.ransom_sim"

# Fake "victim" files (created inside the sandbox only!)
VAULT_FILES = {
    "homework.docx": b"R4NS0M says: do your homework. (fake file)",
    "family_photos.jpg": b"\xff\xd8 fake jpeg bytes, nobody was harmed",
    "game_save.dat": b"level=99 gold=1337 sword=legendary (fake)",
    "secret_passwords.txt": b"hunter2 (fake, obviously)",
    "to_do_list.txt": b"1. survive Ransom\n2. touch grass\n3. delete this",
    "diary.txt": b"dear diary, today a ghost in my PC asked for gold.",
    "definitely_not_pirated_movie.mp4": b"00000000 fake mp4 content",
}

# Items Ransom "encrypts" (purely cosmetic, from DOORS)
INVENTORY_ITEMS = [
    "Flashlight", "Vitamins", "Lockpick", "Lighter",
    "Crucifix", "Candle", "Bandages", "Skull Key",
]

# Popup titles (real DOORS trivia — from doorsgame.wiki/wiki/Ransom)
POPUP_HEADERS = [
    "RANSOM", "Untitled", "Untitled (2)", "Untitled (3)",
    "RANSOM.exe", "RNAOSM", "RNASOM", "RANASOM", "MOSNAR",
    "R4NS0M", "I FOUND YOU", "RANSOMRANSOM", "RRAANNSSOOMM",
    "WHATWOULDSHETHINK", "LACKLUSTER", "INCOMPETENT",
    "NONIMPRESSIVE", "DISAPPOINTING", "IMG.JPG",
    "YOU ARE AN IDIOT", "ENCRYPTED", "AJWBXV", "times up",
    "YOUR GOLD IS VERY YUMMY!", "YOURGOLDAREBELONGTOUS",
    "ERROR", "ENCRYPTION", "KEY",
]

POPUP_LINES = [
    "YOUR FILES ARE LOCKED.",
    "GIVE US GOLD.",
    "WE ARE WATCHING YOU.",
    "PAY UP.",
    "NICE DRAWERS YOU GOT THERE.",
    "CLOSE ME. GO ON.",
    "SILENCE IS GOLD.",
    "GOLD GOLD GOLD GOLD",
    "HAND IT OVER.",
    "WE KNOW WHERE YOU SLEEP.",
    "THE TIMER IS TICKING.",
    "STOP READING. START LOOTING.",
]

# ASCII art — every line must have the SAME width (checked at startup).

FACE_NORMAL = [
    "▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
    "█▒░░░░░░░░░░░░░░░▒█",
    "█░▓▀▀▀▓░░░░▓▀▀▀▓░░█",
    "█░▓▓▓▓▓░░░░▓▓▓▓▓░░█",
    "█░▓▄▄▄▓░░░░▓▄▄▄▓░░█",
    "█░░░░░░░░░░░░░░░░░█",
    "█░░░░░▓▄▄▄▄▓░░░░░░█",
    "█░░░░░▓░░░░▓░░░░░░█",
    "█░░░░░▓▀▀▀▀▓░░░░░░█",
    "█░░░░░░░░░░░░░░░░░█",
    "▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀",
]

FACE_JSCARE = [
    "▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
    "█░░░░░░░░░░░░░░░░░█",
    "█░░░░▓▓▓░░░░▓▓▓░░░█",
    "█░░░░░░░░░░░░░░░░░█",
    "█░░░▓▄▄▄▄▄▄▄▄▓░░░░█",
    "█░░░▓░▓▓▓▓▓▓░▓░░░░█",
    "█░░░▓▀▀▀▀▀▀▀▀▓░░░░█",
    "█░░░░░░░░░░░░░░░░░█",
    "█░░░░░░░░░░░░░░░░░█",
    "▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀",
]

STOP_SIGN = [
    "  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄  ",
    " █████████████████ ",
    " █░░░░░░░░░░░░░░░█ ",
    " █░░░S T O P░░░░░█ ",
    " █░░░░░░░░░░░░░░░█ ",
    " █████████████████ ",
    "  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀  ",
]

LOGO = [
    "╦═╗╔═╗╔╗╔╔═╗╔═╗╔╦╗  ╔═╗╦ ╦╔═╗",
    "╠╦╝║ ║║║║╚═╗║ ║║║║  ╚═╗║ ║║╣ ",
    "╩╚═╚═╝╝╚╝╚═╝╚═╝╩ ╩  ╚═╝╚═╝╚═╝",
]

# ============================================================
#  ANSI helpers
# ============================================================

RESET = "\x1b[0m"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
CODES = {
    "r": "31", "rr": "91", "g": "32", "y": "33", "d": "90",
    "w": "97", "b": "1", "dim": "2", "blink": "5", "inv": "7",
}


def col(text, *codes):
    code = ";".join(CODES.get(c, c) for c in codes)
    return f"\x1b[{code}m{text}{RESET}"


def vis_len(s):
    """Visible length (ANSI codes don't take space)."""
    return len(ANSI_RE.sub("", s))


def fit(s, w):
    """Truncate to visible width w without cutting an ANSI code in half."""
    if vis_len(s) <= w:
        return s
    parts, seen, i = [], 0, 0
    while i < len(s) and seen < w:
        if s[i] == "\x1b":
            j = s.index("m", i) + 1
            parts.append(s[i:j])
            i = j
        else:
            parts.append(s[i])
            seen += 1
            i += 1
    return "".join(parts) + RESET


def bell():
    sys.stdout.write("\x07")
    sys.stdout.flush()


def cls():
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def mv(y, x):
    sys.stdout.write(f"\x1b[{y};{x}H")


def out(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def size():
    try:
        c, r = os.get_terminal_size()
        return max(c, 40), max(r, 20)
    except OSError:
        return 80, 24


def sleep(s):
    if s > 0:
        time.sleep(s)


# ============================================================
#  Terminal (raw-ish input via cbreak)
# ============================================================

class Term:
    def __init__(self):
        self.fd = None
        self.old = None
        self.demo = False
        self.demo_queue = []  # keys "pressed" by the demo bot

    def start(self):
        if not self.demo and not sys.stdin.isatty():
            raise RuntimeError(
                "R4NS0M needs a real terminal.\n"
                "Run it from your terminal (Konsole / GNOME Terminal / etc.)\n"
                "or use  --demo caught  to watch an automatic playthrough."
            )
        if sys.stdin.isatty():
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        sys.stdout.write("\x1b[?25l")  # hide cursor
        sys.stdout.flush()

    def stop(self):
        sys.stdout.write("\x1b[?25h\x1b[0m")
        sys.stdout.flush()
        if self.fd is not None and self.old is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            except termios.error:
                pass
            self.fd = None

    def push(self, key):
        self.demo_queue.append(key)

    def get_key(self, timeout=0.0):
        """Return one key ('a', ' ', 'enter', 'esc', ...) or None."""
        if self.demo:
            return self.demo_queue.pop(0) if self.demo_queue else None
        if self.fd is None:
            return None
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        try:
            data = os.read(self.fd, 64)
        except OSError:
            return None
        if not data:
            return None
        first = data[0]
        if first == 27:  # escape sequence (arrows etc.) — drain the rest
            while True:
                rr, _, _ = select.select([self.fd], [], [], 0)
                if not rr:
                    break
                try:
                    os.read(self.fd, 64)
                except OSError:
                    break
            return "esc"
        if first in (13, 10):
            return "enter"
        if first == 32:
            return " "
        if first in (127, 8):
            return "backspace"
        return chr(first).lower()

    def flush(self):
        while self.get_key(0) is not None:
            pass


# ============================================================
#  Sandbox vault (the ONLY files this program ever touches)
# ============================================================

class Vault:
    def __init__(self, root):
        self.root = os.path.abspath(os.path.expanduser(root))

    @property
    def files_dir(self):
        return os.path.join(self.root, "victim_files")

    def _safe(self, path):
        path = os.path.abspath(path)
        if os.path.commonpath([self.root, path]) != self.root:
            raise RuntimeError(f"refusing to touch file outside sandbox: {path}")
        return path

    def ensure(self):
        os.makedirs(self.files_dir, exist_ok=True)
        for name, content in VAULT_FILES.items():
            p = self._safe(os.path.join(self.files_dir, name))
            if not os.path.exists(p):
                with open(p, "wb") as f:
                    f.write(content)

    def current(self):
        if not os.path.isdir(self.files_dir):
            return []
        return sorted(os.listdir(self.files_dir))

    def _ours(self, name):
        """True if this file is one of our fake files (or its .locked form)."""
        return name in VAULT_FILES or name.endswith(".locked") and name[:-7] in VAULT_FILES

    def lock_all(self):
        for name in self.current():
            if name.endswith(".locked") or not self._ours(name):
                continue
            p = self._safe(os.path.join(self.files_dir, name))
            os.rename(p, p + ".locked")

    def unlock_all(self):
        for name in self.current():
            if name.endswith(".locked") and self._ours(name):
                p = self._safe(os.path.join(self.files_dir, name))
                os.rename(p, p[:-len(".locked")])

    def destroy_all(self):
        for name in self.current():
            if self._ours(name):
                p = self._safe(os.path.join(self.files_dir, name))
                os.remove(p)


# ============================================================
#  Drawing primitives
# ============================================================

def draw_center(art, color_code, dy=0, dx=0, clr=True):
    cols, rows = size()
    if clr:
        cls()
    x = max(0, (cols - len(art[0])) // 2 + dx)
    y = max(0, (rows - len(art)) // 2 + dy)
    for i, line in enumerate(art):
        mv(y + i, x)
        out(col(line, color_code))
    return y, x


def draw_noise(n=50):
    """Scatter random red 'static' pixels over the screen."""
    cols, rows = size()
    chars = "▓▒░*#+."
    for _ in range(n):
        y = random.randint(0, rows - 1)
        x = random.randint(0, cols - 1)
        mv(y, x)
        out(col(random.choice(chars), random.choice(["r", "rr", "d"])))


def popup(header, lines, color_code="rr", dy=0):
    """Draw a fake window centered on screen. Returns (y, x, w, h)."""
    cols, rows = size()
    w = max(vis_len(header) + 5, max(vis_len(l) for l in lines) + 4)
    w = min(w + 2, cols - 2)
    h = len(lines) + 2
    x = max(0, (cols - w) // 2)
    y = max(0, (rows - h) // 2 + dy)
    fill = w - 5 - vis_len(header)
    mv(y, x)
    out(col("╔═ " + header + " " + "═" * max(0, fill) + "╗", color_code))
    for i, line in enumerate(lines):
        line = fit(line, w - 4)
        mv(y + 1 + i, x)
        out(col("║ ", color_code) +
            col(line + " " * max(0, w - 4 - vis_len(line)), "w") +
            col(" ║", color_code))
    mv(y + h - 1, x)
    out(col("╚" + "═" * (w - 2) + "╝", color_code))
    return y, x, w, h


def glitch_face(duration=0.9, face=FACE_NORMAL, dx=0, dy=0):
    """The face flickers in place with static."""
    end = time.time() + duration
    while time.time() < end:
        cls()
        y, x = draw_center(face, "w", dy=dy, dx=dx, clr=False)
        for _ in range(6):
            i = random.randint(0, len(face) - 1)
            j = random.randint(0, len(face[0]) - 1)
            if random.random() < 0.4:
                mv(y + i, x + j)
                out(col(random.choice("▓░#"), "rr"))
        sleep(0.05)


def jumpscare(term):
    """Red static + big face + bells."""
    for _ in range(3):
        bell()
        sleep(0.08)
    end = time.time() + 1.4
    while time.time() < end:
        cls()
        draw_center(FACE_JSCARE, "w", clr=False)
        draw_noise(80)
        sleep(0.06)


# ============================================================
#  Phase 1: intro
# ============================================================

def intro(term, args):
    cols, rows = size()
    cls()
    draw_center(LOGO, "rr", dy=-3)
    popup("R4NS0M.exe", [
        "DOORS Ransom simulator",
        "",
        "100% FAKE ransomware.",
        "Your real files are never touched.",
        "",
        "Vault (fake files):",
        os.path.expanduser(args.vault),
        "",
        "The ghost wants gold.",
        "Don't move when he watches.",
    ], dy=4)
    mv(rows - 1, max(0, (cols - 26) // 2))
    out(col("  >>> PRESS ANY KEY <<<  ", "blink", "rr"))
    if args.demo:
        sleep(0.4)
        return
    while True:
        k = term.get_key(0.05)
        if k is not None:
            if k == "q":
                raise KeyboardInterrupt
            return


# ============================================================
#  Phase 2: "infection" cinematic
# ============================================================

def infect(term, vault, args):
    cls()
    draw_center(FACE_NORMAL, "w", dy=-4)
    popup("I FOUND YOU", ["i know what is on your computer.", "", "now it is MINE."], dy=4)
    sleep(0.4 if args.demo else 1.6)

    cls()
    popup("ENCRYPTED", ["YOUR FILES BELONG TO US NOW.", "", "we accept payment in gold only."], dy=-6)
    names = sorted(VAULT_FILES)
    cols, rows = size()
    x0 = max(2, (cols - 44) // 2)
    y0 = rows // 2 + 2
    for i, name in enumerate(names):
        for step in range(5):
            mv(y0 + i, x0)
            bar = "▓" * (step * 2) + "░" * (10 - step * 2)
            out(col(f"[{bar}] {name}", "d"))
            sleep(0.02 if args.demo else 0.08)
        mv(y0 + i, x0)
        out(col(f"[{'▓' * 10}] {name}  ", "d") + col("LOCKED", "rr"))
    sleep(0.2 if args.demo else 0.6)
    popup("RANSOM", [
        f"PAY {args.gold} GOLD WITHIN {args.time} SECONDS",
        "or every file gets deleted.",
        "",
        "But first...",
        "he wants to play a game.",
    ], dy=-2)
    sleep(0.4 if args.demo else 1.4)

    cls()
    draw_center(STOP_SIGN, "rr", dy=-3)
    mv(rows // 2 + 4, max(0, (cols - 44) // 2))
    out(col("WHEN HIS FACE APPEARS — DO NOT MOVE.", "b", "w"))
    mv(rows // 2 + 5, max(0, (cols - 46) // 2))
    out(col("that means: do not press ANY key. AT ALL.", "d"))
    if args.demo:
        sleep(0.4)
        return
    sleep(1.6)
    term.flush()
    sleep(0.8)


# ============================================================
#  Phase 3: STOP rounds (the A-90 / Ransom minigame)
# ============================================================

def stop_rounds(term, args, stats):
    """Return True if the player got caught."""
    cols, rows = size()
    for rnd in range(1, args.rounds + 1):
        cls()
        mv(rows // 2, cols // 2)
        out(col("...", "d"))
        sleep(0.2 if args.demo else random.uniform(0.9, 1.6))

        # face phase: any key = caught
        warn = max(1.2, 3.0 - 0.7 * (rnd - 1))
        caught = False
        end = time.time() + warn
        while time.time() < end:
            cls()
            draw_center(FACE_NORMAL, "w", clr=False,
                        dx=random.randint(-6, 6), dy=random.randint(-3, 3))
            draw_noise(30)
            mv(1, max(0, (cols - 24) // 2))
            out(col("DO NOT MOVE", "b", "rr", "blink"))
            mv(rows - 2, max(0, (cols - 44) // 2))
            out(col(f"round {rnd}/{args.rounds} — he is watching you", "d"))
            if rnd == args.rounds:
                popup("YOU ARE AN IDIOT", ["PRESS ENTER", "go on. press it."],
                      dy=3)
            if term.get_key(0.04) is not None:
                caught = True
                break
        if caught:
            stats["rounds"] = rnd - 1
            return True

        # STOP sign phase: still no keys allowed
        end = time.time() + 0.9
        while time.time() < end:
            cls()
            draw_center(STOP_SIGN, "rr", clr=False)
            draw_noise(20)
            mv(rows - 2, max(0, (cols - 12) // 2))
            out(col("S T O P", "b", "rr", "blink"))
            if term.get_key(0.04) is not None:
                caught = True
                break
        if caught:
            stats["rounds"] = rnd - 1
            return True

        stats["rounds"] = rnd
        cls()
        popup("...", [f"he is gone. for now.  ({rnd}/{args.rounds})"])
        sleep(0.2 if args.demo else 1.0)
    return False


# ============================================================
#  Phase 4: the ransom attack (90s to collect 500 gold)
# ============================================================

BAR_W = 26


def attack(term, vault, args, stats):
    """Return True if the ransom was paid."""
    vault.lock_all()  # you were caught: NOW the files get "encrypted"
    cols, rows = size()
    limit = args.time
    need = args.gold
    deadline = time.time() + limit
    gold = 0
    honey_used = 0

    bar_pos = BAR_W // 2
    bar_dir = 1
    spots = random.sample(range(BAR_W), 4)
    next_tick = time.time()

    honey_at = time.time() + random.uniform(0.3, 0.65) * limit
    honey_until = None

    popup_at = time.time() + random.uniform(5, 9)
    popup_until = None
    popup_header = ""
    popup_lines = []

    msg = ""
    msg_until = 0

    demo_pushed_c = False
    demo_pushed_h = False

    cls()
    while True:
        now = time.time()
        if now >= deadline:
            return finish_failed(vault, stats, gold)

        # --- demo bot logic (pushes keys at the right moments) ---
        if args.demo:
            if popup_until:
                if not demo_pushed_c and now > popup_until - 0.35:
                    term.push("c")
                    demo_pushed_c = True
            else:
                demo_pushed_c = False
            if honey_until:
                if args.demo == "caught" and not demo_pushed_h and now > honey_until - 0.3:
                    term.push("h")
                    demo_pushed_h = True
            else:
                demo_pushed_h = False
            if args.demo == "caught" and not popup_until and not honey_until and bar_pos in spots:
                term.push(" ")

        # --- input ---
        k = term.get_key(0.03)
        if k in ("q", "esc"):
            raise KeyboardInterrupt

        if popup_until:
            if now >= popup_until or k == "c" or k == " ":
                popup_until = None
                popup_at = now + random.uniform(7, 14)
            k = None  # the popup swallows all other keys
        elif honey_until:
            if now >= honey_until:
                honey_until = None
                honey_at = now + random.uniform(8, 14)
                msg, msg_until = "the honey pot despawned...", now + 1.5
            elif k == "h":
                honey_until = None
                honey_used += 1
                cls()
                popup("RANSOM ACCEPTED", [
                    "HONEY POT!", "he takes the honey and leaves.", "",
                    "unlocking your files...",
                ])
                bell()
                sleep(0.5 if args.demo else 1.2)
                return finish_paid(vault, stats, gold, need, honey_used)
        else:
            if now >= popup_at:
                popup_header = random.choice(POPUP_HEADERS)
                line1, line2 = random.sample(POPUP_LINES, 2)
                popup_lines = [line1, line2]
                popup_until = now + 3.0
            if now >= honey_at and honey_until is None:
                honey_until = now + 2.2
                msg, msg_until = "", 0
            if k == " ":
                if bar_pos in spots:
                    gain = random.randint(40, 160)
                    gold += gain
                    spots.remove(bar_pos)
                    spots.append(random.choice(
                        [i for i in range(BAR_W) if i not in spots]))
                    msg, msg_until = col(f"+{gain} GOLD!", "y"), now + 1.2
                    if gold >= need:
                        sleep(0.3)
                        return finish_paid(vault, stats, gold, need, honey_used)
                else:
                    deadline -= 2
                    msg, msg_until = col("CLANK! -2s", "r"), now + 1.0

        # --- move the loot bar cursor ---
        if now >= next_tick:
            bar_pos += bar_dir
            if bar_pos <= 0 or bar_pos >= BAR_W - 1:
                bar_dir = -bar_dir
                bar_pos = max(0, min(BAR_W - 1, bar_pos))
            next_tick = now + 0.08

        # --- render ---
        left = max(0, int(deadline - now))
        mm, ss = left // 60, left % 60
        tcol = "rr" if left <= 15 else ("y" if left <= 30 else "w")

        cls()
        # HUD
        w = min(cols - 4, 58)
        x = max(0, (cols - w) // 2)
        mv(0, x)
        out(col("╔═ " + "R4NS0M" + " " + "═" * (w - 11) + "╗", "rr"))
        mv(1, x)
        time_part = f"TIME  {mm:02d}:{ss:02d}"
        gold_part = f"    GOLD  {gold} / {need}"
        pad = w - 4 - len(time_part) - len(gold_part)
        out(col("║ ", "rr") +
            col(time_part, tcol) + col(gold_part, "y") +
            " " * max(0, pad) + col(" ║", "rr"))
        mv(2, x)
        locked = "  ".join(col("✖", "r") + i for i in INVENTORY_ITEMS)
        line = fit("LOCKED: " + locked, w - 4)
        out(col("║ ", "rr") + line +
            " " * max(0, w - 4 - vis_len(line)) + col(" ║", "rr"))
        mv(3, x)
        out(col("╚" + "═" * (w - 2) + "╝", "rr"))

        # loot bar
        bar_y = rows // 2 + 1
        mv(bar_y - 1, max(0, (cols - 44) // 2))
        out(col("LOOT THE DRAWER — press SPACE on a $", "d"))
        cells = []
        for i in range(BAR_W):
            if i == bar_pos:
                cells.append(col("►", "b", "w"))
            elif i in spots:
                cells.append(col("$", "b", "y"))
            else:
                cells.append(col("─", "d"))
        mv(bar_y, max(0, (cols - BAR_W - 2) // 2))
        out("[" + "".join(cells) + "]")
        mv(bar_y + 1, max(0, (cols - 48) // 2))
        out(col("$ = gold   ► = you   CLANK = -2 seconds", "d"))

        # messages / honey pot
        if now < msg_until:
            mv(bar_y + 3, max(0, (cols - 60) // 2))
            out(msg)
        if honey_until:
            mv(bar_y + 5, max(0, (cols - 36) // 2))
            out(col("🍯 HONEY POT! PRESS H NOW! 🍯", "b", "y", "blink"))

        # popup overlays everything
        if popup_until:
            popup(popup_header, popup_lines + [
                "", f"TIME LEFT: {max(0, int(deadline - now))}s",
                col("press C to close", "d"),
            ], dy=-2)

        draw_noise(random.randint(0, 8))
        sleep(0.02)


def finish_paid(vault, stats, gold, need, honey_used):
    stats["gold"] = gold
    stats["honey"] = honey_used
    vault.unlock_all()
    names = vault.current()
    cols, rows = size()
    x0 = max(2, (cols - 44) // 2)
    for i, name in enumerate(names):
        mv(rows // 2 + 5 + i, x0)
        out(col("unlocked: ", "g") + name)
        sleep(0.04)
    sleep(0.3)
    return True


def finish_failed(vault, stats, gold):
    stats["gold"] = gold
    end = time.time() + 1.2
    while time.time() < end:
        cls()
        draw_center(FACE_JSCARE, "w", clr=False)
        draw_noise(90)
        sleep(0.05)
    popup("TIMES UP", [
        "the ransom was NOT paid.",
        "-55 HP",
        "",
        "deleting your encrypted files...",
    ], dy=3)
    bell()
    vault.destroy_all()
    sleep(0.5)
    return False


# ============================================================
#  Endings & main loop
# ============================================================

def verdict_screen(stats, vault, outcome):
    """outcome: 'paid' | 'failed' | 'avoided'"""
    cls()
    files = vault.current()
    if outcome == "paid":
        verdict = col("RANSOM PAID — you survived", "g")
        fstate = col(f"{len(files)} files restored", "g")
    elif outcome == "avoided":
        verdict = col("FIREWALL — he never caught you", "g")
        fstate = col(f"{len(files)} files untouched", "g")
    else:
        verdict = col("YOU GOT RANSOMED — 55 damage", "rr")
        fstate = col("your fake files were deleted", "rr")
    popup("FINAL REPORT", [
        verdict,
        "",
        f"stop rounds survived: {stats['rounds']}",
        f"gold looted: {stats['gold']}",
        f"honey pots grabbed: {stats['honey']}",
        fstate,
        "",
        col("it was all a simulation. nothing real happened.", "d"),
    ], dy=-2)
    cols, rows = size()
    mv(rows - 1, max(0, (cols - 22) // 2))
    out(col("  >>> PLAY AGAIN? Y/N <<<  ", "blink", "rr"))


def ask_again(term, args):
    if args.demo:
        sleep(0.3)
        return False
    while True:
        k = term.get_key(0.05)
        if k == "y":
            return True
        if k in ("n", "q", "esc", "enter"):
            return False


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="R4NS0M — fake DOORS-style ransomware simulator. 100% harmless.")
    p.add_argument("--time", type=int, default=90,
                   help="seconds to pay the ransom (DOORS: 90)")
    p.add_argument("--gold", type=int, default=500,
                   help="gold required (DOORS: 500)")
    p.add_argument("--rounds", type=int, default=3,
                   help="STOP rounds before the attack")
    p.add_argument("--vault", default=VAULT_DEFAULT,
                   help="sandbox folder for fake files (default: %(default)s)")
    p.add_argument("--demo", nargs="?", const="caught", choices=["caught", "avoid", "fail"],
                   help="automatic playthrough: caught/avoid/fail")
    args = p.parse_args(argv)
    args.time = max(5, min(args.time, 900))
    args.gold = max(50, min(args.gold, 99999))
    args.rounds = max(1, min(args.rounds, 9))
    return args


def main(argv=None):
    args = parse_args(argv)

    # sanity check on ASCII art widths (fail loudly, not with a broken UI)
    for name, art in [("FACE_NORMAL", FACE_NORMAL), ("FACE_JSCARE", FACE_JSCARE),
                      ("STOP_SIGN", STOP_SIGN), ("LOGO", LOGO)]:
        widths = {len(line) for line in art}
        if len(widths) != 1:
            print(f"art bug: {name} has uneven line widths {widths}")
            return 2

    term = Term()
    term.demo = args.demo is not None
    vault = Vault(args.vault)

    def on_signal(sig, frame):
        term.stop()
        sys.stdout.write("\n[!] Ransom despawned. (nothing was harmed)\n")
        sys.exit(130)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        while True:
            vault.ensure()
            stats = {"rounds": 0, "gold": 0, "honey": 0}
            term.start()
            try:
                intro(term, args)
                infect(term, vault, args)

                if args.demo in ("caught", "fail"):
                    term.push("x")  # bot moves on the first round
                caught = stop_rounds(term, args, stats)

                if caught:
                    jumpscare(term)
                    paid = attack(term, vault, args, stats)
                    verdict_screen(stats, vault, "paid" if paid else "failed")
                else:
                    verdict_screen(stats, vault, "avoided")

                again = ask_again(term, args)
            finally:
                term.stop()
            if not again:
                break
    except KeyboardInterrupt:
        term.stop()
        sys.stdout.write("\n[!] Ransom despawned. (nothing was harmed)\n")
        return 130

    sys.stdout.write("\nR4NS0M closed. All fake files live in: " +
                     vault.files_dir + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
