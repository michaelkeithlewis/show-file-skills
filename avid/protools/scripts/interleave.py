#!/usr/bin/env python3
"""interleave.py - join two mono files (L and R) into one interleaved stereo WAV.

PTSL has no "combine two monos into stereo" command. When a template has a stereo
track for a pair of mono stems (overheads L/R, keys L/R, crowd L/R), write one
stereo file and import that. Reads block-wise, so long files are fine. Never
re-bounce in Pro Tools for this.

    interleave.py L.wav R.wav out.wav [--subtype PCM_24]

Write out.wav into the session's "Audio Files" folder. The output length is the
shorter of the two inputs. Both inputs must share a sample rate.
"""
import argparse
import sys

import numpy as np
import soundfile as sf


def interleave(left, right, out, subtype="PCM_24", block=1 << 20):
    with sf.SoundFile(left) as l, sf.SoundFile(right) as r:
        if l.samplerate != r.samplerate:
            sys.exit(f"sample rates differ: {l.samplerate} vs {r.samplerate}")
        with sf.SoundFile(out, "w", samplerate=l.samplerate, channels=2, subtype=subtype) as o:
            while True:
                a = l.read(block, dtype="float64", always_2d=True)
                b = r.read(block, dtype="float64", always_2d=True)
                n = min(len(a), len(b))
                if n == 0:
                    break
                o.write(np.column_stack([a[:n, 0], b[:n, 0]]))
    return out


def main():
    ap = argparse.ArgumentParser(prog="interleave", description=__doc__.splitlines()[0])
    ap.add_argument("left")
    ap.add_argument("right")
    ap.add_argument("out")
    ap.add_argument("--subtype", default="PCM_24", help="soundfile subtype (PCM_24, PCM_16, FLOAT)")
    a = ap.parse_args()
    print("wrote", interleave(a.left, a.right, a.out, a.subtype))


if __name__ == "__main__":
    main()
