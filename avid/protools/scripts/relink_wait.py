"""relink_wait.py : after an open with 'Automatically Find & Relink', wait until Pro Tools stops relinking
(offline count is 0, or unchanged for 90 s while Pro Tools' CPU is under 40%), then print the count."""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptctl import engine
from ptsl import PTSL_pb2 as pt
from ptgui import paged
def offline():
    with engine() as e:
        return len(list(paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_OfflineFiles"]}, "file_locations")))
def cpu():
    out = subprocess.run(["ps", "-A", "-o", "%cpu,comm"], capture_output=True, text=True).stdout
    return max([float(l.split()[0]) for l in out.splitlines() if "MacOS/Pro Tools" in l] or [0])
last, since, t0 = None, time.time(), time.time()
while time.time() - t0 < 1800:
    try: n = offline()
    except Exception as ex: print("query failed", ex, flush=True); time.sleep(10); continue
    if n != last: last, since = n, time.time(); print(f"[{round(time.time()-t0)}s] offline {n}", flush=True)
    if n == 0 or (time.time() - since > 90 and cpu() < 40): break
    time.sleep(10)
print("SETTLED offline", last, flush=True)
