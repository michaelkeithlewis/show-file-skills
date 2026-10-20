#!/usr/bin/env python3
"""dLive surface fader layout ('Channel Left/Middle/Right Bank Switcher' in each surface scene):
[01][strips per layer] + 6 layers x strips x [strip type][index]. CTi1500 / C1500 use the left bank only
(12 strips x 6 layers); larger surfaces add middle/right banks.
Strip types: Ip 01, Grp 02, StGrp 03, Aux 04, StAux 05, FX 06, StFX 07, Main 08, Mtx 0a, StMtx 0b,
FXRtn 0c, DCA 0d, Mon 0e, 0f (seen, unnamed), UFX 13, UFXRtn 14, empty 00. Index = number within the type - 1.

usage:
  dlive_layout.py dump <show.tar.gz>
  dlive_layout.py set <show.tar.gz> <layout.json> <out.tar.gz>
layout.json: {"bank": "Left", "layers": [["DCA 1", "DCA 2", ..., "-"], ... 6 layers]}  (names: "Ip 18",
"Grp 1", "StGrp 2", "Aux 3", "StAux 1", "Main 1", "Mtx 2", "StMtx 1", "FXRtn 3", "UFXRtn 1", "DCA 12", "-")."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dlive_mix import read_show, write_show, inner, repack_inner, SceneFile
T = {0x01: "Ip", 0x02: "Grp", 0x03: "StGrp", 0x04: "Aux", 0x05: "StAux", 0x06: "FX", 0x07: "StFX", 0x08: "Main",
     0x0a: "Mtx", 0x0b: "StMtx", 0x0c: "FXRtn", 0x0d: "DCA", 0x0e: "Mon", 0x13: "UFX", 0x14: "UFXRtn"}
BYNAME = {v.lower(): k for k, v in T.items()}

def strip(name):
    if name.strip() in ("-", ""): return (0, 0)
    kind, num = name.rsplit(" ", 1)
    return (BYNAME[kind.lower()], int(num) - 1)

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "dump":
        _, F = read_show(a[1])
        sc = SceneFile(next(iter(inner(F[next(n for n in F if n.endswith("SurfaceScene65535.tar.gz"))])[1].values())))
        for bank in ("Left", "Middle", "Right"):
            p = sc.get("Channel %s Bank Switcher" % bank); n = p[1]
            if len(p) <= 2: print(bank, "bank: unused"); continue
            print(bank, "bank (%d strips x 6 layers)" % n)
            for L in range(6):
                row = [p[2 + 2 * (L * n + k):4 + 2 * (L * n + k)] for k in range(n)]
                print("  ", "ABCDEF"[L], " | ".join("-" if t == 0 else "%s %d" % (T.get(t, hex(t)), i + 1) for t, i in row))
    elif len(a) == 4 and a[0] == "set":
        spec = json.load(open(a[2])); bank = spec.get("bank", "Left"); layers = spec["layers"]
        n = len(layers[0]); assert len(layers) == 6 and all(len(L) == n for L in layers), "need 6 layers of equal length"
        body = bytes([0x01, n]) + b"".join(bytes(strip(s)) for L in layers for s in L)
        M, F = read_show(a[1]); k = 0
        for name in sorted(F):
            if "/Scenes/SurfaceScene" not in name: continue
            ms, inn = inner(F[name]); (dn,) = inn
            if b"Channel %s Bank Switcher\x00" % bank.encode() not in inn[dn]: continue
            sc = SceneFile(inn[dn]); old = sc.get("Channel %s Bank Switcher" % bank)
            assert len(old) in (2, len(body)), "bank size differs from the show (%d vs %d)" % (len(old), len(body))
            sc.set("Channel %s Bank Switcher" % bank, body)
            inn[dn] = sc.to_bytes(); F[name] = repack_inner(ms, inn); k += 1
        write_show(M, F, a[3]); print("%s bank written in %d surface scenes -> %s" % (bank, k, a[3]))
    else:
        sys.exit(__doc__)
