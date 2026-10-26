"""tx_regions.py STEMS_DIR REGIONS.json [--out DIR]
Transcribe chosen stretches of a long multitrack (a live service, a conference, a podcast) so you can
name and mark its sections. For each region, the listed stems are summed, normalized and resampled to
16 kHz, then run through Whisper (lyrics.transcribe). Pick the regions from envelopes.py first.

REGIONS.json is a list of [name, start_sec, end_sec, [stem files], whisper_model], for example:
    [["A_announce", 411, 878, ["Announce 1.wav", "Announce 2.wav"], "base"],
     ["B_worship", 932, 1789, ["Vox 1.wav", "Vox 2.wav"], "small"]]
Output: DIR/<name>.wav per region and DIR/transcripts.json ({name: [{start, end, text}]}, session
seconds). Rerunning reuses mixed region files. Needs faster-whisper."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf

def mix(d, files, a, b, out, sr_out=16000):
    import scipy.signal as ss
    acc = None; sr = None
    for f in files:
        with sf.SoundFile(os.path.join(d, f)) as s:
            sr = s.samplerate; s.seek(int(a * sr))
            y = s.read(int((b - a) * sr), dtype="float32", always_2d=True).mean(axis=1)
        acc = y if acc is None else acc[:len(y)] + y[:len(acc)]
    g = np.max(np.abs(acc)) or 1.0
    acc = (acc / g * 0.9).astype(np.float32)
    acc = ss.resample(acc, int(len(acc) * sr_out / sr)).astype(np.float32)
    sf.write(out, acc, sr_out, subtype="PCM_16")
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stems_dir"); ap.add_argument("regions"); ap.add_argument("--out", default="/tmp/tx")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    from lyrics import transcribe
    res = {}
    for name, t0, t1, files, model in json.load(open(a.regions)):
        p = os.path.join(a.out, name + ".wav")
        if not os.path.exists(p): mix(a.stems_dir, files, t0, t1, p)
        print("mixed", name, flush=True)
        segs = transcribe(p, model_size=model)
        for s in segs: s["start"] += t0; s["end"] += t0
        res[name] = segs
        json.dump(res, open(os.path.join(a.out, "transcripts.json"), "w"), indent=1)
        print("done", name, len(segs), flush=True)
