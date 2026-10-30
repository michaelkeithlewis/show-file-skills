#!/usr/bin/env python3
"""process.py - write per-instrument starting processing into a session, and read processing back.

The values come from data/templates.json: one template per instrument category, the show-weighted medians of
39 real DiGiCo sessions, in display units (Hz as shown on the strip, dBFS, ms). meta.write_keys there
names the (module, param, band) slot for each value and the display -> stored conversion; this module reads those
keys and checks them against the constants in sesproc.py, whose SD comp and Mustard writers it
reuses (with thresholds passed through as dBFS, not dLive levels).

What gets written per channel (only where the template has the processor in):
  HPF / LPF        module 07: in (03, 1/0), frequency (05, 1/0). Stored = shown / 1.25 (HPF), shown / 0.8 (LPF).
  EQ               module 04: EQ in (02, 0); UI band n at band byte 4 - n: on 03, shape 04 (1 bell, 3 low shelf,
                   4 high shelf), freq 05, Q 06, gain 07. Shelves only on bands 1-2 (low) and 3-4 (high).
  Gate             Dyn2 = module 05 band 3: mode 0b (0 gate), in 02, threshold 0e, range 0a, attack 11, hold 13,
                   release 12 (times stored in seconds).
  SD compressor    Dyn1 = module 05 band 0, single band (mode 0). Templates whose Dyn1 is mostly multiband or a
                   de-esser in the real sessions still get the single-band medians (multiband gain keys are not
                   verified). Dyn2 as a second comp when the template has dyn2_comp in.
  Mustard comp     module 1d, Quantum only, up to the console's instance cap (a stereo channel uses 2), best
                   candidates first. On a Mustard channel the SD compressor stays off (the Mustard comp replaces
                   it). Past the cap the Mustard settings go to the SD compressor instead.
                   Mustard channels open on the M view of their bank (Session.set_strip_view).
  Delay, polarity  module 09 (07 on, 08 seconds); module 01 (02): 1 inverts a mono channel; a stereo channel
                   takes a side mask (the iPad map gives phase 0-3), so both sides = 3.
Thresholds are dBFS as set on the source sessions' gain structure: starting points, not a mix.
Not written: preamp gain and 48V (they live on the I/O sockets), input patch, sends, groups, FX.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ROOT
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import sesproc

TEMPLATES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'templates.json')
_T = None


def templates():
    global _T
    if _T is None:
        with open(TEMPLATES_PATH) as f:
            _T = json.load(f)
        _check_keys(_T['meta']['write_keys'])
    return _T


def _k(v):
    return tuple(v[:3])


def _check_keys(wk):
    """The JSON's write keys and the sesproc constants must name the same slots."""
    pairs = [(_k(wk['hpf_in']), sesproc.HPF_IN), (_k(wk['hpf_freq']), sesproc.HPF_F), (_k(wk['lpf_in']), sesproc.LPF_IN),
             (_k(wk['lpf_freq']), sesproc.LPF_F), (_k(wk['eq_in']), sesproc.EQ_IN), (_k(wk['polarity']), sesproc.POLARITY),
             (_k(wk['delay']['on']), sesproc.DELAY_ON), (_k(wk['delay']['time']), sesproc.DELAY),
             (tuple(wk['comp']['in'][:3]), (0x05, sesproc.C_IN, 0)), (tuple(wk['comp']['mode'][:3]), (0x05, sesproc.C_MODE, 0)),
             (tuple(wk['dyn2']['mode'][:3]), (0x05, sesproc.G_MODE, 3)), (tuple(wk['dyn2']['hold'][:3]), (0x05, sesproc.G_HOLD, 3)),
             (tuple(wk['mustard_comp']['on'][:3]), (sesproc.MC, sesproc.MC_ON, 0)),
             (tuple(wk['mustard_comp']['model'][:3]), (sesproc.MC, sesproc.MC_TYPE, 0)),
             ((wk['eq_band_n']['freq'][0], wk['eq_band_n']['freq'][1]), (0x04, sesproc.EQ_FREQ))]
    bad = [p for p in pairs if p[0] != p[1]]
    if bad:
        raise RuntimeError('templates.json write_keys disagree with sesproc constants: %r' % bad)


WK = None


def keys():
    """write_keys as (module, param, band) tuples, display -> stored factors included."""
    global WK
    if WK is None:
        wk = templates()['meta']['write_keys']
        WK = {
            'hpf_in': _k(wk['hpf_in']), 'hpf_f': _k(wk['hpf_freq']), 'lpf_in': _k(wk['lpf_in']),
            'lpf_f': _k(wk['lpf_freq']), 'eq_in': _k(wk['eq_in']), 'polarity': _k(wk['polarity']),
            'delay_on': _k(wk['delay']['on']), 'delay': _k(wk['delay']['time']),
            'eq': {f: tuple(wk['eq_band_n'][f][:2]) for f in ('on', 'shape', 'freq', 'q', 'gain')},
            'dyn2': {f: _k(wk['dyn2'][k]) for f, k in (('mode', 'mode'), ('in', 'in'), ('thr', 'threshold'),
                                                     ('atk', 'attack'), ('rel', 'release'), ('hold', 'hold'),
                                                     ('range', 'range'), ('ratio', 'ratio_when_comp'))},
        }
    return WK


HPF_PER, LPF_PER = sesproc.HPF_SHOWN_PER_STORED, sesproc.LPF_SHOWN_PER_STORED
SHAPES = {'bell': 1.0, 'low_shelf': 3.0, 'high_shelf': 4.0}
SHAPE_NAMES = {1: 'bell', 2: 'shape2', 3: 'low_shelf', 4: 'high_shelf'}
SHELF_BANDS = {'low_shelf': (1, 2), 'high_shelf': (3, 4)}
KNEE_NAMES = {0: 'hard', 1: 'medium', 2: 'soft'}
COMP_MODES = {0: 'comp', 1: 'multiband', 2: 'deesser'}
DYN2_MODES = {0: 'gate', 1: 'ducker', 2: 'comp'}
MUSTARD_MODELS = {v: k for k, v in sesproc.MC_MODEL.items()}
MUSTARD_PRIORITY = {'lead_vocal': 0, 'vocal_generic': 1, 'snare_top': 2, 'kick_in': 3, 'bass_di': 3,
                    'acoustic_guitar': 4, 'folk_strings': 5, 'strings': 5, 'drum_crotch': 6}


def dbfs(db):
    """Template thresholds are already dBFS; DiGiCo thresholds stop at 0."""
    return sesproc.clamp(float(db), -60.0, 0.0)


def resolve(category, role='foh'):
    """-> (template dict, category it came from) or (None, None) for 'other' / unknown categories.
    role 'mon' uses the monitor-pool template when the category has a non-thin one."""
    cats = templates()['categories']
    if category not in cats:
        return None, None
    src = cats[category].get('use_template_of') or category
    e = cats.get(src) or cats[category]
    mon = e.get('monitor')
    if role == 'mon' and mon and (mon.get('samples') or {}).get('channels', 0) >= 5:
        return mon['template'], src + ' (monitor)'
    return e['template'], src


def category_label(category):
    e = templates()['categories'].get(category)
    return e['label'] if e else 'Other'


class Writer(sesproc.Writer):
    """sesproc.Writer that remembers every value written, so the build can check the file reads back the same."""

    def __init__(self, ses, ch):
        super().__init__(ses, ch)
        self.written = {}

    def put(self, key, value):
        super().put(key, value)
        self.written[tuple(key)] = float(value)


def _num(x, default):
    return default if x is None else float(x)


def write_template(ses, ch, tpl, stereo, mustard):
    """Write template `tpl` on internal channel `ch`. mustard: 'on' (allocated), 'over' (wanted, no instance left)
    or None. Returns the Writer (notes + written values)."""
    K = keys()
    w = Writer(ses, ch)
    h = tpl.get('hpf') or {}
    if h.get('in') and h.get('freq_hz'):
        w.put(K['hpf_in'], 1.0)
        w.put(K['hpf_f'], sesproc.clamp(float(h['freq_hz']), 20.0, 20000.0) / HPF_PER)
    lo = tpl.get('lpf') or {}
    if lo.get('in') and lo.get('freq_hz'):
        w.put(K['lpf_in'], 1.0)
        w.put(K['lpf_f'], sesproc.clamp(float(lo['freq_hz']), 20.0, 20000.0) / LPF_PER)

    eq = tpl.get('eq') or {}
    if eq.get('in') and eq.get('bands'):
        w.put(K['eq_in'], 1.0)
        for b in eq['bands']:
            n, shape = int(b['band']), b.get('shape', 'bell')
            if shape in SHELF_BANDS and n not in SHELF_BANDS[shape]:
                w.note('EQ band %d %s written as a bell (shelves sit on bands %s)' % (
                    n, shape.replace('_', ' '), '/'.join(map(str, SHELF_BANDS[shape]))))
                shape = 'bell'
            m, bb = K['eq'], 4 - n
            w.put((m['freq'][0], m['freq'][1], bb), sesproc.clamp(float(b['freq_hz']), 20.0, 20000.0))
            w.put((m['gain'][0], m['gain'][1], bb), sesproc.clamp(float(b['gain_db']), -18.0, 18.0))
            q = 0.85 if shape in SHELF_BANDS else sesproc.clamp(_num(b.get('q'), 0.71), 0.1, 20.0)
            w.put((m['q'][0], m['q'][1], bb), q)
            w.put((m['shape'][0], m['shape'][1], bb), SHAPES.get(shape, 1.0))
            w.put((m['on'][0], m['on'][1], bb), 1.0)

    g, D = tpl.get('gate') or {}, K['dyn2']
    gate_on = bool(g.get('in') and g.get('threshold_db') is not None)
    if gate_on:
        w.put(D['mode'], 0.0)
        w.put(D['in'], 1.0)
        w.put(D['thr'], dbfs(g['threshold_db']))
        w.put(D['range'], sesproc.clamp(_num(g.get('range_db'), 40.0), 0.0, 90.0))
        w.put(D['atk'], sesproc.clamp(_num(g.get('attack_ms'), 0.05), 0.05, 100.0) / 1000.0)
        w.put(D['hold'], sesproc.clamp(_num(g.get('hold_ms'), 100.0), 2.0, 2000.0) / 1000.0)
        w.put(D['rel'], sesproc.clamp(_num(g.get('release_ms'), 200.0), 5.0, 10000.0) / 1000.0)
    d2 = tpl.get('dyn2_comp') or {}
    if d2.get('in') and not gate_on and d2.get('threshold_db') is not None:
        w.put(D['mode'], 2.0)
        w.put(D['in'], 1.0)
        w.put(D['thr'], dbfs(d2['threshold_db']))
        w.put(D['ratio'], sesproc.clamp(_num(d2.get('ratio'), 3.0), 1.0, 50.0))
        w.put(D['atk'], sesproc.clamp(_num(d2.get('attack_ms'), 10.0), 0.05, 100.0) / 1000.0)
        w.put(D['rel'], sesproc.clamp(_num(d2.get('release_ms'), 300.0), 5.0, 10000.0) / 1000.0)

    c, mc = tpl.get('comp') or {}, tpl.get('mustard_comp') or {}
    if mustard == 'on':
        model = mc.get('model') or 'classic'
        kw = dict(thr=mc.get('threshold_db'), out=mc.get('output_db'), mix=_num(mc.get('mix'), 1.0), to_fs=dbfs)
        if model == 'classic':
            kw.update(ratio=mc.get('ratio'), atk_ms=mc.get('attack_ms'), rel_ms=mc.get('release_ms'),
                      knee=mc.get('knee'))
        elif model == 'optical':
            kw.update(ratio=min(_num(mc.get('ratio'), 3.0), 3.0))
        elif model == 'vca':
            kw.update(ratio=mc.get('ratio'))
        elif model == 'levamp':
            kw.pop('thr')
        sesproc.put_mustard(w, model if model in sesproc.MC_MODEL else 'classic', **kw)
        if c.get('in'):
            w.note('Mustard comp replaces the SD comp')
    elif c.get('in') and c.get('threshold_db') is not None:
        sesproc.put_comp(w, c['threshold_db'], _num(c.get('ratio'), 3.0), _num(c.get('attack_ms'), 10.0),
                     _num(c.get('release_ms'), 300.0), c.get('knee') or 'hard', max(0.0, _num(c.get('makeup_db'), 0.0)),
                     to_fs=dbfs)
        if c.get('mode') in ('multiband', 'deesser'):
            w.note('SD comp written single band')
        if mustard == 'over':
            w.note('no Mustard instance left: SD comp from the template')
    elif mustard == 'over' and mc.get('threshold_db') is not None:
        sesproc.put_comp(w, mc['threshold_db'], min(_num(mc.get('ratio'), 3.0), 50.0), _num(mc.get('attack_ms'), 10.0),
                     _num(mc.get('release_ms'), 250.0), 'medium', max(0.0, _num(mc.get('output_db'), 0.0)), to_fs=dbfs)
        w.note('no Mustard instance left: Mustard settings on the SD comp')

    dl = tpl.get('delay') or {}
    if dl.get('on') and dl.get('ms'):
        w.put(K['delay'], sesproc.clamp(float(dl['ms']), 0.0, 1300.0) / 1000.0)
        w.put(K['delay_on'], 1.0)
    if tpl.get('polarity_invert'):
        w.put(K['polarity'], 3.0 if stereo else 1.0)
    return w


def mustard_plan(chans, cap):
    """chans: [(surface n, category, stereo, template)]. -> ({n: 'on' | 'over'}, instances used).
    Channels whose template turns the Mustard comp on, best priority first, a stereo channel costing 2."""
    want = [(MUSTARD_PRIORITY.get(cat, 9), n, 2 if st else 1) for n, cat, st, tpl in chans
            if tpl and (tpl.get('mustard_comp') or {}).get('on')]
    out, used = {}, 0
    for _, n, cost in sorted(want):
        if cap is not None and used + cost <= cap:
            out[n] = 'on'
            used += cost
        else:
            out[n] = 'over'
    return out, used


def apply(ses, plan, console, processing='templates', role='foh'):
    """Write processing for every planned channel. plan: [{'n', 'idx', 'category', 'stereo'}] in surface order.
    Returns {n: {'notes': [...], 'written': {key: value}, 'source': category used, 'mustard': 'on'|'over'|None}}
    and the Mustard instance count."""
    has_mustard = bool(console.get('mustard')) and ses.has_mustard
    rows, chans = {}, []
    for p in plan:
        tpl, src = resolve(p['category'], role) if processing == 'templates' else (None, None)
        chans.append((p['n'], p['category'], p['stereo'], tpl))
        rows[p['n']] = {'notes': [], 'written': {}, 'source': src, 'mustard': None}
    mplan, used = mustard_plan(chans, console.get('mustard_cap') if has_mustard else 0)
    if not has_mustard:
        mplan = {n: None for n in mplan}
    for (n, cat, st, tpl), p in zip(chans, plan):
        if tpl is None:
            continue
        w = write_template(ses, p['idx'], tpl, st, mplan.get(n))
        rows[n].update(notes=w.notes, written=w.written, mustard=mplan.get(n))
    if has_mustard:
        for p in plan:
            ses.set_strip_view(p['idx'], ses.VIEW_MUSTARD if rows[p['n']]['mustard'] == 'on' else ses.VIEW_SD)
    return rows, used


def _r(x, nd=1):
    return round(float(x), nd)


def readback_channel(ses, idx):
    """Processing on internal channel idx, decoded from the file into display units."""
    K, g = keys(), lambda key: ses.get(idx, *key)
    out = {'hpf': None, 'lpf': None, 'eq': [], 'gate': None, 'comp': None, 'mustard': None,
           'polarity': g(K['polarity']) != 0.0, 'delay_ms': None}
    if g(K['hpf_in']) == 1.0:
        out['hpf'] = _r(g(K['hpf_f']) * HPF_PER)
    if g(K['lpf_in']) == 1.0:
        out['lpf'] = _r(g(K['lpf_f']) * LPF_PER)
    if g(K['eq_in']) == 1.0:
        m = K['eq']
        for n in (1, 2, 3, 4):
            bb = 4 - n
            on = ses.get(idx, m['on'][0], m['on'][1], bb) == 1.0
            gain = ses.get(idx, m['gain'][0], m['gain'][1], bb)
            if on and abs(gain) >= 0.05:
                out['eq'].append({'band': n, 'type': SHAPE_NAMES.get(int(ses.get(idx, m['shape'][0], m['shape'][1], bb)), '?'),
                                  'freq': _r(ses.get(idx, m['freq'][0], m['freq'][1], bb)), 'gain': _r(gain),
                                  'q': _r(ses.get(idx, m['q'][0], m['q'][1], bb), 2), 'on': True})
    D = K['dyn2']
    if g(D['in']) == 1.0:
        mode = DYN2_MODES.get(int(g(D['mode'])), str(g(D['mode'])))
        gate = {'mode': mode, 'threshold': _r(g(D['thr'])), 'attack_ms': _r(g(D['atk']) * 1000, 2),
                'release_ms': _r(g(D['rel']) * 1000)}
        if mode == 'comp':
            gate['ratio'] = _r(g(D['ratio']), 2)
        else:
            gate.update(range=_r(g(D['range'])), hold_ms=_r(g(D['hold']) * 1000))
        out['gate'] = gate
    if ses.get(idx, 0x05, sesproc.C_IN, 0) == 1.0:
        c = lambda p: ses.get(idx, 0x05, p, 0)
        out['comp'] = {'mode': COMP_MODES.get(int(c(sesproc.C_MODE)), '?'), 'threshold': _r(c(sesproc.C_THR)),
                       'ratio': _r(c(sesproc.C_RATIO), 2), 'attack_ms': _r(c(sesproc.C_ATK) * 1000, 2),
                       'release_ms': _r(c(sesproc.C_REL) * 1000), 'knee': KNEE_NAMES.get(int(c(sesproc.C_KNEE)), '?'),
                       'makeup': _r(c(sesproc.C_MK))}
    if ses.has_module(sesproc.MC, idx) and ses.get(idx, sesproc.MC, sesproc.MC_ON, 0) == 1.0:
        mc = lambda p: ses.get(idx, sesproc.MC, p, 0)
        out['mustard'] = {'model': MUSTARD_MODELS.get(mc(sesproc.MC_TYPE), str(mc(sesproc.MC_TYPE))),
                          'threshold': _r(mc(sesproc.MC_THR)), 'ratio': _r(mc(sesproc.MC_RATIO), 2),
                          'attack_ms': _r(mc(sesproc.MC_ATK) * 1000, 2), 'release_ms': _r(mc(sesproc.MC_REL) * 1000),
                          'knee': 'hard' if mc(sesproc.MC_KNEE) == 1.0 else 'soft', 'mix': _r(mc(sesproc.MC_MIX), 2),
                          'output': _r(mc(sesproc.MC_OUT))}
    if g(K['delay_on']) == 1.0:
        out['delay_ms'] = _r(g(K['delay']) * 1000, 2)
    return out


def summary(rb):
    """One plain line of what a channel's readback holds, for the report."""
    parts = []
    if rb['hpf']:
        parts.append('HPF %s' % hz(rb['hpf']))
    if rb['lpf']:
        parts.append('LPF %s' % hz(rb['lpf']))
    if rb['eq']:
        parts.append('EQ ' + ', '.join('%s%s %+.1f' % ({'low_shelf': 'LS ', 'high_shelf': 'HS '}.get(b['type'], ''),
                                                         hz(b['freq']), b['gain']) for b in rb['eq']))
    if rb['gate']:
        gt = rb['gate']
        parts.append('gate %.0f dB' % gt['threshold'] if gt['mode'] == 'gate' else
                     'Dyn2 %s %.0f dB' % (gt['mode'], gt['threshold']))
    if rb['comp']:
        parts.append('comp %.0f dB %.1f:1' % (rb['comp']['threshold'], rb['comp']['ratio']))
    if rb['mustard']:
        parts.append('Mustard %s %.0f dB' % (rb['mustard']['model'], rb['mustard']['threshold']))
    if rb['delay_ms']:
        parts.append('delay %.2f ms' % rb['delay_ms'])
    if rb['polarity']:
        parts.append('polarity')
    return '; '.join(parts) or 'flat'


def hz(f):
    return ('%.2gk' % (f / 1000.0)).replace('.0k', 'k') if f >= 1000 else '%d' % round(f)
