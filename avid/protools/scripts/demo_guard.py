#!/usr/bin/env python3
"""demo_guard.py: auto-answer the pop-ups Pro Tools throws while sessions open.

Default rules (edit scan() to change them):
  * plug-in demo / trial prompts (e.g. "Free 14-Day Demo")    -> Cancel (never Start Demo / Buy)
  * "Session Notes" I/O mismatch notice                       -> No (don't save a report)
  * "Missing AAX Plugins" / "Missing ..." notices              -> OK (plug-ins load inactive)
  * "Some of the inserts could not be made active" (OK-only)  -> OK
Settings windows (Playback Engine, I/O Setup, ...) are never touched: a broader
"any OK-only window" rule once closed a Playback Engine window, so it was removed.
Anything else is logged once (title, text, buttons) and left for a human.

Runs until stopped (Ctrl+C). macOS only; needs the same Accessibility grant as
ptax.py. Run it in its own terminal while a big session opens:
    .venv/bin/python scripts/demo_guard.py | tee -a demo_guard.log
"""
import os, sys, time, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__); sys.exit(0)
from ptax import AXUIElementCreateApplication, attr, children, walk, press

APPS = ["Pro Tools", "UA Connect", "UA Cloud Helper"]
WORDS = ("demo", "trial")
SEEN = set()


def pids():
    out = []
    for name in APPS:
        r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True).stdout.split()
        out += [(name, int(p)) for p in r]
    return out


def scan():
    for name, pid in pids():
        for w in children(AXUIElementCreateApplication(pid)):
            if attr(w, "AXRole") != "AXWindow":
                continue
            title = str(attr(w, "AXTitle") or "")
            if title.startswith(("Edit:", "Mix:")):
                continue
            text, cancel, buttons = [title], None, {}
            for el, d, _ in walk(w, max_depth=8):
                r = attr(el, "AXRole")
                if r in ("AXStaticText", "AXTextArea"):
                    text.append(str(attr(el, "AXValue") or ""))
                elif r == "AXButton":
                    t = str(attr(el, "AXTitle") or attr(el, "AXDescription") or "")
                    text.append(t)
                    if t.strip():
                        buttons[t.strip().lower()] = el
                    if t.strip().lower() == "cancel":
                        cancel = el
            blob = " ".join(text).lower()
            key = (title, tuple(buttons))
            now = f"{datetime.datetime.now():%H:%M:%S}"
            if cancel is not None and any(wd in blob for wd in WORDS):
                press(cancel)
                print(f"{now} cancelled demo prompt in {name}: {' '.join(blob.split())[:100]}", flush=True)
            elif title == "Session Notes" and "no" in buttons:
                press(buttons["no"])
                print(f"{now} answered No to Session Notes", flush=True)
            elif "inserts could not be made active" in blob and list(buttons) == ["ok"]:
                press(buttons["ok"])
                print(f"{now} pressed OK on inactive-inserts notice", flush=True)
            elif title.startswith("Missing") and "ok" in buttons:
                press(buttons["ok"])
                print(f"{now} pressed OK on {title}: {' '.join(blob.split())[:300]}", flush=True)
            elif buttons and key not in SEEN and "locating" not in blob and not (list(buttons) == ["cancel"]):
                SEEN.add(key)
                print(f"{now} UNHANDLED dialog in {name}: title={title!r} buttons={list(buttons)} text={' '.join(blob.split())[:200]}", flush=True)


if __name__ == "__main__":
    print(f"{datetime.datetime.now():%H:%M:%S} demo_guard started", flush=True)
    while True:
        try:
            scan()
        except Exception as ex:
            print("scan error:", ex, flush=True)
        time.sleep(2)
