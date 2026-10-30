"""session_map.py <outdir> [--no-lyrics] : read the musical map of the OPEN session (read-only; nothing is written to PT).

For a session someone else built (a producer session), where the tempo map is already set and the audio
sits wherever the producer put it. It prints:
  GRID   the session's own tempo/meter, read with CId_GetTimeAsType (bar|beat -> samples; PTSL has no tempo
         read), and how far the tempo map strays from one constant tempo.
  PHASE  whether the audio is on that grid: strong onsets against the 8th-note grid from bar 1, swept over
         +/-3% of the session tempo and every phase. The real click wins sharply (a 170.00 BPM song: 98% of
         strong onsets on-grid, 169/171: ~11%). A best phase of 20-50 ms is onset-detector lag, not an offset.
  KEY    Krumhansl key of the summed non-drum stems.
  SECTIONS  Whisper lyric sections (lyrics.py) snapped to session bars. Compare with the producer's markers
         (PRODUCER_MARKERS) before placing anything: producers mark a section a bar before the vocal enters.
  QC_FLAGS  stems that are silent, barely play (<1% active), touch 0 dBFS or flat-top (3+ samples at full scale).
It renders each folder group (perc / lv / bgv / music) from the EDL in session time to <outdir>/*.wav at
22.05 kHz, skipping inactive and muted tracks; <outdir>/mix.wav is the input for ref_offset.py."""
import sys, os, re, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf, librosa
from ptctl import engine
from ptsl import PTSL_pb2 as pt
from ptgui import paged
import analyze, lyrics
assert len(sys.argv) > 1 and not sys.argv[1].startswith("-"), __doc__
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
SR = 22050

def S(e, loc):
    r = e.client.run_command(pt.CId_GetTimeAsType, {"location": {"location": loc, "time_type": "TLType_BarsBeats"}, "time_type": "TLType_Samples"})
    return int(r["converted_location"]["location"])

with engine() as e:
    ssr = e.session_sample_rate()
    tl = e.track_list()
    info = e.client.run_command(pt.CId_ExportSessionInfoAsText, {"include_track_edls": True, "track_offset_options": "TOOptions_Samples", "output_type": "ESI_String"})["session_info"]
    clips = {c["clip_full_name"]: c for c in paged(e, pt.CId_GetClipList, {}, "clip_list")}
    files = {f["file_id"]: f["path"] for f in paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations")}
    beat0, beat1, bar2 = S(e, "1|1|000"), S(e, "1|2|000"), S(e, "2|1|000")
    name = e.session_name()
    mem = e.client.run_command(pt.CId_GetMemoryLocations, {}).get("memory_locations", [])

by = {t.name: t for t in tl}
st = lambda a: pt.TrackAttributeState.Name(a)
def anc(n):
    out = []; p = by[n].parent_folder_name if n in by else ""
    while p: out.append(p); p = by[p].parent_folder_name if p in by else ""
    return out
rows = {}
for b in re.split(r"\nTRACK NAME:\t", info)[1:]:
    tn = re.sub(r" \((Stereo|Mono)\)$", "", b.split("\n")[0].strip())
    rows[tn] = [[x.strip() for x in l.split("\t")] for l in b.split("\n") if re.match(r"^\d+\s*\t\s*\d+\s*\t", l)]
    rows[tn] = [(r[2], int(r[3]), int(r[4]), r[6] if len(r) > 6 else "") for r in rows[tn] if r[3].isdigit() and r[4].isdigit()]

beat = beat1 - beat0; barlen = bar2 - beat0; meter = round(barlen / beat); bpm = 60 * ssr / beat
end = max([r[2] for v in rows.values() for r in v] or [0])
nbars = int(end / barlen) + 2
with engine() as e:
    probe = [b for b in (2, 9, 17, 33, 49, 65, 81, 97, 129) if b <= nbars] + [nbars]
    bar_s = {b: S(e, f"{b}|1|000") for b in probe}
dev = max(abs(bar_s[b] - (b - 1) * barlen) for b in bar_s) / ssr
grid = {"bpm": round(bpm, 3), "meter_beats": meter, "bar1_sample": beat0, "bar_sec": barlen / ssr,
        "tempo_map_max_dev_sec": round(dev, 4), "song_end_sec": round(end / ssr, 2), "bars": round(end / barlen, 2)}
print("GRID", grid, flush=True)

n = int(end / ssr * SR) + SR
groups = {"perc": np.zeros(n, np.float32), "lv": np.zeros(n, np.float32), "bgv": np.zeros(n, np.float32), "music": np.zeros(n, np.float32)}
qc, cache, used = [], {}, []
for tn, rr in rows.items():
    t = by.get(tn)
    if t is None or not rr: continue
    a = t.track_attributes
    inactive = st(a.is_inactive).endswith(("Explicitly", "Implicitly")); hidden = st(a.is_hidden).endswith(("Explicitly", "Implicitly"))
    A = anc(tn)
    g = "perc" if ({"DRUM GROUP", "PERC GROUP"} & set(A)) else "lv" if any(x == "LV" or x.startswith("LV.") for x in A) else "bgv" if ("BGV" in A or "VOCALS" in A) else "music"
    skip = inactive or a.is_muted or not A
    used.append({"track": tn, "folder": A[0] if A else "", "group": g, "inactive": inactive, "hidden": hidden, "muted": a.is_muted, "used_in_analysis": not skip})
    for cn, s0, s1, state in rr:
        c = clips.get(cn)
        if not c or c.get("file_id") not in files: continue
        p = files[c["file_id"]]
        if p not in cache:
            try:
                y, fsr = sf.read(p, dtype="float32", always_2d=True)
            except Exception as ex:
                qc.append({"file": os.path.basename(p), "error": str(ex)}); cache[p] = None; continue
            pk = float(np.max(np.abs(y))) if y.size else 0.0
            rms = float(np.sqrt(np.mean(y.astype(np.float64) ** 2))) if y.size else 0.0
            act = float(np.mean(np.max(np.abs(y), axis=1) > 10 ** (-60 / 20))) if y.size else 0.0
            fs = np.abs(y) >= 0.999; runs = int(np.sum(fs[2:] & fs[1:-1] & fs[:-2]))
            qc.append({"file": os.path.basename(p), "track": tn, "rate": fsr, "ch": y.shape[1], "peak_db": round(20*np.log10(pk+1e-12), 1),
                       "rms_db": round(20*np.log10(rms+1e-12), 1), "active_pct": round(act*100, 1), "fullscale_runs": runs})
            cache[p] = (y, fsr)
        if skip or cache[p] is None: continue
        y, fsr = cache[p]
        ch = 1 if (cn.endswith(".R") and y.shape[1] > 1) else 0
        off = int(c["src_start_point"]["position"]); ln = s1 - s0
        seg = y[off:off + ln, ch]
        seg = librosa.resample(seg, orig_sr=fsr, target_sr=SR) if fsr != SR else seg
        i0 = int(s0 / ssr * SR); seg = seg[:max(0, n - i0)]
        groups[g][i0:i0 + len(seg)] += seg
cache = None
for k, v in groups.items():
    pk = float(np.max(np.abs(v))) or 1.0
    if np.max(np.abs(v)) > 1e-6: sf.write(f"{OUT}/{k}.wav", v / pk * 0.9, SR)
mix = groups["music"] + groups["perc"] + groups["lv"] + groups["bgv"]; mix /= (np.max(np.abs(mix)) or 1) / 0.9
sf.write(f"{OUT}/mix.wav", mix, SR)

src = groups["perc"] if np.max(np.abs(groups["perc"])) > 1e-4 else groups["music"]
env = librosa.onset.onset_strength(y=src, sr=SR); on = librosa.onset.onset_detect(onset_envelope=env, sr=SR, units="frames")
stg = env[on]; t_on = librosa.frames_to_time(on[stg >= np.quantile(stg, 0.6)], sr=SR) if len(on) else np.array([])
def frac(per, ph, w=0.02):
    r = (t_on - ph) % per; return float(np.mean(np.minimum(r, per - r) < w)) if len(t_on) else 0.0
sweep = []
for b in np.arange(bpm * 0.97, bpm * 1.03, 0.01):
    per = 60 / b / 2
    sweep += [(frac(per, ph), b, ph) for ph in np.arange(0, per, 0.002)]
sweep.sort(reverse=True)
per = 60 / bpm / 2
at = max((frac(per, ph), ph) for ph in np.arange(0, per, 0.002))
fit = {"src": "perc" if src is groups["perc"] else "music", "strong_onsets": int(len(t_on)),
       "best": [(round(b, 2), round(f * 100, 1), round(ph * 1000)) for f, b, ph in sweep[:3]],
       "session_tempo_on_grid_pct": round(at[0] * 100, 1), "session_tempo_best_phase_ms": round(at[1] * 1000)}
print("PHASE", fit, flush=True)
key = analyze.detect_key(groups["music"] + 0.5 * groups["lv"], SR)
print("KEY", key, flush=True)

lyr = None
if np.max(np.abs(groups["lv"])) > 1e-4 and "--no-lyrics" not in sys.argv:
    lyr = lyrics.analyze_lyrical_structure(f"{OUT}/lv.wav", f"{OUT}/mix.wav")
    tx = lyr.pop("transcript", None)
    json.dump(tx, open(f"{OUT}/transcript.json", "w"), indent=1)
    bl = barlen / ssr
    for s in lyr["sections"]:
        s["bar"] = int(round(s["start"] / bl)) + 1; s["bar_sec"] = round((s["bar"] - 1) * bl, 3)
    print("SECTIONS", [(s["label"], round(s["start"], 1), s["bar"]) for s in lyr["sections"]], flush=True)
print("PRODUCER_MARKERS", [(m.get("name"), str(m.get("start_time")).strip()) for m in mem], flush=True)
json.dump({"session": name, "grid": grid, "fit": fit, "key": key, "lyrics": lyr, "tracks": used, "qc": qc,
           "producer_markers": [(m.get("name"), m.get("start_time")) for m in mem]}, open(f"{OUT}/analysis.json", "w"), indent=1, default=str)
bad = [q for q in qc if q.get("error") or q["peak_db"] < -60 or q["active_pct"] < 1 or q["fullscale_runs"] > 0 or q["peak_db"] >= -0.1]
print("QC_FLAGS", json.dumps(bad), flush=True)
print("DONE")
