"""relink_dialog.py : on Pro Tools' 'Missing Files' dialog choose 'Automatically Find & Relink' and press OK."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 1):
    w = next((w for w in ptax.children(ptax.app()) if str(ptax.attr(w, "AXTitle") or "") == "Missing Files"), None)
    if w is not None: break
    time.sleep(1)
else:
    sys.exit("NO DIALOG")
el = lambda role, title: next((e for e, d, _ in ptax.walk(w, max_depth=3) if ptax.attr(e, "AXRole") == role and ptax.attr(e, "AXTitle") == title), None)
txt = next((ptax.attr(e, "AXValue") for e, d, _ in ptax.walk(w, max_depth=3) if ptax.attr(e, "AXRole") == "AXStaticText" and "missing" in str(ptax.attr(e, "AXValue"))), "")
rb = el("AXRadioButton", "Automatically Find & Relink"); ptax.press(rb); time.sleep(0.3)
print("selected:", ptax.attr(rb, "AXValue"), "|", txt)
ptax.press(el("AXButton", "OK")); print("OK pressed")
