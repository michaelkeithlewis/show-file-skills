#!/usr/bin/env python3
"""Check a dLive show file (firmware 2.x, Version 14) for anything Director or a console could reject or
misread, before it goes near either. Exit 1 on errors; warnings are things Director tolerates.

usage: dlive_lint.py <show.tar.gz> [--quiet]

Checks: container + Version; MixConfig, InputConfig, FollowPan, SceneSafes against each other; every
StageBox scene (framing round-trip, u32 chain length, header recall-filter config, mixer tables parse and
agree, patch section version/refs, name tables, preamps, inserts, side chains, levels, section lengths
against every length seen in Director-saved shows); every surface scene (framing, SoftKeys, strip banks);
multifunction macros (token grammar, channel refs)."""
import io, json, os, re, struct, sys, tarfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dlive_mix import SceneFile, MixConfig, cm_parse, mm_parse, inner
from dlive_patch import Patch, BLOCKS, NONE
from dlive_scene import Scene
import dlive_safes

LENGTHS = json.load(open(os.path.join(HERE, "section_lengths.json")))
SOURCE_TYPES = set(range(0x00, 0x2f))          # eAudioSourceType values seen in Director (0x00-0x2e)
STRIP_TYPES = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x13, 0x14}  # seen in Director-saved banks
MANAGERS = ["Input Channel", "Mono Group Channel", "Stereo Group Channel", "Mono Aux Channel", "Stereo Aux Channel",
            "Mono FX Send Channel", "Stereo FX Send Channel", "Stereo AHFX Send Channel", "Main Channel",
            "Mono Matrix Channel", "Stereo Matrix Channel", "FX Return Channel", "AHFX Return Channel", "DCA Channel"]

class Report:
    def __init__(self): self.errors, self.warnings = [], []
    def err(self, where, msg): self.errors.append("%s: %s" % (where, msg))
    def warn(self, where, msg): self.warnings.append("%s: %s" % (where, msg))

def lint(path):
    r = Report()
    try:
        with tarfile.open(path) as t:
            members = t.getmembers()
            files = {m.name: t.extractfile(m).read() for m in members if m.isfile()}
    except Exception as e:
        r.err("container", "cannot read tar.gz: %s" % e); return r
    if any(m.pax_headers for m in members): r.warn("container", "PAX headers present (Director writes plain ustar)")
    if not all(m.name.startswith("Show/") or m.name == "Show" for m in members): r.err("container", "members outside Show/")
    v = files.get("Show/Version.dat", b"").strip()
    if v != b"14": r.err("Show/Version.dat", "version %r; these tools know Version 14 (firmware 2.x) only" % v)
    mc_raw = files.get("Show/MixConfig/MixConfig.dat")
    if not mc_raw or len(mc_raw) != 13 or mc_raw[0] != 1:
        r.err("MixConfig", "missing or malformed"); return r
    mc = MixConfig(mc_raw); c = mc.counts
    used = MixConfig.buses_used(c)
    if used > 64: r.err("MixConfig", "%d mix buses used (max 64)" % used)
    odd = MixConfig.odd_mono(c)
    if odd: r.err("MixConfig", "odd mono count %s: stereo mixes land off their even bus (console selects the wrong strip)" % odd)
    if mc_raw[7] != 1 or mc_raw[8] != 1: r.warn("MixConfig", "main mode is not LR; dlive_mix reconfigure refuses these")
    tok = files.get("Show/InputConfig/InputConfig.dat", b"").decode(errors="replace").split()
    if len(tok) != 65 or tok[0] != "1" or any(x not in ("0", "1") for x in tok[1:]):
        r.err("InputConfig", "expected '1' + 64 flags")
    fp = files.get("Show/FollowPanSettings/FollowPanSettings.dat")
    if fp:
        lines = [l for l in fp.decode().split("\n")[1:] if l.strip()]
        want = c["sAux"] + c["sFX"] + 8 + c["sMtx"]
        if len(lines) != want: r.err("FollowPanSettings", "%d lines, mixer config needs %d" % (len(lines), want))
    for n, b in files.items():
        if n.startswith("Show/SceneSafes/StageBox"):
            if len(b) != dlive_safes.TOTAL: r.err(n, "size %d (expected %d)" % (len(b), dlive_safes.TOTAL))
            elif b[3:16] != mc_raw: r.err(n, "embedded mixer config does not match MixConfig.dat")
    for n, b in files.items():
        if n.startswith("Show/Multifunctions/"): lint_multifunction(r, n, b)
    for n in sorted(files):
        if "/Scenes/" not in n or not n.endswith(".tar.gz"): continue
        try:
            ms, inn = inner(files[n])
        except Exception as e:
            r.err(n, "inner archive unreadable: %s" % e); continue
        for dn, d in inn.items():
            if b"Channel Mapper\x00" in d: lint_stagebox(r, n.split("/")[-1], d, mc, live=n.endswith("65535.tar.gz"))
            elif b"Surface Soft Controls\x00" in d: lint_surface(r, n.split("/")[-1], d)
    return r

def lint_section_lengths(r, where, sc):
    for l, p in sc.sections:
        fam = re.sub(r"\d+", "N", l)
        allowed = LENGTHS.get(fam)
        if allowed and len(p) not in allowed:
            r.err(where, "section %r is %d bytes; Director-saved shows only have %s" % (l, len(p), allowed))

def lint_stagebox(r, where, d, mc, live):
    try:
        sc = SceneFile(d)
    except Exception as e:
        r.err(where, "section chain does not parse: %s" % e); return
    if sc.to_bytes() != d: r.err(where, "re-serialising the chain changes bytes (framing or u32 length wrong)")
    lint_section_lengths(r, where, sc)
    if live and bytes(sc.header).find(b"\x15" + bytes(mc.raw)) < 0:
        i = bytes(sc.header).find(b"\x15\x01")
        blank = i > 0 and not any(sc.header[i + 2:i + 13])
        (r.warn if blank else r.err)(where, "header recall filter %s the show's mixer config" % ("is blank, not" if blank else "does not carry"))
    old = (lambda w, m: r.warn(w, "older-format stored scene, Director converts it on recall: " + m)) if not live else r.err
    try:
        hdrs = []
        for lab, n in (("Input Mixer", 128), ("FX Return Mixer", 32), ("AHFX Return Mixer", 16)):
            h, cc, chans = cm_parse(sc.get(lab))
            if len(chans) != n: r.err(where, "%s has %d channels (expected %d)" % (lab, len(chans), n))
            hdrs.append(cc)
            for k, ch in enumerate(chans):
                f = struct.unpack(">h", ch["rest"][3:5])[0]
                if f > 2560: r.err(where, "%s ch %d fader %+.1f dB above +10" % (lab, k + 1, f / 256))
                for kind in ("mFX", "mAux", "sFX", "sAux", "mMtx", "sMtx"):
                    for s in ch[kind]:
                        if s[0] > 1 or s[1] > 1 or struct.unpack(">h", s[2:4])[0] > 2560 or (len(s) == 5 and s[4] > 74):
                            r.err(where, "%s ch %d bad %s send %s" % (lab, k + 1, kind, s.hex())); break
        hh, mcounts, mixes = mm_parse(sc.get("Mix Mixer"))
        for cc in hdrs:
            for k in ("MG", "SG", "mFX", "sFX", "mAux", "sAux", "mMtx", "sMtx"):
                if cc[k] != mcounts[k]: r.err(where, "mixer tables disagree on %s (%d vs %d)" % (k, cc[k], mcounts[k]))
        if live:
            for k in ("MG", "SG", "mFX", "sFX", "mAux", "sAux", "mMtx", "sMtx"):
                if mcounts[k] != mc.counts[k]: r.err(where, "live scene %s=%d but MixConfig says %d" % (k, mcounts[k], mc.counts[k]))
        for key, m in mixes.items():
            f = struct.unpack(">h", m["ch"][3:5])[0]
            if f > 2560: r.err(where, "mix %s %d fader above +10 dB" % key)
            if any(x > 1 for x in m["ch"][16:48]): r.err(where, "mix %s %d DCA/mute-group bytes not 0/1" % key)
    except Exception as e:
        old(where, "mixer tables do not parse: %s" % e)
    try:
        p = Patch(d)
        for ch in range(1, 129):
            x = p.input(ch)
            if x["active"] > 4: r.err(where, "Ip %d ABCD active byte %d" % (ch, x["active"]))
            for t, n in x["sources"]:
                if t not in SOURCE_TYPES: r.err(where, "Ip %d source type 0x%02x unknown" % (ch, t))
        for name, (off, cnt) in BLOCKS.items():
            for k in range(cnt):
                t, n = p._ref(off + 3 * k)
                if (t, n) != NONE and t not in SOURCE_TYPES: r.err(where, "%s %d: source type 0x%02x unknown" % (name, k + 1, t))
    except Exception as e:
        old(where, "patch section: %s" % e)
    try:
        s = Scene(d)
        for mgr in MANAGERS:
            try: names = s.names(mgr)
            except KeyError: continue
            base, n = s.manager(mgr)
            for k in range(n):
                raw = bytes(s.d[base + 9 * k: base + 9 * k + 9])
                nm, col = names[k]
                if b"\x00" not in raw or any(not (32 <= b < 127) for b in raw.split(b"\x00")[0]):
                    r.err(where, "%s %d name bytes %s" % (mgr, k + 1, raw.hex()))   # bytes after the NUL are leftovers
                elif nm != nm.rstrip(" "): r.warn(where, "%s %d name %r is space padded" % (mgr, k + 1, nm))
                if col > 7: r.err(where, "%s %d colour %d" % (mgr, k + 1, col))
    except Exception as e:
        r.err(where, "name tables: %s" % e)
    for l, pl in sc.sections:
        if l.startswith("StageBox Analogue Input, Number") and len(pl) == 5:
            g = struct.unpack(">h", pl[1:3])[0] / 256
            if pl[3] > 1 or pl[4] > 1 or not (0 <= g <= 60): r.err(where, "%s = %s" % (l, pl.hex()))
        elif re.match(r"Insert( \d)?, ", l) and len(pl) == 3 and pl[1] > 1:
            r.err(where, "%s in/out byte %d" % (l, pl[1]))
        elif "side chain source" in l and len(pl) == 3 and pl[1] == 1 and pl[2] > 127:
            r.err(where, "%s points at input %d" % (l, pl[2] + 1))

def lint_surface(r, where, d):
    try:
        sc = SceneFile(d)
    except Exception as e:
        r.err(where, "section chain does not parse: %s" % e); return
    if sc.to_bytes() != d: r.err(where, "re-serialising the chain changes bytes")
    lint_section_lengths(r, where, sc)
    try:
        sys.path.insert(0, HERE)
        from dlive_softkeys import parse
        out, end = parse(sc.get("Surface Soft Controls"))
        bad = [k + 1 for k, (o, raw, desc) in enumerate(out) if raw[1] != 1 or raw[2] > 7]
        if bad: r.warn(where, "SoftKeys use a key type this parser does not size (from key %d); not verified" % bad[0])
    except Exception as e:
        r.warn(where, "SoftKeys not verified (%s)" % e)
    for bank in ("Left", "Middle", "Right"):
        try: p = sc.get("Channel %s Bank Switcher" % bank)
        except KeyError: continue
        n = p[1]
        if len(p) != 2 + 2 * 6 * n: r.err(where, "%s bank length %d for %d strips" % (bank, len(p), n)); continue
        for k in range(6 * n):
            t, i = p[2 + 2 * k], p[3 + 2 * k]
            if t not in STRIP_TYPES: r.err(where, "%s bank strip %d type 0x%02x unknown" % (bank, k + 1, t))
            elif t == 1 and i > 127: r.err(where, "%s bank strip %d input %d" % (bank, k + 1, i + 1))

def lint_multifunction(r, name, b):
    try:
        lines = b.decode().split("\n")
        if lines[0] != "2": r.warn(name, "header version %r" % lines[0])
        sys.path.insert(0, HERE)
        from dlive_multifunctions import tokens
        for l in lines[2:]:
            if l.strip(): tokens(l)
    except Exception as e:
        r.err(name, "macro does not parse: %s" % e)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    if sys.argv[1] in ("-h", "--help"): print(__doc__); sys.exit(0)
    rep = lint(sys.argv[1])
    for w in ([] if "--quiet" in sys.argv else rep.warnings): print("WARN ", w)
    for e in rep.errors: print("ERROR", e)
    print("%s: %d errors, %d warnings" % (os.path.basename(sys.argv[1]), len(rep.errors), len(rep.warnings)))
    sys.exit(1 if rep.errors else 0)
