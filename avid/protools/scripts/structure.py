#!/usr/bin/env python3
"""structure.py - song-structure labelling (verse/chorus/…) from stems.

Combines repetition-based segmentation (Laplacian spectral clustering of a
harmonic source, per the librosa method) with vocal-activity from the vocal
stem to name sections: Intro / Verse / Chorus / Bridge / Instrumental / Outro.

This is a heuristic ESTIMATE - repetition + vocal energy, not lyric understanding.
Always have a human sanity-check the result.

    .venv/bin/python scripts/structure.py PRIMARY.wav [--vocal VOCAL.wav] [--types 5]
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import librosa
import scipy.ndimage
import scipy.sparse
import scipy.linalg
import sklearn.cluster

BPO = 12 * 3
N_OCT = 7


def _segment_types(y, sr, n_types):
    """Return (beat_times, seg_id_per_beat) via Laplacian segmentation."""
    C = librosa.amplitude_to_db(
        np.abs(librosa.cqt(y=y, sr=sr, bins_per_octave=BPO, n_bins=N_OCT * BPO)),
        ref=np.max)
    _, beats = librosa.beat.beat_track(y=y, sr=sr, trim=False)
    beats = librosa.util.fix_frames(beats, x_min=0)
    Csync = librosa.util.sync(C, beats, aggregate=np.median)
    beat_times = librosa.frames_to_time(beats, sr=sr)
    if Csync.shape[1] < n_types + 2:
        return beat_times, np.zeros(Csync.shape[1], dtype=int)

    R = librosa.segment.recurrence_matrix(Csync, width=3, mode="affinity", sym=True)
    Rf = librosa.segment.timelag_filter(scipy.ndimage.median_filter)(R, size=(1, 7))
    mfcc = librosa.feature.mfcc(y=y, sr=sr)
    Msync = librosa.util.sync(mfcc, beats)
    dist = np.sum(np.diff(Msync, axis=1) ** 2, axis=0)
    sigma = np.median(dist) or 1.0
    sim = np.exp(-dist / sigma)
    R_path = np.diag(sim, k=1) + np.diag(sim, k=-1)
    dp, dr = R_path.sum(axis=1), Rf.sum(axis=1)
    denom = np.sum((dp + dr) ** 2) or 1.0
    mu = dp.dot(dp + dr) / denom
    A = mu * Rf + (1 - mu) * R_path

    L = scipy.sparse.csgraph.laplacian(A, normed=True)
    _, evecs = scipy.linalg.eigh(L)
    evecs = scipy.ndimage.median_filter(evecs, size=(9, 1))
    k = min(n_types, evecs.shape[1] - 1)
    Cnorm = np.cumsum(evecs ** 2, axis=1) ** 0.5
    Cnorm[Cnorm == 0] = 1.0
    X = evecs[:, :k] / Cnorm[:, k - 1: k]
    seg_ids = sklearn.cluster.KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
    return beat_times, seg_ids


def _contiguous(beat_times, seg_ids, total_dur):
    """Collapse per-beat ids into [start, end, type_id] spans."""
    spans, start_i = [], 0
    for i in range(1, len(seg_ids) + 1):
        if i == len(seg_ids) or seg_ids[i] != seg_ids[start_i]:
            a = float(beat_times[start_i])
            b = float(beat_times[i]) if i < len(seg_ids) else total_dur
            spans.append([a, b, int(seg_ids[start_i])])
            start_i = i
    return spans


def _merge_short(spans, min_dur=6.0):
    """Fold spans shorter than min_dur into the previous span."""
    out = []
    for s in spans:
        if out and (s[1] - s[0]) < min_dur:
            out[-1][1] = s[1]
        else:
            out.append(list(s))
    return out


def analyze_structure(primary_path, vocal_path=None, n_types=5):
    y, sr = librosa.load(primary_path, sr=None, mono=True)
    dur = len(y) / sr
    beat_times, seg_ids = _segment_types(y, sr, n_types)
    spans = _merge_short(_contiguous(beat_times, seg_ids, dur))

    if vocal_path:
        v, vsr = librosa.load(vocal_path, sr=None, mono=True)
        vrms = librosa.feature.rms(y=v)[0]
        vt = librosa.times_like(vrms, sr=vsr)
        vmax = float(vrms.max()) or 1.0
        def vocal_level(a, b):
            seg = vrms[(vt >= a) & (vt < b)]
            return float(seg.mean()) / vmax if len(seg) else 0.0
    else:
        def vocal_level(a, b):
            return None

    for s in spans:
        s.append(vocal_level(s[0], s[1]))

    labelled = _label(spans, dur, has_vocal=bool(vocal_path))
    return {
        "primary": primary_path,
        "vocal": vocal_path,
        "duration_sec": round(dur, 3),
        "method": "laplacian-segmentation + vocal-activity" if vocal_path
                  else "laplacian-segmentation (no vocal)",
        "sections": labelled,
    }


VOCAL_ON = 0.12


def _label(spans, dur, has_vocal):
    n = len(spans)
    by_type = {}
    for i, s in enumerate(spans):
        by_type.setdefault(s[2], []).append(i)

    type_vocal = {t: np.mean([spans[i][3] for i in idxs]) for t, idxs in by_type.items()} \
        if has_vocal else {}

    chorus_type = verse_type = None
    if has_vocal:
        recurring = {t: idxs for t, idxs in by_type.items()
                     if len(idxs) >= 2 and type_vocal[t] >= VOCAL_ON}
        if recurring:
            chorus_type = max(recurring, key=lambda t: type_vocal[t])
            rest = {t: idxs for t, idxs in recurring.items() if t != chorus_type}
            if rest:
                verse_type = max(rest, key=lambda t: len(rest[t]))

    based = []
    for i, s in enumerate(spans):
        a, b, t, vlev = s
        has_v = has_vocal and vlev is not None and vlev >= VOCAL_ON
        if has_vocal and not has_v:
            base = "Intro" if i == 0 else ("Outro" if i == n - 1 else "Instrumental")
        elif t == chorus_type:
            base = "Chorus"
        elif t == verse_type:
            base = "Verse"
        elif has_vocal and i >= n * 0.55 and len(by_type[t]) == 1:
            base = "Bridge"
        elif has_vocal:
            base = "Verse"
        else:
            base = "Section"
        based.append({"start": a, "end": b, "base": base,
                      "vocal": vlev, "type_id": t})

    merged = []
    for s in based:
        if merged and merged[-1]["base"] == s["base"]:
            merged[-1]["end"] = s["end"]
            if s["vocal"] is not None:
                merged[-1]["_v"].append(s["vocal"])
        else:
            s = dict(s); s["_v"] = [s["vocal"]] if s["vocal"] is not None else []
            merged.append(s)

    counts = {}
    for s in merged:
        counts[s["base"]] = counts.get(s["base"], 0) + 1
    seen, out = {}, []
    for i, s in enumerate(merged, 1):
        base = s["base"]
        if counts[base] > 1 and base not in ("Intro", "Outro", "Bridge"):
            seen[base] = seen.get(base, 0) + 1
            label = f"{base} {seen[base]}"
        else:
            label = base
        vmean = round(float(np.mean(s["_v"])), 2) if s["_v"] else None
        out.append({"index": i, "start": round(s["start"], 3),
                    "end": round(s["end"], 3), "label": label,
                    "vocal_level": vmean})
    return out


if __name__ == "__main__":
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument("primary")
    p.add_argument("--vocal")
    p.add_argument("--types", type=int, default=5)
    a = p.parse_args()
    print(json.dumps(analyze_structure(a.primary, a.vocal, a.types), indent=2))
