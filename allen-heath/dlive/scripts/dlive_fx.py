#!/usr/bin/env python3
"""Decode the FX side of a dLive show: UltraFX (UFX/AHFX) units, standard FX rack units, Dyn8 units,
per-channel FX/UFX sends and FX/UFX return routing, in physical units.

Decoded from dLive Director V2.12 (symbols + objdump). Parameter definitions (names, ranges, conversion
codes, per-program parameter lists, Dyn8 point map) are the Director's own static tables, extracted to
fx_tables.json next to this file (see the addresses recorded inside it).

usage:
  dlive_fx.py dump  <show.tar.gz> [--scene 65535] [--all]   JSON (--all also lists unused units)
  dlive_fx.py table <show.tar.gz> [--scene 65535]           short human table

Section layouts (live scene, values big endian):
  AHFX Manager NN (246 B)  6 | 3 | prog u16 | subtype u8 | name[19] | wet u16 | dry u16 | 72 x param u16
                           | width u16 | 72 x MIDI CC u8              (cAHFXNetObject::FillGetStatus @0x100e5ada0)
  FX Manager NN (124 B)    7 | prog u16 | name[19] | wet u16 | dry u16 | 48 x param u16 | width u16
                                                                     (cIFXNetObject::FillGetStatus @0x100279300)
  Dynamics Unit NN (140 B) 2 | type u8 | 60 x param-point u16 | 8 x bands-wide u8 | 8 x self-keyed u8 | sc u8 u8
                                                         (nDynamicsDataNet::PackFullMessage @0x1000d81c0)
Gains on the wire are GainToUWORD: dB = (u ^ 0x8000 as s16) / 256, 0 = -inf. Anything not tied to a
confirmed conversion is reported as {"?raw": ...}.
"""
import argparse, io, json, math, os, re, struct, sys, tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dlive_mix import SceneFile, cm_parse
import dlive_patch as DP

TB = json.load(open(os.path.join(HERE, "fx_tables.json")))

def uword_gain(u):
    """GainToUWORD inverse (@0x100110370 / UWORDToGain @0x1001039a0)."""
    if u == 0:
        return None
    s = u ^ 0x8000
    s = s - 65536 if s >= 32768 else s
    return round(s / 256.0, 3)

def freq(u):
    return round(4.0 * 2.0 ** (u / 4608.0), 1)

def time_ms(u):
    return 0.0 if u == 0 else round(10.0 ** ((u - 1) * 11.0 / 65536) / 1000.0, 3)

def step(u):
    return round((u - 0x8000) / 16.0, 3)

def offset_halved(u):
    """cDynamicsProgramDefines::GetFromOffsetHalved @0x100503330 (0.5 steps of 1/32)."""
    eax = (u ^ 0xFFFF8000) & 0xFFFFFFFF
    ax = eax & 0xFFFF
    neg = ax >= 0x8000
    ecx = (u + 0xF) if neg else eax
    edx = ((u - 0x7FE1) & 0xFFFF) if neg else ax
    sdx = edx - 65536 if edx >= 32768 else edx
    v = float(sdx >> 5)
    if ecx & 0x10:
        v += -0.5 if u <= 0x7FF0 else 0.5
    return v

AHFX_CONV = {
    18: (freq, "Hz"), 20: (freq, "Hz"), 22: (freq, "Hz"),
    15: (time_ms, "ms"), 16: (time_ms, "ms"), 17: (time_ms, "ms"),
    6: (lambda u: round((u - 0x8000) / 16.0, 2), "ms"),
    12: (lambda u: round((u - 0x8000) / 16.0, 1), "%"), 37: (lambda u: round((u - 0x8000) / 16.0, 1), "%"),
    23: (uword_gain, "dB"), 24: (uword_gain, "dB"), 26: (uword_gain, "dB"),
    9: (lambda u: round((u - 0x8000) / 32.0, 3), "dB"), 10: (lambda u: round((u - 0x8000) / 10.0, 2), "dB"),
    7: (lambda u: round((u - 0x8000) / 16.0, 2), "st"), 8: (lambda u: u - 0x8000, "cent"),
    13: (lambda u: round((u - 0x8000) / 16.0, 2), "Hz"),
    1: (lambda u: u, "raw"), 2: (lambda u: u, "ms"), 3: (lambda u: u, "ms"), 28: (lambda u: u, "ms"),
    4: (step, "step"), 5: (step, "step"), 11: (step, "step"), 39: (lambda u: u, "raw"), 40: (step, "step"),
}
IFX_CONV = {
    15: (freq, "Hz"), 19: (freq, "Hz"), 12: (time_ms, "ms"),
    6: (lambda u: round((u - 0x8000) / 16.0, 2), "ms"), 3: (lambda u: u, "ms"),
    4: (step, "step"), 22: (step, "step"), 1: (lambda u: u, "raw"),
}

def decode_params(words, defs, types, conv_tab, subtypes=None):
    out = []
    for i, (ptype, sub, _x, _y) in enumerate(defs):
        if ptype == 0 or i >= len(words):
            continue
        name, mn, mx, cv = types[ptype] if ptype < len(types) else ("type%d" % ptype, 0, 0, -1)
        if name == "Null":
            continue
        if subtypes and sub and sub < len(subtypes) and subtypes[sub] not in ("Null SubParam",):
            name = "%s (%s)" % (name, subtypes[sub])
        u = words[i]
        fn = conv_tab.get(cv)
        if fn is None:
            out.append({"p": i, "name": name, "?raw": "0x%04x" % u, "conv": cv})
        else:
            out.append({"p": i, "name": name, "value": fn[0](u), "unit": fn[1]})
    return out

def live_scene(show, scene="65535"):
    with tarfile.open(show) as t:
        m = next(m for m in t.getmembers() if m.name.endswith("Scenes/StageBoxScene%s.tar.gz" % scene))
        inner = tarfile.open(fileobj=io.BytesIO(t.extractfile(m).read()))
        return next(inner.extractfile(x).read() for x in inner.getmembers() if x.isfile())

def names(S, kind):
    p = S.get(kind + " Name Colour Manager")
    if p is None:
        return []
    n = (len(p) - 1) // 10
    return [p[1 + 9 * k:10 + 9 * k].split(b"\0")[0].decode("latin1") for k in range(n)]

def send(b):
    """[on, pre, level s16be (dB*256), (pan)] (dlive_mix.edit_send)."""
    lvl = struct.unpack(">h", b[2:4])[0]
    d = {"on": bool(b[0]), "pre": bool(b[1]), "level_db": None if lvl <= -32767 else round(lvl / 256.0, 2)}
    if len(b) == 5:
        d["pan"] = b[4]
    return d

def ahfx_unit(p):
    prog = struct.unpack(">H", p[2:4])[0]
    words = struct.unpack(">72H", p[0x1c:0xac])
    pr = TB["ahfx_programs"][prog] if prog < len(TB["ahfx_programs"]) else {"name": "prog%d" % prog, "params": []}
    return {"model": pr["name"], "program": prog, "preset": p[5:0x18].split(b"\0")[0].decode("latin1").strip(),
            "subtype": p[4], "hdr": p[1], "wet_db": uword_gain(struct.unpack(">H", p[0x18:0x1a])[0]),
            "dry_db": uword_gain(struct.unpack(">H", p[0x1a:0x1c])[0]),
            "width": struct.unpack(">H", p[0xac:0xae])[0],
            "params": decode_params(words, pr["params"], TB["ahfx_param_types"], AHFX_CONV, TB["ahfx_subtypes"])}

def ifx_unit(p):
    prog = struct.unpack(">H", p[1:3])[0]
    words = struct.unpack(">48H", p[0x1a:0x7a])
    pr = TB["ifx_programs"][prog] if prog < len(TB["ifx_programs"]) else {"name": "prog%d" % prog, "params": []}
    return {"model": pr["name"], "program": prog, "preset": p[3:0x16].split(b"\0")[0].decode("latin1").strip(),
            "wet_db": uword_gain(struct.unpack(">H", p[0x16:0x18])[0]),
            "dry_db": uword_gain(struct.unpack(">H", p[0x18:0x1a])[0]),
            "width": struct.unpack(">H", p[0x7a:0x7c])[0],
            "params": decode_params(words, pr["params"], TB["ifx_param_types"], IFX_CONV)}

MBC_TYPE = ["Peak", "RMS", "Auto Punch", "Auto Opto", "Slow Auto", "Fast Auto"]
SLOPE = ["6 dB/oct", "18 dB/oct", "24 dB/oct"]

def dyneq_ratio(idx):
    """Cut/Boost index 0..108 -> OCTIVE_DYN_EQ_RATIO_LOOKUP @0x1017b2770; 54 = 1:1 (no action)."""
    if idx == 54:
        return ("off", 1.0)
    s = TB["dyn8_dyneq_slope"][idx]
    if idx < 54:
        return ("cut", round(1.0 / (1.0 + s), 2))
    return ("boost", round(1.0 / (1.0 + TB["dyn8_dyneq_slope"][108 - idx]), 2))

def dyn8_unit(p):
    w = struct.unpack(">60H", p[2:122])
    ix = lambda u: (u - 0x8000) >> 4
    mbc = []
    for b in range(4):
        mbc.append({"band": b + 1, "in": bool(ix(w[5 + b])), "threshold_db": offset_halved(w[1 + b]),
                    "ratio": TB["dyn8_mbc_ratio"][min(ix(w[13 + b]), 52)], "ratio_index": ix(w[13 + b]),
                    "gain_db": round((w[9 + b] - 0x8000) / 10.0, 1),
                    "attack_ms": time_ms(w[23 + b]), "release_ms": time_ms(w[27 + b])})
    dyneq = []
    for b in range(4):
        widx = ix(w[31 + b])
        wtab = TB["dyn8_shelf_width"] if b in (0, 3) else TB["dyn8_width"]
        mode, ratio = dyneq_ratio(w[39 + b])
        dyneq.append({"band": b + 1, "in": bool(ix(w[55 + b])), "freq_hz": freq(w[35 + b]),
                      "width": wtab[min(widx, 32)], "width_index": widx,
                      "action": mode, "ratio": ratio, "cut_boost_index": w[39 + b],
                      "threshold_db": offset_halved(w[43 + b]),
                      "above_below": ix(w[47 + b]), "release_mode": ix(w[51 + b])})
    return {"type_byte": p[1], "trim_db": round((w[0] - 0x8000) / 10.0, 1), "bypass": bool(ix(w[59])),
            "mbc": {"bands": mbc, "crossovers_hz": [freq(w[17]), freq(w[18]), freq(w[19])],
                    "slope": SLOPE[min(ix(w[20]), 2)], "detector": MBC_TYPE[min(ix(w[21]), 5)],
                    "soft_knee": bool(ix(w[22])),
                    "active": any(b["in"] for b in mbc)},
            "dyn_eq": {"bands": dyneq, "active": any(b["in"] and b["action"] != "off" for b in dyneq)},
            "?raw_tail": {"bands_wide": list(p[122:130]), "self_keyed": list(p[130:138]), "sc": list(p[138:140])}}

def decode(show, scene="65535", show_all=False):
    raw = live_scene(show, scene)
    sc = SceneFile(raw)
    S = dict(sc.sections)
    patch = DP.Patch(raw)
    desc = lambda r: DP.describe(*r)
    fx_in = patch.block("FX rack input")
    ufx_in = patch.block("UFX rack input")
    dyn_in = patch.block("Dyn unit input")
    ins_a, ins_b = patch.block("Ip Ins A return"), patch.block("Ip Ins B return")
    other_ret = {n: patch.block(n) for n in ("Grp Ins return", "St Grp Ins return", "Aux Ins return",
                                              "St Aux Ins return", "Main Ins return", "Mtx Ins return",
                                              "St Mtx Ins return")}

    def returned_to(label):
        hits = []
        for i, r in enumerate(ins_a):
            if desc(r) == label: hits.append("Ip %d Ins A" % (i + 1))
        for i, r in enumerate(ins_b):
            if desc(r) == label: hits.append("Ip %d Ins B" % (i + 1))
        for n, blk in other_ret.items():
            for i, r in enumerate(blk):
                if desc(r) == label: hits.append("%s %d" % (n.replace(" return", ""), i + 1))
        return hits

    ufx_send_names = names(S, "Stereo AHFX Send Channel")
    ufx_ret_names = names(S, "AHFX Return Channel")
    sfx_names, mfx_names = names(S, "Stereo FX Send Channel"), names(S, "Mono FX Send Channel")
    fx_ret_names = names(S, "FX Return Channel")
    in_names = names(S, "Input Channel")

    out = {"show": os.path.basename(show), "scene": scene, "input_names": {i + 1: n for i, n in enumerate(in_names[:64])},
           "ufx_units": {}, "fx_units": {}, "dyn8_units": {}, "sends": {}, "returns": {}}
    for k in range(1, 9):
        p = S.get("AHFX Manager %02d" % k)
        if p is None: continue
        feed = [desc(ufx_in[2 * (k - 1)]), desc(ufx_in[2 * (k - 1) + 1])]
        u = ahfx_unit(p)
        u["fed_by"] = feed
        u["returns_to"] = sorted(set(returned_to("UFX Rtn %d" % (2 * k - 1)) + returned_to("UFX Rtn %d" % (2 * k))))
        u["send_bus_name"] = ufx_send_names[k - 1] if k - 1 < len(ufx_send_names) else None
        u["return_name"] = ufx_ret_names[k - 1] if k - 1 < len(ufx_ret_names) else None
        u["used"] = any(f != "-" for f in feed)
        if show_all or u["used"]: out["ufx_units"][k] = u
    for k in range(1, 17):
        p = S.get("FX Manager %02d" % k)
        if p is None: continue
        feed = [desc(fx_in[2 * (k - 1)]), desc(fx_in[2 * (k - 1) + 1])]
        u = ifx_unit(p)
        u["fed_by"] = feed
        u["returns_to"] = sorted(set(returned_to("FX Rtn %d" % (2 * k - 1)) + returned_to("FX Rtn %d" % (2 * k))))
        u["return_name"] = fx_ret_names[k - 1] if k - 1 < len(fx_ret_names) else None
        u["used"] = any(f != "-" for f in feed) and u["model"] != "Empty Rack"
        if show_all or u["used"]: out["fx_units"][k] = u
    for k in range(1, 65):
        p = S.get("Dynamics Unit %02d" % k)
        if p is None: continue
        feed = desc(dyn_in[k - 1])
        used = feed != "-"
        if not (show_all or used): continue
        u = dyn8_unit(p)
        u["fed_by"] = feed
        u["returns_to"] = returned_to("Dyn %d out" % k)
        out["dyn8_units"][k] = u

    h, c, chans = cm_parse(S["Input Mixer"])
    for i, ch in enumerate(chans[:64]):
        lst = []
        for j, b in enumerate(ch["sFX"]):
            s = send(b)
            if s["level_db"] is not None and s["level_db"] > -80:
                lst.append(dict(bus="St FX %d" % (j + 1), name=sfx_names[j] if j < len(sfx_names) else None, **s))
        for j, b in enumerate(ch["mFX"]):
            s = send(b)
            if s["level_db"] is not None and s["level_db"] > -80:
                lst.append(dict(bus="FX %d" % (j + 1), name=mfx_names[j] if j < len(mfx_names) else None, **s))
        rest = ch["rest"]
        if len(rest) >= 47 + 40:
            for u in range(8):
                s = send(rest[47 + 5 * u:52 + 5 * u])
                if s["level_db"] is not None and s["level_db"] > -80:
                    lst.append(dict(bus="UFX %d" % (u + 1), name=ufx_send_names[u] if u < len(ufx_send_names) else None, **s))
        if lst:
            out["sends"][i + 1] = lst
    nm_of = lambda ch: in_names[ch - 1] if ch - 1 < len(in_names) else None
    for k, u in out["ufx_units"].items():
        if u["fed_by"][0].startswith("UFX Send"):
            n = int(u["fed_by"][0].split()[-1])
            u["senders"] = [dict(ch=ch, ch_name=nm_of(ch), **{x: s[x] for x in ("level_db", "on", "pre")})
                            for ch, lst in out["sends"].items() for s in lst if s["bus"] == "UFX %d" % n]
    for k, u in out["fx_units"].items():
        if u["fed_by"][0].startswith("FX Send") and c["mFX"] == 0:
            n = int(u["fed_by"][0].split()[-1])
            u["senders"] = [dict(ch=ch, ch_name=nm_of(ch), **{x: s[x] for x in ("level_db", "on", "pre")})
                            for ch, lst in out["sends"].items() for s in lst if s["bus"] == "St FX %d" % n]
            if n > c["sFX"]:
                u["note"] = "FX Send %d is not a bus in this mixer config (stale patch)" % n
    out["fx_send_bus_note"] = ("patch 'FX Send N' = stereo FX send N when the mixer config has no mono FX "
                               "(this show: mFX=%d sFX=%d)" % (c["mFX"], c["sFX"]))

    for lab, key, nm in (("FX Return Mixer", "fx", fx_ret_names), ("AHFX Return Mixer", "ufx", ufx_ret_names)):
        if lab not in S: continue
        h2, c2, rch = cm_parse(S[lab])
        rows = {}
        for i, ch in enumerate(rch):
            r = ch["rest"]
            main = bool(r[0]); fader = struct.unpack(">h", r[3:5])[0]
            mg = [k + 1 for k, v in enumerate(ch["MG"]) if v]
            sg = [k + 1 for k, v in enumerate(ch["SG"]) if v]
            auxes = []
            for kind in ("mAux", "sAux"):
                for j, b in enumerate(ch[kind]):
                    s = send(b)
                    if s["on"] and s["level_db"] is not None and s["level_db"] > -60:
                        auxes.append(dict(bus=("Aux %d" if kind == "mAux" else "St Aux %d") % (j + 1), **s))
            dca = [k + 1 for k in range(24) if r[15 + k]]
            if mg or sg or auxes or fader > -32767:
                rows[i + 1] = {"unit": i // 2 + 1, "side": "LR"[i % 2],
                               "name": nm[i // 2] if i // 2 < len(nm) else None, "main": main,
                               "fader_db": None if fader <= -32767 else round(fader / 256.0, 2),
                               "mono_groups": mg, "stereo_groups": sg, "dca": dca, "aux_sends": auxes}
        out["returns"][key] = rows
    return out

def table(d):
    L = []
    nm = d.get("input_names", {})
    ip = lambda s: re.sub(r"\bIp (\d+)\b", lambda m: "Ip %s %s" % (m.group(1), nm.get(int(m.group(1)), "")), s)
    for k, u in d["ufx_units"].items():
        dec =next((p for p in u["params"] if p["name"].startswith("Decay Time")), None)
        pre = next((p for p in u["params"] if p["name"].startswith("Predelay")), None)
        dly = next((p for p in u["params"] if p["name"] == "Delay Time"), None)
        extra = ""
        if dec: extra += " decay %.2fs" % (dec["value"] / 1000.0)
        if pre: extra += " predelay %sms" % pre["value"]
        if dly: extra += " delay %sms" % dly["value"]
        L.append("UFX %d %-16s %-20s fed %-28s ret %s%s" % (k, u["model"], u["preset"], "/".join(u["fed_by"]),
                                                             ",".join(u["returns_to"]) or "-", extra))
    for k, u in d["fx_units"].items():
        L.append("FX %2d %-16s %-20s fed %-28s ret %s" % (k, u["model"], u["preset"], "/".join(u["fed_by"]),
                                                            ",".join(u["returns_to"]) or "-"))
    for k, u in d["dyn8_units"].items():
        eq = ["%s %.0fHz %s %s %.1fdB" % ("B%d" % b["band"], b["freq_hz"], b["width"], "%s %.2f:1" % (b["action"], b["ratio"]), b["threshold_db"])
              for b in u["dyn_eq"]["bands"] if b["in"] and b["action"] != "off"]
        mb = ["B%d thr %.1f %.2f:1 g%+.1f" % (b["band"], b["threshold_db"], b["ratio"], b["gain_db"])
              for b in u["mbc"]["bands"] if b["in"]]
        L.append("Dyn %2d on %-14s trim %+.1f DynEQ[%s] MBC[%s xo %s %s]" % (
            k, ip(u["fed_by"]), u["trim_db"], "; ".join(eq), "; ".join(mb),
            "/".join("%.0f" % x for x in u["mbc"]["crossovers_hz"]), u["mbc"]["detector"]))
    for ch, lst in d["sends"].items():
        L.append("Ip %2d %-9s sends: %s" % (ch, nm.get(ch, ""), ", ".join("%s(%s) %s%s%s" % (
            s["bus"], s["name"], "off " if not s["on"] else "", "pre " if s["pre"] else "",
            "-inf" if s["level_db"] is None else "%+.1f" % s["level_db"]) for s in lst)))
    for key, rows in d["returns"].items():
        for i, r in rows.items():
            if r["side"] != "L": continue
            L.append("Rtn %s %d %-9s fader %s main %s grp %s stgrp %s dca %s %s" % (
                key.upper(), r["unit"], r["name"], "-inf" if r["fader_db"] is None else "%+.1f" % r["fader_db"],
                "on" if r["main"] else "off", r["mono_groups"] or "-", r["stereo_groups"] or "-", r["dca"] or "-",
                ", ".join("%s %s%+.1f" % (a["bus"], "pre " if a["pre"] else "", a["level_db"]) for a in r["aux_sends"])))
    return "\n".join(L)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["dump", "table"])
    ap.add_argument("show")
    ap.add_argument("--scene", default="65535")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    d = decode(a.show, a.scene, a.all)
    print(json.dumps(d, indent=1, default=str) if a.cmd == "dump" else table(d))
