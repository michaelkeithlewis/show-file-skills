#!/usr/bin/env python3
"""prep_session.py - end-to-end "stems folder -> prepped PT session" building blocks.

The agent drives these with judgment (categorization, channel/ambiguity calls);
confirm with the engineer at the marked decision points. See
references/session-prep.md for the playbook.

Run pieces via the CLI, or import the functions. Always use the venv python
that has py-ptsl installed (see README.md):
    .venv/bin/python scripts/prep_session.py channels "<stems dir>"
"""
import argparse, json, os, re, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from ptctl import engine
from ptsl import PTSL_pb2 as pt
rc = pt.CommandId

# ---------- session creation -------------------------------------------------

def create_from_template(group, template_name, song_name, parent_dir,
                         sample_rate=48000, bit_depth=24, wait_secs=1800, poll=10,
                         on_progress=print):
    """Create a session from a template and WAIT for it to finish opening.

    A big template takes 10-20 min while PT instantiates plugins. For that whole
    window PTSL answers PT_NoOpenedSession and the .ptx on disk is a 0-byte stub.
    Both look exactly like a hang and are NORMAL, so this polls until the session
    really reports open rather than throwing the race back at the caller.
    (If ~/Documents is iCloud-synced, keep the Pro Tools Plug-In Settings folder
    downloaded and point parent_dir at a `.nosync` parent first -- see
    references/session-prep.md.)
    """
    import time
    t0 = time.time()
    try:
        with engine() as e:
            b = e.create_session_from_template(template_group=group, template_name=template_name,
                                               name=song_name, path=parent_dir)
            b.sample_rate(sample_rate); b.bit_depth(bit_depth); b.wave_format()
            b.create()
    except Exception as ex:
        # .create() returns before the session is open; the builder's own
        # follow-up calls race ahead and throw. Not a failure -- the poll below
        # is the real answer.
        if on_progress:
            on_progress("create() raised %s: %s -- polling for the session" % (type(ex).__name__, ex))
    last = None
    while time.time() - t0 < wait_secs:
        try:
            with engine() as e:
                name = e.session_name()
                if name:
                    return {"session": name, "path": e.session_path(),
                            "tracks": len(e.track_list()),
                            "waited_secs": round(time.time() - t0)}
        except Exception as ex:
            last = "%s: %s" % (type(ex).__name__, ex)
        if on_progress:
            on_progress("[%ss] still building (plugins instantiating) -- %s"
                        % (round(time.time() - t0), last))
        time.sleep(poll)
    raise TimeoutError("session did not open within %ss; last status: %s" % (wait_secs, last))

# ---------- stems: download + import ----------------------------------------

def download_offloaded(stems_dir):
    """Materialize any iCloud-offloaded (dataless) stems by reading them. Import
    fails on .icloud placeholders."""
    out = []
    for p in stem_files(stems_dir):
        with open(p, "rb") as fh:
            while fh.read(1 << 20):
                pass
        out.append(p)
    return out

def stem_files(stems_dir, recursive=True):
    """Audio files under stems_dir. RECURSIVE by default -- drops routinely arrive
    as a tree (BASS/, DRUMS/CCM KIT/, ...) and a flat listdir silently sees only
    the few files at the top level (one 64-stem drop showed only 3)."""
    out = []
    if recursive:
        for dp, _dn, fn in os.walk(stems_dir):
            for f in fn:
                if f.lower().endswith((".wav", ".aif", ".aiff")) and not f.startswith("._"):
                    out.append(os.path.join(dp, f))
    else:
        out = [os.path.join(stems_dir, f) for f in os.listdir(stems_dir)
               if f.lower().endswith((".wav", ".aif", ".aiff")) and not f.startswith("._")]
    return sorted(out)

def import_stems(file_list):
    """Import audio to NEW tracks. Uses raw CId_Import with IType_Audio - the
    wrapped import_audio is broken (hardcodes IType_Session)."""
    body = {"import_type": "IType_Audio", "audio_data": {
        "file_list": file_list,
        "audio_operations": "AOperations_AddAudio",
        "destination": "MDestination_NewTrack", "location": "MLocation_SessionStart",
        "audio_destination": "MDestination_NewTrack", "audio_location": "MLocation_SessionStart",
        "location_data": {"location_type": "SLType_Start", "location_options": "TOOptions_TimeCode",
                          "location_value": "00:00:00:00"}}}
    with engine() as e:
        before = len(e.track_list())
        e.client.run_command(rc.CId_Import, body)
        return {"added": len(e.track_list()) - before}

# ---------- channel analysis (FULL FILE - never sample the head) -------------

def channel_kind(path):
    """Returns 'mono' | 'dual-mono' | 'stereo' | 'L-only' | 'R-only' analysing the
    WHOLE file. (Head-sampling misclassifies stems whose intro is identical L/R but whose body is stereo.)
    'L-only'/'R-only' = a stereo file with one side dead, i.e. one half of a
    hard-panned pair. Those must be merged with their partner by lr_pairs(), not kept
    as two stereo tracks."""
    import soundfile as sf
    if sf.info(path).channels < 2:
        return "mono"
    y, _ = sf.read(path, always_2d=True)
    L, R = y[:, 0], y[:, 1]
    pl, pr = float(np.max(np.abs(L))), float(np.max(np.abs(R)))
    if pr < 1e-5 < pl:
        return "L-only"
    if pl < 1e-5 < pr:
        return "R-only"
    if float(np.max(np.abs(L - R))) < 1e-4:
        return "dual-mono"
    mid = np.sqrt(np.mean(((L + R) / 2) ** 2)); side = np.sqrt(np.mean(((L - R) / 2) ** 2))
    return "stereo" if side / (mid + 1e-12) > 0.02 else "dual-mono"

def louder_side(path):
    import soundfile as sf
    y, _ = sf.read(path, frames=3_000_000, always_2d=True)
    if y.shape[1] < 2:
        return "L"
    r = [float(np.sqrt(np.mean(y[:, c] ** 2))) for c in range(2)]
    return "L" if r[0] >= r[1] else "R"

def _pair_base(path):
    """('<base>', 'L'|'R'|None) from a stem name: drops the export counter (_1, _2),
    then a 'PAN L/R' tag anywhere ('CINEMA TOM PAN L 2.0' -> 'CINEMA TOM 2.0'),
    else a trailing side tag (L, R, Left, ...)."""
    b = re.sub(r"_\d+$", "", os.path.splitext(os.path.basename(path))[0])
    m = (re.search(r"(?i)[\s_.-]+pan[\s_-]*(l|r|left|right)\b", b)
         or re.search(r"(?i)[\s_.-]+(l|r|left|right)$", b))
    if not m:
        return b.strip(), None
    return " ".join((b[:m.start()] + b[m.end():]).split()), m.group(1)[0].upper()

def lr_pairs(stems_dir, kinds=None):
    """Find hard-panned pairs that belong on ONE stereo track:
    an L-only + R-only stereo file, or two mono files tagged L/R, sharing a base name
    in the same folder. The side comes from the AUDIO for one-sided files, never the
    name (one real drop named its RIGHT half '... PAN L_2'). Returns
    {"pairs": [{name, folder, L, R, l_clip, r_clip, name_lies}], "lone": [...]}.
    l_clip/r_clip are the PT clip names to spot with merge_lr_pair()."""
    kinds = kinds or {f: channel_kind(f) for f in stem_files(stems_dir)}
    groups = {}
    for f, k in kinds.items():
        base, tag = _pair_base(f)
        side = {"L-only": "L", "R-only": "R"}.get(k) or (tag if k == "mono" else None)
        if side:
            groups.setdefault((os.path.dirname(f), base.upper()), []).append((f, k, side, tag, base))
    pairs, lone = [], []
    for (d, _), items in groups.items():
        ls = [i for i in items if i[2] == "L"]; rs = [i for i in items if i[2] == "R"]
        if len(ls) == 1 and len(rs) == 1:
            (lf, lk, _, ltag, base), (rf, rk, _, rtag, _) = ls[0], rs[0]
            root = lambda f: os.path.splitext(os.path.basename(f))[0]
            pairs.append({"name": base, "folder": os.path.relpath(d, stems_dir),
                          "L": lf, "R": rf,
                          "l_clip": root(lf) + (".L" if lk != "mono" else ""),
                          "r_clip": root(rf) + (".R" if rk != "mono" else ""),
                          "name_lies": ltag == "R" or rtag == "L"})
        else:
            lone += [i[0] for i in items if i[1] != "mono"]   # one-sided, no partner -> mono of the live side
    return {"pairs": pairs, "lone": lone}

# ---------- organize: fold a loose track into a folder ----------------------

def fold_into_folder(e, src_name, dest_name, folder, track_format):
    """Recreate src as a track INSIDE folder (move-into-folder has no command):
    create in folder -> copy clips -> paste -> delete loose src.
    NOTE: copy/paste has silently landed empty tracks. Prefer dualmono_to_mono /
    CId_SpotClipsByID, and verify every track with the EDL afterwards. The new
    track outputs to the session's main bus, NOT the folder bus; run
    route_folders.py afterwards."""
    e.client.run_command(rc.CId_CreateNewTracks, {"number_of_tracks": 1, "track_name": dest_name,
        "track_type": "TType_Audio", "track_format": track_format, "track_timebase": "TTimebase_Samples",
        "insertion_point_position": "TIPoint_Last", "insertion_point_track_name": folder})
    e.select_all_clips_on_track(src_name); e.copy()
    e.select_tracks_by_name([dest_name])
    e.set_timeline_selection(in_time="00:00:00:00", out_time="00:00:00:00")
    e.paste()
    e.client.run_command(rc.CId_DeleteTracks, {"track_names": [src_name]})

def move_onto(e, src_name, dest_name, start=None):
    """Move every clip of a loose track ONTO an existing template track, then
    delete the loose track. Use this when the template's own tracks carry the
    inserts, sends and VCAs you want to keep. `start` defaults to the session
    start time: a session that starts at 01:00:00:00 would otherwise get every
    clip pasted an hour early."""
    start = start or e.session_start_time()
    e.select_all_clips_on_track(src_name); e.copy()
    e.select_tracks_by_name([dest_name])
    e.set_timeline_selection(in_time=start, out_time=start)
    e.paste()
    e.client.run_command(rc.CId_DeleteTracks, {"track_names": [src_name]})

def dualmono_to_mono(e, dest_name, folder, clip_base, side):
    """Create a MONO track in folder and spot only the louder channel clip
    (<clip_base>.<side>) onto it - true mono from a dual-mono file, no rebounce."""
    cid = _clip_id(e, f"{clip_base}.{side}")
    if not cid:
        raise RuntimeError(f"clip {clip_base}.{side} not found")
    e.client.run_command(rc.CId_CreateNewTracks, {"number_of_tracks": 1, "track_name": dest_name,
        "track_type": "TType_Audio", "track_format": "TFormat_Mono", "track_timebase": "TTimebase_Samples",
        "insertion_point_position": "TIPoint_Last", "insertion_point_track_name": folder})
    e.client.run_command(rc.CId_SpotClipsByID, {"src_clips": [cid], "dst_track_name": dest_name,
        "dst_location_data": {"location_type": "SLType_Start",
                              "location": {"time_type": "TLType_Samples", "location": "0"}}})

def merge_lr_pair(e, dest_name, folder, l_clip, r_clip, before_track=None):
    """ONE stereo track from a hard-panned pair: spot l_clip on ch1 and r_clip on ch2.
    The two clips may come from DIFFERENT files (one-sided stereo halves '<a>.L' +
    '<b>.R', or two mono files) - SpotClipsByID takes that, verified on PT 2026.4. No rebounce, no new audio file. Verify with the EDL after."""
    ids = [_clip_id(e, c) for c in (l_clip, r_clip)]
    if not all(ids):
        raise RuntimeError(f"clip not found: {[c for c, i in zip((l_clip, r_clip), ids) if not i]}")
    pos = ({"insertion_point_position": "TIPoint_Before", "insertion_point_track_name": before_track}
           if before_track else
           {"insertion_point_position": "TIPoint_Last", "insertion_point_track_name": folder})
    e.client.run_command(rc.CId_CreateNewTracks, {"number_of_tracks": 1, "track_name": dest_name,
        "track_type": "TType_Audio", "track_format": "TFormat_Stereo", "track_timebase": "TTimebase_Samples",
        **pos})
    e.client.run_command(rc.CId_SpotClipsByID, {"src_clips": ids, "dst_track_name": dest_name,
        "dst_location_data": {"location_type": "SLType_Start",
                              "location": {"time_type": "TLType_Samples", "location": "0"}}})

def _clip_id(e, clip_full_name):
    off = 0
    while True:
        cl = e.client.run_command(rc.CId_GetClipList, {"pagination_request": {"limit": 500, "offset": off}})
        page = cl.get("clip_list", [])
        for c in page:
            if c.get("clip_full_name") == clip_full_name:
                return c["clip_id"]
        if len(page) < 500:
            return None
        off += 500

# ---------- color each stem to match its parent group -----------------------

def color_by_group(e):
    pal = e.client.run_command(rc.CId_GetColorPalette, {"color_palette_target": "CPTarget_Tracks"})["color_list"]
    hex2idx = {c.lower(): i + 1 for i, c in enumerate(pal)}
    byname = {t.name: t for t in e.track_list()}
    by_idx = {}
    for t in e.track_list():
        if "Audio" in pt.TrackType.Name(t.type) and t.parent_folder_name in byname:
            idx = hex2idx.get((byname[t.parent_folder_name].color or "").lower())
            if idx:
                by_idx.setdefault(idx, []).append(t.name)
    for idx, names in by_idx.items():
        e.client.run_command(rc.CId_SetTrackColor, {"track_names": names, "color_index": idx})
    return {idx: names for idx, names in by_idx.items()}

# ---------- click grid: detect tempo, snap section markers to bars -----------

def detect_click_grid(percussive_paths):
    """Grid-search a constant tempo+phase against percussion onsets. Click tempos
    are usually whole numbers and detection tends to read slightly high, so
    rounded_bpm is the detected value rounded DOWN. Feed a dense source (kick,
    snare, hats, shakers): a sparse one returns a confident triplet or octave
    error. Returns bpm/period."""
    import librosa
    ys = []
    sr = None
    for p in percussive_paths:
        y, sr = librosa.load(p, sr=None, mono=True); ys.append(y)
    n = min(len(x) for x in ys); mix = sum(x[:n] for x in ys)
    onsets = librosa.onset.onset_detect(y=mix, sr=sr, units="time", backtrack=True)
    best = None
    for bpm in np.arange(60.0, 200.0, 0.02):
        period = 60.0 / bpm
        res = onsets % period; d = np.minimum(res, period - res)
        err = float(np.mean(d ** 2))
        if best is None or err < best[0]:
            best = (err, bpm, period)
    bpm = best[1]
    return {"detected_bpm": round(bpm, 2), "rounded_bpm": float(int(bpm)), "period": best[2],
            "onsets": int(len(onsets)), "candidates": score_candidates(onsets, bpm)}

def _fit(onsets, bpm, tol):
    """(rms_sec, on_grid_fraction) of onsets against a bpm grid at its best phase."""
    period = 60.0 / bpm
    best = None
    for ph in np.linspace(0, period, 120, endpoint=False):
        r = (onsets - ph) % period
        d = np.minimum(r, period - r)
        cur = (float(np.mean(d <= tol)), -float(np.sqrt(np.mean(d ** 2))))
        if best is None or cur > best:
            best = cur
    return -best[1], best[0]

def score_candidates(onsets, bpm, tol=0.035, lo=50.0, hi=220.0):
    """The grid search has no confidence value and its error shrinks as the
    period shrinks, so it leans toward fast tempos and octave/triplet relatives.
    This scores the detected tempo, its relatives, and tempos implied by the
    modal inter-onset interval (the felt pulse). Each candidate is refined within
    +/-1.5 percent, then reported with the RMS distance from onsets to the nearest
    grid line and the share of onsets within `tol` seconds of a line. A slower
    tempo that keeps a high on-grid share is usually the click; confirm by ear."""
    onsets = np.asarray(onsets, dtype=float)
    ioi = np.diff(np.sort(onsets))
    ioi = ioi[ioi > 0.1]
    modal = None
    seeds = {bpm, bpm / 2, bpm / 3, bpm * 2, bpm / 1.5}
    if len(ioi):
        hist, edges = np.histogram(ioi, bins=np.arange(0.1, 3.0, 0.01))
        modal = float(edges[np.argmax(hist)] + 0.005)
        seeds |= {60.0 / modal * k for k in (0.25, 0.5, 1.0, 2.0)}
    rows = []
    for c in sorted(x for x in seeds if lo <= x <= hi):
        grid = np.arange(c * 0.985, c * 1.015, 0.02)
        fits = [(_fit(onsets, b, tol), b) for b in grid]
        (rms, frac), b = max(fits, key=lambda f: (f[0][1], -f[0][0]))
        rows.append({"bpm": round(float(b), 2), "rms_ms": round(rms * 1000, 1),
                     "on_grid_pct": round(frac * 100, 1)})
    rows.sort(key=lambda r: (-r["on_grid_pct"], r["bpm"]))
    return {"rows": rows, "modal_ioi_sec": round(modal, 3) if modal else None}

def place_grid_markers(e, sections, bpm, beats_per_bar=4, base=200):
    """Place section markers on exact bar lines of a bpm grid (bar1 = 0:00),
    Absolute reference (tempo-safe). sections = [{start, label}]. Returns bars."""
    import ptprep
    bar_len = beats_per_bar * 60.0 / bpm
    marks, bars = [], []
    for s in sections:
        k = round(s["start"] / bar_len)
        marks.append((round(k * bar_len, 3), s["label"])); bars.append((s["label"], k + 1))
    # clear our prior prep markers then place
    sc = json.load(open(ptprep.SIDE_CAR)) if os.path.exists(ptprep.SIDE_CAR) else {}
    key = e.session_name(); nums = sc.get(key, [])
    if nums:
        e.client.run_command(rc.CId_ClearMemoryLocation, {"location_list": nums})
        sc[key] = []; ptprep._save_sidecar(sc)
    ptprep.place_markers(e, marks)
    return bars


# ---------- CLI --------------------------------------------------------------

def _cli():
    p = argparse.ArgumentParser(prog="prep_session")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("channels"); sp.add_argument("stems_dir")
    sp = sub.add_parser("download"); sp.add_argument("stems_dir")
    sp = sub.add_parser("grid"); sp.add_argument("paths", nargs="+")
    a = p.parse_args()
    if a.cmd == "channels":
        root = a.stems_dir
        kinds = {}
        for f in stem_files(root):
            rel = os.path.relpath(os.path.dirname(f), root)
            k = kinds[f] = channel_kind(f)
            side = "  louder=" + louder_side(f) if k == "dual-mono" else ""
            print(f"{rel:24} {os.path.basename(f):28} {k}{side}", flush=True)
        lr = lr_pairs(root, kinds)
        if lr["pairs"] or lr["lone"]:
            print("\nHARD-PANNED PAIRS -> one stereo track each (merge_lr_pair):")
            for p in lr["pairs"]:
                lie = "  (name lies about the side)" if p["name_lies"] else ""
                print(f"  {p['name']}: L={p['l_clip']}  R={p['r_clip']}{lie}")
            for f in lr["lone"]:
                print(f"  NO PARTNER: {os.path.basename(f)} -> mono track from its live side")
    elif a.cmd == "download":
        print("materialized:", len(download_offloaded(a.stems_dir)))
    elif a.cmd == "grid":
        print(json.dumps(detect_click_grid(a.paths), indent=2))

if __name__ == "__main__":
    _cli()
