#!/usr/bin/env python3
"""Dump how a dLive show builds ear mixes: names of inputs/aux/FX/UFX, every ON send into aux / FX / UFX
from inputs, FX returns and UFX returns (level, pre/post, pan), and mix masters.
usage: dlive_ears.py show.tar.gz [--dest sAux,mAux,mFX,sFX,UFX]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dlive_mix import read_show, inner, SceneFile, cm_parse, mm_parse
from dlive_scene import Scene

def live(files):
    n = next(n for n in files if n.endswith("Scenes/StageBoxScene65535.tar.gz"))
    return next(iter(inner(files[n])[1].values()))

def names_any(files, kind):
    for n in sorted(files):
        if "/Scenes/" not in n: continue
        try:
            d = next(iter(inner(files[n])[1].values()))
            return [x[0] for x in Scene(d).names(kind)]
        except Exception:
            continue
    return []

def fmt(b):
    lv = struct.unpack(">h", b[2:4])[0]
    s = ("pre " if b[1] else "post") + (" -inf" if lv <= -32000 else "%+5.1f" % (lv / 256))
    if len(b) == 5: s += " p%+d" % (b[4] - 37)
    return s

def main(path, dests):
    members, files = read_show(path)
    sc = SceneFile(live(files))
    N = {k: names_any(files, v) for k, v in dict(ip="Input Channel", maux="Mono Aux Channel", saux="Stereo Aux Channel",
         mfx="Mono FX Send Channel", sfx="Stereo FX Send Channel", ufx="Stereo AHFX Send Channel",
         fxr="FX Return Channel", ufxr="AHFX Return Channel").items()}
    for k in ("maux", "saux", "mfx", "sfx", "ufx"):
        print(k, N[k])
    out = []
    for lab, nk in (("Input Mixer", "ip"), ("FX Return Mixer", "fxr"), ("AHFX Return Mixer", "ufxr")):
        h, c, chans = cm_parse(sc.get(lab))
        for i, ch in enumerate(chans):
            k = i if nk == "ip" else i // 2                 # FX/UFX return mixers hold L/R rows per strip
            nm = (N[nk][k] if k < len(N[nk]) else "?") + ("" if nk == "ip" else "LR"[i % 2])
            row = []
            for kind, nkd in (("mAux", "maux"), ("sAux", "saux"), ("mFX", "mfx"), ("sFX", "sfx")):
                if kind not in dests: continue
                for j, b in enumerate(ch[kind]):
                    if b[0] and struct.unpack(">h", b[2:4])[0] > -32000:
                        dn = N[nkd][j] if j < len(N[nkd]) else ""
                        row.append("%s%d(%s)=%s" % (kind, j + 1, dn, fmt(b)))
            if "UFX" in dests and len(ch["rest"]) > 47:
                for j in range(8):
                    b = ch["rest"][47 + 5 * j:52 + 5 * j]
                    if b[0] and struct.unpack(">h", b[2:4])[0] > -32000:
                        row.append("UFX%d(%s)=%s" % (j + 1, N["ufx"][j] if j < len(N["ufx"]) else "", fmt(b)))
            if row:
                out.append("%s %3d %-8s %s" % (lab[:5], i + 1, nm, "  ".join(row)))
    print("\n".join(out))
    hdr, c, mixes = mm_parse(sc.get("Mix Mixer"))
    for key, m in mixes.items():
        if key[0] in ("mAux", "sAux"):
            print(key, "fader %+.1f" % (struct.unpack(">h", m["ch"][3:5])[0] / 256), "mute", m["ch"][2])

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    d = "sAux,mAux,mFX,sFX,UFX"
    if "--dest" in sys.argv: d = sys.argv[sys.argv.index("--dest") + 1]
    main(sys.argv[1], d.split(","))
