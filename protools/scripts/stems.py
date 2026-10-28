"""stems.py: stem and instrumental bounces, solo-in-place through the whole chain.
  stems.py plan  [--map auto|map.json]                      list the stems this session would print (no bouncing)
  stems.py bounce --song "The Gift" --in S --out S [--mode stems|instrumental|both] [--version V2]
                  [--map map.json] [--only DRUMS BASS] [--click] [--final <final PtMst.wav>] [--zip]
How the engineer prints stems: SOLO IN PLACE, so every stem gets all the processing. Solo the stem's folder,
everything else goes implicitly muted, and the solo-safe returns (MASTER BUS, GLUE VERB, K/S Para, every FX return in
the template) still run, so the stem carries its reverbs, the bus chain and the master chain. Bounce PtMst.
Range: use the FINAL master's exact range (sample in/out), so stems and instrumental line up with it sample for sample.
Layout:
  Bounced Files/<Song> FINALS/<Song> STEMS/<Song>_<STEM>.wav   STEM in caps: DRUMS, PERC, BASS, AGs, EGs, KEYS, PIANO,
                                                               ORCH, FX, LVs, BGVs, CLICK ... ; <Song> STEMS.zip beside it
  Bounced Files/<Song> FINALS/<Song>_MKL_<ver>_Instrumental_PtMst.wav   everything but the VOCALS folder
WAV, interleaved stereo, 48 kHz 24-bit (the session's bounce settings). Older deliveries were 16-bit; pass
--bits 16 if a client asks. Solo and mute states are restored afterwards."""
import argparse, json, os, re, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from ptctl import engine
from ptsl import PTSL_pb2 as pt
from ptgui import posix

# Template folder -> stem name. A folder not listed here becomes a stem named after itself.
STEM_NAMES = {"DRUM GROUP": "DRUMS", "PERC GROUP": "PERC", "BASS GROUP": "BASS", "GUITAR GROUP": "EGs", "AGs": "AGs",
              "KEYS GROUP": "KEYS", "Piano": "PIANO", "ORCH GRP": "ORCH", "FX GROUP": "FX", "LV": "LVs", "LV DBLS": "LV DBLs",
              "BGV": "BGVs"}
VOCAL_ROOT = "VOCALS"
SPLIT_INTO_CHILDREN = {"BAND", VOCAL_ROOT}      # these are containers; their child folders are the stems

def session_tracks(e):
    tl = e.track_list()
    kind = {t.name: pt.TrackType.Name(t.type) for t in tl}
    return tl, kind

def auto_map(tl, kind):
    """{stem name: [folders to solo]} from the folder tree. A child folder of GUITAR GROUP / KEYS GROUP becomes its own
    stem (AGs, PIANO); its parent stem then solos the parent's other members only."""
    folders = [t for t in tl if "Folder" in kind[t.name]]
    by_parent = {}
    for t in tl: by_parent.setdefault(t.parent_folder_name, []).append(t)
    stems = {}
    def has_audio(f):
        stack = [f]
        while stack:
            x = stack.pop()
            for c in by_parent.get(x, []):
                if "Audio" in kind[c.name]: return True
                if "Folder" in kind[c.name]: stack.append(c.name)
        return False
    for f in folders:
        if f.name in SPLIT_INTO_CHILDREN or not has_audio(f.name): continue
        parent = f.parent_folder_name
        root = (not parent) or parent in SPLIT_INTO_CHILDREN          # top-level folder, or a folder directly in BAND / VOCALS
        split = parent in ("GUITAR GROUP", "KEYS GROUP") and f.name in STEM_NAMES   # AGs / Piano get their own stem
        if not (root or split): continue                                # KICK GRP, TAIKO HITS, RIDESSSS ride with their parent
        name = STEM_NAMES.get(f.name, f.name.upper())
        if split:
            stems[name] = [f.name]; continue
        if f.name in ("GUITAR GROUP", "KEYS GROUP"):
            subs = {c.name for c in by_parent.get(f.name, []) if "Folder" in kind[c.name] and c.name in STEM_NAMES and has_audio(c.name)}
            members = [c.name for c in by_parent.get(f.name, []) if c.name not in subs and "Aux" not in kind[c.name]]
            stems[name] = members if subs else [f.name]
            continue
        stems[name] = [f.name]
    return stems

def vocal_free_solo(tl, kind):
    """What to solo for an instrumental: every top-level folder and top-level audio track except VOCALS."""
    return [t.name for t in tl if not t.parent_folder_name and t.name != VOCAL_ROOT
            and ("Folder" in kind[t.name] or "Audio" in kind[t.name])]

def bounce(e, base, t_in, t_out, bits):
    e.client.run_command(pt.CId_SetTimelineSelection, {"in_time": str(t_in), "out_time": str(t_out), "location_type": "TLType_Samples"})
    ai = pt.EM_AudioInfo(compression_type=pt.CT_PCM, export_format=pt.EF_Interleaved, bit_depth=pt.Bit16 if bits == 16 else pt.Bit24,
                         sample_rate=pt.SR_48000, pad_to_frame_boundary=pt.TB_False, delivery_format=pt.EM_DF_SingleFile)
    loc = pt.EM_LocationInfo(import_after_bounce=pt.TB_False, file_destination=pt.EM_FD_SessionFolder)
    e.export_mix(base_name=base, file_type=pt.EMFType_WAV, sources=[pt.EM_SourceInfo(source_type=pt.EMSType_Bus, name="PtMst")],
                 audio_info=ai, video_info=pt.EM_VideoInfo(), location_info=loc, dolby_atmos_info=pt.EM_DolbyAtmosInfo(), offline_bounce=pt.TB_True)

def stats(path):
    y, sr = sf.read(path, always_2d=True)
    peak = 20 * np.log10(np.abs(y).max() + 1e-12); rms = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
    return y, peak, rms

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "bounce"])
    ap.add_argument("--song"); ap.add_argument("--in", dest="t_in", type=int); ap.add_argument("--out", dest="t_out", type=int)
    ap.add_argument("--mode", default="both", choices=["stems", "instrumental", "both"]); ap.add_argument("--version", default="")
    ap.add_argument("--map"); ap.add_argument("--only", nargs="*"); ap.add_argument("--click", action="store_true")
    ap.add_argument("--final"); ap.add_argument("--zip", action="store_true"); ap.add_argument("--bits", type=int, default=24)
    a = ap.parse_args()
    with engine() as e:
        tl, kind = session_tracks(e)
        smap = json.load(open(a.map)) if a.map else auto_map(tl, kind)
        if a.click and any(t.name == "Click 1" for t in tl): smap["CLICK"] = ["Click 1"]
        if a.only: smap = {k: v for k, v in smap.items() if k in a.only}
        inst = vocal_free_solo(tl, kind)
        if a.cmd == "plan":
            for k, v in smap.items(): print(f"STEM {k:10} solo {v}")
            print("INSTRUMENTAL solo", inst); return
        sess = posix(e.client.run_command(pt.CId_GetSessionPath, {})["session_path"]["path"])
        bf = os.path.join(os.path.dirname(sess), "Bounced Files")
        finals = os.path.join(bf, f"{a.song} FINALS"); stems_dir = os.path.join(finals, f"{a.song} STEMS")
        os.makedirs(stems_dir, exist_ok=True)
        was_solo = [t.name for t in tl if t.track_attributes.is_soloed]
        all_names = [t.name for t in tl]
        jobs = []
        if a.mode in ("stems", "both"): jobs += [(f"{a.song}_{k}", v, stems_dir) for k, v in smap.items()]
        if a.mode in ("instrumental", "both"):
            jobs.append((f"{a.song}_MKL_{a.version + '_' if a.version else ''}Instrumental_PtMst", inst, finals))
        made = []
        try:
            for base, solo, dest in jobs:
                e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": all_names, "enabled": False})
                e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": solo, "enabled": True})
                t0 = time.time(); bounce(e, base, a.t_in, a.t_out, a.bits)
                src = os.path.join(bf, base + ".wav"); dst = os.path.join(dest, base + ".wav")
                shutil.move(src, dst); y, pk, rm = stats(dst); made.append((dst, y))
                print(f"BOUNCED {base}  {time.time() - t0:.0f} s  peak {pk:6.1f}  rms {rm:6.1f}  solo {solo}", flush=True)
        finally:
            e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": all_names, "enabled": False})
            if was_solo: e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": was_solo, "enabled": True})
    stem_files = [y for p, y in made if os.path.dirname(p) == stems_dir]
    if a.final and stem_files:
        f, _ = sf.read(a.final, always_2d=True); n = min([len(f)] + [len(y) for y in stem_files])
        s = sum(y[:n] for y in stem_files); r = f[:n] - s
        print("stems summed vs final: correlation %.3f, residual %.1f dB under the final (the master chain runs per stem, so it never nulls)"
              % (np.corrcoef(s.mean(1), f[:n].mean(1))[0, 1], 20 * np.log10(np.sqrt(np.mean(f[:n] ** 2)) / (np.sqrt(np.mean(r ** 2)) + 1e-12))))
    if a.zip and stem_files:
        z = stems_dir + ".zip"; subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", stems_dir, z], check=True); print("ZIP", z)
    print("STEMS DONE", len(made))

if __name__ == "__main__":
    main()
