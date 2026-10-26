"""clipgain_normalize.py [--target -18] [--peak-cap -1] [--folders ...] [--tracks ...] [--dry] [--force]
Gain-stage every stem with CLIP GAIN, never a rebounce: each audio track's clips get the clip gain
that puts the track's average level (gated RMS of the audio it plays) at --target dBFS, so every
plug-in sees the same input level. A track whose peak would pass --peak-cap stops at the cap.
Clip gain goes in by keystroke (Ctrl+Shift+Up/Down = one Clip Gain Nudge, 0.5 dB in the default prefs,
verified by bounce 2026-10-25), so it lands on the nearest 0.5 dB.
Average = mean power of 400 ms blocks above -60 dBFS and within 20 dB of the mean of those blocks
(drops silence and decay tails, so a stem that plays for 5% of the song is judged on that 5%).
PTSL cannot read clip gain, so run this on FRESH clips (right after prep, clip gain 0). Tracks with
edited clips (more than one clip per channel, or a clip that starts past the file start) are skipped
unless named with --tracks. Never run it while the engineer is working: the keystrokes hit his selection."""
import argparse, collections, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from ptctl import engine
from ptsl import PTSL_pb2 as pt
from ptgui import nudge_clip_gain, posix, paged, edl, user_idle_secs, user_touched, guard_start

NUDGE = 0.5

def level(segments):
    """segments: [(path, channel_index, start, end)] -> (gated RMS dBFS, peak dBFS) of what the track plays."""
    chans = []
    for path, ch, s0, s1 in segments:
        y, sr = sf.read(path, start=s0, stop=s1, dtype="float64", always_2d=True)
        chans.append(y[:, min(ch, y.shape[1] - 1)])
    n = max(len(c) for c in chans)
    y = np.stack([np.pad(c, (0, n - len(c))) for c in chans], axis=1)
    blk = int(48000 * 0.4); m = len(y) // blk
    if m == 0: return -200.0, -200.0
    pw = (y[:m * blk] ** 2).reshape(m, blk, -1).mean(axis=(1, 2))
    db = 10 * np.log10(pw + 1e-20)
    g = db > -60
    if not g.any(): return -200.0, 20 * math.log10(np.abs(y).max() + 1e-20)
    g &= db > 10 * math.log10(pw[g].mean()) - 20
    return 10 * math.log10(pw[g].mean()), 20 * math.log10(np.abs(y).max() + 1e-20)

ap = argparse.ArgumentParser()
ap.add_argument("--target", type=float, default=-18.0); ap.add_argument("--peak-cap", type=float, default=-1.0)
ap.add_argument("--folders", nargs="*"); ap.add_argument("--tracks", nargs="*")
ap.add_argument("--dry", action="store_true"); ap.add_argument("--force", action="store_true")
a = ap.parse_args()
with engine() as e:
    tl = {t.name: t for t in e.track_list()}
    clips = {c["clip_full_name"]: c for c in paged(e, pt.CId_GetClipList, {}, "clip_list")}
    files = {f["file_id"]: posix(f["path"]) for f in paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations")}
    st = e.client.run_command(pt.CId_GetSessionPath, {})
    log = os.path.join(os.path.dirname(posix(st["session_path"]["path"])), ".premix_clipgain.json")
    applied = json.load(open(log)) if os.path.exists(log) else {}
    plan, skipped = [], []
    for name, rows in edl(e).items():
        t = tl.get(name)
        if t is None or not rows or (a.tracks and name not in a.tracks) or (a.folders and t.parent_folder_name not in a.folders):
            continue
        if name in applied and not a.tracks:
            continue   # already clip-gained (see .premix_clipgain.json); name it with --tracks to add more
        cs = [clips.get(r[2]) for r in rows]
        per_ch = collections.Counter(r[0] for r in rows)
        edited = (not all(cs) or max(per_ch.values()) > 1 or any(c["src_start_point"]["position"] != 0 for c in cs)
                  or any(not r[3].startswith("1|1") for r in rows))
        if edited and not a.tracks:
            skipped.append(name); continue
        segs = []
        for r, c in zip(rows, cs):
            sfx = c["clip_full_name"][len(c["clip_root_name"]):]
            ch = 1 if sfx.endswith(".R") else 0
            segs.append((files[c["file_id"]], ch, int(c["src_start_point"]["position"]), int(c["src_end_point"]["position"])))
        rms, peak = level(segs)
        if rms <= -200: continue
        gain = min(a.target - rms, a.peak_cap - peak, 36.0)  # Pro Tools clip gain tops out at +36 dB
        steps = round(gain / NUDGE)
        plan.append((name, rms, peak, steps))
    for name, rms, peak, steps in plan:
        capped = " (peak cap)" if a.target - rms > a.peak_cap - peak else (" (+36 max)" if a.target - rms > 36 else "")
        print(f"{name:40} avg {rms:6.1f}  peak {peak:6.1f}  clip gain {steps * NUDGE:+5.1f} dB{capped}", flush=True)
    print(f"{len(plan)} tracks, skipped (edited): {skipped}", flush=True)
    if a.dry: sys.exit()
    if user_idle_secs() < 120 and not a.force:
        sys.exit(f"someone used the Mac {user_idle_secs():.0f} s ago; rerun when Pro Tools is free (or --force)")
    guard_start()
    for name, rms, peak, steps in plan:
        if user_touched(): sys.exit("STOPPED: someone used the Mac mid-run; rerun to finish (tracks already in .premix_clipgain.json are skipped)")
        nudge_clip_gain(e, name, steps)
        applied[name] = applied.get(name, 0.0) + steps * NUDGE   # premix.py reads this: PTSL cannot read clip gain
        json.dump(applied, open(log, "w"), indent=1)
        print("GAINED", name, f"{steps * NUDGE:+.1f}", flush=True)
    print("NORMALIZE DONE", len(plan), flush=True)
