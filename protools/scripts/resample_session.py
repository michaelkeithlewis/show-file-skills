"""resample_session.py "<stems dir>" [--track NAME] [--dry]
Repair a BUILT session whose stems were linked at the wrong sample rate (AddAudio never converts:
a 44.1k stem in a 48k session plays 8.8% fast and 1.5 semitones sharp). Run with the session open.
1. Every timeline file whose rate != the session's gets an afconvert copy (prep_session.resample_stems):
   stems under <stems dir> go to "<stems dir> 48k/", PT's "Renamed Audio Files" copies to "<...> 48k/_renamed/".
2. The copies go into the clip list (CId_ImportAudioToClipList, AddAudio).
3. In Slip mode (Shuffle pushes the old clip right instead of replacing it), each affected track gets
   SelectAllClipsOnTrack + Clear, then the new clips spotted at sample 0 in the old channel order.
   Only tracks holding whole-file clips at the session start are swapped; anything edited is listed and left.
4. Edit mode is restored. Verify with the EDL, then save. Markers placed from analysis (absolute samples)
   are already in true time; markers placed by ear on the fast audio are NOT rescaled by this script.
First run: a 108-track, 113-file session, 2026-10-25."""
import argparse, collections, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soundfile as sf
from ptctl import engine
from ptsl import PTSL_pb2 as pt
import prep_session as ps

def posix(p): return "/" + p.split(":", 1)[1].replace(":", "/") if ":" in p and not p.startswith("/") else p
def paged(e, cid, body, key):
    out, off = [], 0
    while True:
        p = e.client.run_command(cid, {**body, "pagination_request": {"limit": 500, "offset": off}}).get(key, [])
        out += p
        if len(p) < 500: return out
        off += 500
def clips(e): return paged(e, pt.CId_GetClipList, {}, "clip_list")
def files(e): return {f["file_id"]: posix(f["path"]) for f in paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations")}
def suffix(c): return c["clip_full_name"][len(c["clip_root_name"]):]
def edl(e):
    t = e.client.run_command(pt.CId_ExportSessionInfoAsText, {"include_track_edls": True, "include_file_list": False,
                                                              "output_type": "ESI_String"}).get("session_info", "")
    out = []
    for b in re.split(r"\nTRACK NAME:\t", t)[1:]:
        name = re.sub(r" \((Stereo|Mono)\)$", "", b.split("\n")[0].strip())
        rows = [[x.strip() for x in l.split("\t")] for l in b.split("\n") if re.match(r"^\d+\s*\t\s*\d+\s*\t", l)]
        out.append((name, sorted(rows)))
    return out

ap = argparse.ArgumentParser()
ap.add_argument("stems_dir"); ap.add_argument("--track"); ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
stems = a.stems_dir.rstrip("/")
with engine() as e:
    sr = int(e.session_sample_rate())
    out_dir = f"{stems} {sr // 1000}k"
    allc, fl = clips(e), files(e)
    byname = {c["clip_full_name"]: c for c in allc}
    rate = {fid: sf.info(p).samplerate for fid, p in fl.items() if os.path.exists(p)}
    plan, skipped, wrong = [], [], set()
    for name, rows in edl(e):
        if a.track and name != a.track: continue
        cs = [byname.get(r[2]) for r in rows]
        if not rows or not all(cs) or all(rate.get(c["file_id"]) == sr for c in cs): continue
        whole = all(r[1] == "1" and r[3].startswith("1|1") for r in rows) and len({r[0] for r in rows}) == len(rows) \
            and all(c["src_start_point"]["position"] == 0 for c in cs)
        if not whole: skipped.append(name); continue
        plan.append((name, [(r[2], c) for r, c in zip(rows, cs)]))
        wrong |= {fl[c["file_id"]] for c in cs}
    def dest(p):
        if p.startswith(stems + "/"): return os.path.join(out_dir, os.path.splitext(os.path.relpath(p, stems))[0] + ".aif")
        return os.path.join(out_dir, "_renamed", os.path.splitext(os.path.basename(p))[0] + ".aif")
    print(f"session {sr} Hz: {len(plan)} tracks to swap, {len(wrong)} files to convert, skipped (edited): {skipped}", flush=True)
    if a.dry: sys.exit()
    for p in sorted(wrong):
        if not os.path.exists(dest(p)):
            ps.resample_stems(os.path.dirname(p), sr, out_dir=os.path.dirname(dest(p)), files=[p])
    have = {p: fid for fid, p in fl.items()}
    todo = sorted({dest(p) for p in wrong} - set(have))
    if todo:
        r = e.client.run_command(pt.CId_ImportAudioToClipList, {"file_list": todo, "audio_operations": "AOperations_AddAudio"})
        if r.get("failure_list"): sys.exit(f"import failures: {r['failure_list'][:3]}")
        print("imported", len(todo), flush=True)
    allc, fl = clips(e), files(e)
    have = {p: fid for fid, p in fl.items()}
    byfile = collections.defaultdict(list)
    for c in allc: byfile[c["file_id"]].append(c)
    mode0 = e.client.run_command(pt.CId_GetEditMode, {})["current_setting"]
    e.client.run_command(pt.CId_SetEditMode, {"edit_mode": "EMO_Slip"})
    try:
        for name, chans in plan:
            src = []
            for old, c in chans:
                new = [x for x in byfile[have[dest(fl[c["file_id"]])]] if suffix(x) == suffix(c)]
                assert new, (name, old)
                src.append(new[0]["clip_id"])
            e.client.run_command(pt.CId_SelectAllClipsOnTrack, {"track_name": name})
            e.client.run_command(pt.CId_Clear, {})
            e.client.run_command(pt.CId_SpotClipsByID, {"src_clips": src, "dst_track_name": name,
                "dst_location_data": {"location_type": "SLType_Start", "location": {"time_type": "TLType_Samples", "location": "0"}}})
            print("swapped", name, flush=True)
    finally:
        e.client.run_command(pt.CId_SetEditMode, {"edit_mode": mode0})
    left = [n for n, rows in edl(e) if any(rate.get(byname[r[2]]["file_id"]) not in (None, sr) for r in rows if r[2] in byname)]
    print("RESAMPLE DONE", len(plan), "tracks; still on wrong-rate clips:", left, flush=True)
