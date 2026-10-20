#!/usr/bin/env python3
"""edit.py - DiGiCo Lite: open any session as a readable model and change it with edit ops, by bytes.

    open_session(data, console_key=None) -> {'model': Model, 'warnings': [str]}
    apply_ops(data, ops, console_key=None) -> {'data': bytes, 'model': Model, 'changes': [str], 'warnings': [str],
                                              'refused': [{'op', 'why'}]}
    python3 -m sessionmaker.edit <in.ses> '<ops json>' [out.ses]          (from digico/scripts)

apply_ops is a pure function: the same bytes and ops give the same bytes. Ops run in order. An op that can not be
made on this session is refused with a plain sentence and leaves the file as it was before that op; the others
still run. validate.py (and, for routing ops, sends.route_errors / patch.patch_errors) must not find anything new
after an op, or the op is refused.

The writers are the Session Maker's own: ses.py (slots by (module, param, band), set_strip_view),
process.py (keys and the template writer), dlive2digico.py (put_comp, put_mustard), sends.py, patch.py, fx.py,
buses.py, layout.py (relayout for every structural op) and options.py (FX choices, mix plans, output picks).

Model = the Session Checker readout (sessionmaker/inspect.py) plus, per channel:
  id ('c<internal index>': stable across renames, moves, stereo flips and other channels coming and going),
  category / category_label / group (taxonomy.py on the name; FX returns from their patch), view ('sd' | 'mustard'),
  fx_return, and 'edit': every editable value with its on flag (hpf, lpf, eq bands 1-4, gate, comp, mustard, delay,
  polarity, trim, fader, mute, pan) in display units.
and a top-level 'edit' block: console_key, console_name, quantum, mustard_cap, structural (False when the session
has snapshots; structural_why says why), max_inputs, engine_room, sockets (the input sockets a patch op can name),
fx_kinds, groups (the group selector words).

Op = {'op': name, 'target': Selector, ...fields}. Fields of each op (display units: Hz, dB, ms):
  set          hpf / lpf: {'on', 'freq'} (or a number = on at that frequency, or a bool)
               eq: {'band' 1-4 (optional: picked by frequency), 'type' bell | low_shelf | high_shelf, 'freq',
                    'gain', 'q', 'on'} or a list of them, or {'flat': True}; eq_on: bool
               gate: {'on', 'thr', 'range', 'attack', 'hold', 'release'}
               comp: {'on', 'thr', 'ratio', 'attack', 'release', 'knee', 'makeup'}
               mustard: {'on', 'model' classic | vca | fet | optical | levamp, 'thr', 'ratio', 'attack', 'release',
                         'out', 'mix', 'knee', 'sd_comp'}
               delay_ms, polarity, trim_db, fader_db, mute, pan (-1..1), view ('sd' | 'mustard'), name
               The fields may sit on the op itself or in op['fields'].
               Mustard on a selection: Quantum only, within the console's instance cap (a stereo channel uses 2),
               best candidates first (process.MUSTARD_PRIORITY by category, then channel order). Channels that miss
               out are named in the warnings and keep their SD comp. Where Mustard takes over, the SD comp goes off
               and the strip opens on the M view. Settings: the op's, else the channel's SD comp (when it is on),
               else the category template's Mustard comp, else Classic -20 dB 3:1. 'mustard': {'on': False} turns the
               Mustard comp off and puts its settings back on the SD comp (sd_comp False skips that).
  rename       {'name'} for one channel, or {'names': [...]} in target order. 8 characters on the console.
  stereo       {'stereo': True | False}. Two adjacent mono channels with stereo True become ONE stereo channel
               (the first keeps its processing, sends and patch; its name loses the L/R; the second goes), unless
               'pair': False. 'split': True turns a stereo channel into L and R mono channels.
  move         {'to': n} (the first moved channel lands at surface n) or {'after': n} or {'before': n}.
  add_channels {'count', 'names' or 'name', 'stereo', 'after' (default: after the last), 'category' ('auto' writes
               the category template of each name)}
  remove_channels  target only.
  apply_template   {'category' (id, or 'auto' = from the name), 'role' foh | mon}
  send         {'aux' (number or bus name), 'level_db', 'pre' (bool or post | pre | pre-mute | ...), 'pan', 'on'}
  patch        {'socket': 'Rack 1:5' | 'Local 3' | 'MADI 12' | '1:Mic 5' | {'device', 'number'}, 'alt', 'use_alt',
               'unpatch', 'keep_preamp' (default True: gain, 48V and pad follow the channel to a free socket)}.
               Several channels take consecutive sockets (a stereo channel takes 2).
  preamp       {'gain_db', 'phantom', 'pad'} on the channel's socket(s).
  add_fx       {'kind' (options.FX_CHOICES or a factory preset name), 'aux' (feed; default the first free mono
               aux), 'return' ('new' | 'none' | channel number), 'name', 'sends' ('auto' | 'none')}
  remove_fx    {'unit': rack number} or {'name'}; 'remove_return': also remove its return channel(s).
  mixes        {'stereo' IEM count, 'mono' wedge count, 'click' all | drums | none, 'outputs', 'names'}
  buses        {'aux_mono', 'aux_stereo', 'grp_mono', 'grp_stereo'}
  name_bus     {'kind' aux | group | matrix, 'n', 'name'}

Selector = {'all': True} | {'channels': [n]} | {'range': [a, b]} | {'category': [ids]} | {'group': word}
  | {'name': regex} | {'ids': ['c12']} | {'stereo': bool}; several keys in one dict combine with 'and';
  {'except': Selector} removes channels, {'or': [Selector, ...]} unites. Group words: GROUPS below.

Structural ops (stereo, move, add_channels, remove_channels, a new FX return channel, mixes or buses that need a
new bus layout) go through layout.relayout / buses.restructure, which keep every channel's processing, name, sends
and patch on its internal index. They are refused on sessions with snapshots: each snapshot holds its own copy of
every channel, and those copies would be left in the old layout.
"""
import json
import os
import re
import struct
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ROOT  # ses.py and dlive2digico.py sit next to this package
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from ses import Channel, Record, Session  # noqa: E402
import dlive2digico as d2d  # noqa: E402

from . import buses as B  # noqa: E402
from . import consoles, layout, process, taxonomy, validate  # noqa: E402
from . import fx as FX  # noqa: E402
from . import inspect as I  # noqa: E402
from . import options as O  # noqa: E402
from . import patch as P  # noqa: E402
from . import sends as S  # noqa: E402

NAME_MAX = 8


class Refuse(Exception):
    """An op that can not be made, with the plain sentence that says why."""


def _sentence(e):
    """A writer's error as a sentence: first letter up, one full stop."""
    s = re.sub(r'\s+', ' ', str(e)).strip().strip("'\"")
    if not s:
        return 'That change could not be made on this session.'
    s = s[:1].upper() + s[1:]
    return s if s.endswith(('.', '!', '?')) else s + '.'


# ---------------------------------------------------------------------------------------------------- the session
_KEYS = None


def _keys_json():
    global _KEYS
    if _KEYS is None:
        try:
            with open(os.path.join(TOOLS, 'keys_from_offsets.json')) as f:
                _KEYS = json.load(f)
        except (OSError, ValueError):
            _KEYS = {}
    return _KEYS


class LiveSession(Session):
    """ses.Session that parses only the live objects (section 211) and the channel list (201), walked by structure
    with the Session Checker's reader. ses.Session scans the whole file for module records (snapshots and the preset
    library too), about 1.2 s on a 28 MB show; this takes a fraction of that. records holds the live input and Spice
    Rack records only; _name_bus swaps in the copies a bus rename needs."""

    def __init__(self, data):  # noqa: D107 - same contract as Session, bytes only
        self.d = bytearray(data)
        self.keys = _keys_json()
        self._parse()

    def _parse(self):
        d = self.d
        if hasattr(self, '_sends_objs'):
            del self._sends_objs            # sends.objects() caches by file length; a move keeps the length
        span = self.section_span(211)
        if span is None:
            raise Refuse('This session has no channel data, so it can not be edited.')
        try:
            objs = I._walk_211(d, span, I._Clock(30.0))
        except I.Stop as e:
            raise Refuse(e.msg)
        self.records, self.inputs = [], []
        for o in objs:
            if o['type'] == 0x01:
                recs = [Record(d, r) for r in o['recs']]
                self.records.extend(recs)
                if recs:
                    self.inputs.append(Channel(o['index'] + 1, recs, o['trailer']))
            elif o['type'] == 0x18:
                self.records.extend(Record(d, r) for r in o['recs'])
        self.records.sort(key=lambda r: r.off)
        self.snapshot_inputs = []
        self.inputs.sort(key=lambda c: c.index)
        self.by_index = {c.index: c for c in self.inputs}
        self._parse_201()


def _records_named(ses, names):
    """Every module record in the file (live, snapshot or library copy) whose name field is one of `names`, in file
    order. sends._rename_object walks ses.records for the copies of a bus; only records carrying its name matter."""
    out = {}
    for nm in names:
        try:
            nb = nm.encode('latin1')
        except UnicodeEncodeError:
            continue
        if len(nb) > 31:
            continue
        pat = re.compile(re.escape(layout.REC) + b'..\x00\x00' + re.escape(bytes([len(nb)]) + nb), re.S)
        for m in pat.finditer(ses.d):
            p = m.start()
            if p not in out and Record.valid(ses.d, p):
                out[p] = Record(ses.d, p)
    return [out[p] for p in sorted(out)]


# ---------------------------------------------------------------------------------------------------- categories
def _group_sets():
    t = taxonomy._templates()['groups']
    g = {k: set(v) for k, v in t.items()}
    return {
        'vocals': g['vocals'], 'drums': g['drums'], 'toms': {'rack_tom', 'floor_tom', 'roto_tom'},
        'kick': {'kick_in', 'kick_out', 'kick_sub'}, 'snare': {'snare_top', 'snare_bottom'},
        'overheads': {'overheads'}, 'cymbals': {'overheads', 'hihat', 'ride'}, 'bass': g['bass'],
        'guitars': {'electric_guitar', 'acoustic_guitar', 'folk_strings'}, 'keys': g['keys'],
        'tracks': {'tracks_music', 'tracks_drums_perc', 'tracks_bass', 'tracks_vocals'},
        'playback': g['playback'], 'talkback': g['comms'], 'fx_returns': g['fx_returns'],
        'strings': {'strings', 'folk_strings'}, 'horns': {'horns'}, 'ambience': g['ambience'],
    }


GROUPS = None
GROUP_ALIASES = {'vocal': 'vocals', 'vox': 'vocals', 'voices': 'vocals', 'drum': 'drums', 'kit': 'drums',
                 'tom': 'toms', 'kicks': 'kick', 'snares': 'snare', 'oh': 'overheads', 'ohs': 'overheads',
                 'guitar': 'guitars', 'gtrs': 'guitars', 'gtr': 'guitars', 'key': 'keys', 'keyboards': 'keys',
                 'track': 'tracks', 'stems': 'tracks', 'tb': 'talkback', 'comms': 'talkback', 'fx': 'fx_returns',
                 'returns': 'fx_returns', 'fx returns': 'fx_returns', 'fx_return': 'fx_returns'}


def _groups():
    global GROUPS
    if GROUPS is None:
        GROUPS = _group_sets()
    return GROUPS


FX_WORDS = [(re.compile(r'(?i)dly|delay|echo|slap|tap'), 'fx_delay'),
            (re.compile(r'(?i)chor|thick|doub|pitch|oct|flang|phas|mod'), 'fx_modulation'),
            (re.compile(r'(?i)verb|hall|plate|room|rev|amb|chamb|spring|gate'), 'fx_reverb')]


def _categorize(name, stereo=False):
    """taxonomy.rule_category on a console name. 8-character names lose their spaces ("SnareTop", "FloorTom"); when
    the rules are unsure of the name as written (< 0.6), the camel-case split reading wins if the rules are sure of
    it. Over the 908 names in the real sessions this changes no sure reading."""
    try:
        c, p, _ = taxonomy.rule_category(name, stereo=stereo)
        if p < 0.6:
            sp = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
            sp = re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])', ' ', sp)
            if sp != name:
                c2, p2, _ = taxonomy.rule_category(sp, stereo=stereo)
                if p2 >= 0.6:
                    return c2
        return c
    except Exception:  # noqa: BLE001 - a name the rules choke on is just 'other'
        return 'other'


# ---------------------------------------------------------------------------------------------------- the state
def _resolve_key(d, want=None):
    """(console key, note or None) for the file: the family code, the Pulse bit and the fixed header counts decide
    (inspect._models); `want` picks between the keys the file loads on."""
    code = bytes(d[11:15]).decode('latin1').strip()
    fam = I.FAMILY.get(code, ([], None))[0]
    made, loads = I._models(code, d, fam)
    if not made:
        return None, None
    if want:
        w = str(want).strip().lower()
        if w in made or w in loads:
            return w, None
        name = (consoles.CONSOLES.get(w) or {}).get('name', w)
        return made[0], 'This file is a %s session, not one for the %s, so it is edited as a %s session.' % (
            consoles.CONSOLES.get(made[0], {}).get('name', made[0]), name,
            consoles.CONSOLES.get(made[0], {}).get('name', made[0]))
    return made[0], None


class _State:
    def __init__(self, data, console_key=None):
        d = bytes(data)
        hdr = I._header(d) if d else None
        if not hdr:
            raise Refuse('The file is empty.')
        self.key, self.key_note = _resolve_key(d, console_key)
        if self.key is None or self.key not in consoles.CONSOLES:
            raise Refuse("We could not tell which console this file is for, so it can not be edited.")
        self.console = consoles.CONSOLES[self.key]
        self.ses = LiveSession(d)
        self.family = self.ses.model
        self.quantum = self.family in layout.QUANTUM_FAMILIES
        self.cap = self.console.get('mustard_cap') if self.quantum else None
        sp = self.ses.section_span(210)
        self.snapshots = I._snapshots(d, sp) if sp else 0
        self.warnings = []
        self._cat = {}
        self._base = None
        self.structural = False             # set by ops that change the layout (validate runs after them)
        self.routing = False                # set by ops that change patch or bus routing

    # -- bytes ----------------------------------------------------------------------------------------------------
    def data(self):
        return bytes(self.ses.d)

    def reload(self, data):
        self.ses = LiveSession(data)

    def warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)

    # -- channels ---------------------------------------------------------------------------------------------------
    def numbers(self):
        return sorted(self.ses.display)

    def idx(self, n):
        return self.ses.display[n]

    def name(self, n):
        return self.ses.by_index[self.idx(n)].name

    def width(self, n):
        return self.ses.width.get(n, 1)

    def label(self, n):
        return '%d %s' % (n, self.name(n).strip() or '(no name)')

    def fx_unit_of(self, n):
        """FX unit index (0-based id byte) whose return this channel's main input is, else None."""
        c = self.ses.by_index[self.idx(n)]
        rec = c.records.get(0x01)
        q = rec.slots.get((0x00, 0)) if rec else None
        if q is None:
            return None
        raw = bytes(self.ses.d[q:q + 4])
        return raw[2] if raw[0] == 0 and raw[3] == FX.FX_TYPE else None

    def cat(self, n):
        """Template category of surface channel n from its name (taxonomy.py); FX returns from their patch."""
        idx, nm, w = self.idx(n), self.name(n), self.width(n)
        fxu = self.fx_unit_of(n)
        k = (idx, nm, w, fxu)
        hit = self._cat.get(idx)
        if hit and hit[0] == k:
            return hit[1]
        c = _categorize(nm, w == 2)
        if fxu is not None and c not in _groups()['fx_returns']:
            c = next((cat for rx, cat in FX_WORDS if rx.search(nm)), 'fx_other')
        self._cat[idx] = (k, c)
        return c

    def mustard_uses(self, n):
        """True when channel n holds a Mustard instance: any Mustard module on, or the editor's own allocation."""
        idx = self.idx(n)
        c = self.ses.by_index[idx]
        for mod in I.MUSTARD_MODS:
            r = c.records.get(mod)
            if r is not None and (0x02, 0) in r.slots and self.ses.get(idx, mod, 0x02, 0) == 1.0:
                return True
        off = self.ses.chrec_off.get(idx)
        if off is not None and self.ses.d[off + 2] >= 0x58:
            return struct.unpack_from('<h', self.ses.d, off + 86)[0] >= 0
        return False

    def mustard_used(self):
        return sum(self.width(n) for n in self.numbers() if self.mustard_uses(n))

    # -- the console's default channel (for new channels and "is this value still the default?") -----------------
    def base(self):
        """{(module, param, band): raw 4 bytes} of a pristine input channel of this console and build (the editor's
        default session in baselines, nearest build when this one is missing), plus its master band and
        first aux / group bands. None when no default session of the family exists."""
        if self._base is None:
            self._base = False
            path = None
            vers = self.console.get('versions') or {}
            if vers:
                b = min(vers, key=lambda v: (abs(v - self.ses.version), -v))
                path = vers[b]
            if path and os.path.exists(path):
                try:
                    dd = open(path, 'rb').read()
                    c = layout.Container(dd)
                    objs, _ = layout.objects(c.sec(211)[1])
                    ins = [o for o in objs if layout.obj_id(o) >> 8 == 1]
                    o = layout.default_object(ins)
                    vals = {}
                    for p, typ, cnt in layout.obj_records(o):
                        for k in range(cnt):
                            q = p + 0x3e + 8 * k
                            vals.setdefault((typ, o[q], o[q + 2]), bytes(o[q + 4:q + 8]))
                    bs = Session(dd)
                    self._base = {'vals': vals, 'master': dd[S.MASTER_ID_AT],
                                  'aux0': bs.auxes[0]['band'] if bs.auxes else 0,
                                  'grp_other': next((g['band'] for g in bs.groups if g['band'] != dd[S.MASTER_ID_AT]),
                                                    None), 'build': bs.version}
                except Exception:  # noqa: BLE001 - no default: new channels stay clones, defaults stay unknown
                    self._base = False
        return self._base or None

    def is_default(self, n, key):
        """True when slot `key` of channel n still holds the console default value (so the engineer never set it)."""
        b = self.base()
        if not b or key not in b['vals']:
            return False
        idx = self.idx(n)
        if not self.ses.has_slot(idx, *key):
            return False
        q = self.ses.slot(idx, *key)
        return bytes(self.ses.d[q:q + 4]) == b['vals'][key]


# ---------------------------------------------------------------------------------------------------- selectors
def _ints(v, what='channel'):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return [int(v)]
    if isinstance(v, str):
        out = []
        for part in re.split(r'[,\s]+', v.strip()):
            if not part:
                continue
            m = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                out += list(range(min(a, b), max(a, b) + 1))
            elif part.isdigit():
                out.append(int(part))
            else:
                raise Refuse('%r is not a %s number.' % (part, what))
        return out
    if isinstance(v, (list, tuple)):
        out = []
        for x in v:
            out += _ints(x, what)
        return out
    raise Refuse('Channel numbers must be numbers.')


def _select(st, sel):
    """Surface channel numbers (in surface order) a selector names. Never invents channels."""
    allns = st.numbers()
    have = set(allns)
    if sel is None or sel == {} or sel == []:
        raise Refuse('Say which channels to change.')
    if sel in ('all', '*', True):
        return list(allns)
    if isinstance(sel, (int, float, list, tuple)) and not isinstance(sel, bool) and not (
            isinstance(sel, list) and sel and isinstance(sel[0], dict)):
        sel = {'channels': sel}
    if isinstance(sel, str):
        if sel.strip().lower() in _groups() or sel.strip().lower() in GROUP_ALIASES:
            sel = {'group': sel}
        else:
            sel = {'channels': sel}
    if isinstance(sel, list):
        sel = {'or': sel}
    if not isinstance(sel, dict):
        raise Refuse('That channel selection is not one I can read.')
    cur = list(allns)
    known = {'all', 'channels', 'range', 'category', 'group', 'name', 'ids', 'except', 'or', 'stereo', 'mono'}
    bad = [k for k in sel if k not in known]
    if bad:
        raise Refuse('I do not know the channel selector %r.' % bad[0])
    if 'or' in sel:
        parts = sel['or'] if isinstance(sel['or'], list) else [sel['or']]
        u = set()
        for p in parts:
            u |= set(_select(st, p))
        cur = [n for n in cur if n in u]
    if sel.get('all') is False:
        cur = []
    if 'channels' in sel:
        want = _ints(sel['channels'])
        miss = [n for n in want if n not in have]
        if miss:
            raise Refuse('This session has %d channels, so there is no channel %s.' % (len(allns), _nums(miss)))
        ws = set(want)
        cur = [n for n in cur if n in ws]
    if 'range' in sel:
        r = _ints(sel['range'])
        if len(r) != 2:
            raise Refuse('A channel range needs a first and a last channel.')
        a, b = min(r), max(r)
        if a not in have or b not in have:
            raise Refuse('This session has channels 1 to %d, so %d to %d is out of range.' % (len(allns), a, b))
        cur = [n for n in cur if a <= n <= b]
    if 'category' in sel:
        cats = sel['category'] if isinstance(sel['category'], (list, tuple, set)) else [sel['category']]
        cats = {str(c) for c in cats}
        cur = [n for n in cur if st.cat(n) in cats]
    if 'group' in sel:
        gs = sel['group'] if isinstance(sel['group'], (list, tuple)) else [sel['group']]
        keep = set()
        for g in gs:
            w = GROUP_ALIASES.get(str(g).strip().lower(), str(g).strip().lower())
            if w == 'mono':
                keep |= {n for n in cur if st.width(n) == 1}
            elif w == 'stereo':
                keep |= {n for n in cur if st.width(n) == 2}
            elif w in _groups():
                cats = _groups()[w]
                keep |= {n for n in cur if st.cat(n) in cats or (w == 'fx_returns' and st.fx_unit_of(n) is not None)}
            else:
                raise Refuse('I do not know the channel group %r. Try one of: %s.' % (g, ', '.join(sorted(_groups()))))
        cur = [n for n in cur if n in keep]
    if 'stereo' in sel or 'mono' in sel:
        want_st = bool(sel['stereo']) if 'stereo' in sel else not bool(sel['mono'])
        cur = [n for n in cur if (st.width(n) == 2) == want_st]
    if 'name' in sel:
        try:
            rx = re.compile(str(sel['name']), re.I)
        except re.error:
            rx = re.compile(re.escape(str(sel['name'])), re.I)
        cur = [n for n in cur if rx.search(st.name(n))]
    if 'ids' in sel:
        ids = sel['ids'] if isinstance(sel['ids'], (list, tuple)) else [sel['ids']]
        want = set()
        for x in ids:
            m = re.match(r'^c?(\d+)$', str(x).strip())
            if not m:
                raise Refuse('%r is not a channel id.' % (x,))
            want.add(int(m.group(1)))
        missing = want - set(st.ses.by_index)
        if missing:
            raise Refuse('Channel id c%d is not in this session any more.' % min(missing))
        cur = [n for n in cur if st.idx(n) in want]
    if 'except' in sel:
        drop = set(_select_soft(st, sel['except']))
        cur = [n for n in cur if n not in drop]
    return cur


def _select_soft(st, sel):
    try:
        return _select(st, sel)
    except Refuse:
        return []


def _targets(st, op, need=True):
    ns = _select(st, op.get('target', op.get('channels')))
    if need and not ns:
        raise Refuse('No channel in this session matches %s.' % _describe_sel(op.get('target')))
    return ns


def _describe_sel(sel):
    if isinstance(sel, dict):
        if sel.get('group'):
            return 'the %s' % (sel['group'] if isinstance(sel['group'], str) else ', '.join(sel['group']))
        if sel.get('category'):
            c = sel['category']
            return 'the category %s' % (c if isinstance(c, str) else ', '.join(c))
        if sel.get('name'):
            return 'the name %r' % sel['name']
    return 'that selection'


def _nums(ns):
    ns = sorted(set(ns))
    out, i = [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append('%d' % ns[i] if i == j else '%d-%d' % (ns[i], ns[j]))
        i = j + 1
    if len(out) > 1:
        return ', '.join(out[:-1]) + ' and ' + out[-1]
    return out[0] if out else ''


def _who(st, ns, limit=6):
    """'5 Vox 1, 6 Vox 2 and 7 BGV' or '12 channels (5-16)'."""
    ns = list(ns)
    if not ns:
        return 'no channels'
    if len(ns) <= limit:
        labs = [st.label(n) for n in ns]
        return labs[0] if len(labs) == 1 else ', '.join(labs[:-1]) + ' and ' + labs[-1]
    return '%d channels (%s)' % (len(ns), _nums(ns))


# ---------------------------------------------------------------------------------------------------- reading values
K = None


def _k():
    global K
    if K is None:
        K = process.keys()
    return K


def _get(st, idx, key):
    return st.ses.get(idx, *key) if st.ses.has_slot(idx, *key) else None


def _put(st, idx, key, value):
    if not st.ses.has_slot(idx, *key):
        raise Refuse('Channel %d has no %02x/%02x/%d setting in this file.' % (
            next((n for n, i in st.ses.display.items() if i == idx), idx), key[0], key[1], key[2]))
    st.ses.set(idx, key[0], key[1], key[2], value)


def _r(x, nd=1):
    if x is None or x != x or x in (float('inf'), float('-inf')):
        return None
    return round(float(x), nd)


def _ms(x, nd=2):
    return None if x is None else _r(x * 1000.0, nd)


COMP = {'on': d2d.C_IN, 'mode': d2d.C_MODE, 'thr': d2d.C_THR, 'ratio': d2d.C_RATIO, 'attack': d2d.C_ATK,
        'release': d2d.C_REL, 'knee': d2d.C_KNEE, 'makeup': d2d.C_MK}
MC = {'on': d2d.MC_ON, 'model': d2d.MC_TYPE, 'thr': d2d.MC_THR, 'ratio': d2d.MC_RATIO, 'attack': d2d.MC_ATK,
      'release': d2d.MC_REL, 'knee': d2d.MC_KNEE, 'mix': d2d.MC_MIX, 'out': d2d.MC_OUT}
FADER, PAN, TRIM = (0x0c, 0x21, 0), (0x0d, 0x23, 0), (0x01, 0x01, 0)
MUTE = (0x0c, 0x22, 0)


def _edit_params(st, idx):
    """Every value the editor's inspector can change on internal channel idx, display units, with on flags."""
    k = _k()
    g = lambda key: _get(st, idx, key)  # noqa: E731
    out = {}
    hf, lf = g(k['hpf_f']), g(k['lpf_f'])
    out['hpf'] = {'on': g(k['hpf_in']) == 1.0, 'freq': _r(hf * process.HPF_PER if hf is not None else None)}
    out['lpf'] = {'on': g(k['lpf_in']) == 1.0, 'freq': _r(lf * process.LPF_PER if lf is not None else None)}
    out['eq_on'] = g(k['eq_in']) == 1.0
    m = k['eq']
    bands = []
    for n in (1, 2, 3, 4):
        bb = 4 - n
        shape = g((m['shape'][0], m['shape'][1], bb))
        bands.append({'band': n, 'on': g((m['on'][0], m['on'][1], bb)) == 1.0,
                      'type': process.SHAPE_NAMES.get(int(shape), 'bell') if shape is not None else None,
                      'freq': _r(g((m['freq'][0], m['freq'][1], bb))), 'gain': _r(g((m['gain'][0], m['gain'][1], bb))),
                      'q': _r(g((m['q'][0], m['q'][1], bb)), 2)})
    out['eq'] = bands
    D = k['dyn2']
    mode = g(D['mode'])
    out['gate'] = {'on': g(D['in']) == 1.0, 'mode': process.DYN2_MODES.get(int(mode), 'gate') if mode is not None else None,
                   'thr': _r(g(D['thr'])), 'range': _r(g(D['range'])), 'attack': _ms(g(D['atk'])),
                   'hold': _ms(g(D['hold']), 1), 'release': _ms(g(D['rel']), 1), 'ratio': _r(g(D['ratio']), 2)}
    c = lambda p: g((0x05, p, 0))  # noqa: E731
    cm, kn = c(d2d.C_MODE), c(d2d.C_KNEE)
    out['comp'] = {'on': c(d2d.C_IN) == 1.0, 'mode': process.COMP_MODES.get(int(cm), 'comp') if cm is not None else None,
                   'thr': _r(c(d2d.C_THR)), 'ratio': _r(c(d2d.C_RATIO), 2), 'attack': _ms(c(d2d.C_ATK)),
                   'release': _ms(c(d2d.C_REL), 1), 'knee': process.KNEE_NAMES.get(int(kn), 'hard') if kn is not None
                   else None, 'makeup': _r(c(d2d.C_MK))}
    if st.ses.has_module(d2d.MC, idx):
        mc = lambda p: g((d2d.MC, p, 0))  # noqa: E731
        mt = mc(d2d.MC_TYPE)
        out['mustard'] = {'on': mc(d2d.MC_ON) == 1.0,
                          'model': process.MUSTARD_MODELS.get(mt, 'classic') if mt is not None else None,
                          'thr': _r(mc(d2d.MC_THR)), 'ratio': _r(mc(d2d.MC_RATIO), 2), 'attack': _ms(mc(d2d.MC_ATK)),
                          'release': _ms(mc(d2d.MC_REL), 1), 'knee': 'hard' if mc(d2d.MC_KNEE) == 1.0 else 'soft',
                          'mix': _r(mc(d2d.MC_MIX), 2), 'out': _r(mc(d2d.MC_OUT))}
    else:
        out['mustard'] = None
    dl = g(k['delay'])
    out['delay'] = {'on': g(k['delay_on']) == 1.0, 'ms': _ms(dl)}
    pol = g(k['polarity'])
    out['polarity'] = bool(pol) if pol is not None else None
    out['trim_db'] = _r(g(TRIM))
    out['fader_db'] = _r(g(FADER))
    mu = g(MUTE)
    out['mute'] = None if mu is None else mu == 1.0
    out['pan'] = _r(g(PAN), 2)
    return out


def _views(ses):
    """{internal index: view byte} from the surface banks (first strip that holds the channel)."""
    out = {}
    try:
        for b in ses.banks():
            for j, (typ, i) in enumerate(b['strips']):
                if typ == ses.STRIP_INPUT and i + 1 not in out:
                    out[i + 1] = ses.d[b['view'] + j]
    except (ValueError, struct.error, IndexError):
        pass
    return out


# ---------------------------------------------------------------------------------------------------- the model
def _model(st):
    d = st.data()
    r = I.inspect(d)
    if not r.get('ok'):
        raise Refuse(r.get('error') or 'This session can not be read.')
    views = _views(st.ses)
    grp = taxonomy.groups()
    labels = taxonomy.labels()
    for ch in r['channels']:
        n, idx = ch['n'], ch['idx']
        ch['id'] = 'c%d' % idx
        if n not in st.ses.display or st.ses.display[n] != idx:
            continue
        cat = st.cat(n)
        ch['category'] = cat
        ch['category_label'] = labels.get(cat, cat)
        ch['group'] = grp.get(cat, 'other')
        ch['view'] = 'mustard' if views.get(idx) == st.ses.VIEW_MUSTARD else 'sd'
        ch['fx_return'] = st.fx_unit_of(n) is not None
        try:
            ch['edit'] = _edit_params(st, idx)
        except (KeyError, struct.error, Refuse):
            ch['edit'] = None
    if r.get('mustard') is not None and st.cap:
        r['mustard']['cap'] = st.cap
        r['mustard']['cap_verified'] = bool(st.console.get('mustard_cap_verified'))
    socks = []
    try:
        for s in P.input_sockets(st.ses):
            socks.append({'ref': '%s:%d' % (s['group'], s['number']), 'name': s['name'], 'group': s['group'],
                          'number': s['number'], 'device': s['device'],
                          'mic': bool(re.search(r'\bmic\b', s['name'] or '', re.I))})
    except (ValueError, KeyError, struct.error):
        pass
    room = None
    try:
        er = layout.engine_room(d)
        room = er['room'] if er else None
    except (ValueError, StopIteration, struct.error):
        pass
    r['console_key'] = st.key
    r['edit'] = {'console_key': st.key, 'console_name': st.console['name'], 'quantum': st.quantum,
                 'mustard_cap': st.cap, 'structural': not st.snapshots,
                 'structural_why': None if not st.snapshots else _snap_why(st),
                 'max_inputs': min(st.console['max_inputs'], layout.MAX_INPUT_IDS), 'engine_room': room,
                 'engine_used': sum(st.width(n) for n in st.numbers()),
                 'sockets': socks, 'fx_kinds': [{'kind': k, 'label': v[4]} for k, v in O.FX_CHOICES.items()],
                 'groups': sorted(_groups()) + ['mono', 'stereo']}
    return I._finite(r)


def _snap_why(st):
    return ('This session has %d snapshot%s, and each one keeps its own copy of every channel. Adding, removing, '
            'moving or pairing channels here would leave those copies behind, so do that on the console (Session '
            'Structure). Processing, names, sends and patch edits work.' % (st.snapshots,
                                                                            '' if st.snapshots == 1 else 's'))


# ---------------------------------------------------------------------------------------------------- 'set'
SET_ORDER = ('name', 'hpf', 'lpf', 'eq_on', 'eq', 'gate', 'comp', 'mustard', 'delay_ms', 'polarity', 'trim_db',
             'fader_db', 'mute', 'pan', 'view')
ALIASES = {'threshold': 'thr', 'threshold_db': 'thr', 'thr_db': 'thr', 'attack_ms': 'attack', 'release_ms': 'release',
           'hold_ms': 'hold', 'range_db': 'range', 'makeup_db': 'makeup', 'output': 'out', 'output_db': 'out',
           'out_db': 'out', 'gain_db': 'gain', 'freq_hz': 'freq', 'frequency': 'freq', 'hz': 'freq', 'shape': 'type',
           'in': 'on', 'enabled': 'on', 'enable': 'on'}


def _norm(v):
    """A sub-field value as a dict with canonical keys. A bool is {'on'}; a number is {'on': True, 'value'}."""
    if isinstance(v, bool):
        return {'on': v}
    if isinstance(v, (int, float)):
        return {'on': True, 'value': float(v)}
    if isinstance(v, str) and v.strip().lower() in ('on', 'off', 'in', 'out', 'bypass'):
        return {'on': v.strip().lower() in ('on', 'in')}
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise Refuse('%r is not a setting I can read.' % (v,))
    out = {}
    for key, x in v.items():
        out[ALIASES.get(key, key)] = x
    return out


def _num(v, what, lo=None, hi=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise Refuse('%s must be a number.' % what)
    if x != x or x in (float('inf'), float('-inf')):
        raise Refuse('%s must be a number.' % what)
    if lo is not None and hi is not None:
        x = max(lo, min(hi, x))
    return x


def _tpl(st, n, part):
    """The category template's block `part` for channel n (or {})."""
    tpl, _ = process.resolve(st.cat(n))
    return (tpl or {}).get(part) or {}


def _op_set(st, op):
    f = {}
    for key in ('fields', 'set', 'values'):
        if isinstance(op.get(key), dict):
            f.update(op[key])
    for key in SET_ORDER:
        if key in op:
            f[key] = op[key]
    if 'eq_in' in f and 'eq_on' not in f:
        f['eq_on'] = f.pop('eq_in')
    unknown = [k for k in f if k not in SET_ORDER]
    if unknown:
        raise Refuse('I can not set %r on a channel. I can set %s.' % (unknown[0], ', '.join(SET_ORDER)))
    if not f:
        raise Refuse('Say what to set: HPF, LPF, EQ, gate, comp, Mustard, delay, polarity, trim, fader, mute or pan.')
    ns = _targets(st, op)
    out = []
    for key in SET_ORDER:
        if key in f:
            out += SETTERS[key](st, ns, f[key])
    return out


def _set_name(st, ns, v):
    return _op_rename(st, {'target': {'channels': ns}, 'name': v} if len(ns) == 1 else
                      {'target': {'channels': ns}, 'names': v})


def _set_filter(which):
    def run(st, ns, v):
        k = _k()
        kin, kf, per = ((k['hpf_in'], k['hpf_f'], process.HPF_PER) if which == 'hpf'
                        else (k['lpf_in'], k['lpf_f'], process.LPF_PER))
        f = _norm(v)
        freq = f.get('freq', f.get('value'))
        on = f.get('on', True if freq is not None else None)
        if on is None:
            raise Refuse('Say a frequency or on/off for the %s.' % which.upper())
        if freq is not None:
            freq = _num(freq, 'The %s frequency' % which.upper())
            if not 20.0 <= freq <= 20000.0:
                raise Refuse('The %s frequency must be 20 Hz to 20 kHz.' % which.upper())
        used = {}
        for n in ns:
            idx = st.idx(n)
            fq = freq
            if on and fq is None and st.is_default(n, kf):
                t = _tpl(st, n, which)
                fq = float(t['freq_hz']) if t.get('freq_hz') else (100.0 if which == 'hpf' else 12000.0)
            if fq is not None:
                _put(st, idx, kf, fq / per)
            _put(st, idx, kin, 1.0 if on else 0.0)
            used[n] = fq if fq is not None else (_get(st, idx, kf) or 0) * per
        if not on:
            return ['%s out on %s.' % (which.upper(), _who(st, ns))]
        if freq is not None:
            return ['%s at %s on %s.' % (which.upper(), _hz(freq), _who(st, ns))]
        return ['%s in on %s (%s).' % (which.upper(), _who(st, ns), _vals(st, used, _hz))]
    return run


def _hz(f):
    return ('%.3g kHz' % (f / 1000.0)) if f >= 1000 else '%d Hz' % round(f)


def _vals(st, by_n, fmt):
    """'120 Hz on all' or '5 at 120 Hz, 6 at 140 Hz'."""
    vs = {fmt(v) for v in by_n.values()}
    if len(vs) == 1:
        return vs.pop()
    items = list(by_n.items())
    s = ', '.join('%d at %s' % (n, fmt(v)) for n, v in items[:6])
    return s + (', ...' if len(items) > 6 else '')


def _set_eq_on(st, ns, v):
    on = _norm(v).get('on', bool(v))
    for n in ns:
        _put(st, st.idx(n), _k()['eq_in'], 1.0 if on else 0.0)
    return ['EQ %s on %s.' % ('in' if on else 'out', _who(st, ns))]


EQ_TYPES = {'bell': 'bell', 'peak': 'bell', 'peaking': 'bell', 'parametric': 'bell', 'param': 'bell',
            'low_shelf': 'low_shelf', 'lowshelf': 'low_shelf', 'low shelf': 'low_shelf', 'ls': 'low_shelf',
            'lo_shelf': 'low_shelf', 'lf_shelf': 'low_shelf', 'high_shelf': 'high_shelf', 'highshelf': 'high_shelf',
            'high shelf': 'high_shelf', 'hs': 'high_shelf', 'hi_shelf': 'high_shelf', 'hf_shelf': 'high_shelf'}
BAND_CENTRE = {1: 100.0, 2: 500.0, 3: 2500.0, 4: 8000.0}


def _band_state(st, idx, n):
    m, bb = _k()['eq'], 4 - n
    g = lambda f: _get(st, idx, (m[f][0], m[f][1], bb))  # noqa: E731
    return {'on': g('on') == 1.0, 'gain': g('gain') or 0.0, 'freq': g('freq') or BAND_CENTRE[n],
            'shape': process.SHAPE_NAMES.get(int(g('shape') or 1), 'bell')}


def _pick_band(st, idx, typ, freq):
    import math
    if typ == 'low_shelf':
        return 1 if not (_band_state(st, idx, 1)['on'] and _band_state(st, idx, 1)['shape'] != 'low_shelf'
                         and abs(_band_state(st, idx, 1)['gain']) >= 0.05) else 2
    if typ == 'high_shelf':
        return 4 if not (_band_state(st, idx, 4)['on'] and _band_state(st, idx, 4)['shape'] != 'high_shelf'
                         and abs(_band_state(st, idx, 4)['gain']) >= 0.05) else 3
    if freq is None:
        return None
    oct_ = lambda a, b: abs(math.log2(max(a, 1.0) / max(b, 1.0)))  # noqa: E731
    bands = {n: _band_state(st, idx, n) for n in (1, 2, 3, 4)}
    busy = {n for n, b in bands.items() if b['on'] and abs(b['gain']) >= 0.05}
    near = sorted((oct_(bands[n]['freq'], freq), n) for n in busy if bands[n]['shape'] == 'bell')
    if near and near[0][0] <= 0.67:
        return near[0][1]
    free = [n for n in (1, 2, 3, 4) if n not in busy]
    if not free:
        # every band is busy: retune the nearest bell within an octave (the sentence says what it held)
        return near[0][1] if near and near[0][0] <= 1.0 else None
    return min(free, key=lambda n: (oct_(BAND_CENTRE[n], freq), n))


def _set_eq(st, ns, v):
    items = v if isinstance(v, list) else [v]
    out = []
    m = _k()['eq']
    for it in items:
        f = _norm(it)
        if f.get('flat') or f.get('reset'):
            for n in ns:
                idx = st.idx(n)
                for b in (1, 2, 3, 4):
                    _put(st, idx, (m['gain'][0], m['gain'][1], 4 - b), 0.0)
            out.append('EQ flat on %s (all four bands at 0 dB).' % _who(st, ns))
            continue
        band = f.get('band')
        if band is not None:
            band = int(_num(band, 'The EQ band'))
            if band not in (1, 2, 3, 4):
                raise Refuse('DiGiCo channels have EQ bands 1 to 4.')
        typ = f.get('type')
        if typ is not None:
            typ = EQ_TYPES.get(str(typ).strip().lower().replace('-', '_'))
            if typ is None:
                raise Refuse('An EQ band is a bell, a low shelf or a high shelf.')
        freq = _num(f['freq'], 'The EQ frequency', 20.0, 20000.0) if f.get('freq') is not None else None
        gain = f.get('gain', f.get('value'))
        gain = _num(gain, 'The EQ gain') if gain is not None else None
        if gain is not None and abs(gain) > 18.0:
            raise Refuse('An EQ band goes from -18 to +18 dB.')
        q = _num(f['q'], 'The EQ Q', 0.1, 20.0) if f.get('q') is not None else None
        on = f.get('on', True)
        picked, retuned = {}, []
        for n in ns:
            idx = st.idx(n)
            b = band or _pick_band(st, idx, typ or 'bell', freq)
            if b is not None and not band:
                bs = _band_state(st, idx, b)
                if bs['on'] and abs(bs['gain']) >= 0.05 and freq is not None and abs(bs['freq'] - freq) > 0.5:
                    retuned.append('%s band %d was %s %+.1f dB' % (st.label(n), b, _hz(bs['freq']), bs['gain']))
            if b is None:
                if freq is None:
                    raise Refuse('Say which EQ band (1 to 4) or a frequency.')
                raise Refuse('All four EQ bands on %s are in use. Say which band to change.' % st.label(n))
            t = typ or (_band_state(st, idx, b)['shape'] if band else 'bell')
            if t in process.SHELF_BANDS and b not in process.SHELF_BANDS[t]:
                raise Refuse('A %s sits on band %s on DiGiCo, not band %d.' % (
                    t.replace('_', ' '), ' or '.join(map(str, process.SHELF_BANDS[t])), b))
            bb = 4 - b
            if freq is not None:
                _put(st, idx, (m['freq'][0], m['freq'][1], bb), freq)
            if gain is not None:
                _put(st, idx, (m['gain'][0], m['gain'][1], bb), gain)
            if t in process.SHELF_BANDS:
                _put(st, idx, (m['q'][0], m['q'][1], bb), 0.85)
            elif q is not None:
                _put(st, idx, (m['q'][0], m['q'][1], bb), q)
            if typ is not None or t != _band_state(st, idx, b)['shape']:
                _put(st, idx, (m['shape'][0], m['shape'][1], bb), process.SHAPES.get(t, 1.0))
            _put(st, idx, (m['on'][0], m['on'][1], bb), 1.0 if on else 0.0)
            if on:
                _put(st, idx, _k()['eq_in'], 1.0)
            picked[n] = b
        what = []
        if typ:
            what.append(typ.replace('_', ' '))
        if freq is not None:
            what.append(_hz(freq))
        if gain is not None:
            what.append('%+.1f dB' % gain)
        if q is not None and (typ or 'bell') == 'bell':
            what.append('Q %.2g' % q)
        byb = {}
        for n, b in picked.items():
            byb.setdefault(b, []).append(n)
        main = max(byb, key=lambda b: (len(byb[b]), -b))
        bt = 'band %d' % main
        if len(byb) > 1:
            bt += ' (%s)' % '; '.join('band %d on %s' % (b, _nums(v)) for b, v in sorted(byb.items()) if b != main)
        if not on:
            out.append('EQ %s off on %s.' % (bt, _who(st, ns)))
        else:
            out.append('EQ %s on %s, %s.' % (' '.join(what) or 'band on', _who(st, ns), bt))
        if retuned:
            st.warn('Every EQ band was in use, so the nearest one was retuned: %s.' % '; '.join(retuned[:6]))
    return out


GATE_DEFAULT = {'thr': -40.0, 'range': 40.0, 'attack': 0.05, 'hold': 100.0, 'release': 200.0}
COMP_DEFAULT = {'thr': -20.0, 'ratio': 3.0, 'attack': 10.0, 'release': 150.0, 'knee': 'hard', 'makeup': 0.0}


def _set_gate(st, ns, v):
    f = _norm(v)
    if 'value' in f and 'thr' not in f:
        f['thr'] = f.pop('value')
    on = f.get('on', True)
    D = _k()['dyn2']
    given = {k: f[k] for k in ('thr', 'range', 'attack', 'hold', 'release') if f.get(k) is not None}
    lim = {'thr': (-60.0, 0.0), 'range': (0.0, 90.0), 'attack': (0.05, 100.0), 'hold': (2.0, 2000.0),
           'release': (5.0, 10000.0)}
    for k_, x in list(given.items()):
        given[k_] = _num(x, 'The gate %s' % k_, *lim[k_])
    was_comp, tpl_used = [], []
    for n in ns:
        idx = st.idx(n)
        if not on:
            _put(st, idx, D['in'], 0.0)
            continue
        mode = _get(st, idx, D['mode'])
        if mode not in (None, 0.0) and _get(st, idx, D['in']) == 1.0:
            was_comp.append(n)
        vals = dict(given)
        if 'thr' not in vals and (st.is_default(n, D['thr']) or mode not in (None, 0.0)):
            t = _tpl(st, n, 'gate')
            src = ({'thr': t.get('threshold_db'), 'range': t.get('range_db'), 'attack': t.get('attack_ms'),
                    'hold': t.get('hold_ms'), 'release': t.get('release_ms')} if t.get('threshold_db') is not None
                   else GATE_DEFAULT)
            for k_, x in src.items():
                if k_ not in vals and x is not None:
                    vals[k_] = max(lim[k_][0], min(lim[k_][1], float(x)))
            tpl_used.append(n)
        _put(st, idx, D['mode'], 0.0)
        if 'thr' in vals:
            _put(st, idx, D['thr'], vals['thr'])
        if 'range' in vals:
            _put(st, idx, D['range'], vals['range'])
        for k_, key in (('attack', 'atk'), ('hold', 'hold'), ('release', 'rel')):
            if k_ in vals:
                _put(st, idx, D[key], vals[k_] / 1000.0)
        _put(st, idx, D['in'], 1.0)
    if was_comp:
        st.warn('Dyn2 on %s was a compressor or ducker. It is a gate now.' % _who(st, was_comp))
    if not on:
        return ['Gate out on %s.' % _who(st, ns)]
    bits = []
    if 'thr' in given:
        bits.append('threshold %.0f dB' % given['thr'])
    if 'range' in given:
        bits.append('range %.0f dB' % given['range'])
    for k_ in ('attack', 'hold', 'release'):
        if k_ in given:
            bits.append('%s %s ms' % (k_, ('%.2f' % given[k_]).rstrip('0').rstrip('.')))
    s = 'Gate in on %s' % _who(st, ns)
    if bits:
        s += ': ' + ', '.join(bits)
    if tpl_used and 'thr' not in given:
        s += ' (starting thresholds from the %s templates; set them at line check)' % (
            'instrument' if len(tpl_used) > 1 else 'instrument')
    return [s + '.']


def _comp_from(st, n):
    """Starting SD comp values for channel n: the category template's comp, else COMP_DEFAULT."""
    t = _tpl(st, n, 'comp')
    if t.get('threshold_db') is not None:
        return {'thr': t['threshold_db'], 'ratio': t.get('ratio') or 3.0, 'attack': t.get('attack_ms') or 10.0,
                'release': t.get('release_ms') or 150.0, 'knee': t.get('knee') or 'hard',
                'makeup': max(0.0, t.get('makeup_db') or 0.0)}
    return dict(COMP_DEFAULT)


def _write_comp(st, idx, vals):
    if 'thr' in vals:
        for band in (0, 1, 2):          # the editor mirrors the comp threshold into all three records
            if st.ses.has_slot(idx, 0x05, d2d.C_THR, band):
                st.ses.set(idx, 0x05, d2d.C_THR, band, process.dbfs(vals['thr']))
    if 'ratio' in vals:
        _put(st, idx, (0x05, d2d.C_RATIO, 0), d2d.clamp(float(vals['ratio']), 1.0, 50.0))
    if 'attack' in vals:
        _put(st, idx, (0x05, d2d.C_ATK, 0), d2d.clamp(float(vals['attack']), 0.02, 100.0) / 1000.0)
    if 'release' in vals:
        _put(st, idx, (0x05, d2d.C_REL, 0), d2d.clamp(float(vals['release']), 1.0, 10000.0) / 1000.0)
    if 'knee' in vals:
        _put(st, idx, (0x05, d2d.C_KNEE, 0), d2d.KNEE.get(str(vals['knee']).lower(), 0.0))
    if 'makeup' in vals:
        _put(st, idx, (0x05, d2d.C_MK, 0), d2d.clamp(float(vals['makeup']), 0.0, 40.0))


def _set_comp(st, ns, v):
    f = _norm(v)
    if 'value' in f and 'thr' not in f:
        f['thr'] = f.pop('value')
    on = f.get('on', True)
    given = {}
    for k_ in ('thr', 'ratio', 'attack', 'release', 'makeup'):
        if f.get(k_) is not None:
            given[k_] = _num(f[k_], 'The comp %s' % k_)
    if f.get('knee') is not None:
        if str(f['knee']).lower() not in d2d.KNEE:
            raise Refuse('The SD comp knee is hard, medium or soft.')
        given['knee'] = str(f['knee']).lower()
    if 'thr' in given and not -60.0 <= given['thr'] <= 0.0:
        raise Refuse('A comp threshold goes from -60 to 0 dBFS.')
    both = []
    for n in ns:
        idx = st.idx(n)
        if not on:
            _put(st, idx, (0x05, d2d.C_IN, 0), 0.0)
            continue
        vals = dict(given)
        if 'thr' not in vals and st.is_default(n, (0x05, d2d.C_THR, 0)):
            for k_, x in _comp_from(st, n).items():
                vals.setdefault(k_, x)
        if f.get('mode') is not None or _get(st, idx, (0x05, d2d.C_MODE, 0)) not in (0.0, None):
            _put(st, idx, (0x05, d2d.C_MODE, 0), 0.0)
        _write_comp(st, idx, vals)
        _put(st, idx, (0x05, d2d.C_IN, 0), 1.0)
        if st.ses.has_module(d2d.MC, idx) and _get(st, idx, (d2d.MC, d2d.MC_ON, 0)) == 1.0:
            both.append(n)
    if both:
        st.warn('%s now run%s the SD comp and the Mustard comp.' % (_who(st, both), 's' if len(both) == 1 else ''))
    if not on:
        return ['SD comp out on %s.' % _who(st, ns)]
    bits = []
    if 'thr' in given:
        bits.append('threshold %.0f dB' % given['thr'])
    if 'ratio' in given:
        bits.append('%.3g:1' % given['ratio'])
    if 'attack' in given:
        bits.append('attack %.3g ms' % given['attack'])
    if 'release' in given:
        bits.append('release %.4g ms' % given['release'])
    if 'knee' in given:
        bits.append('%s knee' % given['knee'])
    if 'makeup' in given:
        bits.append('makeup %+.1f dB' % given['makeup'])
    return ['SD comp in on %s%s.' % (_who(st, ns), (': ' + ', '.join(bits)) if bits else '')]


# ---------------------------------------------------------------------------------------------------- Mustard
MODEL_ALIASES = {'classic': 'classic', 'vca': 'vca', 'vintage vca': 'vca', 'vintage': 'vca', 'fet': 'fet',
                 '1176': 'fet', 'optical': 'optical', 'opto': 'optical', 'la2a': 'optical', 'la-2a': 'optical',
                 'levamp': 'levamp', 'leveling amp': 'levamp', 'levelling amp': 'levamp', 'leveler': 'levamp'}
FET_RATIO_BUTTON = [(4.0, 1.0), (8.0, 2.0), (12.0, 3.0), (20.0, 4.0)]


LAST_FOR_MUSTARD = {'tracks_music': 10, 'tracks_drums_perc': 10, 'tracks_bass': 10, 'tracks_vocals': 10,
                    'media_playback': 10, 'audience': 11, 'other': 11, 'fx_reverb': 11, 'fx_delay': 11,
                    'fx_modulation': 11, 'fx_other': 11, 'click': 12, 'cues_guide': 12, 'timecode': 12,
                    'talkback': 12, 'comms_radio': 12, 'measurement_ref': 12, 'test_signal': 12}


def _mustard_rank(cat):
    """process.MUSTARD_PRIORITY first (lead vocal 0 ... drum crotch 6), the other instruments 9, then playback,
    ambience and unknown channels, then click, talkback and test signals (they gain nothing from a Mustard comp)."""
    return process.MUSTARD_PRIORITY.get(cat, LAST_FOR_MUSTARD.get(cat, 9))


def _mustard_base(st, n):
    """Starting Mustard comp settings for channel n (op values override them): the channel's own SD comp when it is
    on (its threshold, ratio and times carried over), else the category template's Mustard comp, else its SD comp
    template, else Classic -20 dB 3:1."""
    idx = st.idx(n)
    c = lambda p: _get(st, idx, (0x05, p, 0))  # noqa: E731
    if c(d2d.C_IN) == 1.0 and c(d2d.C_THR) is not None:
        return {'model': 'classic', 'thr': c(d2d.C_THR), 'ratio': d2d.clamp(c(d2d.C_RATIO) or 3.0, 1.0, 20.0),
                'attack': (c(d2d.C_ATK) or 0.01) * 1000.0, 'release': (c(d2d.C_REL) or 0.15) * 1000.0,
                'knee': 'hard' if (c(d2d.C_KNEE) or 0.0) == 0.0 else 'soft', 'out': c(d2d.C_MK) or 0.0,
                'mix': 1.0, 'from': 'sd'}
    mc = _tpl(st, n, 'mustard_comp')
    if mc.get('threshold_db') is not None or mc.get('model') == 'levamp':
        return {'model': mc.get('model') or 'classic', 'thr': mc.get('threshold_db'), 'ratio': mc.get('ratio'),
                'attack': mc.get('attack_ms'), 'release': mc.get('release_ms'), 'knee': mc.get('knee'),
                'out': mc.get('output_db'), 'mix': mc.get('mix') if mc.get('mix') is not None else 1.0,
                'from': 'template'}
    cc = _tpl(st, n, 'comp')
    if cc.get('threshold_db') is not None:
        return {'model': 'classic', 'thr': cc['threshold_db'], 'ratio': cc.get('ratio') or 3.0,
                'attack': cc.get('attack_ms') or 10.0, 'release': cc.get('release_ms') or 150.0,
                'knee': cc.get('knee') or 'hard', 'out': max(0.0, cc.get('makeup_db') or 0.0), 'mix': 1.0,
                'from': 'template'}
    return {'model': 'classic', 'thr': -20.0, 'ratio': 3.0, 'attack': 10.0, 'release': 150.0, 'knee': 'hard',
            'out': 0.0, 'mix': 1.0, 'from': 'default'}


def _mustard_current(st, n):
    """The Mustard comp values channel n holds now, in _write_mustard's units."""
    idx = st.idx(n)
    g = lambda p: _get(st, idx, (d2d.MC, p, 0))  # noqa: E731
    vals = {'model': process.MUSTARD_MODELS.get(g(d2d.MC_TYPE), 'classic'), 'thr': g(d2d.MC_THR),
            'ratio': g(d2d.MC_RATIO), 'attack': None if g(d2d.MC_ATK) is None else g(d2d.MC_ATK) * 1000.0,
            'release': None if g(d2d.MC_REL) is None else g(d2d.MC_REL) * 1000.0,
            'knee': 'hard' if g(d2d.MC_KNEE) == 1.0 else 'soft', 'out': g(d2d.MC_OUT), 'mix': g(d2d.MC_MIX)}
    return {k_: x for k_, x in vals.items() if x is not None}


def _write_mustard(st, n, vals):
    """Mustard comp on channel n with vals (model, thr, ratio, attack, release, knee, out, mix), through
    dlive2digico.put_mustard as build does (thresholds already dBFS)."""
    idx = st.idx(n)
    w = d2d.Writer(st.ses, idx)
    model = vals.get('model') or 'classic'
    kw = dict(out=vals.get('out'), mix=d2d.clamp(float(vals.get('mix') if vals.get('mix') is not None else 1.0), 0, 1),
              to_fs=process.dbfs)
    if model in ('classic', 'vca', 'optical'):
        kw['thr'] = vals.get('thr')
    if model == 'classic':
        kw.update(ratio=vals.get('ratio'), atk_ms=vals.get('attack'), rel_ms=vals.get('release'), knee=vals.get('knee'))
    elif model == 'optical':
        r = vals.get('ratio')
        kw['ratio'] = min(float(r), 3.0) if r is not None else None
    elif model == 'vca':
        kw['ratio'] = vals.get('ratio')
    d2d.put_mustard(w, model, **kw)
    if model == 'fet':
        if vals.get('input') is not None:
            w.put((d2d.MC, d2d.MC_FET_IN, 0), d2d.clamp(float(vals['input']), -40.0, 20.0))
        if vals.get('ratio') is not None:
            r = float(vals['ratio'])
            w.put((d2d.MC, d2d.MC_FET_RATIO, 0), min(FET_RATIO_BUTTON, key=lambda x: abs(x[0] - r))[1])
        if vals.get('out') is not None:
            w.put((d2d.MC, d2d.MC_FET_OUT, 0), d2d.clamp(float(vals['out']), -24.0, 24.0))


def _set_tidal(st, n, value):
    """cb +86 TidalChannel: the editor's Mustard instance number (-1 none). Set to -1 when a channel gives its
    instance back, so the readout and the console count agree before the editor reallocates on load."""
    idx = st.idx(n)
    off = st.ses.chrec_off.get(idx)
    if off is not None and st.ses.d[off + 2] >= 0x58:
        struct.pack_into('<h', st.ses.d, off + 86, value)


def _set_mustard(st, ns, v):
    f = _norm(v)
    if not st.quantum:
        raise Refuse('The %s has no Mustard processing. Use the SD comp.' % st.console['name'])
    on = f.get('on', True)
    model = f.get('model')
    if model is not None:
        model = MODEL_ALIASES.get(str(model).strip().lower())
        if model is None:
            raise Refuse('The Mustard comp models are Classic, VCA, FET, Optical and Leveling Amp.')
    given = {}
    for k_ in ('thr', 'ratio', 'attack', 'release', 'out', 'mix', 'input'):
        if f.get(k_) is not None:
            given[k_] = _num(f[k_], 'The Mustard %s' % k_)
    if f.get('knee') is not None:
        given['knee'] = 'hard' if str(f['knee']).lower() == 'hard' else 'soft'
    if 'thr' in given and not -60.0 <= given['thr'] <= 0.0:
        raise Refuse('A Mustard threshold goes from -60 to 0 dBFS.')
    if 'mix' in given and given['mix'] > 1.0:
        given['mix'] = given['mix'] / 100.0
    no_mod = [n for n in ns if not st.ses.has_module(d2d.MC, st.idx(n))]
    if no_mod:
        raise Refuse('%s %s no Mustard modules in this file.' % (_who(st, no_mod), 'has' if len(no_mod) == 1 else 'have'))
    if not on:
        return _mustard_off(st, ns, f.get('sd_comp', True))
    # allocation: channels already holding an instance keep it; the rest by priority within the cap
    cap = st.cap
    holding = [n for n in ns if st.mustard_uses(n)]
    others = sum(st.width(n) for n in st.numbers() if n not in ns and st.mustard_uses(n))
    used = others + sum(st.width(n) for n in holding)
    want = [n for n in ns if n not in holding]
    want.sort(key=lambda n: (_mustard_rank(st.cat(n)), n))
    got, missed = list(holding), []
    for n in want:
        cost = st.width(n)
        if cap is None or used + cost <= cap:
            got.append(n)
            used += cost
        else:
            missed.append(n)
    got.sort()
    from_sd = []
    for n in got:
        idx = st.idx(n)
        cur_on = _get(st, idx, (d2d.MC, d2d.MC_ON, 0)) == 1.0
        if cur_on:
            vals = _mustard_current(st, n)    # already on: only the given values change
        else:
            base = _mustard_base(st, n)
            vals = {k_: x for k_, x in base.items() if x is not None and k_ != 'from'}
            if base.get('from') == 'sd':
                from_sd.append(n)
        if model is not None:
            vals['model'] = model
        vals.update(given)
        if not cur_on or given or model is not None:
            _write_mustard(st, n, vals)
        _put(st, idx, (0x05, d2d.C_IN, 0), 0.0)                 # the Mustard comp replaces the SD comp
        st.ses.set_strip_view(idx, st.ses.VIEW_MUSTARD)
    out = []
    if got:
        mname = {'classic': 'Classic', 'vca': 'VCA', 'fet': 'FET', 'optical': 'Optical', 'levamp': 'Leveling Amp'}
        s = 'Mustard %scomp on %s' % ((mname[model] + ' ') if model else '', _who(st, got))
        bits = []
        if 'thr' in given:
            bits.append('threshold %.0f dB' % given['thr'])
        if 'ratio' in given:
            bits.append('%.3g:1' % given['ratio'])
        if bits:
            s += ': ' + ', '.join(bits)
        s += '. The SD comp is off there and the strips open on the M view'
        if from_sd:
            s += '; %s took %s SD comp settings' % (_who(st, from_sd, 3), 'its' if len(from_sd) == 1 else 'their')
        out.append(s + '.')
        out.append('Mustard uses %d of %d instances (a stereo channel uses 2).' % (used, cap) if cap is not None else
                   'Mustard uses %d instances (a stereo channel uses 2).' % used)
    if missed:
        st.warn('No Mustard instance left for %s: the %s runs %d (a stereo channel uses 2). %s the SD comp.' % (
            _who(st, sorted(missed), 8), st.console['name'], cap, 'It keeps' if len(missed) == 1 else 'They keep'))
    if not got:
        raise Refuse('Every Mustard instance on the %s is in use (%d of %d). Turn Mustard off somewhere first.' % (
            st.console['name'], used, cap))
    if cap is not None and not st.console.get('mustard_cap_verified'):
        st.warn('The Mustard limit of %d on the %s is from DiGiCo\'s figures, not checked in the editor yet.' % (
            cap, st.console['name']))
    return out


def _mustard_off(st, ns, sd_comp=True):
    off, moved = [], []
    for n in ns:
        idx = st.idx(n)
        if _get(st, idx, (d2d.MC, d2d.MC_ON, 0)) != 1.0:
            continue
        g = lambda p: _get(st, idx, (d2d.MC, p, 0))  # noqa: E731
        vals = {'thr': g(d2d.MC_THR), 'ratio': d2d.clamp(g(d2d.MC_RATIO) or 3.0, 1.0, 50.0),
                'attack': (g(d2d.MC_ATK) or 0.01) * 1000.0, 'release': (g(d2d.MC_REL) or 0.15) * 1000.0,
                'knee': 'hard' if g(d2d.MC_KNEE) == 1.0 else 'soft', 'makeup': max(0.0, g(d2d.MC_OUT) or 0.0)}
        _put(st, idx, (d2d.MC, d2d.MC_ON, 0), 0.0)
        off.append(n)
        if sd_comp and _get(st, idx, (0x05, d2d.C_IN, 0)) != 1.0:
            if vals['thr'] is None:
                vals.pop('thr')
            _put(st, idx, (0x05, d2d.C_MODE, 0), 0.0)
            _write_comp(st, idx, vals)
            _put(st, idx, (0x05, d2d.C_IN, 0), 1.0)
            moved.append(n)
        if not st.mustard_uses_modules(n):
            st.ses.set_strip_view(idx, st.ses.VIEW_SD)
            _set_tidal(st, n, -1)
    if not off:
        return ['Mustard comp was already off on %s.' % _who(st, ns)]
    s = 'Mustard comp off on %s' % _who(st, off)
    if moved:
        s += '; %s %s back on the SD comp with the same settings' % (_who(st, moved, 3), 'is' if len(moved) == 1
                                                                       else 'are')
    return [s + '.', 'Mustard uses %d%s instances now.' % (st.mustard_used(), (' of %d' % st.cap) if st.cap else '')]


def _mustard_uses_modules(self, n):
    idx = self.idx(n)
    c = self.ses.by_index[idx]
    for mod in I.MUSTARD_MODS:
        r = c.records.get(mod)
        if r is not None and (0x02, 0) in r.slots and self.ses.get(idx, mod, 0x02, 0) == 1.0:
            return True
    return False


_State.mustard_uses_modules = _mustard_uses_modules


def _set_simple(key, what):
    def run(st, ns, v):
        if key == 'view':
            return _set_view(st, ns, v)
        f = _norm(v) if not isinstance(v, (int, float)) or isinstance(v, bool) else {'value': float(v)}
        k = _k()
        if key == 'delay_ms':
            ms = f.get('value', f.get('ms'))
            on = f.get('on', ms is not None and float(ms) > 0)
            if ms is not None:
                ms = _num(ms, 'The delay', 0.0, 1300.0)
            for n in ns:
                idx = st.idx(n)
                if ms is not None:
                    _put(st, idx, k['delay'], ms / 1000.0)
                _put(st, idx, k['delay_on'], 1.0 if on and (ms is None or ms > 0) else 0.0)
            if not on or ms == 0:
                return ['Delay off on %s.' % _who(st, ns)]
            return ['Delay %s on %s.' % (('%.4g ms' % ms) if ms is not None else 'on', _who(st, ns))]
        if key == 'polarity':
            inv = f.get('on', f.get('value'))
            inv = bool(inv)
            for n in ns:
                _put(st, st.idx(n), k['polarity'], (3.0 if st.width(n) == 2 else 1.0) if inv else 0.0)
            return ['Polarity %s on %s.' % ('inverted' if inv else 'normal', _who(st, ns))]
        if key == 'mute':
            m = bool(f.get('on', f.get('value')))
            for n in ns:
                _put(st, st.idx(n), MUTE, 1.0 if m else 0.0)
            return ['%s %s.' % ('Muted' if m else 'Unmuted', _who(st, ns))]
        val = f.get('value')
        if val is None:
            raise Refuse('Say a value for the %s.' % what)
        if key == 'pan':
            val = _num(val, 'The pan')
            if abs(val) > 1.0:
                val = val / 100.0
            val = max(-1.0, min(1.0, val)) + 0.0
            for n in ns:
                _put(st, st.idx(n), PAN, val)
            _follow_linked_pans(st, ns)
            return ['Pan %s on %s.' % ('centre' if val == 0 else '%d%% %s' % (round(abs(val) * 100), 'left' if val < 0
                                                                              else 'right'), _who(st, ns))]
        lim = {'trim_db': (-40.0, 40.0), 'fader_db': (-150.0, 10.0)}[key]
        val = _num(val, 'The %s' % what)
        if not lim[0] <= val <= lim[1]:
            raise Refuse('The %s goes from %+g to %+g dB.' % (what, lim[0], lim[1]))
        for n in ns:
            _put(st, st.idx(n), TRIM if key == 'trim_db' else FADER, val + 0.0)
        return ['%s %s on %s.' % (what[:1].upper() + what[1:], ('off' if val <= -150 else '%+.1f dB' % val)
                                  if key == 'fader_db' else '%+.1f dB' % val, _who(st, ns))]
    return run


def _follow_linked_pans(st, ns):
    """Stereo auxes with link pans on take each send pan from the channel pan, and the editor rewrites them on load.
    Write the same values here so the file is already what the console would make (an SD9 V2242 boot showed the
    editor moving six IEM send pans after a pan edit that left them alone)."""
    from . import sends as SE
    try:
        auxes = [b for b in SE.buses(st.ses, 'aux') if b.get('width') == 2]
    except Exception:      # noqa: BLE001 - an odd bus table: leave the sends for the editor to settle
        return
    for b in auxes:
        try:
            mode = SE.link_pans(st.ses, b['number'])
        except Exception:  # noqa: BLE001
            continue
        if not mode:
            continue
        for n in ns:
            idx = st.idx(n)
            if st.ses.has_slot(idx, SE.SEND, SE.S_PAN, b['band']):
                st.ses.set(idx, SE.SEND, SE.S_PAN, b['band'], SE._linked_pan(st.ses, idx, mode))


def _set_view(st, ns, v):
    vv = str(v.get('value', v.get('view', '')) if isinstance(v, dict) else v).strip().lower()
    if vv not in ('sd', 'mustard', 'm'):
        raise Refuse("The strip view is 'sd' or 'mustard'.")
    if vv != 'sd' and not st.quantum:
        raise Refuse('The %s has no Mustard view.' % st.console['name'])
    for n in ns:
        st.ses.set_strip_view(st.idx(n), st.ses.VIEW_SD if vv == 'sd' else st.ses.VIEW_MUSTARD)
    return ['%s open%s on the %s view.' % (_who(st, ns), 's' if len(ns) == 1 else '', 'SD' if vv == 'sd' else 'M')]


SETTERS = {'name': _set_name, 'hpf': _set_filter('hpf'), 'lpf': _set_filter('lpf'), 'eq_on': _set_eq_on,
           'eq': _set_eq, 'gate': _set_gate, 'comp': _set_comp, 'mustard': _set_mustard,
           'delay_ms': _set_simple('delay_ms', 'delay'), 'polarity': _set_simple('polarity', 'polarity'),
           'trim_db': _set_simple('trim_db', 'trim'), 'fader_db': _set_simple('fader_db', 'fader'),
           'mute': _set_simple('mute', 'mute'), 'pan': _set_simple('pan', 'pan'), 'view': _set_simple('view', 'view')}


# ---------------------------------------------------------------------------------------------------- names
def _clean_name(name, n):
    from .build import short_name, clean_text
    full = clean_text(name, 80)
    short, changed = short_name(full, n)
    return full, short, changed


def _op_rename(st, op):
    ns = _targets(st, op)
    if op.get('names') is not None:
        names = op['names'] if isinstance(op['names'], list) else [op['names']]
    elif op.get('name') is not None:
        names = [op['name']]
    else:
        raise Refuse('Say the new name.')
    if len(names) != len(ns):
        if len(names) == 1 and len(ns) > 1:
            raise Refuse('Give each of the %d channels its own name, or rename one channel at a time.' % len(ns))
        raise Refuse('%d names for %d channels. Give one name per channel.' % (len(names), len(ns)))
    out = []
    for n, nm in zip(ns, names):
        full, short, changed = _clean_name(nm, n)
        if not full:
            raise Refuse('A channel name needs at least one letter or number.')
        old = st.name(n)
        st.ses.rename(st.idx(n), short)
        out.append('Renamed %d %s to %s.' % (n, old.strip() or '(no name)', short) if not changed else
                   'Renamed %d %s to %s (%r is shortened to 8 characters on the console).' % (
                       n, old.strip() or '(no name)', short, full))
    return out


# ---------------------------------------------------------------------------------------------------- sends
def _aux_number(st, a):
    if isinstance(a, dict):
        a = a.get('n', a.get('number', a.get('aux')))
    if isinstance(a, str) and not a.strip().isdigit():
        w = re.sub(r'^aux\s*', '', a.strip(), flags=re.I)
        if w.isdigit():
            a = int(w)
        else:
            hit = [x['number'] for x in st.ses.auxes if x['name'].strip().lower() == a.strip().lower()]
            if not hit:
                hit = [x['number'] for x in st.ses.auxes if a.strip().lower() in x['name'].strip().lower()]
            if len(hit) != 1:
                raise Refuse('No aux is called %r.' % a if not hit else '%r matches auxes %s. Say the number.' % (
                    a, _nums(hit)))
            a = hit[0]
    try:
        a = int(a)
    except (TypeError, ValueError):
        raise Refuse('Say which aux, by number or name.')
    if a not in st.ses.aux_band:
        raise Refuse('This session has %d aux%s, so there is no aux %d.' % (
            len(st.ses.auxes), '' if len(st.ses.auxes) == 1 else 'es', a))
    return a


def _aux_label(st, a):
    x = next(x for x in st.ses.auxes if x['number'] == a)
    nm = x['name'].strip()
    return 'Aux %d' % a if not nm or nm.lower() == ('aux %d' % a) else 'Aux %d (%s)' % (a, nm)


def _op_send(st, op):
    ns = _targets(st, op)
    aux = _aux_number(st, op.get('aux', op.get('to', op.get('bus'))))
    level = op.get('level_db', op.get('level'))
    if level is not None:
        level = _num(level, 'The send level')
        if level > 10.0:
            raise Refuse('A send goes up to +10 dB.')
    on = op.get('on')
    if op.get('off'):
        on = False
    pre = op.get('pre', op.get('prepost'))
    if isinstance(pre, str):
        p = pre.strip().lower().replace(' ', '-').replace('_', '-')
        p = {'pre-fader': 'pre', 'prefader': 'pre', 'post-fader': 'post', 'postfader': 'post', 'mid-eq/dynamics':
             'mid-eq', 'pre-eq/dynamics': 'pre-eq'}.get(p, p)
        if p not in S.PREPOST:
            raise Refuse('A send is post, pre, pre-mute, mid-eq, pre-eq or pre-processing.')
        pre = p
    pan = op.get('pan')
    if pan is not None:
        pan = _num(pan, 'The send pan')
        if abs(pan) > 1.0:
            pan = pan / 100.0
    lv = {}
    for n in ns:
        cur = S.read_send(st.ses, n, aux)
        lvl = level
        if lvl is None and on is not False and cur['level'] <= S.OFF_DB:
            lvl = 0.0
        o = on if on is not None else (lvl is None or lvl > S.OFF_DB)
        try:
            S.set_send(st.ses, n, aux, lvl, on=o, pre=pre, pan=pan)
        except (ValueError, KeyError) as e:
            raise Refuse(_sentence(e))
        lv[n] = S.read_send(st.ses, n, aux)
    if on is False:
        return ['Send to %s off on %s.' % (_aux_label(st, aux), _who(st, ns))]
    levels = {round(x['level'], 1) for x in lv.values()}
    pps = {x['prepost'] for x in lv.values()}
    s = 'Send to %s on %s' % (_aux_label(st, aux), _who(st, ns))
    bits = []
    if len(levels) == 1:
        bits.append('%+.1f dB' % levels.pop())
    if len(pps) == 1:
        bits.append({'post': 'post-fader', 'pre': 'pre-fader'}.get(next(iter(pps)), str(next(iter(pps)))))
    if pan is not None:
        bits.append('pan %+.2f' % pan)
    return [s + (': ' + ', '.join(bits) if bits else '') + '.']


# ---------------------------------------------------------------------------------------------------- patch
def _socket(st, spec):
    """An input socket dict (patch.input_sockets shape) from a spec: 'Rack 1:5', 'Local 3', 'MADI 12', '1:Mic 5',
    ('Rack 1', 5), {'device'|'group', 'number'} or {'type', 'idx'}."""
    ses = st.ses
    try:
        if isinstance(spec, dict) and 'type' in spec and 'idx' in spec:
            return P.find_input_socket(ses, {'type': int(spec['type']), 'idx': int(spec['idx'])})
        if isinstance(spec, dict):
            dev = spec.get('device', spec.get('group', spec.get('rack')))
            num = spec.get('number', spec.get('socket', spec.get('input')))
            if isinstance(dev, int) or (isinstance(dev, str) and dev.strip().isdigit()):
                dev = 'Rack %d' % int(dev)
            return P.find_input_socket(ses, (str(dev), int(num)))
        if isinstance(spec, (list, tuple)) and len(spec) == 2:
            return P.find_input_socket(ses, (str(spec[0]), int(spec[1])))
        if isinstance(spec, str):
            s = P.socket_from_text(ses, spec)
            if s is not None:
                return s
            return P.find_input_socket(ses, spec.strip())
    except (KeyError, ValueError, TypeError) as e:
        raise Refuse(_sentence(e).replace("'", ''))
    raise Refuse('Say which input socket, for example Rack 1:5 or Local 3.')


def _main_refs(st, skip=()):
    """{(type, idx): [surface channels]} of every channel's main input (a stereo channel holds two sockets)."""
    out = {}
    for n in st.numbers():
        if n in skip:
            continue
        try:
            info = P.input_of(st.ses, n)
        except KeyError:
            continue
        r = info.get('main_ref')
        if r and r['type'] != FX.FX_TYPE:
            out.setdefault((r['type'], r['idx']), []).append(n)
            if st.width(n) == 2:
                out.setdefault((r['type'], r['idx'] + 1), []).append(n)
    return out


def _op_patch(st, op):
    ns = _targets(st, op)
    st.routing = True
    if op.get('unpatch') or op.get('socket') in (None, 'none', '') and op.get('alt') is None:
        if not op.get('unpatch') and op.get('socket') not in ('none', ''):
            raise Refuse('Say which input socket, for example Rack 1:5, or unpatch.')
        for n in ns:
            P.patch_input(st.ses, n, None)
        return ['Unpatched %s.' % _who(st, ns)]
    out = []
    first = _socket(st, op['socket']) if op.get('socket') not in (None, '') else None
    alt = _socket(st, op['alt']) if op.get('alt') is not None else None
    if alt is not None and len(ns) > 1:
        raise Refuse('Set an alt input one channel at a time.')
    keep = op.get('keep_preamp', True) is not False
    plan = []
    if first is not None:
        row = [s for s in P.input_sockets(st.ses) if s['type'] == first['type']]
        row.sort(key=lambda s: s['idx'])
        k = next(i for i, s in enumerate(row) if s['id'] == first['id'])
        for n in ns:
            need = st.width(n)
            if k + need > len(row) or (need == 2 and row[k + 1]['idx'] != row[k]['idx'] + 1):
                raise Refuse('%s runs out of inputs at %s. Patch the rest somewhere else.' % (first['group'],
                                                                                            st.label(n)))
            plan.append((n, row[k]))
            k += need
    else:
        plan = [(ns[0], None)]
    others = _main_refs(st, skip=set(ns))
    shared = []
    for n, sock in plan:
        old = P.input_of(st.ses, n)
        old_pre = None
        if old.get('main_ref') and old['main_ref']['type'] != FX.FX_TYPE:
            old_pre = P.read_preamp(st.ses, {'type': old['main_ref']['type'], 'idx': old['main_ref']['idx']})
        try:
            r = P.patch_input(st.ses, n, {'type': sock['type'], 'idx': sock['idx']} if sock else
                              old.get('main_ref'), {'type': alt['type'], 'idx': alt['idx']} if alt else None,
                              use_alt=bool(op.get('use_alt')))
        except (KeyError, ValueError) as e:
            raise Refuse(_sentence(e))
        if sock is None:
            out.append('Alt input of %s is %s%s.' % (st.label(n), alt['name'], ' and in use' if op.get('use_alt')
                                                     else ''))
            continue
        socks = [r['refs']['main']] + ([r['refs']['right']] if r['refs']['right'] else [])
        busy = [s for s in socks if (s['type'], s['idx']) in others]
        if busy:
            shared.append('%s now shares %s with %s' % (st.label(n), busy[0]['name'], _who(
                st, others[(busy[0]['type'], busy[0]['idx'])], 3)))
        carried = ''
        if keep and old_pre and not busy and any(old_pre.get(x) is not None for x in ('gain_db', 'phantom', 'pad')):
            done = []
            for s in socks:
                try:
                    _, g = P.set_preamp(st.ses, s, old_pre.get('gain_db'), old_pre.get('phantom'), old_pre.get('pad'),
                                        clamp=True)
                    done.append(g)
                except ValueError:
                    pass
            if done:
                carried = '; gain %+.1f dB and 48V %s came along' % (done[0] if done[0] is not None else 0.0,
                                                                    'on' if old_pre.get('phantom') else 'off')
        where = '%s:%d' % (sock['group'], sock['number'])
        nm = r['main'] if r['main'] and r['main'] != where else ''
        out.append('Patched %s to %s%s%s%s.' % (st.label(n), where, (' (%s)' % nm) if nm else '',
                                                (', right side %s' % r['right']) if r['right'] else '', carried))
    for s in shared:
        st.warn(s + '. Gain, 48V and pad live on the socket, so they share those too.')
    if len(out) > 8:
        out = ['Patched %s from %s:%d on.' % (_who(st, ns), first['group'], first['number'])]
    return out


def _op_preamp(st, op):
    ns = _targets(st, op)
    gain = op.get('gain_db', op.get('gain'))
    ph = op.get('phantom', op.get('48v', op.get('p48')))
    pad = op.get('pad')
    if gain is None and ph is None and pad is None:
        raise Refuse('Say a gain, 48V on or off, or pad on or off.')
    if gain is not None:
        gain = _num(gain, 'The gain')
    unp, nopre, done = [], [], []
    for n in ns:
        info = P.input_of(st.ses, n)
        r = info.get('main_ref')
        if not r or r['type'] == FX.FX_TYPE:
            unp.append(n)
            continue
        socks = [r] + ([{'type': r['type'], 'idx': r['idx'] + 1}] if st.width(n) == 2 else [])
        ok = True
        for s in socks:
            try:
                P.set_preamp(st.ses, s, gain, None if ph is None else bool(ph), None if pad is None else bool(pad),
                             clamp=True)
            except (ValueError, KeyError):
                ok = False
        (done if ok else nopre).append(n)
    if unp:
        st.warn('%s %s not patched to a socket, so there is no preamp to set.' % (_who(st, unp),
                                                                                   'is' if len(unp) == 1 else 'are'))
    if nopre:
        st.warn('%s %s on inputs without a mic preamp (MADI, Dante, line), so gain, 48V and pad do nothing there.' % (
            _who(st, nopre), 'is' if len(nopre) == 1 else 'are'))
    if not done:
        raise Refuse('None of those channels sits on a mic preamp.')
    bits = []
    if gain is not None:
        bits.append('gain %+.1f dB' % (round(gain * 2) / 2))
    if ph is not None:
        bits.append('48V %s' % ('on' if ph else 'off'))
    if pad is not None:
        bits.append('pad %s' % ('on' if pad else 'off'))
    txt = ' and '.join(bits) if len(bits) <= 2 else ', '.join(bits[:-1]) + ' and ' + bits[-1]
    return ['%s for %s (set on the input socket%s).' % (txt[:1].upper() + txt[1:], _who(st, done),
                                                       's' if len(done) > 1 else '')]


# ---------------------------------------------------------------------------------------------------- templates
def _reset_processing(st, n):
    idx, k = st.idx(n), _k()
    for key in (k['hpf_in'], k['lpf_in'], k['eq_in'], k['dyn2']['in'], (0x05, d2d.C_IN, 0), k['delay_on'],
                k['polarity']):
        if st.ses.has_slot(idx, *key):
            st.ses.set(idx, key[0], key[1], key[2], 0.0)
    m = k['eq']
    for b in (1, 2, 3, 4):
        if st.ses.has_slot(idx, m['on'][0], m['on'][1], 4 - b):
            st.ses.set(idx, m['on'][0], m['on'][1], 4 - b, 0.0)
    if st.ses.has_slot(idx, d2d.MC, d2d.MC_ON, 0):
        st.ses.set(idx, d2d.MC, d2d.MC_ON, 0, 0.0)


def _op_apply_template(st, op):
    ns = _targets(st, op)
    cats = process.templates()['categories']
    want = op.get('category', op.get('template', 'auto')) or 'auto'
    role = 'mon' if op.get('role') == 'mon' else 'foh'
    rows = []
    for n in ns:
        c = st.cat(n) if want in ('auto', True) else str(want)
        if c != 'other' and c not in cats:
            raise Refuse('There is no %r template. Pick one of the instrument categories.' % c)
        tpl, src = process.resolve(c, role)
        rows.append((n, c, tpl, src))
    for n, c, tpl, src in rows:
        _reset_processing(st, n)
    has_m = st.quantum and st.ses.has_mustard
    remaining = None
    if has_m and st.cap is not None:
        remaining = st.cap - sum(st.width(n) for n in st.numbers() if n not in ns and st.mustard_uses_modules(n))
    mplan, _ = process.mustard_plan([(n, c, st.width(n) == 2, tpl) for n, c, tpl, _ in rows],
                                    remaining if has_m else 0)
    if not has_m:
        mplan = {}
    over, flat = [], []
    for n, c, tpl, src in rows:
        idx = st.idx(n)
        if tpl is None:
            flat.append(n)
        else:
            w = process.write_template(st.ses, idx, tpl, st.width(n) == 2, mplan.get(n))
            if mplan.get(n) == 'over':
                over.append(n)
            for note in w.notes:
                if not any(x in note for x in ('Mustard comp replaces', 'no Mustard instance', 'single band')):
                    st.warn('%s: %s.' % (st.label(n), note))
        if has_m:
            m_on = st.mustard_uses_modules(n)
            st.ses.set_strip_view(idx, st.ses.VIEW_MUSTARD if m_on else st.ses.VIEW_SD)
            if not m_on:
                _set_tidal(st, n, -1)
    if over:
        st.warn('No Mustard instance left for %s: %s on the SD comp instead.' % (
            _who(st, over), 'its Mustard settings are' if len(over) == 1 else 'their Mustard settings are'))
    labels = taxonomy.labels()
    byc = {}
    for n, c, tpl, src in rows:
        if tpl is not None:
            byc.setdefault(labels.get(c, c), []).append(n)
    out = ['%s template on %s.' % (lab, _who(st, chs)) for lab, chs in byc.items()]
    if flat:
        out.append('No template for %s (category other), so %s flat now.' % (_who(st, flat), 'it is' if len(flat) == 1
                                                                             else 'they are'))
    out.append('Template values are starting points from real touring sessions. Check them at line check.')
    return out


# ---------------------------------------------------------------------------------------------------- structure
def _need_layout(st):
    if st.snapshots:
        raise Refuse(_snap_why(st))


def _spec(st, order=None, width=None, names=None):
    order = st.numbers() if order is None else order
    width, names = width or {}, names or {}
    return [{'name': names.get(n, st.name(n)), 'width': width.get(n, st.width(n)), 'idx': st.idx(n),
             'src': st.idx(n)} for n in order]


def _banks_standard(st):
    """True when the input banks are the editor's plain 12-per-bank layout in channel order."""
    try:
        bl = st.ses.banks()
    except (ValueError, struct.error):
        return False
    order = [st.idx(n) for n in st.numbers()]
    k = 0
    for b in bl:
        ins = [(t, i) for t, i in b['strips'] if t == st.ses.STRIP_INPUT]
        if not ins:
            break
        want = order[k:k + 12]
        if [i + 1 for t, i in b['strips'][:len(want)] if t == st.ses.STRIP_INPUT] != want:
            return False
        k += len(want)
    return k == len(order)


def _engine_msg(st, e):
    m = re.search(r'need (\d+) engine channels; this session has room for (\d+)', str(e))
    if m:
        return ('The %s has room for %s processing paths%s, and a stereo channel takes 2. This change needs %s.' % (
            st.console['name'], m.group(2), '' if st.quantum else ' next to its buses', m.group(1)))
    if 'input banks are not the first banks' in str(e):
        return ('This session keeps other banks in front of its input banks, so its banks can not be rebuilt here. '
                'Rebuild Banks on the console first, or change the layout there.')
    return _sentence(e)


def _clear_dead(st, dead_idx):
    """Zero every route that names a removed input (FX unit feeds, output sockets fed by its direct out, sidechain
    keys, Spice Rack links): the slots buses.REF_SLOTS lists. -> {object type: count}."""
    dead = {0x0100 | (i - 1) for i in dead_idx}
    hits = {}
    for oid, o in S.objects(st.ses).items():
        t = oid >> 8
        for module, slots in o.mods.items():
            for (param, band), q in slots.items():
                if not any((ot is None or ot == t) and m == module and pr == param for ot, m, pr in B.REF_SLOTS):
                    continue
                v = st.ses.d[q:q + 4]
                if v[0] == 0 and v[1] in (0, 1) and (v[2] | (v[3] << 8)) in dead:
                    st.ses.d[q:q + 4] = b'\0\0\0\0'
                    hits[t] = hits.get(t, 0) + 1
    return hits


def _freshen(st, idx, keep=()):
    """Make new channel idx a pristine default channel: every slot from the console's own default channel (sends
    off, no group but the master, unpatched, flat), its width slots kept. Without a default session the channel
    keeps relayout's clone and only its processing, sends and patch are cleared."""
    ses = st.ses
    c = ses.by_index[idx]
    b = st.base()
    master = ses.d[S.MASTER_ID_AT]
    zero = b'\0\0\0\0'
    for mod, rec in c.records.items():
        for (param, band), q in rec.slots.items():
            key = (mod, param, band)
            if key in keep:
                continue
            src = None
            if b:
                if mod == 0x02:
                    src = b['vals'].get((0x02, param, b['aux0']))
                elif mod == 0x03 and param == 0x09:
                    src = b['vals'].get((0x03, 0x09, b['master'])) if band == master else (
                        b['vals'].get((0x03, 0x09, b['grp_other'])) if b['grp_other'] is not None else zero)
                else:
                    src = b['vals'].get(key)
            elif (mod == 0x01 and param in (0x00, 0x0e)) or (mod == 0x0e and param == 0xfe):
                src = zero
            elif mod == 0x02 and param == S.S_LEVEL:
                src = struct.pack('<f', S.OFF_DB)
            elif mod == 0x02 and param == S.S_ON:
                src = zero
            if src is not None:
                ses.d[q:q + 4] = src
    if not b:
        n = next(n for n, i in ses.display.items() if i == idx)
        _reset_processing(st, n)
    w = 2 if c.records and ses.d[c.trailer + 40] == 2 else 1
    for (m, prm, bd), (mono, stv) in layout.STEREO_SLOTS.items():
        if ses.has_slot(idx, m, prm, bd):
            ses.set(idx, m, prm, bd, stv if w == 2 else mono)
    off = ses.chrec_off.get(idx)
    if off is not None and ses.d[off + 2] >= 0x58:
        struct.pack_into('<h', ses.d, off + 86, -1)


def _relayout(st, spec, dead=(), clones=()):
    """layout.relayout + the fixes every structural op needs. clones: spec positions whose channel is a copy of an
    existing one (a split's right side); other entries without 'idx' are new and get a default channel."""
    _need_layout(st)
    views = _views(st.ses)
    old = set(st.ses.by_index)
    std = _banks_standard(st)
    m_before = st.mustard_used() if st.quantum else 0
    try:
        data = layout.relayout(st.data(), spec)
    except ValueError as e:
        raise Refuse(_engine_msg(st, e))
    st.reload(data)
    st.structural = st.routing = True
    if dead:
        hits = _clear_dead(st, dead)
        if hits.get(FX.FX_TYPE):
            st.warn('An FX unit was fed from a removed channel\'s direct out. It has no input now.')
        if any(0x4d <= t <= 0x5f for t in hits):
            st.warn('An output socket was fed from a removed channel\'s direct out. It is unpatched now.')
    FX.restore_feed_modes(st.ses)
    clone_idx = set()
    for pos in clones:
        clone_idx.add(st.ses.display[pos + 1])
    for idx in sorted(set(st.ses.by_index) - old):
        if idx in clone_idx:
            off = st.ses.chrec_off.get(idx)
            if off is not None and st.ses.d[off + 2] >= 0x58:
                struct.pack_into('<h', st.ses.d, off + 86, -1)
            continue
        _freshen(st, idx)
    _reapply_views(st, views, old)
    if st.quantum and st.cap is not None:
        m_after = st.mustard_used()
        if m_after > st.cap and m_after > m_before:
            raise Refuse('That needs %d Mustard instances (a stereo channel uses 2), and the %s runs %d. Turn Mustard '
                         'off on %d channel%s first.' % (m_after, st.console['name'], st.cap, m_after - st.cap,
                                                         '' if m_after - st.cap == 1 else 's'))
    if not std:
        st.warn('The input banks are rebuilt in channel order, 12 strips a bank, as Rebuild Banks does.')


def _reapply_views(st, views, old):
    """After a bank rebuild (relayout copies the first input bank's view bytes to every new bank): each kept channel
    gets its old SD / M view back, new channels and empty strips the SD view."""
    for idx in st.ses.by_index:
        st.ses.set_strip_view(idx, views.get(idx, st.ses.VIEW_SD) if idx in old else st.ses.VIEW_SD)
    try:
        for b in st.ses.banks():
            if not any(t == st.ses.STRIP_INPUT for t, _ in b['strips']):
                continue
            for j, (t, _) in enumerate(b['strips']):
                if t == 0:
                    st.ses.d[b['view'] + j] = st.ses.VIEW_SD
    except (ValueError, struct.error):
        pass


def _spice_insert(st, n):
    c = st.ses.by_index[st.idx(n)]
    rec = c.records.get(0x08)
    if rec is None:
        return False
    for key in ((0xfe, 0), (0xfe, 1), (0x00, 0), (0x00, 1)):
        q = rec.slots.get(key)
        if q is not None and st.ses.d[q] == 0 and st.ses.d[q + 3] == 0x18 and st.ses.d[q + 1] <= 1:
            return True
    return False


def _after_width(st, idxs, w):
    """After channels (internal indices) changed width: polarity mask, alt input, FX feeds from their direct out."""
    k = _k()
    ses = st.ses
    for idx in idxs:
        if ses.has_slot(idx, *k['polarity']):
            v = ses.get(idx, *k['polarity'])
            if w == 2 and v == 1.0:
                ses.set(idx, *k['polarity'], 3.0)
            elif w == 1 and v not in (0.0, 1.0):
                ses.set(idx, *k['polarity'], 1.0 if int(v) & 1 else 0.0)
        if w == 2:
            rec = ses.by_index[idx].records.get(0x01)
            if rec is not None:
                if (0x00, 1) in rec.slots:
                    q = rec.slots[(0x00, 1)]
                    ses.d[q:q + 4] = b'\0\0\0\0'
                if (0x0e, 0) in rec.slots:
                    ses.set(idx, 0x01, 0x0e, 0, 0.0)
    # FX units fed from these channels' direct outs: L/R legs follow the width
    objs = S.objects(ses)
    for oid, o in objs.items():
        if oid >> 8 != FX.FX_TYPE or not o.has(FX.FX_MODULE, 0x00, 0) or not o.has(FX.FX_MODULE, 0x00, 1):
            continue
        q0, q1 = o.slot(FX.FX_MODULE, 0x00, 0), o.slot(FX.FX_MODULE, 0x00, 1)
        r0 = bytes(ses.d[q0:q0 + 4])
        if r0[0] != 0 or r0[3] != 0x01 or (r0[2] + 1) not in idxs:
            continue
        src = r0[2] + 1
        ses.d[q1:q1 + 4] = bytes((0, 1 if w == 2 else 0, src - 1, 0x01))
        if ses.has_slot(src, 0x0e, 0xe8, 0):
            ses.set(src, 0x0e, 0xe8, 0, 2.0 if w == 2 else 0.0)


def _right_side_notes(st, ns):
    """Warn when a stereo channel's right side lands on a socket another channel uses, or past its device."""
    others = None
    for n in ns:
        info = P.input_of(st.ses, n)
        r = info.get('main_ref')
        if not r or r['type'] == FX.FX_TYPE:
            continue
        try:
            right = P.right_socket(st.ses, P.find_input_socket(st.ses, r))
        except (ValueError, KeyError):
            st.warn('%s is stereo on the last socket of its device, so its right side is silent. Patch it on an '
                    'odd socket.' % st.label(n))
            continue
        if others is None:
            others = _main_refs(st, skip=set(ns))
        users = others.get((right['type'], right['idx']))
        if users:
            st.warn('%s takes %s as its right side, and %s is patched there too.' % (st.label(n), right['name'],
                                                                                   _who(st, users, 3)))


def _side_base(name):
    m = I.PAIR_RE.match(name.strip())
    if m and m.group(1).strip():
        return m.group(1).strip()
    return name.strip()


def _op_stereo(st, op):
    ns = _targets(st, op)
    on = True
    for key in ('stereo', 'on', 'value'):
        if key in op:
            on = bool(op[key])
            break
    if 'width' in op:
        on = int(op['width']) == 2
    if op.get('mono'):
        on = False
    _need_layout(st)
    if on:
        mono = [n for n in ns if st.width(n) == 1]
        pair = op.get('pair', op.get('merge'))
        if pair is None:
            pair = len(ns) == 2 and ns[1] == ns[0] + 1 and len(mono) == 2
        if pair:
            if len(ns) != 2 or ns[1] != ns[0] + 1:
                raise Refuse('A stereo pair is two channels next to each other, like 9 and 10.')
            if len(mono) != 2:
                raise Refuse('%s is already stereo.' % _who(st, [n for n in ns if n not in mono]))
            return _merge_pair(st, ns[0], ns[1], op.get('name'))
        if not mono:
            return ['%s %s already stereo.' % (_who(st, ns), 'is' if len(ns) == 1 else 'are')]
        sp = [n for n in mono if _spice_insert(st, n)]
        if sp:
            raise Refuse('%s has a Spice Rack insert, and a stereo channel needs two Spice Rack slots. Take the insert '
                         'off first.' % _who(st, sp))
        idxs = [st.idx(n) for n in mono]
        _relayout(st, _spec(st, width={n: 2 for n in mono}))
        _after_width(st, set(idxs), 2)
        nn = [n for n in st.numbers() if st.idx(n) in idxs]
        _right_side_notes(st, nn)
        return ['%s %s stereo now (the right side is the next input socket).' % (
            _who(st, nn), 'is' if len(nn) == 1 else 'are')]
    sts = [n for n in ns if st.width(n) == 2]
    if not sts:
        return ['%s %s already mono.' % (_who(st, ns), 'is' if len(ns) == 1 else 'are')]
    idxs = [st.idx(n) for n in sts]
    if op.get('split'):
        spec, clones, names = [], [], {}
        for n in st.numbers():
            if n in sts:
                base = _side_base(st.name(n))
                lname = _clean_name(base + ' L', n)[1]
                rname = _clean_name(base + ' R', n)[1]
                spec.append({'name': lname, 'width': 1, 'idx': st.idx(n), 'src': st.idx(n)})
                clones.append(len(spec))
                spec.append({'name': rname, 'width': 1, 'src': st.idx(n)})
                names[n] = (lname, rname)
            else:
                spec += _spec(st, [n])
        _relayout(st, spec, clones=clones)
        _after_width(st, set(idxs), 1)
        # the R copy: right socket, no FX direct-out feed of its own
        for pos in clones:
            rn = pos + 1
            left_n = rn - 1
            lr = P.input_of(st.ses, left_n).get('main_ref')
            if lr and lr['type'] != FX.FX_TYPE:
                try:
                    P.patch_input(st.ses, rn, {'type': lr['type'], 'idx': lr['idx'] + 1})
                except (KeyError, ValueError):
                    P.patch_input(st.ses, rn, None)
            ridx = st.idx(rn)
            if st.ses.has_slot(ridx, 0x0e, 0xfe, 0):
                q = st.ses.slot(ridx, 0x0e, 0xfe, 0)
                if st.ses.d[q + 3] == FX.FX_TYPE:
                    st.ses.d[q:q + 4] = b'\0\0\0\0'
                    st.ses.set(ridx, 0x0e, 0xe8, 0, 1.0)
        out = ['Split %s into L and R mono channels (the R channel copies the processing and sends, on the next '
               'input socket).' % ', '.join('%s' % '/'.join(v) for v in names.values())]
        return out
    _relayout(st, _spec(st, width={n: 1 for n in sts}))
    _after_width(st, set(idxs), 1)
    nn = [n for n in st.numbers() if st.idx(n) in idxs]
    return ['%s %s mono now (left input only).' % (_who(st, nn), 'is' if len(nn) == 1 else 'are')]


def _merge_pair(st, a, b, name=None):
    ia, ib = st.idx(a), st.idx(b)
    if _spice_insert(st, a):
        raise Refuse('%s has a Spice Rack insert, and a stereo channel needs two Spice Rack slots. Take the insert '
                     'off first.' % st.label(a))
    la, lb = st.label(a), st.label(b)
    base = name if name else _side_base(st.name(a))
    full, short, changed = _clean_name(base, a)
    pa, pb = P.input_of(st.ses, a), P.input_of(st.ses, b)
    sends_b = [s for s in S.read_sends(st.ses, b)]
    spec = []
    for n in st.numbers():
        if n == b:
            continue
        e = _spec(st, [n])[0]
        if n == a:
            e['width'], e['name'] = 2, short
        spec.append(e)
    _relayout(st, spec, dead={ib})
    _after_width(st, {ia}, 2)
    na = next(n for n in st.numbers() if st.idx(n) == ia)
    out = ['%s and %s are one stereo channel now: %d %s. It keeps %s processing, sends and patch; channels after it '
           'moved up one.' % (la, lb, na, short, la.split(' ', 1)[0] + "'s")]
    ra, rb = pa.get('main_ref'), pb.get('main_ref')
    if ra and ra['type'] != FX.FX_TYPE:
        want_r = {'type': ra['type'], 'idx': ra['idx'] + 1}
        if rb and (rb['type'], rb['idx']) != (want_r['type'], want_r['idx']):
            st.warn('%s was on %s. The stereo channel takes the socket after %s as its right side, so move that '
                    'source or repatch.' % (lb, pb.get('main'), pa.get('main')))
    elif rb and not ra:
        st.warn('%s was unpatched, so the stereo channel is unpatched. Patch its left side.' % la)
    if sends_b and not S.read_sends(st.ses, na):
        st.warn('%s had sends and %s did not. The stereo channel has none; add them again.' % (lb, la))
    _right_side_notes(st, [na])
    return out


def _op_move(st, op):
    ns = _targets(st, op)
    _need_layout(st)
    rest = [n for n in st.numbers() if n not in ns]
    if 'after' in op:
        m = int(_num(op['after'], 'The channel to move after'))
        if m == 0:
            i = 0
        elif m not in rest:
            raise Refuse('Channel %d is not one I can move after (it is being moved or does not exist).' % m)
        else:
            i = rest.index(m) + 1
    elif 'before' in op:
        m = int(_num(op['before'], 'The channel to move before'))
        if m not in rest:
            raise Refuse('Channel %d is not one I can move before (it is being moved or does not exist).' % m)
        i = rest.index(m)
    else:
        to = op.get('to', op.get('position'))
        if to is None:
            raise Refuse('Say where to move them: to a channel number, or after or before a channel.')
        to = int(_num(to, 'The new position'))
        if not 1 <= to <= len(st.numbers()):
            raise Refuse('Pick a position from 1 to %d.' % len(st.numbers()))
        i = min(to - 1, len(rest))
    order = rest[:i] + ns + rest[i:]
    if order == st.numbers():
        return ['%s %s already there.' % (_who(st, ns), 'is' if len(ns) == 1 else 'are')]
    labels = [st.label(n) for n in ns]
    idxs = [st.idx(n) for n in ns]
    _relayout(st, _spec(st, order))
    new = [n for n in st.numbers() if st.idx(n) in idxs]
    return ['Moved %s to %s. Processing, sends and patch moved with %s.' % (
        ', '.join(labels), ('channel %d' % new[0]) if len(new) == 1 else 'channels %s' % _nums(new),
        'it' if len(new) == 1 else 'them')]


def _op_add_channels(st, op):
    _need_layout(st)
    names = op.get('names')
    if names is not None and not isinstance(names, list):
        names = [names]
    count = op.get('count')
    count = int(_num(count, 'The channel count')) if count is not None else (len(names) if names else 1)
    if count < 1:
        raise Refuse('Add at least one channel.')
    if names and len(names) != count:
        raise Refuse('%d names for %d new channels.' % (len(names), count))
    cap = min(st.console['max_inputs'], layout.MAX_INPUT_IDS)
    nowc = len(st.numbers())
    if nowc + count > cap:
        raise Refuse('The %s holds %d inputs. This session has %d, so %d more do not fit.' % (
            st.console['name'], cap, nowc, count))
    stereo = bool(op.get('stereo'))
    after = op.get('after', op.get('at'))
    if after is None and op.get('position') is not None:
        after = int(_num(op['position'], 'The position')) - 1
    after = nowc if after is None else int(_num(after, 'The channel to add after'))
    if not 0 <= after <= nowc:
        raise Refuse('Pick a channel from 0 to %d to add after.' % nowc)
    base = op.get('name')
    new = []
    for k in range(count):
        pos = after + k + 1
        nm = names[k] if names else (('%s %d' % (base, k + 1)) if base and count > 1 else (base or 'Ch %d' % pos))
        full, short, changed = _clean_name(nm, pos)
        new.append({'name': short, 'width': 2 if stereo else 1, 'full': full})
    order = st.numbers()
    spec = _spec(st, order[:after]) + [{'name': e['name'], 'width': e['width']} for e in new] + \
        _spec(st, order[after:])
    old = set(st.ses.by_index)
    _relayout(st, spec)
    added = [n for n in st.numbers() if st.idx(n) not in old]
    out = ['Added %s%s (%s, %s).' % (_who(st, added), ' after channel %d' % after if after < nowc else '',
                                     'stereo' if stereo else 'mono', 'flat and unpatched')]
    cat = op.get('category', op.get('template'))
    if cat:
        out += _op_apply_template(st, {'target': {'channels': added}, 'category': 'auto' if cat is True else cat,
                                       'role': op.get('role')})[:-1]
    return out


def _op_remove_channels(st, op):
    ns = _targets(st, op)
    _need_layout(st)
    if len(ns) >= len(st.numbers()):
        raise Refuse('A session needs at least one input channel.')
    labels = _who(st, ns, 8)
    fxr = [n for n in ns if st.fx_unit_of(n) is not None]
    dead = {st.idx(n) for n in ns}
    _relayout(st, [e for e in _spec(st) if e['idx'] not in dead], dead=dead)
    if fxr:
        st.warn('Removed FX return%s. The FX unit%s still run%s with no return channel.' % (
            '' if len(fxr) == 1 else 's', '' if len(fxr) == 1 else 's', 's' if len(fxr) == 1 else ''))
    return ['Removed %s. The channels after %s moved up.' % (labels, 'it' if len(ns) == 1 else 'them')]


# ---------------------------------------------------------------------------------------------------- FX
def _aux_busy(st, a):
    """(input sends on, pre-fader sends on, feeds an FX unit) for aux a."""
    band = st.ses.aux_band[a]
    on = pre = 0
    for c in st.ses.inputs:
        rec = c.records.get(S.SEND)
        if rec is None or (S.S_LEVEL, band) not in rec.slots:
            continue
        lv = st.ses.get(c.index, S.SEND, S.S_LEVEL, band)
        if lv > S.OFF_DB and st.ses.get(c.index, S.SEND, S.S_ON, band) == 1.0:
            on += 1
            if (S.S_PREPOST, band) in rec.slots and st.ses.get(c.index, S.SEND, S.S_PREPOST, band) != 0.0:
                pre += 1
    b = S.bus(st.ses, 'aux', a)
    feeds = False
    for o in S._sides(b):
        if o.has(S.OUT, S.O_ROUTE):
            q = o.slot(S.OUT, S.O_ROUTE)
            feeds |= st.ses.d[q + 3] == FX.FX_TYPE
    return on, pre, feeds


def _name_bus(st, kind, n, name):
    """sends.name_bus with ses.records narrowed to the records that carry the bus's current names (fast on big
    files; the same copies get renamed)."""
    b = S.bus(st.ses, kind, n)
    olds = {b['name']}
    if b['robj'] is not None:
        olds.add(b['robj'].name)
    saved = st.ses.records
    st.ses.records = _records_named(st.ses, olds)
    try:
        return S.name_bus(st.ses, kind, n, name)
    finally:
        st.ses.records = saved


def _op_add_fx(st, op):
    kind = op.get('kind', op.get('fx', op.get('preset', op.get('type')))) or 'hall'
    try:
        choice = O.fx_choice(kind)
        preset, uname, short, role, label = O.FX_CHOICES[choice]
    except ValueError:
        try:
            lib = FX._Doc(st.ses.d)
            pi = FX.resolve_preset(lib.lib, lib.kinds, str(kind))
        except ValueError as e:
            raise Refuse(_sentence(e))
        preset = uname = lib.lib[pi]['name']
        short, role, label = uname[:8], None, uname
    have = [u['name'] for u in FX.units(st.ses)]
    name = O._ascii(op.get('name') or '')[:24] or uname
    if not op.get('name') and name in have:
        k = 2
        while '%s %d' % (uname, k) in have:
            k += 1
        name = '%s %d' % (uname, k)
    a = op.get('aux', op.get('feed_aux'))
    if a is not None:
        aux = _aux_number(st, a)
        son, spre, feeds = _aux_busy(st, aux)
        if feeds:
            raise Refuse('%s already feeds an FX unit. Pick another aux.' % _aux_label(st, aux))
        if spre >= 2:
            st.warn('%s carries %d pre-fader sends (it looks like a monitor mix). It feeds the %s now too.' % (
                _aux_label(st, aux), spre, name))
    else:
        aux = None
        for x in st.ses.auxes:
            if x['width'] != 1:
                continue
            son, spre, feeds = _aux_busy(st, x['number'])
            if not son and not feeds:
                aux = x['number']
                break
        if aux is None:
            raise Refuse('Every mono aux is in use. Say which aux feeds the %s, for example "on aux 5".' % label)
    ret = op.get('return', 'new')
    ret = 'new' if ret in (None, 'auto', True) else ret
    if ret not in ('new', 'none', False):
        ret = int(_num(ret, 'The return channel'))
        if ret not in st.ses.display:
            raise Refuse('This session has %d channels, so there is no channel %d.' % (len(st.numbers()), ret))
    if ret == 'new' or (isinstance(ret, int) and st.width(ret) == 1):
        _need_layout(st)
    views = _views(st.ses)
    old = set(st.ses.by_index)
    son_before = _aux_busy(st, aux)[0]
    rname = short
    if ret == 'new':
        taken = {st.name(n).lower() for n in st.numbers()}
        rname = O._short(short, taken)
    try:
        unit = FX.add_fx(st.ses, preset, feed_aux=aux,
                         return_to=None if ret in ('none', False) else ('fx_return' if ret == 'new' else ('input', ret)),
                         name=name, return_name=rname, make_stereo=True)
    except ValueError as e:
        raise Refuse(_sentence(e))
    O._fresh(st.ses)
    st.routing = True
    if set(st.ses.by_index) != old or ret == 'new' or isinstance(ret, int):
        st.structural = True
        new = sorted(set(st.ses.by_index) - old)
        for idx in new:
            _freshen(st, idx, keep={(0x01, 0x00, 0)})
            st.ses.rename(idx, rname[:8])
        _reapply_views(st, views, old)
    _name_bus(st, 'aux', aux, name)
    S.set_bus_fader(st.ses, 'aux', aux, db=0.0, mute=False)
    out = []
    rch = [r['input'] for u in FX.units(st.ses) if u['unit'] == unit for r in u['returns']]
    out.append('Added FX %d: %s (%s), fed by aux %d (renamed %s, master at 0 dB)%s.' % (
        unit, name, preset, aux, name, (', returning on %s' % _who(st, rch)) if rch else ', no return channel'))
    sends = op.get('sends', 'auto')
    if sends != 'none' and role and not son_before:
        table = O.FX_SENDS.get(role, {})
        chans = [n for n in st.numbers() if st.cat(n) in table and n not in rch]
        if role == 'delay' and not chans:
            chans = [n for n in st.numbers() if st.cat(n) == 'vocal_generic'][:1]
            table = dict(table, vocal_generic=0.0)
        for n in chans:
            S.set_send(st.ses, n, aux, table[st.cat(n)], on=True, pre='post')
        if chans:
            out.append('Post-fader sends to the %s from %s, at the levels engineers use in the real sessions.' % (
                name, _who(st, chans)))
        else:
            out.append('No channel here is a usual source for a %s, so no sends were added.' % label.lower())
    return out


def _op_remove_fx(st, op):
    units = FX.units(st.ses)
    if not units:
        raise Refuse('This session has no FX units.')
    want = op.get('unit', op.get('n', op.get('number')))
    if want is None and op.get('name'):
        nm = str(op['name']).strip().lower()
        hit = [u for u in units if u['name'].strip().lower() == nm] or \
            [u for u in units if nm in u['name'].strip().lower()]
        if len(hit) != 1:
            raise Refuse('No FX unit is called %r.' % op['name'] if not hit else '%r matches FX %s. Say the number.'
                         % (op['name'], _nums([u['unit'] for u in hit])))
        u = hit[0]
    else:
        if want is None:
            raise Refuse('Say which FX unit to remove, by number or name.')
        want = int(_num(want, 'The FX unit'))
        u = next((x for x in units if x['unit'] == want), None)
        if u is None:
            raise Refuse('This session has FX 1 to %d, so there is no FX %d.' % (len(units), want))
    rets = [r['input'] for r in u['returns']]
    if op.get('remove_return') and rets:
        _need_layout(st)
    cid, k = u['id'], u['id'] & 0xff
    d = FX._Doc(st.ses.d)
    FX._clear_stale(d, cid, set())            # every output that names the unit: route cleared, mono mode back
    for oid, o in d.obj.items():              # inputs patched to its return
        if oid >> 8 != 0x01:
            continue
        q = layout.obj_slot(o, 0x01, 0x00, 0)
        if q is not None and o[q] == 0 and o[q + 3] == FX.FX_TYPE and o[q + 2] == k:
            o[q:q + 4] = b'\0\0\0\0'
    cbs = d.fx_cbs()
    p, r = next((p, r) for p, r in cbs if struct.unpack_from('<H', r, 4)[0] == cid)
    num = struct.unpack_from('<H', r, 6)[0]
    del d.s201[p:p + len(r)]
    struct.pack_into('<I', d.s201, d.gq + 0x70, len(cbs) - 1)
    for q, rr in d.fx_cbs():
        nn = struct.unpack_from('<H', d.s201, q + 6)[0]
        if nn > num:
            struct.pack_into('<H', d.s201, q + 6, nn - 1)
    del d.obj[cid]
    st.reload(d.build())
    st.structural = st.routing = True
    feeds = ', '.join(dict.fromkeys('aux %d' % f['aux'] for f in u.get('feed') or [] if f.get('aux')))
    out = ['Removed FX %d (%s)%s.' % (u['unit'], u['name'], (', fed by ' + feeds) if feeds else '')]
    if rets:
        if op.get('remove_return'):
            out += _op_remove_channels(st, {'target': {'channels': rets}})
        else:
            st.warn('%s returned the %s and %s unpatched now.' % (_who(st, rets), u['name'],
                                                                 'is' if len(rets) == 1 else 'are'))
    if len(units) > u['unit']:
        out.append('FX units after it moved up one in the rack.')
    return out


# ---------------------------------------------------------------------------------------------------- buses, mixes
def _layout_now(st):
    return B.describe(st.data())


def _restructure(st, am, ast, gm, gs):
    if st.snapshots:
        raise Refuse(_snap_why(st))
    views = _views(st.ses)
    try:
        data = B.restructure(st.data(), am, ast, gm, gs, console=st.key)
    except ValueError as e:
        msg = str(e)
        m = re.search(r'needs (\d+) busses .*console has (\d+)', msg)
        if m:
            raise Refuse('The %s has %s bus slots (a stereo bus takes 2, the Master takes 2). That layout needs %s.'
                         % (st.console['name'], m.group(2), m.group(1)))
        raise Refuse('That bus layout does not work on this session: %s' % _sentence(msg))
    st.reload(data)
    st.structural = st.routing = True
    for idx, v in views.items():
        if idx in st.ses.by_index:
            st.ses.set_strip_view(idx, v)


def _op_buses(st, op):
    cur = _layout_now(st)
    want = [op.get(k, cur[k]) for k in ('aux_mono', 'aux_stereo', 'grp_mono', 'grp_stereo')]
    want = [int(_num(x, 'A bus count', 0, 128)) for x in want]
    if tuple(want) == (cur['aux_mono'], cur['aux_stereo'], cur['grp_mono'], cur['grp_stereo']):
        return ['The bus layout is already %d mono + %d stereo auxes, %d mono + %d stereo groups.' % tuple(want)]
    used = []
    for a in st.ses.auxes:
        on, pre, feeds = _aux_busy(st, a['number'])
        if on or feeds:
            used.append(a)
    _restructure(st, *want)
    d = _layout_now(st)
    out = ['Bus layout: %d mono + %d stereo auxes, %d mono + %d stereo groups (Master included).' % (
        d['aux_mono'], d['aux_stereo'], d['grp_mono'], d['grp_stereo'])]
    gone = [a for a in used if (a['width'] == 1 and a['number'] > want[0]) or
            (a['width'] == 2 and a['number'] - cur['aux_mono'] > want[1])]
    if gone:
        st.warn('Removed aux%s %s had sends or fed an FX unit.' % ('' if len(gone) == 1 else 'es', ', '.join(
            '%d %s' % (a['number'], a['name']) for a in gone)))
    return out


def _op_mixes(st, op):
    try:
        mx = O.normalize({'mixes': {k: op.get(k) for k in ('stereo', 'mono', 'click', 'outputs', 'names')
                                    if op.get(k) is not None}}).get('mixes')
    except ValueError as e:
        raise Refuse(_sentence(e))
    if not mx:
        raise Refuse('Say how many IEM (stereo) or wedge (mono) mixes.')
    need_s, need_m = mx['stereo'], mx['mono']

    def free(width):
        out = []
        for a in st.ses.auxes:
            if a['width'] != width:
                continue
            on, pre, feeds = _aux_busy(st, a['number'])
            if not on and not feeds:
                out.append(a['number'])
        return out
    fs, fm = free(2), free(1)
    if len(fs) < need_s or len(fm) < need_m:
        cur = _layout_now(st)
        add_s, add_m = max(0, need_s - len(fs)), max(0, need_m - len(fm))
        limit = B.bus_limit(st.data(), st.key)
        am, ast, gm, gs = cur['aux_mono'] + add_m, cur['aux_stereo'] + add_s, cur['grp_mono'], cur['grp_stereo']
        width = lambda: am + 2 * ast + gm + 2 * gs  # noqa: E731
        took = []
        if limit is not None and width() > limit:
            # take back unused buses from the end of each class (restructure removes from the end), mono auxes first,
            # then mono groups, then stereo groups (never the Master), as the builder's automatic layout does
            spare = 0 if add_m else len(fm) - need_m
            k = _trailing_unused(st, 'aux', 1, spare)
            while k and width() > limit:
                am, k = am - 1, k - 1
                took.append('mono aux')
            k = _trailing_unused(st, 'group', 1, gm)
            while k and width() > limit:
                gm, k = gm - 1, k - 1
                took.append('mono group')
            k = _trailing_unused(st, 'group', 2, gs - 1)
            while k and width() > limit:
                gs, k = gs - 1, k - 1
                took.append('stereo group')
        if limit is not None and width() > limit:
            raise Refuse('The %s has %d bus slots (a stereo bus takes 2, the Master takes 2). %s need%s %s, and the '
                         'session has no unused buses left to take back. Use fewer mixes, or free some auxes first.' % (
                             st.console['name'], limit, O._needs_text({'mixes': mx}),
                             's' if need_s + need_m == 1 else '', O._auxes_text(need_m, need_s)))
        _restructure(st, am, ast, gm, gs)
        msg = 'Added %s to make room for the mixes' % O._auxes_text(add_m, add_s)
        if took:
            from collections import Counter
            msg += ', and took back %s that nothing used' % ' and '.join(
                '%d %s%s' % (c, w, '' if c == 1 else ('es' if w.endswith('aux') else 's'))
                for w, c in Counter(took).items())
        st.warn(msg + '.')
        fs, fm = free(2), free(1)
    plan = [{'n': n, 'name': st.name(n), 'full_name': st.name(n), 'category': st.cat(n), 'stereo': st.width(n) == 2,
             'fx_return': st.fx_unit_of(n) is not None} for n in st.numbers()]
    mixes = O._mix_plan(mx, plan)
    its, itm = iter(fs), iter(fm)
    for m in mixes:
        m['aux'] = next(its) if m['stereo'] else next(itm)
    st.routing = True
    for m in mixes:
        if m['stereo']:
            S.set_link_pans(st.ses, m['aux'], 'on')
    chans = [{'n': p['n'], 'name': p['name'], 'category': p['category'], 'stereo': p['stereo']} for p in plan
             if not p['fx_return']]
    for m in mixes:
        _name_bus(st, 'aux', m['aux'], m['name'][:S.NAME_MAX])
    for m in mixes:                                     # monitor_mixes without its own rename (done above, fast)
        S.set_bus_fader(st.ses, 'aux', m['aux'], db=0.0, mute=False)
        _mix_sends(st, m, chans)
    out = ['%s on aux %s: %s. Every channel goes pre-fader at a starting level, each player\'s own channels 6 dB up%s.'
           % (O._needs_text({'mixes': mx})[:1].upper() + O._needs_text({'mixes': mx})[1:],
              _nums([m['aux'] for m in mixes]), ', '.join(m['name'] for m in mixes),
              ', stereo mixes with link pans on' if need_s else '')]
    if mx.get('outputs'):
        picks = O._pick_outputs(st.ses, mixes)
        done = []
        for m in mixes:
            socks = picks.get(m['aux'])
            if not socks:
                continue
            S.patch_output(st.ses, 'aux', m['aux'], {'type': socks[0]['type'], 'idx': socks[0]['idx']},
                           {'type': socks[1]['type'], 'idx': socks[1]['idx']} if len(socks) > 1 else None)
            done.append('%s on %s' % (m['name'], '/'.join(s['name'] for s in socks)))
        if done:
            out.append('Mix outputs: %s.' % ', '.join(done))
        left = [m['name'] for m in mixes if m['aux'] not in picks]
        if left:
            st.warn('No free line outputs left for %s. Patch %s on the console.' % (
                ', '.join(left), 'it' if len(left) == 1 else 'them'))
    return out


def _bus_used(st, kind, n):
    """True when bus n carries anything: an aux with input sends on, an FX feed or output patch; a group that is the
    Master, has inputs or other groups routed to it, or output patch."""
    try:
        if any(S.outputs_of(st.ses, kind, n)):
            return True
    except (KeyError, ValueError):
        return True
    if kind == 'aux':
        on, pre, feeds = _aux_busy(st, n)
        return bool(on or feeds)
    if n == S.master_group(st.ses):
        return True
    band = st.ses.group_band[n]
    for c in st.ses.inputs:
        rec = c.records.get(S.GROUPS)
        if rec is not None and (S.G_ASSIGN, band) in rec.slots and st.ses.get(c.index, S.GROUPS, S.G_ASSIGN, band) > .5:
            return True
    for g in st.ses.groups:
        if g['number'] != n and n in S.bus_routes(st.ses, g['number']):
            return True
    return False


def _trailing_unused(st, kind, width, most):
    """How many buses of this kind and width, counted back from the last one, carry nothing (at most `most`)."""
    lst = [x['number'] for x in (st.ses.auxes if kind == 'aux' else st.ses.groups) if x['width'] == width]
    k = 0
    for n in reversed(lst):
        if k >= most or _bus_used(st, kind, n):
            break
        k += 1
    return k


def _mix_sends(st, m, chans):
    """sends.monitor_mixes for one mix, without its name_bus (the caller renames through _name_bus)."""
    a = m['aux']
    stereo_aux = next(x['width'] for x in st.ses.auxes if x['number'] == a) == 2
    linked = stereo_aux and S.link_pans(st.ses, a) in (1, 2)
    own = set(m.get('own', []))
    for c in chans:
        cat = c.get('category') or 'other'
        level = float(S.MIX_BASE.get(cat, S.MIX_BASE['other']))
        if cat in S.ONLY_ON_REQUEST and not m.get('click'):
            level = S.OFF_DB
        elif level > S.OFF_DB and c['n'] in own:
            level = min(S.MAX_DB, level + S.OWN_BOOST)
        if level <= S.OFF_DB:
            S.set_send(st.ses, c['n'], a, S.OFF_DB, on=False, pre='pre')
            continue
        pan = None
        if stereo_aux and not linked and not c.get('stereo'):
            pan = st.ses.get(st.ses.ch(c['n']), 0x0d, 0x23, 0)
        S.set_send(st.ses, c['n'], a, level, on=True, pre='pre', pan=pan)


def _op_name_bus(st, op):
    kind = str(op.get('kind', 'aux')).strip().lower()
    kind = {'grp': 'group', 'groups': 'group', 'auxes': 'aux', 'mtx': 'matrix'}.get(kind, kind)
    if kind not in S.KINDS:
        raise Refuse('A bus is an aux, a group or a matrix.')
    n = op.get('n', op.get('number', op.get('bus', op.get('aux'))))
    if kind == 'aux':
        n = _aux_number(st, n)
    else:
        n = int(_num(n, 'The %s number' % kind))
    name = O._ascii(op.get('name') or '')
    if not name:
        raise Refuse('Say the new name.')
    if len(name) > S.NAME_MAX:
        raise Refuse('Bus names are %d characters at most.' % S.NAME_MAX)
    try:
        old = S.bus(st.ses, kind, n)['name']
        _name_bus(st, kind, n, name)
    except (KeyError, ValueError) as e:
        raise Refuse(_sentence(e))
    dflt = old.strip().lower() in ('%s %d' % (kind, n), 'grp %d' % n, 'mtx %d' % n, '')
    return ['Renamed %s %d%s to %s.' % (kind.capitalize(), n, '' if dflt else ' (%s)' % old.strip(), name)]


# ---------------------------------------------------------------------------------------------------- the pipeline
HANDLERS = {'set': _op_set, 'rename': _op_rename, 'stereo': _op_stereo, 'move': _op_move,
            'add_channels': _op_add_channels, 'remove_channels': _op_remove_channels,
            'apply_template': _op_apply_template, 'send': _op_send, 'patch': _op_patch, 'preamp': _op_preamp,
            'add_fx': _op_add_fx, 'remove_fx': _op_remove_fx, 'mixes': _op_mixes, 'buses': _op_buses,
            'name_bus': _op_name_bus}
OP_ALIASES = {'add_channel': 'add_channels', 'remove_channel': 'remove_channels', 'delete_channels': 'remove_channels',
              'template': 'apply_template', 'sends': 'send', 'gain': 'preamp', 'mix': 'mixes', 'bus_layout': 'buses',
              'rename_bus': 'name_bus', 'pair': 'stereo'}


def _checks(st):
    """(validate errors, route / patch errors) of the current bytes."""
    d = st.data()
    try:
        errs, _ = validate.check(d)
    except Exception as e:  # noqa: BLE001
        errs = ['structure check failed (%s)' % type(e).__name__]
    rerrs = []
    try:
        rerrs = S.route_errors(st.ses) + P.patch_errors(st.ses)
    except Exception:  # noqa: BLE001 - a reader gap on an odd real session is not a new error
        pass
    return errs, rerrs


def open_session(data, console_key=None):
    """Read a session for editing. -> {'model', 'warnings'}. ValueError with a plain sentence when the file can not
    be opened (not a DiGiCo session, damaged, a console we do not know)."""
    try:
        st = _State(data, console_key)
        model = _model(st)
    except I.Stop as e:
        raise ValueError(e.msg)
    except Refuse as e:
        raise ValueError(str(e))
    except (struct.error, IndexError, KeyError, StopIteration) as e:
        raise ValueError('This DiGiCo session is damaged or in a layout we can not read yet (%s).' % type(e).__name__)
    warns = []
    if st.key_note:
        warns.append(st.key_note)
    if st.snapshots:
        warns.append(_snap_why(st))
        warns.append('Edits change the live settings. Each snapshot keeps its stored values, so update the snapshots '
                     'on the console after loading.')
    if not model['structure']['ok']:
        warns.append('The structure check found problems in this file (see the readout). Edits keep them as they are.')
    return {'model': model, 'warnings': warns}


def apply_ops(data, ops, console_key=None):
    """Apply edit ops in order. Pure: the same input gives the same bytes. Never raises on a weird session: an op
    that fails is refused with a sentence and the file stays as it was before that op."""
    data = bytes(data)
    if isinstance(ops, dict):
        ops = [ops]
    ops = list(ops or [])
    try:
        st = _State(data, console_key)
    except Exception as e:  # noqa: BLE001
        why = str(e) if isinstance(e, Refuse) else e.msg if isinstance(e, I.Stop) else \
            'This file can not be edited (%s).' % type(e).__name__
        return {'data': data, 'model': None, 'changes': [], 'warnings': [why],
                'refused': [{'op': o, 'why': why} for o in ops]}
    if st.key_note:
        st.warn(st.key_note)
    base_errs, base_route = _checks(st) if ops else ([], [])
    changes, refused = [], []
    for op in ops:
        before, w0 = st.data(), len(st.warnings)
        st.structural = st.routing = False
        try:
            if not isinstance(op, dict):
                raise Refuse('Each change must be an object with an "op".')
            name = OP_ALIASES.get(str(op.get('op', '')).strip().lower(), str(op.get('op', '')).strip().lower())
            h = HANDLERS.get(name)
            if h is None:
                raise Refuse('I do not know the change %r. I know: %s.' % (op.get('op'), ', '.join(HANDLERS)))
            msgs = h(st, op)
            if st.structural or st.routing:
                errs, rerrs = _checks(st)
                new = [e for e in errs if e not in base_errs]
                if new:
                    raise Refuse('That change would leave the file inconsistent (%s), so it was not made.' %
                                 I._plain(new[0]).rstrip('.'))
                newr = [e for e in rerrs if e not in base_route]
                if newr:
                    raise Refuse('That change would leave the patch inconsistent (%s), so it was not made.' %
                                 newr[0].rstrip('.'))
            changes.extend(msgs)
        except Refuse as e:
            st.reload(before)
            del st.warnings[w0:]
            refused.append({'op': op, 'why': str(e)})
        except Exception as e:  # noqa: BLE001 - never crash on a weird real session
            st.reload(before)
            del st.warnings[w0:]
            refused.append({'op': op, 'why': 'That change could not be made on this session (%s: %s).' % (
                type(e).__name__, str(e)[:120])})
    out = st.data()
    try:
        model = _model(st)
    except Exception as e:  # noqa: BLE001 - the edits left a file the reader refuses: give back the original
        try:
            st.reload(data)
            m0 = _model(st)
        except Exception:  # noqa: BLE001 - the original does not read either
            m0 = None
        return {'data': data, 'model': m0, 'changes': [], 'warnings': list(st.warnings),
                'refused': [{'op': o, 'why': 'The edited file did not read back (%s), so nothing was changed.' %
                             _sentence(e).rstrip('.')} for o in ops]}
    return {'data': out, 'model': model, 'changes': changes, 'warnings': list(st.warnings), 'refused': refused}


# ---------------------------------------------------------------------------------------------------- CLI
def main(argv):
    if len(argv) < 3:
        print("usage: python3 -m sessionmaker.edit <in.ses> '<ops json>' [out.ses]", file=sys.stderr)
        return 2
    data = open(argv[1], 'rb').read()
    ops = json.loads(open(argv[2]).read() if os.path.exists(argv[2]) else argv[2])
    t0 = time.perf_counter()
    res = apply_ops(data, ops)
    ms = (time.perf_counter() - t0) * 1000
    for c in res['changes']:
        print('+ ' + c)
    for w in res['warnings']:
        print('! ' + w)
    for r in res['refused']:
        print('x %s: %s' % (r['op'].get('op') if isinstance(r['op'], dict) else r['op'], r['why']))
    if len(argv) > 3:
        with open(argv[3], 'wb') as f:
            f.write(res['data'])
    print('%.0f ms, %d bytes' % (ms, len(res['data'])))
    return 1 if res['refused'] else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
