#!/usr/bin/env python3
"""ptax.py: drive the Pro Tools GUI through the macOS Accessibility API.

The SoundFlow approach: find controls by role and description, press them, and
pick menu items by name. No mouse movement, no screen coordinates.

macOS only. Needs pyobjc (pyobjc-framework-ApplicationServices and
pyobjc-framework-Quartz) and Accessibility permission for the process that runs
Python: add your terminal app (Terminal, iTerm, or the app that hosts Claude
Code) under System Settings > Privacy & Security > Accessibility. Check with:

    .venv/bin/python scripts/ptax.py trusted      # must print True
    .venv/bin/python scripts/ptax.py outputs      # every track's main output
"""
import sys, time, argparse, subprocess
try:
    from ApplicationServices import (
        AXUIElementCreateApplication, AXUIElementCopyAttributeValue,
        AXUIElementPerformAction, AXIsProcessTrusted,
    )
except ImportError:  # not macOS, or pyobjc missing: --help still works
    def _missing(*_a, **_k):
        sys.exit("ptax.py needs macOS and pyobjc: pip install pyobjc-framework-ApplicationServices pyobjc-framework-Quartz")
    AXUIElementCreateApplication = AXUIElementCopyAttributeValue = _missing
    AXUIElementPerformAction = AXIsProcessTrusted = _missing

ATTRS = ["AXRole", "AXSubrole", "AXTitle", "AXDescription", "AXValue", "AXHelp"]


def pt_pid():
    out = subprocess.run(["pgrep", "-x", "Pro Tools"], capture_output=True, text=True).stdout.split()
    if not out:
        sys.exit("Pro Tools is not running")
    return int(out[0])


def attr(el, name):
    err, val = AXUIElementCopyAttributeValue(el, name, None)
    return val if err == 0 else None


def children(el):
    return attr(el, "AXChildren") or []


def label(el):
    parts = []
    for a in ATTRS:
        v = attr(el, a)
        if v not in (None, ""):
            s = str(v).replace("\n", " ")
            parts.append(f"{a[2:]}={s[:60]}")
    return " | ".join(parts)


def app():
    return AXUIElementCreateApplication(pt_pid())


def window(prefix):
    for w in children(app()):
        if attr(w, "AXRole") == "AXWindow" and str(attr(w, "AXTitle") or "").startswith(prefix):
            return w
    sys.exit(f"no window starting with {prefix!r}")


def walk(el, depth=0, max_depth=99, path=()):
    yield el, depth, path
    if depth < max_depth:
        for i, c in enumerate(children(el)):
            yield from walk(c, depth + 1, max_depth, path + (i,))


def press(el):
    return AXUIElementPerformAction(el, "AXPress")


def menu_items(menu):
    return [(str(attr(m, "AXTitle") or ""), m) for m in children(menu)]


def track_groups(w):
    """{track name: AXGroup} for every track header the Edit/Mix window exposes."""
    import re
    out = {}
    for el, d, _ in walk(w, max_depth=3):
        if attr(el, "AXRole") != "AXGroup":
            continue
        m = re.match(r"^\d+ (.+) - .*Track\s*$", str(attr(el, "AXTitle") or ""))
        if m:
            out.setdefault(m.group(1), el)
    return out


def find(el, role=None, prefix=None, max_depth=4):
    for c, d, _ in walk(el, max_depth=max_depth):
        if role and attr(c, "AXRole") != role:
            continue
        if prefix and not str(attr(c, "AXTitle") or attr(c, "AXDescription") or "").startswith(prefix):
            continue
        return c
    return None


def open_menu(button, wait=0.4):
    press(button)
    time.sleep(wait)
    for c, d, _ in walk(button, max_depth=2):
        if attr(c, "AXRole") == "AXMenu":
            return c
    for c, d, _ in walk(app(), max_depth=2):
        if attr(c, "AXRole") == "AXMenu":
            return c
    return None


def dump_menu(menu, depth=0, max_depth=1):
    for title, m in menu_items(menu):
        print("  " * depth + f"- {title!r} enabled={attr(m, 'AXEnabled')}")
        if depth < max_depth:
            for sub in children(m):
                if attr(sub, "AXRole") == "AXMenu":
                    dump_menu(sub, depth + 1, max_depth)


def cmd_outmenu(a):
    w = window(a.window)
    g = track_groups(w).get(a.track)
    if g is None:
        sys.exit(f"track {a.track!r} not exposed (scroll it into view)")
    btn = find(g, "AXPopUpButton", "Audio Output Path selector")
    print("current:", attr(btn, "AXValue"))
    menu = open_menu(btn)
    if menu is None:
        sys.exit("no AXMenu appeared")
    dump_menu(menu, max_depth=a.depth)
    AXUIElementPerformAction(menu, "AXCancel")


def popup_dialog():
    """Pro Tools draws pop-up menus as AXDialog windows holding AXMenuItems."""
    for c in children(app()):
        if attr(c, "AXSubrole") == "AXDialog" and any(
                attr(m, "AXRole") == "AXMenuItem" for m in children(c)):
            return c
    return None


def item(menu, title=None, prefix=None):
    for m in children(menu):
        if attr(m, "AXRole") != "AXMenuItem":
            continue
        t = str(attr(m, "AXTitle") or "")
        if (title is not None and t.strip() == title) or (prefix is not None and t.startswith(prefix)):
            return m
    return None


def submenu(menu_item):
    for c in children(menu_item):
        if attr(c, "AXRole") == "AXWindow":
            return c
    return None


def close_popup():
    d = popup_dialog()
    if d is not None:
        # Escape to Pro Tools only; a global keystroke lands in whatever app is in front
        from Quartz import CGEventCreateKeyboardEvent, CGEventPostToPid
        for down in (True, False):
            CGEventPostToPid(pt_pid(), CGEventCreateKeyboardEvent(None, 53, down))
        time.sleep(0.2)


def out_label(btn):
    return " ".join(str(attr(btn, "AXTitle") or "").split()).replace("Audio Output Path selector ", "")


def route_track(groups, track, bus):
    """Set one track's main output to `bus` through its output selector."""
    g = groups.get(track)
    if g is None:
        return f"{track}: not exposed (scroll it into view)"
    btn = find(g, "AXPopUpButton", "Audio Output Path selector")
    if btn is None:
        return f"{track}: no output selector"
    close_popup()
    press(btn)
    for _ in range(20):
        d = popup_dialog()
        if d is not None:
            break
        time.sleep(0.05)
    else:
        return f"{track}: menu did not open"
    bus_menu = submenu(item(d, title="bus") or d)
    target = bus_menu is not None and item(bus_menu, prefix=bus + " (")
    if not target:
        close_popup()
        return f"{track}: no bus named {bus!r}"
    press(target)
    time.sleep(0.3)
    got = out_label(btn)
    ok = got.startswith(f"{bus} (")
    return f"{track}: {'OK' if ok else 'CHECK'} -> {got}"


def cmd_route(a):
    w = window(a.window)
    groups = track_groups(w)
    for t in a.tracks:
        print(route_track(groups, t, a.bus), flush=True)


def cmd_outputs(a):
    w = window(a.window)
    for name, g in track_groups(w).items():
        btn = find(g, "AXPopUpButton", "Audio Output Path selector")
        if btn is not None:
            print(f"{name:30} {out_label(btn)}")


def cmd_trackmenu(a):
    """Press an item in one of a track's pop-up menus, e.g. Track options > Show Automation Lanes."""
    g = track_groups(window(a.window)).get(a.track)
    if g is None:
        sys.exit(f"track {a.track!r} not exposed (scroll it into view)")
    btn = find(g, "AXPopUpButton", a.button)
    if btn is None:
        sys.exit(f"no {a.button!r} button on {a.track!r}")
    close_popup()
    press(btn)
    for _ in range(20):
        d = popup_dialog()
        if d is not None:
            break
        time.sleep(0.05)
    else:
        sys.exit("menu did not open")
    menu = d
    for step in a.path[:-1]:
        menu = submenu(item(menu, title=step))
        if menu is None:
            close_popup()
            sys.exit(f"no submenu {step!r}")
    target = item(menu, title=a.path[-1])
    if target is None:
        close_popup()
        sys.exit(f"no item {a.path[-1]!r}")
    press(target)
    print(f"{a.track}: pressed {' > '.join([a.button] + a.path)}")


def cmd_windows(a):
    for w in children(app()):
        if attr(w, "AXRole") != "AXWindow":
            continue
        title = str(attr(w, "AXTitle") or "")
        if title.startswith(("Edit:", "Mix:")):
            continue
        texts, buttons = [], []
        for el, d, _ in walk(w, max_depth=6):
            r = attr(el, "AXRole")
            if r == "AXButton" and attr(el, "AXTitle"):
                buttons.append(str(attr(el, "AXTitle")))
            elif r == "AXStaticText" and attr(el, "AXValue"):
                texts.append(" ".join(str(attr(el, "AXValue")).split())[:120])
        print(f"WINDOW {title!r} subrole={attr(w, 'AXSubrole')}")
        for t in texts[:12]:
            print(f"   text: {t}")
        print(f"   buttons: {buttons}")


def cmd_click(a):
    for w in children(app()):
        if attr(w, "AXRole") != "AXWindow":
            continue
        if a.window and not str(attr(w, "AXTitle") or "").startswith(a.window):
            continue
        for el, d, _ in walk(w, max_depth=8):
            if attr(el, "AXRole") == "AXButton" and str(attr(el, "AXTitle") or "") == a.button:
                press(el)
                print(f"pressed {a.button!r} in {attr(w, 'AXTitle')!r}")
                return
    sys.exit(f"no button {a.button!r}")


def cmd_menu(a):
    bar = next(c for c in children(app()) if attr(c, "AXRole") == "AXMenuBar")
    node = bar
    for i, step in enumerate(a.path):
        found = None
        for c in children(node):
            if str(attr(c, "AXTitle") or "").rstrip(".…") == step.rstrip(".…"):
                found = c
                break
        if found is None:
            sys.exit(f"no menu item {step!r}")
        if i == len(a.path) - 1:
            press(found)
            print("pressed", " > ".join(a.path))
            return
        kids = children(found)
        node = kids[0] if kids and attr(kids[0], "AXRole") == "AXMenu" else found


def keys(script):
    subprocess.run(["osascript", "-e", f'tell application "System Events" to {script}'], check=True)


def cmd_dump(a):
    w = window(a.window)
    t0 = time.time()
    n = 0
    for el, d, _ in walk(w, max_depth=a.depth):
        n += 1
        print("  " * d + label(el))
    print(f"# {n} elements in {time.time() - t0:.1f}s", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(prog="ptax", description="Drive the Pro Tools GUI through the macOS Accessibility API")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="print the AX tree of a window")
    d.add_argument("--window", default="Edit:")
    d.add_argument("--depth", type=int, default=4)
    sub.add_parser("trusted", help="print True if this process has Accessibility permission")
    o = sub.add_parser("outmenu", help="print one track's output menu")
    o.add_argument("track")
    o.add_argument("--window", default="Edit:")
    o.add_argument("--depth", type=int, default=1)
    r = sub.add_parser("route", help="route tracks to a bus: route BUS TRACK...")
    r.add_argument("bus")
    r.add_argument("tracks", nargs="+")
    r.add_argument("--window", default="Edit:")
    ou = sub.add_parser("outputs", help="print every exposed track's main output")
    ou.add_argument("--window", default="Edit:")
    tm = sub.add_parser("trackmenu", help="trackmenu TRACK BUTTON ITEM [ITEM...]")
    tm.add_argument("track")
    tm.add_argument("button")
    tm.add_argument("path", nargs="+")
    tm.add_argument("--window", default="Edit:")
    sub.add_parser("windows", help="list open dialogs with their text and buttons")
    cl = sub.add_parser("click", help="press a button by title")
    cl.add_argument("button")
    cl.add_argument("--window", default="")
    mn = sub.add_parser("menu", help="press a menu bar item: menu Track New...")
    mn.add_argument("path", nargs="+")
    a = ap.parse_args()
    if a.cmd == "trusted":
        print(AXIsProcessTrusted())
    elif a.cmd == "outmenu":
        cmd_outmenu(a)
    elif a.cmd == "route":
        cmd_route(a)
    elif a.cmd == "outputs":
        cmd_outputs(a)
    elif a.cmd == "trackmenu":
        cmd_trackmenu(a)
    elif a.cmd == "windows":
        cmd_windows(a)
    elif a.cmd == "click":
        cmd_click(a)
    elif a.cmd == "menu":
        cmd_menu(a)
    elif a.cmd == "dump":
        cmd_dump(a)


if __name__ == "__main__":
    main()
