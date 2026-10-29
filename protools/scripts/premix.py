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
  premix.py plugcomp --faders G.json --out H.json   solo + bounce each group of stems sharing an insert chain; move
                                                        their faders until the real bus lands on the planned loudness
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
CACHED = set()
def cache(name):
    p = "/tmp/premix_" + hashlib.md5(name.encode()).hexdigest() + ".npy"; CACHED.add(p); return p
def _drop_cache():   # each command re-renders its stems; ~90 MB a stem, 25 GB after one album (2026-10-29)
    for p in CACHED:
        try: os.remove(p)
        except OSError: pass
import atexit; atexit.register(_drop_cache)
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
def silent(t):
    a = t.track_attributes
    return pt.TrackAttributeState.Name(a.is_inactive).endswith(("Explicitly", "Implicitly")) or bool(a.is_muted)
TOPO = [{}]   # routing folders: {name: {bus, out, parent, fader}}, filled by session_map()
def session_map():
    with engine() as e:
        tl = e.track_list()
        st = e.client.run_command(pt.CId_GetSessionPath, {})
        sess = posix(st["session_path"]["path"])
        clips = {c["clip_full_name"]: c for c in paged(e, pt.CId_GetClipList, {}, "clip_list")}
        files = {f["file_id"]: posix(f["path"]) for f in paged(e, pt.CId_GetFileLocation, {"file_filters": ["FLTFilter_AllFiles"]}, "file_locations")}
        rows = edl_samples(e)
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
        if silent(t): continue   # producer tracks parked inactive or muted (a muted synth bass) do not sound: keep them out of the model
        segs = []
        for r in rows[t.name]:
            c = clips.get(r[2])
            if c is None or r[-1].strip().lower() == "muted": continue
            sfx = c["clip_full_name"][len(c["clip_root_name"]):]
            segs.append((files[c["file_id"]], 1 if sfx.endswith(".R") else 0, int(c["src_start_point"]["position"]),
                         int(c["src_end_point"]["position"]), int(r[0]) - 1, int(r[3])))
        chain, b, seen = [], out.get(t.name), set()
        while b and b not in seen and b not in ("no output", "?"):
            seen.add(b); chain.append(b)
            f = inp.get(b)
            b = out.get(f) if f else None
        tracks[t.name] = {"folder": t.parent_folder_name, "format": int(t.format), "pan": pans.get(t.name, 0),
                          "segs": segs, "chain": chain}
    return sess, tracks

def edl_samples(e):
    """Track EDLs with clip start/end in samples from session start (each clip sits where it plays, so producer
    comps and section pieces sum in time). Rows: [channel, event, clip, start, end, duration, state]."""
    t = e.client.run_command(pt.CId_ExportSessionInfoAsText, {"include_track_edls": True, "include_file_list": False,
                             "track_offset_options": "TOOptions_Samples", "output_type": "ESI_String"}).get("session_info", "")
    st = re.search(r"SESSION START:\s*(\d+)", t); st = int(st.group(1)) if st else 0
    out = {}
    for b in re.split(r"\nTRACK NAME:\t", t)[1:]:
        rows = []
        for l in b.split("\n"):
            if not re.match(r"^\d+\s*\t\s*\d+\s*\t", l): continue
            x = [v.strip() for v in l.split("\t")]
            if len(x) < 7 or not x[3].isdigit() or x[6] not in ("Muted", "Unmuted"): continue   # marker list rows (Ticks)
            x = x[:7]; x[3] = str(int(x[3]) - st); rows.append(x)
        out[re.sub(r" \((Stereo|Mono)\)$", "", b.split("\n")[0].strip())] = sorted(rows)
    return out

def render(tr, n):
    """Pre-fader, post-clip-gain, post-pan stereo output of one track (clip gain applied by the caller)."""
    y = np.zeros((n, 2), np.float32)
    mono = tr["format"] == 1
    for path, ch, s0, s1, dst, at in tr["segs"]:
        if at >= n: continue
        x, sr = sf.read(path, start=s0, stop=s1, dtype="float32", always_2d=True)
        x = x[:, min(ch, x.shape[1] - 1)][:n - max(at, 0)]
        if at < 0: x = x[-at:]; at = 0
        if mono:
            th = (tr["pan"] / 100 + 1) * math.pi / 4
            y[at:at + len(x), 0] += x * math.cos(th); y[at:at + len(x), 1] += x * math.sin(th)
        else:
            y[at:at + len(x), dst] += x
    return y

def song_len(tracks):
    return max(at + s1 - s0 for t in tracks.values() for _, _, s0, s1, _, at in t["segs"]) + 2 * SR

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
    live = set()
    for t in tracks.values():
        f = t["folder"]
        while f and f not in live: live.add(f); f = folders.get(f, {}).get("parent")
    for f in sorted(folders, key=depth, reverse=True):
        b = folders[f]["bus"]
        if not b: continue                                   # no bus (FX GROUP): its tracks bypass the fader
        if f in hand_set: continue   # the engineer set this folder by hand (a folder driven hot into its own plug-ins):
                                     # never change what feeds it; its fader still absorbs its parent's moves
        kids_t = [x for x, t in tracks.items() if t["chain"] and t["chain"][0] == b]
        kids_f = [c for c, v in folders.items() if v["out"] == b and c != f and c in live]   # skip empty folders (ORCH GRP, BGV with no stems)
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
ROLE_TARGETS = [("KICK", 0.0), ("SNARE", 0.0), ("DRUM", 0.0), ("BASS", -1.0), ("TOM", -3.0), ("GUITAR", -4.0), ("KEYS", -4.0),
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

# Printed effect returns on producer sessions ("v lead apollo fx", "LV verb.dup3", "bgv harm 1 verb", "Vocal Echos").
# Loudness-matching them to the dry stems would put a reverb print as loud as the vocal (producer session, 2026-10-29), so
# they keep the producer's printed wet/dry ratio: fader = dry partner's fader + partner clip gain - own clip gain.
WET = re.compile(r"\b(fx|verb|reverb|delay|dly|echos?|throw|wet)\b", re.I)
WET_WORDS = re.compile(r"\b(apollo|fx|verb|reverb|delay|dly|echos?|throw|wet|print)\b", re.I)
def is_wet(name): return bool(WET.search(re.sub(r"\.(dup\d+|cm)\b", " ", name)))
def wet_partners(x, dry, tracks):
    base = re.sub(r"\s+\.", ".", re.sub(r"\s+", " ", WET_WORDS.sub(" ", x))).strip()
    if base in dry: return [base]
    alias = [d for d in dry if re.sub(r"\.(rx|cm|comp)$", "", d.strip()) == base]   # "v lead apollo fx" -> "v lead.rx"
    if alias: return alias
    f = tracks[x]["folder"]
    while True:
        sib = [d for d in dry if tracks[d]["folder"] == f]
        if sib: return sib
        f = TOPO[0].get(f, {}).get("parent")
        if not f: return list(dry)

def plan(tracks, stats, ref, headroom, n, ref_cap=3.0, cg=None):
    """1. inside each folder, match every stem's loudness to the folder median (nothing sticks out);
    2. set each folder's loudness to its ROLE_TARGETS offset from the kick folder;
    3. let the reference nudge folders by at most +/-ref_cap dB toward its tonal balance (a free fit
       is degenerate: on a test song it put the toms folder at +12 dB, 12 LU over the kick);
    4. one trim so the loudest bus peaks at the headroom.
    Printed effect returns (is_wet) sit out of 1-3 and follow their dry partner (see WET)."""
    cg = cg or {}
    wet = {x for x in tracks if is_wet(x)}
    dry = {x: t for x, t in tracks.items() if x not in wet}
    if not dry: dry, wet = dict(tracks), set()
    part = {x: wet_partners(x, dry, tracks) for x in wet}
    fold = collections.defaultdict(list)
    for name, tr in dry.items(): fold[tr["folder"] or "(none)"].append(name)
    within = {}
    for f, names in fold.items():
        live = [stats[x]["lufs"] for x in names if stats[x]["lufs"] > -100]
        med = float(np.median(live)) if live else 0.0
        for x in names:
            within[x] = float(np.clip(med - stats[x]["lufs"], -12, 12)) if stats[x]["lufs"] > -100 else 0.0
    gl = group_lufs(dry, within, n)
    # Anchor = the kick folder, else the whole kit (producer sessions keep drums in DRUM GROUP), else the lead
    # vocal, else the loudest folder; every folder lands on its role offset from the anchor's ROLE level. (Picking the
    # loudest folder as "kick" put one song's BGVs 3 LU over the lead and another's bass 4 LU over it, 2026-10-29.)
    live_f = [f for f in gl if gl[f] > -100]
    anchor = next((f for k in ("KICK", "DRUM", "LV") for f in live_f if k in f.upper()), max(gl, key=gl.get))
    ref_level = gl[anchor] - role_target(anchor)
    base = {f: (ref_level + role_target(f)) - gl[f] if gl[f] > -100 else 0.0 for f in gl}
    if anchor in base: base[anchor] = 0.0
    def faders_for(gn):
        fd = {x: within[x] + gn[dry[x]["folder"] or "(none)"] for x in dry}
        for x in wet:
            fd[x] = float(np.median([fd[d] + cg.get(d, 0.0) for d in part[x]])) - cg.get(x, 0.0)
        return fd
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
    return fad, {"role": base, "ref_nudge": nudge, "group_lufs_before": gl, "wet_follows": part}, within, trim

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

def bounce_all(sess, tracks, n, ref):
    """Offline-bounce every bus in the chain plus PtMst in one pass; peak + loudness per bus, bands vs ref."""
    buses = sorted({b for t in tracks.values() for b in t["chain"]}) + ["PtMst"]
    with engine() as e:
        e.client.run_command(pt.CId_SetTimelineSelection, {"in_time": "0", "out_time": str(n), "location_type": "TLType_Samples"})
    base = "ZZPREMIX"
    bounce_buses(buses, base)
    bf = os.path.join(os.path.dirname(sess), "Bounced Files")
    res = {}
    for f in sorted(os.listdir(bf)):
        if not f.startswith(base): continue
        y, _ = sf.read(os.path.join(bf, f), dtype="float32", always_2d=True)
        res[f] = {"peak": float(20 * np.log10(np.abs(y).max() + 1e-12)), "lufs": kloud(y)}
        if ref and "PtMst" in f:
            b = bands(y); t = sum(b.values()); mine = {nm: db(v / t) for nm, v in b.items()}
            tgt, rl = ref_shares(ref)
            res["vs_ref"] = {nm: round(mine[nm] - tgt[nm], 1) for _, _, nm in BANDS}; res["ref_lufs"] = rl
        os.remove(os.path.join(bf, f))
    return res

def plugin_chains():
    """{track: (insert names...)} from the session text export (PTSL has no insert read)."""
    with engine() as e:
        t = e.client.run_command(pt.CId_ExportSessionInfoAsText, {"include_track_edls": True, "include_file_list": False,
                                 "output_type": "ESI_String"}).get("session_info", "")
    out = {}
    for b in re.split(r"\nTRACK NAME:\t", t)[1:]:
        name = re.sub(r" \((Stereo|Mono)\)$", "", b.split("\n")[0].strip())
        pl = next((l for l in b.split("\n") if l.startswith("PLUG-INS:")), "PLUG-INS:")
        out[name] = tuple(x.strip() for x in pl[9:].split("\t") if x.strip())
    return out

def wait_idle(limit=1800):
    t0 = time.time()
    while user_idle_secs() < 120:
        if time.time() - t0 > limit: sys.exit("Mac in use for 30 min; rerun plugcomp with --current to finish")
        time.sleep(10)
    guard_start()

def plugcomp(sess, tracks, cg, n, doc, out, cur=None, passes=4):
    """The model is pre-plug-in, so a stem whose own inserts (or a producer aux it feeds) change its level lands
    off its planned loudness. Solo each group of stems that share an insert chain and route, offline-bounce the
    folder bus it lands on (several groups per pass when their buses differ), and move the group's faders until
    the bounce is within 1 LU of the PLANNED loudness (the model at doc's faders). Several passes, secant steps:
    a producer chain need not move 1 dB per fader dB (one vocal chain moved 2 dB per dB). Faders stop at +12.
    On one producer session (2026-10-29) the LV chain (Auto-Tune Realtime Access demo + RVox) came out 13 dB under plan while
    the printed verbs beside it matched, so a folder-fader fix would have pushed the verbs up with the vocal.
    Printed effects (is_wet) are left as their producer chain makes them. Types the faders itself; writes the
    full fader file (doc with corrected stem faders) to out."""
    plan_f = dict(doc["faders"]); fad = dict(cur or plan_f); chains = plugin_chains()
    bus2folder = {v["bus"]: k for k, v in TOPO[0].items() if v["bus"]}
    groups = collections.defaultdict(list)
    for x, t in tracks.items():
        route = tuple(t["chain"])
        target = next((b for b in route if b in bus2folder), route[-1] if route else None)
        if not target or (not chains.get(x) and route and route[0] == target): continue   # no inserts, straight to its folder: model is exact
        if is_wet(x): continue   # a printed effect keeps its producer chain's level change (an echo print through a saturator + delays read -11 dB)
        groups[(chains.get(x, ()), route, target)].append(x)
    tgt = {}
    for g, members in groups.items():
        tgt[g] = kloud(sum(np.load(cache(x)) * np.float32(10 ** (plan_f.get(x, 0.0) / 20)) for x in members))
    hist = collections.defaultdict(list); report = []; open_g = [g for g in groups if tgt[g] > -100]
    for pas in range(1, passes + 1):
        if not open_g: break
        todo, real = list(open_g), {}
        while todo:
            batch, used = [], set()
            for g in todo:
                if g[2] not in used: batch.append(g); used.add(g[2])
            todo = [g for g in todo if g not in batch]
            names = [x for g in batch for x in groups[g]]
            with engine() as e:
                e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": names, "enabled": True})
                e.client.run_command(pt.CId_SetTimelineSelection, {"in_time": "0", "out_time": str(n), "location_type": "TLType_Samples"})
            try:
                bounce_buses(sorted(used), "ZZPC")
            finally:
                with engine() as e: e.client.run_command(pt.CId_SetTrackSoloState, {"track_names": names, "enabled": False})
            bf = os.path.join(os.path.dirname(sess), "Bounced Files"); got = {}
            for f in os.listdir(bf):
                if f.startswith("ZZPC"):   # one source bounces to "ZZPC.wav" with no bus suffix
                    y, _ = sf.read(os.path.join(bf, f), dtype="float32", always_2d=True); os.remove(os.path.join(bf, f))
                    got[f[5:-4] if f.startswith("ZZPC_") else sorted(used)[0]] = kloud(y)
            for g in batch: real[g] = got.get(g[2], -200.0)
        moves = {}
        for g in list(open_g):
            members = groups[g]; r = real[g]; off = fad[members[0]] - plan_f[members[0]]
            line = f"pass {pas} {g[2]:14} {', '.join(members)[:50]:50} plan {tgt[g]:6.1f} real {r:6.1f} LUFS at {off:+5.1f}  [{' / '.join(g[0])[:60]}]"
            if r < -100:
                line += "  SILENT in the bounce: left as planned"; open_g.remove(g)
            else:
                hist[g].append((off, r)); err = tgt[g] - r
                if abs(err) < 1.0:
                    open_g.remove(g); line += "  ok"
                else:
                    slope = 1.0
                    if len(hist[g]) >= 2 and abs(hist[g][-1][0] - hist[g][-2][0]) > 0.4:
                        slope = float(np.clip((hist[g][-1][1] - hist[g][-2][1]) / (hist[g][-1][0] - hist[g][-2][0]), 0.5, 3.0))
                    step = err / slope; capped = False
                    for x in members:
                        v = round(min(max(fad[x] + step, -60.0), 12.0) * 2) / 2
                        capped |= v >= 12.0 and step > 0
                        if v != fad[x]: moves[x] = v; fad[x] = v
                    line += f"  -> {step:+.1f} dB (slope {slope:.2f})" + ("  STOPS AT +12" if capped else "")
                    if capped or not any(x in moves for x in members): open_g.remove(g)
            print(line, flush=True); report.append(line)
        if moves:
            wait_idle()
            for x, v in moves.items():
                if user_touched(): sys.exit("STOPPED: someone used the Mac mid-run; rerun plugcomp with --current")
                got = set_volume(x, v)
                if got is None or abs(float(got) - v) >= 0.05: print(f"CHECK {x} {v:+.1f} -> {got}", flush=True)
            json.dump({**doc, "faders": fad}, open(out, "w"), indent=1)
    comp = {x: round(fad[x] - plan_f[x], 1) for x in fad if abs(fad[x] - plan_f[x]) > 0.05}
    json.dump({**doc, "faders": fad, "plugin_comp": comp, "plugcomp_report": report}, open(out, "w"), indent=1)
    print("stem fader corrections vs plan:", comp, "| not converged:", [", ".join(groups[g]) for g in open_g])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["model", "trim", "plan", "topdown", "apply", "verify", "check", "plugcomp"])
    ap.add_argument("file", nargs="?"); ap.add_argument("--faders"); ap.add_argument("--ref"); ap.add_argument("--out")
    ap.add_argument("--headroom", type=float, default=-6.0); ap.add_argument("--force", action="store_true")
    ap.add_argument("--bpm", type=float, default=120.0); ap.add_argument("--live", action="store_true")
    ap.add_argument("--current", help="plugcomp: fader file of what is typed in Pro Tools now (default: --faders)")
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
        print(json.dumps(bounce_all(sess, tracks, n, a.ref), indent=1)); return
    stats = analyze(tracks, cg, n)
    if a.cmd == "plugcomp":
        plugcomp(sess, tracks, cg, n, json.load(open(a.faders)), a.out, json.load(open(a.current))["faders"] if a.current else None); return
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
                if g > -100 and g - m > -2.0 and not any(k in f.upper() for k in ("KICK", "DRUM", "BASS", "LV")):   # anchors (kick or whole kit) + the lead vocal
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
        fad, gain, within, trim = plan(tracks, stats, a.ref, a.headroom, n, cg=cg)
        json.dump({"faders": fad, "folder_moves": gain, "within": within, "trim": trim}, open(a.out, "w"), indent=1)
        print("role moves:", {k: round(v, 1) for k, v in gain["role"].items()})
        print("reference nudges:", gain["ref_nudge"], "trim", round(trim, 1))
        gl = group_lufs(tracks, fad, n); k = next((f for f in gl if "KICK" in f.upper()), None)
        print("folder loudness vs kick after plan:", {f: round(v - gl[k], 1) for f, v in sorted(gl.items(), key=lambda kv: -kv[1])} if k else gl)
        for x in sorted(fad, key=lambda x: (tracks[x]["folder"], x)):
            print(f"  {tracks[x]['folder']:14} {x:28} {fad[x]:+5.1f}")

if __name__ == "__main__":
    main()
