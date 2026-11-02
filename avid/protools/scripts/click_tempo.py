#!/usr/bin/env python3
"""click_tempo.py <click stem> [--trim-to-bar N]: read tempo, meter and bar 1 off the click itself.

The click is the timing authority. Kick/snare onset guessing (detect_click_grid) is a
fallback for drops that have no click stem; it lands on octave and triplet relatives.

It peak-picks every click (rising edge over 0.25 x peak, 120 ms debounce), takes the
median inter-click interval as the click value, and reads the accent pattern from the
click's brightness (zero-crossing rate over 30 ms): the accented click is the downbeat,
and the count between accents is the beats per bar. Gaps over 1.5 clicks split it into
click regions (a song can pause its click).

Prints JSON: click_bpm, beats_per_bar, meter guess, bar_secs, first_downbeat_secs,
pt_tempo (quarter-note BPM for set_tempo.py), regions, and with --trim-to-bar N the
sample to cut the stems at so the first downbeat lands on bar N+1 with N bars of pre-roll.

"""
import argparse, json
import numpy as np
import soundfile as sf


def read_click(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(1)
    e = np.abs(x)
    thr = 0.25 * e.max()
    idx = np.flatnonzero(e > thr)
    onsets, last = [], -10**12
    deb = int(0.12 * sr)
    for i in idx:
        if i - last > deb:
            j = i
            while j > 0 and e[j - 1] > 0.02 * e.max() and i - j < int(0.01 * sr):
                j -= 1
            onsets.append(j)
        last = i
    return x, sr, np.array(onsets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("click")
    ap.add_argument("--trim-to-bar", type=int, default=None,
                    help="bars of pre-roll before the first downbeat when re-cutting stems")
    a = ap.parse_args()
    x, sr, on = read_click(a.click)
    if len(on) < 8:
        raise SystemExit(json.dumps({"error": f"only {len(on)} clicks found"}))
    d = np.diff(on)
    ioi = float(np.median(d[(d > 0.2 * sr) & (d < 2 * sr)]))
    bpm = 60.0 * sr / ioi

    regions, s = [], 0
    for k in np.flatnonzero(d > 1.5 * ioi):
        regions.append((on[s], on[k])); s = k + 1
    regions.append((on[s], on[-1]))

    w = int(0.03 * sr)
    zc = np.array([np.mean(np.abs(np.diff(np.sign(x[o:o + w])))) for o in on])
    pk = np.array([np.abs(x[o:o + w]).max() for o in on])
    feat = zc if np.ptp(zc) > 0.1 * zc.max() else pk
    hi = feat > (feat.min() + feat.max()) / 2
    acc = np.flatnonzero(hi)
    if 1 < len(acc) < len(on):
        gaps = np.diff(acc)
        bpb = int(np.bincount(gaps).argmax())
        first_down = int(on[acc[0]])
    else:
        bpb, first_down = None, int(on[0])

    meter = {3: "3/4", 4: "4/4", 6: "6/8", 12: "12/8", 2: "2/4", 5: "5/4", 7: "7/8"}.get(bpb)
    pt_tempo = bpm / 2 if meter and meter.endswith("/8") else bpm
    bar = (bpb or 4) * ioi
    out = {"click_bpm": round(bpm, 3), "clicks": int(len(on)), "beats_per_bar": bpb,
           "meter": meter, "pt_tempo": round(pt_tempo, 3), "bar_secs": round(bar / sr, 4),
           "first_downbeat_secs": round(first_down / sr, 4), "first_downbeat_sample": first_down,
           "regions_secs": [(round(r0 / sr, 2), round(r1 / sr, 2)) for r0, r1 in regions]}
    if a.trim_to_bar is not None:
        out["cut_at_sample"] = int(first_down - round(a.trim_to_bar * bar))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
