# R4NS0M

A **100% fake ransomware simulator**, inspired by
[**Ransom**](https://doorsgame.wiki/wiki/Ransom), the entity from
Roblox [DOORS](https://www.roblox.com/games/6516141723/DOORS) by LSPLASH.

It looks like ransomware. It sounds like ransomware. It even shows you
fake files being "encrypted". But it never touches anything real —
it is a game, and the game is: **don't get ransomed**.

Two versions live here:

| Version        | File            | Needs                     |
| -------------- | --------------- | ------------------------- |
| **GUI window** | `ransom_gui.py` | `pygame-ce` (see below)   |
| Terminal       | `ransom.py`     | nothing (stdlib only)     |

The GUI version is the main game: it runs **fullscreen** in its own
window (no terminal needed), uses the art in this folder (`ransom.png`
his face, `stop.png` the STOP warning, `yell.png` his scream,
`loud-yell.png` the time-out scream), and **screams at you** with
`ransom.mp3` when he catches you moving — the audio starts *before*
the face appears, so you hear him before you see him.

Before the game really starts it shows a warning screen: loud audio,
strobing lights, fake file changes — press **Y** to run or **N** to
abort (photosensitivity warning included).

## The Ransom mechanic (straight from DOORS)

In DOORS, Ransom is a glitchy monochrome face that appears on your
screen and flashes a red STOP sign. If you move — even one keypress —
he jumpscares you, "encrypts" all the items in your inventory, and
gives you **90 seconds to collect 500 Gold** to buy them back.
Fail, and he takes 55 HP and deletes the items forever.

This simulator recreates that in three phases:

1. **Infection** — popups and red static announce that your files
   are "encrypted" (only the fake files in the sandbox, see below).
2. **STOP rounds** — his face appears. Press *nothing* — and don't
   move the mouse either: in the GUI version, mouse movement counts
   as moving. Clear every round and you get the **FIREWALL** ending.
   The last round even shows a "PRESS ENTER" popup. Don't fall for it.
3. **The attack** — if you moved, he screams at you (audio first,
   then his face), your inventory is locked and the clock starts:
   collect the gold by looting drawers (press `SPACE` when the cursor
   hits a `$`), close the popup spam (`C`), and grab the 🍯 **Honey
   Pot** (`H`) if it appears — it pays the whole ransom instantly.
   His face keeps flashing at random spots on the screen, and when
   the timer drops below 15 seconds the screen shakes, tears and
   pulses red. Time out and `loud-yell.png` slams in — your fake
   files get deleted.

## Safety

This program is **theatre, not malware**:

- It only creates / renames / deletes a handful of fake files inside
  its own sandbox folder (`~/.ransom_sim/victim_files` by default).
  A guard refuses to touch any path outside that folder.
- It has **no network code** at all.
- Closing the window, `Q` or `Esc` stops it at any time.

Please keep it that way — this is a game. Never write real ransomware.

## Run

```bash
# GUI window (main version — always fullscreen)
pip install --user --break-system-packages pygame-ce   # one-time setup
python3 ransom_gui.py
python3 ransom_gui.py --time 60 --gold 300 --rounds 4
python3 ransom_gui.py --windowed        # run in a window instead
python3 ransom_gui.py --demo caught     # watch a bot get ransomed and pay
python3 ransom_gui.py --demo avoid      # watch a bot clear the STOP rounds
python3 ransom_gui.py --demo fail       # watch a bot get his files deleted

# or double-click  R4NS0M.desktop  (right-click → Allow launching)
```

Terminal version (no dependencies):

```bash
python3 ransom.py
python3 ransom.py --demo caught
```

| Option       | Default          | Meaning                                   |
| ------------ | ---------------- | ----------------------------------------- |
| `--time`     | `90`             | Seconds to pay the ransom                 |
| `--gold`     | `500`            | Gold required (DOORS values: 90 / 500)    |
| `--rounds`   | `3`              | Number of STOP rounds                     |
| `--vault`    | `~/.ransom_sim`  | Sandbox folder for the fake files         |
| `--demo`     | —                | Automatic playthrough (no keyboard needed)|
| `--windowed` | —                | GUI: window instead of fullscreen         |

## Controls (GUI)

| Input     | When                          | Action                        |
| --------- | ----------------------------- | ----------------------------- |
| `Y`/`N`   | warning screen                | run it / abort                 |
| *(none)*  | face / STOP sign appears      | stay perfectly still (or else)|
| `SPACE`   | loot bar, cursor on `$`       | grab 40–160 gold              |
| `C`       | popup covering the screen     | close it (timer keeps running)|
| `H`       | honey pot appears             | pay the ransom instantly      |
| `Q`/`Esc` | anywhere                      | quit (ransom despawned)       |

## Files

- `ransom_gui.py` — the pygame window version (images + sound).
- `ransom.py` — the terminal version, stdlib only (Python 3.8+).
- `ransom.png` / `stop.png` / `yell.png` / `loud-yell.png` — the game art.
- `ransom.mp3` — the scream that plays when he catches you moving
  (falls back to a synthesized screech if the file is missing).
- `R4NS0M.desktop` — desktop launcher for the GUI version.
- `shots/` — screenshots of the game.
- `test_pty.py` — drives the terminal version through a pseudo-terminal.

`ransom.mp3` plays on the trigger (any keypress or mouse movement
while he is watching, and again if the timer runs out). It starts
*slightly before* the face appears, keeps screaming while you loot
(like the R4NS0M track in DOORS), and stops the moment you pay.
Everything else (tada, clank, honey blip) is synthesized at startup,
so the only audio file needed is the scream.

Inspired by DOORS (© LSPLASH). Popup titles are real DOORS trivia
from the [official wiki](https://doorsgame.wiki/wiki/Ransom).
