#!/usr/bin/env python3
"""Read Logic Pro ProjectData (strips, inserts, routing) and add latency-alignment delays.

ProjectData lives inside a project package:
  <Song>.logicx/Alternatives/000/ProjectData
Format notes: ../references/PROJECTDATA.md. Work on a copy of the project, never the original.

Commands:
  logic_pd.py strips   ProjectData [--lat lat.txt]
      One line per channel strip: index, name, input, output, inserts (with latency if
      --lat is given).
  logic_pd.py extract  ProjectData OUTDIR
      Write the ClassInfo plist of every AU insert to OUTDIR/NNN_<offset>.plist.
      Feed OUTDIR to aulat.swift on a Mac to measure each plugin's real latency (lat.txt).
  logic_pd.py paths    ProjectData --lat lat.txt [--main-out 73] [--json paths.json]
      Follow every audio strip through its buses and aux strips to the main output and
      sum the measured insert latency on the way.
  logic_pd.py plan     paths.json [--target N] [--json plan.json]
      Delay per strip so every path lands on the same total (default target = the
      longest path).
  logic_pd.py add-delay ProjectData OUT plan.json
      Insert Apple's AUSampleDelay at insert 1 of each strip in plan.json, set to the
      planned samples. Existing inserts move down one slot. Writes a new file.
"""
import argparse
import collections
import json
import os
import plistlib
import re
import struct
import sys
import uuid

HDR = 24
CH_HDR = 36
NO_SLOT = 0xFFFFFFFF
FIRST_INSERT, LAST_INSERT = 5, 15
SIG_AUDIO = b"\xab\xf7\xd3\xcf"
SIG_AUX = b"\xab\xf5\xd7\xcf"
NONE16 = 0xFFFF


def load(path):
    d = open(path, "rb").read()
    if len(d) < HDR or struct.unpack_from("<Q", d, 16)[0] != len(d) - HDR:
        sys.exit("%s: header length field does not match the file size, not a ProjectData file?" % path)
    return d


def chunks(d):
    """Yield (offset, tag, strip, slot, payload) for every chunk."""
    p = HDR
    while p < len(d):
        tag = d[p:p + 4]
        sz = struct.unpack_from("<Q", d, p + 28)[0]
        if p + CH_HDR + sz > len(d):
            sys.exit("chunk at %d runs past the end of the file" % p)
        yield p, tag, struct.unpack_from("<I", d, p + 14)[0], struct.unpack_from("<I", d, p + 18)[0], d[p + CH_HDR:p + CH_HDR + sz]
        p += CH_HDR + sz


def io_name(v, is_input=False, live=False):
    if v == NONE16:
        return "none"
    if live:
        return "In%d" % (v + 1)
    if 33 <= v < 32 + 256:
        return "Bus%d" % (v - 32)
    return "out%d" % v if not is_input else "in%d" % v


def read_lat(path):
    """lat.txt lines from aulat.swift: NNN_<offset>.plist SUBT MANU ... samples=N | NOTFOUND."""
    lat = {}
    if not path:
        return lat
    for line in open(path):
        m = re.match(r"\d+_(\d+)\.plist (\S+) \S+ (?:.*samples=(\d+)|NOTFOUND)", line)
        if m:
            lat[int(m.group(1))] = (m.group(2), int(m.group(3)) if m.group(3) else None)
    return lat


def au_name(chunk_bytes):
    return chunk_bytes[0x9C:0xA8].split(b"\0")[0].decode("latin1", "replace")


def parse(d, lat):
    """strips: {idx: dict(name, sig, inn, out, off)}; inserts: {idx: [(slot, name, latency|None|'native', plist_off)]}"""
    strips, inserts = {}, collections.defaultdict(list)
    for p, tag, ch, slot, pl in chunks(d):
        if tag == b"OCuA" and slot == NO_SLOT and len(pl) >= 0x60:
            out, inn = struct.unpack_from("<HH", pl, 0x5C)
            strips[ch] = dict(name=pl[0x3D:0x4C].split(b"\0")[0].decode("latin1", "replace"),
                              sig=pl[0x4C:0x50], kind=pl[0x50], inn=inn, out=out, off=p)
        elif tag == b"UCuA" and FIRST_INSERT <= slot <= LAST_INSERT:
            x = pl.find(b"<?xml")
            if x > 0:
                off = p + CH_HDR + x
                nm = au_name(d[p:p + 0xB0])
                L = lat[off][1] if off in lat else None
                inserts[ch].append((slot, nm, L, off))
            else:
                found = re.findall(rb"[A-Za-z][\x20-\x7e]{3,}", pl[0x8C:0xB0])
                inserts[ch].append((slot, (found[:1] or [b"?"])[0].decode(), "native", None))
    return strips, inserts


def total(ins):
    return sum(l for _, _, l, _ in ins if isinstance(l, int))


def cmd_strips(a):
    d = load(a.projectdata)
    strips, inserts = parse(d, read_lat(a.lat))
    for ch in sorted(set(strips) | set(inserts)):
        s = strips.get(ch)
        if s:
            live = s["sig"] == SIG_AUDIO
            src = io_name(s["inn"], True, live)
            head = "%-4d %-15s in %-6s out %-6s" % (ch, s["name"], src, io_name(s["out"]))
        else:
            head = "%-4d %-15s" % (ch, "?")
        ins = ["%d:%s%s" % (sl - 4, n, "" if l is None else "(%s)" % l) for sl, n, l, _ in inserts.get(ch, [])]
        print(head, ("lat %d " % total(inserts.get(ch, []))) if a.lat else "", " ".join(ins))


def cmd_extract(a):
    d = load(a.projectdata)
    os.makedirs(a.outdir, exist_ok=True)
    n = 0
    for p, tag, ch, slot, pl in chunks(d):
        if tag == b"UCuA" and FIRST_INSERT <= slot <= LAST_INSERT:
            x = pl.find(b"<?xml")
            if x <= 0:
                continue
            e = pl.find(b"</plist>", x)
            if e < 0:
                continue
            body = pl[x:e + len(b"</plist>")]
            fn = os.path.join(a.outdir, "%03d_%d.plist" % (n, p + CH_HDR + x))
            open(fn, "wb").write(body + b"\n")
            n += 1
    print("wrote %d plists to %s" % (n, a.outdir))


def cmd_paths(a):
    d = load(a.projectdata)
    strips, inserts = parse(d, read_lat(a.lat))
    auxin = collections.defaultdict(list)
    for ch, s in strips.items():
        if s["sig"] == SIG_AUX and s["inn"] != NONE16 and s["inn"] >= 33:
            auxin[s["inn"] - 32].append(ch)

    def path(ch, seen=()):
        s = strips[ch]
        o, own = s["out"], total(inserts.get(ch, []))
        if ch in seen:
            return None, [s["name"], "LOOP"]
        if o == a.main_out:
            return own, [s["name"]]
        if o < 33 or o == NONE16:
            return None, [s["name"], io_name(o)]
        nxt = auxin.get(o - 32)
        if not nxt:
            return None, [s["name"], "Bus%d (no aux)" % (o - 32)]
        l, pp = path(nxt[0], seen + (ch,))
        return (None if l is None else l + own), [s["name"]] + pp

    res = {}
    for ch, s in sorted(strips.items()):
        if s["sig"] != SIG_AUDIO:
            continue
        if s["out"] != a.main_out and not (33 <= s["out"] < NONE16):
            continue
        l, pp = path(ch)
        res[ch] = l
        print(ch, s["name"], io_name(s["inn"], True, True), "lat", l, " > ".join(pp))
    if a.json:
        json.dump({str(k): v for k, v in res.items()}, open(a.json, "w"), indent=1)
        print("wrote", a.json)


def cmd_plan(a):
    paths = {k: v for k, v in json.load(open(a.paths)).items() if isinstance(v, int)}
    if not paths:
        sys.exit("no measured paths")
    target = a.target if a.target is not None else max(paths.values())
    plan = {}
    for k, v in sorted(paths.items(), key=lambda kv: int(kv[0])):
        if v > target:
            sys.exit("strip %s path %d is longer than target %d" % (k, v, target))
        if target - v > 0:
            plan[k] = target - v
    print("target %d samples, %d strips need delay" % (target, len(plan)))
    out = json.dumps(plan, indent=1)
    if a.json:
        open(a.json, "w").write(out + "\n")
        print("wrote", a.json)
    else:
        print(out)


def cmd_add_delay(a):
    if os.path.abspath(a.projectdata) == os.path.abspath(a.out):
        sys.exit("refusing to overwrite the input, write a new file")
    d = bytearray(load(a.projectdata))
    plan = {int(k): int(v) for k, v in json.load(open(a.plan)).items()}
    cl = []
    for p, tag, ch, slot, pl in chunks(bytes(d)):
        cl.append(bytearray(d[p:p + CH_HDR + len(pl)]))

    def tag(c): return bytes(c[:4])
    def ch_(c): return struct.unpack_from("<I", c, 14)[0]
    def slot_(c): return struct.unpack_from("<I", c, 18)[0]

    tmpl = next((c for c in cl if tag(c) == b"UCuA" and FIRST_INSERT <= slot_(c) <= LAST_INSERT
                 and bytes(c[0xD0:0xD5]) == b"<?xml"), None)
    if tmpl is None:
        sys.exit("no AU insert in this project to use as a chunk template; add any AU insert in Logic, save, retry")

    def sdly_chunk(ch, slot, samples):
        pl = plistlib.dumps({"data": bytes(16) + struct.pack(">f", float(samples)), "manufacturer": 0x6170706C,
                             "name": "Untitled", "subtype": 0x73646C79, "type": 0x61756678, "version": 0},
                            fmt=plistlib.FMT_XML)
        body = pl + b"\n"
        body += b"\0" * ((-len(body)) % 4)
        c = bytearray(tmpl[:0xD0])
        struct.pack_into("<I", c, 14, ch)
        struct.pack_into("<I", c, 18, slot)
        c[0x2A] = slot - FIRST_INSERT
        c[0x9C:0xA8] = b"AUSampleDel\0"
        c[0xA8:0xB4] = b"lppa" + b"xfua" + b"ylds"
        struct.pack_into("<I", c, 0xBC, len(body))
        c += body + uuid.uuid1().bytes + b"\0" * 4
        struct.pack_into("<Q", c, 28, len(c) - CH_HDR)
        return c

    strip_idx = {ch_(c): k for k, c in enumerate(cl) if tag(c) == b"OCuA" and slot_(c) == NO_SLOT}
    for ch, samples in sorted(plan.items()):
        if ch not in strip_idx:
            sys.exit("strip %d not found" % ch)
        k = strip_idx[ch]
        oc = cl[k]
        j, slots = k + 1, {}
        while j < len(cl) and tag(cl[j]) == b"UCuA" and ch_(cl[j]) == ch:
            slots[slot_(cl[j])] = j
            j += 1
        ins = sorted(s for s in slots if FIRST_INSERT <= s <= LAST_INSERT)
        free = next((s for s in range(FIRST_INSERT, LAST_INSERT + 1) if s not in slots), None)
        if free is None:
            sys.exit("strip %d has no free insert slot" % ch)
        for s in sorted([s for s in ins if s < free], reverse=True):
            c = cl[slots[s]]
            struct.pack_into("<I", c, 18, s + 1)
            c[0x2A] = s + 1 - FIRST_INSERT
        struct.pack_into("<I", oc, CH_HDR + 0x84 + 4 * free, 1)
        new = sdly_chunk(ch, FIRST_INSERT, samples)
        pos = min([slots[s] for s in slots if s >= FIRST_INSERT] or [j])
        cl.insert(pos, new)
        for kk in strip_idx:
            if strip_idx[kk] >= pos:
                strip_idx[kk] += 1
        print("strip %d: AUSampleDelay %d samples at insert 1, moved %s" % (ch, samples, [s - 4 for s in ins if s < free]))
    body = b"".join(bytes(c) for c in cl)
    hdr = bytearray(d[:HDR])
    struct.pack_into("<Q", hdr, 16, len(body))
    open(a.out, "wb").write(bytes(hdr) + body)
    print("bytes %d -> %d, wrote %s" % (len(d), HDR + len(body), a.out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("strips")
    s.add_argument("projectdata")
    s.add_argument("--lat")
    s.set_defaults(fn=cmd_strips)
    e = sub.add_parser("extract")
    e.add_argument("projectdata")
    e.add_argument("outdir")
    e.set_defaults(fn=cmd_extract)
    p = sub.add_parser("paths")
    p.add_argument("projectdata")
    p.add_argument("--lat", required=True)
    p.add_argument("--main-out", type=int, default=73, help="strip output value of the main/stereo out (check with 'strips')")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_paths)
    pl = sub.add_parser("plan")
    pl.add_argument("paths")
    pl.add_argument("--target", type=int)
    pl.add_argument("--json")
    pl.set_defaults(fn=cmd_plan)
    ad = sub.add_parser("add-delay")
    ad.add_argument("projectdata")
    ad.add_argument("out")
    ad.add_argument("plan")
    ad.set_defaults(fn=cmd_add_delay)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
