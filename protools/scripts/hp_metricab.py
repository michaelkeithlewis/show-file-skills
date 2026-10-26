"""hp_metricab.py: per-song finish on an open session (Mix window showing the master bus strip).
  1. Headphones off the master bus: send B -> your headphone output, PRE, 0 dB; the bus's main output -> no output.
     Use this when the template's master bus feeds only the headphones and the print/bounce comes off a bus above it.
  2. ADPTR Metric AB on that bus: load a Librarian preset (made with metricab_ref.py) so the reference plays in sync.

    hp_metricab.py [PRESET] [--track "MASTER BUS"] [--hp "External Headphones 1-2"] [--insert G]

Omit PRESET to skip Metric AB. Idempotent: settings that are already right are left alone.
macOS only; needs the Accessibility grant (see ptax.py). Never run it while the engineer is working in Pro Tools."""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__); sys.exit(0)
import ptax

def popup():
    for _ in range(40):
        d = ptax.popup_dialog()
        if d is not None: return d
        time.sleep(0.05)
    raise SystemExit("popup did not open")

def strip(track):
    return ptax.track_groups(ptax.window("Mix:"))[track]

def headphones(track, hp):
    m = strip(track)
    sb = ptax.find(m, "AXButton", "Send Assignment B", max_depth=4)
    if ptax.attr(sb, "AXValue") != hp:
        ptax.close_popup(); ptax.press(sb)
        sm = ptax.submenu(ptax.item(popup(), title="output"))
        ptax.press(ptax.item(sm, prefix=hp)); time.sleep(1)
    sel = ptax.find(strip(track), "AXButton", "Send selector B", max_depth=4)
    if "pre" not in str(ptax.attr(sel, "AXValue")):
        fw = next((x for x in ptax.children(ptax.app()) if ptax.attr(x, "AXSubrole") == "AXFloatingWindow"
                   and ptax.find(x, "AXButton", "Output View selector", max_depth=2) is not None), None)
        if fw is None:  # open the send window
            ptax.press(sel); time.sleep(1)
            fw = next(x for x in ptax.children(ptax.app()) if ptax.attr(x, "AXSubrole") == "AXFloatingWindow")
        ptax.press(ptax.find(fw, "AXButton", "Pre/Post fader", max_depth=2)); time.sleep(0.5)
    out = ptax.find(strip(track), "AXPopUpButton", "Audio Output Path selector")
    if ptax.attr(out, "AXValue") != "no output":
        ptax.close_popup(); ptax.press(out)
        ptax.press(ptax.item(popup(), title="no output")); time.sleep(0.5)
    m = strip(track)
    r = (ptax.attr(ptax.find(m, "AXButton", "Send Assignment B", max_depth=4), "AXValue"),
         ptax.attr(ptax.find(m, "AXButton", "Send selector B", max_depth=4), "AXValue"),
         ptax.attr(ptax.find(m, "AXPopUpButton", "Audio Output Path selector"), "AXValue"))
    print("HEADPHONES", r, flush=True)
    return r[0] == hp and str(r[1]).startswith("pre is active") and r[2] == "no output"

def metricab(track, preset, slot):
    g = ptax.find(strip(track), "AXButton", f"Insert Assignment {slot}", max_depth=4)
    if ptax.attr(g, "AXValue") != "ADPTR MetricAB":
        raise SystemExit(f"insert {slot} on {track} is {ptax.attr(g, 'AXValue')!r}, not ADPTR MetricAB")
    ptax.press(g); time.sleep(3)
    pw = ptax.window("Plug-in: ADPTR")
    lib = ptax.find(pw, "AXPopUpButton", "Librarian menu", max_depth=2)
    ptax.press(lib); time.sleep(1)
    hit = None
    for el, d, _ in ptax.walk(ptax.app(), max_depth=5):
        if ptax.attr(el, "AXRole") == "AXMenuItem" and ptax.attr(el, "AXTitle") == preset:
            hit = el; break
    if hit is None:
        raise SystemExit(f"preset {preset!r} not in Librarian")
    ptax.press(hit); time.sleep(3)
    v = ptax.attr(ptax.find(ptax.window("Plug-in: ADPTR"), "AXPopUpButton", "Librarian menu", max_depth=2), "AXValue")
    print("METRICAB", v, flush=True)
    for x in ptax.children(ptax.app()):  # close plug-in + send windows
        if ptax.attr(x, "AXSubrole") == "AXFloatingWindow":
            for el, d, _ in ptax.walk(x, max_depth=1):
                if ptax.attr(el, "AXSubrole") == "AXCloseButton": ptax.press(el)
    return v == preset

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("preset", nargs="?")
    ap.add_argument("--track", default="MASTER BUS")
    ap.add_argument("--hp", default="External Headphones 1-2", help="output name the headphone send goes to")
    ap.add_argument("--insert", default="G", help="insert slot letter that holds Metric AB")
    a = ap.parse_args()
    ok = headphones(a.track, a.hp)
    if a.preset: ok = metricab(a.track, a.preset, a.insert) and ok
    print("HP_METRICAB", "OK" if ok else "CHECK", flush=True)
