"""channel_check.py : channel format of every track in the OPEN session, from the EDL (read-only).
Counts mono tracks, stereo tracks built from two files (an L/R pair already merged), and stereo tracks on one
stereo file with that file's channel_kind (stereo / dual-mono / panned-mono / L-only / R-only). It lists by name
only the stereo-file tracks that are dual-mono, panned-mono or one-sided: those are the ones to fix (step 3).
unknown-clip = a clip PTSL could not match to a file (hidden demo/reference tracks, usually)."""
import sys, os, collections; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptctl import engine
from ptsl import PTSL_pb2 as pt
from ptgui import posix, paged, edl
import prep_session as ps
with engine() as e:
    tl = {t.name: t for t in e.track_list()}
    clips = {c["clip_full_name"]: c for c in paged(e, pt.CId_GetClipList, {}, "clip_list")}
    files = {f["file_id"]: posix(f["path"]) for f in paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations")}
    rows_by = edl(e)
out = collections.defaultdict(list)
for name, rows in rows_by.items():
    t = tl.get(name)
    if not rows or t is None: continue
    cs = [clips.get(r[2]) for r in rows]
    if not all(cs): out["unknown-clip"].append(name); continue
    fids = {c["file_id"] for c in cs}
    fmt = "stereo" if int(t.format) == 2 else "mono"
    if fmt == "mono": out["mono track"].append(name); continue
    if len(fids) == 2: out["stereo track, two files (merged pair)"].append(name); continue
    k = ps.channel_kind(files[cs[0]["file_id"]])
    out[f"stereo track, file {k}"].append((name, t.parent_folder_name))
for k, v in out.items(): print(f"{k}: {len(v)}"); 
for k, v in out.items():
    if "dual" in k or "panned" in k or "only" in k: print(k, v)
