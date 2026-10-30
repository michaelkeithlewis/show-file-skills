#!/usr/bin/env python3
"""Decode dLive input-channel processing from a show file into physical units.

Decoded from dLive Director V2.12 (symbols + objdump; notes: references/format-processing.md).
Scene sections are "<Family>[,] Input Channel NN" (NN zero padded) in each StageBox scene; the live
state is StageBoxScene65535. Every multi-byte value is big endian.

usage:
  dlive_proc.py dump <show.tar.gz> [--scene 65535] [--ch 1-64] [--raw]
  dlive_proc.py table <show.tar.gz> [--scene 65535] [--ch 1,2,3]   (one line per channel)

Fields this tool could not tie to a confirmed conversion are emitted as {"?raw": "<hex>"} or under a
"raw" key, never guessed.
"""
import argparse, io, json, math, os, re, struct, sys, tarfile

DLIVE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DLIVE)
from dlive_mix import SceneFile
import dlive_patch as DP

def gain_db(s16):
    """GAIN: signed 1/256 dB. 0x8001 (-32767) is -inf (UWORDToGain @0x1001039a0, GainToString /256)."""
    return None if s16 <= -32767 else round(s16 / 256.0, 3)

def freq_hz(u16):
    """UWORDToFreq @0x1001103e0: 4 * 2^(u/4608)."""
    return round(4.0 * 2.0 ** (u16 / 4608.0), 2)

def time_s(u16):
    """UWORDToTime @0x100110440: 0 -> 0, else 10^((u-1) * 11/65536) microseconds."""
    return 0.0 if u16 == 0 else 10.0 ** ((u16 - 1) * 0.0001678466796875) * 1e-6

def time_ms(u16):
    return round(time_s(u16) * 1000.0, 4)

WIDTH_Q = [0.92, 0.991, 1.073, 1.169, 1.281, 1.415, 1.492, 1.578, 1.673, 1.781, 1.903, 2.041, 2.145, 2.388,
           2.608, 2.872, 3.194, 3.596, 4.319, 4.801, 5.765, 7.209, 8.653, 11.096, 12.022]

def width(u16):
    idx = min(u16 >> 8, 24)
    q = WIDTH_Q[idx]
    bw = 2.0 / math.log(2) * math.asinh(1.0 / (2.0 * q))
    return dict(q=q, width_oct=round(bw, 3), width_index=idx)

PEQ_TYPE = {0: "bell", 1: "lf_shelf", 2: "hf_shelf", 3: "lpf", 4: "hpf"}
HPF_TYPE = {0: (12, "12dB Butterworth"), 1: (18, "18dB Butterworth"), 2: (24, "24dB Butterworth"),
            3: (18, "18dB Bessel"), 5: (6, "6dB Butterworth")}
GATE_TYPE = {0: "gate", 1: "ducker", 2: "dual_threshold_expander", 3: "source_expander"}
COMP_TYPE = {0: "manual_peak", 1: "manual_rms", 2: "opto", 3: "16T", 4: "16VU", 5: "ducker", 6: "amp76",
             7: "mighty", 8: "level_amp", 9: "bus", 10: "distressor"}
RATIO_MANUAL = [1.0, 1.025, 1.05, 1.075, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0,
                2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0, 7.0,
                8.0, 10.0, 12.0, 16.0, 20.0, 40.0, 60.0]
RATIO_16T = [1.0, 1.025, 1.05, 1.1, 1.2, 1.3, 1.5, 1.7, 2.0, 2.1, 2.25, 2.5, 2.6, 2.75, 2.85, 3.0, 3.1, 3.25,
             3.5, 3.75, 4.0, 4.25, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0, 12.0, 16.0, 20.0, 60.0, 60.0, -5.0,
             -3.2, -2.0, -1.7, -1.5, -1.2, -1.0]
RATIO_16VU = [1.0, 1.1, 1.25, 1.5, 1.6, 1.75, 2.0, 2.1, 2.25, 2.5, 2.6, 2.75, 2.85, 3.0, 3.1, 3.25, 3.5, 3.6,
              3.75, 3.85, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0, 10.0,
              12.0, 16.0, 20.0, 30.0, 40.0, 60.0]
RATIO_OPTO = [1.2] * 7 + [1.5] * 7 + [2.0] * 6 + [3.0] * 7 + [4.0] * 7 + [6.0] * 6 + [10.0]
RATIO_TABLE = {0: RATIO_MANUAL, 1: RATIO_MANUAL, 2: RATIO_OPTO, 3: RATIO_16T, 4: RATIO_16VU}
FIXED_TIMES = {3: (1.5, 130.0), 4: (0.5, 80.0)}
DISTRESSOR_RATIO = ["2:1", "3:1", "4:1", "6:1", "10:1", "20:1", "Smash", "Brit"]

u8 = lambda b, o: b[o]
u16 = lambda b, o: struct.unpack_from(">H", b, o)[0]
s16 = lambda b, o: struct.unpack_from(">h", b, o)[0]
raw = lambda b: {"?raw": b.hex()}

def biquad_band(b, o, gain_signed=True):
    """9-byte band: gain(GAIN) freq(u16) width(u16) type(u8) qtype(u8) bypass(u8).
    cBiquadFourBandNetObject::FillGetStatus @0x100b28310 / SetBandFullData @0x100b27b20."""
    t = u8(b, o + 6)
    d = dict(type=PEQ_TYPE.get(t, "type_%d" % t), gain_db=gain_db(s16(b, o)), freq_hz=freq_hz(u16(b, o + 2)))
    d.update(width(u16(b, o + 4)))
    d["constant_q"] = bool(u8(b, o + 7))
    d["band_bypass"] = bool(u8(b, o + 8))
    return d

def dec_peq(b):
    if len(b) != 38 or b[0] != 4: return raw(b)
    return dict(bypass=bool(b[37]), bands=[biquad_band(b, 1 + 9 * k) for k in range(4)])

def dec_lpf(b):
    if len(b) != 11 or b[0] != 4: return raw(b)
    band = biquad_band(b, 1)
    return dict(bypass=bool(b[10]), freq_hz=band["freq_hz"], type=band["type"], q=band["q"])

def dec_hpf(b):
    """cHighPassFilter::FillGetStatus @0x100297c80: ver 3, freq u16, type u8, bypass u8 (+0x98 =
    MIDISetHPFBypassed). Type list cFiltersForm::CreateUI + map table @0x1029aeaa0."""
    if len(b) != 5 or b[0] != 3: return raw(b)
    slope, name = HPF_TYPE.get(b[3], (None, "type_%d" % b[3]))
    return dict(bypass=bool(b[4]), freq_hz=freq_hz(u16(b, 1)), slope_db_oct=slope, type=name)

def scf_body(b, o):
    """Two side-chain bands (HPF, LPF) at o and o+9, then bypass, bandpass on, bandpass freq."""
    b1, b2 = biquad_band(b, o), biquad_band(b, o + 9)
    return dict(bypass=bool(b[o + 18]),
                hpf=dict(freq_hz=b1["freq_hz"], type=b1["type"], band_bypass=b1["band_bypass"]),
                lpf=dict(freq_hz=b2["freq_hz"], type=b2["type"], band_bypass=b2["band_bypass"]),
                bandpass=bool(b[o + 19]), bandpass_freq_hz=freq_hz(u16(b, o + 20)))

def dec_scf(b):
    """Gate side-chain filter section: cGateSideChainPEQNetObject::FillGetStatus @0x1002db340
    (ver 4 + body). The compressor embeds the same body without a version byte at offset 105."""
    if len(b) != 23 or b[0] != 4: return raw(b)
    return scf_body(b, 1)

def dec_gate(b):
    """cGate::FillGetStatus @0x1002921b0, field owners from cGate::Set* setters."""
    if len(b) != 19 or b[0] != 3: return raw(b)
    t = b[1]
    return dict(enable=bool(b[18]), type=GATE_TYPE.get(t, "type_%d" % t),
                threshold_db=gain_db(s16(b, 2)), upper_threshold_db=gain_db(s16(b, 4)),
                lower_threshold_db=gain_db(s16(b, 6)), depth_db=gain_db(s16(b, 8)),
                hold_ms=time_ms(u16(b, 10)), release_ms=time_ms(u16(b, 13)), attack_ms=time_ms(u16(b, 15)),
                raw=dict(release_type=b[12], timing_selection=b[17]))

def dec_comp(b):
    """cCompressor::FillGetStatus @0x1001fb4b0 (127 bytes), field owners from cCompressor::Set*,
    conversions from cCompressorSystemFunctions::SendAll_*_Settings_ToDriver."""
    if len(b) != 127 or b[0] != 8: return raw(b)
    t = b[1]
    tab = RATIO_TABLE.get(t)
    ri = u16(b, 14)
    generic = dict(threshold_db=gain_db(s16(b, 8)),
                   ratio=(tab[ri] if tab and ri < len(tab) else None), ratio_index=ri,
                   attack_ms=time_ms(u16(b, 10)), release_ms=time_ms(u16(b, 12)),
                   knee="soft" if b[18] else "hard", makeup_db=gain_db(s16(b, 16)))
    uses = {0: ("threshold_db", "ratio", "ratio_index", "attack_ms", "release_ms", "knee", "makeup_db"),
            1: ("threshold_db", "ratio", "ratio_index", "attack_ms", "release_ms", "knee", "makeup_db"),
            2: ("threshold_db", "ratio", "ratio_index", "knee", "makeup_db"),
            3: ("threshold_db", "ratio", "ratio_index", "knee", "makeup_db"),
            4: ("threshold_db", "ratio", "ratio_index", "knee", "makeup_db"),
            5: ("threshold_db", "attack_ms", "release_ms", "makeup_db"),
            9: ("makeup_db",)}.get(t, ())
    d = dict(enable=bool(b[2]), model=COMP_TYPE.get(t, "type_%d" % t))
    d.update({k: v for k, v in generic.items() if k in uses})
    d["stored_unused"] = {k: v for k, v in generic.items() if k not in uses}
    d["parallel"] = dict(on=bool(b[7]), wet_db=gain_db(s16(b, 3)), dry_db=gain_db(s16(b, 5)))
    if t in FIXED_TIMES:
        d["fixed_attack_ms"], d["fixed_release_ms"] = FIXED_TIMES[t]
    if t == 5:
        d["ducker"] = dict(depth_db=gain_db(s16(b, 23)), hold_ms=time_ms(u16(b, 25)))
    if t == 6:
        d["amp76"] = dict(ratio_state=b[27], ratio_label_assumed=["4:1", "8:1", "12:1", "20:1", "all"][b[27]] if b[27] < 5 else None,
                          threshold_db_from_state=[-6.0, -6.0, -4.5, -3.0, -1.0][b[27]] if b[27] < 5 else None,
                          rubber_band=b[32], in_gain_db=gain_db(s16(b, 34)), out_gain_db=gain_db(s16(b, 36)),
                          raw=dict(attack=u16(b, 28), release=u16(b, 30)))
    if t == 7:
        d["mighty"] = dict(detector=b[38], in_gain_db=gain_db(s16(b, 39)), release_ms=time_ms(u16(b, 41)))
    if t == 8:
        d["level_amp"] = dict(raw=dict(r37=u16(b, 43), limit=b[45], peak=u16(b, 46), gain=u16(b, 48)))
    if t == 9:
        d["bus"] = dict(raw=dict(threshold=u16(b, 50), attack=u16(b, 52), release=u16(b, 54), ratio=u16(b, 56)))
    if t == 10:
        d["distressor"] = dict(ratio_state=b[58], ratio_label=DISTRESSOR_RATIO[b[58]] if b[58] < 8 else None, in_gain_db=gain_db(s16(b, 63)), out_gain_db=gain_db(s16(b, 65)),
                               raw=dict(attack=u16(b, 59), release=u16(b, 61), distortion=b[67], scf=b[68]))
    if t in (3, 4):
        d["states"] = dict(attack=b[19], recovery=b[20], burn=b[21], transient=b[22])
    d["ab_state"] = b[33]
    d["sidechain_filter"] = scf_body(b, 105)
    if t in (6, 7, 8, 9, 10): d["sidechain_filter"]["note"] = "model may repurpose these fields"
    return d

def dec_atten(b):
    """cDigitalAttenuator::GetStatus @0x10020e990: ver 1, trim GAIN, phase, mute (Director 2.11 writes
    2 extra trailing bytes, reported raw)."""
    if len(b) < 5 or b[0] != 1: return raw(b)
    d = dict(trim_db=gain_db(s16(b, 1)), polarity_inverted=bool(b[3]), mute=bool(b[4]))
    if len(b) > 5: d["extra_raw"] = b[5:].hex()
    return d

def dec_delay(b):
    """cDelay::GetStatus @0x10020cb30: ver 1, delay u16 in samples at 96 kHz (FPGA max 0x7fff = 341.3 ms,
    cFPGADelayUnit::WriteDelayAmount), bypass."""
    if len(b) != 4 or b[0] != 1: return raw(b)
    n = u16(b, 1)
    return dict(bypass=bool(b[3]), samples=n, ms=round(n / 96.0, 3))

def dec_insert(b):
    """cInsertNetObject::GetStatus @0x1002aefc0: ver 2, bypass (InsertBypass), level mode."""
    if len(b) != 3 or b[0] != 2: return raw(b)
    return dict(bypass=bool(b[1]), level_mode=b[2])

def dec_source(b):
    if len(b) != 3 or b[0] != 1: return raw(b)
    return dict(type=b[1], channel=b[2] + 1)

def dec_preamp_model(b):
    """cPreampModel::FillGetStatus @0x1002de780 (18 bytes); field meaning not mapped."""
    if len(b) != 18 or b[0] != 2: return raw(b)
    return {"model": b[1], "?raw": b.hex()}

def dec_analogue(b):
    """cAnalogueInput::GetStatus @0x1004f86a0: ver 1, gain GAIN (whole dB, SetGain masks 0xff00), pad, 48V."""
    if len(b) != 5 or b[0] != 1: return raw(b)
    return dict(gain_db=gain_db(s16(b, 1)), pad=bool(b[3]), phantom_48v=bool(b[4]))

FAMILY = {"Highpass Filter": ("hpf", dec_hpf), "Lowpass Filter": ("lpf", dec_lpf),
          "Gate": ("gate", dec_gate), "SCF Gate": ("gate_sidechain_filter", dec_scf),
          "Gate side chain source": ("gate_key_source", dec_source),
          "Parametric EQ": ("peq", dec_peq), "Compressor": ("comp", dec_comp),
          "Compressor side chain source": ("comp_key_source", dec_source),
          "Digital Attenuator": ("trim", dec_atten), "Delay": ("delay", dec_delay),
          "Insert 1": ("insert_1", dec_insert), "Insert 2": ("insert_2", dec_insert),
          "Preamp Model": ("preamp_model", dec_preamp_model)}

def read_show(path):
    with tarfile.open(path) as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers() if m.isfile()}

def scene_bytes(F, scene):
    name = next(n for n in F if n.endswith("StageBoxScene%s.tar.gz" % scene))
    with tarfile.open(fileobj=io.BytesIO(F[name])) as t:
        (m,) = [m for m in t.getmembers() if m.isfile()]
        return t.extractfile(m).read()

def names(sc):
    p = sc.get("Input Channel Name Colour Manager")
    n = (len(p) - 1) // 10
    return [p[1 + 9 * k:10 + 9 * k].split(b"\x00")[0].decode("latin1") for k in range(n)]

def text_lines(F, path):
    v = F.get(path)
    return v.decode("latin1").split() if v else None

PRE_RE = [(re.compile(r"StageBox Analogue Input, Number (\d+)$"), "mixrack"),
          (re.compile(r"StageBox TSnake Analogue Input, Number (\d+)$"), "dx"),
          (re.compile(r"StageBox Port B TSnake Analogue Input, Slot (\d+),? Number (\d+)$"), "io")]

def preamp_sections(sc):
    out = {}
    for lab, p in sc.sections:
        for rx, kind in PRE_RE:
            m = rx.match(lab)
            if m: out[(kind,) + tuple(int(g) for g in m.groups())] = p
    return out

def preamp_key(t, n):
    """Socket -> (analogue input section key, certain?). MixRack sockets are certain (48V byte verified
    against Director-saved shows); DX and I/O-port remote preamps are assumed."""
    if t == DP.T_MIXRACK: return ("mixrack", n + 1), True
    if t == DP.T_DX12: return ("dx", n + 1), False
    if t == DP.T_DX34: return ("dx", n + 33), False
    if t in (DP.T_IO1, DP.T_IO2, DP.T_IO3): return ("io", t - DP.T_IO1 + 1, n + 1), False
    return None, False

def decode_show(path, scene="65535", chans=range(1, 129), with_raw=False):
    F = read_show(path)
    data = scene_bytes(F, scene)
    sc = SceneFile(data)
    sec = {}
    for lab, p in sc.sections:
        m = re.match(r"(.*?),? ?Input Channel (\d+)$", lab)
        if m: sec[(m.group(1), int(m.group(2)))] = p
    pre_secs = preamp_sections(sc)
    nm = names(sc)
    pairs = text_lines(F, "Show/InputConfig/InputConfig.dat")
    order = text_lines(F, "Show/ProcessingOrdering/InputProcessingOrdering.dat")
    try:
        patch = DP.Patch(data)
    except Exception:
        patch = None
    out = []
    for ch in chans:
        d = dict(ch=ch, name=nm[ch - 1] if ch <= len(nm) else None)
        if pairs and len(pairs) > 64:
            k = (ch - 1) // 2
            d["stereo_pair"] = pairs[1 + k] == "1"
        if order and len(order) > ch:
            d["peq_before_comp"] = order[ch] == "true"
        if patch:
            ip = patch.input(ch)
            act = ip["active"]
            t, n = ip["sources"][act - 1 if 1 <= act <= 4 else 0]
            src = DP.describe(t, n)
            key, sure = preamp_key(t, n)
            pre = dec_analogue(pre_secs[key]) if key in pre_secs else None
            if pre is not None and not sure: pre["socket_mapping"] = "assumed"
            d["source"] = dict(active="ABCD"[act - 1] if 1 <= act <= 4 else "off", socket=src)
            d["preamp"] = pre
        for fam, (key, fn) in FAMILY.items():
            p = sec.get((fam, ch))
            if p is not None:
                d[key] = fn(p)
                if with_raw: d.setdefault("_raw", {})[key] = p.hex()
        out.append(d)
    return out

def parse_ch(s):
    if not s: return range(1, 129)
    res = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        res += list(range(int(a), int(b or a) + 1))
    return res

def short(c):
    def f(x, nd=0):
        return "-inf" if x is None else ("%.*f" % (nd, x))
    pre = c.get("preamp") or {}
    hp = c.get("hpf", {}); g = c.get("gate", {}); co = c.get("comp", {}); pq = c.get("peq", {}); tr = c.get("trim", {})
    s = "%3d %-8s " % (c["ch"], c["name"] or "")
    s += "pre %s%s%s%s " % (f(pre.get("gain_db")), "P" if pre.get("pad") else "", "+48" if pre.get("phantom_48v") else "",
                           "?" if pre.get("socket_mapping") else "") if pre else "pre -   "
    s += "trim %s%s " % (f(tr.get("trim_db"), 1), " INV" if tr.get("polarity_inverted") else "")
    s += "HPF %s " % ("off" if hp.get("bypass") else "%s/%s" % (f(hp.get("freq_hz")), hp.get("slope_db_oct")))
    if pq and "bands" in pq:
        bands = []
        for b in pq["bands"]:
            if b["band_bypass"] or (b["type"] == "bell" and abs(b["gain_db"] or 0) < 0.05): continue
            bands.append("%s %s%+.1f q%.2f" % (b["type"], f(b["freq_hz"]), b["gain_db"] or 0, b["q"]))
        s += "PEQ%s[%s] " % (" OFF" if pq["bypass"] else "", "; ".join(bands))
    if g:
        s += "GATE %s %s thr%s dep%s " % ("on" if g.get("enable") else "off", g.get("type"), f(g.get("threshold_db"), 1), f(g.get("depth_db")))
    if co:
        s += "COMP %s %s" % ("on" if co.get("enable") else "off", co.get("model"))
        if "threshold_db" in co: s += " thr%s" % f(co["threshold_db"], 1)
        if co.get("ratio"): s += " %s:1" % co["ratio"]
        if "attack_ms" in co: s += " a%sms r%sms" % (f(co["attack_ms"], 2), f(co["release_ms"]))
        if "fixed_attack_ms" in co: s += " (fixed a%s/r%sms)" % (co["fixed_attack_ms"], co["fixed_release_ms"])
        if "makeup_db" in co: s += " mk%s" % f(co["makeup_db"], 1)
        a76 = co.get("amp76")
        if a76: s += " in%s out%s ratio %s(state %d)" % (f(a76["in_gain_db"], 1), f(a76["out_gain_db"], 1), a76["ratio_label_assumed"], a76["ratio_state"])
        ds = co.get("distressor")
        if ds: s += " in%s out%s ratio %s(state %d)" % (f(ds["in_gain_db"], 1), f(ds["out_gain_db"], 1), ds["ratio_label"], ds["ratio_state"])
        mg = co.get("mighty")
        if mg: s += " in%s r%sms det%d" % (f(mg["in_gain_db"], 1), f(mg["release_ms"]), mg["detector"])
    dl = c.get("delay", {})
    if dl and dl.get("samples") and not dl.get("bypass"):
        s += " DLY %.2fms" % dl["ms"]
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["dump", "table"])
    ap.add_argument("show")
    ap.add_argument("--scene", default="65535")
    ap.add_argument("--ch")
    ap.add_argument("--raw", action="store_true")
    a = ap.parse_args()
    res = decode_show(a.show, a.scene, parse_ch(a.ch), a.raw)
    if a.cmd == "dump":
        json.dump(res, sys.stdout, indent=1)
        print()
    else:
        for c in res: print(short(c))

if __name__ == "__main__":
    main()
