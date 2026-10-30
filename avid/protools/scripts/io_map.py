"""io_map.py [ALL] : read every track's output and every aux/folder input from the Edit window (Accessibility, read-only).

Use it on a session someone else built (a producer session) before routing anything. route_folders.py --dry
lists every foldered track that is not on its folder bus, and that includes producer chains on purpose:
on one producer session the kick/snare/overhead tracks output to Bus 7-8, which the producer's drum aux takes in and
sends on to the DRUMS folder bus. Routing those would bypass the producer's bus. This prints each aux's input -> output and
flags only the tracks whose output NO aux or folder listens to (the real stragglers). ALL prints every track."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptax import window, track_groups, find, attr, out_label
from ptctl import engine
from ptsl import PTSL_pb2 as pt
def bare(l):
    l = l.split(" -> ")[0]
    return l.rsplit(" (", 1)[0] if l.endswith(")") else l
def lab(g, d):
    b = find(g, "AXPopUpButton", d)
    if b is None: return None
    s = " ".join(str(attr(b, "AXTitle") or attr(b, "AXValue") or "").split()).replace(d + " ", "")
    return bare(s.strip("\" "))
with engine() as e:
    tl = e.track_list()
    folders = [t.name for t in tl if "Folder" in pt.TrackType.Name(t.type)]
    e.client.run_command(pt.CommandId.CId_SetTrackOpenState, {"track_names": folders, "enabled": True})
    kinds = {t.name: pt.TrackType.Name(t.type) for t in tl}
    inact = {t.name for t in tl if pt.TrackAttributeState.Name(t.track_attributes.is_inactive).endswith(("Explicitly", "Implicitly"))}
g = track_groups(window("Edit:"))
ins, outs = {}, {}
for n, grp in g.items():
    outs[n] = bare(out_label(find(grp, "AXPopUpButton", "Audio Output Path selector")) or "")
    if kinds.get(n, "").startswith(("Aux", "RoutingFolder")):
        ins[n] = lab(grp, "Audio Input Path selector")
listen = {}
for n, i in ins.items():
    listen.setdefault(i, []).append(n)
OK = ("PrMst", "PtMst", "MON L/R", "External Headphones 1-2", "no output")
for n in g:
    o, k = outs[n], kinds.get(n, "?")
    if k != "AudioTrack" and not k.startswith("Aux"):
        continue
    tag = "" if (o in listen or o in OK or o.startswith(("Out", "MON"))) else "   <-- NOBODY LISTENS"
    if k.startswith("Aux") or tag or "ALL" in sys.argv:
        print(f"{k[:5]} {n!r:34} in={ins.get(n)!r:24} out={o!r}{' INACTIVE' if n in inact else ''}{tag}")
print("not exposed:", [t.name for t in tl if t.name not in g and kinds[t.name] == "AudioTrack"])
print("listeners:", {k: v for k, v in listen.items()})
