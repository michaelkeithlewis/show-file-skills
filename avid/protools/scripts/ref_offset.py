"""ref_offset.py REF.wav MIX.wav [--write] : where a client reference sits against the session (PT 0).

MIX is audio in session time: a summed stem render (session_map.py writes mix.wav) or any bounce from 0.
Prints OFFSET <ms> (negative = the reference starts that far INTO the song, so pad it) and AGREE (share of
10 s windows that hold at that offset; under 0.8 means a different edit, so do not sync it).
A single whole-song cross-correlation peak lies on repetitive songs: on a 60 BPM song it said -6991 ms
and the windows scattered from -11976 to +6. So the top whole-song peaks are candidates, the 10 s windows
vote, a mel-spectrogram match breaks the +/-1 beat tie (grooves repeat every beat, chords do not), and the
winner is refined to ~0.1 ms. --write saves '<ref> ALIGNED.wav' next to the original (padded or trimmed,
same rate and sample format); the client's file is never touched."""
import sys, os, numpy as np, soundfile as sf
from scipy.signal import resample_poly, fftconvolve, find_peaks
def load(f, sr):
    y, s = sf.read(f, dtype="float32", always_2d=True); return resample_poly(y.mean(1), sr, s)
def env(y, sr, ms):
    y = np.abs(y); k = max(1, int(sr * ms / 1000)); y = np.convolve(y, np.ones(k) / k, "same"); return np.maximum(np.diff(y, prepend=y[0]), 0)
SR = 2000
ref, mix = env(load(sys.argv[1], SR), SR, 10), env(load(sys.argv[2], SR), SR, 10)
c = fftconvolve(ref, mix[::-1], "full"); lags = np.arange(len(c)) - (len(mix) - 1)
pk, _ = find_peaks(c, distance=SR // 2); top = pk[np.argsort(c[pk])[::-1][:8]]
W = 10 * SR
def windows(L, slack=0.05):
    out = []
    for i in range(0, len(mix) - W, W):
        a = mix[i:i + W]
        if np.linalg.norm(a) < 1e-6: continue
        best = (-1, 0)
        for d in range(-int(slack * SR), int(slack * SR) + 1):
            j = i + L + d
            if j < 0 or j + W > len(ref): continue
            b = ref[j:j + W]; v = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
            if v > best[0]: best = (v, d)
        if best[0] > -1: out.append(best)
    return out
cands = []
for p in top:
    L = int(lags[p]); w = windows(L); good = [x for x in w if x[0] > 0.3]
    cands.append((len(good) / max(1, len(w)), float(np.median([x[0] for x in w])) if w else 0, L, w))
import librosa
MS = 8000; HOP = 160
def mel(f):
    y = load(f, MS); return librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=MS, n_fft=1024, hop_length=HOP, n_mels=40))
Mr, Mm = mel(sys.argv[1]), mel(sys.argv[2])
def melscore(L):
    k = int(round(L / SR * MS / HOP)); a = Mm[:, max(0, -k):]; b = Mr[:, max(0, k):]; n = min(a.shape[1], b.shape[1])
    a, b = a[:, :n] - a[:, :n].mean(0), b[:, :n] - b[:, :n].mean(0)
    return float(np.mean(np.sum(a * b, 0) / (np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9)))
cands = [c + (melscore(c[2]),) for c in cands if c[0] >= 0.5] or [c + (melscore(c[2]),) for c in cands]
cands.sort(key=lambda x: x[4], reverse=True)
agree, med, L, w, ms = cands[0]
FS = 8000; r8, m8 = env(load(sys.argv[1], FS), FS, 4), env(load(sys.argv[2], FS), FS, 4); L8 = L * FS // SR
cs = []
for d in range(-int(0.12 * FS), int(0.12 * FS) + 1):
    lag = L8 + d; a = m8[max(0, -lag):]; b = r8[max(0, lag):]; n = min(len(a), len(b))
    cs.append(float(np.dot(a[:n], b[:n]) / (np.linalg.norm(a[:n]) * np.linalg.norm(b[:n]) + 1e-9)))
cs = np.array(cs); k = int(np.argmax(cs))
sub = (cs[k - 1] - cs[k + 1]) / (2 * (cs[k - 1] - 2 * cs[k] + cs[k + 1])) if 0 < k < len(cs) - 1 else 0
off = (L8 + k - int(0.12 * FS) + sub) / FS * 1000
spread = [round(d / SR * 1000) for v, d in w if v > 0.3]
print(f"OFFSET {off:+.2f} AGREE {agree:.2f} mel {ms:.3f} median_corr {med:.2f} windows {len(w)} spread_ms {min(spread, default=0)}..{max(spread, default=0)}")
print("  other candidates:", [(round(x[2] / SR * 1000), round(x[0], 2), round(x[4], 3)) for x in cands[1:4]])

if "--write" in sys.argv and abs(off) > 5 and agree >= 0.8:
    i = sf.info(sys.argv[1]); y, sr = sf.read(sys.argv[1], dtype="float32", always_2d=True)
    n = int(round(abs(off) / 1000 * sr))
    y = np.vstack([np.zeros((n, y.shape[1]), np.float32), y]) if off < 0 else y[n:]
    out = os.path.splitext(sys.argv[1])[0] + " ALIGNED.wav"
    sf.write(out, y, sr, subtype=i.subtype)
    print("WROTE", out, ("padded" if off < 0 else "trimmed"), n, "samples")
