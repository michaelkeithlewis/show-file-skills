#!/usr/bin/env python3
"""ptprep.py - track-preparation layer over PTSL + analyze.py.

Resolves the audio actually referenced by the open session (wherever the files
live on disk), runs tempo/key/section analysis, and writes the results back as
Pro Tools memory locations (markers). Tempo itself can't be written via the SDK,
so `tempo` prints the detected value plus manual-entry instructions.

    PY=.venv/bin/python        # the venv with py-ptsl, see README.md
    $PY ptprep.py sources                      # list analyzable session audio
    $PY ptprep.py analyze AG_1 [--sections 8]  # analyze one source
    $PY ptprep.py tempo AG_1                    # detect tempo + how to set it
    $PY ptprep.py markers AG_1 [--sections] [--bars] [--beats] [--dry-run]
    $PY ptprep.py clear-prep                    # remove markers this tool added
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptctl import engine
from ptsl import PTSL_pb2 as pt

import analyze as analyzer
import structure as structurer
import lyrics as lyricser

VOCAL_HINTS = ("vox", "vocal", "lead vox", "lv", "vcl", "vox_")

# Records which memory-location numbers this tool placed, per session, so
# `clear-prep` removes only those. Lives outside the skill folder.
SIDE_CAR = os.environ.get("PTPREP_SIDECAR") or os.path.join(
    os.path.expanduser("~/.cache/protools-skill"), "prep_markers.json")


# ---- session audio discovery -------------------------------------------------

def _colon_to_posix(location, filename):
    """Convert a Pro Tools 'Macintosh HD:Users:...:' path to POSIX."""
    loc = location.strip().rstrip(":")
    parts = loc.split(":")
    if not parts:
        return None
    vol, rest = parts[0], parts[1:]
    root = "/" if vol in ("Macintosh HD", "") else f"/Volumes/{vol}/"
    return os.path.join(root, *rest, filename.strip())


def _file_map(e):
    """{filename: posix_path} from the session text export's ONLINE FILES block."""
    b = e.export_session_as_text()
    b.all_tracks(); b.include_file_list()
    txt = b.export_string()
    out, in_block = {}, False
    for line in txt.splitlines():
        if "O N L I N E" in line:
            in_block = True
            continue
        if "O F F L I N E" in line or "T R A C K" in line:
            in_block = False
        if in_block and "\t" in line:
            fn, _, loc = line.partition("\t")
            fn = fn.strip()
            if fn.lower() == "filename" or not loc.strip():
                continue
            p = _colon_to_posix(loc, fn)
            if p:
                out[fn] = p
    return out


def session_sources(e):
    """List unique analyzable sources: clip root name -> resolved file + timeline offset."""
    fmap = _file_map(e)
    cl = e.client.run_command(pt.CommandId.CId_GetClipList,
                              {"pagination_request": {"limit": 500, "offset": 0}})
    clips = cl.get("clip_list", []) if cl else []
    sr = e.session_sample_rate()
    seen, sources = {}, []
    for c in clips:
        if c.get("clip_type") != "CType_Audio":
            continue
        root = c.get("clip_root_name", "")
        if root in seen:
            continue
        seen[root] = True
        # match a file whose name starts with the clip root
        path = next((p for fn, p in fmap.items() if fn.split(".")[0] == root), None)
        if path is None:
            path = next((p for fn, p in fmap.items() if fn.startswith(root)), None)
        start = int(c.get("start_point", {}).get("position", 0) or 0)
        src_start = int(c.get("src_start_point", {}).get("position", 0) or 0)
        sources.append({
            "name": root,
            "clip": c.get("clip_full_name", root),
            "file": path,
            "exists": bool(path and os.path.exists(path)),
            "timeline_offset_sec": round((start - src_start) / sr, 4),
        })
    return sources


def _find_vocal(e):
    """Best-guess vocal source in the session (for verse/chorus labelling)."""
    for s in session_sources(e):
        hay = f"{s['name']} {s.get('clip','')}".lower()
        if s.get("exists") and any(h in hay for h in VOCAL_HINTS):
            return s
    return None


def _resolve(e, query):
    """Pick a source by substring of its name / clip / file, or treat query as a path."""
    if os.path.exists(query):
        return {"name": os.path.basename(query), "file": query,
                "exists": True, "timeline_offset_sec": 0.0}
    q = query.lower()
    for s in session_sources(e):
        if q in s["name"].lower() or q in (s["clip"] or "").lower() \
           or (s["file"] and q in s["file"].lower()):
            return s
    return None


# ---- marker placement --------------------------------------------------------

def _fmt_minsecs(t):
    t = max(0.0, float(t))
    m = int(t // 60)
    return f"{m}:{t - 60 * m:06.3f}"


def _load_sidecar():
    if os.path.exists(SIDE_CAR):
        with open(SIDE_CAR) as f:
            return json.load(f)
    return {}


def _save_sidecar(d):
    os.makedirs(os.path.dirname(SIDE_CAR), exist_ok=True)
    with open(SIDE_CAR, "w") as f:
        json.dump(d, f, indent=2)


def place_markers(e, marks, dry_run=False, base=200):
    """marks: list of (seconds, name). Returns assigned location numbers.

    PTSL won't auto-increment unnumbered markers (every one lands on the same
    slot), so we assign explicit free numbers starting at `base`.
    """
    if dry_run:
        for t, name in marks:
            print(f"  {_fmt_minsecs(t):>12}  {name}")
        return []
    used = {m.number for m in e.get_memory_locations()}
    added, n = [], base
    # Absolute (sample) reference so markers stay put when tempo is set later -
    # NOT Bar|Beat, which would drag them around once a tempo map exists.
    abs_ref = pt.MemoryLocationReference.MLReference_Absolute
    for t, name in marks:
        while n in used:
            n += 1
        e.create_memory_location(memory_number=n, name=name,
                                 start_time=_fmt_minsecs(t), reference=abs_ref)
        used.add(n)
        added.append(n)
        n += 1
    # record for clean removal later, keyed by session
    sc = _load_sidecar()
    key = e.session_name()
    sc[key] = sorted(set(sc.get(key, []) + added))
    _save_sidecar(sc)
    return added


# ---- commands ----------------------------------------------------------------

def cmd_sources(e, args):
    print(json.dumps(session_sources(e), indent=2))


def cmd_analyze(e, args):
    s = _resolve(e, args.source)
    if not s or not s.get("exists"):
        print(json.dumps({"error": "source not found / file offline", "query": args.source,
                          "hint": "run `ptprep.py sources` to see options"}))
        sys.exit(1)
    res = analyzer.analyze_file(s["file"], n_sections=args.sections,
                                beats_per_bar=args.beats_per_bar)
    res["timeline_offset_sec"] = s["timeline_offset_sec"]
    res["source_name"] = s["name"]
    if args.no_beats:
        res["beats"] = f"<{len(res['beats'])} beats>"
    print(json.dumps(res, indent=2))


def _run_structure(e, args):
    """Resolve primary + vocal sources and return (analysis, primary_source)."""
    s = _resolve(e, args.source)
    if not s or not s.get("exists"):
        return None, None
    if getattr(args, "vocal", None):
        vsrc = _resolve(e, args.vocal)
    else:
        vsrc = _find_vocal(e)
    vpath = vsrc["file"] if (vsrc and vsrc.get("exists")) else None
    res = structurer.analyze_structure(s["file"], vpath, n_types=args.types)
    res["timeline_offset_sec"] = s["timeline_offset_sec"]
    res["vocal_source"] = vsrc["name"] if vsrc else None
    return res, s


def cmd_structure(e, args):
    res, s = _run_structure(e, args)
    if not res:
        print(json.dumps({"error": "source not found", "query": args.source}))
        sys.exit(1)
    print(json.dumps(res, indent=2))


def _run_lyrics(e, args):
    """Transcribe the vocal stem and label verse/chorus/bridge by lyric repetition,
    snapping boundaries to the harmonic source's musical segmentation."""
    s = _resolve(e, args.source)            # harmonic/primary source (for snapping)
    if not s or not s.get("exists"):
        return None, None
    vsrc = _resolve(e, args.vocal) if getattr(args, "vocal", None) else _find_vocal(e)
    if not vsrc or not vsrc.get("exists"):
        return {"error": "no vocal source found for lyric analysis"}, s
    res = lyricser.analyze_lyrical_structure(vsrc["file"], music_path=s["file"],
                                             model_size=getattr(args, "model", "small"))
    res.pop("transcript", None)
    res["timeline_offset_sec"] = s["timeline_offset_sec"]
    res["vocal_source"] = vsrc["name"]
    return res, s


def cmd_lyrics(e, args):
    res, s = _run_lyrics(e, args)
    if not res:
        print(json.dumps({"error": "source not found", "query": args.source}))
        sys.exit(1)
    print(json.dumps(res, indent=2))


def cmd_tempo(e, args):
    s = _resolve(e, args.source)
    if not s or not s.get("exists"):
        print(json.dumps({"error": "source not found", "query": args.source}))
        sys.exit(1)
    res = analyzer.analyze_file(s["file"], n_sections=2, beats_per_bar=args.beats_per_bar)
    bpm = res["tempo_bpm"]
    print(json.dumps({
        "source": s["name"],
        "detected_bpm": bpm,
        "candidates": res["tempo_candidates"],
        "key": res["key"]["key"],
        "how_to_set": [
            "PTSL cannot write tempo - set it once by hand, then re-run `markers` for guides:",
            f"1. In Pro Tools, open the Conductor track and type {bpm} into the Tempo (or use the default tempo field).",
            "2. OR: make a timeline selection over a steady bar, then Event > Identify Beat (Cmd+I) and confirm the bar/beat.",
            "3. Enable the Conductor (Tempo ruler) so the grid follows the song.",
        ],
    }, indent=2))


def cmd_markers(e, args):
    s = _resolve(e, args.source)
    if not s or not s.get("exists"):
        print(json.dumps({"error": "source not found", "query": args.source}))
        sys.exit(1)
    # default to sections if no marker type chosen
    if not (args.sections_markers or args.structure or args.lyrics or args.bars or args.beats):
        args.sections_markers = True

    # --lyrics / --structure override plain section markers with named sections
    if args.lyrics or args.structure:
        sres, _ = (_run_lyrics(e, args) if args.lyrics else _run_structure(e, args))
        if sres.get("error"):
            print(json.dumps(sres)); sys.exit(1)
        off = sres["timeline_offset_sec"]
        marks = [(sec["start"] + off, f"{args.prefix}{sec['label']}") for sec in sres["sections"]]
        if not (args.bars or args.beats):
            marks.sort(key=lambda m: m[0])
            mode = "lyric" if args.lyrics else "structure"
            if args.dry_run:
                print(f"DRY RUN - {len(marks)} {mode} markers from '{s['name']}' "
                      f"(vocal: {sres.get('vocal_source') or 'none'}):")
                place_markers(e, marks, dry_run=True)
                return
            added = place_markers(e, marks)
            print(json.dumps({"source": s["name"], "mode": mode,
                              "vocal_source": sres.get("vocal_source"),
                              "placed": len(added), "location_numbers": added}, indent=2))
            return
        # fall through to also add bars/beats below
        beat_src = analyzer.analyze_file(s["file"], n_sections=2, beats_per_bar=args.beats_per_bar)
        res = {"sections": sres["sections"], "tempo_bpm": beat_src["tempo_bpm"],
               "key": beat_src["key"], "beats": beat_src["beats"], "downbeats": beat_src["downbeats"]}
    else:
        res = analyzer.analyze_file(s["file"], n_sections=args.sections,
                                    beats_per_bar=args.beats_per_bar)
        off = s["timeline_offset_sec"]
        marks = []
        if args.sections_markers:
            for sec in res["sections"]:
                marks.append((sec["start"] + off, f"{args.prefix}{sec['label']}"))
    if args.bars:
        for i, t in enumerate(res["downbeats"], 1):
            marks.append((t + off, f"{args.prefix}Bar {i}"))
    if args.beats:
        for i, t in enumerate(res["beats"], 1):
            marks.append((t + off, f"{args.prefix}beat {i}"))
    marks.sort(key=lambda m: m[0])
    if args.dry_run:
        print(f"DRY RUN - {len(marks)} markers from '{s['name']}' "
              f"(tempo {res['tempo_bpm']} BPM, key {res['key']['key']}):")
        place_markers(e, marks, dry_run=True)
        return
    added = place_markers(e, marks)
    print(json.dumps({"source": s["name"], "placed": len(added),
                      "tempo_bpm": res["tempo_bpm"], "key": res["key"]["key"],
                      "location_numbers": added}, indent=2))


def cmd_clear_prep(e, args):
    sc = _load_sidecar()
    key = e.session_name()
    nums = sc.get(key, [])
    if not nums:
        print(json.dumps({"cleared": 0, "note": "no prep markers recorded for this session"}))
        return
    e.client.run_command(pt.CommandId.CId_ClearMemoryLocation, {"location_list": nums})
    sc[key] = []
    _save_sidecar(sc)
    print(json.dumps({"cleared": len(nums), "location_numbers": nums}))


def build_parser():
    p = argparse.ArgumentParser(prog="ptprep", description="Pro Tools track preparation")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sources", help="list analyzable session audio with resolved paths").set_defaults(fn=cmd_sources)

    def add_common(sp):
        sp.add_argument("source", help="clip/track/file substring, or a direct audio path")
        sp.add_argument("--sections", type=int, default=8)
        sp.add_argument("--beats-per-bar", type=int, default=4)

    sp = sub.add_parser("analyze", help="tempo/key/sections for one source")
    add_common(sp); sp.add_argument("--no-beats", action="store_true"); sp.set_defaults(fn=cmd_analyze)

    sp = sub.add_parser("tempo", help="detect tempo + manual-entry instructions")
    sp.add_argument("source"); sp.add_argument("--beats-per-bar", type=int, default=4)
    sp.set_defaults(fn=cmd_tempo)

    sp = sub.add_parser("structure", help="verse/chorus labels from musical repetition + vocal energy")
    sp.add_argument("source", help="harmonic source for structure (e.g. acoustic gtr, full mix)")
    sp.add_argument("--vocal", help="vocal source (auto-detected if omitted)")
    sp.add_argument("--types", type=int, default=5, help="how many structural types to cluster")
    sp.set_defaults(fn=cmd_structure)

    sp = sub.add_parser("lyrics", help="verse/chorus/bridge from transcribed lyric repetition (best)")
    sp.add_argument("source", help="harmonic source (boundaries snap to it); vocal auto-detected")
    sp.add_argument("--vocal", help="vocal source to transcribe (auto-detected if omitted)")
    sp.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium")
    sp.set_defaults(fn=cmd_lyrics)

    sp = sub.add_parser("markers", help="place section/bar/beat markers from analysis")
    add_common(sp)  # provides --sections (count), --beats-per-bar
    sp.add_argument("--lyrics", action="store_true",
                    help="label verse/chorus/bridge from transcribed lyric repetition (best)")
    sp.add_argument("--structure", action="store_true",
                    help="label verse/chorus from musical repetition + vocal energy")
    sp.add_argument("--vocal", help="vocal source for --structure/--lyrics (auto-detected if omitted)")
    sp.add_argument("--types", type=int, default=5, help="structural types for --structure")
    sp.add_argument("--model", default="small", help="whisper model for --lyrics")
    sp.add_argument("--section-markers", dest="sections_markers", action="store_true",
                    help="place energy-labelled section markers (default if no type chosen)")
    sp.add_argument("--bars", action="store_true", help="place a marker on each estimated downbeat")
    sp.add_argument("--beats", action="store_true", help="place a marker on every beat (a lot)")
    sp.add_argument("--prefix", default="", help="prepend to every marker name")
    sp.add_argument("--dry-run", action="store_true", help="preview without writing")
    sp.set_defaults(fn=cmd_markers)

    sub.add_parser("clear-prep", help="remove markers this tool placed in the open session").set_defaults(fn=cmd_clear_prep)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        with engine() as e:
            args.fn(e, args)
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
