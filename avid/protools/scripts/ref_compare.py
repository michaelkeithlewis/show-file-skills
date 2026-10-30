#!/usr/bin/env python3
"""Compare a unity-gain stem sum against a reference mix.

Deliberately does NOT try to invert the mix for per-group fader values. Groups
overlap spectrally and the reference is compressed and limited, so a least-squares
fit is unstable: it happily returns "-79 dB on the cymbals". What IS reliable is
(a) how far off the overall level is, (b) how the tonal balance differs band by
band, and (c) which group dominates each band, which is what turns (b) into a move.

    ref_compare.py <stems_dir> <reference.wav> [--json report.json]

Groups come from the drop's own subfolders (DRUMS/, BASS/, ...). Files inside a
folder whose name starts with DRUM are split into KICK / SNARE / TOMS / CYMS by
filename. Loose files at the top level are grouped by a filename keyword. The
reference must be a WAV/AIFF/FLAC that soundfile/librosa can read (convert
.m4a/.mp3 first, for example with ffmpeg).
"""
import os, sys, json, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, librosa

BANDS = [(20, 60, "sub"), (60, 120, "low"), (120, 250, "low-mid"),
         (250, 500, "mid"), (500, 1000, "upper-mid"), (1000, 2000, "presence"),
         (2000, 4000, "edge"), (4000, 8000, "air"), (8000, 16000, "top")]


KEYWORDS = [("kick", "KICK"), ("snare", "SNARE"), ("snr", "SNARE"), ("tom", "TOMS"),
            ("oh", "CYMS"), ("hat", "CYMS"), ("ride", "CYMS"), ("perc", "PERC"),
            ("bass", "BASS"), ("gtr", "GUITAR"), ("guitar", "GUITAR"), ("elec", "GUITAR"),
            ("acg", "GUITAR"), ("piano", "KEYS"), ("keys", "KEYS"), ("rhodes", "KEYS"),
            ("organ", "KEYS"), ("synth", "SYNTH"), ("pad", "SYNTH"), ("string", "ORCH"),
            ("bgv", "BGV"), ("vox", "VOX"), ("vocal", "VOX")]


def group_of(rel, name):
    """Group for one stem: its top-level subfolder, with drums split by name."""
    n = name.lower()
    top = rel.split(os.sep)[0].upper()
    if rel != "." and not top.startswith("DRUM"):
        sub = rel.split(os.sep)[-1].upper()
        return "PERC" if sub.startswith("PERC") else top
    if top.startswith("DRUM"):
        for kw, g in KEYWORDS[:7]:
            if kw in n:
                return g
        return "PERC" if "perc" in rel.lower() else "CYMS"
    for kw, g in KEYWORDS:
        if kw in n:
            return g
    return "OTHER"


def band_energy(y, sr):
    S = np.abs(librosa.stft(y, n_fft=8192, hop_length=4096)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=8192)
    out = {}
    for lo, hi, nm in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        out[nm] = float(S[m].sum())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems_dir"); ap.add_argument("reference")
    ap.add_argument("--json", help="write the numbers (trim, band diffs, group levels, moves) here")
    a = ap.parse_args()
    SR = 44100

    ref, _ = librosa.load(a.reference, sr=SR, mono=True)
    groups = {}
    for dp, _dn, fn in os.walk(a.stems_dir):
        rel = os.path.relpath(dp, a.stems_dir)
        for f in sorted(fn):
            if f.lower().endswith((".aif", ".aiff", ".wav")) and not f.startswith("._"):
                g = group_of(rel, f)
                y, _ = librosa.load(os.path.join(dp, f), sr=SR, mono=True)
                cur = groups.get(g)
                if cur is None or len(cur) < len(y):
                    cur = np.pad(cur if cur is not None else np.zeros(0), (0, len(y) - (len(cur) if cur is not None else 0)))
                if len(y) < len(cur):
                    y = np.pad(y, (0, len(cur) - len(y)))
                groups[g] = cur + y
    n = max(max(len(v) for v in groups.values()), len(ref))
    for g in groups:
        groups[g] = np.pad(groups[g], (0, n - len(groups[g])))
    ref = np.pad(ref, (0, n - len(ref)))
    total = sum(groups.values())

    rms = lambda y: 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
    pk = lambda y: 20 * np.log10(np.max(np.abs(y)) + 1e-12)
    print(f"unity sum : RMS {rms(total):6.1f} dB   peak {pk(total):6.1f} dB")
    print(f"reference : RMS {rms(ref):6.1f} dB   peak {pk(ref):6.1f} dB")
    trim = rms(ref) - rms(total)
    print(f"\nGLOBAL TRIM to match the reference: {trim:+.1f} dB")
    if pk(total) > 0:
        print(f"  (the unity sum peaks {pk(total):+.1f} dB - it is clipping the master as built)")

    bt, br = band_energy(total, SR), band_energy(ref, SR)
    tt, tr = sum(bt.values()), sum(br.values())
    print("\n--- tonal balance vs the reference (share of total energy) ---")
    print(f"{'band':11} {'stems':>8} {'ref':>8} {'diff':>8}")
    diffs = {}
    for lo, hi, nm in BANDS:
        a_ = 10 * np.log10(bt[nm] / tt + 1e-12)
        b_ = 10 * np.log10(br[nm] / tr + 1e-12)
        diffs[nm] = a_ - b_
        flag = "  <-- heavy" if a_ - b_ > 2 else ("  <-- light" if a_ - b_ < -2 else "")
        print(f"{nm:11} {a_:7.1f} {b_:7.1f} {a_-b_:+7.1f}{flag}")

    print("\n--- who owns each band in the stem sum (top 2 groups) ---")
    gb = {g: band_energy(y, SR) for g, y in groups.items()}
    for lo, hi, nm in BANDS:
        tot = sum(gb[g][nm] for g in gb) + 1e-12
        top = sorted(gb, key=lambda g: -gb[g][nm])[:2]
        share = ", ".join(f"{g} {100*gb[g][nm]/tot:.0f}%" for g in top)
        print(f"{nm:11} {share}{'   <-- ' + ('pull' if diffs[nm] > 2 else 'push') if abs(diffs[nm]) > 2 else ''}")

    off = [nm for lo, hi, nm in BANDS if abs(diffs[nm]) > 2]
    movers = []
    for nm in off:
        movers += sorted(gb, key=lambda g: -gb[g][nm])[:1]
    movers = list(dict.fromkeys(movers))[:3]
    if movers:
        target = {nm: 10 * np.log10(br[nm] / tr + 1e-12) for _lo, _hi, nm in BANDS}

        def score(trims):
            e = {}
            for _lo, _hi, nm in BANDS:
                v = sum(gb[g][nm] * (10 ** (trims.get(g, 0.0) / 10.0)) for g in gb)
                e[nm] = v
            t = sum(e.values()) + 1e-12
            return sum((10 * np.log10(e[nm] / t + 1e-12) - target[nm]) ** 2
                       for _lo, _hi, nm in BANDS)

        grid = np.arange(-12, 12.5, 0.5)
        best = {g: 0.0 for g in movers}
        for _ in range(6):
            for g in movers:
                cur = dict(best)
                vals = []
                for v in grid:
                    cur[g] = float(v)
                    vals.append((score(cur), float(v)))
                best[g] = min(vals)[1]
        print("\n--- suggested moves (constrained fit on the off bands) ---")
        for g in movers:
            print(f"{g:8} {best[g]:+6.1f} dB")
        print(f"band error {score({g: 0.0 for g in movers}):.1f} -> {score(best):.1f}")
        clamped = [g for g in movers if abs(best[g]) >= 12]
        if clamped:
            print(f"  (hit the +/-12 dB clamp: {', '.join(clamped)}; treat as a direction, not a value)")
    else:
        best = {}

    print("\n--- group levels at unity ---")
    for g in sorted(groups, key=lambda g: -rms(groups[g])):
        print(f"{g:8} {rms(groups[g]):6.1f} dB RMS")

    if a.json:
        json.dump({"global_trim_db": round(float(trim), 2),
                   "band_diff_db": {k: round(float(v), 2) for k, v in diffs.items()},
                   "group_rms_db": {g: round(float(rms(y)), 2) for g, y in groups.items()},
                   "suggested_moves_db": best},
                  open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
