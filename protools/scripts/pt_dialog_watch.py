"""pt_dialog_watch.py: log (and screenshot, when Screen Recording is granted) every Pro Tools dialog,
and auto-answer the known blockers, during unattended work.

    .venv/bin/python scripts/pt_dialog_watch.py | tee -a pt_dialogs.log

Stops when /tmp/pt_dialog_watch.stop exists. Screenshots go to ~/pt-dialog-shots (or $PT_DIALOG_SHOTS).
Edit AUTO to change which dialogs are answered. macOS only; needs the Accessibility grant (see ptax.py).
demo_guard.py is the stricter sibling (plug-in demo prompts, missing plug-ins)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__); sys.exit(0)
import ptax
AUTO = {"Session Notes": "No",            # "Some inputs are missing" on open (interface not connected)
        "": "OK"}                          # untitled OK-only alerts (plug-in info notices and similar)
SHOT = os.environ.get("PT_DIALOG_SHOTS") or os.path.expanduser("~/pt-dialog-shots")
STOP = "/tmp/pt_dialog_watch.stop"
os.makedirs(SHOT, exist_ok=True)

def shot(tag):
    try:
        import Quartz
        from AppKit import NSBitmapImageRep, NSPNGFileType
        if not Quartz.CGPreflightScreenCaptureAccess():
            return "no Screen Recording permission"
        img = Quartz.CGWindowListCreateImage(Quartz.CGRectInfinite, Quartz.kCGWindowListOptionOnScreenOnly,
                                             Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
        p = f"{SHOT}/{time.strftime('%Y%m%d-%H%M%S')}-{tag}.png"
        NSBitmapImageRep.alloc().initWithCGImage_(img).representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(p, True)
        return p
    except Exception as ex:
        return f"shot failed {ex}"

seen = set()
while not os.path.exists(STOP):
    try:
        for w in ptax.children(ptax.app()):
            if ptax.attr(w, "AXSubrole") != "AXDialog":
                continue
            title = str(ptax.attr(w, "AXTitle") or "")
            texts, buttons = [], []
            for el, d, _ in ptax.walk(w, max_depth=6):
                r = ptax.attr(el, "AXRole")
                if r == "AXButton" and ptax.attr(el, "AXTitle"): buttons.append(str(ptax.attr(el, "AXTitle")))
                elif r == "AXStaticText" and ptax.attr(el, "AXValue"): texts.append(" ".join(str(ptax.attr(el, "AXValue")).split()))
            if not buttons and not texts: continue
            key = (title, tuple(texts[:4]), tuple(buttons))
            if key not in seen:
                seen.add(key)
                print(time.strftime("%H:%M:%S"), "DIALOG", repr(title), texts[:8], buttons, shot("dialog"), flush=True)
            want = AUTO.get(title)
            if want and want in buttons and (title or buttons == ["OK"]):
                for el, d, _ in ptax.walk(w, max_depth=8):
                    if ptax.attr(el, "AXRole") == "AXButton" and str(ptax.attr(el, "AXTitle")) == want:
                        ptax.press(el); print(time.strftime("%H:%M:%S"), "clicked", want, flush=True); break
    except Exception as ex:
        print("watch err", ex, flush=True)
    time.sleep(3)
