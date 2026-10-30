"""fader_readback.py F.json: read every stem + folder fader from the Mix window and list the ones that differ from F."""
import json, sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import ptax
d = json.load(open(sys.argv[1])); want = dict(d["faders"]); want.update(d.get("folder_faders", {}))
g = ptax.track_groups(ptax.window("Mix:")); bad = {}
for x, v in want.items():
    s = g.get(x)
    vol = [ptax.attr(el, "AXValue") for el, dd, _ in ptax.walk(s, max_depth=2)
           if ptax.attr(el, "AXTitle") == "Volume" and ptax.attr(el, "AXRole") == "AXSlider"] if s is not None else []
    got = int(vol[0]) / 10.0 if vol and vol[0] is not None else None
    if got is None or abs(got - v) > 0.06: bad[x] = (v, got)
print("READBACK", len(want), "faders, off:", bad)
