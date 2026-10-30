#!/usr/bin/env python3
"""lyrics.py - verse/chorus/bridge detection from transcribed lyrics.

Song form is really a *lyrical* pattern: a chorus repeats the same words, verses
keep a melody but change words, a bridge is unique words once. So we transcribe
the vocal stem (Whisper) and find lyrical repetition, then (optionally) snap the
section boundaries to the musical segmentation from structure.py.

    .venv/bin/python scripts/lyrics.py VOCAL.wav [--model base] [--music PRIMARY.wav]
"""
import argparse
import json
import re
import warnings
from difflib import SequenceMatcher

warnings.filterwarnings("ignore")

_MODEL_CACHE = {}


def _words_to_lines(words, gap=0.7, max_words=10):
    """Re-chunk word stream into sung phrases by pauses (sustained singing fools
    Whisper's own segmentation, so we split on inter-word gaps / length)."""
    lines, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > gap or len(cur) >= max_words):
            lines.append(cur); cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return [{"start": float(l[0]["start"]), "end": float(l[-1]["end"]),
             "text": "".join(x["word"] for x in l).strip()}
            for l in lines if "".join(x["word"] for x in l).strip()]


def transcribe(vocal_path, model_size="small"):
    """Return [{start, end, text}] sung phrases, split by pauses via word timestamps."""
    from faster_whisper import WhisperModel
    if model_size not in _MODEL_CACHE:
        _MODEL_CACHE[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    model = _MODEL_CACHE[model_size]
    segments, _info = model.transcribe(vocal_path, word_timestamps=True, vad_filter=True,
                                        condition_on_previous_text=False)
    words = []
    seg_fallback = []
    for s in segments:
        seg_fallback.append({"start": float(s.start), "end": float(s.end), "text": s.text.strip()})
        for w in (s.words or []):
            if w.start is not None:
                words.append({"start": w.start, "end": w.end, "word": w.word})
    if words:
        return _words_to_lines(words, gap=1.1, max_words=12)
    return [s for s in seg_fallback if s["text"]]


def _norm(t):
    return " ".join(re.sub(r"[^a-z0-9 ]", "", t.lower()).split())


def _sim(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _group_lines(segments, thresh=0.6):
    """Cluster segments by lyric similarity; return a group-id per segment."""
    groups = []
    gid = [None] * len(segments)
    for i, seg in enumerate(segments):
        placed = False
        for g, grp in enumerate(groups):
            if _sim(seg["text"], grp["rep"]) >= thresh:
                grp["members"].append(i)
                gid[i] = g
                placed = True
                break
        if not placed:
            groups.append({"rep": seg["text"], "members": [i]})
            gid[i] = len(groups) - 1
    return gid, groups


def label_from_lyrics(segments, music_bounds=None, total_dur=None):
    """Turn transcribed segments into labelled sections via lyrical repetition."""
    if not segments:
        return []
    gid, groups = _group_lines(segments)
    repeated = {g for g, grp in enumerate(groups) if len(grp["members"]) >= 2}

    roles = ["chorus" if gid[i] in repeated else "verse" for i in range(len(segments))]

    raw = []
    start_i = 0
    for i in range(1, len(segments) + 1):
        if i == len(segments) or roles[i] != roles[start_i]:
            raw.append({"role": roles[start_i],
                        "start": segments[start_i]["start"],
                        "end": segments[i - 1]["end"],
                        "text": " / ".join(segments[j]["text"] for j in range(start_i, i)),
                        "seg_idx": list(range(start_i, i))})
            start_i = i

    def _merge_short(sections, min_dur=7.0):
        changed = True
        while changed and len(sections) > 1:
            changed = False
            for k, s in enumerate(sections):
                if (s["end"] - s["start"]) < min_dur:
                    tgt = k - 1 if k > 0 else k + 1
                    a, b = (tgt, k) if tgt < k else (k, tgt)
                    sections[a]["end"] = sections[b]["end"]
                    sections[a]["start"] = sections[a]["start"]
                    sections[a]["text"] = sections[a]["text"] + " / " + sections[b]["text"]
                    sections[a]["role"] = sections[min(a, b)]["role"] if a != k else sections[a]["role"]
                    sections[a]["role"] = sections[tgt]["role"]
                    del sections[b]
                    changed = True
                    break
        return sections
    raw = _merge_short(raw)
    coalesced = []
    for s in raw:
        if coalesced and coalesced[-1]["role"] == s["role"]:
            coalesced[-1]["end"] = s["end"]
            coalesced[-1]["text"] += " / " + s["text"]
        else:
            coalesced.append(dict(s))
    raw = coalesced

    chorus_positions = [k for k, s in enumerate(raw) if s["role"] == "chorus"]
    if chorus_positions:
        first_chorus = chorus_positions[0]
        for k, s in enumerate(raw):
            if s["role"] == "verse" and k > first_chorus and total_dur \
               and s["start"] > 0.5 * total_dur:
                s["role"] = "bridge"
                break

    if music_bounds:
        for s in raw:
            near = min(music_bounds, key=lambda b: abs(b - s["start"]))
            if abs(near - s["start"]) <= 4.0:
                s["start"] = near

    counts = {}
    for s in raw:
        counts[s["role"]] = counts.get(s["role"], 0) + 1
    seen, out = {}, []
    for i, s in enumerate(raw, 1):
        role = s["role"]
        base = role.capitalize()
        if counts[role] > 1 and role != "bridge":
            seen[role] = seen.get(role, 0) + 1
            label = f"{base} {seen[role]}"
        else:
            label = base
        out.append({"index": i, "start": round(s["start"], 3),
                    "end": round(s["end"], 3), "label": label,
                    "lyric": s["text"][:80]})
    return out


def analyze_lyrical_structure(vocal_path, music_path=None, model_size="small"):
    segments = transcribe(vocal_path, model_size)
    total_dur = segments[-1]["end"] if segments else None
    music_bounds = None
    if music_path:
        import structure as structurer
        sres = structurer.analyze_structure(music_path, vocal_path)
        music_bounds = [sec["start"] for sec in sres["sections"]]
        total_dur = sres["duration_sec"]
    return {
        "vocal": vocal_path,
        "music": music_path,
        "model": model_size,
        "method": "lyric-repetition" + (" + music-boundary-snap" if music_path else ""),
        "num_lines": len(segments),
        "sections": label_from_lyrics(segments, music_bounds, total_dur),
        "transcript": segments,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("vocal")
    p.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium")
    p.add_argument("--music", help="harmonic source to snap boundaries to")
    p.add_argument("--show-transcript", action="store_true")
    a = p.parse_args()
    res = analyze_lyrical_structure(a.vocal, a.music, a.model)
    if not a.show_transcript:
        res.pop("transcript", None)
    print(json.dumps(res, indent=2))
