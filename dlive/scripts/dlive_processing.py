#!/usr/bin/env python3
"""Input-channel processing in a dLive show: reset to Director defaults, or copy from another show by a
channel map (e.g. last tour's show as the starting point for a new artist, matched by instrument).

usage:
  dlive_processing.py dump <show.tar.gz> <ch>
  dlive_processing.py reset <show.tar.gz> <out.tar.gz> [--channels 1-128]
  dlive_processing.py copy <show.tar.gz> <source.tar.gz> <map.json> <out.tar.gz>
                           [--trims] [--no-sends] [--clear-unmapped 1-64,121-128]

What moves (per channel): preamp model, HPF, LPF, gate + side chain, SCF gate, PEQ, compressor + side chain,
delay, insert 1/2 in/out (+ trim with --trims). copy also moves insert loops to FX/UFX/Dyn8 units (first
destination channel per source channel owns the unit; I/O-port outboard inserts are skipped), remaps keyed
side chains through the map, and copies stereo FX / UFX / mono aux sends (not stereo aux = IEM mixes).
reset also clears input insert patching. Direct Output and stereo image are never touched.
Applied to every StageBox scene. Defaults (input_defaults.json) are pair-aware: linked stereo channels use
Director's stereo variant.
map.json: {"1": 1, "6": 4, "49": 48}  destination ch -> source ch."""
import json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from dlive_mix import read_show, write_show, inner, repack_inner, SceneFile, cm_parse, cm_build, CM_DEF_MONO, CM_DEF_ST
from dlive_patch import Patch, BLOCKS, NONE

DEF = json.load(open(os.path.join(HERE, "input_defaults.json")))
FAMS = ["Preamp Model", "Highpass Filter", "Lowpass Filter", "Gate", "Gate side chain source", "SCF Gate",
        "Parametric EQ", "Compressor", "Compressor side chain source", "Delay", "Insert 1", "Insert 2"]
IO_TYPES = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06}

def ranges(s):
    out = set()
    for part in s.split(","):
        a, _, b = part.partition("-"); out |= set(range(int(a), int(b or a) + 1))
    return out

def proc_index(sections):
    idx = {}
    for i, (l, p) in enumerate(sections):
        m = re.match(r"(.*?),? ?Input Channel (\d+)$", l)
        if m: idx[(m.group(1), int(m.group(2)))] = i
    return idx

def pairs(files):
    flags = files["Show/InputConfig/InputConfig.dat"].decode().split()[1:]
    return {ch for k in range(64) if flags[k] == "1" for ch in (2 * k + 1, 2 * k + 2)}

def default(fam, ch, linked):
    if linked and fam in DEF["stereo"]: return bytes.fromhex(DEF["stereo"][fam])
    v = DEF["mono"][fam]
    return bytes.fromhex(v[:4]) + bytes([ch - 1]) if v.endswith("SELF") else bytes.fromhex(v)

def stagebox_scenes(files):
    for n in sorted(files):
        if "/Scenes/StageBoxScene" in n:
            ms, inn = inner(files[n]); (dn,) = inn
            if b"Channel Mapper\x00" in inn[dn]: yield n, ms, inn, dn

def do_reset(src, out, chans, trims=True):
    M, F = read_show(src); linked = pairs(F); fams = FAMS + (["Digital Attenuator"] if trims else []); n = 0
    for name, ms, inn, dn in list(stagebox_scenes(F)):
        sc = SceneFile(inn[dn]); idx = proc_index(sc.sections)
        for ch in chans:
            for fam in fams:
                sc.sections[idx[(fam, ch)]][1] = default(fam, ch, ch in linked)
        p = Patch(sc.to_bytes())
        for blk in ("Ip Ins A return", "Ip Ins B return"):
            off = BLOCKS[blk][0]
            for ch in chans: p._set_ref(off + 3 * (ch - 1), NONE)
        for unit in ("FX rack input", "UFX rack input", "Dyn unit input"):
            off, cnt = BLOCKS[unit]
            for i in range(cnt):
                t, x = p._ref(off + 3 * i)
                if t in (0x08, 0x09) and x + 1 in chans: p._set_ref(off + 3 * i, NONE)
        inn[dn] = bytes(p.d); F[name] = repack_inner(ms, inn); n += 1
    write_show(M, F, out); return n

def do_copy(dst, src_show, cmap, out, trims=False, sends=True, clear_unmapped=()):
    _, T = read_show(src_show)
    s_raw = next(iter(inner(T[next(n for n in T if n.endswith("StageBoxScene65535.tar.gz"))])[1].values()))
    s_sc = SceneFile(s_raw); s_idx = proc_index(s_sc.sections); s_patch = Patch(s_raw)
    _, s_cc, s_ch = cm_parse(s_sc.get("Input Mixer"))
    first = {}
    for d in sorted(cmap): first.setdefault(cmap[d], d)
    fams = FAMS + (["Digital Attenuator"] if trims else [])
    M, F = read_show(dst); n = 0
    for name, ms, inn, dn in list(stagebox_scenes(F)):
        sc = SceneFile(inn[dn]); idx = proc_index(sc.sections)
        for d, s in cmap.items():
            for fam in fams:
                p = s_sc.sections[s_idx[(fam, s)]][1]
                if "side chain" in fam and p[1] == 1:
                    k = p[2] + 1; p = p[:2] + bytes([(d if k == s else first.get(k, d)) - 1])
                if fam.startswith("Insert") and first[s] != d:
                    ret = s_patch.block("Ip Ins A return" if fam == "Insert 1" else "Ip Ins B return")[s - 1]
                    if ret != NONE: p = p[:1] + b"\x00" + p[2:]
                sc.sections[idx[(fam, d)]][1] = p
        if sends:
            hdr, cc, chans = cm_parse(sc.get("Input Mixer"))
            for ch in set(cmap) | set(clear_unmapped):
                c = chans[ch - 1]
                if ch in cmap:
                    s = s_ch[cmap[ch] - 1]
                    c["sFX"] = [s["sFX"][k] if k < s_cc["sFX"] else CM_DEF_ST for k in range(cc["sFX"])]
                    c["mAux"] = [s["mAux"][k] if k < s_cc["mAux"] else CM_DEF_MONO for k in range(cc["mAux"])]
                    c["rest"] = c["rest"][:47] + s["rest"][47:87]
                else:
                    c["sFX"] = [CM_DEF_ST] * cc["sFX"]; c["mAux"] = [CM_DEF_MONO] * cc["mAux"]
                    c["rest"] = c["rest"][:47] + CM_DEF_ST * 8
            sc.set("Input Mixer", cm_build(hdr, cc, chans))
        p = Patch(sc.to_bytes())
        for k, blk in ((1, "Ip Ins A return"), (2, "Ip Ins B return")):
            styp = 0x08 if k == 1 else 0x09
            for s, d in first.items():
                ret = s_patch.block(blk)[s - 1]
                if ret == NONE or ret[0] in IO_TYPES: continue
                p._set_ref(BLOCKS[blk][0] + 3 * (d - 1), ret)
                for unit in ("FX rack input", "UFX rack input", "Dyn unit input"):
                    uoff, ucnt = BLOCKS[unit]
                    for i in range(ucnt):
                        if s_patch._ref(uoff + 3 * i) == (styp, s - 1): p._set_ref(uoff + 3 * i, (styp, d - 1))
        inn[dn] = bytes(p.d); F[name] = repack_inner(ms, inn); n += 1
    write_show(M, F, out); return n

if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda f, d=None: a[a.index(f) + 1] if f in a else d
    if len(a) == 3 and a[0] == "dump":
        _, F = read_show(a[1]); ch = int(a[2])
        sc = SceneFile(next(iter(inner(F[next(n for n in F if n.endswith("StageBoxScene65535.tar.gz"))])[1].values())))
        for (fam, c), i in sorted(proc_index(sc.sections).items()):
            if c == ch: print("%-30s %s" % (fam, sc.sections[i][1].hex()))
    elif len(a) >= 3 and a[0] == "reset":
        n = do_reset(a[1], a[2], ranges(opt("--channels", "1-128")))
        print("reset input processing in %d scenes -> %s" % (n, a[2]))
    elif len(a) >= 5 and a[0] == "copy":
        cmap = {int(k): int(v) for k, v in json.load(open(a[3])).items()}
        n = do_copy(a[1], a[2], cmap, a[4], trims="--trims" in a, sends="--no-sends" not in a,
                    clear_unmapped=ranges(opt("--clear-unmapped")) - set(cmap) if opt("--clear-unmapped") else ())
        print("copied processing for %d channels into %d scenes -> %s" % (len(cmap), n, a[4]))
    else:
        sys.exit(__doc__)
