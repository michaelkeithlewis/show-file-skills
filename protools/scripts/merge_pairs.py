"""merge_pairs.py <stems dir> : merge every hard-panned pair in the OPEN session into one stereo track.
Skips a pair whose source tracks carry inserts/sends or edits. Routes + colors the new track like its source."""
import os, sys, re, subprocess, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prep_session as ps
from ptctl import engine
from ptsl import PTSL_pb2 as pt
rc = pt.CommandId
PY = sys.executable
lr = ps.lr_pairs(sys.argv[1])
print(len(lr["pairs"]), "pairs; lone:", lr["lone"])

def edl(e):
    return e.client.run_command(rc.CId_ExportSessionInfoAsText, {
        "include_file_list": False, "include_clip_list": False, "include_markers": False,
        "include_plugin_list": False, "include_track_edls": True, "show_sub_frames": False,
        "track_list_type": "AllTracks", "include_user_timestamps": False,
        "fade_handling_type": "DontShowCrossfades", "track_offset_options": "Samples",
        "text_as_file_format": "UTF8", "output_type": "ESI_String"})["session_info"]

def track_clips(x):
    out, cur = {}, None
    for ln in x.splitlines():
        if ln.startswith("TRACK NAME:"):
            cur = ln.split("\t", 1)[1].rsplit(" (", 1)[0]; out[cur] = []
        elif cur and re.match(r"^\d+\s*\t", ln):
            f = ln.split("\t"); out[cur].append((f[0].strip(), f[2].strip(), f[3].strip()))
    return out

def strip(name):
    r = subprocess.run([PY, os.path.join(os.path.dirname(os.path.abspath(__file__)), "strips.py"), name], capture_output=True, text=True).stdout.strip()
    return r

with engine() as e:
    tc = track_clips(edl(e))
    tl = {t.name: t for t in e.track_list()}
    pal = e.client.run_command(rc.CId_GetColorPalette, {"color_palette_target": "CPTarget_Tracks"})["color_list"]
    hex2idx = {c.lower(): i + 1 for i, c in enumerate(pal)}
    jobs = []
    for p in lr["pairs"]:
        lroot, rroot = p["l_clip"].rsplit(".", 1)[0], p["r_clip"].rsplit(".", 1)[0]
        lt = [t for t, cl in tc.items() if cl and all(c[1].startswith(lroot) for c in cl)]
        rt = [t for t, cl in tc.items() if cl and all(c[1].startswith(rroot) for c in cl)]
        if len(lt) != 1 or len(rt) != 1:
            print("SKIP", p["name"], "source tracks not found uniquely", lt, rt); continue
        lt, rt = lt[0], rt[0]
        if len(tc[lt]) != 2 or len(tc[rt]) != 2 or any(c[2] != "0" for c in tc[lt] + tc[rt]):
            print("SKIP", p["name"], "sources are edited (not one whole clip at 0)"); continue
        sl, sr = strip(lt), strip(rt)
        if "inserts []" not in sl or "inserts []" not in sr or ":" in sl.split("sends")[1] or ":" in sr.split("sends")[1]:
            print("SKIP", p["name"], "sources have inserts/sends:", sl, "|", sr); continue
        out = re.search(r"out=(.*?) vol", sl).group(1)
        name = p["name"] if p["name"] not in tl else p["name"] + " LR"
        jobs.append((name, lt, rt, p["l_clip"], p["r_clip"], out))
    made = []
    for name, lt, rt, lc, rcl, out in jobs:
        folder = tl[lt].parent_folder_name
        ps.merge_lr_pair(e, name, folder, lc, rcl, before_track=lt)
        got = track_clips(edl(e)).get(name, [])
        ok = [(c[0], c[1]) for c in got] == [("1", lc), ("2", rcl)]
        idx = hex2idx.get((tl[lt].color or "").lower())
        if idx: e.client.run_command(rc.CId_SetTrackColor, {"track_names": [name], "color_index": idx})
        if ok:
            e.client.run_command(rc.CId_DeleteTracks, {"track_names": [lt, rt]})
            made.append((name, out)); print("MERGED", name, "<-", lt, "+", rt, "| folder", folder, "| out", out)
        else:
            print("MISMATCH", name, got, "- sources kept")
for name, out in made:
    if out and out != "PrMst":
        print(subprocess.run([PY, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ptax.py"), "route", out, name],
                             capture_output=True, text=True).stdout.strip())
