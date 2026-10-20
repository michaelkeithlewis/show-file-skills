#!/usr/bin/env python3
"""Check that the top-level GlobalSnapshot's Chains and Plugins derive exactly from the Chains list.

usage: check_derive.py FILE.rack2

LiveProfessor stores the chains twice: once under the root Chains node and once as the
current state inside the top-level GlobalSnapshot. The rule tested here:
  GlobalSnapshot/Chains/Chain  = ChainId (int64, the ProcessorSettingsContainer id)
                                 + the ChainSettings props and children
  GlobalSnapshot/Plugins/Plugin = PluginId (int64, the pluginUid)
                                 + the Plugin children without bussesLayout
lp_generate.py builds the current state with this rule. Run this on your own saved
sessions to confirm the rule holds for your LiveProfessor version. PluginSnapshot
uId and updateTime are ignored: the current-state copy gets its own values.
Exit code 0 = every chain and plugin matches.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vt  # noqa: E402


def strip_uid(node):
    for s, _ in node.walk():
        if s.type == "PluginSnapshot":
            s.props = [(k, v) for k, v in s.props if k not in ("uId", "updateTime")]
    return node


def main(path):
    n, _ = vt.load(path)
    chains = next(n.find("Chains"))
    gs = next(k for k in n.kids if k.type == "GlobalSnapshot")
    gch = next(gs.find("Chains"))
    gpl = next(gs.find("Plugins"))
    bad = 0

    def eq(a, b):
        return vt.wr_node(a) == vt.wr_node(b)

    for i, c in enumerate(chains.find("Chain")):
        cs = next(c.find("ChainSettings"))
        psc = next(cs.find("ProcessorSettingsContainer"))
        d = vt.Node("Chain", [("ChainId", ("int64", psc.get("id")))] + copy.deepcopy(cs.props),
                    [copy.deepcopy(k) for k in cs.kids])
        ok = i < len(gch.kids) and eq(d, gch.kids[i])
        bad += not ok
        print("chain %-30r %s" % (psc.get("name"), "ok" if ok else "MISMATCH"))
    cp = [p for c in chains.find("Chain") for p in next(c.find("ChainPlugins")).find("Plugin")]
    if len(cp) != len(gpl.kids):
        print("plugin count %d in chains, %d in GlobalSnapshot" % (len(cp), len(gpl.kids)))
        bad += 1
    for p, a in zip(cp, gpl.kids):
        d = vt.Node("Plugin", [("PluginId", ("int64", p.get("pluginUid")))],
                    [copy.deepcopy(k) for k in p.kids if k.type != "bussesLayout"])
        ok = eq(strip_uid(d), strip_uid(copy.deepcopy(a)))
        bad += not ok
        print("plugin %-29r %s" % (p.get("pluginTypeName"), "ok" if ok else "MISMATCH"))
    print("all match" if not bad else "%d mismatch(es)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) == 2 else 2)
    sys.exit(main(sys.argv[1]))
