"""route_out.py OUTPUT TRACK... : set a track's main output to a physical OUTPUT path (ptax route only does buses)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
target, tracks = sys.argv[1], sys.argv[2:]
groups = ptax.track_groups(ptax.window("Edit:"))
for t in tracks:
    g = groups.get(t); btn = g and ptax.find(g, "AXPopUpButton", "Audio Output Path selector")
    if not btn: print(t, "not exposed"); continue
    ptax.close_popup(); ptax.press(btn)
    for _ in range(20):
        d = ptax.popup_dialog()
        if d is not None: break
        time.sleep(0.05)
    else: print(t, "menu did not open"); continue
    tops = [str(ptax.attr(m, "AXTitle") or "") for m in ptax.children(d) if ptax.attr(m, "AXRole") == "AXMenuItem"]
    sub = ptax.submenu(ptax.item(d, title="output") or d)
    it = sub is not None and ptax.item(sub, prefix=target)
    if not it:
        names = [str(ptax.attr(m, "AXTitle") or "") for m in ptax.children(sub)] if sub is not None else []
        ptax.close_popup(); print(t, "no output", repr(target), "top:", tops, "output menu:", names[:20]); continue
    ptax.press(it); time.sleep(0.3)
    print(t, "->", ptax.out_label(btn))
