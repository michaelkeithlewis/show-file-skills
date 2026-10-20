#!/usr/bin/env python3
"""fx.py - SD FX units (reverbs, delays, choruses, pitch shifters) in a DiGiCo session, written by bytes.

Decoded from the Quantum 225 V2242 editor's own edit (an editor-made baseline before and after the edit: 3 reverbs fed by aux
1-3, returning on inputs 48-50), the 14 V2242 default sessions and the FX units in 39 real sessions (V1455-V2025).
Write-up with offsets and editor proofs: the decode notes (not published).

An FX unit lives in four places:
  section 219  preset library: 'db 00' | u32 entry count | entries. An entry is 'd7 00 01 00 00 00' + a library object
               ('d5 00 01 00 01' | u32 1 | one module record of type 0x15 named "FX 1" | ff*8 00*4 | '27 00' | id 0x0e00
               | name[32] | ff ff ff ff | 01) + u16-length preset name + u16-length group name ("Room Reverbs")
               + 12 bytes ('00 00 0e 00' + TDateTime, 0 on factory presets) + 02 (factory) + u16 preset UID + u16 1
               + 00. Every V2242 default holds the same 34 factory FX presets at entries 0-33 (Quantum files add 8
               Chilli 6 presets after them).
  section 201  one channel record (cb) per unit in the 'FX' group (type 0x0e, present with count 0 in every default):
               a mono aux record with id 0x0e00|k, number = rack position, name = preset name, +41 width 02,
               +42 i32 library index of the preset (-1 = none), +84 EngineChannel (2 per unit).
  section 211  one live object per unit, sorted by id between TB In (0x0c00) and the matrix inputs (0x0f00):
               'd5 00 01 00 01' | u32 1 | the library record renamed to the preset, count + 1, live byte +57 = 01,
               slot (f0,0) = 0 inserted after (05,0), (ff,0) = 1.0 | ff*8 00*4 | '27 00' | id | name[32]
               | i32 library index | 02.
  routing      the unit's inputs are its slots (00,0) L and (00,1) R, raw '00 00 <idx> <type>' (05 aux, 07 right
               side of a stereo aux, 01 input channel). The aux names the unit on its output module:
               (0e,fe,0) = '00 <side> <k> 0e', and a mono aux feeding both sides has (0e,e8,0) = 0.0 (mono > stereo).
               A return is an input channel whose main input (01,00,0) is '00 00 <k> 0e' (a real session also has
               '00 01 <k> 0e', read as the right output only).
               DiGiCo SD/Quantum consoles have no separate FX return path; returns are input channels.
Slot (80,0) on the record is the preset UID (the same number ends the library entry).

API (all take a ses.py Session, edit ses.d in place and re-parse it):
  list_presets(ses)                       -> [{index, name, category, kind, uid, slots}]
  units(ses)                              -> [{unit, id, name, preset, engine, kind, feed, returns, params}]
  add_fx(ses, preset, feed_aux=None, return_to=None, name=None, return_name=None, make_stereo=True,
         feed_input=None)                -> unit number (1-based rack position)
  feed_from_aux(ses, unit, aux) / feed_from_input(ses, unit, n) / return_to_input(ses, unit, n)
  set_fx_params(ses, unit, **params)      -> {key: value written}
  restore_feed_modes(ses)                 -> inputs fixed; call after any layout.relayout() of a session whose FX
                                             units are fed from mono input direct outs (relayout resets their
                                             mono > stereo output mode to 1.0)
"""
import os
import re
import struct
import sys

try:
    from . import layout
except ImportError:                       # run as a plain script
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import layout  # noqa: E402

FX_TYPE = 0x0e          # section 201 record type, object id high byte and patch source type of an FX unit
FX_MODULE = 0x15        # module record type of an FX unit
T_AUX, T_RIGHT = 0x05, 0x07
LIVE_FLAG = 57          # record header byte: 01 on live records, 00 on library copies
MAX_UNITS = 32          # FX ids are 0x0e00 | k; the editors kept 32 units (largest real session: 15 units)
POOL_UNITS = 16         # units with DSP per pool (reverbs / other effects): the editors give a 17th reverb no DSP

# The categories of the factory presets. FPGA reverbs and the other effects use separate DSP pools (EngineChannel).
REVERB_GROUPS = ('Hall Reverbs', 'Room Reverbs', 'Plate Reverbs', 'Non-Lin Reverbs')
KIND_OF_GROUP = {'Hall Reverbs': 'reverb', 'Room Reverbs': 'reverb', 'Plate Reverbs': 'reverb',
                 'Non-Lin Reverbs': 'reverb', 'Delays': 'delay', 'Choruses': 'chorus',
                 'Pitch Shifters': 'pitch', 'Specials': 'special'}
# EngineChannel of the first unit in each pool, by file family: reverbs at 128 (Quantum) or 64 (SD), the other
# effects at 0, 2 per unit, in rack order (real sessions V1455-V2025, the V2242 editor's own v4 edit and the
# editor proofs in the decode notes (not published). engine_slots() has the full order.
QUANTUM_FAMILIES = layout.QUANTUM_FAMILIES
REVERB_BASE = {'quantum': 128, 'sd': 64}
# Quantum families whose other-effects pool stops at 26: the Quantum 112 V2242 editor gives a 15th and 16th
# non-reverb unit EngineChannel -1 (no DSP) whether they are written at 64/66 or at 28/30 (verifier probes,
# q112_v2242_cap and results_probe.jsonl q112_v2242_capsd).
SHORT_OTHER_POOL = {'Q1'}

# Friendly names for kind and preset words -> factory preset name.
KIND_PRESET = [
    (r'^(hall|large hall|big hall|reverb)$', 'Large hall'),
    (r'^(warm hall)$', 'Warm hall'), (r'^(stage hall)$', 'Stage hall'), (r'^(ambient hall)$', 'Ambient hall'),
    (r'^(cathedral|church)$', 'Cathedral'),
    (r'^(room|live room)$', 'Live room'), (r'^(wood room)$', 'Wood room'), (r'^(clear room)$', 'Clear room'),
    (r'^(drum room|percussion room)$', 'Percussion room'), (r'^(small room|practice room)$', 'Practice room'),
    (r'^(plate|medium plate)$', 'Medium Plate'), (r'^(short plate|tight plate)$', 'Short Plate'),
    (r'^(vocal plate|vox plate|long plate)$', 'Vocal Plate'), (r'^(drum plate|snare plate)$', 'Drum Plate'),
    (r'^(percussion plate)$', 'Percussion Plate'),
    (r'^(gated|gate|non-?lin(ear)?)$', 'Non-Linear'), (r'^(ambience)$', 'Non-Linear Ambience'),
    (r'^(reverse)$', 'Reverse Ambience'), (r'^(kick ambience)$', 'Kick Ambience'),
    (r'^(delay|studio delay|tap delay)$', 'Studio delay'), (r'^(slap|slapback|simple delay)$', 'Simple delay'),
    (r'^(ten ?tap|multi ?tap)$', 'TenTap delay'),
    (r'^(chorus|guitar chorus)$', 'Guitar chorus'), (r'^(piano chorus)$', 'Piano chorus'),
    (r'^(string chorus|wide chorus)$', 'Wide String chorus'),
    (r'^(thicken|doubler|vocal thicken|adt)$', 'Vocal Thicken'), (r'^(unison|vocal unison)$', 'Vocal Unison'),
    (r'^(octave|octave down|octaver)$', 'Octave Down'), (r'^(enhancer|audio enhancer)$', 'Audio Enhancer'),
]

# Named parameters -> (param, band) on the type 0x15 record. Every name was matched to its control on the V2242
# editor's FX rack display. predelay, lo/hi_filter, hi_damping, decay, time, feedback and mix
# were also written, booted and re-saved unchanged on 18 console/firmware pairs (decode notes, not published).
PARAMS = {
    'reverb': {'early_reflect': (0x2e, 0), 'predelay': (0x0f, 0), 'lo_filter': (0x14, 1), 'hi_filter': (0x14, 0),
               'hi_damping': (0x37, 0), 'decay': (0x12, 0), 'mix': (0x01, 0)},
    'delay': {'time': (0x02, 0), 'feedback': (0x03, 0), 'mix': (0x01, 0)},
    'chorus': {'delay': (0x11, 0), 'depth': (0x03, 0), 'mix': (0x01, 0)},
    'pitch': {'pitch_left': (0x02, 0), 'pitch_right': (0x02, 1), 'mix': (0x01, 0)},
    'special': {'mix': (0x01, 0)},
}
# Keys whose meaning depends on the preset (same key, different control on the rack display).
PRESET_PARAMS = {
    'Studio delay': {'hi_pass': (0x06, 0), 'lo_pass': (0x06, 16)},
    'Simple delay': {'lo_pass': (0x06, 0)},
}
UNITS = {'early_reflect': 'dB', 'predelay': 's', 'decay': 's', 'time': 's', 'lo_filter': 'Hz', 'hi_filter': 'Hz',
         'hi_damping': 'Hz', 'mix': '%', 'feedback': '%', 'hi_pass': 'Hz', 'lo_pass': 'Hz', 'delay': 's',
         'depth': 's', 'pitch_left': 'ratio', 'pitch_right': 'ratio'}


# ---------------------------------------------------------------------------------------------------- helpers
def _f(b, p):
    return struct.unpack_from('<f', b, p)[0]


def _sstr31(name):
    return layout.sstr31(name)


def _reload(ses, data):
    ses.d = bytearray(data)
    ses._parse()


def _family(data):
    return bytes(data[11:15]).decode('latin1').strip()


def _rec_slots(b, p):
    """[(param, band, offset of the 8-byte slot)] of the module record at p."""
    cnt = struct.unpack_from('<H', b, p + 0x30)[0]
    s0 = p + 4 + 0x3a
    return [(b[s0 + 8 * k], b[s0 + 8 * k + 2], s0 + 8 * k) for k in range(cnt)]


def _obj_end(s, p):
    """End of the object at p ('d5 00' | u16 dl | dl bytes | u32 nrec | records | 41-byte trailer)."""
    if s[p:p + 2] != b'\xd5\x00':
        raise ValueError('no object at %#x' % p)
    q = p + 4 + struct.unpack_from('<H', s, p + 2)[0]
    nrec = struct.unpack_from('<I', s, q)[0]
    q += 4
    for _ in range(nrec):
        if s[q:q + 4] != layout.REC:
            raise ValueError('broken module record at %#x' % q)
        q += 4 + 0x3a + 8 * struct.unpack_from('<H', s, q + 0x30)[0] + 12
    if s[q:q + 2] != b'\x27\x00':
        raise ValueError('broken object trailer at %#x' % q)
    return q + 41


_NEXT = re.compile(rb'\xd7\x00..\x00\x00\xd5\x00', re.S)


def library(data):
    """Section 219 entries: [{index, name, category, type, rec (record bytes), uid, factory}]."""
    c = data if isinstance(data, layout.Container) else layout.Container(data)
    s = bytes(c.sec(219)[1])
    if s[:2] != b'\xdb\x00':
        raise ValueError('section 219 does not start with db 00')
    n = struct.unpack_from('<I', s, 2)[0]
    p, out = 6, []
    for i in range(n):
        if p + 8 > len(s) or s[p:p + 2] != b'\xd7\x00' or s[p + 6:p + 8] != b'\xd5\x00':
            break                         # entry kinds this reader does not know (big V2025 libraries): stop here
        end = _obj_end(s, p + 6)
        o = p + 6 + 4 + struct.unpack_from('<H', s, p + 8)[0] + 4      # first record
        typ = struct.unpack_from('<H', s, o + 4)[0]
        cnt = struct.unpack_from('<H', s, o + 0x30)[0]
        rec = s[o:o + 4 + 0x3a + 8 * cnt + 12]
        q = end
        ln = struct.unpack_from('<H', s, q)[0]
        name = s[q + 2:q + 2 + ln].decode('latin1')
        q += 2 + ln
        ln = struct.unpack_from('<H', s, q)[0]
        cat = s[q + 2:q + 2 + ln].decode('latin1')
        q += 2 + ln
        m = _NEXT.search(s, q) if i + 1 < n else None
        nq = m.start() if m else len(s)
        tail = s[q + 12:nq]
        out.append({'index': i, 'name': name, 'category': cat, 'type': typ, 'rec': rec,
                    'factory': len(tail) >= 1 and tail[0] == 2,
                    'uid': struct.unpack_from('<H', tail, 1)[0] if len(tail) >= 3 else None})
        p = nq
    return out


def _keyset(rec):
    return frozenset((prm, b) for prm, b, _ in _rec_slots(rec, 0))


def _kinds(lib):
    """kind of every library entry: from the factory group name, else from a factory preset with the same keys."""
    sig = {}
    for e in lib:
        if e['type'] == FX_MODULE and e['category'] in KIND_OF_GROUP:
            sig.setdefault(_keyset(e['rec']), KIND_OF_GROUP[e['category']])
    return [KIND_OF_GROUP.get(e['category']) or sig.get(_keyset(e['rec'])) or 'other' if e['type'] == FX_MODULE
            else None for e in lib]


def _signatures(lib, kinds):
    """{factory key set: kind} and {factory key set: preset name} (names only where one preset has that key set).
    A live record's key set minus (f0,0) names its algorithm even when its preset index is -1 or stale."""
    kind, names = {}, {}
    for e, k in zip(lib, kinds):
        if e['type'] == FX_MODULE and e['category'] in KIND_OF_GROUP:
            ks = _keyset(e['rec'])
            kind.setdefault(ks, k)
            names.setdefault(ks, []).append(e['name'])
    return kind, {ks: v[0] for ks, v in names.items() if len(v) == 1}


# ---------------------------------------------------------------------------------------------------- reading
CB_HL = (0x50, 0x58, 0x78, 0x79)     # channel record header lengths; 0x78 = Quantum 112 / 852 at V1926-V2126


def _groups201(s201):
    """layout.groups201 with every record length the editors write (layout's list lacks 0x78, which Q112 and Q852
    files of V1926-V2126 use; without it the FX record template and the aux lookups found nothing there)."""
    s, out = bytes(s201), {}
    for m in re.finditer(re.escape(layout.GROUP_HDR), s):
        q = m.start()
        if q + 0x74 > len(s) or s[q + 5] > 31:
            continue
        typ, cnt, p, offs = s[q + 4], struct.unpack_from('<I', s, q + 0x70)[0], q + 0x74, []
        for _ in range(cnt):
            if p + 4 > len(s) or s[p:p + 2] != b'\xcb\x00' or s[p + 2] not in CB_HL or \
                    struct.unpack_from('<H', s, p + 4)[0] >> 8 != typ:
                offs = None
                break
            offs.append(p)
            p += 4 + s[p + 2]
        if offs:
            out.setdefault(typ, []).extend(offs)
    return out


class _Doc:
    """The file split into its parts: container, section 201 FX group, 211 objects by id."""

    def __init__(self, data):
        self.c = layout.Container(data)
        self.family = _family(self.c.head)
        self.s201 = self.c.sec(201)[1]
        objs, self.tail = layout.objects(self.c.sec(211)[1])
        self.head211 = bytearray(self.c.sec(211)[1][:6])
        self.obj = {layout.obj_id(o): o for o in objs}
        self.lib = library(self.c)
        self.kinds = _kinds(self.lib)
        self.sig_kind, self.sig_name = _signatures(self.lib, self.kinds)
        m = re.search(rb'\xca\x00\x6c\x00\x0e\x02FX', bytes(self.s201))
        if m is None:
            raise ValueError('this session has no FX group in section 201')
        self.gq = m.start()

    # section 201 ---------------------------------------------------------
    def fx_cbs(self):
        """[(offset, record bytes)] of the FX group's channel records, in rack order."""
        s, q = self.s201, self.gq
        cnt = struct.unpack_from('<I', s, q + 0x70)[0]
        p, out = q + 0x74, []
        for _ in range(cnt):
            ln = 4 + struct.unpack_from('<H', s, p + 2)[0]
            out.append((p, bytearray(s[p:p + ln])))
            p += ln
        return out

    def cbs(self, typ):
        g = _groups201(self.s201)
        return [(p, self.s201[p:p + 4 + self.s201[p + 2]]) for p in g.get(typ, [])]

    def cb_by_id(self, cid):
        for t in (cid >> 8,):
            for p, r in self.cbs(t):
                if struct.unpack_from('<H', r, 4)[0] == cid:
                    return p, r
        return None, None

    # section 211 ---------------------------------------------------------
    def slot(self, cid, module, param, band):
        o = self.obj[cid]
        q = layout.obj_slot(o, module, param, band)
        if q is None:
            raise KeyError('object %#x has no slot %02x/%02x/%d' % (cid, module, param, band))
        return o, q

    def put_raw(self, cid, module, param, band, raw4):
        o, q = self.slot(cid, module, param, band)
        o[q:q + 4] = raw4

    def put(self, cid, module, param, band, value):
        o, q = self.slot(cid, module, param, band)
        struct.pack_into('<f', o, q, float(value))

    def unit_kind(self, cid):
        """(kind, factory preset name or None) of live unit `cid`, from its own keys, else from its preset index."""
        o = self.obj[cid]
        rp = layout.obj_records(o)[0][0]
        ks = frozenset((prm, b) for prm, b, _ in _rec_slots(o, rp)) - {(0xf0, 0)}
        if ks in self.sig_kind:
            return self.sig_kind[ks], self.sig_name.get(ks)
        _, r = self.cb_by_id(cid)
        pi = struct.unpack_from('<i', r, 42)[0] if r is not None else -1
        if 0 <= pi < len(self.lib) and self.kinds[pi]:
            return self.kinds[pi], self.lib[pi]['name']
        return 'other', None

    def build(self):
        objs = sorted(self.obj.values(), key=layout.obj_id)
        struct.pack_into('<I', self.head211, 2, len(objs))
        self.c.sec(211)[1] = self.head211 + b''.join(objs) + self.tail
        self.c.sec(201)[1] = self.s201
        return self.c.build()


def _route(raw):
    side, idx, typ = raw[1], raw[2], raw[3]
    return {'type': typ, 'index': idx, 'side': side}


def list_presets(ses):
    """FX presets in the session's library (section 219), in library order. `index` is what a unit stores."""
    d = _Doc(ses.d)
    out = []
    for e, kind in zip(d.lib, d.kinds):
        if e['type'] != FX_MODULE:
            continue
        out.append({'index': e['index'], 'name': e['name'], 'category': e['category'], 'kind': kind,
                    'uid': e['uid'], 'factory': e['factory'],
                    'slots': {(prm, b): round(_f(e['rec'], q + 4), 6) for prm, b, q in _rec_slots(e['rec'], 0)
                              if (prm, b) not in ((0, 0), (0, 1))}})
    return out


def units(ses):
    """Live FX units in rack order, with what feeds them and which input channels return them."""
    d = _Doc(ses.d)
    aux_num = {a['band']: a['number'] for a in ses.auxes}
    out = []
    for p, r in d.fx_cbs():
        cid = struct.unpack_from('<H', r, 4)[0]
        o = d.obj.get(cid)
        e = {'unit': struct.unpack_from('<H', r, 6)[0], 'id': cid, 'name': r[9:9 + r[8]].decode('latin1'),
             'width': r[41], 'preset': struct.unpack_from('<i', r, 42)[0],
             'engine': struct.unpack_from('<h', r, 84)[0] if layout.cb_has_engine(r) else None}
        if o is not None:
            e['kind'] = d.unit_kind(cid)[0]
            rp = layout.obj_records(o)[0][0]
            feed = []
            for prm, b, q in _rec_slots(o, rp):
                if prm == 0 and b in (0, 1) and o[q + 7]:
                    rt = _route(o[q + 4:q + 8])
                    if rt['type'] == T_AUX:
                        rt['aux'] = aux_num.get(rt['index'])
                    feed.append(dict(rt, input=('L', 'R')[b]))
            e['feed'] = feed
            e['params'] = {(prm, b): round(_f(o, q + 4), 6) for prm, b, q in _rec_slots(o, rp)
                           if (prm, b) not in ((0, 0), (0, 1))}
        rets = []
        for n in sorted(ses.display):
            idx = ses.display[n]
            q = layout.obj_slot(d.obj[0x0100 | (idx - 1)], 0x01, 0x00, 0)
            raw = d.obj[0x0100 | (idx - 1)][q:q + 4]
            if raw[3] == FX_TYPE and raw[2] == cid & 0xff:
                rets.append({'input': n, 'side': 'LR'[raw[1]] if ses.width.get(n) == 1 else 'L+R'})
        e['returns'] = rets
        out.append(e)
    return out


# ---------------------------------------------------------------------------------------------------- writing
def resolve_preset(lib, kinds, preset):
    """A library index from a preset name ('Vocal Plate'), a kind word ('hall', 'plate', 'delay'), or an index."""
    fx = [e for e in lib if e['type'] == FX_MODULE]
    if isinstance(preset, int):
        if 0 <= preset < len(lib) and lib[preset]['type'] == FX_MODULE:
            return preset
        raise ValueError('library entry %d is not an FX preset' % preset)
    want = str(preset).strip().lower()
    for e in fx:
        if e['name'].lower() == want:
            return e['index']
    for rx, name in KIND_PRESET:
        if re.match(rx, want):
            for e in fx:
                if e['name'].lower() == name.lower():
                    return e['index']
    raise ValueError('no FX preset called %r; try one of: %s' % (preset, ', '.join(e['name'] for e in fx)))


def engine_slots(family, kind):
    """EngineChannels a unit of this kind may take, in the order the editor hands them out (2 per unit, POOL_UNITS
    units per pool). Reverbs: 128-158 on Quantum, 64-94 on SD. Other effects: 0-30 on SD; on Quantum 0-26, then 64
    and 66 (the V2242 editors move a 15th non-reverb unit from 28 to 64), except Quantum 112 (Q1): 0-26 only, so
    14 other effects. A 17th reverb gets EngineChannel -1 from the editor (no DSP). the decode notes (not published), capacity
    probes."""
    quantum = family in QUANTUM_FAMILIES
    if kind == 'reverb':
        base = REVERB_BASE['quantum' if quantum else 'sd']
        return list(range(base, base + 2 * POOL_UNITS, 2))
    if quantum:
        tail = [] if family in SHORT_OTHER_POOL else list(range(64, 128, 2))
        return (list(range(0, 28, 2)) + tail)[:POOL_UNITS]
    return list(range(0, 2 * POOL_UNITS, 2))


def _engine(d, kind):
    """Next free EngineChannel for a unit of this kind (reverbs and other effects use separate DSP pools)."""
    used = set()
    for _, r in d.fx_cbs():
        if layout.cb_has_engine(r):
            e = struct.unpack_from('<h', r, 84)[0]
            used |= {e, e + 1}
    for e in engine_slots(d.family, kind):
        if e not in used and e + 1 not in used:
            return e
    raise ValueError('this console has no DSP left for another %s (%d per session)'
                     % ('reverb' if kind == 'reverb' else 'non-reverb effect', POOL_UNITS))


def _live_record(entry, name, stamp):
    """The library record turned into a live unit record: renamed, (f0,0) added after (05,0), (ff,0) = 1.0."""
    rec = bytearray(entry['rec'])
    hdr = rec[:4 + 0x3a]
    hdr[8:40] = _sstr31(name)
    if stamp is not None:
        hdr[40:48] = stamp
    hdr[LIVE_FLAG] = 1
    slots = [bytearray(rec[q:q + 8]) for _, _, q in _rec_slots(rec, 0)]
    if not any(s[0] == 0xf0 for s in slots):
        at = next((k + 1 for k, s in enumerate(slots) if s[0] == 0x05 and s[2] == 0), len(slots))
        slots.insert(at, bytearray([0xf0, FX_MODULE, 0, 0, 0, 0, 0, 0]))
    for s in slots:
        if s[0] == 0xff and s[2] == 0:
            struct.pack_into('<f', s, 4, 1.0)
        if s[0] == 0x00 and s[2] in (0, 1):
            s[4:8] = b'\0\0\0\0'
    struct.pack_into('<H', hdr, 0x30, len(slots))
    return hdr + b''.join(slots) + rec[len(rec) - 12:]


def _stamp(d):
    """A TDateTime from a live record of this session (record header +40), so the new unit looks like a peer."""
    for o in d.obj.values():
        for p, _, _ in layout.obj_records(o):
            return bytes(o[p + 40:p + 48])
    return None


def _aux_ids(d, ses, aux):
    """(L object id, R object id or None, width) of surface aux `aux`."""
    if aux not in ses.aux_band:
        raise ValueError('this session has no aux %s (auxes 1-%d)' % (aux, len(ses.auxes)))
    band = ses.aux_band[aux]
    lid = (T_AUX << 8) | band
    _, r = d.cb_by_id(lid)
    width = r[41]
    rid = struct.unpack_from('<H', r, 54)[0] if width == 2 else None
    if width == 2 and (rid is None or rid >> 8 != T_RIGHT or rid not in d.obj):
        raise ValueError('aux %d is stereo but its right side could not be found' % aux)
    return lid, rid, width


def _clear_stale(d, cid, sources):
    """Before unit `cid` gets new sources: unpatch every OTHER output that still names this unit (route 0, a mono
    output back to mono > mono 1.0), and empty the inputs of any other unit that one of the new `sources` fed
    (replace=True moves a source, it does not leave the old unit pointing at it). Default values are the ones every
    default session holds on an unpatched output: route 00 00 00 00, mode 1.0 mono / 2.0 stereo."""
    k = cid & 0xff
    for oid, o in d.obj.items():
        if oid in sources:
            continue
        q = layout.obj_slot(o, 0x0e, 0xfe, 0)
        if q is None or o[q + 3] != FX_TYPE or o[q + 2] != k:
            continue
        o[q:q + 4] = b'\0\0\0\0'
        m = layout.obj_slot(o, 0x0e, 0xe8, 0)
        if m is not None and struct.unpack_from('<f', o, m)[0] == 0.0:
            struct.pack_into('<f', o, m, 1.0)
    for oid in sources:
        o = d.obj[oid]
        q = layout.obj_slot(o, 0x0e, 0xfe, 0)
        if q is None or o[q + 3] != FX_TYPE or o[q + 2] == k:
            continue
        other = d.obj.get((FX_TYPE << 8) | o[q + 2])
        if other is None:
            continue
        src = (oid & 0xff, oid >> 8)
        for b in (0, 1):
            p = layout.obj_slot(other, FX_MODULE, 0x00, b)
            if p is not None and (other[p + 2], other[p + 3]) == src:
                other[p:p + 4] = b'\0\0\0\0'


def feed_from_aux(ses, unit, aux, replace=False):
    """Feed FX unit `unit` (rack number) from surface aux `aux`. A mono aux feeds both sides (mono > stereo).
    The unit's previous source, if any, is unpatched."""
    d = _Doc(ses.d)
    cid = _unit_id(d, unit)
    lid, rid, width = _aux_ids(d, ses, aux)
    k = cid & 0xff
    for oid in (lid, rid):
        if oid is None:
            continue
        o, q = d.slot(oid, 0x0e, 0xfe, 0)
        busy = o[q + 3] != 0 and not (o[q + 3] == FX_TYPE and o[q + 2] == k)
        if busy and not replace:
            raise ValueError('aux %d already feeds something else (pass replace=True to move it)' % aux)
    _clear_stale(d, cid, {x for x in (lid, rid) if x is not None})
    d.put_raw(lid, 0x0e, 0xfe, 0, bytes([0, 0, k, FX_TYPE]))
    if width == 2:
        d.put_raw(rid, 0x0e, 0xfe, 0, bytes([0, 1, k, FX_TYPE]))
        d.put_raw(cid, FX_MODULE, 0x00, 0, bytes([0, 0, lid & 0xff, T_AUX]))
        d.put_raw(cid, FX_MODULE, 0x00, 1, bytes([0, 0, rid & 0xff, T_RIGHT]))
    else:
        d.put(lid, 0x0e, 0xe8, 0, 0.0)                     # mono > stereo: the aux feeds both sides
        d.put_raw(cid, FX_MODULE, 0x00, 0, bytes([0, 0, lid & 0xff, T_AUX]))
        d.put_raw(cid, FX_MODULE, 0x00, 1, bytes([0, 0, lid & 0xff, T_AUX]))
    _reload(ses, d.build())


def feed_from_input(ses, unit, n, replace=False):
    """Feed FX unit `unit` from the direct output of surface input `n` (for example a vocal FX mic). A mono input
    feeds both sides (mono > stereo, (0e,e8,0) = 0.0); a stereo input feeds L and R ('00 01 <idx> 01' = its right)."""
    if n not in ses.display:
        raise ValueError('this session has no input %s' % n)
    d = _Doc(ses.d)
    cid = _unit_id(d, unit)
    k = cid & 0xff
    oid = 0x0100 | (ses.display[n] - 1)
    o, q = d.slot(oid, 0x0e, 0xfe, 0)
    if o[q + 3] != 0 and not (o[q + 3] == FX_TYPE and o[q + 2] == k) and not replace:
        raise ValueError('input %d direct out already goes somewhere (pass replace=True to move it)' % n)
    _clear_stale(d, cid, {oid})
    d.put_raw(oid, 0x0e, 0xfe, 0, bytes([0, 0, k, FX_TYPE]))
    src = oid & 0xff
    if ses.width.get(n) == 2:
        d.put_raw(cid, FX_MODULE, 0x00, 0, bytes([0, 0, src, 0x01]))
        d.put_raw(cid, FX_MODULE, 0x00, 1, bytes([0, 1, src, 0x01]))
    else:
        d.put(oid, 0x0e, 0xe8, 0, 0.0)
        d.put_raw(cid, FX_MODULE, 0x00, 0, bytes([0, 0, src, 0x01]))
        d.put_raw(cid, FX_MODULE, 0x00, 1, bytes([0, 0, src, 0x01]))
    _reload(ses, d.build())


def restore_feed_modes(ses):
    """Put back mono > stereo (0e,e8,0) = 0.0 on every mono input whose direct out feeds both sides of an FX unit.
    layout.relayout() rewrites every input's output mode to its width default (1.0 on a mono input), which turns
    such a feed into 'left side only' (real sessions: 0.0 with both sides fed 30 times, 1.0 with left only 11).
    fx.py calls this after each of its own relayouts; call it after any later layout.relayout() of a session that
    has FX units fed from input direct outs. Returns the number of inputs fixed."""
    d = _Doc(ses.d)
    fixed = 0
    for cid, o in list(d.obj.items()):
        if cid >> 8 != FX_TYPE:
            continue
        q0, q1 = layout.obj_slot(o, FX_MODULE, 0x00, 0), layout.obj_slot(o, FX_MODULE, 0x00, 1)
        if q0 is None or q1 is None or o[q0:q0 + 4] != o[q1:q1 + 4] or o[q0 + 3] != 0x01 or o[q0 + 1] != 0:
            continue
        src = d.obj.get(0x0100 | o[q0 + 2])
        if src is None or src[-1] != 1:                     # object trailer: last byte = width
            continue
        q, m = layout.obj_slot(src, 0x0e, 0xfe, 0), layout.obj_slot(src, 0x0e, 0xe8, 0)
        if q is None or m is None or src[q + 3] != FX_TYPE or src[q + 2] != cid & 0xff:
            continue
        if struct.unpack_from('<f', src, m)[0] != 0.0:
            struct.pack_into('<f', src, m, 0.0)
            fixed += 1
    if fixed:
        _reload(ses, d.build())
    return fixed


def _relayout(ses, spec):
    _reload(ses, layout.relayout(bytes(ses.d), spec))
    restore_feed_modes(ses)


def return_to_input(ses, unit, n, name=None, make_stereo=True):
    """Patch FX unit `unit` into surface input `n` (main input). A mono input is made stereo first (relayout,
    which keeps every other channel and moves the engine channels) unless make_stereo is False, in which case it
    gets the left side."""
    if n not in ses.display:
        raise ValueError('this session has no input %s' % n)
    if make_stereo and ses.width.get(n) == 1:
        spec = []
        for m in sorted(ses.display):
            idx = ses.display[m]
            spec.append({'name': ses.by_index[idx].name, 'width': 2 if m == n else ses.width[m], 'idx': idx,
                         'src': idx})
        _relayout(ses, spec)
    d = _Doc(ses.d)
    cid = _unit_id(d, unit)
    idx = ses.display[n]
    d.put_raw(0x0100 | (idx - 1), 0x01, 0x00, 0, bytes([0, 0, cid & 0xff, FX_TYPE]))
    _reload(ses, d.build())
    if name:
        ses.rename(idx, name[:8])


def _unit_id(d, unit):
    for _, r in d.fx_cbs():
        if struct.unpack_from('<H', r, 6)[0] == unit:
            return struct.unpack_from('<H', r, 4)[0]
    raise ValueError('this session has no FX unit %s' % unit)


def add_fx(ses, preset, feed_aux=None, return_to=None, name=None, return_name=None, make_stereo=True,
           feed_input=None):
    """Add an FX unit from the session's preset library and route it.

    preset       preset name ('Vocal Plate'), a kind word (hall, plate, room, vocal plate, delay, slap, chorus,
                 thicken, octave ...) or a library index (list_presets()).
    feed_aux     surface aux number that feeds the unit (mono aux: both sides; stereo aux: L and R), or None.
    feed_input   surface input whose direct output feeds the unit instead (a vocal FX mic), or None.
    return_to    ('input', n): surface input n becomes the return (made stereo unless make_stereo=False);
                 'fx_return': a new stereo input is added after the last one and named after the unit;
                 None: no return.
    name         rack name of the unit (default: the preset name). return_name: name of the return channel
                 (8 characters at most are written).
    Returns the unit number (its position in the FX rack, 1-based). On any error the session is left unchanged."""
    before = bytes(ses.d)
    try:
        return _add_fx(ses, preset, feed_aux, return_to, name, return_name, make_stereo, feed_input)
    except Exception:
        _reload(ses, before)
        raise


def _add_fx(ses, preset, feed_aux, return_to, name, return_name, make_stereo, feed_input):
    if return_to is not None and return_to != 'fx_return' and not (
            isinstance(return_to, (tuple, list)) and len(return_to) == 2 and return_to[0] == 'input'):
        raise ValueError("return_to must be ('input', n), 'fx_return' or None")
    if feed_aux is not None and feed_input is not None:
        raise ValueError('a unit has one source: pass feed_aux or feed_input, not both')
    d = _Doc(ses.d)
    pi = resolve_preset(d.lib, d.kinds, preset)
    entry, kind = d.lib[pi], d.kinds[pi]
    pool = [c for c, _ in ((struct.unpack_from('<H', r, 4)[0], r) for _, r in d.fx_cbs())
            if c in d.obj and (d.unit_kind(c)[0] == 'reverb') == (kind == 'reverb')]
    cap = len(engine_slots(d.family, kind))      # V1455 records have no EngineChannel, so count the units too
    if len(pool) >= cap:
        raise ValueError('this session already has %d %s units (%d per session on this console)'
                         % (len(pool), 'reverb' if kind == 'reverb' else 'non-reverb', cap))
    uname = (name or entry['name'])[:31]
    cbs = d.fx_cbs()
    used = {struct.unpack_from('<H', r, 4)[0] & 0xff for _, r in cbs}
    k = next((i for i in range(MAX_UNITS) if i not in used), None)
    if k is None:
        raise ValueError('the FX rack is full (%d units)' % MAX_UNITS)
    cid = (FX_TYPE << 8) | k
    number = len(cbs) + 1

    # 201: a mono aux record turned into an FX record, appended to the FX group
    tpl = next((bytearray(r) for _, r in cbs), None)
    if tpl is None:
        tpl = next((bytearray(r) for _, r in d.cbs(T_AUX) if r[41] == 1), None)
        if tpl is None:
            raise ValueError('no mono aux record to copy the FX record from')
        tpl[54:56] = b'\0\0'
    struct.pack_into('<HH', tpl, 4, cid, number)
    tpl[8:40] = _sstr31(uname)
    tpl[41] = 2
    struct.pack_into('<i', tpl, 42, pi)
    if layout.cb_has_engine(tpl):
        struct.pack_into('<h', tpl, 84, _engine(d, kind))
    end = cbs[-1][0] + len(cbs[-1][1]) if cbs else d.gq + 0x74
    d.s201[end:end] = tpl
    struct.pack_into('<I', d.s201, d.gq + 0x70, number)

    # 211: the live object
    rec = _live_record(entry, uname, _stamp(d))
    trailer = b'\x27\x00' + struct.pack('<H', cid) + _sstr31(uname) + struct.pack('<i', pi) + b'\x02'
    d.obj[cid] = bytearray(b'\xd5\x00\x01\x00\x01' + struct.pack('<I', 1) + rec + trailer)
    _reload(ses, d.build())

    if feed_aux is not None:
        feed_from_aux(ses, number, feed_aux)
    if feed_input is not None:
        feed_from_input(ses, number, feed_input)
    if return_to == 'fx_return':
        spec = [{'name': ses.by_index[ses.display[m]].name, 'width': ses.width[m], 'idx': ses.display[m],
                 'src': ses.display[m]} for m in sorted(ses.display)]
        spec.append({'name': (return_name or uname)[:8], 'width': 2})
        _relayout(ses, spec)
        return_to_input(ses, number, len(spec), make_stereo=False)
    elif return_to is not None:
        return_to_input(ses, number, return_to[1], name=return_name, make_stereo=make_stereo)
    return number


def set_fx_params(ses, unit, **params):
    """Set FX unit parameters by name (PARAMS for the unit's kind plus PRESET_PARAMS for its preset; units in UNITS:
    times in seconds, filters in Hz, mix and feedback in %) or by raw key:
    set_fx_params(ses, 1, decay=1.8, **{'0x2e/0': -1.2}). Returns {(param, band): value}."""
    d = _Doc(ses.d)
    cid = _unit_id(d, unit)
    o = d.obj[cid]
    rp = layout.obj_records(o)[0][0]
    keys = {(prm, b) for prm, b, _ in _rec_slots(o, rp)}
    kind, pname = d.unit_kind(cid)
    names = dict(PARAMS.get(kind, {}))
    names.update(PRESET_PARAMS.get(pname, {}))
    done = {}
    for k, v in params.items():
        if k in names:
            key = names[k]
        else:
            m = re.match(r'^(?:0x)?([0-9a-f]{1,2})/(\d+)$', k, re.I)
            if not m:
                raise ValueError('%s has no parameter %r (named: %s)' % (kind, k, ', '.join(sorted(names)) or '-'))
            key = (int(m.group(1), 16), int(m.group(2)))
        if key not in keys or key in ((0, 0), (0, 1), (0x80, 0), (0xff, 0)):
            raise ValueError('FX unit %d (%s) has no writable parameter %r' % (unit, kind, k))
        d.put(cid, FX_MODULE, key[0], key[1], v)
        done[key] = float(v)
    _reload(ses, d.build())
    return done


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: python3 -m sessionmaker.fx file.ses  (list the FX units, their feeds and returns)')
        sys.exit(0 if len(sys.argv) > 1 else 2)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ses import Session
    s = Session(sys.argv[1])
    for u in units(s):
        print('FX %d %-14s %-7s engine %-4s preset %-3d feed %s returns %s' % (
            u['unit'], u['name'], u.get('kind'), u['engine'], u['preset'],
            ', '.join('%s<-%s' % (f['input'], 'aux %s' % f.get('aux') if f['type'] == T_AUX else
                                  '%02x:%d' % (f['type'], f['index'])) for f in u.get('feed', [])) or '-',
            ', '.join('in %d' % x['input'] for x in u['returns']) or '-'))
