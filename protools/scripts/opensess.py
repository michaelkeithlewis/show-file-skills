"""opensess.py <ptx path> -> open a session and wait until PTSL reports it open"""
import os, sys, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptctl import engine
from ptsl import PTSL_pb2 as pt
path = sys.argv[1]; want = path.rsplit("/", 1)[1][:-4]
t0 = time.time()
try:
    with engine() as e:
        e.client.run_command(pt.CId_OpenSession, {"session_path": path})
except Exception as ex:
    print("open raised", type(ex).__name__, ex, flush=True)
while time.time() - t0 < 1800:
    try:
        with engine() as e:
            if e.session_name() == want:
                print("OPEN", want, round(time.time() - t0), "s", len(e.track_list()), "tracks", flush=True); sys.exit(0)
    except Exception as ex:
        pass
    print(f"[{round(time.time()-t0)}s] waiting", flush=True); time.sleep(10)
sys.exit("timeout")
