#!/usr/bin/env python3
"""route_groups.py - last-resort helper for routing foldered tracks by hand.

Use route_folders.py first; it routes through the Accessibility API with no
clicks. This script is for when that is not possible (no Accessibility grant).

WHY THIS IS SEMI-MANUAL: PTSL cannot set a track's main output without the
Private API. Every route was tried and each one is closed:
  * CId_SetTrackMainOutputAssignments works, but needs a `signalpath_id`.
  * The only command that returns one, CId_GetTrackControlInfo, answers
    "Private API has not been enabled in this session". CId_EnableAPI needs an
    Avid-issued encrypted key.
  * Bus names are not ids ("Signal path with ID 'PERC GROUP' was not found").
  * Ids are not enumerable -- 0..63 all rejected; the id format is a 128-bit
    GUID like {00000000-2a000000-a4bb95e0-d6e12fae}.
  * A track's own .id / .id_compressed are a different id space and are rejected.
  * CId_CreateSignalPath: "Creating signal paths of type 'SPType_Bus' is not yet
    implemented."
  * CId_Import with IType_Session (Import Session Data, which CAN carry main
    output assignments in the GUI) fails headlessly with a generic error.

So this script does the only part that can be automated without Accessibility,
SELECTING each folder's tracks in turn, and leaves you one gesture per folder:

    Option+Shift+click the output selector on any selected track, pick the bus.

Run `verify_routing.py` afterwards to confirm.

    route_groups.py [--list]
"""
import os, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptctl import engine
from ptsl import PTSL_pb2 as pt

# The folder list comes from the open session. Do NOT hard-code a bus list from
# CId_GetExportMixSourceList: it only enumerates buses already in use as a
# source, so an absent name there means "nothing feeds it yet", not "no such
# bus". The bus a folder owns is shown on the folder's own input selector and is
# usually, but not always, the folder's name.


def children(e, folder):
    return [t.name for t in e.track_list()
            if t.type == pt.TType_Audio and t.parent_folder_name == folder]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print the plan and exit")
    a = ap.parse_args()

    with engine() as e:
        folders = [t.name for t in e.track_list() if t.type == pt.TType_RoutingFolder]
        plan = [(f, f, children(e, f)) for f in folders]
        plan = [p for p in plan if p[2]]
        if a.list:
            for f, bus, ch in plan:
                print(f"{f:14} -> {bus:14} ({len(ch)} tracks)")
            return
        print("For each group: Option+Shift+click the output selector on any\n"
              "selected track and choose the bus named below.\n")
        for i, (f, bus, ch) in enumerate(plan, 1):
            e.select_tracks_by_name(ch)
            print(f"[{i}/{len(plan)}] {f}: {len(ch)} tracks selected  ->  set output to the bus '{f}' owns")
            try:
                input("      press Enter when done ")
            except EOFError:
                print("      (non-interactive; stopping here)")
                return
        e.save_session()
        print("\nsaved. now run: verify_routing.py")


if __name__ == "__main__":
    main()
