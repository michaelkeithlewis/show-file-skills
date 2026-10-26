"""premix.py: a first premix on a prepped session (run after clipgain_normalize.py).
  premix.py model  [--faders F.json] [--ref REF.wav]  predicted bus peak/average, per-track loudness, bands vs ref
  premix.py trim   --out F.json [--headroom -6]         ONE fader value for every stem: loudest bus peak = headroom
  premix.py plan   --ref REF.wav --out F.json          balance: loudness-match inside each folder, reference
                                                        band match between folders, then the headroom trim
  premix.py topdown --faders F.json --out G.json       move what a group shares onto its folder fader, parent first
                                                        in effect (bus inputs stay <= -6 dBFS peak, -18 LUFS); --live
                                                        reads the current faders from Pro Tools instead of F.json
  premix.py apply  F.json [--force]                    type the faders (stems + "folder_faders") into the Output windows
  premix.py verify [--faders F.json] [--ref REF.wav]   offline-bounce every bus in one pass; peaks + bands vs ref
  premix.py check  --faders F.json --bpm N             4-bar windows: each folder's loudness vs the whole mix; flags
                                                        any folder (not kick/bass) within 2 LU of the mix = sticking out
The model is the PRE-PLUG-IN linear sum (clip gain from .premix_clipgain.json, fader, Pro Tools' sin/cos pan
law for mono tracks, unity for stereo tracks), summed into each track's folder bus and every bus above it up
to PrMst. Plug-ins change gain, so `verify` bounces the real buses. Loudness = BS.1770 K-weighted, gated
(-70 LUFS absolute, -10 LU relative), so a stem is judged on the parts where it plays.
Never run `apply` while the engineer is working in Pro Tools (it types into his session)."""
import argparse, collections, hashlib, json, math, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from scipy.signal import lfilter
from ptctl import engine
from ptsl import PTSL_pb2 as pt
import ptax
from ptgui import posix, paged, edl, user_idle_secs, user_touched, guard_start, close_floating, strip, text, key

SR = 48000
BANDS = [(20, 60, "sub"), (60, 120, "low"), (120, 250, "low-mid"), (250, 500, "mid"), (500, 1000, "upper-mid"),
         (1000, 2000, "presence"), (2000, 4000, "edge"), (4000, 8000, "air"), (8000, 16000, "top")]
KB1, KA1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
KB2, KA2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]

def db(x): return 10 * math.log10(max(x, 1e-30))
def cache(name): return "/tmp/premix_" + hashlib.md5(name.encode()).hexdigest() + ".npy"
def kloud(y):
    """Gated BS.1770 loudness (LUFS) of an (n, ch) block at 48k."""
    k = lfilter(KB2, KA2, lfilter(KB1, KA1, y, axis=0), axis=0)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    if len(k) < blk: return -200.0
    cs = np.concatenate([np.zeros((1, k.shape[1])), np.cumsum(k.astype(np.float64) ** 2, axis=0)])
    st = np.arange(0, len(k) - blk + 1, hop)
    ms = ((cs[st + blk] - cs[st]) / blk).sum(axis=1)
    lz = -0.691 + 10 * np.log10(ms + 1e-30)
    g = lz > -70
    if not g.any(): return -200.0
    g &= lz > -0.691 + 10 * np.log10(ms[g].mean()) - 10
    return float(-0.691 + 10 * np.log10(ms[g].mean()))
def bands(y):
    m = y.mean(axis=1); n = 8192; hop = 4096
    if len(m) < n: return {b[2]: 0.0 for b in BANDS}
    fr = np.fft.rfftfreq(n, 1 / SR); win = np.hanning(n)
    acc = np.zeros(len(fr))
    for i in range(0, len(m) - n, hop):
        acc += np.abs(np.fft.rfft(m[i:i + n] * win)) ** 2
    return {nm: float(acc[(fr >= lo) & (fr < hi)].sum()) for lo, hi, nm in BANDS}

# ---------- the session as Pro Tools sums it ----------------------------------------------------
TOPO = [{}]   # routing folders: {name: {bus, out, parent, fader}}, filled by session_map()
def session_map():
    with engine() as e:
        tl = e.track_list()
        st = e.client.run_command(pt.CId_GetSessionPath, {})
        sess = posix(st["session_path"]["path"])
        clips = {c["clip_full_name"]: c for c in paged(e, pt.CId_GetClipList, {}, "clip_list")}
        files = {f["file_id"]: posix(f["path"]) for f in paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations")}
        rows = edl(e)
    g = ptax.track_groups(ptax.window("Mix:"))
    def sel(n, title):
        s = g.get(n); b = ptax.find(s, "AXPopUpButton", title) if s is not None else None
        return b
    out, inp, pans = {}, {}, {}
    kind = {t.name: pt.TrackType.Name(t.type) for t in tl}
    for t in tl:
        b = sel(t.name, "Audio Output Path selector")
        if b is not None: out[t.name] = ptax.out_label(b).rsplit(" (", 1)[0]
        if "Folder" in kind[t.name] or "Aux" in kind[t.name]:
            b = sel(t.name, "Audio Input Path selector")
            if b is not None:
                inp[" ".join(str(ptax.attr(b, "AXTitle") or "").split()).replace("Audio Input Path selector ", "").strip('" ')] = t.name
        if "Audio" in kind[t.name] and int(t.format) == 1 and g.get(t.name) is not None:
            ind = [ptax.attr(el, "AXTitle") for el, d, _ in ptax.walk(g[t.name], max_depth=2)
                   if str(ptax.attr(el, "AXTitle") or "").startswith("Audio Pan indicator")]
            v = ind[0].split()[-1] if ind else ">0<"
            pans[t.name] = 0 if v == ">0<" else (-int(v.strip("<")) if v.startswith("<") else int(v.strip(">")))
    folders = {}
    for t in tl:
        if "Folder" not in kind[t.name] or g.get(t.name) is None: continue
        vol = [ptax.attr(el, "AXValue") for el, d, _ in ptax.walk(g[t.name], max_depth=2)
               if ptax.attr(el, "AXTitle") == "Volume" and ptax.attr(el, "AXRole") == "AXSlider"]
        bus = next((k for k, v in inp.items() if v == t.name), None)
        folders[t.name] = {"bus": bus, "out": out.get(t.name), "parent": t.parent_folder_name,
                           "fader": (int(vol[0]) / 10.0) if vol and vol[0] is not None else 0.0}
    TOPO[0] = folders
    tracks = {}
    for t in tl:
        if "Audio" not in kind[t.name] or t.name not in rows or not rows[t.name]: continue
        segs = []
        for r in rows[t.name]:
            c = clips.get(r[2])
            if c is None: continue
            sfx = c["clip_full_name"][len(c["clip_root_name"]):]
            segs.append((files[c["file_id"]], 1 if sfx.endswith(".R") else 0, int(c["src_start_point"]["position"]),
                         int(c["src_end_point"]["position"]), int(r[0]) - 1))
        chain, b, seen = [], out.get(t.name), set()
        while b and b not in seen and b not in ("no output", "?"):
            seen.add(b); chain.append(b)
            f = inp.get(b)
            b = out.get(f) if f else None
        tracks[t.name] = {"folder": t.parent_folder_name, "format": int(t.format), "pan": pans.get(t.name, 0),
                          "segs": segs, "chain": chain}
    return sess, tracks

def render(tr, n):
    """Pre-fader, post-clip-gain, post-pan stereo output of one track (clip gain applied by the caller)."""
    y = np.zeros((n, 2), np.float32)
    mono = tr["format"] == 1
    for path, ch, s0, s1, dst in tr["segs"]:
        x, sr = sf.read(path, start=s0, stop=s1, dtype="float32", always_2d=True)
        x = x[:, min(ch, x.shape[1] - 1)][:n]
        if mono:
            th = (tr["pan"] / 100 + 1) * math.pi / 4
            y[:len(x), 0] += x * math.cos(th); y[:len(x), 1] += x * math.sin(th)
        else:
            y[:len(x), dst] += x
    return y

def song_len(tracks):
    return max(s1 - s0 for t in tracks.values() for _, _, s0, s1, _ in t["segs"]) + 2 * SR

def clipgains(sess):
    p = os.path.join(os.path.dirname(sess), ".premix_clipgain.json")
    return json.load(open(p)) if os.path.exists(p) else {}

def analyze(tracks, cg, n):
    """Per track at clip gain, fader 0: loudness, peak, band energies, rendered output cached on disk."""
    stats = {}
    for name, tr in tracks.items():
        y = render(tr, n) * (10 ** (cg.get(name, 0.0) / 20))
        stats[name] = {"lufs": kloud(y), "peak": float(20 * np.log10(np.abs(y).max() + 1e-12)), "bands": bands(y)}
        np.save(cache(name), y)
    return stats

def bus_sums(tracks, faders, n):
    sums = collections.defaultdict(lambda: np.zeros((n, 2), np.float32))
    for name, tr in tracks.items():
        y = np.load(cache(name)) * np.float32(10 ** (faders.get(name, 0.0) / 20))
        for b in tr["chain"]:
            sums[b] += y
    return {b: {"peak": float(20 * np.log10(np.abs(s).max() + 1e-12)), "lufs": kloud(s)} for b, s in sums.items()}

def bus_sums_ff(tracks, faders, ffaders, n):
    """Like bus_sums, but each routing folder's fader scales its output into the next bus up."""
    bus2folder = {v["bus"]: k for k, v in TOPO[0].items() if v["bus"]}
    sums = collections.defaultdict(lambda: np.zeros((n, 2), np.float32))
    for name, tr in tracks.items():
        y = np.load(cache(name)); g = faders.get(name, 0.0)
        for b in tr["chain"]:
            sums[b] += y * np.float32(10 ** (g / 20))
            f = bus2folder.get(b)
            if f: g += ffaders.get(f, 0.0)
    return {b: {"peak": float(20 * np.log10(np.abs(s).max() + 1e-12)), "lufs": kloud(s)} for b, s in sums.items()}

def topdown(tracks, faders, n, bus_headroom=-6.0, bus_lufs=-18.0, max_up=6.0):
    """Rule: what a whole group shares belongs on the group fader, all the way up to the
    parent group, so track faders sit near unity with good resolution. Folder faders sit AFTER the folder's
    plug-ins, so lifting a folder's children raises that folder's bus input: lift only as far as the bus stays
    at or below bus_headroom peak and bus_lufs average (pre-plug-in; the bus plug-ins get the same -18 the stems
    get). Deepest folders first; the sum of faders on every path is kept, so the mix itself does not move."""
    folders = TOPO[0]
    fad = dict(faders); ff = {f: v["fader"] for f, v in folders.items()}
    bus2folder = {v["bus"]: k for k, v in folders.items() if v["bus"]}
    def depth(f):
        d = 0
        while folders.get(f, {}).get("parent"): f = folders[f]["parent"]; d += 1
        return d
    moves = {}
    hand_set = {f for f, v in folders.items() if abs(v["fader"]) > 0.05}
    for f in sorted(folders, key=depth, reverse=True):
        b = folders[f]["bus"]
        if not b: continue                                   # no bus (FX GROUP): its tracks bypass the fader
        if f in hand_set: continue   # the engineer set this folder by hand (a folder driven hot into its own plug-ins):
                                     # never change what feeds it; its fader still absorbs its parent's moves
        kids_t = [x for x, t in tracks.items() if t["chain"] and t["chain"][0] == b]
        kids_f = [c for c, v in folders.items() if v["out"] == b and c != f]
        levels = [fad[x] for x in kids_t] + [ff[c] for c in kids_f]
        if not levels: continue
        st = bus_sums_ff(tracks, fad, ff, n).get(b, {"peak": -200, "lufs": -200})
        r = min(-float(np.median(levels)), bus_headroom - st["peak"], bus_lufs - st["lufs"])   # raise the children by r ...
        r = max(r, -(max_up - ff[f]))                             # ... the folder fader comes down by r
        r = math.floor(r * 2) / 2
        if r == 0: continue
        for x in kids_t: fad[x] += r
        for c in kids_f: ff[c] += r
        ff[f] -= r; moves[f] = -r
    return fad, ff, moves
def band_shares(stats, faders, members=None):
    tot = {nm: 0.0 for _, _, nm in BANDS}
    for name, s in stats.items():
        if members is not None and name not in members: continue
        g = 10 ** (faders.get(name, 0.0) / 10)
        for nm in tot: tot[nm] += s["bands"][nm] * g
    t = sum(tot.values()) + 1e-30
    return {nm: db(v / t) for nm, v in tot.items()}

def ref_shares(ref):
    y, sr = sf.read(ref, dtype="float32", always_2d=True)
    if sr != SR:
        from scipy.signal import resample_poly
        y = resample_poly(y, SR, sr, axis=0).astype(np.float32)
    b = bands(y); t = sum(b.values())
    return {nm: db(v / t) for nm, v in b.items()}, kloud(y)

# Group loudness targets, LU relative to the kick group, gated over the parts where each group plays.
# First-blend defaults; edit here. Matched against the folder name (first hit wins).
ROLE_TARGETS = [("KICK", 0.0), ("SNARE", 0.0), ("BASS", -1.0), ("TOM", -3.0), ("GUITAR", -4.0), ("KEYS", -4.0),
                ("ORCH", -4.0), ("BGV", -6.0), ("LV", 0.0), ("OH", -9.0), ("PERC", -9.0), ("FX", -9.0)]
def role_target(folder):
    for k, v in ROLE_TARGETS:
        if k in folder.upper(): return v
    return -6.0

def group_lufs(tracks, faders, n):
    sums = collections.defaultdict(lambda: np.zeros((n, 2), np.float32))
    for name, tr in tracks.items():
        sums[tr["folder"] or "(none)"] += np.load(cache(name)) * np.float32(10 ** (faders.get(name, 0.0) / 20))
    return {f: kloud(y) for f, y in sums.items()}

def plan(tracks, stats, ref, headroom, n, ref_cap=3.0):
    """1. inside each folder, match every stem's loudness to the folder median (nothing sticks out);
    2. set each folder's loudness to its ROLE_TARGETS offset from the kick folder;
    3. let the reference nudge folders by at most +/-ref_cap dB toward its tonal balance (a free fit
       is degenerate: on a test song it put the toms folder at +12 dB, 12 LU over the kick);
    4. one trim so the loudest bus peaks at the headroom."""
    fold = collections.defaultdict(list)
    for name, tr in tracks.items(): fold[tr["folder"] or "(none)"].append(name)
    within = {}
    for f, names in fold.items():
        live = [stats[x]["lufs"] for x in names if stats[x]["lufs"] > -100]
        med = float(np.median(live)) if live else 0.0
        for x in names:
            within[x] = float(np.clip(med - stats[x]["lufs"], -12, 12)) if stats[x]["lufs"] > -100 else 0.0
    gl = group_lufs(tracks, within, n)
    anchor = next((f for f in gl if "KICK" in f.upper()), max(gl, key=gl.get))
    base = {f: (gl[anchor] + role_target(f)) - gl[f] if gl[f] > -100 else 0.0 for f in gl}
    if anchor in base: base[anchor] = 0.0
    def faders_for(gn): return {x: within[x] + gn[tracks[x]["folder"] or "(none)"] for x in tracks}
    nudge = {f: 0.0 for f in fold}
    if ref:
        target, _ = ref_shares(ref)
        def score(nd):
            sh = band_shares(stats, faders_for({f: base[f] + nd[f] for f in fold}))
            return sum((sh[nm] - target[nm]) ** 2 for _, _, nm in BANDS) + 0.5 * sum(v * v for v in nd.values())
        grid = np.arange(-ref_cap, ref_cap + 0.25, 0.5)
        for _ in range(6):
            for f in fold:
                nudge[f] = min((score({**nudge, f: float(v)}), float(v)) for v in grid)[1]
    gain = {f: base[f] + nudge[f] for f in fold}
    fad = faders_for(gain)
    b = bus_sums(tracks, fad, n)
    trim = headroom - max(v["peak"] for v in b.values())
    fad = {x: round((v + trim) * 2) / 2 for x, v in fad.items()}
    return fad, {"role": base, "ref_nudge": nudge, "group_lufs_before": gl}, within, trim

# ---------- Pro Tools I/O -----------------------------------------------------------------------
def set_volume(track, value):
    close_floating()
    ptax.press(ptax.find(strip(track), "AXButton", "Output Window button", max_depth=2)); time.sleep(1.0)
    w = next(w for w in ptax.children(ptax.app()) if ptax.attr(w, "AXSubrole") == "AXFloatingWindow")
    field = lambda: next(el for el, d, _ in ptax.walk(w, max_depth=2) if ptax.attr(el, "AXTitle") == "Volume Numerical")
    ptax.press(field()); time.sleep(0.3); text(f"{value:.1f}"); key(36); time.sleep(0.4)
    got = ptax.attr(field(), "AXValue"); close_floating()
    return got

def bounce_buses(buses, base):
    with engine() as e:
        have = set(e.client.run_command(pt.CId_GetExportMixSourceList, {"type": "EMSType_Bus"})["source_list"])
        src = [pt.EM_SourceInfo(source_type=pt.EMSType_Bus, name=b) for b in buses if b in have]
        # FilePerMixSource: SingleFile with several sources writes ONE multichannel file (2 channels per source)
        ai = pt.EM_AudioInfo(compression_type=pt.CT_PCM, export_format=pt.EF_Interleaved, bit_depth=pt.Bit32Float,
                             sample_rate=pt.SR_48000, pad_to_frame_boundary=pt.TB_False, delivery_format=pt.EM_DF_FilePerMixSource)
        loc = pt.EM_LocationInfo(import_after_bounce=pt.TB_False, file_destination=pt.EM_FD_SessionFolder)
        e.export_mix(base_name=base, file_type=pt.EMFType_WAV, sources=src, audio_info=ai, video_info=pt.EM_VideoInfo(),
                     location_info=loc, dolby_atmos_info=pt.EM_DolbyAtmosInfo(), offline_bounce=pt.TB_True)
        return [b for b in buses if b in have]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["model", "trim", "plan", "topdown", "apply", "verify", "check"])
    ap.add_argument("file", nargs="?"); ap.add_argument("--faders"); ap.add_argument("--ref"); ap.add_argument("--out")
    ap.add_argument("--headroom", type=float, default=-6.0); ap.add_argument("--force", action="store_true")
    ap.add_argument("--bpm", type=float, default=120.0); ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    if a.cmd == "apply":
        doc = json.load(open(a.file)); fad = dict(doc["faders"]); fad.update(doc.get("folder_faders", {}))
        if user_idle_secs() < 120 and not a.force:
            sys.exit(f"someone used the Mac {user_idle_secs():.0f} s ago; rerun when Pro Tools is free (or --force)")
        guard_start()
        bad = []
        for x, v in fad.items():
            if user_touched(): sys.exit("STOPPED: someone used the Mac mid-run; rerun apply to finish (it retypes every fader)")
            got = set_volume(x, v)
            ok = got is not None and abs(float(got) - v) < 0.05
            print(f"{'SET' if ok else 'CHECK'} {x} {v:+.1f} -> {got}", flush=True)
            if not ok: bad.append(x)
        print("APPLY DONE", len(fad), "bad:", bad); return
    sess, tracks = session_map()
    cg = clipgains(sess); n = song_len(tracks)
    if a.cmd == "verify":
        buses = sorted({b for t in tracks.values() for b in t["chain"]}) + ["PtMst"]
        with engine() as e:
            e.client.run_command(pt.CId_SetTimelineSelection, {"in_time": "0", "out_time": str(n), "location_type": "TLType_Samples"})
        base = "ZZPREMIX"
        got = bounce_buses(buses, base)
        bf = os.path.join(os.path.dirname(sess), "Bounced Files")
        res = {}
        for f in sorted(os.listdir(bf)):
            if not f.startswith(base): continue
            y, _ = sf.read(os.path.join(bf, f), dtype="float32", always_2d=True)
            res[f] = {"peak": float(20 * np.log10(np.abs(y).max() + 1e-12)), "lufs": kloud(y)}
            if a.ref and "PtMst" in f:
                b = bands(y); t = sum(b.values()); mine = {nm: db(v / t) for nm, v in b.items()}
                tgt, rl = ref_shares(a.ref)
                res["vs_ref"] = {nm: round(mine[nm] - tgt[nm], 1) for _, _, nm in BANDS}; res["ref_lufs"] = rl
            os.remove(os.path.join(bf, f))
        print(json.dumps(res, indent=1)); return
    stats = analyze(tracks, cg, n)
    if a.cmd == "topdown":
        if a.live:
            g = ptax.track_groups(ptax.window("Mix:")); live = {}
            for x in tracks:
                v = [ptax.attr(el, "AXValue") for el, d, _ in ptax.walk(g[x], max_depth=2)
                     if ptax.attr(el, "AXTitle") == "Volume" and ptax.attr(el, "AXRole") == "AXSlider"]
                live[x] = int(v[0]) / 10.0 if v and v[0] is not None else 0.0
            src = {"faders": live}
        else:
            src = json.load(open(a.faders))
        fad, ff, moves = topdown(tracks, src["faders"], n)
        before = bus_sums_ff(tracks, src["faders"], {f: v["fader"] for f, v in TOPO[0].items()}, n)
        after = bus_sums_ff(tracks, fad, ff, n)
        json.dump({**src, "faders": {x: round(v * 2) / 2 for x, v in fad.items()}, "folder_faders": ff, "topdown_moves": moves},
                  open(a.out, "w"), indent=1)
        print("folder faders:", {f: v for f, v in ff.items() if v})
        print("track faders now", min(fad.values()), "to", max(fad.values()), "median", float(np.median(list(fad.values()))))
        for bname in sorted(after):
            print(f"BUS {bname:14} peak {before[bname]['peak']:6.1f} -> {after[bname]['peak']:6.1f}   {before[bname]['lufs']:6.1f} -> {after[bname]['lufs']:6.1f} LUFS")
        return
    if a.cmd == "check":
        fad = json.load(open(a.faders))["faders"]
        sums = collections.defaultdict(lambda: np.zeros((n, 2), np.float32))
        for name, tr in tracks.items():
            sums[tr["folder"] or "(none)"] += np.load(cache(name)) * np.float32(10 ** (fad.get(name, 0.0) / 20))
        mix = sum(sums.values()); win = int(16 * 60 / a.bpm * SR); flags = []
        print("bar    mix  " + " ".join(f"{f[:6]:>6}" for f in sorted(sums)))
        for i, s0 in enumerate(range(0, n - win // 2, win)):
            m = kloud(mix[s0:s0 + win]); row = []
            for f in sorted(sums):
                g = kloud(sums[f][s0:s0 + win]); row.append(f"{g - m:6.1f}" if g > -100 else "     .")
                if g > -100 and g - m > -2.0 and not any(k in f.upper() for k in ("KICK", "BASS", "LV")):   # anchors + the lead vocal
                    flags.append((1 + 4 * i, f, round(g - m, 1)))
            print(f"{1 + 4 * i:3}  {m:6.1f} " + " ".join(row))
        print("STICKING OUT (folder within 2 LU of the mix; fine when it is the only thing playing):", flags)
        return
    if a.cmd == "model":
        fad = json.load(open(a.faders))["faders"] if a.faders else {}
        for x in sorted(stats, key=lambda x: (tracks[x]["folder"], x)):
            print(f"{tracks[x]['folder']:14} {x:28} {stats[x]['lufs']:6.1f} LUFS  peak {stats[x]['peak']:6.1f}  fader {fad.get(x, 0):+5.1f}")
        for b, v in sorted(bus_sums(tracks, fad, n).items()):
            print(f"BUS {b:14} peak {v['peak']:6.1f}  {v['lufs']:6.1f} LUFS")
        if a.ref:
            tgt, rl = ref_shares(a.ref); sh = band_shares(stats, fad)
            print("bands vs ref:", {nm: round(sh[nm] - tgt[nm], 1) for _, _, nm in BANDS})
        return
    if a.cmd == "trim":
        b = bus_sums(tracks, {}, n)
        loud = max(b, key=lambda k: b[k]["peak"])
        t = round((a.headroom - b[loud]["peak"]) * 2) / 2
        json.dump({"faders": {x: t for x in tracks}, "trim": t, "loudest_bus": loud}, open(a.out, "w"), indent=1)
        print(f"loudest bus {loud} peaks {b[loud]['peak']:.1f} dBFS at unity -> every stem fader {t:+.1f} dB"); return
    if a.cmd == "plan":
        fad, gain, within, trim = plan(tracks, stats, a.ref, a.headroom, n)
        json.dump({"faders": fad, "folder_moves": gain, "within": within, "trim": trim}, open(a.out, "w"), indent=1)
        print("role moves:", {k: round(v, 1) for k, v in gain["role"].items()})
        print("reference nudges:", gain["ref_nudge"], "trim", round(trim, 1))
        gl = group_lufs(tracks, fad, n); k = next((f for f in gl if "KICK" in f.upper()), None)
        print("folder loudness vs kick after plan:", {f: round(v - gl[k], 1) for f, v in sorted(gl.items(), key=lambda kv: -kv[1])} if k else gl)
        for x in sorted(fad, key=lambda x: (tracks[x]["folder"], x)):
            print(f"  {tracks[x]['folder']:14} {x:28} {fad[x]:+5.1f}")

if __name__ == "__main__":
    main()
