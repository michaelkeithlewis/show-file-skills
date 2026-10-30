#!/usr/bin/env python3
"""dLive input/output patch ("Channel Mapper" scene section) reader/writer, firmware 2.x.

Decoded from dLive Director V2.12 with REA + objdump (notes: references/format-patch.md):
- cChannelMapper::GetStatus @0x1001cefe0 writes it, SetStatus @0x1001d0720 reads it.
- Section = u16be len (15 + 0x288c), "Channel Mapper\\0", fixed 0x288c-byte payload, byte 0 = version 6.
- ref = 3 bytes: eAudioSourceType (u8) + number (u16be, 0-based). 0x14/0 = unassigned.
- Inputs 1-128 at +1, 13 bytes each: active byte (0 = ABCD off -> A, 1-4 = A-D, per
  cChannelMapperBase::GetActiveInputChannelSource jump table), then refs A, B, C, D.
- Every other block is indexed by destination (output socket, insert return, rack input...)
  and holds the ref of the source that feeds it.
- Location names and offsets come from CSVImportUtilities::LocationsToUsefulTypes and
  ChannelsToUsefulTypes. Stereo mixes number 2*(n-1) + (0 L, 1 R).

Every StageBox scene that holds the section gets the same edit (incl. StageBoxScene65535,
the live state), so recalling a scene does not undo the patch.

usage:
  dlive_patch.py dump <show.tar.gz|scene.dat> [--all]
  dlive_patch.py apply <show.tar.gz> <patch.json> <out.tar.gz>

patch.json:
  {"inputs":  {"1": "IO 1:1", "47": {"A": "IO 1:47", "B": "IO 1:49", "active": "B"}},
   "outputs": {"IO 1": {"1": "Aux 3", "11": "MixRack:11", "20": "Ip 12 DO"},
               "MixRack": {"1": "Main L", "2": "Main R"}}}
  {"vsc": {"port": "IO 4", "first": 65, "last": 120}}   virtual soundcheck port + socket range
  blocks: {"VSC input source": {"1": "VSC port 65"}, "VSC record send": {"65": "Ip 1 VSC rec"},
           "Ip Ins B return": {"3": "IO 4:3"}, "Main Ins return": {"1": "IO 4:57"}}
Input sources: "MixRack:n", "DX 1/2:n", "DX 3/4:n", "IO 1:n".."IO 3:n", "Surface:n",
  "Surface DX 5/6:n", "IO 4:n", "IO 5:n", "USB:n", "SigGen", "FX Rtn n", "UFX Rtn n", "Unassigned".
Output sources: any input source (socket passthrough), "Ip n DO", "Ip n Ins A send", "Ip n Ins B send",
  "Main Ins send L|R", "Ip n VSC rec", "Grp n", "St Grp n L|R",
  "Aux n", "St Aux n L|R", "Main L|R", "Mtx n", "St Mtx n L|R", "PAFL L|R", "Wedge", "IEM L|R".
Output destinations: see DEST below ("IO 1", "MixRack", "DX 1/2", "Surface", "USB", ...).
Plain mono mixes are numbered by the show's mixer config (Aux 3 = third mono aux).
"""
import io, json, os, re, shutil, struct, sys, tarfile, tempfile

LABEL = b"Channel Mapper\x00"
PAYLOAD_LEN = 0x288C
VERSION = 6
NONE = (0x14, 0)

T_MIXRACK, T_SURFACE, T_IO1, T_IO2, T_IO3, T_DX12, T_DX34 = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06
T_DO, T_INSA, T_INSB = 0x07, 0x08, 0x09
T_GRP, T_STGRP, T_AUX, T_STAUX, T_MAIN, T_MTX, T_STMTX = 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12
T_PAFL, T_NONE = 0x13, 0x14
T_FXRTN, T_FXSEND, T_WEDGE, T_IEM = 0x1C, 0x1D, 0x1E, 0x21
T_VSC_IN, T_DYN_OUT, T_VSC_REC, T_SIGGEN, T_TALK, T_UFXRTN, T_UFXSEND = 0x26, 0x27, 0x28, 0x2A, 0x2B, 0x2D, 0x2E

IN_LOC = {
    "MixRack": (T_MIXRACK, 0, 64),
    "Surface": (T_SURFACE, 0, 12),
    "Surface DX 5/6": (T_SURFACE, 12, 32),
    "IO 4": (T_SURFACE, 44, 128),
    "IO 5": (T_SURFACE, 172, 128),
    "USB": (T_SURFACE, 300, 2),
    "IO 1": (T_IO1, 0, 128),
    "IO 2": (T_IO2, 0, 128),
    "IO 3": (T_IO3, 0, 128),
    "DX 1/2": (T_DX12, 0, 32),
    "DX 3/4": (T_DX34, 0, 32),
}
ALIASES = {"mixrack dx 1/2": "DX 1/2", "mixrack dx 3/4": "DX 3/4", "io1": "IO 1", "io2": "IO 2",
           "io3": "IO 3", "io4": "IO 4", "io5": "IO 5", "dx1/2": "DX 1/2", "dx3/4": "DX 3/4"}

NAMED = {T_DO: "Ip {} DO", T_INSA: "Ip {} Ins A send", T_INSB: "Ip {} Ins B send", T_GRP: "Grp {}",
         T_AUX: "Aux {}", T_MTX: "Mtx {}", T_FXRTN: "FX Rtn {}", T_FXSEND: "FX Send {}",
         T_UFXRTN: "UFX Rtn {}", T_UFXSEND: "UFX Send {}", T_DYN_OUT: "Dyn {} out",
         T_VSC_IN: "VSC port {}", T_VSC_REC: "Ip {} VSC rec",
         0x15: "Grp {} Ins send", 0x17: "Aux {} Ins send", 0x1A: "Mtx {} Ins send"}
STEREO = {T_STGRP: "St Grp", T_STAUX: "St Aux", T_MAIN: "Main", T_STMTX: "St Mtx",
          0x16: "St Grp Ins send", 0x18: "St Aux Ins send", 0x19: "Main Ins send", 0x1B: "St Mtx Ins send"}

BLOCKS = {
    "VSC input source": (0x0681, 128), "VSC record send": (0x0801, 128),
    "Ip Ins A return": (0x0A04, 128), "Ip Ins B return": (0x0B84, 128),
    "Surface outputs": (0x0D04, 512),
    "Grp ext in": (0x1304, 64), "St Grp ext in": (0x13C4, 32), "Aux ext in": (0x1424, 64),
    "St Aux ext in": (0x14E4, 32), "Main ext in": (0x1544, 6), "Mtx ext in": (0x1556, 64),
    "St Mtx ext in": (0x1616, 32), "Grp Ins return": (0x1676, 64), "St Grp Ins return": (0x1736, 32),
    "Aux Ins return": (0x1796, 64), "St Aux Ins return": (0x1856, 32), "Main Ins return": (0x18B6, 6),
    "Mtx Ins return": (0x18C8, 64), "St Mtx Ins return": (0x1988, 32),
    "MixRack outputs": (0x19E8, 32), "Talkback source": (0x1A48, 1), "FX rack input": (0x1A4B, 32),
    "UFX rack input": (0x1AAB, 16), "Ext talk to PAFL": (0x1ADB, 16),
    "IO 1 outputs": (0x1B0B, 128), "IO 2 outputs": (0x1C8B, 128), "IO 3 outputs": (0x1E0B, 128),
    "DX 1/2 outputs": (0x1F8B, 32), "DX 3/4 outputs": (0x1FEB, 32), "ME outputs": (0x204B, 40),
    "Dyn unit input": (0x20C3, 64), "iMX6 input": (0x2183, 4),
}
VSC_FLAGS, VSC_BYTES, TALKBACK = 0x0981, 0x0A01, 0x218F
VSC_PORTS = ["IO 1", "IO 2", "IO 3", "IO 4", "IO 5"]
DEST = {
    "MixRack": ("MixRack outputs", 0, 32), "IO 1": ("IO 1 outputs", 0, 128),
    "IO 2": ("IO 2 outputs", 0, 128), "IO 3": ("IO 3 outputs", 0, 128),
    "DX 1/2": ("DX 1/2 outputs", 0, 32), "DX 3/4": ("DX 3/4 outputs", 0, 32), "ME": ("ME outputs", 0, 40),
    "Surface": ("Surface outputs", 0, 16), "Surface DX 5/6": ("Surface outputs", 16, 32),
    "IO 4": ("Surface outputs", 48, 128), "IO 5": ("Surface outputs", 176, 128),
    "USB": ("Surface outputs", 304, 2),
    "FX rack input": ("FX rack input", 0, 32), "UFX rack input": ("UFX rack input", 0, 16),
}


def describe(t, n):
    if (t, n) == NONE:
        return "-"
    if t == T_NONE:
        return "Unassigned(%d!)" % n
    for name, (lt, first, cnt) in IN_LOC.items():
        if lt == t and first <= n < first + cnt:
            return "%s:%d" % (name, n - first + 1)
    if t in NAMED:
        return NAMED[t].format(n + 1)
    if t in STEREO:
        if t == T_MAIN and n < 2:
            return "Main %s" % "LR"[n]
        return "%s %d %s" % (STEREO[t], n // 2 + 1, "LR"[n % 2])
    if t == T_PAFL:
        return "PAFL %s" % "LR"[n % 2] if n < 2 else "PAFL #%d" % n
    if t == T_WEDGE:
        return "Wedge"
    if t == T_IEM:
        return "IEM %s" % "LR"[n % 2]
    if t == T_SIGGEN:
        return "SigGen"
    if t == T_TALK:
        return "Talkback"
    return "type0x%02x:%d" % (t, n)


def parse_source(s):
    s = s.strip()
    low = s.lower()
    if low in ("unassigned", "-", "none", ""):
        return NONE
    if low == "siggen":
        return (T_SIGGEN, 0)
    if low == "talkback":
        return (T_TALK, 0)
    if low == "wedge":
        return (T_WEDGE, 0)
    m = re.fullmatch(r"(.+?)\s*:\s*(\d+)", s)
    if m:
        raw = m.group(1).lower()
        raw = ALIASES.get(raw.replace(" ", ""), ALIASES.get(raw, raw))
        loc = next((k for k in IN_LOC if k.lower() == raw.lower()), None)
        if loc is None:
            raise ValueError("unknown location in %r" % s)
        t, first, cnt = IN_LOC[loc]
        k = int(m.group(2))
        if not 1 <= k <= cnt:
            raise ValueError("%s socket must be 1..%d" % (loc, cnt))
        return (t, first + k - 1)
    m = re.fullmatch(r"(?:ip|input)\s*(\d+)\s*ins\s*([ab])\s*send", low)
    if m:
        return (T_INSA if m.group(2) == "a" else T_INSB, int(m.group(1)) - 1)
    m = re.fullmatch(r"(?:ip|input)\s*(\d+)\s*vsc rec", low)
    if m:
        return (T_VSC_REC, int(m.group(1)) - 1)
    m = re.fullmatch(r"vsc port\s*(\d+)", low)
    if m:
        return (T_VSC_IN, int(m.group(1)) - 1)
    m = re.fullmatch(r"main ins send\s*1?\s*([lr])", low)
    if m:
        return (0x19, "lr".index(m.group(1)))
    m = re.fullmatch(r"(?:ip|input)\s*(\d+)\s*(do|direct out)?", low)
    if m:
        return (T_DO, int(m.group(1)) - 1)
    m = re.fullmatch(r"(main|pafl|iem)\s*([lr])", low)
    if m:
        return ({"main": T_MAIN, "pafl": T_PAFL, "iem": T_IEM}[m.group(1)], "lr".index(m.group(2)))
    m = re.fullmatch(r"(st ?grp|st ?aux|st ?mtx|st ?group|st ?matrix)\s*(\d+)\s*([lr])", low)
    if m:
        kind = m.group(1).replace(" ", "")
        t = T_STGRP if "gr" in kind else T_STAUX if "aux" in kind else T_STMTX
        return (t, 2 * (int(m.group(2)) - 1) + "lr".index(m.group(3)))
    m = re.fullmatch(r"(grp|group|aux|mtx|matrix|fx rtn|ufx rtn|fx send|ufx send)\s*(\d+)", low)
    if m:
        t = {"grp": T_GRP, "group": T_GRP, "aux": T_AUX, "mtx": T_MTX, "matrix": T_MTX, "fx rtn": T_FXRTN,
             "ufx rtn": T_UFXRTN, "fx send": T_FXSEND, "ufx send": T_UFXSEND}[m.group(1)]
        return (t, int(m.group(2)) - 1)
    raise ValueError("cannot parse source %r" % s)


class Patch:
    def __init__(self, data):
        self.d = data if isinstance(data, bytearray) else bytearray(data)
        i = self.d.find(LABEL)
        if i < 2:
            raise KeyError("no Channel Mapper section")
        n = struct.unpack_from(">H", self.d, i - 2)[0]
        assert n == len(LABEL) + PAYLOAD_LEN, "unexpected Channel Mapper length 0x%x" % n
        self.p = i + len(LABEL)
        assert self.d[self.p] == VERSION, "unexpected Channel Mapper version %d" % self.d[self.p]

    def _ref(self, off):
        return self.d[self.p + off], struct.unpack_from(">H", self.d, self.p + off + 1)[0]

    def _set_ref(self, off, ref):
        t, n = ref
        self.d[self.p + off] = t
        struct.pack_into(">H", self.d, self.p + off + 1, n)

    def input(self, ch):
        assert 1 <= ch <= 128
        o = 1 + 13 * (ch - 1)
        return dict(active=self.d[self.p + o], sources=[self._ref(o + 1 + 3 * k) for k in range(4)])

    def set_input(self, ch, a=None, b=None, c=None, d=None, active=None):
        """Sources are strings or (type, number) refs; active: 'off'|'A'..'D' or 0-4."""
        assert 1 <= ch <= 128
        o = 1 + 13 * (ch - 1)
        for k, src in enumerate((a, b, c, d)):
            if src is not None:
                self._set_ref(o + 1 + 3 * k, parse_source(src) if isinstance(src, str) else src)
        if active is not None:
            self.d[self.p + o] = active if isinstance(active, int) else {"off": 0, "a": 1, "b": 2, "c": 3, "d": 4}[active.lower()]

    def block(self, name):
        off, cnt = BLOCKS[name]
        return [self._ref(off + 3 * k) for k in range(cnt)]

    def output(self, dest, socket):
        blk, first, cnt = DEST[dest]
        assert 1 <= socket <= cnt, "%s socket must be 1..%d" % (dest, cnt)
        return self._ref(BLOCKS[blk][0] + 3 * (first + socket - 1))

    def set_output(self, dest, socket, src):
        blk, first, cnt = DEST[dest]
        assert 1 <= socket <= cnt, "%s socket must be 1..%d" % (dest, cnt)
        self._set_ref(BLOCKS[blk][0] + 3 * (first + socket - 1), parse_source(src) if isinstance(src, str) else src)

    def set_block(self, name, index, src):
        off, cnt = BLOCKS[name]
        assert 1 <= index <= cnt
        self._set_ref(off + 3 * (index - 1), parse_source(src) if isinstance(src, str) else src)

    def vsc(self):
        port, start, end = self.d[self.p + VSC_BYTES:self.p + VSC_BYTES + 3]
        return dict(port=VSC_PORTS[port] if port < len(VSC_PORTS) else "port%d" % port, first=start + 1, last=end)

    def set_vsc(self, port, first, last):
        """port 'IO 1'..'IO 5'; sockets first..last on that port carry VSC record/playback."""
        assert 1 <= first <= last <= 128
        self.d[self.p + VSC_BYTES:self.p + VSC_BYTES + 3] = bytes([VSC_PORTS.index(port), first - 1, last])

    def apply(self, plan):
        for ch, v in plan.get("inputs", {}).items():
            if isinstance(v, str):
                self.set_input(int(ch), a=v)
            else:
                self.set_input(int(ch), v.get("A"), v.get("B"), v.get("C"), v.get("D"), v.get("active"))
        for dest, socks in plan.get("outputs", {}).items():
            for s, src in socks.items():
                self.set_output(dest, int(s), src)
        for name, idx in plan.get("blocks", {}).items():
            for i, src in idx.items():
                self.set_block(name, int(i), src)
        if "vsc" in plan:
            v = plan["vsc"]; self.set_vsc(v["port"], int(v["first"]), int(v["last"]))

    def dump(self, show_all=False):
        out = ["Inputs (active: off=ABCD off, else selected source):"]
        for ch in range(1, 129):
            r = self.input(ch)
            if not show_all and r["active"] == 0 and all(x == NONE for x in r["sources"][1:]) and r["sources"][0] == NONE:
                continue
            act = "off" if r["active"] == 0 else "ABCD"[r["active"] - 1] if r["active"] <= 4 else "?%d" % r["active"]
            srcs = [describe(*x) for x in r["sources"]]
            out.append("  Ip %3d  %-4s %s" % (ch, act, srcs[0] if not show_all and all(x == "-" for x in srcs[1:])
                                              else " | ".join(srcs)))
        out.append("VSC port %(port)s, sockets %(first)d-%(last)d" % self.vsc())
        for name, (off, cnt) in BLOCKS.items():
            rows = [(k + 1, describe(*x)) for k, x in enumerate(self.block(name)) if show_all or x != NONE]
            if rows:
                out.append("%s (%d set):" % (name, len(rows)))
                out.append("  " + "  ".join("%d=%s" % r for r in rows))
        return "\n".join(out)


def _scene_members(show_dir):
    sdir = os.path.join(show_dir, "Scenes")
    for fn in sorted(os.listdir(sdir)):
        if fn.startswith("StageBoxScene") and fn.endswith(".tar.gz"):
            yield os.path.join(sdir, fn)


def _rewrite_scene(path, fn):
    with tarfile.open(path) as t:
        members = t.getmembers()
        datas = {m.name: t.extractfile(m).read() for m in members if m.isfile()}
    changed = False
    for name, data in datas.items():
        if LABEL in data:
            new = fn(bytearray(data))
            if new != data:
                datas[name] = bytes(new); changed = True
    if changed:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as t:
            for m in members:
                m.mtime = int(m.mtime); m.pax_headers = {}
                if m.isfile():
                    m.size = len(datas[m.name]); t.addfile(m, io.BytesIO(datas[m.name]))
                else:
                    t.addfile(m)
        open(path, "wb").write(buf.getvalue())
    return changed


def apply_show(template, plan, out):
    work = tempfile.mkdtemp()
    try:
        with tarfile.open(template) as t:
            t.extractall(work, filter="fully_trusted")
        pairs = read_pairs(open(os.path.join(work, "Show/InputConfig/InputConfig.dat"), "rb").read())
        live = Patch(load_live_scene(template)); live.apply(plan)
        touched = {int(ch) for ch in plan.get("inputs", {})}
        found = [p for p in pair_problems(live, pairs) if p[0] in touched or p[0] + 1 in touched]
        if any(crossed for _, _, crossed in found):
            raise SystemExit("refused, nothing written:\n  " + "\n  ".join(why for _, why, crossed in found if crossed))
        for _, why, _ in found:
            print("warning: " + why)
        edited = 0

        def edit(data):
            try:
                p = Patch(data)
            except AssertionError as e:
                print("skip (%s) %s" % (e, os.path.basename(path)))
                return data
            p.apply(plan); return p.d
        for path in _scene_members(os.path.join(work, "Show")):
            edited += _rewrite_scene(path, edit)
        with tarfile.open(template) as src, tarfile.open(out, "w:gz", format=tarfile.USTAR_FORMAT) as dst:
            for m in src.getmembers():
                m.mtime = int(m.mtime); m.pax_headers = {}
                if m.isfile():
                    data = open(os.path.join(work, m.name), "rb").read()
                    m.size = len(data); dst.addfile(m, io.BytesIO(data))
                else:
                    dst.addfile(m)
    finally:
        shutil.rmtree(work)
    return edited


def in_loc(ref):
    for name, (lt, first, cnt) in IN_LOC.items():
        if lt == ref[0] and first <= ref[1] < first + cnt:
            return name, first, cnt
    return None


def read_pairs(flags):
    """Odd input numbers of the stereo pairs, from InputConfig.dat bytes ("1" then 64 flags)."""
    tok = flags.decode().split()
    return [2 * i + 1 for i in range(64) if tok[1 + i] == "1"]


def pair_problems(p, pairs):
    """[(odd input, sentence, even start)] for every stereo input whose sockets are not an odd socket and the next one
    (any of A-D). Crossed = next-door sockets of one location that start even or run backwards; otherwise it is split."""
    out = []
    for n in pairs:
        for slot in range(4):
            a, b = p.input(n)["sources"][slot], p.input(n + 1)["sources"][slot]
            la, lb = (None if s == NONE else in_loc(s) for s in (a, b))
            if la is None and lb is None:
                continue
            near = bool(la and la == lb and abs(b[1] - a[1]) == 1)
            if near and b[1] > a[1] and (a[1] - la[1]) % 2 == 0:
                continue
            out.append((n, "stereo input %d/%d source %s is on %s and %s; a pair takes an odd socket and the next one"
                        % (n, n + 1, "ABCD"[slot], describe(*a), describe(*b)), near))
    return out


def load_live_scene(show):
    """Scene bytes for StageBoxScene65535 (live state) from a show tar.gz, or a raw .dat."""
    if not show.endswith(".tar.gz"):
        return open(show, "rb").read()
    with tarfile.open(show) as t:
        m = next(m for m in t.getmembers() if m.name.endswith("Scenes/StageBoxScene65535.tar.gz"))
        inner = tarfile.open(fileobj=io.BytesIO(t.extractfile(m).read()))
        return next(inner.extractfile(x).read() for x in inner.getmembers() if x.isfile())


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "dump":
        print(Patch(load_live_scene(a[1])).dump("--all" in a))
    elif len(a) == 4 and a[0] == "apply":
        n = apply_show(a[1], json.load(open(a[2])), a[3])
        print("patched %d StageBox scenes -> %s" % (n, a[3]))
    else:
        sys.exit(__doc__)
