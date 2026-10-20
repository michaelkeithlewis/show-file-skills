#!/usr/bin/env python3
"""ptctl - a thin, chat-friendly control surface over the Pro Tools Scripting SDK (PTSL).

Pro Tools must be running with its scripting server live (it listens on
127.0.0.1:31416). This wraps py-ptsl so Claude can drive the session with short
verbs (`ptctl.py mute BAND on`) and an `exec` escape hatch for anything else.

Run with the venv python that has py-ptsl installed (see README.md):
    .venv/bin/python scripts/ptctl.py <cmd> ...

Importable too:
    from ptctl import engine
    with engine() as e:
        print(e.session_name())
"""
import argparse
import json
import os
import sys
from contextlib import contextmanager

from ptsl import PTSL_pb2 as pt


def _ename(enum_cls, value, strip=""):
    """Resolve a proto enum int to a clean name, stripping a prefix."""
    try:
        name = enum_cls.Name(value)
        return name[len(strip):] if strip and name.startswith(strip) else name
    except Exception:
        return value


def _attr_set(v):
    """TrackAttributeState is set when value >= 2 (Explicitly/Implicitly)."""
    return v >= 2

# These two strings are what Pro Tools shows in its "allow connection" dialog
# the first time. Keep them stable so the grant sticks. Override with the
# PTSL_COMPANY / PTSL_APP environment variables if you want your own names.
PT_COMPANY = os.environ.get("PTSL_COMPANY", "ShowFileSkills")
PT_APP = os.environ.get("PTSL_APP", "ClaudeCode")

# State setters that all share the (track_names: List[str], new_state: bool) shape.
TRACK_FLAGS = {
    "mute": "set_track_mute_state",
    "solo": "set_track_solo_state",
    "recenable": "set_track_record_enable_state",
    "recordsafe": "set_track_record_safe_enable_state",
    "solosafe": "set_track_solo_safe_state",
    "inputmonitor": "set_track_input_monitor_state",
    "inactive": "set_track_inactive_state",
    "hidden": "set_track_hidden_state",
    "online": "set_track_online_state",
    "frozen": "set_track_frozen_state",
}


@contextmanager
def engine():
    """Open a PTSL engine bound to the running Pro Tools instance."""
    from ptsl import open_engine
    with open_engine(company_name=PT_COMPANY, application_name=PT_APP) as eng:
        yield eng


def server_up(host="127.0.0.1", port=31416, timeout=1.0):
    """True if Pro Tools' scripting server is listening."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_running(wait_seconds=90):
    """Make sure Pro Tools is up with its scripting server listening. Launches
    the app if needed and polls until ready. NOTE: 'listening' isn't always
    'ready' - a freshly launched PT may still show the 'Allow ClaudeCode to
    connect' prompt (the registered engine() will block until you accept it)
    and/or sit on the Dashboard with no session open."""
    import subprocess, time
    if server_up():
        return "already-running"
    subprocess.run(["open", "-a", "Pro Tools"], check=False)
    for _ in range(max(1, wait_seconds // 3)):
        time.sleep(3)
        if server_up():
            return "launched"
    return "timeout"


def _on_off(val: str) -> bool:
    v = val.strip().lower()
    if v in ("on", "true", "1", "yes", "y", "enable", "enabled"):
        return True
    if v in ("off", "false", "0", "no", "n", "disable", "disabled"):
        return False
    raise SystemExit(f"expected on/off, got {val!r}")


def _track_summary(t):
    a = t.track_attributes
    flags = []
    if a.is_muted: flags.append("mute")
    if a.is_soloed: flags.append("solo")
    if a.is_record_enabled: flags.append("rec")
    if a.is_record_enabled_safe: flags.append("rec-safe")
    if a.is_soloed_safe: flags.append("solo-safe")
    if _attr_set(a.is_input_monitoring_on): flags.append("input-mon")
    if _attr_set(a.is_inactive): flags.append("inactive")
    if _attr_set(a.is_hidden): flags.append("hidden")
    if _attr_set(a.is_selected): flags.append("selected")
    if a.is_frozen: flags.append("frozen")
    return {
        "index": t.index,
        "name": t.name,
        "type": _ename(pt.TrackType, t.type, "TType_"),
        "format": _ename(pt.TrackFormat, t.format, "TFormat_"),
        "flags": flags,
    }


# ---- commands ----------------------------------------------------------------

def cmd_status(e, args):
    out = {
        "ptsl_version": e.ptsl_version(),
        "session_name": e.session_name(),
        "session_path": e.session_path(),
        "sample_rate": e.session_sample_rate(),
        "bit_depth": _ename(pt.BitDepth, e.session_bit_depth(), "BDepth_"),
        "audio_format": _ename(pt.SessionAudioFormat, e.session_audio_format(), "SAFormat_"),
        "timecode_rate": _ename(pt.SessionTimeCodeRate, e.session_timecode_rate(), "STCRate_"),
        "session_length": e.session_length(),
        "transport": e.transport_state(),
        "num_tracks": len(e.track_list()),
    }
    print(json.dumps(out, indent=2, default=str))


def cmd_tracks(e, args):
    tl = e.track_list()
    rows = [_track_summary(t) for t in tl]
    if args.filter:
        f = args.filter.lower()
        rows = [r for r in rows if f in r["name"].lower()]
    print(json.dumps(rows, indent=2, default=str))


def cmd_play(e, args):
    st = e.transport_state()
    if "Playing" in st or "Recording" in st:
        print(json.dumps({"transport": st, "action": "already-rolling"}))
        return
    e.toggle_play_state()
    print(json.dumps({"transport": e.transport_state(), "action": "play"}))


def cmd_stop(e, args):
    st = e.transport_state()
    if "Stopped" in st:
        print(json.dumps({"transport": st, "action": "already-stopped"}))
        return
    e.toggle_play_state()
    print(json.dumps({"transport": e.transport_state(), "action": "stop"}))


def cmd_transport(e, args):
    print(json.dumps({"transport": e.transport_state()}))


def cmd_flag(e, args):
    method = getattr(e, TRACK_FLAGS[args._flag])
    state = _on_off(args.state)
    method(args.tracks, state)
    print(json.dumps({"flag": args._flag, "tracks": args.tracks, "state": state}))


def cmd_select(e, args):
    e.select_tracks_by_name(args.tracks)
    print(json.dumps({"selected": args.tracks}))


def cmd_memlocs(e, args):
    locs = e.get_memory_locations()
    rows = [{"number": m.number, "name": m.name, "start": m.start_time} for m in locs]
    print(json.dumps(rows, indent=2, default=str))


def cmd_locate(e, args):
    e.select_memory_location(args.number)
    print(json.dumps({"located": args.number}))


def cmd_marker(e, args):
    kwargs = {"name": args.name}
    if args.time:
        kwargs["start_time"] = args.time
    if args.number is not None:
        kwargs["memory_number"] = args.number
    e.create_memory_location(**kwargs)
    print(json.dumps({"created_marker": args.name, "time": args.time}))


def cmd_selection(e, args):
    in_t, out_t = e.get_timeline_selection()
    print(json.dumps({"in": in_t, "out": out_t}))


def cmd_setsel(e, args):
    e.set_timeline_selection(in_time=args.in_time, out_time=args.out_time)
    print(json.dumps({"in": args.in_time, "out": args.out_time}))


def cmd_save(e, args):
    e.save_session()
    print(json.dumps({"saved": e.session_name()}))


# Commands whose availability is version/edition-gated - probed by `caps`.
# Each: (CId name, benign request body) - body that's valid enough to reach the
# implemented/unimplemented check without mutating the session.
# Non-destructive probes: invalid args reach the implemented/not-implemented
# check WITHOUT mutating the session. "supported (arg err)" means the command
# exists; "UNSUPPORTED" means this PT build doesn't implement the command id.
_CAP_PROBES = {
    "set_track_color":   ("CId_SetTrackColor", {"track_names": ["__notrack__"], "color_index": 1}),
    "route_outputs":     ("CId_SetTrackMainOutputAssignments", {"track_names": ["__notrack__"], "signalpath_ids": []}),
    "delete_tracks":     ("CId_DeleteTracks", {"track_names": ["__notrack__"]}),
    "get_clip_list":     ("CId_GetClipList", {"pagination_request": {"limit": 1, "offset": 0}}),
    "get_media_file_info": ("CId_GetMediaFileInfo", {"file_id": "0"}),
    "bounce_track":      ("CId_BounceTrack", {}),
}

# Wishlist commands that may be ADDED in a newer PTSL. Probe by name so they get
# picked up automatically once py-ptsl ships a proto that defines them.
_WISHLIST_NAMES = [
    "CId_SetTrackColor", "CId_SetTrackMainOutputAssignments", "CId_DeleteTracks",
    "CId_SetTempo", "CId_CreateTempoEvent", "CId_SetMeter", "CId_SetTimeSignature",
    "CId_MoveTracksToFolder", "CId_SetTrackParent", "CId_GroupTracks",
    "CId_SetTrackSends", "CId_SetSendLevel",
]

# Saved PTSL command list. Ships with the Pro Tools 2025.6 list in references/.
BASELINE = os.environ.get("PTSL_BASELINE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "references", "ptsl_commands_baseline.json")


def _all_command_names():
    return sorted(v.name for v in pt.CommandId.DESCRIPTOR.values
                  if v.name.startswith("CId_"))


def cmd_caps(e, args):
    """Probe version/edition-gated commands on the running PT build, and surface
    any brand-new commands vs a saved baseline (run `pip install -U py-ptsl`
    after a PT update so the proto reflects the new version, then re-run this).
    Tempo/meter/foldering need NEW commands from Avid - the wishlist check below
    auto-detects them once they appear in the proto."""
    from ptsl.errors import CommandError
    out = {"ptsl_version": e.ptsl_version(), "command_count": len(_all_command_names()), "probed": {}}
    for label, (cid, body) in _CAP_PROBES.items():
        if not hasattr(pt.CommandId, cid):
            out["probed"][label] = "not-in-proto (upgrade py-ptsl)"
            continue
        try:
            e.client.run_command(getattr(pt.CommandId, cid), body)
            out["probed"][label] = "supported"
        except CommandError as ce:
            out["probed"][label] = "UNSUPPORTED" if "UnsupportedCommand" in str(ce) else "supported (arg err)"
        except Exception as ce:
            out["probed"][label] = f"supported (err: {type(ce).__name__})"

    # which wishlist commands now exist in the proto at all
    names = set(_all_command_names())
    out["wishlist_in_proto"] = {n: (n in names) for n in _WISHLIST_NAMES}

    # diff full command set vs saved baseline -> reveals new commands after update
    if os.path.exists(BASELINE):
        with open(BASELINE) as f:
            base = set(json.load(f).get("commands", []))
        cur = names
        out["new_commands_since_baseline"] = sorted(cur - base)
        out["removed_since_baseline"] = sorted(base - cur)
    else:
        out["baseline"] = "none saved - run `ptctl.py caps --save-baseline` first"

    if getattr(args, "save_baseline", False):
        with open(BASELINE, "w") as f:
            json.dump({"ptsl_version": e.ptsl_version(), "commands": _all_command_names()}, f, indent=2)
        out["baseline_saved"] = BASELINE
    print(json.dumps(out, indent=2))


def cmd_exec(e, args):
    """Run arbitrary Python with the engine bound as `e`. The result of the last
    expression (or anything you print) is shown. This is the escape hatch for the
    ~100 methods not given a dedicated verb."""
    code = args.code
    ns = {"e": e, "json": json}
    try:
        # try eval first (expression), fall back to exec (statements)
        result = eval(code, ns)  # noqa: S307 - intentional, local trusted use
        if result is not None:
            print(result if isinstance(result, str) else json.dumps(result, indent=2, default=str))
    except SyntaxError:
        exec(code, ns)  # noqa: S102 - intentional


def build_parser():
    p = argparse.ArgumentParser(prog="ptctl", description="Chat-friendly Pro Tools (PTSL) control")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="session + transport summary").set_defaults(fn=cmd_status)

    sp = sub.add_parser("tracks", help="list tracks and their state")
    sp.add_argument("--filter", help="substring match on track name")
    sp.set_defaults(fn=cmd_tracks)

    sub.add_parser("play", help="start playback (no-op if rolling)").set_defaults(fn=cmd_play)
    sub.add_parser("stop", help="stop playback (no-op if stopped)").set_defaults(fn=cmd_stop)
    sub.add_parser("transport", help="print transport state").set_defaults(fn=cmd_transport)

    for flag in TRACK_FLAGS:
        sp = sub.add_parser(flag, help=f"set {flag} on one or more tracks")
        sp.add_argument("tracks", nargs="+", help="track name(s); last arg may be on/off")
        sp.set_defaults(fn=cmd_flag, _flag=flag)

    sp = sub.add_parser("select", help="select tracks by name")
    sp.add_argument("tracks", nargs="+")
    sp.set_defaults(fn=cmd_select)

    sub.add_parser("memlocs", help="list memory locations").set_defaults(fn=cmd_memlocs)

    sp = sub.add_parser("locate", help="recall a memory location by number")
    sp.add_argument("number", type=int)
    sp.set_defaults(fn=cmd_locate)

    sp = sub.add_parser("marker", help="create a memory location / marker")
    sp.add_argument("name")
    sp.add_argument("--time", help="start time string in current main counter format")
    sp.add_argument("--number", type=int, help="memory location number")
    sp.set_defaults(fn=cmd_marker)

    sub.add_parser("selection", help="print timeline selection in/out").set_defaults(fn=cmd_selection)

    sp = sub.add_parser("setsel", help="set timeline selection")
    sp.add_argument("in_time")
    sp.add_argument("out_time")
    sp.set_defaults(fn=cmd_setsel)

    sub.add_parser("save", help="save the session").set_defaults(fn=cmd_save)

    sub.add_parser("launch", help="launch Pro Tools if needed and wait for the scripting server").set_defaults(fn=None)

    sp = sub.add_parser("caps", help="probe gated commands + diff command set vs baseline")
    sp.add_argument("--save-baseline", dest="save_baseline", action="store_true",
                    help="save the current command set as the baseline for future diffs")
    sp.set_defaults(fn=cmd_caps)

    sp = sub.add_parser("exec", help="run arbitrary python with engine bound as `e`")
    sp.add_argument("code", help="python expression or statements")
    sp.set_defaults(fn=cmd_exec)

    return p


def _normalize_flag_args(args):
    """For flag verbs, the last positional may be the on/off state."""
    if getattr(args, "_flag", None) and len(args.tracks) >= 2:
        maybe = args.tracks[-1].lower()
        if maybe in ("on", "off", "true", "false", "1", "0", "yes", "no",
                     "enable", "disable", "enabled", "disabled"):
            args.state = args.tracks.pop()
            return
    if getattr(args, "_flag", None):
        # default to turning the flag ON if no state was given
        args.state = getattr(args, "state", "on")


def main(argv=None):
    args = build_parser().parse_args(argv)
    # `launch` runs WITHOUT a connection (Pro Tools may be down)
    if getattr(args, "cmd", None) == "launch":
        status = ensure_running()
        print(json.dumps({"protools": status,
                          "note": "if it just launched, accept the 'Allow ClaudeCode' prompt in PT and open/Dashboard a session"}))
        return
    _normalize_flag_args(args)
    try:
        with engine() as e:
            args.fn(e, args)
    except Exception as exc:  # surface PTSL errors cleanly for chat
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
