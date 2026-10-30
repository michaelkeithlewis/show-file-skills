"""Type into Pro Tools only (CGEventPostToPid), never the frontmost app.
ptkeys.py text "<string>" | key <keycode> [cmd] [shift]"""
import os, sys, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from Quartz import (CGEventCreateKeyboardEvent, CGEventPostToPid, CGEventKeyboardSetUnicodeString,
                    CGEventSetFlags, kCGEventFlagMaskCommand, kCGEventFlagMaskShift)
pid = ptax.pt_pid()
def key(code, flags=0):
    for down in (True, False):
        ev = CGEventCreateKeyboardEvent(None, code, down)
        if flags: CGEventSetFlags(ev, flags)
        CGEventPostToPid(pid, ev); time.sleep(0.03)
def text(s):
    for ch in s:
        for down in (True, False):
            ev = CGEventCreateKeyboardEvent(None, 0, down)
            CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
            CGEventPostToPid(pid, ev)
        time.sleep(0.02)
if sys.argv[1] == "text":
    text(sys.argv[2])
else:
    f = 0
    if "cmd" in sys.argv: f |= kCGEventFlagMaskCommand
    if "shift" in sys.argv: f |= kCGEventFlagMaskShift
    key(int(sys.argv[2]), f)
print("ok")
