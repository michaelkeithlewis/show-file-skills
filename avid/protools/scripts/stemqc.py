#!/usr/bin/env python3
"""stemqc.py - read a stem drop before you build the session.

Two passes, both take the stems folder (recursive):

    stemqc.py levels <stems_dir>
        peak / RMS / % active per stem, quietest first. Catches dead stems, stems
        bounced at full scale, and stems that are present but barely play.

    stemqc.py arrangement <stems_dir> --bpm 110 [--groups-from-folders]
        per-group activity in BAR NUMBERS plus segmentation of the summed mix.
        This is the section map for an INSTRUMENTAL drop, where lyrics.py has no
        vocal to transcribe and structure.py sees one flat section.

See references/session-prep.md for where this fits in a prep.
"""
import argparse, json, os, warnings
warnings.filterwarnings("ignore")
import numpy as np


def stem_paths(root):
    out = []
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith((".wav", ".aif", ".aiff")) and not f.startswith("._"):
                out.append(os.path.join(dp, f))
    return sorted(out)


def levels(root):
    import soundfile as sf
    rows = []
    for p in stem_paths(root):
        y, _sr = sf.read(p, always_2d=True)
        pk = float(np.max(np.abs(y))) if y.size else 0.0
        rms = float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0
        act = float(np.mean(np.max(np.abs(y), axis=1) > 10 ** (-60 / 20))) if y.size else 0.0
        rows.append({"group": os.path.relpath(os.path.dirname(p), root),
                     "file": os.path.basename(p),
                     "peak_db": round(20 * np.log10(pk + 1e-12), 1),
                     "rms_db": round(20 * np.log10(rms + 1e-12), 1),
                     "active_pct": round(act * 100, 1)})
    rows.sort(key=lambda r: r["rms_db"])
    return rows


def arrangement(root, bpm, sr=22050, n_segments=10):
    import librosa
    bar = 4 * 60.0 / bpm
    hop = sr // 4
    paths = stem_paths(root)
    env, total = {}, None
    for p in paths:
        g = os.path.relpath(os.path.dirname(p), root)
        y, _ = librosa.load(p, sr=sr, mono=True)
        if total is None:
            total = np.zeros(len(y))
        n = min(len(y), len(total))
        total[:n] += y[:n]
        e = np.sqrt(np.array([np.mean(y[i:i + hop] ** 2) for i in range(0, len(y) - hop, hop)]))
        env.setdefault(g, []).append(e)
    dur = len(total) / sr

    spans, peaks = {}, {}
    for g, es in env.items():
        n = min(len(e) for e in es)
        m = np.sqrt(sum(e[:n] ** 2 for e in es))
        thr = max(m.max() * 0.06, 1e-5)
        act, t = m > thr, np.arange(n) * hop / sr
        runs, i = [], 0
        while i < n:
            if act[i]:
                j = i
                while j < n and act[j]:
                    j += 1
                if t[j - 1] - t[i] > 1.5:
                    runs.append([round(float(t[i]), 3), round(float(t[j - 1]), 3)])
                i = j
            else:
                i += 1
        spans[g] = runs
        peaks[g] = float(m.max())

    Sdb = librosa.power_to_db(librosa.feature.melspectrogram(y=total, sr=sr))
    bounds = [float(x) for x in librosa.frames_to_time(
        librosa.segment.agglomerative(Sdb, n_segments), sr=sr)]
    return {"bpm": bpm, "bar_sec": round(bar, 5), "duration_sec": round(dur, 3),
            "bars": round(dur / bar, 2), "spans": spans,
            "group_peak": {g: round(v, 6) for g, v in peaks.items()},
            "boundaries_sec": [round(b, 3) for b in bounds],
            "boundary_bars": sorted({int(round(b / bar)) + 1 for b in bounds})}


def main():
    ap = argparse.ArgumentParser(prog="stemqc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("levels"); s.add_argument("stems_dir"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("arrangement"); s.add_argument("stems_dir")
    s.add_argument("--bpm", type=float, required=True); s.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "levels":
        rows = levels(a.stems_dir)
        if a.json:
            print(json.dumps(rows, indent=1)); return
        line = "{group:24} {file:28} peak {peak_db:>7} rms {rms_db:>7} active {active_pct:>5}%"
        for r in rows:
            print(line.format(**r))
        dead = [r["file"] for r in rows if r["active_pct"] < 0.1]
        hot = [r["file"] for r in rows if r["peak_db"] >= -0.05]
        print("\nno audible content:", dead or "none")
        print("pinned at full scale:", hot or "none")
    else:
        res = arrangement(a.stems_dir, a.bpm)
        if a.json:
            print(json.dumps(res, indent=1)); return
        bar = res["bar_sec"]
        print(f"duration {res['duration_sec']}s  bar {bar}s  bars {res['bars']}")
        print("\n--- group activity (bar numbers, bar 1 = 0:00) ---")
        for g, runs in sorted(res["spans"].items()):
            pretty = ", ".join(f"b{int(round(x/bar))+1}-b{int(round(y/bar))+1}" for x, y in runs)
            if not pretty:
                pretty = ("(sparse hits only - run `levels` to see them)"
                          if res["group_peak"].get(g, 0) > 1e-4 else "(no audible content)")
            print(f"{g:24} {pretty}")
        print("\nsegmentation boundary bars:", res["boundary_bars"])


if __name__ == "__main__":
    main()
