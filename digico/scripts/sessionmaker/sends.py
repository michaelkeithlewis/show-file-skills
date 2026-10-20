#!/usr/bin/env python3
"""sends.py - aux sends, group routing, bus names, bus faders and bus output patch, by bytes.

Research and editor proofs: the decode notes (not published). Every key below holds in all 116 editor-written default sessions
(14 consoles, V1455-V2242) and in 39 real sessions; the names come from the editor's own controller
library (tControllerLibrary records in Quantum2.exe V2242 at 0x84bf1f..).

Input channel, module 02 (aux sends): one band per aux; the band byte is the aux's INTERNAL index (ses.aux_band),
12 slots per band:
  01 send level (dB, -150 = off, max +10)   02 send on (0/1)   03 send pan (-1 L .. +1 R; stereo auxes only)
  04 send pre-post (enum, PREPOST below)    f2 aux node safe   0b-11 KLANG (mode, level, unmute, azimuth,
  elevation, width, solo): left alone.
Input channel, module 03 (group assign): param 09 per group band (group internal index, ses.group_band), 0/1.
  The console master is a stereo group too: header byte 0x5c (tConsoleRec.MasterGroupID) holds its band.
Bus objects (section 211, id = type << 8 | internal index; type 05 aux, 06 group, 10 matrix, 07 = the right
side of a stereo aux or group, linked both ways by tChannelRec.BussID at section 201 record +54; the R side is
always named "<name> R"):
  module 0c  21 fader (dB, -150 = off), 22 mute (0/1), 0f link pans (aux: 0 off, 1 sends follow the channel pan,
             2 follow it reversed; the editor rewrites the send pans from this on load), 0c link (stereo).
             The R object mirrors fader, mute and routing in real files; the editor does not enforce it, so the
             writers here always write both sides.
  module 03  param 09 per group band: bus -> group / master routing (groups only).
  module 0e  fe output route: raw 00 00 <socket idx> <socket type>, one of the bus's output sockets. On load the
             editor fills that socket's source from it (editor-proved), so both ends must agree.
             e8 = width (1 mono, 2 stereo, 0 on auxes that feed an FX unit).
Output socket objects (types 4d-5f: 4d INTERNAL, 4e Local I/O, 4f Rack 1 / first rack, 50.. next rack, MADI, USB,
in section 201 group order), module 12:
  00 source route: raw 00 00 <bus internal index> <bus type> (the patch lives here; one socket = one source),
  8a output stereo link, 90 output pad, 93 output SR, 9c socket disable.
A stereo bus is patched L -> socket n, R -> socket n + 1 of the same type in every real session.

Surface channel numbers are used throughout (ch = the strip number, mapped with ses.ch()); aux and group numbers are
surface numbers too (mapped with ses.aux_band / ses.group_band).
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ROOT  # ses.py and sesproc.py sit next to this package
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from ses import Session, chrec_ok  # noqa: E402,F401  (Session re-exported for callers)

T_AUX, T_GROUP, T_RSIDE, T_MATRIX = 0x05, 0x06, 0x07, 0x10
KINDS = {'aux': T_AUX, 'group': T_GROUP, 'matrix': T_MATRIX}

SEND, S_LEVEL, S_ON, S_PAN, S_PREPOST = 0x02, 0x01, 0x02, 0x03, 0x04
GROUPS, G_ASSIGN = 0x03, 0x09
FADER, F_FADER, F_MUTE, F_LINKPANS = 0x0c, 0x21, 0x22, 0x0f
OUT, O_ROUTE, O_WIDTH = 0x0e, 0xfe, 0xe8
SOCKET, SK_SOURCE = 0x12, 0x00
OUTPUT_SOCKET_TYPES = range(0x4d, 0x60)
MASTER_ID_AT = 0x5c                     # header: tConsoleRec (0x24) + 56 = MasterGroupID (band of the master group)
BUSSID_AT = 54                          # section 201 record: cb 00 hl 00 + tChannelRec.BussID @50
OFF_DB, MAX_DB = -150.0, 10.0

# AuxSendPrePostButton caption in the editor: "Post-Fader|Pre-Fader|Pre-Mute|Mid-EQ/Dynamics|Pre-EQ/Dynamics|
# Pre-Processing" = values 0..5 of (02, 04).
PREPOST = {'post': 0, 'pre': 1, 'pre-mute': 2, 'mid-eq': 3, 'pre-eq': 4, 'pre-processing': 5}
PREPOST_NAMES = {v: k for k, v in PREPOST.items()}
LINK_PANS = {'off': 0, 'on': 1, 'reverse': 2}
LINK_NAMES = {v: k for k, v in LINK_PANS.items()}
NAME_MAX = 24                           # longest bus name in the 39 real sessions is 20; "<name> R" must fit 31


# ---------------------------------------------------------------------------- object index
class Obj:
    """One live channel object in section 211: id, name, width and {module: {(param, band): float offset}}."""
    __slots__ = ('id', 'name', 'width', 'trailer', 'recs', 'mods')

    def __init__(self, oid, name, width, trailer, recs, mods):
        self.id, self.name, self.width, self.trailer, self.recs, self.mods = oid, name, width, trailer, recs, mods

    def slot(self, module, param, band=0):
        try:
            return self.mods[module][(param, band)]
        except KeyError:
            raise KeyError('object %#06x (%s) has no slot (%#04x, %#04x, %d)' % (self.id, self.name, module,
                                                                              param, band))

    def has(self, module, param, band=0):
        return (param, band) in self.mods.get(module, {})


def _walk_211(d, lo):
    """Live objects of section 211, walked by structure (as layout.objects, with absolute offsets)."""
    if d[lo:lo + 2] != b'\xd3\x00':
        raise ValueError('section 211 does not start with d3 00')
    n = struct.unpack_from('<I', d, lo + 2)[0]
    p, out = lo + 6, {}
    for _ in range(n):
        p += 4 + struct.unpack_from('<H', d, p + 2)[0]
        nrec = struct.unpack_from('<I', d, p)[0]
        p += 4
        recs, mods = [], {}
        for _ in range(nrec):
            if d[p:p + 4] != b'\xda\x00\x3a\x00':
                raise ValueError('broken module record at %#x' % p)
            typ = struct.unpack_from('<H', d, p + 4)[0]
            cnt = struct.unpack_from('<H', d, p + 0x30)[0]
            s0 = p + 4 + 0x3a
            mods.setdefault(typ, {}).update({(d[s0 + 8 * k], d[s0 + 8 * k + 2]): s0 + 8 * k + 4 for k in range(cnt)})
            recs.append(p)
            p = s0 + 8 * cnt + 12
        if d[p:p + 2] != b'\x27\x00':
            raise ValueError('broken object trailer at %#x' % p)
        oid = struct.unpack_from('<H', d, p + 2)[0]
        out[oid] = Obj(oid, bytes(d[p + 5:p + 5 + min(d[p + 4], 31)]).decode('latin1'), d[p + 40], p, recs, mods)
        p += 41
    return out


def objects(ses):
    """{object id: Obj} of the live objects. Cached on the Session; every write here is fixed-size."""
    idx = getattr(ses, '_sends_objs', None)
    if idx is None or idx[0] != len(ses.d):
        lo, _ = ses.section_span(211)
        idx = (len(ses.d), _walk_211(ses.d, lo))
        ses._sends_objs = idx
    return idx[1]


def _raw(ses, off):
    return bytes(ses.d[off:off + 4])


def _route(idx, typ):
    """A route value: 4 raw bytes 00 00 <index> <type> stored in a float slot."""
    return bytes((0, 0, idx & 0xff, typ & 0xff))


def _setf(ses, off, v):
    struct.pack_into('<f', ses.d, off, float(v))


def _getf(ses, off):
    return struct.unpack_from('<f', ses.d, off)[0]


def _db(v):
    """A level in dB clamped to -150..+10. + 0.0 turns -0.0 into 0.0: the editor re-saves a 0 dB level as +0."""
    return max(OFF_DB, min(MAX_DB, float(v))) + 0.0


# ---------------------------------------------------------------------------- buses
def _chrec(ses, oid):
    """Section 201 record dict (off, id, number, name, width) for object id `oid`, or None."""
    for r in ses.groups201.get(oid >> 8, []):
        if r['id'] == oid:
            return r
    return None


def bus(ses, kind, n):
    """Surface bus `n` of kind 'aux' | 'group' | 'matrix' -> dict(kind, number, band, id, name, width, obj, robj).
    robj is the right-side object of a stereo bus (None for mono)."""
    typ = KINDS[kind]
    rec = next((r for r in ses.groups201.get(typ, []) if r['number'] == n), None)
    if rec is None:
        raise KeyError('no %s %d in this session (it has %d)' % (kind, n, len(ses.groups201.get(typ, []))))
    objs = objects(ses)
    rid = struct.unpack_from('<H', ses.d, rec['off'] + BUSSID_AT)[0] if rec['width'] == 2 else 0
    return {'kind': kind, 'number': n, 'band': rec['id'] & 0xff, 'id': rec['id'], 'name': rec['name'],
            'width': rec['width'], 'obj': objs[rec['id']], 'robj': objs.get(rid) if rid else None,
            'rid': rid or None, 'off': rec['off']}


def buses(ses, kind):
    return [bus(ses, kind, r['number']) for r in sorted(ses.groups201.get(KINDS[kind], []), key=lambda r: r['number'])]


def master_group(ses):
    """Surface number of the group named by tConsoleRec.MasterGroupID (header 0x5c), or None. In every editor default
    that is the stereo group "Master". The byte is 6 in all 39 real sessions, so after a user restructure it can name a
    group that is not the main bus (in 10 of them it names a subgroup that feeds the main bus). Use the 'master' alias
    on default-based builds; on a real session pick the group by number."""
    band = ses.d[MASTER_ID_AT]
    return next((g['number'] for g in ses.groups if g['band'] == band), None)


def _group_number(ses, g):
    if isinstance(g, str) and g.lower() in ('master', 'm', 'lr', 'main'):
        n = master_group(ses)
        if n is None:
            raise KeyError('this session has no master group')
        return n
    return int(g)


def _sides(b):
    return [b['obj']] + ([b['robj']] if b['robj'] is not None else [])


def _sstr31(name):
    raw = name.encode('latin1')
    if len(raw) > 31:
        raise ValueError('name longer than 31 bytes: %r' % name)
    return bytes([len(raw)]) + raw + b'\x00' * (31 - len(raw))


def _rename_object(ses, oid, name):
    """Write `name` into every copy that belongs to object id `oid`: each module record of every copy of the object
    (live and any snapshot copy), its trailer, and every section 201 style channel record with that id."""
    d, field, n = ses.d, _sstr31(name), 0
    want = struct.pack('<H', oid)
    run = []
    for r in ses.records:                         # all module records in the file, in file order
        if run and r.off != run[-1].end + 12:
            run = []
        run.append(r)
        t = r.end + 12
        if d[t:t + 2] == b'\x27\x00' and d[t + 2:t + 4] == want:
            for x in run:
                d[x.off + 8:x.off + 40] = field
                x.name = name
                n += 1
            d[t + 4:t + 36] = field
            n += 1
            run = []
        elif d[t:t + 2] == b'\x27\x00':
            run = []
    p = 0
    pat = b'\xcb\x00'
    while True:
        p = d.find(pat, p)
        if p < 0:
            break
        if d[p + 3] == 0 and d[p + 4:p + 6] == want and chrec_ok(d, p):
            d[p + 8:p + 40] = field
            n += 1
        p += 2
    return n


def name_bus(ses, kind, n, name, max_len=NAME_MAX):
    """Rename surface bus `n` ('aux' | 'group' | 'matrix'). A stereo bus's right side becomes "<name> R".
    -> number of name copies written."""
    name = name.strip()
    if not name or len(name) > max_len:
        raise ValueError('bus name must be 1-%d characters: %r' % (max_len, name))
    name.encode('latin1')
    b = bus(ses, kind, n)
    k = _rename_object(ses, b['id'], name)
    if b['rid']:
        k += _rename_object(ses, b['rid'], name + ' R')
    for typ in (KINDS[kind], T_RSIDE):            # keep the parsed 201 view in step
        for r in ses.groups201.get(typ, []):
            if r['id'] == b['id']:
                r['name'] = name
            elif b['rid'] and r['id'] == b['rid']:
                r['name'] = name + ' R'
    for r in {'aux': ses.auxes, 'group': ses.groups}.get(kind, []):
        if r['number'] == n:
            r['name'] = name
    objs = objects(ses)
    objs[b['id']].name = name
    if b['rid'] and b['rid'] in objs:
        objs[b['rid']].name = name + ' R'
    return k


def set_bus_fader(ses, kind, n, db=None, mute=None):
    """Bus master fader (dB, -150 = off, max +10) and/or mute on surface bus `n`, both sides of a stereo bus."""
    b = bus(ses, kind, n)
    for o in _sides(b):
        if db is not None:
            _setf(ses, o.slot(FADER, F_FADER), _db(db))
        if mute is not None:
            _setf(ses, o.slot(FADER, F_MUTE), 1.0 if mute else 0.0)
    return b


def set_link_pans(ses, n, mode):
    """Aux `n` "link pans": 'off', 'on' (each send pan follows its channel pan) or 'reverse' (follows it mirrored,
    the drummer's view). Also writes every send pan to the value the console derives, so the file is consistent."""
    m = LINK_PANS[mode] if isinstance(mode, str) else int(mode)
    if m not in (0, 1, 2):
        raise ValueError('link pans mode must be off, on or reverse (0-2): %r' % (mode,))
    b = bus(ses, 'aux', n)
    for o in _sides(b):
        _setf(ses, o.slot(FADER, F_LINKPANS), m)
    if m and b['width'] == 2:
        for c in ses.inputs:
            if ses.has_slot(c.index, SEND, S_PAN, b['band']):
                ses.set(c.index, SEND, S_PAN, b['band'], _linked_pan(ses, c.index, m))
    return b


def link_pans(ses, n):
    """Link-pans mode of aux `n`: 0 off, 1 on, 2 reverse."""
    return int(round(_getf(ses, bus(ses, 'aux', n)['obj'].slot(FADER, F_LINKPANS))))


def _linked_pan(ses, idx, mode):
    """The send pan the editor derives on load for a linked stereo aux (proved in the editor: it rewrites stale send
    pans to +channel pan for mode 1 and -channel pan for mode 2). + 0.0 turns -0.0 into the editor's +0."""
    return (1.0 if mode == 1 else -1.0) * ses.get(idx, 0x0d, 0x23, 0) + 0.0


# ---------------------------------------------------------------------------- sends
def set_send(ses, ch, aux_n, level_db=None, on=True, pre=None, pan=None):
    """Aux send from surface input channel `ch` to surface aux `aux_n`.
    level_db: dB (-150 = off .. +10), None keeps it. on: True / False / None (keep).
    pre: None (keep), True / 'pre' (pre-fader), False / 'post', or 'pre-mute', 'mid-eq', 'pre-eq', 'pre-processing'
    (or the 0-5 value). pan: -1 (L) .. +1 (R); only on a stereo aux. -> dict of what the slots now hold."""
    idx = ses.ch(ch)
    if idx not in ses.by_index:
        raise KeyError('no input channel %d' % ch)
    if aux_n not in ses.aux_band:
        raise KeyError('no aux %d in this session (it has %d)' % (aux_n, len(ses.auxes)))
    band = ses.aux_band[aux_n]
    width = next(a['width'] for a in ses.auxes if a['number'] == aux_n)
    if pan is not None and width != 2:                 # check everything before the first write
        raise ValueError('aux %d is mono; a send pan needs a stereo aux' % aux_n)
    if pan is not None:
        pan = max(-1.0, min(1.0, float(pan))) + 0.0     # + 0.0: no -0.0 (the editor saves +0)
    mode = link_pans(ses, aux_n) if width == 2 else 0
    if mode in (1, 2):
        # a linked aux: the editor rewrites every send pan from the channel pan on load, so write that value
        want = _linked_pan(ses, idx, mode)
        if pan is not None and abs(pan - want) > 1e-6:
            raise ValueError('aux %d has link pans %s: the send pan follows the channel pan (%.3f here), not %.3f'
                             % (aux_n, LINK_NAMES[mode], want, pan))
        pan = want
    ppv = _prepost_value(pre) if pre is not None else None
    if level_db is not None:
        ses.set(idx, SEND, S_LEVEL, band, _db(level_db))
    if on is not None:
        ses.set(idx, SEND, S_ON, band, 1.0 if on else 0.0)
    if ppv is not None:
        ses.set(idx, SEND, S_PREPOST, band, ppv)
    if pan is not None:
        ses.set(idx, SEND, S_PAN, band, pan)
    return read_send(ses, ch, aux_n)


def _prepost_value(pre):
    if pre is True:
        return PREPOST['pre']
    if pre is False:
        return PREPOST['post']
    v = PREPOST[pre.lower()] if isinstance(pre, str) else int(pre)
    if not 0 <= v <= 5:
        raise ValueError('pre/post value out of range: %r' % pre)
    return v


def set_bus_send(ses, group_n, aux_n, level_db=None, on=True, pre=None, pan=None):
    """Aux send from surface group `group_n` (a group's own module 02, used for drum groups into a reverb).
    Level, on and pre/post go on both sides of a stereo group. pan: a number for a mono group; for a stereo group a
    (left side, right side) pair, the editor's own stereo spread being (-1, 1). Only on a stereo aux."""
    g = bus(ses, 'group', group_n)
    if aux_n not in ses.aux_band:
        raise KeyError('no aux %d in this session' % aux_n)
    band = ses.aux_band[aux_n]
    width = next(a['width'] for a in ses.auxes if a['number'] == aux_n)
    sides = _sides(g)
    pans = None
    if pan is not None:                                # check everything before the first write
        if width != 2:
            raise ValueError('aux %d is mono; a send pan needs a stereo aux' % aux_n)
        pans = list(pan) if isinstance(pan, (tuple, list)) else [pan]
        if len(pans) != len(sides):
            raise ValueError('group %d takes %d pan value(s)' % (group_n, len(sides)))
    ppv = _prepost_value(pre) if pre is not None else None
    for o in sides:
        if level_db is not None:
            _setf(ses, o.slot(SEND, S_LEVEL, band), _db(level_db))
        if on is not None:
            _setf(ses, o.slot(SEND, S_ON, band), 1.0 if on else 0.0)
        if ppv is not None:
            _setf(ses, o.slot(SEND, S_PREPOST, band), ppv)
    if pans is not None:
        for o, p in zip(sides, pans):
            _setf(ses, o.slot(SEND, S_PAN, band), max(-1.0, min(1.0, float(p))) + 0.0)
    o = g['obj']
    return {'aux': aux_n, 'level': _getf(ses, o.slot(SEND, S_LEVEL, band)), 'on': _getf(ses, o.slot(SEND, S_ON, band)) > .5,
            'prepost': PREPOST_NAMES.get(int(round(_getf(ses, o.slot(SEND, S_PREPOST, band))))),
            'pan': [_getf(ses, x.slot(SEND, S_PAN, band)) for x in sides]}


def read_send(ses, ch, aux_n):
    idx, band = ses.ch(ch), ses.aux_band[aux_n]
    g = lambda p: ses.get(idx, SEND, p, band)
    pp = int(round(g(S_PREPOST)))
    return {'aux': aux_n, 'level': g(S_LEVEL), 'on': g(S_ON) > 0.5, 'pan': g(S_PAN),
            'prepost': PREPOST_NAMES.get(pp, pp)}


def read_sends(ses, ch, active_only=True):
    out = []
    for a in ses.auxes:
        s = read_send(ses, ch, a['number'])
        if not active_only or (s['on'] and s['level'] > OFF_DB):
            out.append(s)
    return out


# ---------------------------------------------------------------------------- group routing
def route_to_groups(ses, ch, groups, exclusive=True):
    """Assign surface input channel `ch` to surface groups `groups` (numbers, or 'master' for the console master).
    exclusive=True clears every other group assign, the master included unless it is listed."""
    idx = ses.ch(ch)
    want = {ses.group_band[_group_number(ses, g)] for g in groups}
    for gr in ses.groups:
        b = gr['band']
        if b in want:
            ses.set(idx, GROUPS, G_ASSIGN, b, 1.0)
        elif exclusive:
            ses.set(idx, GROUPS, G_ASSIGN, b, 0.0)
    return groups_of(ses, ch)


def groups_of(ses, ch):
    idx = ses.ch(ch)
    return [g['number'] for g in ses.groups if ses.get(idx, GROUPS, G_ASSIGN, g['band']) > 0.5]


def route_bus(ses, n, groups, exclusive=True):
    """Route surface group `n` to other groups / the master (both sides of a stereo group)."""
    b = bus(ses, 'group', n)
    want = {ses.group_band[_group_number(ses, g)] for g in groups}
    if b['band'] in want:
        raise ValueError('group %d cannot feed itself' % n)
    for o in _sides(b):
        for gr in ses.groups:
            if gr['band'] in want:
                _setf(ses, o.slot(GROUPS, G_ASSIGN, gr['band']), 1.0)
            elif exclusive:
                _setf(ses, o.slot(GROUPS, G_ASSIGN, gr['band']), 0.0)
    return b


def bus_routes(ses, n):
    b = bus(ses, 'group', n)
    return [g['number'] for g in ses.groups if b['obj'].has(GROUPS, G_ASSIGN, g['band'])
            and _getf(ses, b['obj'].slot(GROUPS, G_ASSIGN, g['band'])) > 0.5]


# ---------------------------------------------------------------------------- output patch
def output_sockets(ses):
    """[{id, type, idx, number, name, group}] of the output sockets (live objects of types 4d-5f)."""
    gname = {}
    lo, hi = ses.section_span(201)
    p = lo
    while True:
        p = ses.d.find(b'\xca\x00\x6c\x00', p, hi)
        if p < 0:
            break
        n = ses.d[p + 5]
        if n <= 31:
            gname.setdefault(ses.d[p + 4], bytes(ses.d[p + 6:p + 6 + n]).decode('latin1'))
        p += 4
    out = []
    for oid, o in sorted(objects(ses).items()):
        if oid >> 8 in OUTPUT_SOCKET_TYPES and o.has(SOCKET, SK_SOURCE):
            out.append({'id': oid, 'type': oid >> 8, 'idx': oid & 0xff, 'number': (oid & 0xff) + 1,
                        'name': o.name, 'group': gname.get(oid >> 8, '%#04x' % (oid >> 8))})
    return out


def find_socket(ses, spec):
    """Output socket from a spec: ('Rack 1', 5) / 'Rack 1:5' (5th socket of that I/O group), the socket's own name
    ('1:Line out 5'), or {'type': 0x4f, 'idx': 4}. Sockets with no name do not exist on the hardware."""
    socks = output_sockets(ses)
    hit = None
    if isinstance(spec, dict):
        hit = next((s for s in socks if s['type'] == spec['type'] and s['idx'] == spec['idx']), None)
    else:
        grp = num = None
        if isinstance(spec, (tuple, list)):
            grp, num = spec
        elif isinstance(spec, str) and ':' in spec and spec.rsplit(':', 1)[1].strip().isdigit():
            g, k = spec.rsplit(':', 1)
            if any(s['group'].lower() == g.strip().lower() for s in socks):
                grp, num = g.strip(), int(k)
        if grp is not None:
            hit = next((s for s in socks if s['group'].lower() == str(grp).lower() and s['number'] == int(num)), None)
        else:
            hit = next((s for s in socks if s['name'] == spec), None)
    if hit is None:
        raise KeyError('no output socket %r' % (spec,))
    if not hit['name'] or hit['name'] == 'unused':
        named = [s['number'] for s in socks if s['type'] == hit['type'] and s['name'] and s['name'] != 'unused']
        raise ValueError('output socket %r does not exist on this console (no name); %s has sockets %s'
                         % (spec, hit['group'], '%d-%d' % (named[0], named[-1]) if named else 'none'))
    return hit


def _socket_source(ses, sock):
    return _raw(ses, objects(ses)[sock['id']].slot(SOCKET, SK_SOURCE))


def _fix_bus_route(ses, src_oid):
    """Point a bus's own output route (0e fe) at one of the sockets that still carry it, or clear it."""
    o = objects(ses).get(src_oid)
    if o is None or not o.has(OUT, O_ROUTE):
        return
    cur = _raw(ses, o.slot(OUT, O_ROUTE))
    feeding = [s for s in output_sockets(ses) if _socket_source(ses, s) == _route(src_oid & 0xff, src_oid >> 8)]
    if cur != b'\0\0\0\0' and cur[3] in OUTPUT_SOCKET_TYPES and any(
            s['type'] == cur[3] and s['idx'] == cur[2] for s in feeding):
        return
    if cur != b'\0\0\0\0' and cur[3] not in OUTPUT_SOCKET_TYPES:
        return                                    # routed to an FX unit or another destination: leave it
    ses.d[o.slot(OUT, O_ROUTE):o.slot(OUT, O_ROUTE) + 4] = (_route(feeding[0]['idx'], feeding[0]['type'])
                                                        if feeding else b'\0\0\0\0')


def patch_output(ses, kind, n, left, right=None, replace=True):
    """Patch surface bus `n` to output sockets. left (and right, for a stereo bus; default = the socket after left)
    are find_socket() specs. replace=True first unpatches every other socket this bus feeds.
    Writes the socket's source route (module 12 param 00) and the bus's output route (module 0e param fe)."""
    b = bus(ses, kind, n)
    sides = [(b['obj'], left)]
    if b['robj'] is not None:
        if right is None:
            ls = find_socket(ses, left)
            right = {'type': ls['type'], 'idx': ls['idx'] + 1}
        sides.append((b['robj'], right))
    elif right is not None:
        raise ValueError('%s %d is mono; it takes one output socket' % (kind, n))
    sides = [(o, find_socket(ses, spec)) for o, spec in sides]   # resolve every socket before the first write
    if len(sides) == 2 and sides[0][1]['id'] == sides[1][1]['id']:
        raise ValueError('%s %d: left and right need two different sockets' % (kind, n))
    if replace:
        unpatch_output(ses, kind, n)
    done = []
    for o, sock in sides:
        so = objects(ses)[sock['id']]
        old = _socket_source(ses, sock)
        src = _route(o.id & 0xff, o.id >> 8)
        q = so.slot(SOCKET, SK_SOURCE)
        ses.d[q:q + 4] = src
        if old not in (b'\0\0\0\0', src):
            _fix_bus_route(ses, (old[3] << 8) | old[2])
        r = o.slot(OUT, O_ROUTE)
        cur = _raw(ses, r)
        # the bus's own route names one of its sockets; when it feeds an FX unit (type 0e) that feed stays
        if cur == b'\0\0\0\0' or (replace and cur[3] in OUTPUT_SOCKET_TYPES):
            ses.d[r:r + 4] = _route(sock['idx'], sock['type'])
        done.append(sock['name'])
    return done


def unpatch_output(ses, kind, n):
    """Remove surface bus `n` from every output socket and clear its output route (FX-unit feeds are kept)."""
    b = bus(ses, kind, n)
    k = 0
    for o in _sides(b):
        src = _route(o.id & 0xff, o.id >> 8)
        for s in output_sockets(ses):
            if _socket_source(ses, s) == src:
                q = objects(ses)[s['id']].slot(SOCKET, SK_SOURCE)
                ses.d[q:q + 4] = b'\0\0\0\0'
                k += 1
        r = o.slot(OUT, O_ROUTE)
        if ses.d[r + 3] in OUTPUT_SOCKET_TYPES:
            ses.d[r:r + 4] = b'\0\0\0\0'
    return k


def route_errors(ses):
    """Patch consistency: every bus whose output route names an output socket must be that socket's source, every
    socket source must name a live bus side, and a bus (or input) that feeds a socket must have a non-empty output
    route (true in all 39 real sessions and 116 defaults). -> list of sentences (empty = consistent)."""
    errs, objs = [], objects(ses)
    socks = {(s['type'], s['idx']): s for s in output_sockets(ses)}
    for s in socks.values():
        src = _socket_source(ses, s)
        if src != b'\0\0\0\0' and ((src[3] << 8) | src[2]) not in objs:
            errs.append('socket %s is fed by %s, which is not in the session' % (s['name'], src.hex()))
        elif src != b'\0\0\0\0' and src[:2] == b'\0\0':          # a main output (insert sends carry a tap byte)
            o = objs[(src[3] << 8) | src[2]]
            if o.has(OUT, O_ROUTE) and _raw(ses, o.slot(OUT, O_ROUTE)) == b'\0\0\0\0':
                errs.append('socket %s is fed by %s, whose own output route is empty' % (s['name'], o.name))
    for oid, o in objs.items():
        if oid >> 8 not in (T_AUX, T_GROUP, T_RSIDE, T_MATRIX) or not o.has(OUT, O_ROUTE):
            continue
        cur = _raw(ses, o.slot(OUT, O_ROUTE))
        if cur[3] in OUTPUT_SOCKET_TYPES:
            s = socks.get((cur[3], cur[2]))
            if s is None or _socket_source(ses, s) != _route(oid & 0xff, oid >> 8):
                errs.append('%s routes to socket %s, which is fed by something else' % (o.name, cur.hex()))
    return errs


def outputs_of(ses, kind, n):
    """Socket names that surface bus `n` feeds, [left..., right...]."""
    b = bus(ses, kind, n)
    out = []
    for o in _sides(b):
        src = _route(o.id & 0xff, o.id >> 8)
        out.append([s['name'] for s in output_sockets(ses) if _socket_source(ses, s) == src])
    return out


# ---------------------------------------------------------------------------- read back
def read_buses(ses):
    """Plain-data view of every aux and group master: name, width, fader, mute, outputs, routing."""
    out = {'aux': [], 'group': [], 'master': master_group(ses)}
    for kind in ('aux', 'group'):
        for b in buses(ses, kind):
            o = b['obj']
            row = {'n': b['number'], 'name': b['name'], 'stereo': b['width'] == 2,
                   'fader': _getf(ses, o.slot(FADER, F_FADER)), 'mute': _getf(ses, o.slot(FADER, F_MUTE)) > 0.5,
                   'outputs': outputs_of(ses, kind, b['number'])}
            if kind == 'aux':
                row['link_pans'] = int(_getf(ses, o.slot(FADER, F_LINKPANS)))
            else:
                row['routes'] = bus_routes(ses, b['number'])
            out[kind].append(row)
    return out


# ---------------------------------------------------------------------------- monitor-mix example
# Starting IEM send levels (dB) by template category (sessionmaker.taxonomy): the medians of 7,400 active sends
# in the 192 stereo IEM-style mixes of 28 real sessions that have them (decode notes, not published), whole dB.
# 69 % of those sends are pre-fader, 30 % post-fader (dedicated monitor desks with the input faders at 0 dB).
MIX_BASE = {'kick_in': -7, 'kick_out': -2, 'kick_sub': -7, 'snare_top': -6, 'snare_bottom': -11, 'hihat': -19,
            'rack_tom': -7, 'floor_tom': -10, 'roto_tom': -5, 'overheads': -11, 'ride': -15, 'drum_crotch': -15,
            'drum_trigger': -17, 'sample_pad': -7, 'hand_perc': -12, 'bass_di': -10, 'bass_amp': -10,
            'synth_bass': -15, 'electric_guitar': -16, 'acoustic_guitar': -15, 'folk_strings': -20, 'strings': -16,
            'horns': -16, 'keys': -15, 'piano': -15, 'organ': -13, 'synth': -18, 'lead_vocal': -6,
            'vocal_generic': -12, 'vocal_fx_mic': -9, 'vocal_ear_split': -6, 'choir': -18, 'speech_mic': -11,
            'tracks_music': -14, 'tracks_drums_perc': -13, 'tracks_bass': -8, 'tracks_vocals': -14, 'click': -7,
            'cues_guide': -8, 'timecode': -150, 'media_playback': -8, 'audience': -19, 'measurement_ref': -150,
            'test_signal': -150, 'fx_reverb': -20, 'fx_delay': -19, 'fx_modulation': -18, 'fx_other': -20,
            'talkback': -4, 'comms_radio': -5, 'other': -15}
ONLY_ON_REQUEST = {'click', 'cues_guide'}   # sent only to the mixes that ask for them (mix['click'])
OWN_BOOST = 6.0                             # a player's own sources come up this much


def monitor_mixes(ses, chans, mixes, pre='pre', fader_db=0.0):
    """Starting IEM mixes. chans: [{'n': surface ch, 'name', 'category', 'stereo'}].
    mixes: [{'aux': surface aux, 'name': 'Drums IEM', 'own': [surface chs], 'click': bool}].
    Every mix gets every channel pre-fader at MIX_BASE[category] (own sources + OWN_BOOST, click only where asked),
    the aux renamed, its master at fader_db and unmuted. -> {aux: {ch: level}}."""
    out = {}
    for m in mixes:
        a = m['aux']
        name_bus(ses, 'aux', a, m['name'])
        set_bus_fader(ses, 'aux', a, db=fader_db, mute=False)
        stereo_aux = next(x['width'] for x in ses.auxes if x['number'] == a) == 2
        linked = stereo_aux and link_pans(ses, a) in (1, 2)
        own = set(m.get('own', []))
        lv = {}
        for c in chans:
            cat = c.get('category') or 'other'
            level = float(MIX_BASE.get(cat, MIX_BASE['other']))
            if cat in ONLY_ON_REQUEST and not m.get('click'):
                level = OFF_DB
            elif level > OFF_DB and c['n'] in own:
                level = min(MAX_DB, level + OWN_BOOST)
            if level <= OFF_DB:
                set_send(ses, c['n'], a, OFF_DB, on=False, pre=pre)
                continue
            pan = None
            if stereo_aux and not linked and not c.get('stereo'):
                pan = ses.get(ses.ch(c['n']), 0x0d, 0x23, 0)   # follow the channel's main pan (a linked aux derives it)
            set_send(ses, c['n'], a, level, on=True, pre=pre, pan=pan)
            lv[c['n']] = level
        out[a] = lv
    return out


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: python3 -m sessionmaker.sends file.ses  (aux and group masters, outputs, routes)')
        sys.exit(0 if len(sys.argv) > 1 else 2)
    s = Session(sys.argv[1])
    rb = read_buses(s)
    print('%s V%d: %d auxes, %d groups, master = group %s' % (s.model, s.version, len(rb['aux']), len(rb['group']),
                                                             rb['master']))
    for kind in ('aux', 'group'):
        for r in rb[kind]:
            print('  %-5s %2d %-12s %s fader %6.1f%s out %s%s' % (
                kind, r['n'], r['name'], 'st' if r['stereo'] else 'mo', r['fader'], ' MUTE' if r['mute'] else '',
                r['outputs'], (' -> groups %s' % r['routes']) if kind == 'group' and r['routes'] else ''))
