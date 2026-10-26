"""pan_to_mono.py [--folders LV BGV] [--tracks NAME...] [--dry] [--no-comp]
Stereo tracks that are really ONE mono signal printed with a pan (the quiet side is an exact scaled copy of the loud side; -10.0 dB on L = pan 61 R) waste a
stereo voice and stereo plug-ins. For each one, with the session open:
  1. Rename the stereo track "<name> ~stereo" and create a MONO "<name>" just before it (same folder).
  2. Spot the LOUDER side's clip at sample 0.
  3. Copy the old track's main output bus, color, solo and mute; delete the old track.
  4. Type the pan into the Output window's "Front Pan Numerical" field (Accessibility; PTSL pan
     write needs the Private API). Pro Tools pans mono with an exact sin/cos -3 dB law (measured
     2026-10-25: 0 = -3.01/-3.01, 61 = -10.41/-0.41), so pan = 100*(4*atan(loud/quiet)/pi - 1).
  5. Unless --no-comp: clip-gain the mono clip up by -20*log10(sin(theta)) (nearest 0.5 dB nudge) so
     the loud side keeps its printed level. Skip it when clipgain_normalize.py runs next.
Only tracks whose clips are whole-file at the session start and come from both channels of ONE
stereo file are touched. Panned-mono = least-squares residual of quiet vs loud < -60 dB, gain > 0.
Dual-mono (gain within 0.05 dB of unity) is left for prep's dual-mono step."""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
import ptax
from ptctl import engine
from ptsl import PTSL_pb2 as pt
from ptgui import set_pan, nudge_clip_gain, strip, posix, paged, edl, user_idle_secs, user_touched, guard_start

def classify(path):
    y, _ = sf.read(path, dtype="float64", always_2d=True)
    if y.shape[1] != 2: return None
    L, R = y[:, 0], y[:, 1]; eL, eR = L @ L, R @ R
    if min(eL, eR) < 1e-12: return None
    loud, p, q = ("L", L, R) if eL >= eR else ("R", R, L)
    g = (p @ q) / (p @ p); res = ((q - g * p) ** 2).sum() / (q @ q)
    if not (res < 1e-6 and g > 0) or abs(20 * math.log10(g)) < 0.05: return None
    th = math.atan(1 / g)
    pan = round(100 * (4 * th / math.pi - 1))
    return {"loud": loud, "pan": pan if loud == "R" else -pan, "quiet_db": round(20 * math.log10(g), 2),
            "comp_db": -20 * math.log10(math.sin(th))}

ap = argparse.ArgumentParser()
ap.add_argument("--folders", nargs="*"); ap.add_argument("--tracks", nargs="*")
ap.add_argument("--dry", action="store_true"); ap.add_argument("--no-comp", action="store_true")
ap.add_argument("--force", action="store_true", help="run even if the Mac was used in the last 2 minutes")
a = ap.parse_args()
with engine() as e:
    tl = {t.name: t for t in e.track_list()}
    clips = {c["clip_full_name"]: c for c in paged(e, pt.CId_GetClipList, {}, "clip_list")}
    files = {f["file_id"]: posix(f["path"]) for f in paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations")}
    pal = e.client.run_command(pt.CId_GetColorPalette, {"color_palette_target": "CPTarget_Tracks"})["color_list"]
    hex2idx = {c.lower(): i + 1 for i, c in enumerate(pal)}
    todo = []
    for name, rows in edl(e).items():
        t = tl.get(name)
        if t is None or (a.tracks and name not in a.tracks) or (a.folders and t.parent_folder_name not in a.folders): continue
        if len(rows) != 2 or not all(r[1] == "1" and r[3].startswith("1|1") and r[2] in clips for r in rows): continue
        cs = [clips[r[2]] for r in rows]
        if cs[0]["file_id"] != cs[1]["file_id"] or any(c["src_start_point"]["position"] != 0 for c in cs): continue
        info = classify(files[cs[0]["file_id"]])
        if not info: continue
        side = next(c for c in cs if c["clip_full_name"].endswith("." + info["loud"]))
        todo.append((name, t, side, info))
    for name, t, side, info in todo:
        print(f"{name}: loud {info['loud']}, quiet side {info['quiet_db']} dB -> mono, pan {info['pan']}", flush=True)
    if a.dry: sys.exit()
    if user_idle_secs() < 120 and not a.force:
        sys.exit(f"someone used the Mac {user_idle_secs():.0f} s ago; rerun when Pro Tools is free (or --force)")
    guard_start()
    for name, t, side, info in todo:
        if user_touched(): sys.exit("STOPPED: someone used the Mac mid-run; rerun to finish (converted tracks no longer qualify)")
        s = strip(name)
        bus = ptax.out_label(ptax.find(s, "AXPopUpButton", "Audio Output Path selector")).rsplit(" (", 1)[0]
        soloed, muted = bool(t.track_attributes.is_soloed), bool(t.track_attributes.is_muted)
        old = name + " ~stereo"
        e.client.run_command(pt.CId_RenameTargetTrack, {"current_name": name, "new_name": old})
        e.client.run_command(pt.CId_CreateNewTracks, {"number_of_tracks": 1, "track_name": name, "track_type": "TType_Audio",
            "track_format": "TFormat_Mono", "track_timebase": "TTimebase_Samples",
            "insertion_point_position": "TIPoint_Before", "insertion_point_track_name": old})
        e.client.run_command(pt.CId_SpotClipsByID, {"src_clips": [side["clip_id"]], "dst_track_name": name,
            "dst_location_data": {"location_type": "SLType_Start", "location": {"time_type": "TLType_Samples", "location": "0"}}})
        idx = hex2idx.get((t.color or "").lower())
        if idx: e.client.run_command(pt.CId_SetTrackColor, {"track_names": [name], "color_index": idx})
        e.client.run_command(pt.CId_DeleteTracks, {"track_names": [old]})
        time.sleep(0.8)
        r = ptax.route_track(ptax.track_groups(ptax.window("Mix:")), name, bus)
        got = set_pan(name, info["pan"])
        if soloed: e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": [name], "enabled": True})
        if muted: e.client.run_command(pt.CId_SetTrackMuteState, {"track_names": [name], "enabled": True})
        steps = 0 if a.no_comp else round(info["comp_db"] / 0.5)
        nudge_clip_gain(e, name, steps)
        print(f"MONO {name}: {r} | pan {got} | comp {steps * 0.5:+.1f} dB", flush=True)
    print("PAN_TO_MONO DONE", len(todo), flush=True)
