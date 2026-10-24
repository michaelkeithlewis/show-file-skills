"""Navigate PT's Open panel by Accessibility only.
opennav.py "<sidebar item>" "<folder>" ... "<file>"   -> selects each and presses Open."""
import os, sys, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from ApplicationServices import AXUIElementSetAttributeValue, AXUIElementPerformAction

def panel():
    for w in ptax.children(ptax.app()):
        if ptax.attr(w, "AXRole") == "AXWindow" and ptax.attr(w, "AXTitle") == "Open":
            return w
    sys.exit("no Open panel")

def outline(desc):
    for el, d, _ in ptax.walk(panel(), max_depth=6):
        if ptax.attr(el, "AXRole") == "AXOutline" and ptax.attr(el, "AXDescription") == desc:
            return el

def row_named(ol, name):
    for r in ptax.children(ol):
        if ptax.attr(r, "AXRole") != "AXRow": continue
        for el, d, _ in ptax.walk(r, max_depth=3):
            if ptax.attr(el, "AXRole") in ("AXTextField", "AXStaticText") and str(ptax.attr(el, "AXValue") or "") == name:
                return r
    return None

def select(ol, name, tries=20):
    for _ in range(tries):
        r = row_named(ol(), name) if callable(ol) else row_named(ol, name)
        if r is not None:
            target = ol() if callable(ol) else ol
            err = AXUIElementSetAttributeValue(target, "AXSelectedRows", [r])
            return err
        time.sleep(0.5)
    sys.exit(f"row {name!r} not found")

def press_open():
    for el, d, _ in ptax.walk(panel(), max_depth=4):
        if ptax.attr(el, "AXRole") == "AXButton" and ptax.attr(el, "AXTitle") == "Open":
            AXUIElementPerformAction(el, "AXPress"); return
    sys.exit("no Open button")

side, *rest = sys.argv[1:]
print("sidebar", side, select(outline("sidebar"), side)); time.sleep(1.5)
for name in rest:
    print("select", name, select(lambda: outline("list view"), name)); time.sleep(0.4)
    press_open(); time.sleep(1.5)
print("done")
