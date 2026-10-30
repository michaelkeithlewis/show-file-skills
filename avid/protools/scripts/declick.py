"""declick.py IN OUT T [--half 72] [--exact] : AR-interpolate a short window around the biggest HF transient near T seconds.
--exact repairs at sample round(T*sr) with no search (use it to fix the same click in a second print where it is masked)."""
import sys, shutil, numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt
EXACT = "--exact" in sys.argv; sys.argv = [x for x in sys.argv if x != "--exact"]
src, dst, T = sys.argv[1], sys.argv[2], float(sys.argv[3]); HALF = int(sys.argv[4]) if len(sys.argv) > 4 else 72
info = sf.info(src); y, sr = sf.read(src, dtype="float64", always_2d=True)
sos = butter(4, 8000, "hp", fs=sr, output="sos")
a = int((T - 0.08) * sr); seg = y[a:a + int(0.16 * sr)].mean(1)
env = np.convolve(np.abs(sosfilt(sos, seg)), np.ones(24) / 24, "same")
k = int(round(T * sr)) if EXACT else a + 4800 // 4 + int(np.argmax(env[1200:-1200]))
def ar_fit(x, p):
    X = np.stack([x[i:len(x) - p + i] for i in range(p)], 1); yv = x[p:]
    return np.linalg.lstsq(X, yv, rcond=None)[0]
def predict(hist, coef, n):
    h = list(hist[-len(coef):]); out = []
    for _ in range(n):
        v = float(np.dot(coef, h[-len(coef):])); out.append(v); h.append(v)
    return np.array(out)
P, CTX = 48, 2048; g0, g1 = k - HALF, k + HALF; n = g1 - g0
w = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n))
for ch in range(y.shape[1]):
    x = y[:, ch]
    fwd = predict(x[g0 - CTX:g0], ar_fit(x[g0 - CTX:g0], P), n)
    rev = x[g1:g1 + CTX][::-1]; bwd = predict(rev, ar_fit(rev, P), n)[::-1]
    x[g0:g1] = (1 - w) * fwd + w * bwd
sf.write(dst, y, sr, subtype=info.subtype)
print(f"repaired {2*HALF} samples ({2*HALF/sr*1000:.1f} ms) at {k/sr:.5f} s, subtype {info.subtype}")
