#!/usr/bin/env python3
"""stemid.py - identify stems by listening, not by filename.

For drops whose files are unnamed or misnamed (Audio 1_03.wav, Track 07, "Inst 1").
The only part of a filename it reads is a channel suffix (.L/.R, _L/_R, " L"/" R"),
which Pro Tools writes on every split-stereo file whatever the track is called.
--blind ignores even that. Names are printed next to the result and scored only
when you pass --truth.

  PY stemid.py "<stems dir>"                         # proposal table
  PY stemid.py "<stems dir>" --json out.json         # + machine-readable proposal
  PY stemid.py "<stems dir>" --truth map.json        # score folders vs {folder: [stem base, ...]}
  PY stemid.py "<stems dir>" --debug                 # + features and top tags per source
  PY stemid.py "<stems dir>" --blind                 # pair L/R by audio only

Passes:
  1. Activity (relative to each file's own peak), level, spectrum, decay rate,
     onsets and chroma per file, at 16 kHz.
  2. Stereo pairs: by channel suffix, else by audio (identical envelope shape, level
     and spectrum, onsets in sync to 10 ms). Audio-only pairs are marked "confirm":
     a tight double (two takes of one part) can pass for a decorrelated stereo pair.
     Identical halves are reported as dual-mono (really one mono source).
  3. AST (AudioSet, ONNX) tags over the four busiest 10 s windows, each normalized
     to -20 dBFS first (stems sit far below what AudioSet was trained on).
  4. Drums by spectrum: cymbal, stereo kit pair = OH, kick vs tom by the lowest
     resonance, snare by body + wires, anything broadband = kit mic.
  5. Vocals. Slow decay (reverb/delay tail) = FX return, which joins the dry stem
     it rings on (that stem's VERB) or VOCALS when it only throws on a few words.
     Dry stems singing the same notes at once (chroma) are one line (lead + its
     doubles); a stem singing alone is the lead in those bars. The line covering
     the most of the song is LV; every other line is a harmony (BGV).
  6. A track name and template folder per source. The folder names come from the
     FOLDER table below; edit it to match your own template's routing folders.

Model: ~/.cache/stemid/ast.onnx (Xenova/ast-finetuned-audioset-10-10-0.4593, fp32).
Per-file features and tags are cached in ~/.cache/stemid/cache, so a re-run is quick.
Run it niced when Pro Tools is busy: `nice -n 15 $PY stemid.py ...`.
"""
import argparse, hashlib, json, os, pickle, re, sys
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

SR = 16000
HOP = 320                      # 20 ms frames
NFFT = 1024
BANDS = [(20, 120), (120, 300), (300, 1000), (1000, 3000), (3000, 8000)]
CACHE = os.path.expanduser("~/.cache/stemid")
MODEL = os.path.join(CACHE, "ast.onnx")
AUDIO_EXT = (".wav", ".aif", ".aiff", ".flac")
AST_MEAN, AST_STD = -4.2677393, 4.5689974
TAIL = 150                     # 3 s an FX return can ring after its dry note
WET_FALL = -200                # dB/s; dry vocals drop ~-280, reverb/delay returns ~-100..-160
SUFFIX = re.compile(r"^(.*?)[ ._-](L|R|Left|Right|LEFT|RIGHT)$")

FAMILIES = {
    "VOX": ["Singing", "Male singing", "Female singing", "Child singing", "Choir",
            "Synthetic singing", "Rapping", "Humming", "Speech", "Male speech, man speaking",
            "Female speech, woman speaking", "A capella", "Vocal music", "Chant", "Mantra",
            "Lullaby", "Yodeling", "Whispering", "Narration, monologue", "Beatboxing"],
    "KIT": ["Drum kit", "Drum", "Bass drum", "Snare drum", "Rimshot", "Drum roll",
            "Drum machine", "Cymbal", "Hi-hat", "Crash cymbal", "Timpani", "Tabla"],
    "PERC": ["Tambourine", "Rattle (instrument)", "Maraca", "Cowbell", "Wood block",
             "Clapping", "Finger snapping", "Jingle bell", "Shaker"],
    "GUITAR": ["Guitar", "Electric guitar", "Acoustic guitar", "Steel guitar, slide guitar",
               "Strum", "Tapping (guitar technique)", "Banjo", "Mandolin", "Ukulele",
               "Plucked string instrument", "Distortion"],
    "BASS": ["Bass guitar", "Double bass"],
    "KEYS": ["Piano", "Electric piano", "Keyboard (musical)", "Organ", "Electronic organ",
             "Hammond organ", "Synthesizer", "Sampler", "Harpsichord", "Accordion",
             "Glockenspiel", "Vibraphone", "Marimba, xylophone"],
    "ORCH": ["Bowed string instrument", "String section", "Violin, fiddle", "Cello",
             "Orchestra", "Brass instrument", "French horn", "Trumpet", "Trombone",
             "Harp", "Flute", "Saxophone", "Clarinet"],
}
# Class -> routing folder in YOUR template. These defaults match a common layout
# (DRUM GROUP > KICK/SNARE/TOM/OH GRP; BAND > BASS/GUITAR/KEYS/ORCH; VOCALS > LV/BGV).
FOLDER = {"KICK": "KICK GRP", "SNARE": "SNARE GRP", "TOM": "TOM GRP", "OH": "OH GRP",
          "CYM": "OH GRP", "KIT": "DRUM GROUP", "PERC": "PERC GROUP", "BASS": "BASS GROUP",
          "GTR": "GUITAR GROUP", "KEYS": "KEYS GROUP", "ORCH": "ORCH GRP", "LV": "LV",
          "BGV": "BGV", "VOXFX": "VOCALS", "DEAD": "-"}


# ---------- io + cache --------------------------------------------------------

def stem_paths(root):
    out = []
    for dp, _, fs in os.walk(root):
        out += [os.path.join(dp, f) for f in fs
                if f.lower().endswith(AUDIO_EXT) and not f.startswith("._")]
    return sorted(out)

def load_16k(path):
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    g = gcd(int(sr), SR)
    return [resample_poly(y[:, c], SR // g, int(sr) // g).astype(np.float32)
            for c in range(y.shape[1])]

def cached(tag, paths, fn):
    h = hashlib.sha1(tag.encode())
    for p in sorted(paths):
        st = os.stat(p)
        h.update(f"{p}|{st.st_size}|{int(st.st_mtime)}".encode())
    path = os.path.join(CACHE, "cache", h.hexdigest()[:20] + ".pkl")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    val = fn()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(val, f)
    return val


# ---------- per-signal features -----------------------------------------------

def env_db(x):
    n = len(x) // HOP
    fr = x[: n * HOP].reshape(n, HOP).astype(np.float64)
    return np.maximum(10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-10), -100).astype(np.float32)

def active(env):
    """Frames within 40 dB of the file's own loudest frame (floor -75 dBFS)."""
    return env > max(-75.0, min(-50.0, float(env.max()) - 40))

def smooth_db(env, w):
    lin = np.convolve(10 ** (env.astype(np.float64) / 10), np.ones(w) / w, "same")
    return np.maximum(10 * np.log10(lin + 1e-10), -80)

def features(x):
    import librosa
    env = env_db(x)
    act = active(env)
    f = {"env": env, "dur": len(x) / SR, "peak_db": float(20 * np.log10(np.max(np.abs(x)) + 1e-10))}
    if act.sum() < 25 or env.max() < -75:       # under half a second of signal = dead stem
        f["silent"] = True
        return f
    S = np.abs(librosa.stft(x, n_fft=NFFT, hop_length=HOP, center=False)) ** 2
    m = min(S.shape[1], len(act))
    S, a = S[:, :m], act[:m]
    Sa = S[:, a]
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    tot = Sa.sum() + 1e-12
    f["bands"] = [float(Sa[(freqs >= lo) & (freqs < hi)].sum() / tot) for lo, hi in BANDS]
    f["centroid"] = float((freqs[:, None] * Sa).sum() / tot)
    f["level_db"] = float(10 * np.log10(np.mean(10 ** (env[act] / 10))))
    mel = librosa.feature.melspectrogram(S=Sa, sr=SR, n_mels=48)
    f["mel"] = (10 * np.log10(mel.mean(axis=1) + 1e-12)).astype(np.float32)
    H, P = librosa.decompose.hpss(np.sqrt(S[:, ::2]), kernel_size=17)
    aa = a[::2][: H.shape[1]]
    hp, pp = float((H[:, aa] ** 2).sum()), float((P[:, aa] ** 2).sum())
    f["perc"] = pp / (hp + pp + 1e-12)
    onv = librosa.onset.onset_strength(S=librosa.power_to_db(S), sr=SR, hop_length=HOP)
    on = librosa.onset.onset_detect(onset_envelope=onv, sr=SR, hop_length=HOP, units="frames")
    on = on[a[np.minimum(on, m - 1)]] if len(on) else on
    f["onsets_per_s"] = float(len(on) / (a.sum() * HOP / SR))
    # 10 ms onset envelope: L/R halves of one source hit in sync, two takes do not
    f["onset10"] = librosa.onset.onset_strength(y=x, sr=SR, hop_length=160).astype(np.float16)
    # decay: how fast the level can fall (2nd percentile of the slope, dB/s)
    sm = smooth_db(env, 3)
    d = np.diff(sm) / (HOP / SR)
    da = act[:-1] & (sm[:-1] > env.max() - 40)
    f["fall"] = float(np.percentile(d[da], 2)) if da.sum() > 50 else 0.0
    # fine spectrum: chroma for "same notes?" and the lowest resonance for kick vs tom
    S4 = np.abs(librosa.stft(x, n_fft=4096, hop_length=HOP, center=False)) ** 2
    m4 = min(S4.shape[1], len(act))
    f["chroma"] = librosa.feature.chroma_stft(S=S4[:, :m4], sr=SR).astype(np.float16)
    f4 = np.fft.rfftfreq(4096, 1 / SR)
    lo = (f4 >= 30) & (f4 <= 400)
    spec = S4[:, :m4][:, act[:m4]].mean(axis=1)
    f["lowpeak"] = float(f4[lo][np.argmax(spec[lo])])
    return f

def combine(fs):
    """Features of a multi-channel source from its channels' features."""
    if len(fs) == 1:
        return dict(fs[0])
    n = min(len(f["env"]) for f in fs)
    env = 10 * np.log10(np.mean([10 ** (f["env"][:n] / 10) for f in fs], axis=0) + 1e-10)
    out = {"env": np.maximum(env, -100).astype(np.float32), "dur": fs[0]["dur"],
           "peak_db": max(f["peak_db"] for f in fs)}
    live = [f for f in fs if not f.get("silent")]
    if not live:
        out["silent"] = True
        return out
    for k in ("centroid", "perc", "onsets_per_s", "fall", "lowpeak"):
        out[k] = float(np.mean([f[k] for f in live]))
    out["bands"] = list(np.mean([f["bands"] for f in live], axis=0))
    out["mel"] = np.mean([f["mel"] for f in live], axis=0)
    nc = min(f["chroma"].shape[1] for f in live)
    out["chroma"] = np.mean([f["chroma"][:, :nc].astype(np.float32) for f in live], axis=0)
    act = active(out["env"])
    out["level_db"] = float(10 * np.log10(np.mean(10 ** (out["env"][act] / 10))))
    return out

def wave_corr(a, b, act):
    """Zero-lag correlation of two channels over the active frames."""
    n = min(len(a), len(b), len(act) * HOP)
    m = np.repeat(act[: n // HOP], HOP)
    a, b = a[: len(m)][m].astype(np.float64), b[: len(m)][m].astype(np.float64)
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-12))


# ---------- AST (AudioSet) tagging ---------------------------------------------

_SESS, _LABELS, _BANKS = None, None, None

def _ast():
    global _SESS, _LABELS
    if _SESS is None:
        import onnxruntime as ort
        import urllib.request
        repo = "https://huggingface.co/Xenova/ast-finetuned-audioset-10-10-0.4593/resolve/main/"
        for name, url in (("config.json", repo + "config.json"), ("ast.onnx", repo + "onnx/model.onnx")):
            if not os.path.exists(os.path.join(CACHE, name)):              # first run: ~350 MB
                os.makedirs(CACHE, exist_ok=True)
                urllib.request.urlretrieve(url, os.path.join(CACHE, name + ".part"))
                os.replace(os.path.join(CACHE, name + ".part"), os.path.join(CACHE, name))
        o = ort.SessionOptions()
        o.intra_op_num_threads = int(os.environ.get("STEMID_THREADS", "4"))
        _SESS = ort.InferenceSession(MODEL, o, providers=["CPUExecutionProvider"])
        cfg = json.load(open(os.path.join(CACHE, "config.json")))
        _LABELS = [cfg["id2label"][str(i)] for i in range(len(cfg["id2label"]))]
    return _SESS, _LABELS

def _kaldi_banks():
    global _BANKS
    if _BANKS is None:
        mel = lambda f: 1127.0 * np.log(1.0 + f / 700.0)
        nb, lo, hi = 128, mel(20.0), mel(SR / 2)
        d = (hi - lo) / (nb + 1)
        fm = mel(np.arange(256) * SR / 512)[None, :]
        left = lo + np.arange(nb)[:, None] * d
        up, down = (fm - left) / d, (left + 2 * d - fm) / d
        _BANKS = np.pad(np.maximum(0, np.minimum(up, down)), ((0, 0), (0, 1)))
    return _BANKS

def fbank(x):
    """torchaudio.compliance.kaldi.fbank as ASTFeatureExtractor calls it (hanning, 128 mels)."""
    n = 1 + (len(x) - 400) // 160
    fr = x[np.arange(400)[None, :] + 160 * np.arange(n)[:, None]].astype(np.float64)
    fr -= fr.mean(axis=1, keepdims=True)
    fr = np.concatenate([fr[:, :1] * 0.03, fr[:, 1:] - 0.97 * fr[:, :-1]], axis=1)
    fr *= np.hanning(400)
    P = np.abs(np.fft.rfft(fr, n=512)) ** 2
    return np.log(np.maximum(P @ _kaldi_banks().T, np.finfo(np.float32).eps))

def ast_tags(x, act, k=4):
    """Max AudioSet probability over the k busiest 10.24 s windows."""
    W, L = 512, 512 * HOP
    starts = []
    if len(x) > L:
        cand = list(range(0, len(act) - W + 1, 125))
        score = [int(act[s: s + W].sum()) for s in cand]
        for i in np.argsort(score)[::-1]:
            if score[i] == 0 or len(starts) == k:
                break
            if all(abs(cand[i] - t) >= W for t in starts):
                starts.append(cand[i])
    starts = starts or [0]
    batch = []
    for s in starts:
        seg = x[s * HOP: s * HOP + L].astype(np.float64)
        a = np.repeat(act[s: s + W], HOP)[: len(seg)]
        rms = np.sqrt(np.mean(seg[a] ** 2)) if a.any() else np.sqrt(np.mean(seg ** 2))
        seg = seg * min(10 ** (40 / 20), 0.1 / max(rms, 1e-9))      # active part to -20 dBFS
        seg = np.pad(seg, (0, max(0, 400 - len(seg))))
        fb = fbank(seg)[:1024]
        fb = np.pad(fb, ((0, 1024 - fb.shape[0]), (0, 0)))
        batch.append((fb - AST_MEAN) / (AST_STD * 2))
    sess, labels = _ast()
    logits = sess.run(None, {"input_values": np.stack(batch).astype(np.float32)})[0]
    p = 1 / (1 + np.exp(-logits))
    return dict(zip(labels, p.max(axis=0).tolist()))


# ---------- pairing ------------------------------------------------------------

def mel_dist(a, b):
    d = (a - a.mean()) - (b - b.mean())
    return float(np.sqrt(np.mean(d ** 2)))

def pair_stats(fa, fb):
    if fa.get("silent") or fb.get("silent"):
        return None
    ea, eb = fa["env"], fb["env"]
    if abs(len(ea) - len(eb)) > max(5, 0.01 * len(ea)):
        return None
    n = min(len(ea), len(eb))
    oa, ob = fa["onset10"].astype(np.float32), fb["onset10"].astype(np.float32)
    no = min(len(oa), len(ob))
    return {"shape": float(np.corrcoef(smooth_db(ea[:n], 12), smooth_db(eb[:n], 12))[0, 1]),
            "dlev": abs(fa["level_db"] - fb["level_db"]),
            "mdist": mel_dist(fa["mel"], fb["mel"]),
            "sync": float(np.corrcoef(oa[:no], ob[:no])[0, 1])}

def suffix_pairs(paths):
    groups = {}
    for p in paths:
        m = SUFFIX.match(os.path.splitext(os.path.basename(p))[0])
        if m:
            groups.setdefault((os.path.dirname(p), m.group(1)), {})[m.group(2)[0].upper()] = p
    return [(g["L"], g["R"]) for g in groups.values() if set(g) == {"L", "R"}]

def audio_pairs(paths, F):
    mono = [p for p in paths if F[p]["nch"] == 1]
    cands = []
    for i, a in enumerate(mono):
        for b in mono[i + 1:]:
            s = pair_stats(F[a], F[b])
            if s and s["shape"] > 0.98 and s["dlev"] < 3 and s["mdist"] < 3 and s["sync"] > 0.9:
                cands.append((s["sync"] + s["shape"], a, b))
    used, pairs = set(), []
    for _, a, b in sorted(cands, key=lambda c: -c[0]):
        if a not in used and b not in used:
            used |= {a, b}
            pairs.append((a, b))
    return pairs


# ---------- classification -----------------------------------------------------

def fam_scores(tags):
    return {fam: max(tags.get(l, 0.0) for l in labels) for fam, labels in FAMILIES.items()}

def top_label(tags, labels):
    return max(labels, key=lambda l: tags.get(l, 0.0))

def classify_inst(s):
    """Folder class + base name for a non-vocal source."""
    t, f, fam = s["tags"], s["feat"], s["fam"]
    b = f["bands"]
    drums = max(fam["KIT"], fam["PERC"])
    tonal = max(fam["GUITAR"], fam["BASS"], fam["KEYS"], fam["ORCH"])
    # hits, not notes (boomy kicks and toms read as harmonic, so a clear drum tag also counts)
    if (f["perc"] > 0.5 and drums >= 0.5 * tonal) or (drums > 0.4 and drums >= 1.5 * tonal):
        if fam["PERC"] > fam["KIT"]:
            lab = top_label(t, FAMILIES["PERC"])
            return "PERC", {"Tambourine": "TAMB", "Rattle (instrument)": "SHAKER",
                            "Maraca": "SHAKER", "Shaker": "SHAKER"}.get(lab, "PERC")
        if b[3] + b[4] > 0.75 and b[0] + b[1] < 0.1:
            hat = t.get("Hi-hat", 0) > max(t.get("Cymbal", 0), t.get("Crash cymbal", 0))
            return "CYM", "HAT" if hat else "CRASH"
        if b[0] > 0.5:                                       # the lowest resonance decides
            return ("KICK", "KICK") if f["lowpeak"] < 75 else ("TOM", "TOMS")
        if s["stereo"]:
            return "OH", "OH"
        if b[1] > 0.55 and b[4] < 0.25:                      # body, little cymbal bleed
            return ("SNARE", "SNARE") if f["lowpeak"] >= 150 else ("TOM", "TOMS")
        return "KIT", "KIT"
    if b[0] > 0.4 and f["perc"] < 0.5:
        return "BASS", "SYNTH BASS" if t.get("Synthesizer", 0) > t.get("Bass guitar", 0) else "BASS"
    if fam["GUITAR"] >= max(fam["KEYS"], fam["ORCH"]):
        ag = t.get("Acoustic guitar", 0) + 0.5 * t.get("Strum", 0)
        return "GTR", "AG" if ag > max(t.get("Electric guitar", 0), t.get("Distortion", 0)) else "EG"
    if fam["ORCH"] > 1.5 * max(fam["KEYS"], fam["GUITAR"]) and t.get("Synthesizer", 0) < 0.2:
        lab = top_label(t, FAMILIES["ORCH"])
        return "ORCH", ("STRINGS" if lab in ("String section", "Bowed string instrument", "Violin, fiddle",
                                             "Cello", "Orchestra") else "HORNS")
    lab = top_label(t, FAMILIES["KEYS"])
    name = {"Piano": "PIANO", "Electric piano": "EP", "Organ": "ORGAN", "Electronic organ": "ORGAN",
            "Hammond organ": "ORGAN"}.get(lab) if t.get(lab, 0) > 0.15 else None
    if name is None:
        name = "PAD" if f["onsets_per_s"] < 1.0 and f["fall"] > -70 else "SYNTH"
    return "KEYS", name

def confidence(s):
    """'check' when the tags barely separate two families (or barely fire at all)."""
    if s["cls"] in ("LV", "BGV", "VOXFX") or s["cls"] == "DEAD":
        return "ok"
    v = sorted(s["fam"].values(), reverse=True)
    return "check" if v[0] < 0.3 or v[0] - v[1] < 0.1 else "ok"

def _tail(act):
    """act extended forward by TAIL frames (where a return can still ring)."""
    c = np.concatenate([[0], np.cumsum(act.astype(np.int32))])
    i = np.arange(len(act))
    return (c[i + 1] - c[np.maximum(0, i - TAIL)]) > 0

def same_notes(a, b):
    """(chroma agreement, seconds) while both stems sing."""
    n = min(len(a["act"]), len(b["act"]), a["feat"]["chroma"].shape[1], b["feat"]["chroma"].shape[1])
    m = a["act"][:n] & b["act"][:n]
    if m.sum() < 150:
        return 0.0, m.sum() * HOP / SR
    ca = a["feat"]["chroma"][:, :n][:, m].astype(np.float32)
    cb = b["feat"]["chroma"][:, :n][:, m].astype(np.float32)
    sim = (ca * cb).sum(0) / (np.linalg.norm(ca, axis=0) * np.linalg.norm(cb, axis=0) + 1e-9)
    return float(np.mean(sim)), m.sum() * HOP / SR

def delayed_copy(s, dry):
    """(r, ms, stem): s's envelope repeats a dry stem 60 ms-1 s later (a delay throw)."""
    es, best = smooth_db(s["feat"]["env"], 3), (0.0, 0, None)
    for o in dry:
        if o is s:
            continue
        ed = smooth_db(o["feat"]["env"], 3)
        idx = np.where(s["act"][: min(len(es), len(ed))])[0]
        idx = idx[idx >= 50]
        if len(idx) < 25 or es[idx].std() < 1e-6:
            continue
        rs = []
        for k in range(50):
            y = ed[idx - k]
            rs.append(0.0 if y.std() < 1e-6 else float(np.corrcoef(es[idx], y)[0, 1]))
        k = int(np.argmax(rs[3:])) + 3
        if rs[k] > best[0] and rs[k] > rs[0] + 0.2:
            best = (rs[k], k * HOP * 1000 // SR, o)
    return best

def classify_vocals(voc):
    """Returns the dry vocal stems (what an FX return or a delay throw can follow)."""
    fx = [s for s in voc if s["feat"]["fall"] > WET_FALL]
    dry = [s for s in voc if s not in fx]
    # a stereo vocal that sounds for a few seconds, alone, is an FX moment, not a part
    moments = []
    for s in dry:
        others = [o["act"] for o in dry if o is not s]
        busy = np.any(others, axis=0) if others else np.zeros(len(s["act"]), bool)
        alone = (s["act"] & ~busy).sum() / max(1, s["act"].sum())
        if s["stereo"] and s["wcorr"] < 0.9 and s["act"].sum() * HOP / SR < 10 and alone > 0.7:
            moments.append(s)
    for s in moments:
        dry.remove(s)
        s["cls"], s["base"] = "VOXFX", "VOX FX"
        s["why"] = f"stereo vocal, {s['act'].sum() * HOP / SR:.0f}s total, nothing else singing"
    # lines: stems singing the same notes at the same time (lead + doubles, or a harmony stack)
    parent = list(range(len(dry)))
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i in range(len(dry)):
        for j in range(i + 1, len(dry)):
            sim, sec = same_notes(dry[i], dry[j])
            if sim >= 0.85:
                parent[root(j)] = root(i)
    lines = {}
    for i, s in enumerate(dry):
        lines.setdefault(root(i), []).append(s)
    lines = list(lines.values())
    # a stem that mostly sings alone is the lead in those bars
    solo = []
    for s in dry:
        others = [o["act"] for o in dry if o is not s]
        busy = np.any(others, axis=0) if others else np.zeros(len(s["act"]), bool)
        if (s["act"] & ~busy).sum() / max(1, s["act"].sum()) > 0.7:
            solo.append(s)
    cover = [np.any([o["act"] for o in ln], axis=0).sum() for ln in lines]
    lead = int(np.argmax(cover)) if lines else -1
    for i, ln in enumerate(lines):
        for s in ln:
            if i == lead or s in solo:
                s["cls"], s["base"] = "LV", "LV"
                s["why"] = "sings alone in its bars" if s in solo and i != lead else \
                    f"lead line ({len(ln)} stems on the same notes)"
            else:
                s["cls"], s["base"] = "BGV", "BGV"
                s["why"] = f"harmony line ({len(ln)} stem(s)), different notes from the lead"
    # FX returns: ring on one dry stem (its VERB) or throw on a few words (VOCALS)
    for s in fx:
        best, bc, bp = None, 0.0, 0.0
        for o in dry:
            n = min(len(o["act"]), len(s["act"]))
            oa, sa = o["act"][:n], s["act"][:n]
            cov = (oa & sa).sum() / max(1, oa.sum())
            prec = (sa & _tail(oa)).sum() / max(1, sa.sum())
            if cov * prec > bc * bp:
                best, bc, bp = o, cov, prec
        if best is not None and bc > 0.5 and bp > 0.6:
            s["cls"], s["base"] = best["cls"], best["cls"] + " VERB"
            s["why"] = f"wet (falls {s['feat']['fall']:.0f} dB/s), rings on {bc:.0%} of a {best['cls']} stem"
        else:
            s["cls"], s["base"] = "VOXFX", "VOX FX"
            s["why"] = f"wet (falls {s['feat']['fall']:.0f} dB/s), throws on {bc:.0%} of its best dry stem"
    return dry

def name_sources(sources):
    groups = {}
    for s in sources:
        groups.setdefault(s["base"], []).append(s)
    for base, ss in groups.items():
        ss.sort(key=lambda s: int(np.argmax(s["act"])) if s["act"].any() else 0)
        for i, s in enumerate(ss):
            s["name"] = base if len(ss) == 1 else f"{base} {i + 1}"


# ---------- driver -------------------------------------------------------------

def analyze(root, blind=False, log=print):
    paths = stem_paths(root)
    F = {}
    for i, p in enumerate(paths):
        def work(p=p):
            ch = load_16k(p)
            f = combine([features(x) for x in ch])
            f["nch"] = len(ch)
            if len(ch) == 2 and not f.get("silent"):
                f["wcorr"] = wave_corr(ch[0], ch[1], active(f["env"]))
            return f
        F[p] = cached("feat2", [p], work)
        log(f"[{i + 1}/{len(paths)}] {os.path.basename(p)}")
    pairs, how = [], {}
    if not blind:
        for a, b in suffix_pairs([p for p in paths if F[p]["nch"] == 1]):
            pairs.append((a, b))
            how[(a, b)] = "suffix"
    left = [p for p in paths if not any(p in pr for pr in pairs)]
    for a, b in audio_pairs(left, F):
        pairs.append((a, b))
        how[(a, b)] = "audio"
    paired = {p for pr in pairs for p in pr}
    sources = [{"files": [a, b], "feat": combine([F[a], F[b]]), "paired_by": how[(a, b)]}
               for a, b in pairs]
    sources += [{"files": [p], "feat": F[p]} for p in paths if p not in paired]
    for k, s in enumerate(sources):
        f = s["feat"]
        if f.get("silent"):
            s.update(cls="DEAD", base="DEAD", kind="dead", tags={}, stereo=False, wcorr=1.0,
                     act=np.zeros(len(f["env"]), bool), why="no signal above -75 dBFS")
            continue
        s["act"] = active(f["env"])

        def work(s=s):
            ch = [c for p in s["files"] for c in load_16k(p)]
            n = min(len(c) for c in ch)
            w = wave_corr(ch[0], ch[1], s["act"]) if len(ch) == 2 else 1.0
            mid = np.mean([c[:n] for c in ch], axis=0) if len(ch) > 1 else ch[0]
            return {"wcorr": w, "tags": ast_tags(mid, s["act"])}
        r = cached("ast2", s["files"], work)
        s["tags"], s["wcorr"] = r["tags"], r["wcorr"]
        nch = sum(F[p]["nch"] for p in s["files"])
        s["stereo"] = nch == 2 and s["wcorr"] < 0.995
        s["kind"] = "mono" if nch == 1 else ("stereo" if s["stereo"] else "dual-mono")
        if s.get("paired_by") == "audio" and s["stereo"]:
            s["kind"] = "stereo?"                       # could be a tight double; confirm
        s["fam"] = fam_scores(s["tags"])
        log(f"tagged {k + 1}/{len(sources)}")
    L = max(len(s["act"]) for s in sources)                # stems of different lengths line up at 0
    for s in sources:
        s["act"] = np.pad(s["act"], (0, L - len(s["act"])))
    live = [s for s in sources if s["kind"] != "dead"]
    voc = [s for s in live if s["fam"]["VOX"] > 0.25 and s["fam"]["VOX"] >= 0.6 * max(s["fam"].values())]
    for s in live:
        if s not in voc:
            s["cls"], s["base"] = classify_inst(s)
            s["why"] = ""
    dry = classify_vocals(voc)
    for s in live:                                   # delay throws, however the tagger heard them
        if s in dry or s["cls"] in ("LV", "BGV"):
            continue
        r, ms, o = delayed_copy(s, dry)
        if r > 0.7:
            s["cls"], s["base"] = "VOXFX", "VOX FX"
            s["why"] = f"repeats a {o['cls']} stem {ms} ms later (r={r:.2f})"
    name_sources(sources)
    for s in sources:
        s["folder"] = FOLDER[s["cls"]]
        s["conf"] = confidence(s)
        if s["kind"] == "stereo?":
            s["conf"] = "check"
        top = sorted(s["tags"].items(), key=lambda kv: -kv[1])
        s["top"] = [(l, round(p, 2)) for l, p in top if l not in ("Music", "Musical instrument")][:4]
    return sources


def _norm_folder(f):
    return re.sub(r"( GROUP| GRP|\.\d+)$", "", f.strip().upper())

def _base(p):
    b = os.path.splitext(os.path.basename(p))[0]
    m = SUFFIX.match(b)
    b = m.group(1) if m else b
    return re.sub(r"_\d+$", "", b).strip()

def score(sources, truth_path):
    T = {b.strip(): folder for folder, bases in json.load(open(truth_path)).items() for b in bases}
    rows = []
    for s in sources:
        want = T.get(_base(s["files"][0]))
        rows.append((want is not None and _norm_folder(want) == _norm_folder(s["folder"]), s, want))
    truth_pairs = {frozenset(pr) for pr in suffix_pairs([p for s in sources for p in s["files"]])}
    got_pairs = {frozenset(s["files"]) for s in sources if len(s["files"]) == 2}
    return rows, truth_pairs, got_pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    ap.add_argument("--truth")
    ap.add_argument("--blind", action="store_true", help="ignore channel suffixes; pair by audio only")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    log = (lambda *_: None) if a.quiet else (lambda m: print(m, file=sys.stderr, flush=True))
    sources = analyze(a.root, blind=a.blind, log=log)
    order = list(dict.fromkeys(FOLDER.values()))
    sources.sort(key=lambda s: (order.index(s["folder"]), s["name"]))
    print(f"{len(sources)} sources from {sum(len(s['files']) for s in sources)} files")
    for s in sources:
        files = " + ".join(os.path.basename(p) for p in s["files"])
        print(f"{s['folder']:<13} {s['name']:<11} {s['kind']:<9} {s['conf']:<5} {files}")
        if a.debug and not s["feat"].get("silent"):
            f = s["feat"]
            print(f"    bands={[round(float(x), 2) for x in f['bands']]} perc={f['perc']:.2f} "
                  f"low={f['lowpeak']:.0f}Hz fall={f['fall']:.0f} lvl={f['level_db']:.0f} "
                  f"act={s['act'].mean():.2f} wcorr={s['wcorr']:.2f} {s.get('why', '')}")
            print(f"    {s['top']}")
    if a.truth:
        rows, tp, gp = score(sources, a.truth)
        print(f"\nfolder match {sum(r[0] for r in rows)}/{len(rows)}; L/R pairs {len(tp & gp)}/{len(tp)}, "
              f"false pairs {len(gp - tp)}")
        for hit, s, want in rows:
            if not hit:
                print(f"  MISS {' + '.join(os.path.basename(p) for p in s['files'])}: "
                      f"said {s['folder']} ({s['name']}), map says {want}")
        for pr in gp - tp:
            print("  FALSE PAIR", " + ".join(os.path.basename(p) for p in pr))
        for pr in tp - gp:
            print("  MISSED PAIR", " + ".join(os.path.basename(p) for p in pr))
    if a.json:
        json.dump([{"files": s["files"], "kind": s["kind"], "folder": s["folder"], "name": s["name"],
                    "conf": s["conf"], "why": s.get("why", ""), "tags": s["top"]} for s in sources],
                  open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
