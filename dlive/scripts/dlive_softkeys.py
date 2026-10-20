#!/usr/bin/env python3
"""dLive SoftKeys ('Surface Soft Controls' in each surface scene).
Format (cSurfaceSoftControlManager::GetStatus @0x1004d8f00): [02][u16 26][u16 26] then 52 settings
(two identical sets of 26 keys) then a tail kept as is. Setting = [function][01][LED colour 0-7][version][payload].
Function ids from the cXxxSoftSetting constructors in Director V2.12.

usage:
  dlive_softkeys.py dump <show.tar.gz>
  dlive_softkeys.py set <show.tar.gz> <out.tar.gz> KEY=SPEC [KEY=SPEC ...]
SPEC (only encodings seen in Director-saved shows):
  unused | mute:StFX1 | mute:UFX2 | mute:Ip18 | mute:DCA3 | abcd:A..D | talkback:<group>[:latch] | vsc:1|2
  | mf:<macro on>/<macro off> | colour suffix @0-7
  e.g. 4=unused 14=abcd:B@2 16=talkback:1:latch 1=mute:StFX1@4
Applies to both key sets in every surface scene."""
import re, struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FN = {0x00: "unused", 0x02: "library", 0x04: "mute", 0x05: "PAFL", 0x0c: "tap tempo", 0x0d: "scene recall",
      0x0e: "custom MIDI", 0x0f: "PAFL clear", 0x10: "scene go", 0x11: "scene control", 0x12: "0x12",
      0x17: "spills", 0x18: "AMM", 0x1e: "0x1e", 0x1f: "talkback", 0x24: "ABCD set all", 0x25: "ABCD set channel",
      0x2b: "virtual soundcheck", 0x2d: "talkback additive", 0x33: "multifunction"}
STRIP = {1: "Ip", 2: "Grp", 3: "StGrp", 4: "Aux", 5: "StAux", 6: "FX", 7: "StFX", 8: "Main", 0x0a: "Mtx",
         0x0b: "StMtx", 0x0c: "FXRtn", 0x0d: "DCA", 0x0e: "Mon", 0x13: "UFX", 0x14: "UFXRtn"}
STRIP_BY_NAME = {v.lower(): k for k, v in STRIP.items()}
FIXED = {0x00: 4, 0x1e: 4, 0x0c: 8, 0x0d: 6, 0x10: 5, 0x24: 5, 0x2b: 5, 0x1f: 6, 0x12: 12}

def parse(p):
    assert p[0] == 2, "unknown SoftKey block version %d" % p[0]
    n1, n2 = struct.unpack(">HH", p[1:5]); o = 5; out = []
    while len(out) < n1 + n2:
        f = p[o]
        if f == 0x33:
            e = o + 5; s1 = p[e:p.index(0, e)]; e = p.index(0, e) + 1; s2 = p[e:p.index(0, e)]; e = p.index(0, e) + 1
            out.append((o, p[o:e], "multifunction %r / %r" % (s1.decode(), s2.decode()))); o = e; continue
        n = FIXED.get(f, 6); raw = p[o:o + n]
        if f in (0x04, 0x05) and n == 6: d = "%s %s%d" % (FN[f], STRIP.get(raw[4], hex(raw[4])), raw[5] + 1)
        elif f == 0x1f: d = "talkback group %d%s" % (raw[4] + 1, " latch" if raw[5] else "")
        elif f == 0x24: d = "ABCD set all -> %s" % "?ABCD"[raw[4]]
        elif f == 0x2b: d = "virtual soundcheck mode %d" % raw[4]
        elif f == 0x0d: d = "scene recall %d" % struct.unpack(">H", raw[4:6])[0]
        else: d = FN.get(f, "0x%02x" % f) + (" " + raw[4:].hex() if len(raw) > 4 else "")
        out.append((o, raw, d)); o += n
    return out, o

def encode(spec):
    colour = 0
    if "@" in spec: spec, c = spec.split("@"); colour = int(c)
    parts = spec.split(":"); kind = parts[0].lower()
    if kind == "unused": return bytes([0x00, 0x01, 0x00, 0x01])
    if kind == "mute":
        m = re.fullmatch(r"([A-Za-z]+)(\d+)", parts[1]); t = STRIP_BY_NAME[m.group(1).lower()]
        return bytes([0x04, 0x01, colour, 0x01, t, int(m.group(2)) - 1])
    if kind == "abcd": return bytes([0x24, 0x01, colour, 0x01, "ABCD".index(parts[1].upper()) + 1])
    if kind == "talkback":
        return bytes([0x1f, 0x01, colour, 0x02, int(parts[1]) - 1, 1 if len(parts) > 2 and parts[2] == "latch" else 0])
    if kind == "vsc":       # virtual soundcheck key, as in a Director-saved show (mode 1 record/live, 2 playback)
        return bytes([0x2b, 0x01, colour, 0x01, int(parts[1])])
    if kind == "mf":        # multifunction key: mf:<macro on>/<macro off> (latching, Director's 01 00 header)
        on, off = spec.split(":", 1)[1].split("/")
        for x in (on, off): assert len(x) <= 16 and all(32 <= ord(c) < 127 for c in x), x
        return bytes([0x33, 0x01, colour, 0x01, 0x00]) + on.encode() + b"\0" + off.encode() + b"\0"
    raise ValueError("unsupported SoftKey spec %r" % spec)

def rebuild(p, changes):
    out, end = parse(p)
    n1 = struct.unpack(">H", p[1:3])[0]
    body = b"".join(changes.get((k % n1) + 1, raw) for k, (o, raw, d) in enumerate(out))
    return p[:5] + body + p[end:]

def surface_scenes(files):
    from dlive_mix import inner
    for n in sorted(files):
        if "/Scenes/SurfaceScene" in n:
            ms, inn = inner(files[n])
            for dn, d in inn.items():
                if b"Surface Soft Controls\x00" in d: yield n, ms, inn, dn, d

if __name__ == "__main__":
    from dlive_mix import read_show, write_show, repack_inner, SceneFile
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "dump":
        _, F = read_show(a[1])
        for n, ms, inn, dn, d in surface_scenes(F):
            if n.endswith("65535.tar.gz"):
                out, end = parse(SceneFile(d).get("Surface Soft Controls"))
                for k, (o, raw, desc) in enumerate(out[:26]): print("%2d  colour %d  %s" % (k + 1, raw[2], desc))
    elif len(a) >= 4 and a[0] == "set":
        changes = {int(k): encode(v) for k, v in (x.split("=", 1) for x in a[3:])}
        M, F = read_show(a[1]); n_sc = 0
        for n, ms, inn, dn, d in list(surface_scenes(F)):
            sc = SceneFile(d); sc.set("Surface Soft Controls", rebuild(sc.get("Surface Soft Controls"), changes))
            inn[dn] = sc.to_bytes(); F[n] = repack_inner(ms, inn); n_sc += 1
        write_show(M, F, a[2]); print("updated keys %s in %d surface scenes -> %s" % (sorted(changes), n_sc, a[2]))
    else:
        sys.exit(__doc__)
