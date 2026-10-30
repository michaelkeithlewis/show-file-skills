#!/usr/bin/env python3
"""options.py - the optional parts of a Session Maker request: bus layout, FX units, monitor mixes, aux sends and the
input patch with starting gain and 48V. build.py calls it; a request without these blocks builds exactly as before.

Request blocks (all optional; absent = the console default, untouched):
  'buses':  'auto' | {'aux_mono', 'aux_stereo', 'grp_mono', 'grp_stereo'}   grp_stereo counts the Master.
            'auto' (also used when the block is absent but FX or mixes need more auxes) keeps the default layout
            when it fits, else adds auxes and takes back unused mono auxes, then groups, until it fits the console's
            bus budget (buses.BUS_LIMIT). Over budget: ValueError with a plain sentence.
  'fx':     [{'kind': FX_CHOICES key or a factory preset name, 'feed_aux': n | None (next free mono aux),
              'return': 'auto' | 'new' | 'none' | channel number, 'name': optional, 'sends': 'auto' | 'none'}]
            Each unit is fed by its own aux (the aux takes the unit's name, master at 0 dB) and returns on a stereo
            input. 'auto' return: an unused FX-return row of the same kind in the plan (fx_reverb, fx_delay,
            fx_modulation, fx_other), else a new stereo channel after the last one. 'auto' sends: post-fader sends
            at the levels engineers use in the real sessions (FX_SENDS), one reverb of each role per channel.
  'mixes':  {'stereo': IEM mixes, 'mono': wedge mixes, 'click': 'all' | 'drums' | 'none', 'outputs': bool,
             'names': optional [..]}. Mixes are named after the players (seats()), every channel goes pre-fader at
            sends.MIX_BASE with the player's own channels 6 dB up, stereo mixes have link pans on, and with
            'outputs' each mix is patched to free line outputs of the stage racks (then the Local I/O).
  'sends':  [{'ch', 'aux', 'level_db', 'pre', 'pan'}]  explicit aux sends, written last.
  'patch':  {'mode': 'rack' | 'local' | 'none', 'start' (or 'start_socket'): first socket on the first device
             (1 to its mic count, else a plain refusal; after the last device the patch wraps back to its lower sockets),
             'gain_db': 'auto' | 'none' | {category: dB}, 'phantom': 'auto' | 'none'}
            Channels go in order onto the mic sockets (patch.default_plan): racks in port order then the Local I/O
            ('rack'), or the Local I/O only ('local'). FX returns are left out. 48V: the channel's own value (the
            list's 48V column), else the mic named in the list (SOURCE_PHANTOM), else the category (PHANTOM_ON).

Order (build.py): restructure the default -> relayout -> apply_fx -> process.apply -> apply_rest -> checks.
Editor proofs and the field map: the decode notes (not published). The starting values come from 39 real sessions as
aggregate medians only: no names or show content.
"""
import json
import os
import re
import unicodedata

from . import buses as B
from . import fx as FX
from . import layout
from . import patch as P
from . import sends as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS_CACHE = os.path.join((os.environ.get('SM_BASELINES') or os.path.join(ROOT, 'baselines')), 'options_facts.json')

FX_CHOICES = {
    'vocal plate': ('Vocal Plate', 'Vocal Plate', 'VoxPlate', 'vocal', 'Vocal plate'),
    'plate': ('Medium Plate', 'Plate', 'Plate', 'vocal', 'Plate'),
    'hall': ('Large hall', 'Hall', 'Hall', 'hall', 'Hall'),
    'room': ('Live room', 'Room', 'Room', 'drum', 'Room (drums)'),
    'drum plate': ('Drum Plate', 'Drum Plate', 'DrumPlt', 'drum', 'Drum plate'),
    'gated': ('Non-Linear', 'Gated Verb', 'GateVerb', 'drum', 'Gated reverb'),
    'delay': ('Studio delay', 'Delay', 'Delay', 'delay', 'Delay'),
    'slap': ('Simple delay', 'Slap', 'Slap', 'delay', 'Slap delay'),
    'chorus': ('Guitar chorus', 'Chorus', 'Chorus', 'mod-guitar', 'Chorus (guitars)'),
    'thicken': ('Vocal Thicken', 'Thicken', 'Thicken', 'mod-vocal', 'Vocal thicken'),
}
FX_ORDER = list(FX_CHOICES)
RETURN_CAT = {'reverb': 'fx_reverb', 'delay': 'fx_delay', 'chorus': 'fx_modulation', 'pitch': 'fx_modulation',
              'special': 'fx_other'}
FX_CATS = ('fx_reverb', 'fx_delay', 'fx_modulation', 'fx_other')
MAX_FX = 8

FX_SENDS = {
    'vocal': {'lead_vocal': 0.0, 'vocal_generic': 0.0, 'choir': -5.0},
    'drum': {'snare_top': -1.0, 'rack_tom': -1.0, 'floor_tom': 0.0, 'roto_tom': -1.0},
    'hall': {'lead_vocal': 0.0, 'vocal_generic': 0.0, 'acoustic_guitar': 0.0, 'choir': -5.0, 'strings': -5.0,
             'keys': -10.0, 'piano': -10.0, 'snare_top': -10.0},
    'delay': {'lead_vocal': 0.0},
    'mod-vocal': {'lead_vocal': 0.0, 'vocal_generic': 0.0},
    'mod-guitar': {'electric_guitar': 0.0},
}
ROLE_ORDER = ('vocal', 'drum', 'delay', 'mod-vocal', 'mod-guitar', 'hall')

GAIN_BASE = {
    'kick_in': 11.5, 'kick_out': 19.0, 'snare_top': 14.0, 'snare_bottom': 11.0, 'hihat': 14.0, 'rack_tom': 15.0,
    'floor_tom': 15.0, 'roto_tom': 22.5, 'overheads': 15.0, 'drum_trigger': 10.0, 'sample_pad': 22.5,
    'hand_perc': 15.5, 'bass_di': 18.0, 'bass_amp': 23.0, 'electric_guitar': 24.0, 'acoustic_guitar': 23.5,
    'keys': 10.0, 'lead_vocal': 17.0, 'vocal_generic': 17.0, 'vocal_fx_mic': 17.0, 'vocal_ear_split': 31.0,
    'speech_mic': 7.0, 'talkback': 33.5, 'tracks_music': 0.0, 'tracks_drums_perc': 0.0, 'tracks_bass': 0.0,
    'tracks_vocals': 0.0, 'click': 1.5, 'cues_guide': 1.0, 'media_playback': 10.0, 'audience': 18.0,
    'measurement_ref': 10.0,
}
PHANTOM_ON = {'kick_in', 'hihat', 'overheads', 'hand_perc', 'audience', 'measurement_ref'}
SOURCE_PHANTOM = [
    (re.compile(r'(?i)\b(km ?1\d\d|km ?184|c ?414|c ?451|c ?214|c ?535|sm ?81|sm ?137|sm ?86|sm ?87|beta ?(87|91|98)|'
                r'b ?91|b ?98|ksm ?(9|32|44|137|141)|e ?614|e ?914|e ?965|at ?40\d\d|at ?20\d\d|nt ?[45]\b|u ?87|'
                r'tlm ?\d+|kms ?1\d\d|dpa|4099|4011|d:?vote|d:?dicate|pzm|mk ?4|cm ?3|j ?48|pro ?48|'
                r'condenser)\b'), True),
    (re.compile(r'(?i)\b(sm ?57|sm ?58|sm ?7b?|beta ?(52|56|57|58)a?|b ?52|d ?6|d ?112|e ?60[2-9]|e ?609|e ?906|'
                r'e ?835|e ?935|e ?945|md ?421|md ?441|re ?20|m ?88|m ?201|i ?5|ksm ?8|dynamic|ribbon|r ?121|'
                r'wireless|rf|line)\b'), False),
]

SEATS = [
    ('lead', 'Lead Vox', {'lead_vocal'}, True),
    ('drums', 'Drums', {'kick_in', 'kick_out', 'kick_sub', 'snare_top', 'snare_bottom', 'hihat', 'rack_tom',
                        'floor_tom', 'roto_tom', 'overheads', 'ride', 'drum_crotch', 'drum_trigger', 'sample_pad'},
     False),
    ('bass', 'Bass', {'bass_di', 'bass_amp', 'synth_bass'}, False),
    ('egtr', 'Gtr', {'electric_guitar'}, True),
    ('keys', 'Keys', {'keys', 'piano', 'organ', 'synth'}, False),
    ('agtr', 'Ac Gtr', {'acoustic_guitar', 'folk_strings'}, True),
    ('perc', 'Perc', {'hand_perc'}, False),
    ('horns', 'Horns', {'horns'}, False),
    ('strings', 'Strings', {'strings'}, False),
    ('bgv', 'BGV', {'vocal_generic'}, True),
    ('choir', 'Choir', {'choir'}, False),
]
SEAT_STAGE_ORDER = ['drums', 'perc', 'bass', 'egtr', 'agtr', 'keys', 'horns', 'strings', 'lead', 'bgv', 'choir']
MAX_MIXES = 24


def _player_key(name):
    """'Gtr 1 Amp' / 'EG1' -> '1'; a name without a number is its own player."""
    m = re.search(r'(\d+)', name or '')
    return m.group(1) if m else (name or '').strip().lower()


def seats(plan):
    """[(key, name, [channel numbers])] in mix-priority order (SEATS), for the channels in `plan`."""
    out = []
    for key, label, cats, per in SEATS:
        chs = [p for p in plan if p.get('category') in cats and not p.get('fx_return')]
        if not chs:
            continue
        if not per:
            out.append((key, label, [p['n'] for p in chs]))
            continue
        groups = {}
        for p in chs:
            groups.setdefault(_player_key(p.get('full_name') or p['name']), []).append(p['n'])
        many = len(groups) > 1
        for k, (_, ns) in enumerate(groups.items(), 1):
            out.append((key, '%s %d' % (label, k) if many else label, ns))
    return out


def _mix_plan(mx, plan):
    """The mixes of a request: [{'aux': None, 'name', 'stereo', 'own', 'click', 'seat'}], IEM mixes first, each kind
    in stage order. prepare() hands out the aux numbers."""
    st, mo = mx['stereo'], mx['mono']
    pool = seats(plan)
    chosen = pool[:st + mo]
    iem, wedge = chosen[:st], chosen[st:st + mo]
    order = lambda lst: sorted(lst, key=lambda s: (SEAT_STAGE_ORDER.index(s[0]), pool.index(s)))
    names = list(mx.get('names') or [])
    has_click = any(p.get('category') in S.ONLY_ON_REQUEST for p in plan)
    out = []
    for stereo, lst, count in ((True, order(iem), st), (False, order(wedge), mo)):
        for k in range(count):
            seat = lst[k] if k < len(lst) else None
            name = seat[1] if seat else ('%s %d' % ('IEM' if stereo else 'Wedge', k + 1))
            out.append({'aux': None, 'name': name, 'stereo': stereo, 'own': seat[2] if seat else [],
                        'seat': seat[0] if seat else None})
    for m, nm in zip(out, names):
        nm = _ascii(nm)[:S.NAME_MAX].strip()
        if nm:
            m['name'] = nm
    if has_click:
        click = mx.get('click', 'all')
        for m in out:
            m['click'] = click == 'all' or (click == 'drums' and m['seat'] == 'drums')
        if click == 'drums' and out and not any(m['seat'] == 'drums' for m in out):
            out[0]['click'] = True
    else:
        for m in out:
            m['click'] = False
    return out


_TRANSLIT = str.maketrans({'\u0141': 'L', '\u0142': 'l', '\u00d8': 'O', '\u00f8': 'o', '\u00df': 'ss', '\u00c6': 'AE',
                           '\u00e6': 'ae', '\u0152': 'OE', '\u0153': 'oe', '\u0110': 'D', '\u0111': 'd', '\u00de': 'Th',
                           '\u00fe': 'th', '\u0131': 'i', '\u00d0': 'D', '\u00f0': 'd'})


def _ascii(s):
    """Plain printable ASCII, as intake.console_name: accents folded ('H\u00e4ll\u00e9' -> 'Halle', '\u00f8' -> 'o'),
    anything else dropped, runs of spaces collapsed. Bus and FX names are written as latin-1 bytes, and the console
    shows ASCII."""
    s = unicodedata.normalize('NFKD', str(s or '').translate(_TRANSLIT)).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', re.sub(r'[^\x20-\x7e]', ' ', s)).strip()


def _int(v, lo, hi, what):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError('%s must be a whole number.' % what)
    if not lo <= n <= hi:
        raise ValueError('%s must be %d to %d.' % (what, lo, hi))
    return n


def fx_choice(kind):
    """A FX_CHOICES key, or the choice of a factory preset name. ValueError for anything else."""
    k = re.sub(r'\s+', ' ', str(kind or '')).strip().lower()
    if k in FX_CHOICES:
        return k
    for key, c in FX_CHOICES.items():
        if c[0].lower() == k:
            return key
    raise ValueError('Unknown FX type %r. Pick one of: %s.' % (kind, ', '.join(c[4] for c in FX_CHOICES.values())))


def present(req):
    """True when the request carries any option block."""
    return any(req.get(k) not in (None, [], {}, '') for k in ('buses', 'fx', 'mixes', 'sends', 'patch'))


def normalize(req):
    """Plain-data option blocks from a request, checked for type and range. -> dict (empty = no options)."""
    o = {}
    fx_in = req.get('fx') or []
    if not isinstance(fx_in, list):
        raise ValueError('FX must be a list.')
    if len(fx_in) > MAX_FX:
        raise ValueError('Pick up to %d FX units.' % MAX_FX)
    units = []
    for u in fx_in:
        u = u if isinstance(u, dict) else {'kind': u}
        key = fx_choice(u.get('kind'))
        ret = u.get('return', 'auto')
        if ret not in ('auto', 'new', 'none', None):
            ret = _int(ret, 1, 256, 'The FX return channel')
        feed = u.get('feed_aux')
        feed = None if feed in (None, '', 'auto') else _int(feed, 1, 128, 'The FX feed aux')
        name = _ascii(u.get('name'))[:24] or None
        units.append({'key': key, 'return': 'none' if ret is None else ret, 'feed_aux': feed, 'name': name,
                      'sends': 'none' if u.get('sends') == 'none' else 'auto'})
    if units:
        o['fx'] = units
    mx = req.get('mixes')
    if mx:
        if not isinstance(mx, dict):
            raise ValueError('Mixes must be an object.')
        st = _int(mx.get('stereo') or 0, 0, MAX_MIXES, 'IEM mixes')
        mo = _int(mx.get('mono') or 0, 0, MAX_MIXES, 'Wedge mixes')
        if st or mo:
            click = mx.get('click', 'all')
            o['mixes'] = {'stereo': st, 'mono': mo, 'click': click if click in ('all', 'drums', 'none') else 'all',
                          'outputs': mx.get('outputs', True) is not False,
                          'names': [_ascii(x)[:24] for x in (mx.get('names') or [])][:2 * MAX_MIXES]}
    bz = req.get('buses')
    if bz not in (None, '', {}):
        if bz == 'auto':
            o['buses'] = 'auto'
        elif isinstance(bz, dict):
            o['buses'] = {k: _int(bz.get(k, 0), 0, 128, lab) for k, lab in
                          (('aux_mono', 'Mono auxes'), ('aux_stereo', 'Stereo auxes'), ('grp_mono', 'Mono groups'),
                           ('grp_stereo', 'Stereo groups'))}
            if o['buses']['aux_mono'] + o['buses']['aux_stereo'] < 1:
                raise ValueError('The bus layout needs at least one aux.')
            o['buses']['grp_stereo'] = max(1, o['buses']['grp_stereo'])
        else:
            raise ValueError("Buses must be 'auto' or the four counts.")
    sd = req.get('sends') or []
    if not isinstance(sd, list):
        raise ValueError('Sends must be a list.')
    out = []
    for e in sd[:4096]:
        if not isinstance(e, dict):
            raise ValueError('Each send needs ch and aux.')
        lv = e.get('level_db', 0.0)
        try:
            lv = max(-150.0, min(10.0, float(lv)))
        except (TypeError, ValueError):
            raise ValueError('A send level must be a number in dB.')
        pre = e.get('pre')
        if pre is not None and not isinstance(pre, bool) and pre not in S.PREPOST and pre not in range(6):
            raise ValueError('Send pre must be one of %s.' % ', '.join(S.PREPOST))
        pan = e.get('pan')
        if pan is not None:
            try:
                pan = max(-1.0, min(1.0, float(pan)))
            except (TypeError, ValueError):
                raise ValueError('A send pan must be -1 to 1.')
        out.append({'ch': _int(e.get('ch'), 1, 256, 'A send channel'), 'aux': _int(e.get('aux'), 1, 128, 'A send aux'),
                    'level_db': lv, 'pre': pre, 'pan': pan})
    if out:
        o['sends'] = out
    pt = req.get('patch')
    if pt:
        if not isinstance(pt, dict):
            raise ValueError('Patch must be an object.')
        mode = pt.get('mode', 'rack')
        if mode not in ('rack', 'local', 'none'):
            raise ValueError("Patch mode must be 'rack', 'local' or 'none'.")
        if mode != 'none':
            gain = pt.get('gain_db', pt.get('gain', 'auto'))
            if gain is True:
                gain = 'auto'
            elif gain in (False, None):
                gain = 'none'
            elif isinstance(gain, dict):
                gain = {str(k): max(-20.0, min(60.0, float(v))) for k, v in gain.items()
                        if isinstance(v, (int, float))}
            elif gain not in ('auto', 'none'):
                raise ValueError("Patch gain must be 'auto', 'none' or dB per category.")
            ph = pt.get('phantom', 'auto')
            ph = 'auto' if ph in (True, 'auto') else 'none'
            o['patch'] = {'mode': mode, 'start': _int(pt.get('start', pt.get('start_socket', 1)) or 1, 1, 128,
                                                      'The first socket'),
                          'gain': gain, 'phantom': ph}
    return o


def _fx_kind(choice):
    """'reverb', 'delay', 'chorus', 'pitch' or 'special' (the DSP pool and the return category follow it)."""
    return FX.KIND_OF_GROUP.get(_group_of(choice), 'special')


_PRESET_GROUP = {}


def _group_of(choice):
    """Factory preset group ('Plate Reverbs', 'Delays') of a choice, from any V2242 default's library."""
    if not _PRESET_GROUP:
        d = os.environ.get('SM_BASELINES') or os.path.join(ROOT, 'baselines')
        try:
            names = sorted((f for f in os.listdir(d) if re.match(r'^q\w*_v2242\.ses$', f)), key=lambda f: f != 'q225_v2242.ses')
        except OSError:
            names = []
        if not names:
            return None
        lib = FX.library(open(os.path.join(d, names[0]), 'rb').read())
        for e in lib[:34]:
            _PRESET_GROUP[e['name'].lower()] = e['category']
    return _PRESET_GROUP.get(FX_CHOICES[choice][0].lower())


_ROLE_WORDS = {'vocal': r'vox|vocal|voc|plate|plt|lead', 'drum': r'drum|room|rm\b|snare|kit|tom|gate|perc',
               'hall': r'hall|verb|rev', 'delay': r'delay|dly|slap|echo|tap', 'mod-vocal': r'thick|doub|vox|vocal',
               'mod-guitar': r'chor|gtr|guitar'}


def _short(name, taken):
    """An 8-character channel name not in `taken` (lower case)."""
    base = name[:8]
    if base.lower() not in taken:
        return base
    for k in range(2, 99):
        cand = (name[:8 - len(str(k))] + str(k))
        if cand.lower() not in taken:
            return cand
    return base


def prepare(req, console, data, plan, warnings):
    """Validate the option blocks against the console and the plan; pick FX returns (plan rows, or new stereo channels
    appended to `plan`), aux numbers and the bus layout; restructure the default when the layout changes.
    -> opts (an empty dict when the request has no option blocks). opts['data'] is the restructured default or None."""
    o = normalize(req)
    if not o:
        return {}
    key, cname = console['key'], console['name']
    o['data'] = None
    nuser = len(plan)
    taken = {p['name'].lower() for p in plan}
    explicit = {}
    for i, u in enumerate(o.get('fx', [])):
        if isinstance(u['return'], int):
            if u['return'] in explicit:
                raise ValueError('FX %d and FX %d both return on channel %d. Give each unit its own return channel.'
                                 % (explicit[u['return']] + 1, i + 1, u['return']))
            explicit[u['return']] = i
    used_rows = set(explicit)
    for i, u in enumerate(o.get('fx', [])):
        preset, uname, short, role, label = FX_CHOICES[u['key']]
        same = [x for x in o['fx'][:i] if x['key'] == u['key']]
        u.update(preset=preset, role=role, label=label, kind=_fx_kind(u['key']))
        u['name'] = u['name'] or (uname if not same else '%s %d' % (uname, len(same) + 1))
        want_cat = RETURN_CAT.get(u['kind'], 'fx_other')
        ret = u['return']
        row = None
        if isinstance(ret, int):
            row = next((p for p in plan[:nuser] if p['n'] == ret), None)
            if row is None:
                raise ValueError('FX %d (%s) returns on channel %d, but the plan has %d channels.' % (
                    i + 1, u['name'], ret, nuser))
        elif ret == 'auto':
            cands = [p for p in plan[:nuser] if p['n'] not in used_rows and p['category'] in (want_cat, 'fx_other')]
            if cands:
                rx = _ROLE_WORDS.get(role, '')
                cands.sort(key=lambda p: (p['category'] != want_cat,
                                          not re.search(rx, (p.get('full_name') or p['name']).lower()), p['n']))
                row = cands[0]
        if row is not None:
            used_rows.add(row['n'])
            u['return_ch'] = row['n']
            row['fx_return'] = True
            if not row['stereo']:
                row['stereo'] = True
                warnings.append('Ch %d %s is made stereo to take the %s return.' % (row['n'], row['name'], u['name']))
            if row['category'] not in FX_CATS:
                row['category'] = want_cat
        elif ret in ('auto', 'new'):
            n = len(plan) + 1
            nm = short
            if same:
                suf = str(len(same) + 1)
                nm = short + ' ' + suf if len(short) + 1 + len(suf) <= 8 else short[:8 - len(suf)] + suf
            nm = _short(nm, taken)
            taken.add(nm.lower())
            plan.append({'n': n, 'idx': n, 'name': nm, 'full_name': '%s return' % u['name'], 'stereo': True,
                         'category': want_cat, 'phantom': None, 'source': None, 'notes': None, 'fx_return': True})
            u['return_ch'] = n
        else:
            u['return_ch'] = None
    cap = min(console['max_inputs'], layout.MAX_INPUT_IDS)
    if len(plan) > cap:
        raise ValueError('The %s holds %d inputs. %d channels plus %d FX return%s make %d. Remove channels or FX.' % (
            cname, cap, nuser, len(plan) - nuser, '' if len(plan) - nuser == 1 else 's', len(plan)))

    cur = B.describe(data)
    am, ast, gm, gs = cur['aux_mono'], cur['aux_stereo'], cur['grp_mono'], cur['grp_stereo']
    limit = B.bus_limit(data, key)
    n_feed = sum(1 for u in o.get('fx', []) if u['feed_aux'] is None)
    mx = o.get('mixes')
    need_m = n_feed + (mx['mono'] if mx else 0)
    need_s = mx['stereo'] if mx else 0
    lay = None
    bz = o.get('buses', 'auto')
    if isinstance(bz, dict):
        lay = (bz['aux_mono'], bz['aux_stereo'], bz['grp_mono'], bz['grp_stereo'])
        if lay[0] < need_m or lay[1] < need_s:
            raise ValueError('The bus layout has %d mono and %d stereo auxes. %s %s.' % (
                lay[0], lay[1], _needs_text(o, verb=True), _auxes_text(need_m, need_s)))
        if lay == (am, ast, gm, gs):
            lay = None
    elif need_m > am or need_s > ast:
        a2, s2, g2, gs2 = max(am, need_m), max(ast, need_s), gm, gs
        width = lambda: a2 + 2 * s2 + g2 + 2 * gs2
        while limit is not None and width() > limit:
            if a2 > need_m:
                a2 -= 1
            elif s2 > need_s:
                s2 -= 1
            elif g2 > 0:
                g2 -= 1
            elif gs2 > 1:
                gs2 -= 1
            else:
                break
        lay = (a2, s2, g2, gs2)
    o['auto_layout'] = not isinstance(bz, dict)
    o['limit'] = limit
    final = lay or (am, ast, gm, gs)
    o['layout'] = {'aux_mono': final[0], 'aux_stereo': final[1], 'grp_mono': final[2], 'grp_stereo': final[3],
                   'width': final[0] + 2 * final[1] + final[2] + 2 * final[3], 'limit': limit,
                   'changed': lay is not None}
    if limit is not None and o['layout']['width'] > limit:
        raise ValueError('The %s has %d bus slots (a stereo bus takes 2, the Master takes 2). %s %s, which do not '
                         'fit next to the Master. Use fewer mixes or FX.' % (
                             cname, limit, _needs_text(o, verb=True), _auxes_text(need_m, need_s))
                         if not isinstance(bz, dict) else
                         'The %s has %d bus slots (a stereo bus takes 2). This layout needs %d.' % (
                             cname, limit, o['layout']['width']))
    if lay is not None:
        try:
            o['data'] = B.restructure(data, *lay, console=key)
        except ValueError as e:
            msg = str(e)
            if 'engine' in msg.lower() or 'pool' in msg.lower():
                raise ValueError('The %s has no processing room for that bus layout next to its inputs. Use fewer '
                                 'buses.' % cname)
            raise ValueError('That bus layout does not work on the %s: %s.' % (cname, msg.rstrip('.')))

    a_m = list(range(1, final[0] + 1))
    a_s = list(range(final[0] + 1, final[0] + final[1] + 1))
    fixed = {u['feed_aux'] for u in o.get('fx', []) if u['feed_aux'] is not None}
    for u in o.get('fx', []):
        if u['feed_aux'] is not None:
            if u['feed_aux'] > final[0] + final[1]:
                raise ValueError('FX %s is fed by aux %d, but the session has %d auxes.' % (
                    u['name'], u['feed_aux'], final[0] + final[1]))
            continue
        u['feed_aux'] = next(a for a in a_m if a not in fixed)
        fixed.add(u['feed_aux'])
    if len(fixed) < len(o.get('fx', [])):
        raise ValueError('Two FX units are fed by the same aux. Give each unit its own aux.')
    if mx:
        free_m = [a for a in a_m if a not in fixed]
        free_s = [a for a in a_s if a not in fixed]
        if len(free_m) < mx['mono'] or len(free_s) < mx['stereo']:
            raise ValueError('The bus layout has no free auxes left for %s.' % _needs_text(o))
        o['mixes_plan'] = _mix_plan(mx, plan)
        it_m, it_s = iter(free_m), iter(free_s)
        for m in o['mixes_plan']:
            m['aux'] = next(it_s) if m['stereo'] else next(it_m)
    for e in o.get('sends', []):
        if e['ch'] > len(plan):
            raise ValueError('A send names channel %d, but the plan has %d channels.' % (e['ch'], len(plan)))
        if e['aux'] > final[0] + final[1]:
            raise ValueError('A send names aux %d, but the session has %d auxes.' % (e['aux'], final[0] + final[1]))
        if e['pan'] is not None and e['aux'] <= final[0]:
            raise ValueError('Aux %d is mono, so a send to it has no pan.' % e['aux'])
    covered = {}
    sends_fx = []
    by_role = {}
    for u in o.get('fx', []):
        if u['sends'] == 'auto':
            by_role.setdefault(u['role'], u)
    for role in ROLE_ORDER:
        u = by_role.get(role)
        if not u:
            continue
        table = FX_SENDS[role]
        chans = [p for p in plan[:nuser] if p['category'] in table]
        if role == 'delay' and not chans:
            chans = [p for p in plan[:nuser] if p['category'] == 'vocal_generic'][:1]
            table = dict(table, vocal_generic=0.0)
        for p in chans:
            if role == 'hall' and p['n'] in covered:
                continue
            sends_fx.append({'ch': p['n'], 'aux': u['feed_aux'], 'level_db': table[p['category']], 'unit': u['name']})
            if role in ('vocal', 'drum'):
                covered[p['n']] = role
    o['fx_sends'] = sends_fx
    pt = o.get('patch')
    if pt:
        for p in plan:
            if p.get('fx_return'):
                continue
            p['gain_db'] = _gain_for(p, pt['gain'])
            p['phantom_set'] = _phantom_for(p) if pt['phantom'] == 'auto' else None
    return o


def _auxes_text(m, s):
    """'1 mono aux', '2 stereo auxes', '3 mono and 2 stereo auxes'."""
    parts = ['%d mono' % m] if m else []
    parts += ['%d stereo' % s] if s else []
    return ' and '.join(parts or ['0']) + (' aux' if m + s == 1 else ' auxes')


def _needs_text(o, verb=False):
    """'2 FX units and 3 IEM mixes'; verb=True adds 'need' / 'needs'."""
    parts = []
    nfx = len(o.get('fx', []))
    if nfx:
        parts.append('%d FX unit%s' % (nfx, '' if nfx == 1 else 's'))
    mx = o.get('mixes') or {}
    if mx.get('stereo'):
        parts.append('%d IEM mix%s' % (mx['stereo'], '' if mx['stereo'] == 1 else 'es'))
    if mx.get('mono'):
        parts.append('%d wedge mix%s' % (mx['mono'], '' if mx['mono'] == 1 else 'es'))
    text = ' and '.join(parts) or 'These options'
    if verb:
        one = len(parts) == 1 and re.match(r'1 ', parts[0])
        text += ' needs' if one else ' need'
    return text


def _gain_for(p, gain):
    if gain == 'none':
        return None
    if isinstance(gain, dict):
        return gain.get(p['category'], GAIN_BASE.get(p['category']))
    return GAIN_BASE.get(p['category'])


def source_phantom(text):
    """True / False when the source text names a known condenser / dynamic mic (or an active DI / a line source)."""
    t = str(text or '')
    if not t.strip():
        return None
    for rx, v in SOURCE_PHANTOM:
        if rx.search(t):
            return v
    return None


def _phantom_for(p):
    if isinstance(p.get('phantom'), bool):
        return p['phantom']
    v = source_phantom(p.get('source'))
    if v is not None:
        return v
    if p['category'] in PHANTOM_ON:
        return True
    if p['category'] in GAIN_BASE:
        return False
    return None


def _fresh(ses):
    """Forget the sends.objects cache (its key is the file length; fx edits rebuild the file)."""
    if hasattr(ses, '_sends_objs'):
        del ses._sends_objs


def apply_fx(ses, opts):
    """After layout.relayout: add each FX unit, feed it from its aux (named after the unit, master at 0 dB, unmuted)
    and patch its return channel. -> nothing; fills unit numbers into opts['fx']."""
    for u in opts.get('fx', []):
        ret = ('input', u['return_ch']) if u.get('return_ch') else None
        u['unit'] = FX.add_fx(ses, u['preset'], feed_aux=u['feed_aux'], return_to=ret, name=u['name'],
                              make_stereo=False)
        _fresh(ses)
        S.name_bus(ses, 'aux', u['feed_aux'], u['name'])
        S.set_bus_fader(ses, 'aux', u['feed_aux'], db=0.0, mute=False)


def _free_line_outs(ses):
    """Output sockets for monitor mixes: the named line outputs of the stage racks (port order), then the Local I/O,
    that nothing feeds yet. -> [[socket dicts of one device in order]]."""
    devs = sorted((d for d in P.list_io(ses) if d['port'] is not None and d['device_code'] in P.PREAMP_DEVICES),
                  key=lambda d: (d['port'] == 0, d['port']))
    socks = S.output_sockets(ses)
    objs = S.objects(ses)
    out = []
    for d in devs:
        lst = [s for s in socks if s['type'] == d['out_type'] and re.search(r'\bline\b', s['name'] or '', re.I)]
        lst.sort(key=lambda s: s['idx'])
        for s in lst:
            q = objs[s['id']].slot(S.SOCKET, S.SK_SOURCE)
            s['free'] = bytes(ses.d[q:q + 4]) == b'\0\0\0\0'
        if lst:
            out.append(lst)
    return out


def _pick_outputs(ses, mixes):
    """{aux: [left socket, right socket?]} for the mixes, in order, stereo mixes on an odd/even pair."""
    devs = _free_line_outs(ses)
    taken, out = set(), {}
    for m in mixes:
        got = None
        for lst in devs:
            for k, s in enumerate(lst):
                if not s['free'] or s['id'] in taken:
                    continue
                if not m['stereo']:
                    got = [s]
                    break
                if k % 2 == 0 and k + 1 < len(lst) and lst[k + 1]['free'] and lst[k + 1]['id'] not in taken \
                        and lst[k + 1]['idx'] == s['idx'] + 1:
                    got = [s, lst[k + 1]]
                    break
            if got:
                break
        if not got:
            continue
        for s in got:
            taken.add(s['id'])
        out[m['aux']] = got
    return out


def apply_rest(ses, opts, plan, warnings):
    """After process.apply: monitor mixes, FX sends, explicit sends, mix outputs and the input patch.
    Records what was written in opts['done'] for the checks and the report."""
    if not opts:
        return
    done = {'sends': {}, 'outputs': {}, 'patch': [], 'patch_notes': []}
    opts['done'] = done
    mixes = opts.get('mixes_plan') or []
    if mixes:
        for m in mixes:
            if m['stereo']:
                S.set_link_pans(ses, m['aux'], 'on')
        chans = [{'n': p['n'], 'name': p['name'], 'category': p['category'], 'stereo': p['stereo']} for p in plan]
        lv = S.monitor_mixes(ses, chans, [{'aux': m['aux'], 'name': m['name'], 'own': m['own'], 'click': m['click']}
                                          for m in mixes], pre='pre', fader_db=0.0)
        for m in mixes:
            for p in plan:
                level = lv[m['aux']].get(p['n'])
                done['sends'][(p['n'], m['aux'])] = (level if level is not None else S.OFF_DB, level is not None,
                                                     S.PREPOST['pre'])
        if opts['mixes'].get('outputs'):
            picks = _pick_outputs(ses, mixes)
            for m in mixes:
                socks = picks.get(m['aux'])
                if not socks:
                    continue
                S.patch_output(ses, 'aux', m['aux'], {'type': socks[0]['type'], 'idx': socks[0]['idx']},
                               {'type': socks[1]['type'], 'idx': socks[1]['idx']} if len(socks) > 1 else None)
                done['outputs'][m['aux']] = [s['name'] for s in socks]
            left = [m['name'] for m in mixes if m['aux'] not in done['outputs']]
            if left:
                warnings.append('No free line outputs left for %s. Patch %s on the console.' % (
                    ', '.join(left), 'it' if len(left) == 1 else 'them'))
    for e in opts.get('fx_sends', []):
        S.set_send(ses, e['ch'], e['aux'], e['level_db'], on=True, pre='post')
        done['sends'][(e['ch'], e['aux'])] = (S._db(e['level_db']), True, S.PREPOST['post'])
    for e in opts.get('sends', []):
        on = e['level_db'] > S.OFF_DB
        r = S.set_send(ses, e['ch'], e['aux'], e['level_db'], on=on, pre=e['pre'], pan=e['pan'])
        pp = S._prepost_value(e['pre']) if e['pre'] is not None else S.PREPOST.get(r['prepost'], r['prepost'])
        done['sends'][(e['ch'], e['aux'])] = (S._db(e['level_db']), on, pp)
    pt = opts.get('patch')
    if pt:
        ins = [p for p in plan if not p.get('fx_return')]
        chans = [{'ch': p['n'], 'stereo': p['stereo'], 'gain_db': p.get('gain_db'), 'phantom': p.get('phantom_set')}
                 for p in ins]
        dev = 'Local I/O' if pt['mode'] == 'local' else None
        pp = P.default_plan(ses, chans, device=dev, start=pt['start'])
        notes, seen = [], set()
        for n in P.patch_inputs(ses, pp):
            m = re.match(r'input (\d+):', n)
            if m and m.group(1) in seen:
                continue
            seen.add(m.group(1) if m else n)
            notes.append(n)
        done['patch_notes'] = notes
        for e in pp:
            main = P.find_input_socket(ses, e['socket'])
            right = P.right_socket(ses, main) if ses.width.get(e['ch']) == 2 else None
            g = None
            if e.get('gain_db') is not None:
                lo, hi = P.gain_range(ses, main)
                g = min(max(round(float(e['gain_db']) / P.GAIN_STEP) * P.GAIN_STEP, lo), hi)
            done['patch'].append({'ch': e['ch'], 'main': main['name'], 'ref': (main['type'], main['idx']),
                                  'right': right['name'] if right else None, 'gain_db': g,
                                  'phantom': e.get('phantom'), 'device': main['group']})
        patched = {e['ch'] for e in pp}
        miss = [p['n'] for p in ins if p['n'] not in patched]
        if miss:
            warnings.append('Channels %s are not patched: no free mic inputs are left on %s. Patch them on the '
                            'console.' % (_ranges(miss), 'the Local I/O' if pt['mode'] == 'local' else
                                          'the stage racks and the Local I/O'))
        moved = [n for n in notes if 'set to' in n]
        if moved:
            lo = re.findall(r'set to ([+-]?\d+\.\d) dB', moved[0])
            warnings.append('%d channel%s got a higher starting gain than planned (%s): the preamps there start at '
                            '%s dB.' % (len(moved), '' if len(moved) == 1 else 's', ', '.join(
                                re.match(r'input (\d+)', n).group(1) for n in moved[:12]) +
                            (', ...' if len(moved) > 12 else ''), lo[0] if lo else '+10'))


def _ranges(ns):
    ns, out, i = sorted(ns), [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append(str(ns[i]) if i == j else '%d-%d' % (ns[i], ns[j]))
        i = j + 1
    return ', '.join(out)


def _chk(name, ok, detail):
    return {'name': name, 'ok': bool(ok), 'detail': detail}


def checks(rs, opts, out_bytes):
    """Read the written file back (rs = a fresh ses.Session of it) and compare with what was planned."""
    if not opts:
        return []
    out = []
    lay = opts['layout']
    if opts.get('buses') or lay['changed']:
        dsc = B.describe(out_bytes)
        got = (dsc['aux_mono'], dsc['aux_stereo'], dsc['grp_mono'], dsc['grp_stereo'])
        want = (lay['aux_mono'], lay['aux_stereo'], lay['grp_mono'], lay['grp_stereo'])
        out.append(_chk('Bus layout', got == want and (lay['limit'] is None or lay['width'] <= lay['limit']),
                        '%d mono and %d stereo auxes, %d mono and %d stereo groups with the Master. %d of %s bus '
                        'slots.' % (got + (lay['width'], lay['limit'] if lay['limit'] is not None else '?'))
                        if got == want else 'The file holds %d+%d auxes and %d+%d groups, not %d+%d and %d+%d.'
                        % (got + want)))
    if opts.get('fx'):
        units = {u['unit']: u for u in FX.units(rs)}
        bad = []
        for u in opts['fx']:
            g = units.get(u['unit'])
            fed = g and any(f.get('aux') == u['feed_aux'] for f in g['feed'])
            ret = g and (u['return_ch'] is None or any(r['input'] == u['return_ch'] for r in g['returns']))
            if not (g and fed and ret and g['name'] == u['name']):
                bad.append(u['name'])
        out.append(_chk('FX', not bad, ('%d unit%s, each fed by its own aux and back on a stereo channel.' % (
            len(opts['fx']), '' if len(opts['fx']) == 1 else 's')) if not bad else 'Not as planned: %s.' %
            ', '.join(bad)))
    sends_done = (opts.get('done') or {}).get('sends') or {}
    if sends_done:
        bad = []
        for (ch, aux), (lv, on, pp) in sends_done.items():
            r = S.read_send(rs, ch, aux)
            if abs(r['level'] - lv) > 1e-4 or r['on'] != on or S.PREPOST.get(r['prepost'], r['prepost']) != pp:
                bad.append((ch, aux))
        nmix = len(opts.get('mixes_plan') or [])
        nact = sum(1 for v in sends_done.values() if v[1])
        out.append(_chk('Sends', not bad, '%d sends written and read back (%d on%s).' % (
            len(sends_done), nact, ', %d monitor mix%s' % (nmix, '' if nmix == 1 else 'es') if nmix else '')
            if not bad else 'Sends differ on %s.' % ', '.join('ch %d aux %d' % b for b in bad[:6])))
    outs = (opts.get('done') or {}).get('outputs') or {}
    if outs or opts.get('mixes_plan'):
        errs = S.route_errors(rs)
        bad = [a for a, names in outs.items() if sum(S.outputs_of(rs, 'aux', a), []) != names]
        out.append(_chk('Outputs', not errs and not bad, ('%d mix%s patched to line outputs. Every output names one '
                                                        'source.' % (len(outs), '' if len(outs) == 1 else 'es'))
                        if not errs and not bad else '; '.join(errs[:2] + ['aux %d is not on %s' % (
                            a, ', '.join(outs[a])) for a in bad[:2]])))
    pt = (opts.get('done') or {}).get('patch')
    if opts.get('patch'):
        bad, n48 = [], 0
        for e in pt or []:
            r = P.input_of(rs, e['ch'])
            ok = r['main_ref'] == {'type': e['ref'][0], 'idx': e['ref'][1]}
            if e['gain_db'] is not None:
                ok &= r['gain_db'] is not None and abs(r['gain_db'] - e['gain_db']) < 0.01
            if e['phantom'] is not None:
                ok &= r['phantom'] == e['phantom']
                n48 += bool(e['phantom'])
            if not ok:
                bad.append(e['ch'])
        errs = P.patch_errors(rs)
        devs = []
        for e in pt or []:
            if e['device'] not in devs:
                devs.append(e['device'])
        out.append(_chk('Input patch', not bad and not errs, ('%d channels on %s, gain and 48V read back (48V on %d).'
                                                              % (len(pt or []), ' and '.join(devs) or 'no sockets',
                                                                 n48)) if not bad and not errs else
                        '; '.join(errs[:2]) or 'Patch differs on channel %s.' % _ranges(bad[:12])))
    return out


def report_lines(opts, plan):
    if not opts:
        return []
    L = ['', '## Buses, FX, mixes and patch', '']
    lay = opts['layout']
    L.append('- Buses: %d mono and %d stereo auxes, %d mono and %d stereo groups (with the Master)%s. %d of %s bus '
             'slots.' % (lay['aux_mono'], lay['aux_stereo'], lay['grp_mono'], lay['grp_stereo'],
                         '' if not lay['changed'] else ', changed from the console default', lay['width'],
                         lay['limit'] if lay['limit'] is not None else '?'))
    by_n = {p['n']: p for p in plan}
    for u in opts.get('fx', []):
        ret = by_n.get(u.get('return_ch'))
        L.append('- FX %d %s (%s preset): fed by aux %d, back on ch %s.' % (
            u['unit'], u['name'], u['preset'], u['feed_aux'],
            '%d %s' % (ret['n'], ret['name']) if ret else 'none'))
    fxs = opts.get('fx_sends') or []
    if fxs:
        per = {}
        for e in fxs:
            per.setdefault(e['unit'], []).append((e['ch'], by_n[e['ch']]['name'], e['level_db']))
        db = lambda v: '%g dB' % (v + 0.0)
        for unit, chs in per.items():
            if len({lv for _, _, lv in chs}) == 1:
                L.append('- Post-fader sends to %s at %s: %s.' % (unit, db(chs[0][2]), ', '.join(
                    '%d %s' % (n, nm) for n, nm, _ in chs)))
            else:
                L.append('- Post-fader sends to %s: %s.' % (unit, ', '.join(
                    '%d %s at %s' % (n, nm, db(lv)) for n, nm, lv in chs)))
    done = opts.get('done') or {}
    for m in opts.get('mixes_plan') or []:
        outs = done.get('outputs', {}).get(m['aux'])
        L.append('- Aux %d %s: %s mix, pre-fader%s%s%s.' % (
            m['aux'], m['name'], 'stereo IEM' if m['stereo'] else 'mono wedge',
            ', own channels %s up 6 dB' % _ranges(m['own']) if m['own'] else '',
            ', click on' if m.get('click') else '', ', out on %s' % ' + '.join(outs) if outs else ''))
    pt = done.get('patch') or []
    if opts.get('patch'):
        if pt:
            runs = []
            for e in pt:
                if runs and runs[-1][0] == e['device']:
                    runs[-1][1].append(e)
                else:
                    runs.append((e['device'], [e]))
            where = '; '.join('%s: ch %s on %s to %s' % (dev, _ranges([e['ch'] for e in es]), es[0]['main'],
                                                          es[-1]['right'] or es[-1]['main']) for dev, es in runs)
            L.append('- Input patch: %s. Starting gain by instrument (medians of 39 real sessions). 48V on ch %s.' % (
                where, _ranges([e['ch'] for e in pt if e['phantom']]) or 'none'))
        for n in done.get('patch_notes') or []:
            L.append('- %s%s%s' % (n[:1].upper(), n[1:], '' if n.endswith('.') else '.'))
    return L


NUMW = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
        'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'couple': 2, 'pair': 2}
_N = r'(\d{1,2}|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)'
_IEM = r'(?:iems?|in[- ]?ears?|ears|iem mix(?:es)?|in[- ]?ear mix(?:es)?)'


FX_WORDS = ((r'\bvocal plate\b|\bvox plate\b', 'vocal plate'), (r'\bdrum plate\b', 'drum plate'),
            (r'(?<!vocal )(?<!vox )(?<!drum )\bplate\b', 'plate'),
            (r'\bhall (?:reverb|verb)\b|\b(?:reverb|verb) hall\b', 'hall'),
            (r'\broom (?:reverb|verb)\b|\b(?:reverb|verb) room\b|\bdrum room (?:reverb|verb)\b', 'room'),
            (r'\bgated? (?:reverb|verb)\b|\bnon-?lin\b', 'gated'), (r'\bslap\b', 'slap'),
            (r'\bdelays?\b(?! ?(?:speakers?|towers?|stacks?|lines?|fills?|rings?))', 'delay'),
            (r'\bchorus (?:fx|effect|pedal|on)\b|\bguitar chorus\b', 'chorus'),
            (r'\bthicken(?:er)?\b|\bdoubler\b', 'thicken'))
_OUTBOARD = re.compile(r'pedal|stomp|helicon|voice ?live|\bsound (?:effects|fx)\b|\bsfx\b|\bqlab\b|\b(?:his|her|their|'
                       r'own) (?:own )?(?:fx|effects|rig|board)|\baxe-?fx\b|\bhelix\b|\bkemper\b|quad cortex|'
                       r'modell?er\b')
_WHO = (r'(?:lead\s+)?(?:singers?|vocalists?|lead vocal(?:ist)?s?|drummers?|bassists?|bass players?|guitarists?|'
        r'guitar players?|keys players?|keyboardists?|keyboard players?|pianists?|md|percussionists?|horn players?|'
        r'sax players?|saxophonists?|backing vocalists?|bgvs?|band ?leaders?|fiddle players?|fiddlers?)')
_WHO_LIST = (r'\b((?:(?:the|our|my|a|one)\s+)?' + _WHO + r'(?:\s*(?:,|and|&|\+)\s*(?:(?:the|our|my)\s+)?' + _WHO +
             r')*)')
_WEARS = (r'\s+(?:(?:wears?|uses?|gets?|has|have|is|are|goes|go|will be|stays?|needs?)\s+)?(?:(?:on|in)\s+)?'
          r'(?:(?:an?|their|his|her|the)\s+)?(?:own\s+)?(?:stereo\s+)?')
_REST = (r'\b(?:everyone|everybody|all the others|the others|others|the rest(?: of (?:the band|them|us))?|'
         r'other players|other musicians|the band)(?:\s+else)?\s+(?:(?:is|are|will be|goes|go|gets?|uses?|stays?|has|have)\s+)?'
         r'(?:(?:on|in)\s+)?(?:(?:a|their)\s+)?')


def _who_count(text):
    """Players named in "the singer and drummer": one per role word, two for a plural ("the singers")."""
    return sum(2 if w.endswith('s') and not w.endswith(('ss', 'bass')) else 1 for w in re.findall(_WHO, text)) or 1


def _n(tok):
    return int(tok) if tok.isdigit() else NUMW.get(tok, 0)


def suggest(description, channels):
    """Options a show description (and the planned channels) ask for. -> (options, note or None).
    options: {'fx': [{'kind'}], 'mixes': {'stereo', 'mono'}, 'role': 'mon'} (keys only when found)."""
    t = ' %s ' % re.sub(r'\s+', ' ', str(description or '').lower())
    out, said = {}, []
    st = mo = None
    m = re.search(_IEM + r'\s+(?:mixes\s+)?for\s+(?:the\s+|all\s+|our\s+)?' + _N + r'\b', t)
    if m:
        st = _n(m.group(1))
    m = m or re.search(r'\b' + _N + r'\s+(?:stereo\s+)?' + _IEM + r'(?!\s+for)', t)
    if m and st is None:
        st = _n(m.group(1))
    w = re.search(r'\b' + _N + r'\s+(?:monitor\s+)?wedges?\b', t) or \
        re.search(r'\bwedges?\s+(?:mixes\s+)?for\s+(?:the\s+)?' + _N + r'\b', t)
    if w:
        mo = _n(w.group(1))
    gen = re.search(r'\b' + _N + r'\s+(?:monitor|mon)\s+mix(?:es)?\b', t)
    if gen and st is None and mo is None:
        if re.search(r'\bwedges?\b', t) and not re.search(_IEM, t):
            mo = _n(gen.group(1))
        else:
            st = _n(gen.group(1))
    st_ = seats([dict(c, n=k + 1, name=c.get('name') or '') for k, c in enumerate(channels or [])])
    players = sum(1 for k, _, _ in st_ if k not in ('lead', 'bgv', 'choir')) + (1 if any(
        k in ('lead', 'bgv') for k, _, _ in st_) else 0)
    no_iem = re.search(r'\bno (?:iem|in[- ]?ear)', t)
    who_iem = re.search(_WHO_LIST + _WEARS + _IEM + r'\b', t)
    who_wdg = re.search(_WHO_LIST + _WEARS + r'(?:monitor\s+)?wedges?\b', t)
    if st is None and who_iem and not no_iem:
        st = _who_count(who_iem.group(1))
        if mo is None and re.search(_REST + r'(?:monitor\s+)?wedges?\b', t):
            mo = max(players - st, 0) or None
    if mo is None and who_wdg:
        mo = _who_count(who_wdg.group(1))
        if st is None and not no_iem and re.search(_REST + _IEM + r'\b', t):
            st = max(players - mo, 0) or None
    if st is None and re.search(r'\b' + _IEM + r'\b', t) and not no_iem:
        st = players or None
    if mo is None and st is None and re.search(r'\bwedges\b', t) and not re.search(r'\bno wedges\b', t):
        mo = players or None
    if st or mo:
        out['mixes'] = {'stereo': min(st or 0, 16), 'mono': min(mo or 0, 16)}
        if st:
            said.append('%d IEM mix%s' % (out['mixes']['stereo'], '' if st == 1 else 'es'))
        if mo:
            said.append('%d wedge mix%s' % (out['mixes']['mono'], '' if mo == 1 else 'es'))
    kinds = []
    td = ' . '.join(c for c in re.split(r'[.;!?,()]|\b(?:and|but|while|whereas|plus)\b', t)
                    if not _OUTBOARD.search(c))
    td = ' %s ' % re.sub(r'\bslap(?:\s*-?\s*back)?(?:\s+delays?)?\b', 'slap', td)
    no_fx = re.search(r'\bno (?:fx|effects)\b|\bwithout (?:any )?(?:fx|effects)\b', t)
    no_rev = re.search(r'\bno (?:reverbs?|verbs?)\b|\bwithout (?:any |a )?(?:reverbs?|verbs?)\b', t)
    no_dly = re.search(r'\bno (?:delays?|slap(?:back)?s?)\b|\bwithout (?:any |a )?delays?\b', t)
    if not no_fx:
        for rx, k in FX_WORDS:
            if (no_rev and FX_CHOICES[k][3] in ('vocal', 'drum', 'hall')) or (no_dly and FX_CHOICES[k][3] == 'delay'):
                continue
            if re.search(rx, td) and k not in kinds:
                kinds.append(k)
        nd = re.search(r'\b' + _N + r'\s+delays\b', td)
        if nd and 'delay' in kinds:
            kinds += ['delay'] * max(0, min(_n(nd.group(1)), 4) - 1 - kinds.count('slap'))
        nr = re.search(r'\b' + _N + r'\s+(?:reverbs|verbs|reverb units)\b', td)
        want = 0 if no_rev else _n(nr.group(1)) if nr else (2 if re.search(r'\b(?:reverbs|verbs)\b', td) else
                                                         1 if re.search(r'\b(?:reverb|verb)\b', td) else 0)
        if re.search(r'\b(?:fx|effects)\b', td) and not want and not kinds:
            want, kinds = (0 if no_rev else 2), ([] if no_dly else ['delay'])
        have = sum(1 for k in kinds if FX_CHOICES[k][3] in ('vocal', 'drum', 'hall'))
        fill = ['hall'] if want == 1 and not have else ['vocal plate', 'room', 'hall', 'plate', 'drum plate']
        for k in fill:
            if have >= min(want, 4):
                break
            if k not in kinds:
                kinds.insert(have, k)
                have += 1
    if not kinds:
        for c in channels or []:
            cat, nm = c.get('category'), (c.get('full_name') or c.get('name') or '').lower()
            if cat == 'fx_reverb':
                k = 'vocal plate' if re.search(r'vox|vocal|plate', nm) else 'room' if re.search(
                    r'drum|room|snare|kit|tom', nm) else 'hall'
            elif cat == 'fx_delay':
                k = 'slap' if 'slap' in nm else 'delay'
            elif cat == 'fx_modulation':
                k = 'thicken' if re.search(r'vox|vocal|thick|doub', nm) else 'chorus'
            else:
                continue
            kinds.append(k)
        if kinds:
            said.append('FX from the return channels in your list')
    elif kinds:
        said.append(', '.join(FX_CHOICES[k][4].lower() for k in kinds[:MAX_FX]))
    if kinds:
        out['fx'] = [{'kind': k} for k in kinds[:MAX_FX]]
    if re.search(r'\bmonitor (?:desk|console|board|engineer|world|side)\b|\bmon (?:world|desk)\b|\bdoing monitors\b', t):
        out['role'] = 'mon'
        said.append('monitor mix')
    note = ('Options set from your description: %s. Change them under Options.' % '; '.join(said)) if said else None
    return out, note


def _io_facts(ses):
    racks, local = [], None
    for d in P.list_io(ses):
        if d['port'] is None or d['device_code'] not in P.PREAMP_DEVICES:
            continue
        outs = sum(1 for s in S.output_sockets(ses) if s['type'] == d['out_type']
                   and re.search(r'\bline\b', s['name'] or '', re.I))
        row = {'name': d['name'], 'device': d['device'], 'mics': d['mic_inputs'], 'line_outs': outs}
        if d['port'] == 0:
            local = row
        elif d['mic_inputs']:
            racks.append(row)
    return {'racks': racks, 'local': local}


def console_facts(refresh=False):
    """{key: {'buses': {aux_mono, aux_stereo, grp_mono, grp_stereo, limit}, 'fx_max': {'reverb', 'other'},
    'io': {build: {'racks': [{name, device, mics, line_outs}], 'local': {...}}}}} for the page, cached in
    baselines/options_facts.json (rebuilt for a default whose size or mtime changed)."""
    import sys
    tools = ROOT
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from ses import Session
    from . import consoles
    try:
        cache = json.load(open(FACTS_CACHE)) if not refresh else {}
    except (OSError, ValueError):
        cache = {}
    files = cache.get('files', {})
    facts = cache.get('facts', {})
    changed = False
    for key, c in consoles.CONSOLES.items():
        for build, path in sorted(c['versions'].items()):
            st = os.stat(path)
            stamp = '%d:%d' % (st.st_size, int(st.st_mtime))
            name = os.path.basename(path)
            f = facts.setdefault(key, {'io': {}})
            if files.get(name) == stamp and str(build) in f.get('io', {}) and 'buses' in f:
                continue
            data = open(path, 'rb').read()
            dsc = B.describe(data)
            f['buses'] = {'aux_mono': dsc['aux_mono'], 'aux_stereo': dsc['aux_stereo'], 'grp_mono': dsc['grp_mono'],
                          'grp_stereo': dsc['grp_stereo'], 'limit': B.bus_limit(data, key)}
            fam = c['family']
            f['fx_max'] = {'reverb': len(FX.engine_slots(fam, 'reverb')), 'other': len(FX.engine_slots(fam, 'delay'))}
            f.setdefault('io', {})[str(build)] = _io_facts(Session(data))
            files[name] = stamp
            changed = True
    if changed:
        tmp = FACTS_CACHE + '.part'
        with open(tmp, 'w') as fh:
            json.dump({'files': files, 'facts': facts}, fh, indent=0, sort_keys=True)
        os.replace(tmp, FACTS_CACHE)
    return facts


def choices():
    """FX choices for the page: [{'key', 'label', 'role'}]."""
    return [{'key': k, 'label': c[4], 'role': c[3]} for k, c in FX_CHOICES.items()]


if __name__ == '__main__':
    f = console_facts(refresh=True)
    print(json.dumps({k: {'buses': v['buses'], 'fx_max': v['fx_max'], 'builds': sorted(v['io'])} for k, v in f.items()},
                     indent=1))
