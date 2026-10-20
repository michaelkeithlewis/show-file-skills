#!/usr/bin/env python3
"""dlive2digico.py - build a DiGiCo SD/Quantum session from a dLive show.

usage: dlive2digico.py <dlive_show.tar.gz> <baseline.ses> <out.ses> [--channels 1-64] [--scene 65535]

Reads the dLive input processing with dlive_proc.py from ../../dlive/scripts (or the folder the DLIVE_SCRIPTS
environment variable names), then writes names and
processing into a DiGiCo baseline session (made in the DiGiCo editor with the channel count
you want). The baseline is patched in place, so file length never changes. A report of every
translation and approximation is written next to the output as <out>.md.

Translated: name, digital trim, polarity, delay, HPF, LPF, 4-band PEQ, gate/ducker (Dyn2),
compressor (Dyn1), stereo-pair panning. Not translated yet: preamp gain/48V/pad (lives on the
I/O sockets), sends, routing, faders, inserts.

Works on Quantum and SD baselines. SD consoles have no Mustard (module 0x1d) and no Spice Rack, so on them
modelled dLive comps go to the SD compressor and Chilli 6 slots are skipped (said in the report).
put_comp() and put_mustard() take `to_fs` so callers with thresholds already in dBFS (sessionmaker) reuse them.
"""
import argparse
import json
import math
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ses import Session  # noqa: E402

# the dLive readers live in the dlive folder next to this one: <repo>/dlive/scripts
DLIVE_DIR = os.environ.get('DLIVE_SCRIPTS') or os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'dlive', 'scripts'))
DLIVE_PROC = os.path.join(DLIVE_DIR, 'dlive_proc.py')

# DiGiCo keys (module, param, band). EQ UI band n lives at band byte 4 - n.
TRIM, POLARITY = (0x01, 0x01, 0), (0x01, 0x02, 0)
DELAY, DELAY_ON = (0x09, 0x08, 0), (0x09, 0x07, 0)
LPF_IN, LPF_F, HPF_IN, HPF_F = (0x07, 0x03, 0), (0x07, 0x05, 0), (0x07, 0x03, 1), (0x07, 0x05, 1)
EQ_IN = (0x04, 0x02, 0)
EQ_FREQ, EQ_Q, EQ_GAIN, EQ_SHAPE, EQ_ON = 0x05, 0x06, 0x07, 0x04, 0x03
SHAPE = {'bell': 1.0, 'lf_shelf': 3.0, 'hf_shelf': 4.0}
C_MODE, C_IN, C_THR, C_KNEE, C_ATK, C_REL, C_RATIO, C_MK, C_AUTO = (
    0x3a, 0x02, 0x0e, 0x0f, 0x11, 0x12, 0x10, 0x09, 0x3b)
G_MODE, G_IN, G_THR, G_ATK, G_REL, G_HOLD, G_RANGE = 0x0b, 0x02, 0x0e, 0x11, 0x12, 0x13, 0x0a
PAN = (0x0d, 0x23, 0)
KNEE = {'hard': 0.0, 'medium': 1.0, 'soft': 2.0}
AMP76_RATIO = {0: 4.0, 1: 8.0, 2: 12.0, 3: 20.0, 4: 20.0}
DISTRESSOR_RATIO = [1.0, 2.0, 3.0, 4.0, 6.0, 10.0, 20.0, 20.0]
# The strip shows each filter's -3 dB cutoff; the file stores the 24 dB/oct design frequency.
# Measured in the V2242 editor: shown HPF = stored x 1.25, shown LPF = stored x 0.8.
HPF_SHOWN_PER_STORED, LPF_SHOWN_PER_STORED = 1.25, 0.8


def dlive_dump(show, scene):
    out = subprocess.run([sys.executable, DLIVE_PROC, 'dump', show, '--scene', str(scene)],
                         cwd=DLIVE_DIR,
                         capture_output=True, text=True, check=True).stdout
    return {c['ch']: c for c in json.loads(out)}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# dLive levels are relative to its nominal 0 dB, with full scale at +18 dB (dLive thresholds run up to +18).
# DiGiCo levels are dBFS (DiGiCo thresholds stop at 0). Every dLive threshold moves by this offset.
DLIVE_TO_DBFS = -18.0


def fs(db):
    """A dLive threshold as a DiGiCo dBFS threshold."""
    return clamp(db + DLIVE_TO_DBFS, -60.0, 0.0)


class Writer:
    def __init__(self, ses, ch):
        self.s, self.ch, self.notes = ses, ch, []

    def put(self, key, value):
        self.s.set(self.ch, key[0], key[1], key[2], value)

    def note(self, msg):
        self.notes.append(msg)


def do_filters(w, c):
    h = c['hpf']
    if not h['bypass']:
        w.put(HPF_IN, 1.0)
        w.put(HPF_F, hpf_stored(h['freq_hz']))
        if h.get('slope_db_oct') != 24:
            w.note('HPF %s on dLive; DiGiCo HPF is 24 dB/oct' % h.get('type'))
    l = c['lpf']
    if not l['bypass']:
        w.put(LPF_IN, 1.0)
        w.put(LPF_F, lpf_stored(l['freq_hz']))


def hpf_stored(hz):
    return clamp(hz, 20.0, 20000.0) / HPF_SHOWN_PER_STORED


def lpf_stored(hz):
    return clamp(hz, 20.0, 20000.0) / LPF_SHOWN_PER_STORED


def do_eq(w, c):
    peq = c['peq']
    bands = [b for b in peq['bands'] if not b['band_bypass']]
    filt = [b for b in bands if b['type'] in ('hpf', 'lpf')]
    for b in filt:
        if b['type'] == 'hpf' and c['hpf']['bypass']:
            w.put(HPF_IN, 1.0)
            w.put(HPF_F, hpf_stored(b['freq_hz']))
            w.note('PEQ HPF band %.0f Hz moved to the channel HPF' % b['freq_hz'])
        elif b['type'] == 'lpf' and c['lpf']['bypass']:
            w.put(LPF_IN, 1.0)
            w.put(LPF_F, lpf_stored(b['freq_hz']))
            w.note('PEQ LPF band %.0f Hz moved to the channel LPF' % b['freq_hz'])
        else:
            w.note('PEQ %s band %.0f Hz dropped (filter already in use)' % (b['type'], b['freq_hz']))
    # a flat bell/shelf does nothing; leave its DiGiCo band free
    bands = [b for b in bands if b['type'] in SHAPE and abs(b['gain_db']) >= 0.05]
    for b in bands:
        if b['type'] not in SHAPE:
            w.note('PEQ band type %s not translated' % b['type'])
    # UI slots: low shelf can sit in 1-2, high shelf in 3-4; bells fill the rest by frequency
    slots = {}
    lows = sorted((b for b in bands if b['type'] == 'lf_shelf'), key=lambda b: b['freq_hz'])
    highs = sorted((b for b in bands if b['type'] == 'hf_shelf'), key=lambda b: -b['freq_hz'])
    for b, n in zip(lows, (1, 2)):
        slots[n] = b
    for b, n in zip(highs, (4, 3)):
        if n not in slots:
            slots[n] = b
    rest = sorted((b for b in bands if b not in slots.values()), key=lambda b: b['freq_hz'])
    free = [n for n in (1, 2, 3, 4) if n not in slots]
    for b, n in zip(rest, free):
        slots[n] = b
    for b in rest[len(free):]:
        w.note('PEQ band %.0f Hz %+.1f dB dropped (no free band)' % (b['freq_hz'], b['gain_db']))
    if not peq['bypass'] and slots:
        w.put(EQ_IN, 1.0)
    elif peq['bypass'] and slots:
        w.note('PEQ is bypassed on dLive; bands written, EQ left out')
    w.eq_used = set(slots)
    for n, b in slots.items():
        bb = 4 - n
        w.put((0x04, EQ_FREQ, bb), clamp(b['freq_hz'], 20.0, 20000.0))
        w.put((0x04, EQ_GAIN, bb), clamp(b['gain_db'], -18.0, 18.0))
        # DiGiCo shelves have no width control; the editor stores 0.85 for a shelf band
        w.put((0x04, EQ_Q, bb), 0.85 if b['type'] in ('lf_shelf', 'hf_shelf') else clamp(b['q'], 0.1, 20.0))
        w.put((0x04, EQ_SHAPE, bb), SHAPE[b['type']])
        w.put((0x04, EQ_ON, bb), 1.0)
        if abs(b['gain_db']) > 18:
            w.note('PEQ gain %+.1f dB clipped to +/-18' % b['gain_db'])


def do_gate(w, c):
    g = c['gate']
    if not g['enable']:
        return
    mode = {'gate': 0.0, 'ducker': 1.0}.get(g['type'])
    thr = g['threshold_db']
    if mode is None:
        mode = 0.0
        thr = g.get('lower_threshold_db', thr)
        w.note('dLive %s approximated as a gate at the lower threshold' % g['type'])
    b = 3
    w.put((0x05, G_MODE, b), mode)
    w.put((0x05, G_IN, b), 1.0)
    w.put((0x05, G_THR, b), fs(thr))
    w.put((0x05, G_RANGE, b), clamp(abs(g['depth_db']), 0.0, 90.0))
    w.put((0x05, G_ATK, b), clamp(g['attack_ms'], 0.05, 100.0) / 1000.0)
    w.put((0x05, G_HOLD, b), clamp(g['hold_ms'], 2.0, 2000.0) / 1000.0)
    w.put((0x05, G_REL, b), clamp(g['release_ms'], 5.0, 10000.0) / 1000.0)


def put_comp(w, thr, ratio, atk_ms, rel_ms, knee, makeup, to_fs=None):
    """SD compressor (Dyn1, single band). `thr` is a dLive level unless `to_fs` (dB -> stored dBFS) is given."""
    to_fs = to_fs or fs
    w.put((0x05, C_MODE, 0), 0.0)
    w.put((0x05, C_IN, 0), 1.0)
    for band in (0, 1, 2):          # the editor mirrors the comp threshold into all three records
        w.put((0x05, C_THR, band), to_fs(thr))
    w.put((0x05, C_RATIO, 0), clamp(ratio, 1.0, 50.0))
    w.put((0x05, C_ATK, 0), clamp(atk_ms, 0.02, 100.0) / 1000.0)
    w.put((0x05, C_REL, 0), clamp(rel_ms, 1.0, 10000.0) / 1000.0)
    w.put((0x05, C_KNEE, 0), KNEE.get(knee, 0.0))
    w.put((0x05, C_MK, 0), clamp(makeup, 0.0, 40.0))


# Mustard compressor (module 0x1d). Keys from the decoder captures (FORMAT.md, mustard.ses).
MC = 0x1d
MC_MODEL = {'classic': 0.0, 'vca': 3.0, 'fet': 4.0, 'optical': 5.0, 'levamp': 8.0}
MC_ON, MC_TYPE, MC_MIX, MC_THR, MC_KNEE, MC_ATK, MC_REL, MC_RATIO, MC_OUT = (
    0x02, 0x0b, 0x47, 0x0e, 0x0f, 0x11, 0x12, 0x10, 0x09)
MC_FET_IN, MC_FET_RATIO, MC_FET_OUT = 0x41, 0x4a, 0x4d
FET_RATIO = {0: 1.0, 1: 2.0, 2: 3.0, 3: 4.0, 4: 4.0}    # Amp76 state 4/8/12/20/all -> FET 4/8/12/20 button
FET_IN_DEFAULT = -20.0    # DiGiCo FET input default; the Amp76 input is applied as an offset from it


def parallel_mix(k):
    p = k.get('parallel') or {}
    if not p.get('on') or p.get('dry_db') is None:
        return 1.0
    wet, dry = 10 ** (p['wet_db'] / 20.0), 10 ** (p['dry_db'] / 20.0)
    return wet / (wet + dry)


def put_mustard(w, model, thr=None, ratio=None, atk_ms=None, rel_ms=None, knee=None, out=None, mix=1.0, to_fs=None):
    """Mustard compressor (Quantum only). `thr` is a dLive level unless `to_fs` (dB -> stored dBFS) is given."""
    to_fs = to_fs or fs
    w.put((MC, MC_TYPE, 0), MC_MODEL[model])
    w.put((MC, MC_ON, 0), 1.0)
    w.put((MC, MC_MIX, 0), clamp(mix, 0.0, 1.0))
    if thr is not None:
        w.put((MC, MC_THR, 0), to_fs(thr))
    if ratio is not None:
        w.put((MC, MC_RATIO, 0), clamp(ratio, 1.0, 20.0))
    if atk_ms is not None:
        w.put((MC, MC_ATK, 0), clamp(atk_ms, 0.05, 100.0) / 1000.0)
    if rel_ms is not None:
        w.put((MC, MC_REL, 0), clamp(rel_ms, 5.0, 5000.0) / 1000.0)
    if knee is not None:
        w.put((MC, MC_KNEE, 0), 1.0 if knee == 'hard' else 0.0)
    if out is not None:
        w.put((MC, MC_OUT, 0), clamp(out, -24.0, 24.0))


# ---------------------------------------------------------------- FX, sends, Chilli, Dyn8
DLIVE_FX = os.path.join(DLIVE_DIR, 'dlive_fx.py')
FX_KEYS = {'predelay_s': (0x0f, 0), 'lo_hz': (0x14, 1), 'hi_hz': (0x14, 0), 'damp_hz': (0x37, 0), 'decay_s': (0x12, 0)}
AUX_LEVEL, AUX_ON = 0x01, 0x02
CHILLI = 0x1f
EQ_DYN_ON, EQ_DYN_THR, EQ_DYN_RATIO, EQ_DYN_ATK, EQ_DYN_REL, EQ_DYN_UNDER = 0x7d, 0x0e, 0x10, 0x11, 0x12, 0x0b


def dlive_fx_dump(show):
    out = subprocess.run([sys.executable, DLIVE_FX, 'dump', show],
                         cwd=DLIVE_DIR,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def ufx_param(u, name):
    for p in u.get('params', []):
        if (p.get('name') or '').strip() == name:
            return p['value']
    return None


def q_from_octaves(width):
    n = float(str(width).split()[0])
    x = 2 ** n
    return math.sqrt(x) / (x - 1)


def fed_channel(unit):
    m = re.match(r'Ip (\d+) Ins [AB] send', unit.get('fed_by') or '')
    return int(m.group(1)) if m else None


def apply_fx(ses, fxj, cfg, cmap, report):
    by_ufx = {f['ufx']: f for f in cfg.get('fx', [])}
    for f in cfg.get('fx', []):
        u = fxj['ufx_units'][str(f['ufx'])]
        rec = next((r for r in ses.records if r.type == 0x15 and r.name == f['digico_fx']), None)
        if rec is None:
            raise SystemExit('baseline has no FX unit named %r' % f['digico_fx'])
        # A nonzero HF CutGain makes the dLive HF Cut a shelf; the DiGiCo hi filter is a cut, so keep the preset's.
        hf_shelf = ufx_param(u, 'HF CutGain')
        vals = {'predelay_s': (ufx_param(u, 'Predelay') or 0.0) / 1000.0,
                'decay_s': (ufx_param(u, 'Decay Time') or 1000.0) / 1000.0,
                'lo_hz': ufx_param(u, 'LF Cut'), 'hi_hz': None if hf_shelf else ufx_param(u, 'HF Cut'),
                'damp_hz': ufx_param(u, 'HiXOver')}
        lim = {'predelay_s': (0.0, 0.5), 'decay_s': (0.1, 10.0), 'lo_hz': (20.0, 2000.0),
               'hi_hz': (1000.0, 20000.0), 'damp_hz': (1000.0, 20000.0)}
        for k, v in vals.items():
            if v is not None and FX_KEYS[k] in rec.slots:
                struct.pack_into('<f', ses.d, rec.slots[FX_KEYS[k]], clamp(float(v), *lim[k]))
        ret = next((r for r in fxj['returns'].get('ufx', {}).values() if r['unit'] == f['ufx']), None)
        if ret is not None:
            ses.set(ses.ch(f['return_ch']), 0x0c, 0x21, 0, ret['fader_db'])
            ses.rename(ses.ch(f['return_ch']), f['return'])
        hi_txt = 'HF cut %.0f Hz' % (vals['hi_hz'] or 0)
        if hf_shelf:
            hi_txt = 'HF shelf %+.1f dB at %.0f Hz not carried (preset hi filter %.0f Hz kept)' % (
                hf_shelf, ufx_param(u, 'HF Cut'), struct.unpack_from('<f', ses.d, rec.slots[FX_KEYS['hi_hz']])[0])
        report.append('- FX: dLive UFX%d %s %r -> DiGiCo %s on Aux %d, return ch %d %s: decay %.2f s, predelay %.0f ms, '
                      'LF cut %.0f Hz, %s, hi damping %.0f Hz, return fader %+.1f dB' % (
                          f['ufx'], u.get('model'), u.get('preset'), f['digico_fx'], f['aux'], f['return_ch'],
                          f['return'], vals['decay_s'], vals['predelay_s'] * 1000, vals['lo_hz'] or 0,
                          hi_txt, vals['damp_hz'] or 0, ret['fader_db'] if ret else 0))
    n_sends = 0
    for ch, n, st in cmap:
        for snd in fxj['sends'].get(str(ch), []):
            m = re.match(r'UFX (\d+)$', snd['bus'])
            f = by_ufx.get(int(m.group(1))) if m else None
            if not f:
                continue
            # the send band is the aux's internal index (section 201), not its number; on a baseline
            # baselines mono auxes 1-4 sit in bands 0-3
            band = ses.aux_band.get(f['aux'], f['aux'] - 1)
            idx = ses.ch(n)
            ses.set(idx, 0x02, AUX_LEVEL, band, clamp(snd['level_db'], -150.0, 10.0) if snd['on'] else -150.0)
            ses.set(idx, 0x02, AUX_ON, band, 1.0 if snd['on'] else 0.0)
            n_sends += 1
    report.append('- FX sends: %d channel sends copied onto Aux 1-3 (post-fade, levels from dLive).' % n_sends)


def apply_chilli(ses, cfg, show_fx, tpl_fx, cmap, ir, report):
    live = [r for r in ses.records if r.type == CHILLI and r.count == 67]
    if not live and cfg.get('chilli'):
        report.append('- Chilli 6 not written: this console has no Spice Rack (SD series).')
        return
    names = {(ir[ch]['name'] or '').strip()[:8]: n for ch, n, st in cmap}
    for c in cfg.get('chilli', []):
        if c['slot'] > len(live):
            report.append('- Chilli 6 slot %d not written: this console has %d Spice Rack slots.' % (c['slot'], len(live)))
            continue
        if c['channel'] not in names:
            raise SystemExit('chilli slot %d: no channel %r in this show' % (c['slot'], c['channel']))
        src, num = c['dyn8'].split(':')
        u = (tpl_fx if src == 'tpl' else show_fx)['dyn8_units'][num]
        r = live[c['slot'] - 1]
        put = lambda pid, band, v: struct.pack_into('<f', ses.d, r.slots[(pid, band)], float(v))
        for i, b in enumerate(u['mbc']['bands']):
            put(0x03, i, 0.0 if b['in'] else 1.0)
            put(0x0e, i, fs(b['threshold_db']))
            put(0x07, i, clamp(b['gain_db'], -18.0, 18.0))
            put(0x11, i, clamp(b['attack_ms'], 0.1, 100.0) / 1000.0)
            put(0x12, i, clamp(b['release_ms'], 5.0, 5000.0) / 1000.0)
            put(0x0a, i, -6.0 if b['in'] and b['threshold_db'] < 0 else 0.0)
        for i, f in enumerate(u['mbc']['crossovers_hz']):
            put(0x05, i + 1, clamp(f, 20.0, 20000.0))
        cuts = [b for b in u['dyn_eq']['bands'] if b['action'] != 'off' and b.get('ratio', 1) > 1]
        for pb, b in zip((4, 5), cuts):
            put(0x05, pb, clamp(b['freq_hz'], 20.0, 20000.0))
            put(0x06, pb, clamp(q_from_octaves(b['width']), 0.1, 20.0))
            put(0x0e, pb, fs(b['threshold_db']))
            put(0x0a, pb, -12.0 * (1.0 - 1.0 / b['ratio']))
            put(0x03, pb, 0.0)
        report.append('- Chilli 6 slot %d on DiGiCo ch %d %s (insert A) <- dLive Dyn8 %s (%s): MBC thr %s, crossovers %s, '
                      'dynamic cuts %s%s' % (
                          c['slot'], names[c['channel']], c['channel'], c['dyn8'], c['why'],
                          '/'.join('%.1f' % b['threshold_db'] for b in u['mbc']['bands']),
                          '/'.join('%.0f' % f for f in u['mbc']['crossovers_hz']),
                          ', '.join('%.0f Hz' % b['freq_hz'] for b in cuts[:2]) or 'none',
                          ('; Dyn8 trim %+.1f dB not carried' % u['trim_db']) if u.get('trim_db') else ''))


def apply_dyn8_dyneq(ses, show_fx, cmap, ir, vocal_names, eq_used, report):
    """Non-vocal Dyn8 units are dropped. Their dynamic-EQ cuts go onto a free band of the channel's
    own EQ (made dynamic) when one is free."""
    ch_to_n = {ch: n for ch, n, st in cmap}
    for num, u in sorted(show_fx['dyn8_units'].items(), key=lambda kv: int(kv[0])):
        ch = fed_channel(u)
        if ch is None or ch not in ch_to_n:
            continue
        name = (ir[ch]['name'] or '').strip()[:8]
        if name in vocal_names:
            continue
        n = ch_to_n[ch]
        idx = ses.ch(n)
        cuts = [b for b in u['dyn_eq']['bands'] if b['action'] != 'off' and b.get('ratio', 1) > 1]
        free = [b for b in (2, 3, 1, 4) if b not in eq_used.get(n, set())]
        done = []
        for b, ui in zip(cuts, free):
            bb = 4 - ui
            ses.set(idx, 0x04, EQ_FREQ, bb, clamp(b['freq_hz'], 20.0, 20000.0))
            ses.set(idx, 0x04, EQ_Q, bb, clamp(q_from_octaves(b['width']), 0.1, 20.0))
            ses.set(idx, 0x04, EQ_GAIN, bb, 0.0)
            ses.set(idx, 0x04, EQ_SHAPE, bb, 1.0)
            ses.set(idx, 0x04, EQ_ON, bb, 1.0)
            ses.set(idx, 0x04, EQ_DYN_ON, bb, 1.0)
            ses.set(idx, 0x04, EQ_DYN_THR, bb, fs(b['threshold_db']))
            ses.set(idx, 0x04, EQ_DYN_RATIO, bb, clamp(b['ratio'], 1.0, 10.0))
            ses.set(idx, 0x04, EQ_DYN_UNDER, bb, 0.0)
            ses.set(idx, *EQ_IN, 1.0)
            done.append('%.0f Hz' % b['freq_hz'])
        dropped = len(cuts) - len(done)
        report.append('- Dyn8 %s on ch %d %s dropped (not a vocal)%s%s' % (
            num, n, name, ('; dynamic EQ on the channel: ' + ', '.join(done)) if done else '',
            ('; %d dynamic cut(s) had no free EQ band' % dropped) if dropped > 0 else ''))


MODELLED = ('16VU', '16T', 'bus', 'opto', 'levelamp', 'amp76', 'distressor', 'mighty')


def do_comp(w, c, mustard_ok):
    """Manual dLive comps go to the SD compressor. Modelled dLive comps go to the matching Mustard
    model when the channel has a Mustard slot (the SD compressor then stays off); otherwise they are
    approximated on the SD compressor."""
    k = c['comp']
    if not k['enable']:
        return
    m = k['model']
    mix = parallel_mix(k)
    if m in ('manual_peak', 'manual_rms'):
        put_comp(w, k['threshold_db'], k['ratio'], k['attack_ms'], k['release_ms'], k['knee'], k['makeup_db'])
    elif m in MODELLED and mustard_ok:
        if m in ('16VU', '16T', 'bus'):
            put_mustard(w, 'vca', thr=k.get('threshold_db'), ratio=k.get('ratio'), out=k.get('makeup_db'), mix=mix)
            w.note('%s -> Mustard Vintage VCA' % m)
        elif m == 'opto':
            ratio = k.get('ratio')
            put_mustard(w, 'optical', thr=k.get('threshold_db'), ratio=min(ratio, 3.0) if ratio else None,
                        out=k.get('makeup_db'), mix=mix)
            w.note('Opto -> Mustard Optical' + (' (ratio %.1f capped at 3:1)' % ratio if ratio and ratio > 3 else ''))
        elif m == 'levelamp':
            put_mustard(w, 'levamp', out=k.get('makeup_db'), mix=mix)
            w.note('LevelAmp -> Mustard Leveling Amp (settings not carried)')
        elif m == 'amp76':
            a = k['amp76']
            put_mustard(w, 'fet', mix=mix)
            w.put((MC, MC_FET_IN, 0), clamp(FET_IN_DEFAULT + a['in_gain_db'], -40.0, 20.0))
            w.put((MC, MC_FET_RATIO, 0), FET_RATIO.get(a['ratio_state'], 2.0))
            w.put((MC, MC_FET_OUT, 0), clamp(a['out_gain_db'], -24.0, 24.0))
            w.note('Amp76 %s in %+.1f out %+.1f -> Mustard FET (input offset from its -20 default)'
                   % (a.get('ratio_label_assumed'), a['in_gain_db'], a['out_gain_db']))
        elif m == 'distressor':
            a = k['distressor']
            ratio = DISTRESSOR_RATIO[min(a['ratio_state'], 7)]
            put_mustard(w, 'classic', thr=-10.0 - a['in_gain_db'], ratio=ratio, atk_ms=5.0, rel_ms=100.0,
                        knee='soft', out=a['in_gain_db'] + a['out_gain_db'], mix=mix)
            w.note('Distressor state %d in %+.1f out %+.1f -> Mustard Classic %.0f:1 (approx.)'
                   % (a['ratio_state'], a['in_gain_db'], a['out_gain_db'], ratio))
        else:  # mighty
            a = k['mighty']
            put_mustard(w, 'classic', thr=-10.0 - a['in_gain_db'], ratio=4.0, atk_ms=1.0,
                        rel_ms=a.get('release_ms', 100.0), knee='hard', out=0.0, mix=mix)
            w.note('Mighty in %+.1f -> Mustard Classic 4:1 (approx.)' % a['in_gain_db'])
    elif m in ('16VU', '16T', 'bus'):
        put_comp(w, k['threshold_db'], k['ratio'], k.get('fixed_attack_ms', 0.5),
                 k.get('fixed_release_ms', 80.0), 'hard', k['makeup_db'])
        w.note('%s -> SD comp (no Mustard slot left)' % m)
    elif m == 'opto':
        put_comp(w, k['threshold_db'], k['ratio'], 10.0, 300.0, 'soft', k['makeup_db'])
        w.note('Opto -> SD comp, soft knee, 10 ms / 300 ms (no Mustard slot left)')
    elif m == 'amp76':
        a = k['amp76']
        ratio = AMP76_RATIO.get(a['ratio_state'], 8.0)
        thr = a['threshold_db_from_state'] - a['in_gain_db']
        put_comp(w, thr, ratio, 0.5, 100.0, 'hard', max(0.0, a['in_gain_db'] + a['out_gain_db']))
        w.note('Amp76 -> SD comp %.0f:1 thr %.1f (no Mustard slot left, approx.)' % (ratio, thr))
    elif m == 'distressor':
        a = k['distressor']
        ratio = DISTRESSOR_RATIO[min(a['ratio_state'], 7)]
        put_comp(w, -10.0 - a['in_gain_db'], ratio, 5.0, 100.0, 'soft', max(0.0, a['in_gain_db'] + a['out_gain_db']))
        w.note('Distressor -> SD comp %.0f:1 (no Mustard slot left, approx.)' % ratio)
    elif m == 'mighty':
        a = k['mighty']
        put_comp(w, -10.0 - a['in_gain_db'], 4.0, 1.0, a.get('release_ms', 100.0), 'hard', 0.0)
        w.note('Mighty -> SD comp 4:1 (no Mustard slot left, approx.)')
    else:
        su = k.get('stored_unused', {})
        put_comp(w, su.get('threshold_db', -2.0), 3.0, su.get('attack_ms', 10.0),
                 su.get('release_ms', 300.0), su.get('knee', 'hard'), su.get('makeup_db', 0.0))
        w.note('%s comp -> SD comp from stored fields (approx.)' % m)


def translate(c, ses, ch, mustard_ok=False):
    w = Writer(ses, ch)
    t = c['trim']
    w.put(TRIM, clamp(t['trim_db'], -40.0, 40.0))
    w.put(POLARITY, 1.0 if t['polarity_inverted'] else 0.0)
    dl = c['delay']
    if not dl['bypass'] and dl['ms'] > 0:
        w.put(DELAY, clamp(dl['ms'], 0.0, 1300.0) / 1000.0)
        w.put(DELAY_ON, 1.0)
    do_filters(w, c)
    do_eq(w, c)
    do_gate(w, c)
    do_comp(w, c, mustard_ok)
    return w.notes, getattr(w, 'eq_used', set())


MUSTARD_LIMIT = 24          # Quantum 225: the editor turns Mustard off past 24 channels
# Mustard goes to the channels that gain most from a modelled comp first.
MUSTARD_RANK = [('vox', 0), ('kick', 1), ('snr', 1), ('snare', 1), ('bass', 2), ('tom', 3), ('floor', 3),
                ('oh', 4), ('vp88', 4), ('eg', 5), ('kemp', 5), ('ag', 6), ('keys', 7), ('nord', 7),
                ('dx7', 7), ('piano', 7), ('steel', 7), ('hats', 8), ('pad', 8), ('aud', 8)]
NO_MUSTARD = ('tb', 'click', 'trig')


def mustard_rank(name):
    n = name.lower()
    if any(t in n for t in NO_MUSTARD):
        return None
    for key, rank in MUSTARD_RANK:
        if key in n:
            return rank
    return 9


def is_spare(c):
    name = (c.get('name') or '').strip()
    return not name or name.isdigit()


def channel_map(ir, ses, first, last):
    """dLive input -> DiGiCo surface channel. A stereo baseline (some stereo widths) gets one DiGiCo
    stereo channel per dLive pair and skips spare channels; an all-mono baseline maps 1:1."""
    if all(w == 1 for w in ses.width.values()):
        return [(ch, ch, False) for ch in range(first, last + 1) if ch in ir and ch in ses.display]
    out, n = [], 0
    for ch in range(first, last + 1):
        c = ir.get(ch)
        if c is None or is_spare(c):
            continue
        if c.get('stereo_pair') and ch % 2 == 0:
            continue                      # right side of a pair: carried by the stereo channel
        n += 1
        stereo = bool(c.get('stereo_pair'))
        if n not in ses.width:
            raise SystemExit('baseline has no channel %d for dLive %d %s' % (n, ch, c['name']))
        if (ses.width[n] == 2) != stereo:
            raise SystemExit('baseline channel %d is %s but dLive %d %s is %s' % (
                n, 'stereo' if ses.width[n] == 2 else 'mono', ch, c['name'], 'stereo' if stereo else 'mono'))
        out.append((ch, n, stereo))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('show')
    ap.add_argument('baseline')
    ap.add_argument('out')
    ap.add_argument('--channels', default='1-64', help='dLive input range to carry over')
    ap.add_argument('--scene', default='65535')
    ap.add_argument('--mustard-limit', type=int, default=MUSTARD_LIMIT)
    ap.add_argument('--config', help='JSON: Chilli 6 slots and FX units made in the baseline')
    a = ap.parse_args()
    first, last = (int(v) for v in a.channels.split('-'))

    ir = dlive_dump(a.show, a.scene)
    ses = Session(a.baseline)
    has_mustard = ses.has_mustard          # Quantum only; SD channels have no module 0x1d
    if not has_mustard:
        a.mustard_limit = 0
    cmap = channel_map(ir, ses, first, last)
    # pick the Mustard channels: modelled comp, enabled, best rank first, then channel order
    want = [(mustard_rank(ir[ch]['name']), n, ch, 2 if st else 1) for ch, n, st in cmap
            if ir[ch]['comp']['enable'] and ir[ch]['comp']['model'] in MODELLED
            and mustard_rank(ir[ch]['name']) is not None]
    mustard, used = set(), 0
    for _, _, ch, cost in sorted(want):          # a stereo channel uses two Mustard instances
        if used + cost <= a.mustard_limit:
            mustard.add(ch)
            used += cost

    report = ['# %s -> DiGiCo %s' % (os.path.basename(a.show), ses.model), '',
              ('Baseline `%s`: %d input channels (%d stereo). Mustard on %d channels, %d of %d instances; those strips open on the Mustard view.' % (
                  os.path.basename(a.baseline), len(ses.display), sum(1 for w in ses.width.values() if w == 2),
                  len(mustard), used, a.mustard_limit)) if has_mustard else
              ('Baseline `%s`: %d input channels (%d stereo). No Mustard on this console (SD series): modelled comps go to the SD compressor.' % (
                  os.path.basename(a.baseline), len(ses.display), sum(1 for w in ses.width.values() if w == 2))), '',
              'Thresholds: dLive levels sit on its nominal 0 dB scale (full scale +18 dB). Every comp, gate, '
              'Chilli and dynamic EQ threshold is written as DiGiCo dBFS, %.0f dB lower. The dynamics match '
              'when the DiGiCo preamps put nominal level at %.0f dBFS.' % (-DLIVE_TO_DBFS, DLIVE_TO_DBFS), '',
              '| DiGiCo | dLive | name | notes |', '| --- | --- | --- | --- |']
    eq_used = {}
    for ch, n, stereo in cmap:
        c = ir[ch]
        name = (c['name'] or '').strip()[:8] or str(ch)
        idx = ses.ch(n)
        ses.rename(idx, name)
        notes, used = translate(c, ses, idx, mustard_ok=ch in mustard)
        eq_used[n] = used
        if stereo:
            notes.insert(0, 'stereo (dLive %d/%d)' % (ch, ch + 1))
        elif all(w == 1 for w in ses.width.values()) and c.get('stereo_pair'):
            ses.set(idx, *PAN, -1.0 if ch % 2 else 1.0)
            notes.append('dLive stereo pair -> mono channel panned %s' % ('L' if ch % 2 else 'R'))
        report.append('| %d | %d | %s | %s |' % (n, ch, name, '; '.join(notes) if notes else 'direct'))
    # The SD/M strip buttons only switch the view, and the view is saved per surface bank. Open every
    # channel with Mustard on at the Mustard view, so the strip shows the engaged Mustard comp.
    for ch, n, stereo in cmap if has_mustard else []:
        idx = ses.ch(n)
        ses.set_strip_view(idx, ses.VIEW_MUSTARD if ses.get(idx, MC, MC_ON, 0) == 1.0 else ses.VIEW_SD)
    if a.config:
        cfg = json.load(open(a.config))
        show_fx = dlive_fx_dump(a.show)
        tpl_fx = (dlive_fx_dump(os.path.expanduser(cfg['template_show']))
                  if any(c['dyn8'].startswith('tpl:') for c in cfg.get('chilli', [])) else None)
        report += ['', '## FX, Chilli 6 and Dyn8', '']
        apply_fx(ses, show_fx, cfg, cmap, report)
        apply_chilli(ses, cfg, show_fx, tpl_fx, cmap, ir, report)
        apply_dyn8_dyneq(ses, show_fx, cmap, ir, {c['channel'] for c in cfg.get('chilli', [])}, eq_used, report)
        report.append('- Not carried: dLive standard FX (GATE gated reverb, SLAP BBD delay, ADT doubler), '
                      'TAP delays with no sends stored, insert FX (tuners, saturators, '
                      'transient designers, sub harmonic), Dyn8 trims, IEM sends, groups, input patch, preamps.')
    ses.save(a.out)
    with open(os.path.splitext(a.out)[0] + '.md', 'w') as f:
        f.write('\n'.join(report) + '\n')
    print('wrote %s (%d channels, Mustard on %d)' % (a.out, len(cmap), len(mustard)))


if __name__ == '__main__':
    main()
