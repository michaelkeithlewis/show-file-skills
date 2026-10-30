"""stems_offline.py <audio dir> : tempo, key and stem QC from the files alone, no Pro Tools.

For a session that will not open (producer sessions can hit the -9004 audio-engine deadlock on open), or a stem drop before it is built. Assumes every file starts at song 0, which holds for
consolidated whole-song exports (check LENGTHS: one value means they all line up). Tempo is a sweep of
60-200 BPM at 0.01 for the share of strong onsets within 20 ms of an 8th-note grid from the file start;
on a session that did open it matched the session tempo exactly (120.00, 89% on-grid). File names pick
the groups: drum/perc words give the onset source, vocal words are left out of the key."""
import sys, os, re, json, numpy as np, soundfile as sf, librosa, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze
d = sys.argv[1]; SR = 22050
PERC = re.compile(r"kick|snare|snr|hat|hh|perc|drum|^d |tamb|shaker|clap|ride|crash|cym|tom|beat|loop|808|bd\d|rim|room|ohs?\b|knee", re.I)
VOX = re.compile(r"v lead|vox|vocal|bgv|^lv|harm|choir", re.I)
files = sorted(f for f in os.listdir(d) if f.lower().endswith((".wav", ".aif", ".aiff")) and not f.startswith("._"))
n = 0; perc = None; music = None; qc = []
for f in files:
    y, sr = sf.read(os.path.join(d, f), dtype="float32", always_2d=True)
    pk = float(np.max(np.abs(y))) if y.size else 0; act = float(np.mean(np.max(np.abs(y), 1) > 1e-3)) if y.size else 0
    fs = np.abs(y) >= 0.999; runs = int(np.sum(fs[2:] & fs[1:-1] & fs[:-2]))
    qc.append({"file": f, "peak_db": round(20 * np.log10(pk + 1e-12), 1), "active_pct": round(act * 100, 1), "fullscale_runs": runs, "sec": round(len(y) / sr, 1)})
    m = librosa.resample(y.mean(1), orig_sr=sr, target_sr=SR)
    tgt = "perc" if PERC.search(f) else "vox" if VOX.search(f) else "music"
    if tgt == "vox": continue
    buf = perc if tgt == "perc" else music
    if buf is None or len(buf) < len(m):
        nb = np.zeros(len(m), np.float32)
        if buf is not None: nb[:len(buf)] = buf
        buf = nb
    buf[:len(m)] += m
    if tgt == "perc": perc = buf
    else: music = buf
src = perc if perc is not None and np.max(np.abs(perc)) > 1e-4 else music
env = librosa.onset.onset_strength(y=src, sr=SR); on = librosa.onset.onset_detect(onset_envelope=env, sr=SR, units="frames")
st = env[on]; t = librosa.frames_to_time(on[st >= np.quantile(st, 0.6)], sr=SR)
best = []
for b in np.arange(60, 200.001, 0.01):
    per = 60 / b / 2; r = (t % per) / per
    h = np.histogram(r, bins=100, range=(0, 1))[0]; h2 = np.concatenate([h, h[:10]])
    w = int(round(0.04 / per * 100)) or 1
    c = np.convolve(h2, np.ones(w), "valid")[:100]
    k = int(np.argmax(c)); best.append((c[k] / len(t), b, (k + w / 2) / 100 * per))
best.sort(reverse=True)
print(json.dumps({"src": "perc" if src is perc else "music", "strong_onsets": len(t),
                  "top": [(round(b, 2), round(fr * 100, 1), round(ph * 1000)) for fr, b, ph in best[:8]],
                  "key": analyze.detect_key(music, SR) if music is not None else None}, default=str))
print("QC_FLAGS", json.dumps([q for q in qc if q["peak_db"] < -60 or q["active_pct"] < 1 or q["fullscale_runs"] > 0]))
print("LENGTHS", sorted({q["sec"] for q in qc}))
