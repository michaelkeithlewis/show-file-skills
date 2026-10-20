#!/usr/bin/env python3
"""analyze.py - audio analysis for Pro Tools track preparation.

Pure analysis, no Pro Tools dependency: give it an audio file, get back tempo,
key, beat/downbeat grid, and section boundaries as a JSON-able dict. ptprep.py
turns this into session markers.

    .venv/bin/python scripts/analyze.py FILE [--sections N]
"""
import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import librosa

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Schmuckler key profiles
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def detect_key(y, sr):
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    best = (-2.0, None)
    ranked = []
    for i in range(12):
        for prof, mode in ((_MAJ, "major"), (_MIN, "minor")):
            r = float(np.corrcoef(np.roll(prof, i), chroma)[0, 1])
            ranked.append((r, f"{NOTE_NAMES[i]} {mode}"))
            if r > best[0]:
                best = (r, f"{NOTE_NAMES[i]} {mode}")
    ranked.sort(reverse=True)
    return {"key": best[1], "confidence": round(best[0], 3),
            "alternates": [k for _, k in ranked[1:3]]}


def detect_tempo(y, sr):
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bpm = float(np.atleast_1d(tempo)[0])
    # half/double candidates - worship/acoustic material is often mis-octaved
    cands = sorted({round(bpm, 1), round(bpm / 2, 1), round(bpm * 2, 1)})
    return bpm, beats.tolist(), cands


def estimate_downbeats(y, sr, beats, beats_per_bar=4):
    """No true downbeat model without madmom; assume a fixed meter and anchor the
    bar on the strongest onset among the first `beats_per_bar` beats."""
    if len(beats) < beats_per_bar:
        return []
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.times_like(onset_env, sr=sr)
    strength = np.interp(beats[:beats_per_bar], times, onset_env)
    phase = int(np.argmax(strength))
    return [beats[i] for i in range(phase, len(beats), beats_per_bar)]


def detect_sections(y, sr, n_sections):
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    bounds = librosa.segment.agglomerative(mfcc, n_sections)
    btimes = librosa.frames_to_time(bounds, sr=sr)
    dur = len(y) / sr
    edges = sorted(set([0.0] + [float(t) for t in btimes] + [dur]))
    # label by relative RMS energy of each span (quiet / mid / full)
    rms = librosa.feature.rms(y=y)[0]
    rms_t = librosa.times_like(rms, sr=sr)
    sections = []
    spans = list(zip(edges[:-1], edges[1:]))
    energies = []
    for a, b in spans:
        seg = rms[(rms_t >= a) & (rms_t < b)]
        energies.append(float(seg.mean()) if len(seg) else 0.0)
    if energies:
        lo, hi = min(energies), max(energies)
        rng = (hi - lo) or 1.0
        for i, ((a, b), e) in enumerate(zip(spans, energies), 1):
            rel = (e - lo) / rng
            tier = "full" if rel > 0.66 else "mid" if rel > 0.33 else "quiet"
            sections.append({"index": i, "start": round(a, 3), "end": round(b, 3),
                             "label": f"Section {i} ({tier})", "energy": round(rel, 2)})
    return sections


def analyze_file(path, n_sections=8, beats_per_bar=4):
    y, sr = librosa.load(path, sr=None, mono=True)
    bpm, beats, tempo_cands = detect_tempo(y, sr)
    downbeats = estimate_downbeats(y, sr, beats, beats_per_bar)
    return {
        "file": path,
        "sample_rate": sr,
        "duration_sec": round(len(y) / sr, 3),
        "tempo_bpm": round(bpm, 2),
        "tempo_candidates": tempo_cands,
        "beats_per_bar_assumed": beats_per_bar,
        "key": detect_key(y, sr),
        "beats": [round(t, 4) for t in beats],
        "downbeats": [round(t, 4) for t in downbeats],
        "sections": detect_sections(y, sr, n_sections),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Analyze an audio file for tempo/key/sections")
    p.add_argument("file")
    p.add_argument("--sections", type=int, default=8, help="number of sections to find")
    p.add_argument("--beats-per-bar", type=int, default=4)
    p.add_argument("--no-beats", action="store_true", help="omit the full beat list from output")
    args = p.parse_args(argv)
    result = analyze_file(args.file, args.sections, args.beats_per_bar)
    if args.no_beats:
        result["beats"] = f"<{len(result['beats'])} beats omitted>"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
