"""premix_state.py save F | restore F | record PTX W | savesess: park solos for the offline bounces, put them back, save."""
import json, os, sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from ptctl import engine
from ptsl import PTSL_pb2 as pt
cmd = sys.argv[1]
with engine() as e:
    if cmd == "save":
        sol = [t.name for t in e.track_list() if t.track_attributes.is_soloed]
        json.dump(sol, open(sys.argv[2], "w")); print("soloed:", sol)
        if sol: e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": sol, "enabled": False})
    elif cmd == "restore":
        sol = json.load(open(sys.argv[2]))
        if sol: e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": sol, "enabled": True})
        print("re-soloed:", sol)
    elif cmd == "record":
        d = json.load(open(sys.argv[3])); d["plan"] = json.load(open(sys.argv[4]))
        json.dump(d, open(os.path.join(os.path.dirname(sys.argv[2]), ".premix_faders.json"), "w"), indent=1)
    elif cmd == "close":
        e.client.run_command(pt.CId_CloseSession, {"save_on_close": False}); print("closed")
    elif cmd == "savesess":
        e.client.run_command(pt.CId_SaveSession, {}); print("saved", e.session_name())
