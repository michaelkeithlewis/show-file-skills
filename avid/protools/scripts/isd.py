"""Drive Pro Tools' Import Session Data dialog by Accessibility.
isd.py menu "<source track>"            -> list destination choices
isd.py set "<source track>" "<dest>"    -> pick a destination
isd.py dests                            -> show every row's destination"""
import os, sys, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptax
from ptax import attr, children, walk, press
from ApplicationServices import AXUIElementPerformAction

def dialog():
    for w in children(ptax.app()):
        if attr(w, "AXRole") == "AXWindow" and attr(w, "AXTitle") == "Import Session Data":
            return w
    sys.exit("no Import Session Data dialog")

def rows():
    for el, d, _ in walk(dialog(), max_depth=2):
        if attr(el, "AXRole") == "AXTable" and attr(el, "AXTitle") == "Source Destination":
            out = []
            for r in children(el):
                if attr(r, "AXRole") != "AXRow": continue
                cells = children(r)
                src = attr(children(cells[0])[0], "AXValue")
                btn = children(cells[1])[0]
                out.append((str(src).rsplit(" (", 1)[0], btn))
            return out
    sys.exit("no source table")

def btn_for(src):
    for s, b in rows():
        if s == src: return b
    sys.exit(f"no source row {src!r}")

def open_dest_menu(b):
    press(b); time.sleep(0.5)
    m = ptax.popup_dialog()
    if m is None:
        for c, d, _ in walk(b, max_depth=2):
            if attr(c, "AXRole") == "AXMenu": return c
    return m

def items(m):
    return [(str(attr(i, "AXTitle") or ""), i) for i in children(m) if attr(i, "AXRole") == "AXMenuItem"]

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "dests":
        for s, b in rows(): print(f"{s:32} -> {attr(b, 'AXValue')}")
    elif cmd == "menu":
        m = open_dest_menu(btn_for(sys.argv[2]))
        print("menu role", attr(m, "AXRole") if m is not None else None)
        for t, i in items(m) if m is not None else []: print(" -", repr(t))
        ptax.close_popup()
        if m is not None and attr(m, "AXRole") == "AXMenu": AXUIElementPerformAction(m, "AXCancel")
    elif cmd == "set":
        src, dest = sys.argv[2], sys.argv[3]
        b = btn_for(src); m = open_dest_menu(b)
        hit = [i for t, i in items(m) if t.strip() == dest or (t.split(" ", 1)[0].isdigit() and t.split(" ", 1)[1] == dest)]
        if not hit:
            ptax.close_popup(); sys.exit(f"{src}: no item {dest!r} in {[t for t, _ in items(m)]}")
        press(hit[0]); time.sleep(0.4)
        print(f"{src} -> {attr(btn_for(src), 'AXValue')}")
