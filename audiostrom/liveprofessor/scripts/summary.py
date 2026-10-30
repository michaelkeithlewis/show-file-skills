#!/usr/bin/env python3
"""Print a readable summary of LiveProfessor sessions: audio device, chains, plugins and routing.

usage: summary.py FILE.rack2 [FILE.rack2 ...]

One line per chain (view order, name, input/output channel count, DelayMode, plugin
names), then every audio patch point of the current state as
"<source>:<channel> -> <destination>:<channel>". Node 1 is HW IN, node 2 is HW OUT,
any other node id is a chain (its ProcessorSettingsContainer id).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vt


def summary(fn):
    n, _ = vt.load(fn)
    print("==", fn)
    for hw in n.find("AudioMidiHardware"):
        for io in hw.find("IOdeviceProperties"):
            print(" device", io.get("audioDeviceType"), io.get("inputDeviceName"),
                  "in", io.get("RequiredInputs"), "out", io.get("RequiredOutputs"))
    names = {1: "HW IN", 2: "HW OUT"}
    for chains in n.find("Chains"):
        for node in chains.find("Chain"):
            cs = next(node.find("ChainSettings"))
            psc = next(cs.find("ProcessorSettingsContainer"))
            names[psc.get("id")] = psc.get("name")
            plugs = []
            for po in cs.find("ProcessorOrder"):
                for p in po.find("plug"):
                    t = p.get("type") or ""
                    plugs.append(t.split("-")[1] if "-" in t else t)
            print("  chain %s %r in=%s out=%s delay=%s %s" % (node.get("ChainViewOrder"), psc.get("name"),
                  cs.get("ChainInputCount"), cs.get("ChainOutputCount"), cs.get("DelayMode"), plugs))
    gs = [k for k in n.kids if k.type == "GlobalSnapshot"]
    for ap in (gs[0].find("AudioPatch") if gs else []):
        for o in ap.find("outputs"):
            for p in o.find("point"):
                s, t = p.get("outputNodeId"), p.get("inputNodeId")
                print("   %s:%d -> %s:%d" % (names.get(s, s), p.get("outputChannelId") + 1,
                                            names.get(t, t), p.get("inputChannelId") + 1))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) > 1 else 2)
    for f in sys.argv[1:]:
        summary(f)
