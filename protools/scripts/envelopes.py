#!/usr/bin/env python3
"""envelopes.py - per-second RMS envelope for a set of stems, as JSON.

Use it to read a long multitrack with no click (a live capture, a service, a
podcast) before placing markers: which stems are active when tells you where
songs, talk and quiet sections are. Reads each whole file block-wise.

    envelopes.py <stems dir> [file ...] [--win 1.0] [--out envs.json]

With no file names, every WAV/AIFF/FLAC in the folder (recursive) is read.
Output: {"<file>": [rms per window, ...], ...}. Convert to dB with 20*log10(x).
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

AUDIO_EXT = (".wav", ".aif", ".aiff", ".flac")


def env(path, win=1.0):
    out = []
    with sf.SoundFile(path) as f:
        n = int(f.samplerate * win)
        while True:
            b = f.read(n, dtype="float32", always_2d=True)
            if len(b) == 0:
                break
            out.append(float(np.sqrt(np.mean(b.astype(np.float64) ** 2))))
    return out


def main():
    ap = argparse.ArgumentParser(prog="envelopes", description=__doc__.splitlines()[0])
    ap.add_argument("stems_dir")
    ap.add_argument("files", nargs="*", help="file names relative to stems_dir (default: all)")
    ap.add_argument("--win", type=float, default=1.0, help="window length in seconds")
    ap.add_argument("--out", default="envs.json")
    a = ap.parse_args()
    names = a.files
    if not names:
        names = sorted(os.path.relpath(os.path.join(dp, f), a.stems_dir)
                       for dp, _, fs in os.walk(a.stems_dir) for f in fs
                       if f.lower().endswith(AUDIO_EXT) and not f.startswith("._"))
    res = {}
    for name in names:
        res[name] = env(os.path.join(a.stems_dir, name), a.win)
        print("done", name, file=sys.stderr, flush=True)
    with open(a.out, "w") as fh:
        json.dump(res, fh)
    print("wrote", a.out, {k: len(v) for k, v in res.items()})


if __name__ == "__main__":
    main()
