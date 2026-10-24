"""trackdata.py all | only "<checkbox title>"...  -> set the Track Data to Import dialog, then OK"""
import os, sys, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from ptax import attr, children, walk, press
w = next(x for x in children(ptax.app()) if attr(x, "AXTitle") == "Track Data to Import")
want = None if sys.argv[1] == "all" else set(sys.argv[2:])
for el, d, _ in walk(w, max_depth=3):
    if attr(el, "AXRole") != "AXCheckBox": continue
    t = str(attr(el, "AXTitle")); on = attr(el, "AXValue") == 1
    should = True if want is None else (t in want)
    if t.startswith("ICON"): should = False if want is not None else on
    if on != should: press(el); time.sleep(0.05)
time.sleep(0.3)
print("ON:", [str(attr(el, "AXTitle")) for el, d, _ in walk(w, max_depth=3) if attr(el, "AXRole") == "AXCheckBox" and attr(el, "AXValue") == 1])
