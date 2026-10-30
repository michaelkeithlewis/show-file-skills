"""strips.py TRACK... -> inserts, sends, output, volume per Mix-window strip"""
import os, sys, re; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from ptax import attr, walk
w = ptax.window("Mix:")
groups = ptax.track_groups(w)
for name in sys.argv[1:]:
    g = groups.get(name)
    if g is None: print(name, "NOT IN MIX WINDOW"); continue
    ins, snd, out, vol = [], [], None, None
    for el, d, _ in walk(g, max_depth=3):
        t = str(attr(el, "AXTitle") or ""); v = attr(el, "AXValue")
        if t.startswith("Insert Assignment") and v and v != "unassigned": ins.append(f"{t[-1]}:{v}")
        elif t.startswith("Send Assignment") and v and v != "unassigned": snd.append(f"{t[-1]}:{v}")
        elif t.startswith("Send selector") and v: snd.append(f"{t[-1]}({v})")
        elif t.startswith("Audio Output Path selector"): out = v
        elif t == "Volume" and vol is None: vol = v
    print(f"{name}: out={out} vol={vol} | inserts {ins} | sends {snd}")
