"""ref_align.py SONG_DIR [SONG_DIR ...] [--ref-glob "*eference*.wav"] [--stems-sub MULTITRACKS]
Where does the reference mix start against the stems (Pro Tools time 0)? Sums the first two minutes
of every stem, correlates an onset envelope of that sum with the reference's, and prints the offset.
Use it before spotting the reference on a track or loading it into Metric AB (metricab_ref.py).

Each SONG_DIR holds the reference (default: a WAV whose name contains "eference") and the stems
(default: a MULTITRACKS subfolder, searched recursively for WAV/AIFF). A corr under about 0.3 means
the match is weak; check by ear."""
import argparse, glob, os, sys
import numpy as np, soundfile as sf
from scipy.signal import resample_poly, fftconvolve
SR = 4000; SECS = 120
def load(f):
    i = sf.info(f); n = min(i.frames, int(SECS * i.samplerate))
    y, sr = sf.read(f, frames=n, dtype="float32", always_2d=True)
    return resample_poly(y.mean(1), SR, sr)
def env(y):
    y = np.abs(y); k = int(SR * 0.01); y = np.convolve(y, np.ones(k) / k, "same")
    d = np.diff(y, prepend=y[0]); return np.maximum(d, 0)
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("songs", nargs="+"); ap.add_argument("--ref-glob", default="*eference*.wav")
ap.add_argument("--stems-sub", default="MULTITRACKS")
a = ap.parse_args()
for song in a.songs:
    name = os.path.basename(os.path.normpath(song))
    refs = glob.glob(os.path.join(song, a.ref_glob))
    if not refs: print(name, "NO REFERENCE"); continue
    sd = os.path.join(song, a.stems_sub)
    stems = [f for ext in ("aif*", "wav") for f in glob.glob(os.path.join(sd, "**", "*." + ext), recursive=True)
             if not os.path.basename(f).startswith("._")]
    if not stems: print(name, "NO STEMS in", sd); continue
    mix = None
    for f in stems:
        y = load(f); mix = y if mix is None else (np.pad(mix, (0, max(0, len(y) - len(mix)))) + np.pad(y, (0, max(0, len(mix) - len(y)))))
    r = load(refs[0]); x, b = env(mix), env(r)
    c = fftconvolve(b, x[::-1], "full"); lag = np.argmax(c) - (len(x) - 1)
    peak = c.max() / (np.linalg.norm(x) * np.linalg.norm(b) + 1e-9)
    print(f"{name}: reference starts {lag / SR * 1000:+.1f} ms vs PT 0 (positive = ref is late)  corr={peak:.2f}  ref={os.path.basename(refs[0])}  stems={len(stems)}", flush=True)
