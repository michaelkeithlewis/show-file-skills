"""snapscan.py FILE...: find sub-ms discontinuities (Brauer-style snaps): an isolated HF burst >20 dB over its 300 ms
neighborhood whose HF width is under 0.3 ms and whose sample step is >12x the local median step."""
import sys, numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt
from scipy.ndimage import median_filter, maximum_filter1d
for path in sys.argv[1:]:
    y, sr = sf.read(path, always_2d=True); m = y.mean(1)
    hp = np.abs(sosfilt(butter(4, 9000, "hp", fs=sr, output="sos"), m))
    w = sr // 1000; n = len(hp) // w; env = hp[:n * w].reshape(n, w).max(1)
    ratio = 20 * np.log10((env + 1e-12) / (median_filter(env, size=301) + 1e-9))
    cand = np.nonzero((ratio == maximum_filter1d(ratio, 201)) & (ratio > 20) & (20 * np.log10(env + 1e-12) > -60))[0]
    hits = []
    for c in cand:
        a = c * w - 480; b = c * w + 480 + w
        if a < 0 or b > len(m): continue
        seg = hp[a:b]; width = (seg > seg.max() / 4).sum() / sr * 1000
        d = np.abs(np.diff(m[a:b])); step = d.max() / (np.median(d) + 1e-12)
        if width < 0.3 and step > 12: hits.append(f"{(a + int(np.argmax(d))) / sr:.6f}(+{ratio[c]:.0f}dB,{step:.0f}x)")
    print(f"{path.rsplit('/', 1)[-1]}: {' '.join(hits) if hits else 'clean'}", flush=True)
