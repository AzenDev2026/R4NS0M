#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R4NS0M GUI — the standalone window version of the fake ransomware simulator.
Inspired by "Ransom" from Roblox DOORS (by LSPLASH).

Same game as ransom.py, but:
  * runs in its own pygame window (no terminal needed),
  * uses your images: ransom.jpeg (his face), stop.png (the STOP warning),
    yell.jpeg (his scream face),
  * screeches at you when he catches you moving.

Safety is identical: it only touches the fake files inside its sandbox
folder (~/.ransom_sim by default), has no network code, and can be
closed at any time.

Run:
    python3 ransom_gui.py
    python3 ransom_gui.py --time 60 --gold 300 --rounds 4
    python3 ransom_gui.py --demo caught|avoid|fail
    python3 ransom_gui.py --windowed   # opt out of fullscreen
"""

import argparse
import io
import math
import os
import random
import struct
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pygame

from ransom import (VAULT_FILES, INVENTORY_ITEMS, POPUP_HEADERS,
                    POPUP_LINES, Vault, VAULT_DEFAULT)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_RANSOM = os.path.join(BASE_DIR, "ransom.png")
IMG_STOP = os.path.join(BASE_DIR, "stop.png")
IMG_YELL = os.path.join(BASE_DIR, "yell.png")
IMG_LOUD_YELL = os.path.join(BASE_DIR, "loud-yell.png")
MP3_SCREAM = os.path.join(BASE_DIR, "ransom.mp3")

# ------------------------------------------------------------
#  colors
# ------------------------------------------------------------

BLACK = (5, 5, 8)
DARKRED = (26, 0, 0)
RED = (220, 20, 20)
BRIGHT_RED = (255, 60, 60)
WHITE = (240, 240, 240)
GRAY = (140, 140, 150)
DIMGRAY = (70, 70, 80)
YELLOW = (255, 210, 40)
GREEN = (90, 230, 90)
GOLD = (255, 200, 60)


# ------------------------------------------------------------
#  sounds (synthesized at runtime — no audio files needed)
# ------------------------------------------------------------

SR = 22050
_mixer_ok = False
_sounds = {}
_scream_chan = None
_scream_mp3 = False


def _wav_bytes(frames16):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames16)
    return buf.getvalue()


def _s16(samples):
    return b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000))
                    for s in samples)


def synth_screech():
    """Harsh distorted scream: noise + falling square + rising sine, clipped."""
    dur = 1.5
    n = int(SR * dur)
    frames = bytearray()
    for i in range(n):
        t = i / SR
        env = (1.0 - t / dur) ** 1.6
        noise = random.uniform(-1, 1)
        f = 260 - 180 * (t / dur)
        sq = 1.0 if ((i * f / SR) % 1.0) < 0.5 else -1.0
        fh = 1500 + 250 * math.sin(2 * math.pi * 9 * t) + 900 * (t / dur)
        sine = math.sin(2 * math.pi * fh * t)
        s = (noise * 0.55 + sq * 0.30 + sine * 0.45) * env * 0.95
        frames += _s16([max(-1.0, min(1.0, s * 1.9))])
    return frames


def synth_tada():
    """Windows-3.1-ish success jingle: two bright dings."""
    out = []
    for f in (1046.5, 1568.0):
        n = int(SR * 0.22)
        for i in range(n):
            t = i / SR
            out.append(math.sin(2 * math.pi * f * t) * (1 - i / n) ** 2 * 0.8)
    return _s16(out)


def synth_clank():
    out = []
    n = int(SR * 0.12)
    for i in range(n):
        t = i / SR
        out.append((1.0 if (i % 40) < 20 else -1.0) * (1 - i / n) * 0.7)
    return _s16(out)


def synth_blip():
    out = []
    for f in (880.0, 1318.5):
        n = int(SR * 0.09)
        for i in range(n):
            t = i / SR
            out.append(math.sin(2 * math.pi * f * t) * (1 - i / n) * 0.6)
    return _s16(out)


def init_audio():
    global _mixer_ok, _scream_chan, _scream_mp3
    try:
        pygame.mixer.init(frequency=SR, size=-16, channels=1, buffer=512)
        pygame.mixer.set_num_channels(8)
        _sounds["screech"] = pygame.mixer.Sound(buffer=_wav_bytes(synth_screech()))
        _sounds["tada"] = pygame.mixer.Sound(buffer=_wav_bytes(synth_tada()))
        _sounds["clank"] = pygame.mixer.Sound(buffer=_wav_bytes(synth_clank()))
        _sounds["blip"] = pygame.mixer.Sound(buffer=_wav_bytes(synth_blip()))
        _scream_chan = pygame.mixer.Channel(7)
        # the real scream (ransom.mp3) — falls back to the synth screech
        if os.path.exists(MP3_SCREAM):
            try:
                _sounds["scream"] = pygame.mixer.Sound(MP3_SCREAM)
                _scream_mp3 = True
            except Exception:
                pass
        _mixer_ok = True
    except Exception:
        _mixer_ok = False


def play(name):
    if _mixer_ok and name in _sounds:
        try:
            _sounds[name].play()
        except Exception:
            pass


def play_scream():
    """The 'you moved' scream: ransom.mp3 if available, synth screech else."""
    if not _mixer_ok or _scream_chan is None:
        return
    try:
        if _scream_mp3:
            _scream_chan.play(_sounds["scream"])
        else:
            _scream_chan.play(_sounds["screech"])
    except Exception:
        pass


def stop_scream():
    if _mixer_ok and _scream_chan is not None:
        try:
            _scream_chan.stop()
        except Exception:
            pass


# ------------------------------------------------------------
#  helpers
# ------------------------------------------------------------

_font_cache = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        path = pygame.font.match_font("dejavusansmono") or \
            pygame.font.match_font("monospace")
        try:
            f = pygame.font.Font(path, size)
        except Exception:
            f = pygame.font.Font(None, size)
        f.set_bold(bold)
        _font_cache[key] = f
    return _font_cache[key]


def text(s, size, color, bold=False):
    return font(size, bold).render(s, True, color)


def fit_text(s, f, maxw):
    """Chop a string so it fits maxw pixels (adds no ellipsis)."""
    while s and f.size(s)[0] > maxw:
        s = s[:-1]
    return s


def draw_window(surf, rect, title, title_color, border=BRIGHT_RED,
                fill=(30, 0, 0), radius=10):
    """Fake OS window with a title in the top bar."""
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    pygame.draw.rect(surf, border, rect, width=2, border_radius=radius)
    bar = pygame.Rect(rect.x, rect.y, rect.w, 30)
    pygame.draw.rect(surf, (120, 0, 0), bar, border_top_left_radius=radius,
                     border_top_right_radius=radius)
    if title:
        t = text(title, 22, title_color, bold=True)
        surf.blit(t, (rect.x + 12, rect.y + 3))


def draw_static(surf, n=60, seed=None):
    rnd = random if seed is None else random.Random(seed)
    w, h = surf.get_size()
    for _ in range(n):
        c = rnd.choice([(120, 0, 0), (200, 0, 0), (90, 90, 90), (40, 40, 40)])
        r = rnd.randint(0, h - 1)
        x = rnd.randint(0, w - 1)
        surf.fill(c, (x, r, rnd.randint(1, 4), rnd.randint(1, 4)))


def draw_glitch_face(surf, img, center, jitter=14, strips=10):
    """Blit the face with screen-tear strips and offset flicker."""
    w, h = surf.get_size()
    x = center[0] - img.get_width() // 2 + random.randint(-jitter, jitter)
    y = center[1] - img.get_height() // 2 + random.randint(-jitter, jitter)
    surf.blit(img, (x, y))
    for _ in range(strips):
        iy = random.randint(0, img.get_height() - 6)
        strip = img.subsurface((0, iy, img.get_width(), 6))
        surf.blit(strip, (x + random.randint(-24, 24), y + iy))


_vignette_cache = {}


def get_vignette(w, h):
    """Dark corners + red-tinged edges, pre-rendered once per size."""
    key = (w, h)
    if key not in _vignette_cache:
        gw, gh = max(48, w // 16), max(27, h // 16)
        small = pygame.Surface((gw, gh), pygame.SRCALPHA)
        for y in range(gh):
            for x in range(gw):
                nx = abs((x + 0.5) / gw - 0.5) * 2
                ny = abs((y + 0.5) / gh - 0.5) * 2
                d = min(1.0, max(nx, ny))
                a = int(210 * max(0.0, (d - 0.35) / 0.65) ** 1.5)
                if a:
                    small.set_at((x, y), (3, 0, 0, a))
        _vignette_cache[key] = pygame.transform.smoothscale(small, (w, h))
    return _vignette_cache[key]


def draw_red_pulse(screen, t):
    """Throbbing red border — panic heartbeat."""
    w, h = screen.get_size()
    a = int(90 + 90 * math.sin(t * 6))
    a = max(0, min(255, a))
    edge = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(edge, (255, 30, 30, a), (0, 0, w, h),
                     width=max(6, w // 90))
    screen.blit(edge, (0, 0))


# ------------------------------------------------------------
#  input (keys + mouse, demo bot queue)
# ------------------------------------------------------------

class Input:
    def __init__(self, demo=None):
        self.demo = demo
        self.queue = []

    def press(self, k):
        self.queue.append(k)

    def get_keys(self):
        keys = []
        while self.queue:
            keys.append(self.queue.pop(0))
        if self.demo:
            return keys
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                keys.append("quit")
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_RETURN:
                    keys.append("enter")
                elif ev.key == pygame.K_SPACE:
                    keys.append(" ")
                elif ev.key == pygame.K_ESCAPE:
                    keys.append("esc")
                elif ev.key == pygame.K_q:
                    keys.append("q")
                elif ev.key == pygame.K_c:
                    keys.append("c")
                elif ev.key == pygame.K_h:
                    keys.append("h")
                elif ev.key == pygame.K_y:
                    keys.append("y")
                elif ev.key == pygame.K_n:
                    keys.append("n")
                elif ev.key < 256:
                    keys.append(chr(ev.key).lower())
                else:
                    keys.append("key")
            elif ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                keys.append("mouse")  # in DOORS, moving = looking around too
        return keys


# ------------------------------------------------------------
#  phases
# ------------------------------------------------------------

def phase_warning(screen, inp, args, shot):
    """Consent gate: ask before the game really starts. Returns True to run."""
    clock = pygame.time.Clock()
    w, h = screen.get_size()
    if args.demo:
        end = time.time() + 0.4
        while time.time() < end:
            screen.fill(BLACK)
            screen.blit(get_vignette(w, h), (0, 0))
            draw_red_pulse(screen, time.time())
            draw_window(screen, pygame.Rect(w // 2 - 270, h // 2 - 160, 540, 320),
                        "R4NS0M.exe — RUN?", WHITE)
            for i, s in enumerate([
                    "This will:", "",
                    "• play LOUD screaming audio",
                    "• flash images and strobing lights",
                    "• pretend to encrypt fake files only",
                    "", "It will NOT harm your computer.",
                    "PRESS Y TO RUN / N TO ABORT",
            ]):
                c = YELLOW if i >= 7 else WHITE
                t = text(s, 22 if i >= 7 else 20, c, bold=(i >= 7))
                screen.blit(t, (w // 2 - 250, h // 2 - 110 + i * 30))
            draw_static(screen, 40)
            pygame.display.flip()
            clock.tick(30)
        if shot:
            pygame.image.save(screen, f"{shot}/00_warning.png")
        return True
    while True:
        keys = inp.get_keys()
        if "y" in keys:
            return True
        if "n" in keys:
            screen.fill(BLACK)
            t = text("smart choice.", 30, GRAY)
            screen.blit(t, ((w - t.get_width()) // 2, (h - 40) // 2))
            pygame.display.flip()
            pygame.time.wait(700)
            return False
        if "quit" in keys or "q" in keys or "esc" in keys:
            raise SystemExit(0)
        screen.fill(BLACK)
        screen.blit(get_vignette(w, h), (0, 0))
        draw_red_pulse(screen, time.time())
        rect = pygame.Rect(w // 2 - 270, h // 2 - 160, 540, 320)
        draw_window(screen, rect, "R4NS0M.exe — RUN?", WHITE)
        for i, s in enumerate([
                "This will:", "",
                "• play LOUD screaming audio",
                "• flash images and strobing lights",
                "• pretend to encrypt fake files only",
                "", "It will NOT harm your computer.",
                "PRESS Y TO RUN / N TO ABORT",
        ]):
            c = YELLOW if i >= 7 else WHITE
            t = text(s, 22 if i >= 7 else 20, c, bold=(i >= 7))
            screen.blit(t, (rect.x + 20, rect.y + 48 + i * 30))
        draw_static(screen, 40)
        pygame.display.flip()
        if shot and not getattr(phase_warning, "shot_done", False):
            pygame.image.save(screen, f"{shot}/00_warning.png")
            phase_warning.shot_done = True
        clock.tick(30)


def phase_intro(screen, inp, args, img_face, shot):
    clock = pygame.time.Clock()
    shot_saved = False

    def render():
        screen.fill(BLACK)
        w, h = screen.get_size()
        t = text("R4NS0M.exe", 84, BRIGHT_RED, bold=True)
        screen.blit(t, ((w - t.get_width()) // 2, h // 8))
        t2 = text("DOORS ransom simulator — 100% FAKE", 26, GRAY)
        screen.blit(t2, ((w - t2.get_width()) // 2, h // 8 + 90))
        draw_glitch_face(screen, img_face, (w // 2, h // 2), jitter=4, strips=6)
        t3 = text("your real files are never touched", 20, GRAY)
        screen.blit(t3, ((w - t3.get_width()) // 2, h - 130))
        t4 = text("vault: " + os.path.expanduser(args.vault), 18, DIMGRAY)
        screen.blit(t4, ((w - t4.get_width()) // 2, h - 100))
        if int(time.time() * 2) % 2 == 0:
            t5 = text(">>> PRESS ANY KEY <<<", 30, BRIGHT_RED, bold=True)
            screen.blit(t5, ((w - t5.get_width()) // 2, h - 60))
        screen.blit(get_vignette(w, h), (0, 0))
        draw_static(screen, 40)
        pygame.display.flip()

    if args.demo:
        render()
        if shot:
            pygame.image.save(screen, f"{shot}/01_intro.png")
        pygame.time.wait(400)
        return
    while True:
        keys = inp.get_keys()
        if "quit" in keys or "q" in keys or "esc" in keys:
            raise SystemExit(0)
        if keys:
            return
        render()
        if shot and not shot_saved:
            pygame.image.save(screen, f"{shot}/01_intro.png")
            shot_saved = True
        clock.tick(30)


def phase_infect(screen, inp, args, img_face, shot):
    clock = pygame.time.Clock()
    w, h = screen.get_size()

    def scene(dur, painter):
        end = time.time() + dur
        while time.time() < end:
            keys = inp.get_keys() if not args.demo else []
            if "quit" in keys:
                raise SystemExit(0)
            if not args.demo and keys:
                return True  # skip cinematic
            screen.fill(BLACK)
            painter()
            draw_static(screen, 30)
            pygame.display.flip()
            clock.tick(30)
        return False

    def paint_found():
        draw_glitch_face(screen, img_face, (w // 2, h // 2 - 40))
        draw_window(screen, pygame.Rect(w // 2 - 170, h // 2 + 80, 340, 110),
                    "I FOUND YOU", WHITE)
        t = text("i know what is on your computer.", 20, WHITE)
        screen.blit(t, (w // 2 - 158, h // 2 + 124))
        t = text("now it is MINE.", 20, WHITE)
        screen.blit(t, (w // 2 - 158, h // 2 + 152))

    def paint_encrypt():
        draw_window(screen, pygame.Rect(w // 2 - 220, 60, 440, 90),
                    "ENCRYPTED", WHITE)
        t = text("YOUR FILES BELONG TO US NOW.", 22, WHITE)
        screen.blit(t, (w // 2 - 208, 104))
        t = text("we accept payment in gold only.", 20, GRAY)
        screen.blit(t, (w // 2 - 208, 132))

    scene(1.6 if not args.demo else 0.3, paint_found)

    # fake encryption progress
    names = sorted(VAULT_FILES)
    start_t = time.time()
    end = start_t + (1.2 if not args.demo else 0.25)
    step_t = 0.0
    while time.time() < end:
        keys = inp.get_keys() if not args.demo else []
        if "quit" in keys:
            raise SystemExit(0)
        screen.fill(BLACK)
        draw_window(screen, pygame.Rect(w // 2 - 220, 60, 440, 90),
                    "ENCRYPTED", WHITE)
        t = text("YOUR FILES BELONG TO US NOW.", 22, WHITE)
        screen.blit(t, (w // 2 - 208, 104))
        t = text("we accept payment in gold only.", 20, GRAY)
        screen.blit(t, (w // 2 - 208, 132))
        for i, name in enumerate(names):
            frac = min(1.0, (time.time() - start_t) / 1.0 - i * 0.12)
            frac = max(0.0, frac)
            bar = pygame.Rect(w // 2 - 208, 210 + i * 34, 300, 20)
            pygame.draw.rect(screen, DIMGRAY, bar)
            pygame.draw.rect(screen, BRIGHT_RED,
                             (bar.x, bar.y, int(bar.w * frac), bar.h))
            t = text(name, 18, WHITE if frac < 1 else RED)
            screen.blit(t, (bar.x + 312, bar.y - 2))
        draw_static(screen, 20)
        pygame.display.flip()
        clock.tick(30)

    def paint_pay():
        draw_window(screen, pygame.Rect(w // 2 - 200, h // 2 - 70, 400, 150),
                    "RANSOM", WHITE)
        t = text(f"PAY {args.gold} GOLD WITHIN {args.time} SECONDS", 22,
                 YELLOW, bold=True)
        screen.blit(t, (w // 2 - 188, h // 2 - 20))
        t = text("or every file gets deleted.", 20, WHITE)
        screen.blit(t, (w // 2 - 188, h // 2 + 8))
        t = text("But first... he wants to play a game.", 18, GRAY)
        screen.blit(t, (w // 2 - 188, h // 2 + 36))

    scene(1.5 if not args.demo else 0.4, paint_pay)

    # stop tutorial
    end = time.time() + (1.8 if not args.demo else 0.4)
    while time.time() < end:
        keys = inp.get_keys() if not args.demo else []
        if "quit" in keys:
            raise SystemExit(0)
        screen.fill(BLACK)
        draw_glitch_face(screen, img_face, (w // 2, h // 2), jitter=3)
        t = text("WHEN HIS FACE APPEARS — DO NOT MOVE.", 34, WHITE, bold=True)
        screen.blit(t, ((w - t.get_width()) // 2, h - 120))
        t = text("that means: no keys. no mouse. nothing.", 22, GRAY)
        screen.blit(t, ((w - t.get_width()) // 2, h - 84))
        screen.blit(get_vignette(w, h), (0, 0))
        draw_static(screen, 30)
        pygame.display.flip()
        clock.tick(30)
    if shot:
        pygame.image.save(screen, f"{shot}/02_tutorial.png")


def phase_stop_rounds(screen, inp, args, img_face, img_stop, stats, shot):
    """Return True if caught. Any keypress OR mouse movement = caught."""
    clock = pygame.time.Clock()
    w, h = screen.get_size()

    for rnd in range(1, args.rounds + 1):
        # calm pause (pressing anything here still counts as moving!)
        moved = False
        end = time.time() + (0.5 if args.demo else random.uniform(0.9, 1.6))
        while time.time() < end:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    raise SystemExit(0)
                if ev.type in (pygame.KEYDOWN, pygame.MOUSEMOTION,
                               pygame.MOUSEBUTTONDOWN):
                    moved = True
            screen.fill(BLACK)
            t = text("...", 40, DIMGRAY)
            screen.blit(t, ((w - t.get_width()) // 2, (h - 40) // 2))
            pygame.display.flip()
            clock.tick(30)
        if moved and not args.demo:
            stats["rounds"] = rnd - 1
            return True

        # face watch phase
        warn = max(1.4, 3.0 - 0.6 * (rnd - 1))
        caught = False
        end = time.time() + warn
        while time.time() < end:
            keys = inp.get_keys()
            if "quit" in keys:
                raise SystemExit(0)
            if keys:
                caught = True
                break
            screen.fill(BLACK)
            jx = random.randint(-60, 60)
            jy = random.randint(-40, 40)
            draw_glitch_face(screen, img_face, (w // 2 + jx, h // 2 + jy))
            if int(time.time() * 3) % 2 == 0:
                t = text("DO NOT MOVE", 40, BRIGHT_RED, bold=True)
                screen.blit(t, ((w - t.get_width()) // 2, 24))
            t = text(f"round {rnd}/{args.rounds} — he is watching you", 20, GRAY)
            screen.blit(t, ((w - t.get_width()) // 2, h - 36))
            if rnd == args.rounds:
                draw_window(screen, pygame.Rect(w // 2 - 160, h // 2 + 130,
                                               320, 90), "YOU ARE AN IDIOT",
                            WHITE)
                t = text("PRESS ENTER", 26, WHITE, bold=True)
                screen.blit(t, (w // 2 - 148, h // 2 + 172))
                t = text("go on. press it.", 18, GRAY)
                screen.blit(t, (w // 2 - 148, h // 2 + 200))
            # rare fullscreen flash — he's toying with you
            if random.random() < 0.015:
                screen.blit(img_face, (random.randint(-40, w - img_face.get_width() + 40),
                                       random.randint(-40, h - img_face.get_height() + 40)))
            screen.blit(get_vignette(w, h), (0, 0))
            draw_static(screen, 60)
            pygame.display.flip()
            clock.tick(30)
        if shot:
            pygame.image.save(screen, f"{shot}/03_round{rnd}.png")
        if caught:
            stats["rounds"] = rnd - 1
            return True

        # stop sign flash phase
        end = time.time() + 1.0
        while time.time() < end:
            keys = inp.get_keys()
            if "quit" in keys:
                raise SystemExit(0)
            if keys:
                caught = True
                break
            screen.fill(DARKRED)
            st = img_stop if img_stop else None
            if st:
                screen.blit(st, ((w - st.get_width()) // 2,
                                 (h - st.get_height()) // 2))
            t = text("S T O P", 54, BRIGHT_RED, bold=True)
            screen.blit(t, ((w - t.get_width()) // 2, h - 80))
            screen.blit(get_vignette(w, h), (0, 0))
            draw_static(screen, 80)
            pygame.display.flip()
            clock.tick(30)
        if shot:
            pygame.image.save(screen, f"{shot}/03_stop{rnd}.png")
        if caught:
            stats["rounds"] = rnd - 1
            return True

        stats["rounds"] = rnd
        end = time.time() + (0.5 if args.demo else 1.0)
        while time.time() < end:
            screen.fill(BLACK)
            draw_window(screen, pygame.Rect(w // 2 - 150, h // 2 - 40, 300, 80),
                        "...", WHITE)
            t = text(f"he is gone. for now. ({rnd}/{args.rounds})", 20, GRAY)
            screen.blit(t, (w // 2 - 138, h // 2))
            pygame.display.flip()
            clock.tick(30)
    return False


def jumpscare(screen, args, img_yell, shot):
    """Audio FIRST, then yell.png: you hear the scream before you see it."""
    clock = pygame.time.Clock()
    w, h = screen.get_size()
    full = img_yell
    play_scream()
    # 1) scream only — black screen and static, the face stays hidden
    end = time.time() + (0.5 if not args.demo else 0.3)
    while time.time() < end:
        screen.fill(BLACK)
        draw_static(screen, 60)
        pygame.display.flip()
        clock.tick(30)
    # 2) the face appears, shaking
    end = time.time() + (1.4 if not args.demo else 0.7)
    while time.time() < end:
        screen.fill(BLACK)
        if full:
            ox = random.randint(-14, 14)
            oy = random.randint(-10, 10)
            screen.blit(full, ((w - full.get_width()) // 2 + ox,
                               (h - full.get_height()) // 2 + oy))
        draw_static(screen, 90)
        pygame.display.flip()
        clock.tick(30)
    if shot:
        pygame.image.save(screen, f"{shot}/04_jumpscare.png")


BAR_W = 26
CELL = 20


def phase_attack(screen, inp, args, vault, stats, img_face, shot):
    """Return True if the ransom was paid."""
    vault.lock_all()  # caught: NOW the fake files get "encrypted"
    clock = pygame.time.Clock()
    w, h = screen.get_size()

    limit, need = args.time, args.gold
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

    # his face randomly flashes near your items (DOORS detail)
    flash_until = None
    flash_pos = (0, 0)
    flash_at = time.time() + random.uniform(2.5, 5)
    tear_at = 0.0

    msg, msg_until = None, 0
    demo_c, demo_h = False, False

    while True:
        now = time.time()
        if now >= deadline:
            play_scream()
            return finish_failed(screen, args, vault, stats, gold, shot)

        # demo bot
        if args.demo:
            if popup_until and not demo_c and now > popup_until - 0.4:
                inp.press("c")
                demo_c = True
            if not popup_until:
                demo_c = False
            if honey_until and not demo_h and now > honey_until - 0.3 \
                    and args.demo == "caught":
                inp.press("h")
                demo_h = True
            if not honey_until:
                demo_h = False
            if args.demo == "caught" and not popup_until and not honey_until \
                    and bar_pos in spots:
                inp.press(" ")

        keys = inp.get_keys()
        if "quit" in keys or "q" in keys or "esc" in keys:
            raise SystemExit(0)

        if popup_until:
            if now >= popup_until or "c" in keys or " " in keys:
                popup_until = None
                popup_at = now + random.uniform(7, 14)
            keys = []
        elif honey_until:
            if now >= honey_until:
                honey_until = None
                honey_at = now + random.uniform(8, 14)
                msg, msg_until = "the honey pot despawned...", now + 1.5
            elif "h" in keys:
                honey_until = None
                honey_used += 1
                stop_scream()
                play("tada")
                draw_pay_popup(screen, args, honey=True)
                return finish_paid(vault, stats, gold, honey_used)
        else:
            if now >= popup_at:
                popup_header = random.choice(POPUP_HEADERS)
                popup_lines = random.sample(POPUP_LINES, 2)
                popup_until = now + 3.0
            if now >= honey_at and honey_until is None:
                honey_until = now + 2.2
                play("blip")
                msg, msg_until = None, 0
            if " " in keys:
                if bar_pos in spots:
                    gain = random.randint(40, 160)
                    gold += gain
                    spots.remove(bar_pos)
                    spots.append(random.choice(
                        [i for i in range(BAR_W) if i not in spots]))
                    msg, msg_until = f"+{gain} GOLD!", now + 1.2
                    if gold >= need:
                        stop_scream()
                        play("tada")
                        draw_pay_popup(screen, args)
                        return finish_paid(vault, stats, gold, honey_used)
                else:
                    play("clank")
                    deadline -= 2
                    msg, msg_until = "CLANK! -2s", now + 1.0

        if now >= next_tick:
            bar_pos += bar_dir
            if bar_pos <= 0 or bar_pos >= BAR_W - 1:
                bar_dir = -bar_dir
                bar_pos = max(0, min(BAR_W - 1, bar_pos))
            next_tick = now + 0.08

        # face flash scheduling
        if flash_until is None and now >= flash_at:
            flash_until = now + 0.16
            flash_pos = (random.randint(int(w * 0.15), int(w * 0.85)),
                         random.randint(int(h * 0.2), int(h * 0.8)))
        elif flash_until is not None and now >= flash_until:
            flash_until = None
            flash_at = now + random.uniform(3.5, 7.0)

        # ---- render ----
        screen.fill(BLACK)
        left = max(0, int(deadline - now))
        mm, ss = left // 60, left % 60
        tcol = BRIGHT_RED if left <= 15 else (YELLOW if left <= 30 else WHITE)

        # panic effects when time runs low: shaking + screen tears
        if left <= 15:
            shx, shy = random.randint(-3, 3), random.randint(-2, 2)
            draw_red_pulse(screen, now)
            if now >= tear_at:
                tear_at = now + random.uniform(0.25, 0.5)
                try:
                    copy = pygame.Surface.copy(screen)
                    for _ in range(3):
                        sy = random.randint(0, h - 30)
                        strip = copy.subsurface((0, sy, w, random.randint(4, 22)))
                        screen.blit(strip, (random.randint(-18, 18), sy))
                except Exception:
                    pass
        else:
            shx, shy = 0, 0

        hud = pygame.Rect(w // 2 - 380 + shx, 16 + shy, 760, 110)
        draw_window(screen, hud, "R4NS0M", WHITE)
        t = text(f"TIME  {mm:02d}:{ss:02d}", 30, tcol, bold=True)
        screen.blit(t, (hud.x + 20, hud.y + 40))
        t = text(f"GOLD  {gold} / {need}", 30, YELLOW, bold=True)
        screen.blit(t, (hud.x + hud.w - t.get_width() - 20, hud.y + 40))
        locked = "  ".join("X" + i for i in INVENTORY_ITEMS)
        t = fit_text("LOCKED: " + locked, font(18), hud.w - 40)
        screen.blit(text(t, 18, RED), (hud.x + 20, hud.y + 82))

        # loot bar
        ly = h // 2 + 40
        label = text("LOOT THE DRAWER — press SPACE on a $", 22, GRAY)
        screen.blit(label, ((w - label.get_width()) // 2, ly - 44))
        bx = (w - BAR_W * CELL) // 2
        for i in range(BAR_W):
            cell = pygame.Rect(bx + i * CELL, ly, CELL - 2, 30)
            if i == bar_pos:
                pygame.draw.rect(screen, WHITE, cell)
            elif i in spots:
                pygame.draw.rect(screen, (60, 45, 0), cell)
                t = text("$", 22, YELLOW, bold=True)
                screen.blit(t, (cell.x + 5, ly + 3))
            else:
                pygame.draw.rect(screen, DIMGRAY, cell)
        hint = text("$ = gold   ▮ = you   CLANK = -2 seconds", 18, DIMGRAY)
        screen.blit(hint, ((w - hint.get_width()) // 2, ly + 44))

        if msg and now < msg_until:
            color = YELLOW if msg.startswith("+") else RED
            t = text(msg, 34, color, bold=True)
            screen.blit(t, ((w - t.get_width()) // 2, ly + 80))

        if honey_until:
            pot_x, pot_y = w // 2, ly + 130
            pygame.draw.circle(screen, GOLD, (pot_x - 40, pot_y), 26)
            pygame.draw.circle(screen, GOLD, (pot_x + 40, pot_y), 26)
            pygame.draw.rect(screen, GOLD, (pot_x - 40, pot_y - 26, 80, 52))
            pygame.draw.ellipse(screen, (150, 100, 0), (pot_x - 46, pot_y - 34,
                                                        92, 16))
            if int(now * 4) % 2 == 0:
                t = text("HONEY POT! PRESS H NOW!", 32, YELLOW, bold=True)
                screen.blit(t, ((w - t.get_width()) // 2, pot_y + 40))

        if popup_until:
            rect = pygame.Rect(w // 2 - 210, h // 2 - 110, 420, 200)
            draw_window(screen, rect, popup_header, WHITE)
            for i, line in enumerate(popup_lines):
                t = text(line, 22, WHITE)
                screen.blit(t, (rect.x + 20, rect.y + 48 + i * 32))
            t = text(f"TIME LEFT: {max(0, int(deadline - now))}s", 22, YELLOW)
            screen.blit(t, (rect.x + 20, rect.y + 118))
            t = text("press C to close", 18, GRAY)
            screen.blit(t, (rect.x + 20, rect.y + 150))

        # his face flashes next to your encrypted items
        if flash_until is not None and img_face is not None:
            screen.blit(img_face, (flash_pos[0] - img_face.get_width() // 2,
                                   flash_pos[1] - img_face.get_height() // 2))

        screen.blit(get_vignette(w, h), (0, 0))
        draw_static(screen, random.randint(0, 14))
        pygame.display.flip()
        if shot and not getattr(phase_attack, "shot_done", False):
            pygame.image.save(screen, f"{shot}/05_attack.png")
            phase_attack.shot_done = True
        clock.tick(30)


def draw_pay_popup(screen, args, honey=False):
    """Show the 'ransom accepted' window for a moment."""
    w, h = screen.get_size()
    screen.fill(BLACK)
    rect = pygame.Rect(w // 2 - 220, h // 2 - 80, 440, 160)
    draw_window(screen, rect, "RANSOM ACCEPTED", WHITE)
    line1 = "he takes the honey and leaves." if honey else "GOLD ACCEPTED."
    t = text(line1, 24, YELLOW, bold=True)
    screen.blit(t, (rect.x + 20, rect.y + 44))
    t = text("unlocking your files...", 22, GRAY)
    screen.blit(t, (rect.x + 20, rect.y + 80))
    pygame.display.flip()
    pygame.time.wait(500 if args.demo else 1200)


def finish_paid(vault, stats, gold, honey_used):
    stats["gold"] = gold
    stats["honey"] = honey_used
    vault.unlock_all()
    return True


def finish_failed(screen, args, vault, stats, gold, shot):
    """Timeout: the scream already started; loud-yell.png appears after it."""
    stats["gold"] = gold
    img = load_img(IMG_LOUD_YELL)
    w, h = screen.get_size()
    full = pygame.transform.scale(
        img, (int(h * img.get_width() / img.get_height()), h)) \
        if img else None
    clock = pygame.time.Clock()
    # 1) scream only — black + static, no face yet
    end = time.time() + (0.6 if not args.demo else 0.3)
    while time.time() < end:
        screen.fill(BLACK)
        draw_static(screen, 80)
        pygame.display.flip()
        clock.tick(30)
    # 2) loud-yell.png slams in, shaking
    end = time.time() + 1.2
    while time.time() < end:
        screen.fill(BLACK)
        if full:
            screen.blit(full, ((w - full.get_width()) // 2 +
                               random.randint(-12, 12),
                               random.randint(-8, 8)))
        draw_static(screen, 90)
        pygame.display.flip()
        clock.tick(30)
    if shot:
        pygame.image.save(screen, f"{shot}/06_loudyell.png")
    screen.fill(BLACK)
    rect = pygame.Rect(w // 2 - 210, h // 2 - 70, 420, 170)
    draw_window(screen, rect, "TIMES UP", WHITE)
    t = text("the ransom was NOT paid.", 24, WHITE)
    screen.blit(t, (rect.x + 20, rect.y + 44))
    t = text("-55 HP", 26, BRIGHT_RED, bold=True)
    screen.blit(t, (rect.x + 20, rect.y + 76))
    t = text("deleting your encrypted files...", 20, GRAY)
    screen.blit(t, (rect.x + 20, rect.y + 110))
    pygame.display.flip()
    vault.destroy_all()
    pygame.time.wait(500 if args.demo else 900)
    if shot:
        pygame.image.save(screen, f"{shot}/06_timesup.png")
    return False


def verdict_screen(screen, inp, args, stats, vault, outcome, shot):
    clock = pygame.time.Clock()
    w, h = screen.get_size()
    files = vault.current()
    if outcome == "paid":
        verdict, vcol = "RANSOM PAID — you survived", GREEN
        fstate, fcol = f"{len(files)} files restored", GREEN
    elif outcome == "avoided":
        verdict, vcol = "FIREWALL — he never caught you", GREEN
        fstate, fcol = f"{len(files)} files untouched", GREEN
    else:
        verdict, vcol = "YOU GOT RANSOMED — 55 damage", BRIGHT_RED
        fstate, fcol = "your fake files were deleted", BRIGHT_RED
    while True:
        keys = inp.get_keys()
        if "quit" in keys:
            raise SystemExit(0)
        screen.fill(BLACK)
        rect = pygame.Rect(w // 2 - 240, h // 2 - 150, 480, 300)
        draw_window(screen, rect, "FINAL REPORT", WHITE)
        lines = [
            (verdict, vcol, 30, True),
            ("", WHITE, 18, False),
            (f"stop rounds survived: {stats['rounds']}", WHITE, 20, False),
            (f"gold looted: {stats['gold']}", WHITE, 20, False),
            (f"honey pots grabbed: {stats['honey']}", WHITE, 20, False),
            (fstate, fcol, 20, False),
            ("", WHITE, 18, False),
            ("it was all a simulation. nothing real happened.", GRAY, 16, False),
        ]
        y = rect.y + 44
        for s, c, sz, b in lines:
            if s:
                t = text(s, sz, c, bold=b)
                screen.blit(t, (rect.x + 24, y))
            y += 34
        if int(time.time() * 2) % 2 == 0:
            t = text(">>> PLAY AGAIN? Y/N <<<", 28, BRIGHT_RED, bold=True)
            screen.blit(t, ((w - t.get_width()) // 2, h - 60))
        draw_static(screen, 30)
        pygame.display.flip()
        if shot and not getattr(verdict_screen, "shot_done", False):
            pygame.image.save(screen, f"{shot}/07_verdict.png")
            verdict_screen.shot_done = True
        if args.demo:
            pygame.time.wait(400)
            return False
        if "y" in keys or "n" in keys or "enter" in keys:
            return "y" in keys
        clock.tick(30)


# ------------------------------------------------------------
#  image loading
# ------------------------------------------------------------

_img_cache = {}


def load_img(path):
    if path not in _img_cache:
        try:
            _img_cache[path] = pygame.image.load(path).convert_alpha()
        except Exception:
            _img_cache[path] = None
    return _img_cache[path]


def scale_img(path, size):
    img = load_img(path)
    return pygame.transform.scale(img, size) if img else None


# ------------------------------------------------------------
#  main
# ------------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(
        description="R4NS0M GUI — fake DOORS-style ransomware in its own window.")
    p.add_argument("--time", type=int, default=90)
    p.add_argument("--gold", type=int, default=500)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--vault", default=VAULT_DEFAULT)
    p.add_argument("--demo", nargs="?", const="caught",
                   choices=["caught", "avoid", "fail"])
    p.add_argument("--windowed", action="store_true",
                   help="run in a window instead of fullscreen (default: fullscreen)")
    p.add_argument("--shot", metavar="DIR",
                   help="debug: save screenshots to DIR at phase changes")
    args = p.parse_args(argv)
    args.time = max(5, min(args.time, 900))
    args.gold = max(50, min(args.gold, 99999))
    args.rounds = max(1, min(args.rounds, 9))
    return args


def main(argv=None):
    args = parse_args(argv)
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    pygame.init()
    init_audio()
    if args.shot:
        os.makedirs(args.shot, exist_ok=True)

    flags = 0 if args.windowed else pygame.FULLSCREEN
    screen = pygame.display.set_mode((0, 0), flags) if not args.windowed \
        else pygame.display.set_mode((900, 600), 0)
    pygame.display.set_caption("R4NS0M.exe")
    icon = load_img(IMG_STOP)
    if icon:
        pygame.display.set_icon(pygame.transform.scale(icon, (32, 32)))

    # scale images to the window
    w, h = screen.get_size()
    face_size = int(min(w, h) * 0.55)
    img_face = scale_img(IMG_RANSOM, (face_size, face_size))
    stop_size = int(min(w, h) * 0.5)
    img_stop = scale_img(IMG_STOP, (stop_size, stop_size))
    img_yell = load_img(IMG_YELL)
    if img_yell:
        yh = int(h * 0.9)
        img_yell = pygame.transform.scale(
            img_yell, (int(yh * img_yell.get_width() / img_yell.get_height()), yh))
    img_loud = load_img(IMG_LOUD_YELL)
    if img_loud:
        lh = int(h * 0.95)
        img_loud = pygame.transform.scale(
            img_loud, (int(lh * img_loud.get_width() / img_loud.get_height()), lh))

    inp = Input(demo=args.demo)
    vault = Vault(args.vault)

    if args.demo in ("caught", "fail"):
        inp.press("x")  # bot moves on the first round

    try:
        while True:
            vault.ensure()
            stats = {"rounds": 0, "gold": 0, "honey": 0}
            if not phase_warning(screen, inp, args, args.shot):
                break  # player declined to run it
            phase_intro(screen, inp, args, img_face, args.shot)
            phase_infect(screen, inp, args, img_face, args.shot)
            caught = phase_stop_rounds(screen, inp, args, img_face, img_stop,
                                       stats, args.shot)
            if caught:
                jumpscare(screen, args, img_yell, args.shot)
                paid = phase_attack(screen, inp, args, vault, stats,
                                    img_face, args.shot)
                verdict_screen(screen, inp, args, stats, vault,
                               "paid" if paid else "failed", args.shot)
            else:
                verdict_screen(screen, inp, args, stats, vault, "avoided",
                               args.shot)
            # demo quits after one playthrough; humans decide at the verdict
            if args.demo:
                break
    except SystemExit:
        raise
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
