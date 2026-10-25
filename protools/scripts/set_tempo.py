"""set_tempo.py BPM -> set the tempo at bar 1 (1|1|000) through the Tempo ruler's Tempo Change dialog.
PTSL has no tempo write, so this goes through Accessibility (ptax). Needs the Conductor on and the
insertion point at the session start. The dialog's BPM field ignores an AXValue write, so it is
focused and typed into with CGEventPostToPid (Pro Tools only, never the frontmost app).
Markers placed Absolute and sample-based audio do not move; tick-based tracks (Click) follow."""
import os, sys, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from ApplicationServices import AXUIElementSetAttributeValue
from Quartz import CGEventCreateKeyboardEvent, CGEventPostToPid, CGEventKeyboardSetUnicodeString

def text(pid, s):
    for ch in s:
        for down in (True, False):
            ev = CGEventCreateKeyboardEvent(None, 0, down)
            CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
            CGEventPostToPid(pid, ev)
        time.sleep(0.05)

def field(w, title):
    for el, d, _ in ptax.walk(w, max_depth=8):
        if ptax.attr(el, "AXRole") == "AXTextField" and ptax.attr(el, "AXTitle") == title:
            return el

bpm = sys.argv[1]
edit = ptax.window("Edit:")
for el, d, _ in ptax.walk(edit, max_depth=8):
    if ptax.attr(el, "AXRole") == "AXButton" and ptax.attr(el, "AXTitle") == "Add Tempo Change":
        ptax.press(el); break
else:
    sys.exit("no Add Tempo Change button (is the Tempo ruler shown?)")
time.sleep(1.5)
w = ptax.window("Tempo Change")
loc, bf = [el for el, d, _ in ptax.walk(w, max_depth=4) if ptax.attr(el, "AXRole") == "AXTextField"]
where = " ".join(str(ptax.attr(loc, "AXValue")).split())
if where != "1| 1| 000":
    ptax.press(ptax.find(w, "AXButton", "Cancel", max_depth=2))
    sys.exit(f"dialog opened at {where!r}, not bar 1; put the insertion point at the session start and retry")
AXUIElementSetAttributeValue(bf, "AXFocused", True); time.sleep(0.3)
text(ptax.pt_pid(), bpm); time.sleep(0.5)
typed = float(ptax.attr(bf, "AXValue"))
if abs(typed - float(bpm)) > 1e-3:
    ptax.press(ptax.find(w, "AXButton", "Cancel", max_depth=2))
    sys.exit(f"BPM field reads {typed}, cancelled")
ptax.press(ptax.find(w, "AXButton", "OK", max_depth=2)); time.sleep(1.5)
now = float(ptax.attr(field(ptax.window("Edit:"), "Tempo value"), "AXValue"))
print("TEMPO", now, "OK" if abs(now - float(bpm)) < 1e-3 else "CHECK")
