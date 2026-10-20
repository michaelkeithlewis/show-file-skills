#!/usr/bin/env python3
"""dLive multifunction macros (Show/Multifunctions/<name>.dat). Text: line 1 '2', line 2 a hex id, then one
action per line as comma tokens: aa,X = byte, a8,hi,lo = 16-bit, e8,X / eb,X = marker with value, ea = bare marker, ad,<bytes>,0 = string.
A strip key is aa,<strip type>,aa,<index>; the last a8 in a line is the count of strip keys that end it;
function 5 (send on/level) also has its source key right after the e8 token.

usage:
  dlive_multifunctions.py dump <show.tar.gz>
  dlive_multifunctions.py remap <show.tar.gz> <map.json> <out.tar.gz> [--remove NAME ...]
map.json: {"47": 49, "29": 23}  old input ch -> new input ch (1-based). A send action whose source channel
has no entry is dropped; any other unmapped input reference is an error (fix the map)."""
import re, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STRIP = {1: "Ip", 2: "Grp", 3: "StGrp", 4: "Aux", 5: "StAux", 6: "FX", 7: "StFX", 8: "Main", 0x0a: "Mtx",
         0x0b: "StMtx", 0x0c: "FXRtn", 0x0d: "DCA", 0x13: "UFX", 0x14: "UFXRtn"}

def tokens(line):
    t = line.strip(",").split(","); out = []; i = 0
    while i < len(t):
        k = t[i]
        if len(k) == 2 and k[0] == "e" and (i + 1 >= len(t) or t[i + 1] in ("aa", "a8", "ad") or t[i + 1][:1] == "e" and len(t[i + 1]) == 2):
            out.append((k, [])); i += 1                                   # bare marker (ea)
        elif k == "aa" or (len(k) == 2 and k[0] == "e"): int(t[i + 1], 16); out.append((k, [t[i + 1]])); i += 2
        elif k == "a8": int(t[i + 1], 16); int(t[i + 2], 16); out.append((k, [t[i + 1], t[i + 2]])); i += 3
        elif k == "ad": j = t.index("0", i + 1); out.append((k, t[i + 1:j + 1])); i = j + 1
        else: raise ValueError("unknown token %r" % k)
    return out

def untokens(tok):
    return ",".join(",".join([k] + v) for k, v in tok) + ","

def key_positions(tok):
    fn = int(tok[0][1][0], 16)
    a8 = [i for i, (k, v) in enumerate(tok) if k == "a8"]
    if not a8: return fn, []
    c = a8[-1]; n = int(tok[c][1][0], 16) * 256 + int(tok[c][1][1], 16)
    keys = [c + 1 + 2 * j for j in range(n)]
    if fn == 5: keys.insert(0, 4)
    for i in keys:
        if i + 1 >= len(tok) or tok[i][0] != "aa" or tok[i + 1][0] != "aa": raise ValueError("unexpected macro shape")
    return fn, keys

def describe(line):
    tok = tokens(line); fn, keys = key_positions(tok)
    return "fn %d: %s" % (fn, " ".join("%s%d" % (STRIP.get(int(tok[i][1][0], 16), "?"), int(tok[i + 1][1][0], 16) + 1) for i in keys))

def remap_line(line, m):
    tok = tokens(line); fn, keys = key_positions(tok)
    for i in keys:
        if int(tok[i][1][0], 16) == 1:
            old = int(tok[i + 1][1][0], 16) + 1
            if old not in m:
                if fn == 5 and i == 4: return None
                raise ValueError("input %d not in the map (%s)" % (old, line))
            tok[i + 1] = ("aa", ["%x" % (m[old] - 1)])
    return untokens(tok)

def remap_file(b, m):
    lines = b.decode().split("\n")
    body = [remap_line(l, m) for l in lines[2:] if l]
    return ("\n".join(lines[:2] + [x for x in body if x is not None]) + "\n").encode()

# ---- writers (shapes copied from Director-saved macros; meanings from cMultifunctionRecall @0x1010ae6e0)
# fn 6 = processing in/out: [aa,6][aa,mode][aa,2][eb,0][a8,0,proc][a8,count][strip keys]. Mode (eSoftkeyMode):
# 1 = in, 2 = out, 0 = toggle. proc (eChannelProcessingMode, RecallProcessing jump table): 1 preamp, 3 HPF,
# 4 gate, 5 insert A (mixes: their one insert), 6 insert B (input channels only), 7 comp, 8 PEQ, 9 NEQ.
# Director-written 'INSERT ON/OFF' and 'LP ON/OFF' macros are proc 5.
# fn 7 = ABCD source select: [aa,7][aa,0][aa,2][eb,0][a8,0,source 1-4][a8,count][strip keys]
# (a Director-written 'VSC ON/OFF': source 2 / 1 on one channel).
MODES = {"in": 1, "on": 1, "out": 2, "off": 2, "toggle": 0}
STRIP_BY_NAME = {v.lower(): k for k, v in STRIP.items()}

def strip_key(s):
    """'Ip12' / 'Main1' / 'StGrp4' -> 'aa,1,aa,b' (strip type, index-1)."""
    m = re.fullmatch(r"([A-Za-z]+)\s*(\d+)", s.strip())
    return "aa,%x,aa,%x" % (STRIP_BY_NAME[m.group(1).lower()], int(m.group(2)) - 1)

def _count(n):
    return "a8,%x,%x" % (n >> 8, n & 0xff)

def insert_action(mode, which, strips):
    """mode in/out/toggle, which 'A'|'B' (B = input channels only), strips like ['Ip1', 'Main1']."""
    if which.upper() == "B": assert all(x.lower().startswith("ip") for x in strips), "insert B exists on inputs only"
    proc = 5 if which.upper() == "A" else 6
    return "aa,6,aa,%x,aa,2,eb,0,a8,0,%x,%s,%s," % (MODES[mode], proc, _count(len(strips)), ",".join(map(strip_key, strips)))

def abcd_action(source, strips):
    """source 'A'..'D' on the listed input channels (only channels with ABCD enabled follow it)."""
    return "aa,7,aa,0,aa,2,eb,0,a8,0,%x,%s,%s," % ("ABCD".index(source.upper()) + 1, _count(len(strips)),
                                                 ",".join(map(strip_key, strips)))

def macro_file(actions, ident=None):
    """Text of a Show/Multifunctions/<name>.dat: '2', a hex id (Director uses epoch ms), one action per line."""
    import time
    ident = ident or int(time.time() * 1000)
    for a in actions:
        tokens(a)
    return ("2\n%x\n" % ident + "".join(a + "\n" for a in actions)).encode()

def add_macro(members, files, name, data):
    """Add or replace Show/Multifunctions/<name>.dat in a read_show() pair (tar member copied from a sibling)."""
    import copy, tarfile
    path = "Show/Multifunctions/%s.dat" % name
    assert len(name) <= 16 and "/" not in name
    if path not in files:
        sib = next((m for m in members if m.name.startswith("Show/Multifunctions/") and m.isfile()), None)
        if sib is not None:
            m = copy.copy(sib); m.name = path
        else:
            m = tarfile.TarInfo(path); m.mode = 0o644
        d = next(i for i, x in enumerate(members) if x.name.rstrip("/") == "Show/Multifunctions")
        members.insert(d + 1, m)
    files[path] = data

if __name__ == "__main__":
    from dlive_mix import read_show, write_show
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "dump":
        _, F = read_show(a[1])
        for n in sorted(F):
            if n.startswith("Show/Multifunctions/"):
                print(n.split("/")[-1])
                for l in F[n].decode().split("\n")[2:]:
                    if l: print("   ", describe(l))
    elif len(a) >= 4 and a[0] == "remap":
        m = {int(k): int(v) for k, v in json.load(open(a[2])).items()}
        remove = {"Show/Multifunctions/%s.dat" % x for x in (a[a.index("--remove") + 1:] if "--remove" in a else [])}
        M, F = read_show(a[1])
        for n in sorted(F):
            if n.startswith("Show/Multifunctions/") and n not in remove: F[n] = remap_file(F[n], m)
        M = [x for x in M if x.name not in remove]
        for n in remove: F.pop(n, None)
        write_show(M, F, a[3]); print("remapped multifunctions -> %s (removed %d)" % (a[3], len(remove)))
    else:
        sys.exit(__doc__)
