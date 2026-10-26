"""ptgui.py: Pro Tools GUI helpers over Accessibility + PID-targeted keystrokes (no mouse, never the frontmost app).
Never run these while the engineer is working in Pro Tools: a keystroke lands on whatever is selected."""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from ptsl import PTSL_pb2 as pt
from ApplicationServices import AXUIElementPerformAction, AXUIElementSetAttributeValue
from Quartz import (CGEventCreateKeyboardEvent, CGEventPostToPid, CGEventKeyboardSetUnicodeString, CGEventSetFlags,
                    kCGEventFlagMaskControl, kCGEventFlagMaskShift)

LAST = "/tmp/ptgui_lastkey"
def hid_idle():
    """Seconds since the last keyboard/mouse input on the Mac (HIDIdleTime). Our own CGEventPostToPid
    keystrokes reset it too (verified 2026-10-26: a posted Shift took it from 90 s to 1 s)."""
    import subprocess
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True).stdout
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) / 1e9 if m else 0.0
def _mark():
    open(LAST, "w").write(str(time.time()))
def since_my_last_key():
    try: return time.time() - float(open(LAST).read())
    except Exception: return float("inf")
def user_idle_secs():
    """Seconds since the last input that was NOT one of our keystrokes (inf when the newest input is ours)."""
    hid, mine = hid_idle(), since_my_last_key()
    return float("inf") if abs(hid - mine) < 2.0 else hid
RUN_START = [time.time()]
def guard_start():
    """Call once the idle check passes; user_touched() then watches for input after this moment."""
    RUN_START[0] = time.time()
def user_touched():
    """True if someone typed or moved the mouse after the run started and after our last keystroke."""
    return hid_idle() + 2.0 < min(since_my_last_key(), time.time() - RUN_START[0])

PID = ptax.pt_pid()
def text(s):
    _mark()
    for ch in s:
        for d in (True, False):
            ev = CGEventCreateKeyboardEvent(None, 0, d); CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
            CGEventPostToPid(PID, ev)
        time.sleep(0.04)
    _mark()
def key(code, flags=0):
    for d in (True, False):
        ev = CGEventCreateKeyboardEvent(None, code, d)
        if flags: CGEventSetFlags(ev, flags)
        CGEventPostToPid(PID, ev); time.sleep(0.03)
    _mark()
def close_floating():
    for w in ptax.children(ptax.app()):
        if ptax.attr(w, "AXSubrole") == "AXFloatingWindow":
            for el, d, _ in ptax.walk(w, max_depth=1):
                if ptax.attr(el, "AXSubrole") == "AXCloseButton": ptax.press(el)
def strip(track):
    return ptax.track_groups(ptax.window("Mix:")).get(track)
def set_pan(track, value):
    """Type a pan (-100..100) into the track's Output window; returns what the field reads back."""
    close_floating()
    ptax.press(ptax.find(strip(track), "AXButton", "Output Window button", max_depth=2)); time.sleep(1.2)
    w = next(w for w in ptax.children(ptax.app()) if ptax.attr(w, "AXSubrole") == "AXFloatingWindow")
    field = lambda: next(el for el, d, _ in ptax.walk(w, max_depth=2) if ptax.attr(el, "AXTitle") == "Front Pan Numerical")
    ptax.press(field()); time.sleep(0.3); text(str(value)); key(36); time.sleep(0.5)
    got = ptax.attr(field(), "AXValue"); close_floating()
    return got
def nudge_clip_gain(e, track, steps):
    """Clip gain by keystroke: Ctrl+Shift+Up/Down = one Clip Gain Nudge (0.5 dB here; verified by bounce 2026-10-25)."""
    if not steps: return
    close_floating()
    ew = ptax.window("Edit:"); AXUIElementPerformAction(ew, "AXRaise"); AXUIElementSetAttributeValue(ew, "AXMain", True)
    time.sleep(0.3)
    e.client.run_command(pt.CId_SelectAllClipsOnTrack, {"track_name": track}); time.sleep(0.2)
    for _ in range(abs(steps)):
        key(126 if steps > 0 else 125, kCGEventFlagMaskControl | kCGEventFlagMaskShift); time.sleep(0.06)
    time.sleep(0.3)
def posix(p): return "/" + p.split(":", 1)[1].replace(":", "/") if ":" in p and not p.startswith("/") else p
def paged(e, cid, body, k):
    out, off = [], 0
    while True:
        p = e.client.run_command(cid, {**body, "pagination_request": {"limit": 500, "offset": off}}).get(k, [])
        out += p
        if len(p) < 500: return out
        off += 500
def edl(e):
    t = e.client.run_command(pt.CId_ExportSessionInfoAsText, {"include_track_edls": True, "include_file_list": False,
                                                              "output_type": "ESI_String"}).get("session_info", "")
    out = {}
    for b in re.split(r"\nTRACK NAME:\t", t)[1:]:
        out[re.sub(r" \((Stereo|Mono)\)$", "", b.split("\n")[0].strip())] = sorted(
            [x.strip() for x in l.split("\t")] for l in b.split("\n") if re.match(r"^\d+\s*\t\s*\d+\s*\t", l))
    return out
