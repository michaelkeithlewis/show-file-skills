#!/usr/bin/env python3
"""verify_routing.py - prove where the audio is actually going.

PTSL cannot read a track's output on this build (Private API), so asking is out.
Bouncing is not: offline-bounce each group bus over a window where the whole
arrangement is playing and measure it. A bus carrying its children reads as
audio; a bus whose children went to the main bus instead reads as digital silence.

This is how a scripted prep was once caught with every stem bypassing the
template: the main bus peaked at 0.0 dB while a group bus read -240 dB.

    verify_routing.py [--at-sample 3700000] [--length 200000] [--master-bus PrMst] [--list]

The bus list comes from the open session: every routing folder owns a bus,
usually of the same name, so each routing folder is bounced, plus the main bus
(--master-bus, the bus your template sums into before the master fader). It is
never a hard-coded list. A folder with no tracks inside it is reported but not
counted as a failure.

NOTE: PT ignores location_info.directory and writes into the session's
"Bounced Files" folder. The script reads them from there and cleans up.
"""
import sys, os, glob, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from ptctl import engine
from ptsl import PTSL_pb2 as pt
rc = pt.CommandId

MASTER_BUS = "PrMst"


def plan_buses(tracks, master_bus=MASTER_BUS):
    """[(bus, has_children)] for every routing folder in the session, then the main bus.
    A folder counts as having children if any track (audio or a nested folder)
    sits directly inside it."""
    parents = {t.parent_folder_name for t in tracks if t.parent_folder_name}
    folders = [t.name for t in tracks if t.type == pt.TType_RoutingFolder]
    return [(f, f in parents) for f in folders] + [(master_bus, True)]


def resolve_bus(folder, sources):
    """A routing folder's bus is usually its own name, but templates rename some
    (a folder BASS GROUP may own `BASS`, DRUM GROUP may own `DRUMS`). Match exactly first, then
    by first word. `sources` only lists buses that something feeds, so an
    unrouted folder falls back to its own name and fails as NO BOUNCE."""
    if folder in sources:
        return folder
    head = folder.split()[0]
    hits = [b for b in sources if "." not in b and b.split()[0].startswith(head)]
    return hits[0] if len(hits) == 1 else folder


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at-sample", type=int, default=3700000)
    ap.add_argument("--length", type=int, default=200000)
    ap.add_argument("--master-bus", default=MASTER_BUS,
                    help="name of the main mix bus to bounce as the reference (default PrMst)")
    ap.add_argument("--list", action="store_true", help="print the buses and exit")
    a = ap.parse_args()

    with engine() as e:
        plan = plan_buses(e.track_list(), a.master_bus)
        if a.list:
            sources = e.client.run_command(rc.CId_GetExportMixSourceList,
                                           {"type": "EMSType_Bus"}).get("source_list", [])
            for bus, has in plan:
                print(f"{bus:14} -> {resolve_bus(bus, sources):14} {'' if has else '(empty folder)'}")
            return
        sources = e.client.run_command(rc.CId_GetExportMixSourceList,
                                       {"type": "EMSType_Bus"}).get("source_list", [])
        plan = [(resolve_bus(b, sources), has) for b, has in plan]
        BUSES = [b for b, _ in plan]
        empty = {b for b, has in plan if not has}
        bdir = os.path.join(os.path.dirname(e.session_path()), "Bounced Files")
        for p in glob.glob(os.path.join(bdir, "VERIFY_*.wav")):
            os.remove(p)
        for bus in BUSES:
            body = {"file_name": "VERIFY_" + bus.replace("/", "_"),
                    "file_type": "EFType_WAV",
                    "mix_source_list": [{"source_type": "EMSType_Bus", "name": bus}],
                    "audio_info": {"compression_type": "CT_PCM", "export_format": "EF_Interleaved",
                                   "bit_depth": "Bit24", "sample_rate": "SR_48000",
                                   "pad_to_frame_boundary": "TB_False",
                                   "delivery_format": "EMDF_SingleFile"},
                    "location_info": {"import_after_bounce": "TB_False",
                                      "file_destination": "EMFD_Directory", "directory": bdir},
                    "offline_bounce": "TB_True",
                    "start_time": {"time_type": "TLType_Samples", "location": str(a.at_sample)},
                    "end_time": {"time_type": "TLType_Samples", "location": str(a.at_sample + a.length)}}
            try:
                e.client.run_command(rc.CId_ExportMix, body)
            except Exception as ex:
                print(f"{bus:14} bounce failed: {str(ex)[:90]}")

    for _ in range(40):                       # offline bounce is async
        if len(glob.glob(os.path.join(bdir, "VERIFY_*.wav"))) >= len(BUSES):
            break
        time.sleep(5)

    print(f"{'bus':14} {'peak dB':>9}  verdict")
    silent = []
    for bus in BUSES:
        p = os.path.join(bdir, "VERIFY_" + bus.replace("/", "_") + ".wav")
        if not os.path.exists(p):
            print(f"{bus:14} {'-':>9}  NO BOUNCE (bus missing or bounce failed)")
            if bus not in empty:
                silent.append(bus)
            continue
        y, _ = sf.read(p, always_2d=True)
        pk = 20 * np.log10(float(np.max(np.abs(y))) + 1e-12)
        # -60 dB is the line. A bus with nothing assigned to it reads -240 dB
        # (true digital silence); -78 dB is plug-in noise floor bleeding through
        # an otherwise empty bus, not audio. The main bus reads near 0 dB when it has the mix.
        ok = pk > -60
        if not ok and bus not in empty:
            silent.append(bus)
        verdict = "carrying audio" if ok else ("silent (empty folder)" if bus in empty else "SILENT")
        print(f"{bus:14} {pk:9.1f}  {verdict}")
        os.remove(p)
    print("\nrouting looks correct" if not silent
          else "\nstill unrouted: " + ", ".join(silent) + "  (redo routing for these)")


if __name__ == "__main__":
    main()
