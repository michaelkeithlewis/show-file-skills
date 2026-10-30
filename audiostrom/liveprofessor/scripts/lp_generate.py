#!/usr/bin/env python3
"""Generate a pre-routed LiveProfessor 2 session (.rack2) from a base session and a JSON channel list.

usage: lp_generate.py BASE.rack2 channels.json OUT.rack2

The base must be a session that LiveProfessor saved. It must contain one mono chain
and one stereo chain with no plugins (named in the JSON as blank_mono / blank_stereo).
Chains that should carry plugins are copied from a named chain in the base.

Every chain is wired HW IN -> chain -> HW OUT, so a chain with no plugins passes
audio. This is the usual layout for console inserts over Dante or MADI.

channels.json (see ../examples/channels.json):
{
  "device": "Dante Virtual Soundcard",   optional, sets input and output device name
  "io": 64,                              hardware channel count to keep (in and out)
  "blank_mono": "<base chain name>",
  "blank_stereo": "<base chain name>",
  "rename_cue_lists": {"OLD": "NEW"},    optional
  "labels": {"57": "Main L"},            optional extra hardware channel labels
  "chains": [
    {"name": "1 Kick In", "inputs": [1]},
    {"name": "3-4 OH", "inputs": [3, 4], "colour": "ffff3333"},
    {"name": "17 Lead Vox", "inputs": [17], "template": "<base chain name with plugins>"},
    {"name": "31-32 Main", "inputs": [31, 32], "outputs": [31, 32], "delay_mode": 0}
  ]
}
"outputs" defaults to "inputs". "colour" is ARGB hex (ff + RRGGBB). "delay_mode"
sets ChainSettings DelayMode (default: keep the template's value). Hardware labels
default to "<n> <chain name without its number prefix>".

What the script removes from the base: every chain not used as a template, song
snapshots (GlobalSnapshot entries under GlobalSnapshots, they hold the old routing),
the UI component tree, plugin windows of removed plugins, and patch rows of removed
chains. It then checks that no integer property or key still points at a removed
chain or plugin, writes the file, and reads it back.
"""
import copy
import json
import random
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vt

HW_IN, HW_OUT = 1, 2
MIDI_CH = 4096


def chain_parts(chain):
    cs = next(chain.find("ChainSettings"))
    return cs, next(cs.find("ProcessorSettingsContainer"))


def plugins_of(chain):
    return list(next(chain.find("ChainPlugins")).find("Plugin"))


def main():
    if len(sys.argv) != 4 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help") else 2)
    src, plan_path, dst = sys.argv[1:4]
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("refusing to overwrite the base, write a new file")
    plan = json.load(open(plan_path))
    root, tail = vt.load(src)

    used = set()
    for node, _ in root.walk():
        for _, v in node.props:
            if v and v[0] in ("int", "int64"):
                used.add(v[1])
    rng = random.Random()

    def new_id():
        while True:
            i = rng.randrange(10_000_000, 200_000_000)
            if i not in used:
                used.add(i)
                return i

    chains = next(root.find("Chains"))
    by_name = {chain_parts(c)[1].get("name"): c for c in chains.kids}
    old_ids = {chain_parts(c)[1].get("id") for c in chains.kids}
    old_plugins = {p.get("pluginUid") for c in chains.kids for p in plugins_of(c)}
    for key in ("blank_mono", "blank_stereo"):
        nm = plan.get(key)
        if nm not in by_name:
            sys.exit("%s %r is not a chain in the base. Chains: %s" % (key, nm, sorted(by_name)))
        if plugins_of(by_name[nm]):
            sys.exit("%s %r has plugins, pick an empty chain" % (key, nm))
    io_n = int(plan.get("io", 64))

    new_chains, kept_plugins, reused = [], set(), set()
    for order, ch in enumerate(plan["chains"]):
        ins = [int(x) for x in ch["inputs"]]
        outs = [int(x) for x in ch.get("outputs", ins)]
        if len(ins) != len(outs) or len(ins) not in (1, 2):
            sys.exit("chain %r: inputs and outputs must both be 1 or 2 channels" % ch["name"])
        if max(ins + outs) > io_n:
            sys.exit("chain %r uses a channel above io=%d" % (ch["name"], io_n))
        tname = ch.get("template")
        if tname:
            if tname not in by_name:
                sys.exit("template %r is not a chain in the base" % tname)
            if tname in reused:
                sys.exit("template %r used twice; plugin ids would collide (copy it in LiveProfessor first)" % tname)
            reused.add(tname)
            tpl, reuse = by_name[tname], True
        else:
            tpl, reuse = by_name[plan["blank_stereo"] if len(ins) == 2 else plan["blank_mono"]], False
        c = copy.deepcopy(tpl)
        cs, psc = chain_parts(c)
        if not reuse:
            psc.set("id", ("int", new_id()))
        psc.set("name", ("str", ch["name"]))
        c.set("ChainViewOrder", ("int", order))
        if "delay_mode" in ch:
            cs.set("DelayMode", ("int", int(ch["delay_mode"])))
        if ch.get("colour"):
            cs.set("ChainColour", ("str", ch["colour"].lower()))
        for p in plugins_of(c):
            kept_plugins.add(p.get("pluginUid"))
        new_chains.append((c, ins, outs))
    chains.kids = [c for c, _, _ in new_chains]
    chain_ids = [chain_parts(c)[1].get("id") for c, _, _ in new_chains]
    gone = old_ids - set(chain_ids)
    gone_plugins = old_plugins - kept_plugins

    hw = next(root.find("AudioMidiHardware"))
    io = next(hw.find("IOdeviceProperties"))
    if plan.get("device"):
        io.set("inputDeviceName", ("str", plan["device"]))
        io.set("outputDeviceName", ("str", plan["device"]))
    mask = ((1 << io_n) - 1).to_bytes((io_n + 7) // 8, "little")
    io.set("ActiveInputChannels", ("bin", mask))
    io.set("ActiveOutputChannels", ("bin", mask))
    io.set("RequiredInputs", ("int", io_n))
    io.set("RequiredOutputs", ("int", io_n))
    label = {}
    for ch in plan["chains"]:
        base = re.sub(r"^\d+(-\d+)?\s+", "", ch["name"])
        ins = ch["inputs"]
        for k, h in enumerate(ins):
            label[int(h)] = base + ((" L", " R")[k] if len(ins) == 2 else "")
    label.update({int(k): v for k, v in plan.get("labels", {}).items()})
    for lst in ("AudioInputs", "AudioOutputs"):
        found = list(hw.find(lst))
        if not found:
            continue
        node = found[0]
        while 0 < len(node.kids) < io_n:
            k = copy.deepcopy(node.kids[-1])
            k.set("Index", ("int", len(node.kids)))
            node.kids.append(k)
        node.kids = node.kids[:io_n]
        for k in node.kids:
            n = k.get("Index") + 1
            k.set("UserLabel", ("str", ("%d %s" % (n, label.get(n, ""))).strip()))
    for ps in root.find("projectSettings"):
        ps.set("AutoSaveCounter", ("int", 1))

    gss = next(root.find("GlobalSnapshots"))
    gss.props = [p for p in gss.props if p[0] != "ActiveSnapshot"]
    gss.kids = [k for k in gss.kids if k.type != "GlobalSnapshot"]
    for gsf in gss.find("GlobalSnapshotFilter"):
        for sf in gsf.find("SnapshotFilter"):
            for pf in sf.find("PluginFilter"):
                pf.props = [(str(i), ("bool", True)) for i in chain_ids + sorted(kept_plugins)]
    for ui in root.find("uiComp"):
        ui.kids = []
    ren = plan.get("rename_cue_lists", {})
    for cls in root.find("CueLists"):
        for cl in cls.find("CueList"):
            if cl.get("CueName") in ren:
                cl.set("CueName", ("str", ren[cl.get("CueName")]))

    gs = next(k for k in root.kids if k.type == "GlobalSnapshot")
    gch = next(gs.find("Chains"))
    gch.kids = []
    gpl = next(gs.find("Plugins"))
    gpl.kids = []
    for c, _, _ in new_chains:
        cs, psc = chain_parts(c)
        gch.kids.append(vt.Node("Chain", [("ChainId", ("int64", psc.get("id")))] + copy.deepcopy(cs.props),
                                [copy.deepcopy(k) for k in cs.kids]))
        for p in plugins_of(c):
            g = vt.Node("Plugin", [("PluginId", ("int64", p.get("pluginUid")))],
                        [copy.deepcopy(k) for k in p.kids if k.type != "bussesLayout"])
            for s, _ in g.walk():
                if s.type == "PluginSnapshot":
                    t = next((v[0] for k, v in s.props if k == "uId" and v), "int64")
                    s.set("uId", (t, new_id()))
            gpl.kids.append(g)

    ap = next(gs.find("AudioPatch"))
    keep = []
    for o in ap.kids:
        nid, cid = o.get("nodeId"), o.get("channelId")
        if nid in gone or nid in chain_ids:
            continue
        if nid == HW_IN and io_n <= cid < MIDI_CH:
            continue
        o.kids = [] if nid == HW_IN and cid < MIDI_CH else [p for p in o.kids if p.get("inputNodeId") not in gone]
        keep.append(o)
    hw_in = {o.get("channelId"): o for o in keep if o.get("nodeId") == HW_IN and o.get("channelId") < MIDI_CH}

    def point(on, oc, inn, ic):
        return vt.Node("point", [("outputNodeId", ("int64", on)), ("outputChannelId", ("int", oc)),
                                 ("inputNodeId", ("int64", inn)), ("inputChannelId", ("int", ic)),
                                 ("isMidi", ("bool", False))])

    for (c, ins, outs), cid in zip(new_chains, chain_ids):
        for k, h in enumerate(ins):
            if h - 1 not in hw_in:
                hw_in[h - 1] = vt.Node("outputs", [("nodeId", ("int64", HW_IN)), ("channelId", ("int", h - 1))])
                keep.append(hw_in[h - 1])
            hw_in[h - 1].kids.append(point(HW_IN, h - 1, cid, k))
        for k, h in enumerate(outs):
            keep.append(vt.Node("outputs", [("nodeId", ("int64", cid)), ("channelId", ("int", k))],
                                [point(cid, k, HW_OUT, h - 1)]))
    ap.kids = keep
    mp = next(gs.find("MidiPatch"))
    mp.kids = [o for o in mp.kids if o.get("nodeId") not in gone] + \
              [vt.Node("outputs", [("nodeId", ("int64", i)), ("channelId", ("int", MIDI_CH))]) for i in chain_ids]

    for node, _ in root.walk():
        if node.type == "storedViewSetItems":
            node.kids = [k for k in node.kids if k.get("storedViewSetItemPluginId") in kept_plugins]

    wv = next(next(root.find("WireView")).find("Nodes"))
    sysn = [k for k in wv.kids if k.get("NodeId") not in gone and k.get("NodeId") not in chain_ids
            and k.get("NodeId") not in gone_plugins]
    cols = (len(chain_ids) + 13) // 14
    for k in sysn:
        if k.get("NodeId") == HW_OUT:
            k.set("XPos", ("int", 220 + 215 * cols))
            k.set("YPos", ("int", 5))
    wv.kids = sysn + [vt.Node("WireViewNode", [("NodeId", ("int64", cid)), ("XPos", ("int", 220 + 215 * (i // 14))),
                                               ("YPos", ("int", 5 + 117 * (i % 14)))])
                      for i, cid in enumerate(chain_ids)]

    dead = gone | gone_plugins
    for node, _ in root.walk():
        for k, v in node.props:
            if v and v[0] in ("int", "int64") and v[1] in dead:
                sys.exit("dangling reference %s.%s=%s, not writing" % (node.type, k, v[1]))
        if any(k.lstrip("-").isdigit() and int(k) in dead for k, _ in node.props):
            sys.exit("dangling key in %s, not writing" % node.type)
    vt.save(dst, root, tail)
    back, _ = vt.load(dst)
    assert vt.wr_node(back) == vt.wr_node(root), "read-back mismatch"
    print("%s: %d chains, %d plugins kept, %d chains and %d plugins removed"
          % (dst, len(chain_ids), len(kept_plugins), len(gone), len(gone_plugins)))


if __name__ == "__main__":
    main()
