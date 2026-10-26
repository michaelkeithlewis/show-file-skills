"""place_onto.py MAP.json [--start 01:00:00:00] [--dry]
Move imported stems ONTO the tracks a template already has, then delete the loose stem tracks.
Use it when the template's own tracks carry the inserts, sends and VCAs you want to keep (a
streaming or broadcast template, a house church template, a live-capture template).

MAP.json is a list of [source_track, template_track] pairs, for example:
    [["session_1-Kick In", "Kick IN"], ["session_3-Snare Top", "Snare Top"], ["AMB MICS.1", "AMB MICS"]]
--start is where the clips land; default is the session start time (a session that starts at
01:00:00:00 would otherwise get every clip pasted an hour early). Verify every track with the EDL after."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("map"); ap.add_argument("--start"); ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
from ptctl import engine
from ptsl import PTSL_pb2 as pt
rc = pt.CommandId

def move_onto(e, src, dest, start):
    e.select_all_clips_on_track(src); e.copy()
    e.select_tracks_by_name([dest])
    e.set_timeline_selection(in_time=start, out_time=start)
    e.paste()
    e.client.run_command(rc.CId_DeleteTracks, {"track_names": [src]})

pairs = json.load(open(a.map))
with engine() as e:
    names = {t.name for t in e.track_list()}
    start = a.start or e.session_start_time()
    for s, d in pairs:
        if s not in names or d not in names:
            print("SKIP", s, "->", d, "(missing:", ", ".join(x for x in (s, d) if x not in names) + ")", flush=True); continue
        if a.dry: print("would move", s, "->", d, "at", start); continue
        move_onto(e, s, d, start); print("onto", s, "->", d, flush=True)
