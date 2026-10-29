"""mixgroups.py off F | on F | list: switch the session's ACTIVE mix groups off (names saved to F) so each fader
can be typed on its own, then switch exactly those back on. Producer sessions group a vocal with its printed
verb ("LV 1" = LV + LV verb): typing one fader moves the other, so premix faders land wrong."""
import json, sys, time
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import ptax
def rows():
    w = ptax.window("Mix:")
    tab = next(el for el, d, _ in ptax.walk(w, max_depth=2) if ptax.attr(el, "AXTitle") == "Group List")
    out = []
    for row in ptax.children(tab):
        if ptax.attr(row, "AXRole") != "AXRow": continue
        for el, d, _ in ptax.walk(row, max_depth=3):
            t = str(ptax.attr(el, "AXTitle") or "")
            if ptax.attr(el, "AXRole") == "AXButton" and " - " in t and not t.startswith(("Selected", "Track selection")):
                out.append((t, el))
    return out
cmd = sys.argv[1]
if cmd == "list":
    print([t for t, _ in rows()])
elif cmd == "off":
    act = [t.split(" ", 1)[1] for t, _ in rows() if t.startswith("Active ")]
    json.dump(act, open(sys.argv[2], "w"))
    for name in act:
        el = next(el for t, el in rows() if t == "Active " + name); ptax.press(el); time.sleep(0.4)
    print("groups off:", act, "| now:", [t for t, _ in rows()])
elif cmd == "on":
    want = json.load(open(sys.argv[2]))
    for name in want:
        el = next((el for t, el in rows() if t.endswith(name) and not t.startswith("Active ")), None)
        if el is not None: ptax.press(el); time.sleep(0.4)
    still = [t for t, _ in rows() if not t.startswith("Active ") and t.split(" ", 1)[-1] in want]
    print("groups on:", want, "| still off:", still)
