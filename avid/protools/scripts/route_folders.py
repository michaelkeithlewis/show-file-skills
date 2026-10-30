#!/usr/bin/env python3
"""route_folders.py: route every audio track in a routing folder to that folder's bus.

PTSL-created tracks output to the session's main bus, not their folder, and PTSL
cannot set outputs without the Private API. This does it through the macOS
Accessibility API instead (ptax.py): the bus is whatever the folder's own Audio
Input selector shows (a folder called DRUM GROUP may own a bus called DRUMS, so
never assume bus = folder name). Tracks already on their folder bus are left
alone; so are aux tracks, which the template routes itself.

Every track must be visible in the Edit window (Pro Tools only exposes controls
for tracks it has drawn). The script opens every routing folder first.

    route_folders.py [--dry]       # route, then re-read every output and report
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__); sys.exit(0)
from ptax import window, track_groups, find, attr, out_label, route_track
from ptctl import engine
from ptsl import PTSL_pb2 as pt


def bare(label):
    """'DRUMS (Stereo)' -> 'DRUMS'"""
    return label.rsplit(" (", 1)[0] if label.endswith(")") else label


def folder_bus(g):
    btn = find(g, "AXPopUpButton", "Audio Input Path selector")
    s = " ".join(str(attr(btn, "AXTitle") or "").split()).replace("Audio Input Path selector ", "")
    return bare(s.strip("\" "))


def main(dry):
    with engine() as e:
        tl = e.track_list()
        kind = lambda t: pt.TrackType.Name(t.type)
        folders = [t.name for t in tl if "RoutingFolder" in kind(t)]
        e.client.run_command(pt.CommandId.CId_SetTrackOpenState, {"track_names": folders, "enabled": True})
        want = [(t.name, t.parent_folder_name) for t in tl
                if "AudioTrack" in kind(t) and t.parent_folder_name in folders]
    time.sleep(1)
    g = track_groups(window("Edit:"))
    buses = {f: folder_bus(g[f]) for f in folders if f in g}
    todo, bad = [], 0
    for t, f in want:
        if t not in g:
            print(f"{t}: not exposed in the Edit window (scroll it into view)"); bad += 1; continue
        cur = bare(out_label(find(g[t], "AXPopUpButton", "Audio Output Path selector")))
        if cur != buses.get(f):
            todo.append((t, f, cur))
    print(f"{len(want)} foldered audio tracks, {len(todo)} to route", flush=True)
    for t, f, cur in todo:
        if dry:
            print(f"  {t}: {cur} -> {buses[f]}"); continue
        r = route_track(g, t, buses[f]); print(" ", r, flush=True)
        if "OK" not in r:
            bad += 1
    if dry:
        return
    time.sleep(0.5)
    g = track_groups(window("Edit:"))
    wrong = [(t, bare(out_label(find(g[t], "AXPopUpButton", "Audio Output Path selector"))), buses[f])
             for t, f in want if t in g
             and bare(out_label(find(g[t], "AXPopUpButton", "Audio Output Path selector"))) != buses[f]]
    for t, got, exp in wrong:
        print(f"WRONG {t}: {got} (want {exp})")
    print("ROUTED" if not (wrong or bad) else f"FAILED {len(wrong) + bad}")


if __name__ == "__main__":
    main("--dry" in sys.argv)
