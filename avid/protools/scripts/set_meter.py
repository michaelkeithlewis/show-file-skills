"""set_meter.py N/D [--click "1/8 note"] [--dotted] -> set the meter at bar 1 (1|1|000) through the Meter
ruler's Meter Change dialog. PTSL has no meter write, so this goes through Accessibility (ptax), like
set_tempo.py. The dialog opens at the insertion point, so it refuses unless that is bar 1. The two meter
fields ignore AXValue and AXFocused writes, so each is pressed (AXPress focuses it) and typed into with CGEventPostToPid (Pro Tools only).
--click picks the metronome value (default: 1/D note, so a 6/8 bar clicks six eighths).
Set the meter BEFORE the tempo: Pro Tools tempo is quarter-note BPM in any meter."""
import argparse, os, sys, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from ptgui import text, user_idle_secs

ap = argparse.ArgumentParser(); ap.add_argument("meter"); ap.add_argument("--click"); ap.add_argument("--dotted", action="store_true")
ap.add_argument("--force", action="store_true"); a = ap.parse_args()
if user_idle_secs() < 120 and not a.force:
    sys.exit(f"someone used the Mac {user_idle_secs():.0f} s ago; rerun when Pro Tools is free (or --force)")
num, den = a.meter.split("/")
click = a.click or f"1/{den} note"

edit = ptax.window("Edit:")
btn = ptax.find(edit, "AXButton", "Add Meter Change", max_depth=8)
if btn is None:
    sys.exit("no Add Meter Change button (is the Meter ruler shown?)")
ptax.press(btn); time.sleep(1.5)
w = ptax.window("Meter Change")
fields = [el for el, d, _ in ptax.walk(w, max_depth=2) if ptax.attr(el, "AXRole") == "AXTextField"]
loc, fn, fd = fields
cancel = lambda: ptax.press(ptax.find(w, "AXButton", "Cancel", max_depth=2))
where = " ".join(str(ptax.attr(loc, "AXValue")).split())
if where != "1| 1| 000":
    cancel(); sys.exit(f"dialog opened at {where!r}, not bar 1; put the insertion point at the session start and retry")
for f, v in ((fn, num), (fd, den)):
    ptax.press(f); time.sleep(0.4)
    text(v); time.sleep(0.4)
got = (str(ptax.attr(fn, "AXValue")).strip(), str(ptax.attr(fd, "AXValue")).strip())
if got != (num, den):
    cancel(); sys.exit(f"meter fields read {got}, cancelled")
pop = ptax.find(w, "AXPopUpButton", "MeterClickMenu", max_depth=2)
if str(ptax.attr(pop, "AXValue")) != click:
    ptax.press(pop); time.sleep(0.6)
    m = ptax.item(ptax.popup_dialog(), title=click)
    if m is None:
        ptax.close_popup(); cancel(); sys.exit(f"no click value {click!r}")
    ptax.press(m); time.sleep(0.5)
if a.dotted:
    ptax.press(pop); time.sleep(0.6); ptax.press(ptax.item(ptax.popup_dialog(), title="dotted")); time.sleep(0.5)
ptax.press(ptax.find(w, "AXButton", "OK", max_depth=2)); time.sleep(1.5)
ruler = next(el for el, d, _ in ptax.walk(ptax.window("Edit:"), max_depth=8)
             if ptax.attr(el, "AXRole") == "AXTable" and ptax.attr(el, "AXTitle") == "Meter")
shown = [str(ptax.attr(el, "AXValue")) for el, d, _ in ptax.walk(ruler, max_depth=4) if ptax.attr(el, "AXRole") == "AXStaticText"]
print("METER", shown, "OK" if shown and shown[0] == f"{num}/{den}" else "CHECK")
