"""filecheck.py : every audio file the open session uses: is it on disk at the path Pro Tools now has, and does any path still say .nosync."""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptctl import engine
from ptsl import PTSL_pb2 as pt
from ptgui import paged
with engine() as e:
    fl = list(paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations"))
    off = list(paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_OfflineFiles"]}, "file_locations"))
    name = e.session_name()
paths = [f.get("path", "") for f in fl]
dirs = collections.Counter(os.path.dirname(p) for p in paths)
print(name, len(paths), "files,", len(off), "offline,", sum("nosync" in p for p in paths), "nosync paths,",
      sum(not os.path.exists(p) for p in paths if p), "not on disk")
for d, n in dirs.most_common(6): print(f"  {n:3d} {d}")
for f in off[:5]: print("  OFFLINE", f.get("path"))
