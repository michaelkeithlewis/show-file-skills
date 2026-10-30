#!/usr/bin/env python3
"""MixRack (DM) local preamps in a dLive show: 'StageBox Analogue Input, Number N' = [01][gain s16 dB*256][pad][48V]
(cAnalogueInput::GetStatus @0x1004f86a0; factory default 01 1b00 00 00 = 27 dB, pad off, 48V off).
Preamps are scene-safe by default on the console, but every StageBox scene carries them, so all are written.

usage:
  dlive_preamps.py dump <show.tar.gz>
  dlive_preamps.py set <show.tar.gz> <out.tar.gz> [--48v-on LIST] [--48v-off LIST] [--pad-on LIST] [--pad-off LIST]
                       [--gain SOCKETS=DB ...]
LIST like 1,2,4-6. Never put PASSIVE ribbon sockets (4038, R-121) in --48v-on; active ribbons (sE VR2) need it."""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dlive_mix import read_show, write_show, inner, repack_inner, SceneFile

def ranges(s):
    out = set()
    for part in s.split(","):
        a, _, b = part.partition("-"); out |= set(range(int(a), int(b or a) + 1))
    return out

LABEL = re.compile(r"StageBox Analogue Input, Number (\d+)$")

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "dump":
        _, F = read_show(a[1])
        sc = SceneFile(next(iter(inner(F[next(n for n in F if n.endswith("StageBoxScene65535.tar.gz"))])[1].values())))
        for l, p in sc.sections:
            m = LABEL.match(l)
            if m: print("socket %2s  gain %5.1f dB  pad %d  48V %d" % (m.group(1), struct.unpack(">h", p[1:3])[0] / 256, p[3], p[4]))
    elif len(a) >= 3 and a[0] == "set":
        def opt(f): return ranges(a[a.index(f) + 1]) if f in a else set()
        on48, off48, padon, padoff = opt("--48v-on"), opt("--48v-off"), opt("--pad-on"), opt("--pad-off")
        assert not (on48 & off48) and not (padon & padoff), "socket in both on and off lists"
        gains = {}
        if "--gain" in a:
            for x in a[a.index("--gain") + 1:]:
                if x.startswith("--"): break
                s, db = x.split("="); db = float(db); assert 0 <= db <= 60, "gain %s out of range" % db
                for k in ranges(s): gains[k] = db
        M, F = read_show(a[1]); n = 0
        for name in sorted(F):
            if "/Scenes/StageBoxScene" not in name: continue
            ms, inn = inner(F[name]); (dn,) = inn
            if b"Channel Mapper\x00" not in inn[dn]: continue
            sc = SceneFile(inn[dn])
            for s in sc.sections:
                m = LABEL.match(s[0])
                if not m: continue
                k = int(m.group(1)); b = bytearray(s[1])
                if k in on48: b[4] = 1
                if k in off48: b[4] = 0
                if k in padon: b[3] = 1
                if k in padoff: b[3] = 0
                if k in gains: struct.pack_into(">h", b, 1, int(round(gains[k] * 256)))
                s[1] = bytes(b)
            inn[dn] = sc.to_bytes(); F[name] = repack_inner(ms, inn); n += 1
        write_show(M, F, a[2]); print("preamps written in %d scenes -> %s" % (n, a[2]))
    else:
        sys.exit(__doc__)
