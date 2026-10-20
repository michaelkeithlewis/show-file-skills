#!/usr/bin/env python3
"""dLive mixer config change + mix routing tables (firmware 2.x shows, Version 14).

Decoded from dLive Director V2.12 (notes: references/format-mixconfig.md) and checked byte for byte
against Director's own config change on a real show.

What a mixer config change touches (and nothing else):
- Show/MixConfig/MixConfig.dat and Show/FollowPanSettings/FollowPanSettings.dat
- Show/SceneSafes/*.dat: remapped per cStageBoxSceneSafesOrRecallFilter::FitFilterToMixerConfig
- the live scene (StageBoxScene65535) only, as Director does. Stored scenes keep their own config;
  Director fits them when they are recalled. In the live scene:
  * Input Mixer / FX Return Mixer / AHFX Return Mixer (cMixer): sends carried by (mix type, number)
  * Mix Mixer (cMixMixer::GetStatus @0x1002cf6f0): mix-to-mix sends, mix channel sections
  * per-mix processing sections (PEQ, GEQ, Compressor, Mix Delay, Digital Attenuator, side chain,
    Insert, Send Source Select) added with Director defaults or dropped
  * patch references to removed mixes stay, as Director leaves them
  * the scene header recall filter and the u32 section-chain length before the first section

usage:
  dlive_mix.py config <show.tar.gz>
  dlive_mix.py reconfigure <show.tar.gz> <out.tar.gz> MG=4 SG=9 mFX=0 sFX=3 mAux=4 sAux=7 mMtx=4 sMtx=5
      (any subset; the rest stay as they are)
  dlive_mix.py mixes <show.tar.gz>        print the Mix Mixer (faders, DCAs, sends to matrix)
  dlive_mix.py apply <show.tar.gz> <plan.json> <out.tar.gz>

plan.json (every key optional):
  {"config": {"sAux": 7, "sFX": 3},
   "mixes": {"St Aux 1": {"name": "LEAD", "colour": 4, "fader": 0, "mute": false, "dca": [13], "pan": "C"},
             "Main": {"fader": -2.5}},
   "sends": [{"from": "Ip 12", "to": "St Aux 1", "level": -6, "pre": true, "on": true, "pan": "L35"},
             {"from": "Grp 2", "to": "Mtx 1", "level": 0}, {"from": "FX Rtn 3", "to": "St Aux 2", "level": "off"}]}
Mix names: Grp n, St Grp n, Aux n, St Aux n, FX n, St FX n, UFX n, Main, Mtx n, St Mtx n (numbered within
their type). Sources: Ip n, FX Rtn n (1-32), UFX Rtn n (1-16), or a mix (groups -> aux/FX/UFX/matrix,
aux/main -> matrix). Levels in dB or "off"; pan 0-74 (37 centre) or C / L50 / R35.
"""
import io, os, re, shutil, struct, sys, tarfile, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KEYS = ["MG", "SG", "mFX", "sFX", "mAux", "sAux", "mMtx", "sMtx"]
STEREO = {"SG", "sFX", "sAux", "sMtx", "Main"}

# ---------------------------------------------------------------- mixer config
class MixConfig:
    """Show/MixConfig/MixConfig.dat: [1, MG, SG, mFX, sFX, mAux, sAux, m7, mode, sMtx, mMtx, PAFL, 23]."""
    def __init__(self, raw):
        self.raw = bytearray(raw)
        assert len(raw) == 13 and raw[0] == 1, raw

    @property
    def counts(self):
        r = self.raw
        return dict(MG=r[1], SG=r[2], mFX=r[3], sFX=r[4], mAux=r[5], sAux=r[6], sMtx=r[9], mMtx=r[10], Main=1,
                    mode=r[8], PAFL=r[11])

    def with_counts(self, c):
        r = bytearray(self.raw)
        r[1], r[2], r[3], r[4], r[5], r[6], r[9], r[10] = c["MG"], c["SG"], c["mFX"], c["sFX"], c["mAux"], c["sAux"], c["sMtx"], c["mMtx"]
        return MixConfig(bytes(r))

    # buses per main mix mode (byte 8: 0 none, 1 LR, 5 5.1, 6 LCR+), from
    # sMixerConfigurationSettings::GetNumberOfMainMixChannels @0x1005676f0; byte 11 = stereo PAFL count
    MAIN_BUSES = (0, 2, 4, 4, 4, 6, 4)

    @staticmethod
    def buses_used(c):
        mode = c.get("mode", 1)
        main = MixConfig.MAIN_BUSES[mode] if mode < len(MixConfig.MAIN_BUSES) else 2
        return (c["MG"] + 2 * c["SG"] + c["mFX"] + 2 * c["sFX"] + c["mAux"] + 2 * c["sAux"] + main
                + 2 * c.get("PAFL", 1) + c["mMtx"] + 2 * c["sMtx"])


# ---------------------------------------------------------------- scene section chain
class SceneFile:
    """Scene .dat: header (name, notes, recall filter, 01 + u32 chain length) + section chain + 1 trailing byte.
    Section = u16be len, label\\0, payload (len counts label + NUL + payload)."""
    def __init__(self, data):
        d = bytes(data)
        self.start = self._find_start(d)
        self.header = bytearray(d[:self.start])
        self.sections, pos = [], self.start
        while pos + 2 <= len(d) - 1:
            n = struct.unpack_from(">H", d, pos)[0]
            body = d[pos + 2:pos + 2 + n]
            z = body.find(b"\x00")
            self.sections.append([body[:z].decode("latin1"), body[z + 1:]])
            pos += 2 + n
        assert pos == len(d) - 1, (pos, len(d))
        self.trailer = d[pos:]

    @staticmethod
    def _find_start(d):
        for p in range(300, min(len(d), 200000)):
            if d[p - 5] == 1 and struct.unpack_from(">I", d, p - 4)[0] == len(d) - p - 1:
                n = struct.unpack_from(">H", d, p)[0]
                if 2 < n < 65536 and d[p + 2:p + 2 + n].find(b"\x00") > 0:
                    return p
        raise ValueError("no section chain")

    def get(self, label):
        for s in self.sections:
            if s[0] == label:
                return s[1]
        raise KeyError(label)

    def set(self, label, payload):
        for s in self.sections:
            if s[0] == label:
                s[1] = bytes(payload); return
        raise KeyError(label)

    def to_bytes(self):
        body = b"".join(struct.pack(">H", len(l) + 1 + len(p)) + l.encode("latin1") + b"\x00" + p for l, p in self.sections)
        hdr = bytearray(self.header)
        struct.pack_into(">I", hdr, len(hdr) - 4, len(body))
        return bytes(hdr) + body + self.trailer


# ---------------------------------------------------------------- cMixer (Input / FX Return / AHFX Return Mixer)
CM_KINDS = ["mFX", "mAux", "sFX", "sAux", "mMtx", "sMtx"]
CM_DEF_MONO, CM_DEF_ST = bytes.fromhex("01008001"), bytes.fromhex("0100800125")

def cm_counts(p):
    return dict(MG=p[1], SG=p[2], mFX=p[3], sFX=p[4], mAux=p[5], sAux=p[6], mMtx=p[7], sMtx=p[8])

def cm_parse(p):
    ver, c = p[0], cm_counts(p)
    ss = lambda k: 4 if k[0] == "m" else 5
    bs = c["MG"] + c["SG"] + sum(c[k] * ss(k) for k in CM_KINDS) + 47 + (40 if ver >= 3 else 0)
    n = (len(p) - 12) // bs
    assert 12 + n * bs == len(p), ("cMixer size", len(p), bs)
    chans = []
    for i in range(n):
        o = 12 + i * bs
        ch = {"MG": list(p[o:o + c["MG"]]), "SG": list(p[o + c["MG"]:o + c["MG"] + c["SG"]])}
        o += c["MG"] + c["SG"]
        for k in CM_KINDS:
            ch[k] = [bytes(p[o + j * ss(k):o + (j + 1) * ss(k)]) for j in range(c[k])]; o += c[k] * ss(k)
        ch["rest"] = bytes(p[o:o + 47 + (40 if ver >= 3 else 0)])
        chans.append(ch)
    return bytearray(p[:12]), c, chans

def cm_build(hdr, c, chans):
    hdr = bytearray(hdr)
    hdr[1:9] = bytes([c["MG"], c["SG"], c["mFX"], c["sFX"], c["mAux"], c["sAux"], c["mMtx"], c["sMtx"]])
    out = bytearray(hdr)
    for ch in chans:
        out += bytes(ch["MG"]) + bytes(ch["SG"])
        for k in CM_KINDS:
            out += b"".join(ch[k])
        out += ch["rest"]
    return bytes(out)

def cm_remap(p, new):
    hdr, old, chans = cm_parse(p)
    for ch in chans:
        ch["MG"] = [ch["MG"][j] if j < old["MG"] else 0 for j in range(new["MG"])]
        ch["SG"] = [ch["SG"][j] if j < old["SG"] else 0 for j in range(new["SG"])]
        for k in CM_KINDS:
            d = CM_DEF_MONO if k[0] == "m" else CM_DEF_ST
            ch[k] = [ch[k][j] if j < old[k] else d for j in range(new[k])]
    return cm_build(hdr, new, chans)


# ---------------------------------------------------------------- cMixMixer (Mix Mixer)
MM_ORDER = ["MG", "SG", "mAux", "sAux", "Main", "mMtx", "sMtx"]
MM_SEND_DEF = bytes.fromhex("0100800125")

def mm_counts(p):
    return dict(MG=p[1], SG=p[2], mFX=p[3], sFX=p[4], mAux=p[5], sAux=p[6], mMtx=p[7], sMtx=p[8], Main=p[9])

def mm_keys(c):
    return [(t, k) for t in MM_ORDER for k in range(c[t])]

def mm_parse(p):
    c = mm_counts(p)
    G = c["MG"] + c["SG"]; M = c["mMtx"] + c["sMtx"]; S = G + c["mAux"] + c["sAux"] + c["Main"]
    o, mixes = 11, {}
    def take(n):
        nonlocal o
        b = bytes(p[o:o + n]); o += n; return b
    for i, key in enumerate(mm_keys(c)):
        m = {}
        if i < G:
            m["mono"] = [take(5) for _ in range(c["mFX"] + c["mAux"])]   # mono FX, then mono aux
            m["st"] = [take(5) for _ in range(c["sFX"] + c["sAux"])]     # stereo FX, then stereo aux
        if i < S:
            m["mtx"] = [take(5) for _ in range(M)]                       # mono mtx, then stereo mtx
        if i < G:
            m["g2g"] = list(take(G)); m["main"] = take(1)
        m["ch"] = take(48)       # 16-byte strip (mute, fader s16 @3, pan @5, mono @7 ...) + 24 DCA + 8 mute groups
        mixes[key] = m
    for key in mm_keys(c)[:G]:
        mixes[key]["ufx"] = take(40)
    assert o == len(p), ("Mix Mixer size", o, len(p))
    return bytearray(p[:11]), c, mixes

def mm_build(hdr, c, mixes):
    hdr = bytearray(hdr)
    hdr[1:9] = bytes([c["MG"], c["SG"], c["mFX"], c["sFX"], c["mAux"], c["sAux"], c["mMtx"], c["sMtx"]])
    out, keys, G = bytearray(hdr), mm_keys(c), c["MG"] + c["SG"]
    for i, key in enumerate(keys):
        m = mixes[key]
        if i < G: out += b"".join(m["mono"]) + b"".join(m["st"])
        if "mtx" in m: out += b"".join(m["mtx"])
        if i < G: out += bytes(m["g2g"]) + m["main"]
        out += m["ch"]
    for key in keys[:G]:
        out += mixes[key]["ufx"]
    return bytes(out)

def mm_new_mix(key, c):
    t = key[0]
    m = {"ch": bytes.fromhex("0000008001250000" "4a80010000250000") + bytes(32)}
    if t not in STEREO:
        m["ch"] = m["ch"][:7] + b"\x01" + m["ch"][8:]
    G = c["MG"] + c["SG"]; M = c["mMtx"] + c["sMtx"]
    if t in ("MG", "SG"):
        m["mono"] = [MM_SEND_DEF] * (c["mFX"] + c["mAux"]); m["st"] = [MM_SEND_DEF] * (c["sFX"] + c["sAux"])
        m["g2g"] = [0] * G; m["main"] = b"\x03"; m["ufx"] = MM_SEND_DEF * 8
    if t not in ("mMtx", "sMtx"):
        m["mtx"] = [MM_SEND_DEF] * M
    return m

def mm_remap(p, new):
    hdr, old, mixes = mm_parse(p)
    new = dict(new, Main=old["Main"])
    def remap(lst, kinds, oc, nc):
        by = {}; i = 0
        for k in kinds:
            for j in range(oc[k]): by[(k, j)] = lst[i]; i += 1
        return [by.get((k, j), MM_SEND_DEF) for k in kinds for j in range(nc[k])]
    out = {}
    for key in mm_keys(new):
        if key not in mixes:
            out[key] = mm_new_mix(key, new); continue
        m = dict(mixes[key])
        if "mono" in m:
            m["mono"] = remap(m["mono"], ["mFX", "mAux"], old, new)
            m["st"] = remap(m["st"], ["sFX", "sAux"], old, new)
            g = m["g2g"]; og = {("MG", j): g[j] for j in range(old["MG"])}
            og.update({("SG", j): g[old["MG"] + j] for j in range(old["SG"])})
            m["g2g"] = [og.get((t, j), 0) for t in ("MG", "SG") for j in range(new[t])]
        if "mtx" in m:
            m["mtx"] = remap(m["mtx"], ["mMtx", "sMtx"], old, new)
        out[key] = m
    return mm_build(hdr, new, out)


# ---------------------------------------------------------------- per-mix processing sections
CH_NAME = {"MG": "Mono Group Channel", "SG": "Stereo Group Channel", "mAux": "Mono Aux Channel",
           "sAux": "Stereo Aux Channel", "Main": "Main Channel", "mMtx": "Mono Matrix Channel",
           "sMtx": "Stereo Matrix Channel"}
SSS_NAME = {"MG": "Mono Group", "SG": "Stereo Group", "mFX": "Mono FX", "mAux": "Mono Aux", "sFX": "Stereo FX",
            "sAux": "Stereo Aux", "Main": "Main", "UFX": "UFX"}
SC_TYPE = {"MG": 2, "SG": 3, "mAux": 4, "sAux": 5, "Main": 8, "mMtx": 0x0A, "sMtx": 0x0B}
DEFAULTS = {   # Director V2.12 defaults, read from freshly created mixes
    "Parametric EQ": "04000047970d00000000000065970d000000000000a72e0d000000000000cb2e0d0000000000",
    "Graphic EQ": "038000800080008000800080008000800080008000800080008000800080008000800080008000800080008000800080"
                  "0080008000800080000000000038540d00000000000047970d00000000000058530d00000000000065970d0000000000"
                  "006e530d000000000000821e0d0000000000009b970d000000000000a72e0d000000000000b92e0d000000000000c1eb"
                  "0d000000000000cb2e0d000000000000d1fe0d000000000000",
    "Compressor": "08010000008001000000553f7a8e00140000000000000000007a8e00ba2d849f0000000000000000006d5c000000000000"
                  "0000000000000000000000320032000000000000000000000000000000000000000000000000000000000000000000000000"
                  "000000000000000041970d000400000000dd2e0d0003000001006597",
    "Mix Delay": "01000000", "Digital Attenuator": "01000000000000", "Insert": "020000", "Send Source Select": "020700",
}
BLOCK_FAMILIES = ["Parametric EQ", "Graphic EQ", "Compressor"]
PER_CHANNEL = ["Mix Delay", "Digital Attenuator", "Compressor side chain source", "Insert"]

def _sides(t):
    return ["Left", "Right"] if t in STEREO else [""]

def mix_channels(c):
    """(type, index, side, label-suffix) for every mix channel that carries processing."""
    out = []
    for t in MM_ORDER:
        for k in range(c[t] if t != "Main" else 1):
            for s in _sides(t):
                out.append((t, k, s, "%s %02d %s" % (CH_NAME[t], k + 1, s)))
    return out

def sss_channels(c):
    out = []
    for t in ["MG", "SG", "mFX", "mAux", "sFX", "sAux", "Main", "UFX"]:
        n = 8 if t == "UFX" else 1 if t == "Main" else c[t]
        for k in range(n):
            for s in (["Left", "Right"] if t in STEREO or t == "UFX" else [""]):
                out.append((t, k, "%s %02d %s" % (SSS_NAME[t], k + 1, s)))
    return out

_MIXLBL = re.compile(r"(Mono|Stereo) (Group|Aux|Matrix) Channel \d\d( Left| Right| )$|Main Channel \d\d (Left|Right)$")
_SSSLBL = re.compile(r"(Mono |Stereo )?(Group|Aux|FX) \d\d( Left| Right| )$|Main \d\d (Left|Right)$|UFX \d\d (Left|Right)$")

def _replace_run(sections, is_member, new_items):
    idx = [i for i, s in enumerate(sections) if is_member(s[0])]
    assert idx and idx == list(range(idx[0], idx[-1] + 1)), "processing run not contiguous"
    sections[idx[0]:idx[-1] + 1] = new_items

def rebuild_processing(scene, new):
    have = {l: p for l, p in scene.sections}
    chans = mix_channels(new)
    def payload(label, fam, t, k):
        if label in have: return have[label]
        if fam == "Compressor side chain source": return bytes([1, SC_TYPE[t], k])
        return bytes.fromhex(DEFAULTS[fam])
    for fam in BLOCK_FAMILIES:
        pre = fam + ", "
        items = [[pre + suf, payload(pre + suf, fam, t, k)] for t, k, s, suf in chans]
        _replace_run(scene.sections, lambda l: l.startswith(pre) and bool(_MIXLBL.match(l[len(pre):])), items)
    items = [[f + ", " + suf, payload(f + ", " + suf, f, t, k)] for t, k, s, suf in chans for f in PER_CHANNEL]
    _replace_run(scene.sections, lambda l: any(l.startswith(f + ", ") and _MIXLBL.match(l[len(f) + 2:]) for f in PER_CHANNEL), items)
    pre = "Send Source Select, "
    items = [[pre + suf, have.get(pre + suf, bytes.fromhex(DEFAULTS["Send Source Select"]))] for t, k, suf in sss_channels(new)]
    _replace_run(scene.sections, lambda l: l.startswith(pre) and bool(_SSSLBL.match(l[len(pre):])), items)


# ---------------------------------------------------------------- scene safes / recall filter
from dlive_safes import fit as safes_fit, BODY as SAFES_BODY

def fit_scene_header(scene, oldcfg, newcfg):
    h = scene.header
    i = bytes(h).find(b"\x15" + bytes(oldcfg.raw))
    assert 0 < i < 4000 and i + 14 + SAFES_BODY + 5 == len(h), "scene header recall filter not found"
    pseudo = b"\x01\x01" + bytes(h[i:i + 14 + SAFES_BODY])
    h[i:i + 14 + SAFES_BODY] = safes_fit(pseudo, oldcfg.counts, newcfg.counts, bytes(newcfg.raw))[2:]


# ---------------------------------------------------------------- follow pan
def follow_pan(text, new):
    lines = text.decode().split("\n")
    assert lines[0] == "1"
    have = {}
    for l in lines[1:]:
        if l.strip():
            t, i, a, b = l.split(","); have[(int(t), int(i))] = (a, b)
    out = ["1"]
    for t, n in ((5, new["sAux"]), (7, new["sFX"]), (19, 8), (11, new["sMtx"])):
        for i in range(n):
            a, b = have.get((t, i), ("0", "0")); out.append("%d,%d,%s,%s" % (t, i, a, b))
    return ("\n".join(out) + "\n").encode()


# ---------------------------------------------------------------- mix edits: masters, sends, names
NAME_MANAGER = {"MG": "Mono Group Channel", "SG": "Stereo Group Channel", "mAux": "Mono Aux Channel",
                "sAux": "Stereo Aux Channel", "mFX": "Mono FX Send Channel", "sFX": "Stereo FX Send Channel",
                "UFX": "Stereo AHFX Send Channel", "Main": "Main Channel", "mMtx": "Mono Matrix Channel",
                "sMtx": "Stereo Matrix Channel"}
_MIXNAME = [(r"main", "Main"), (r"st ?(grp|group)", "SG"), (r"(grp|group)", "MG"), (r"st ?aux", "sAux"),
            (r"aux", "mAux"), (r"st ?fx", "sFX"), (r"fx", "mFX"), (r"st ?(mtx|matrix)", "sMtx"),
            (r"(mtx|matrix)", "mMtx"), (r"ufx", "UFX")]
LEVEL_OFF = -32767

def parse_mix(name):
    """'St Aux 3' -> ('sAux', 2); 'Grp 1', 'Aux 4', 'FX 2', 'St FX 1', 'Mtx 2', 'St Mtx 1', 'UFX 3', 'Main'."""
    low = name.strip().lower()
    for pat, t in _MIXNAME:
        m = re.fullmatch(pat + r"\s*(\d+)?", low)
        if m:
            n = int(m.group(m.lastindex)) if m.lastindex and m.group(m.lastindex) and m.group(m.lastindex).isdigit() else 1
            return (t, n - 1)
    raise ValueError("unknown mix %r" % name)

def parse_source(name):
    low = name.strip().lower()
    m = re.fullmatch(r"(ip|input)\s*(\d+)", low)
    if m: return ("Ip", int(m.group(2)) - 1)
    m = re.fullmatch(r"(u?fx) ?(rtn|return)\s*(\d+)", low)
    if m: return ("UFXR" if m.group(1) == "ufx" else "FXR", int(m.group(3)) - 1)
    return parse_mix(name)

def level_raw(db):
    if db is None or (isinstance(db, str) and db.lower() in ("off", "-inf")) or float(db) <= -127:
        return LEVEL_OFF
    return max(-32767, min(32767, int(round(float(db) * 256))))

def pan_raw(p):
    """0..74 (37 = centre), or 'C', 'L50', 'R35' (percent of full width)."""
    if isinstance(p, int): return p
    p = p.strip().upper()
    if p in ("C", "CENTRE", "CENTER"): return 37
    return round(37 + (-1 if p[0] == "L" else 1) * float(p[1:]) * 0.37)

def edit_send(b, level=None, pre=None, on=None, pan=None):
    """send = [on, pre, level s16be (dB*256), pan (stereo destinations only)]."""
    b = bytearray(b)
    if on is not None: b[0] = 1 if on else 0
    if pre is not None: b[1] = 1 if pre else 0
    if level is not None: struct.pack_into(">h", b, 2, level_raw(level))
    if pan is not None and len(b) == 5: b[4] = pan_raw(pan)
    return bytes(b)

CM_SECTION = {"Ip": "Input Mixer", "FXR": "FX Return Mixer", "UFXR": "AHFX Return Mixer"}

def apply_mix_plan(scene, plan):
    """Edit one SceneFile in place: plan keys 'sends' and 'mixes' (see the module docstring)."""
    cms = {lab: cm_parse(scene.get(lab)) for lab in CM_SECTION.values()}
    hdr, c, mixes = mm_parse(scene.get("Mix Mixer"))
    for s in plan.get("sends", []):
        src, dst = parse_source(s["from"]), parse_mix(s["to"])
        kw = {k: s[k] for k in ("level", "pre", "on", "pan") if k in s}
        if src[0] in CM_SECTION:
            h, cc, chans = cms[CM_SECTION[src[0]]]
            ch = chans[src[1]]
            if dst[0] == "UFX":
                rest = bytearray(ch["rest"]); o = 47 + 5 * dst[1]
                rest[o:o + 5] = edit_send(rest[o:o + 5], **kw); ch["rest"] = bytes(rest)
            else:
                assert dst[1] < cc[dst[0]], "%s does not exist in this mixer config" % s["to"]
                ch[dst[0]][dst[1]] = edit_send(ch[dst[0]][dst[1]], **kw)
        else:
            m = mixes[src]
            if dst[0] == "UFX":
                assert "ufx" in m, "only groups send to UFX"
                u = bytearray(m["ufx"]); u[5 * dst[1]:5 * dst[1] + 5] = edit_send(u[5 * dst[1]:5 * dst[1] + 5], **kw)
                m["ufx"] = bytes(u); continue
            lst, i = {"mFX": ("mono", 0), "mAux": ("mono", c["mFX"]), "sFX": ("st", 0), "sAux": ("st", c["sFX"]),
                      "mMtx": ("mtx", 0), "sMtx": ("mtx", c["mMtx"])}[dst[0]]
            assert lst in m, "%s cannot send to %s" % (s["from"], s["to"])
            assert dst[1] < c[dst[0]], "%s does not exist in this mixer config" % s["to"]
            m[lst][i + dst[1]] = edit_send(m[lst][i + dst[1]], **kw)
    for name, v in plan.get("mixes", {}).items():
        key = parse_mix(name)
        if key not in mixes:
            continue   # FX / UFX sends have no Mix Mixer strip (names only)
        ch = bytearray(mixes[key]["ch"])
        if "mute" in v: ch[2] = 1 if v["mute"] else 0
        if "fader" in v: struct.pack_into(">h", ch, 3, level_raw(v["fader"]))
        if "pan" in v: ch[5] = pan_raw(v["pan"])
        if "dca" in v: ch[16:40] = bytes(1 if k + 1 in v["dca"] else 0 for k in range(24))
        if "mute_groups" in v: ch[40:48] = bytes(1 if k + 1 in v["mute_groups"] else 0 for k in range(8))
        mixes[key]["ch"] = bytes(ch)
    for lab, (h, cc, chans) in cms.items():
        scene.set(lab, cm_build(h, cc, chans))
    scene.set("Mix Mixer", mm_build(hdr, c, mixes))
    data = scene.to_bytes()
    if any("name" in v or "colour" in v for v in plan.get("mixes", {}).values()):
        from dlive_scene import Scene
        s = Scene(data)
        for name, v in plan.get("mixes", {}).items():
            t, k = parse_mix(name)
            if "name" in v or "colour" in v:
                s.set_name(NAME_MANAGER[t], k + 1, v.get("name"), v.get("colour"))
        data = bytes(s.d)
    return data

def apply_show(src, plan, out):
    """Optional plan['config'] first (live scene, as Director), then sends/mixes/names into every StageBox
    scene that has the live scene's mixer config, so recalling a scene keeps the edits."""
    if plan.get("config"):
        tmp = out + ".cfg.tar.gz"
        reconfigure(src, tmp, **plan["config"]); src = tmp
    members, files = read_show(src)
    live = next(n for n in files if n.endswith("Scenes/StageBoxScene65535.tar.gz"))
    want = SceneFile(next(iter(inner(files[live])[1].values()))).get("Mix Mixer")[:11]
    edited = skipped = 0
    for n in sorted(files):
        if "/Scenes/StageBoxScene" not in n: continue
        ms, inn = inner(files[n])
        (dn,) = inn
        if b"Mix Mixer\x00" not in inn[dn]: continue
        sc = SceneFile(inn[dn])
        if sc.get("Mix Mixer")[:11] != want:
            skipped += 1; continue
        inn[dn] = apply_mix_plan(sc, plan)
        files[n] = repack_inner(ms, inn); edited += 1
    write_show(members, files, out)
    if plan.get("config"): os.unlink(src)
    return edited, skipped


# ---------------------------------------------------------------- show level
def read_show(path):
    with tarfile.open(path) as t:
        members = t.getmembers()
        files = {m.name: t.extractfile(m).read() for m in members if m.isfile()}
    return members, files

def write_show(members, files, out):
    with tarfile.open(out, "w:gz", format=tarfile.USTAR_FORMAT) as dst:
        for m in members:
            m.mtime = int(m.mtime); m.pax_headers = {}
            if m.isfile():
                m.size = len(files[m.name]); dst.addfile(m, io.BytesIO(files[m.name]))
            else:
                dst.addfile(m)

def inner(blob):
    with tarfile.open(fileobj=io.BytesIO(blob)) as t:
        ms = t.getmembers()
        return ms, {m.name: t.extractfile(m).read() for m in ms if m.isfile()}

def repack_inner(ms, files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as t:
        for m in ms:
            m.mtime = int(m.mtime); m.pax_headers = {}
            if m.isfile():
                m.size = len(files[m.name]); t.addfile(m, io.BytesIO(files[m.name]))
            else:
                t.addfile(m)
    return buf.getvalue()

def reconfigure(src, out, **changes):
    members, files = read_show(src)
    assert files["Show/Version.dat"].strip() == b"14", "show format %r not supported (needs Version 14, firmware 2.x)" % files["Show/Version.dat"]
    oldcfg = MixConfig(files["Show/MixConfig/MixConfig.dat"])
    assert oldcfg.raw[7] == 1 and oldcfg.raw[8] == 1, "only LR main mode is supported"
    old = oldcfg.counts
    new = dict(old); new.update({k: int(v) for k, v in changes.items()})
    unknown = set(changes) - set(KEYS)
    assert not unknown, "unknown keys %s (use %s)" % (unknown, KEYS)
    used = MixConfig.buses_used(new)
    assert used <= 64, "config needs %d of 64 mix buses" % used
    newcfg = oldcfg.with_counts(new)
    files["Show/MixConfig/MixConfig.dat"] = bytes(newcfg.raw)
    fp = "Show/FollowPanSettings/FollowPanSettings.dat"
    if fp in files: files[fp] = follow_pan(files[fp], new)
    for n in list(files):
        if n.startswith("Show/SceneSafes/StageBox") and len(files[n]) == SAFES_BODY + 16:
            assert files[n][3:16] == bytes(oldcfg.raw), n
            files[n] = bytes(safes_fit(files[n], old, new, bytes(newcfg.raw)))
    live = next(n for n in files if n.endswith("Scenes/StageBoxScene65535.tar.gz"))
    ms, inn = inner(files[live])
    (dname,) = [k for k in inn]
    sc = SceneFile(inn[dname])
    for lab in ("Input Mixer", "FX Return Mixer", "AHFX Return Mixer"):
        sc.set(lab, cm_remap(sc.get(lab), new))
    sc.set("Mix Mixer", mm_remap(sc.get("Mix Mixer"), new))
    rebuild_processing(sc, dict(new, Main=1))
    fit_scene_header(sc, oldcfg, newcfg)
    inn[dname] = sc.to_bytes()
    files[live] = repack_inner(ms, inn)
    write_show(members, files, out)
    return old, new, used


def show_config(path):
    _, files = read_show(path)
    c = MixConfig(files["Show/MixConfig/MixConfig.dat"]).counts
    return c, MixConfig.buses_used(c)


def print_mixes(path):
    _, files = read_show(path)
    live = next(n for n in files if n.endswith("Scenes/StageBoxScene65535.tar.gz"))
    ms, inn = inner(files[live])
    sc = SceneFile(next(iter(inn.values())))
    hdr, c, mixes = mm_parse(sc.get("Mix Mixer"))
    for key in mm_keys(c):
        m = mixes[key]; ch = m["ch"]
        fader = struct.unpack(">h", ch[3:5])[0]
        f = "-inf" if fader <= -32767 else "%+.1f" % (fader / 256)
        dca = [k + 1 for k in range(24) if ch[16 + k]]; mg = [k + 1 for k in range(8) if ch[40 + k]]
        mtx = [i + 1 for i, s in enumerate(m.get("mtx", [])) if s[0] and struct.unpack(">h", s[2:4])[0] > -32767]
        print("%-5s %2d  fader %6s  mute %d  dca %s  mg %s  to-mtx %s" % (key[0], key[1] + 1, f, ch[2], dca, mg, mtx))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "config":
        c, used = show_config(a[1]); print(c, "buses used %d/64" % used)
    elif len(a) >= 3 and a[0] == "reconfigure":
        kv = dict(x.split("=") for x in a[3:])
        old, new, used = reconfigure(a[1], a[2], **kv)
        print("mixer config", {k: old[k] for k in KEYS}, "->", {k: new[k] for k in KEYS}, "buses %d/64 ->" % used, a[2])
    elif len(a) == 2 and a[0] == "mixes":
        print_mixes(a[1])
    elif len(a) == 4 and a[0] == "apply":
        import json
        e, s = apply_show(a[1], json.load(open(a[2])), a[3])
        print("edited %d StageBox scenes (%d skipped: other mixer config) -> %s" % (e, s, a[3]))
    else:
        sys.exit(__doc__)
