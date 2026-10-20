#!/usr/bin/env python3
"""busside.py - the bus side of a DiGiCo session, by bytes: masters, routing, matrix, control groups and the surface.

Newest module (2026-10-20); edit.py does not import it yet. It reads and
writes with sends.py's object index and leaves every existing writer alone.

Encodings (research: the surface round's bus audit, proved by a real-editor boot and re-save on Q225 V2242, Q225
V1619 and SD12 V2242; every key below holds in the 39 real sessions and the 128 editor defaults):
  Control groups   objects of type 0x0a, CG k = internal index + 1 (header byte 0x94 = the count). Module 10:
                   21 fader (dB, default 0), 22 mute, 19 mode (0 move fader, 1 vca style, 2 mute only),
                   1d aux send enable. Membership is a RAW u32 bitmask stored in a float slot on the member:
                   (0c, 04, band (k - 1) // 24), bit (k - 1) % 24. Read and write it with struct '<I'; a float
                   write corrupts it. Inputs, aux, group and matrix masters (both sides of a stereo bus) carry it.
  Matrix inputs    objects of type 0x0f, input n = position + 1 in internal-index order (header byte 0x96).
                   Source (01, 00, 0): raw 00 <side> <idx> <type> (06 group, 05 aux, 01 input; the right side of
                   a stereo source is side 1 with the left object's idx and type). Crosspoints are module 06 with
                   band = the matrix output's id & 0xff: 24 level (dB), 25 on, 08 delay (seconds), 07 delay on.
  Matrix outputs   type 0x10 (header byte 0x93), always mono, fader and mute like the other bus masters.
  Talkback         strips of type 0x0c in the surface banks (section 243).
  Surface banks    section 243 (ses.banks()); placement in section 212: 8 fader-section tables of 42 u16 bank
                   numbers (the bank's list position), position 6 * (layer - 1) + (bank - 1). Q225 (and the Pulse,
                   same file family) and SD12: table 3 is the LEFT bay and table 2 the RIGHT bay (Fader Banks screen
                   of the real editors). Other families have no confirmed map, so their bays are None.
Surface numbers throughout (sends.py's convention): aux, group and matrix numbers as on the console, inputs by
their strip number.

Readers are pure. Writers raise ValueError or KeyError with a plain sentence and check every input before the first
write.
"""
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ROOT  # ses.py and dlive2digico.py sit next to this package
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from ses import Record  # noqa: E402

from . import layout  # noqa: E402
from . import sends as S  # noqa: E402

T_INPUT, T_CG, T_TB, T_MTX_IN = 0x01, 0x0a, 0x0c, 0x0f
FX_TYPE = 0x0e
CG_COUNT_AT, MTX_OUT_AT, MTX_IN_AT = 0x94, 0x93, 0x96
CGM, CG_FADER, CG_MUTE, CG_MODE, CG_AUXSEND = 0x10, 0x21, 0x22, 0x19, 0x1d
MEMBER = (0x0c, 0x04)
MI_SRC = (0x01, 0x00, 0)
XP, XP_LEVEL, XP_ON, XP_DELAY, XP_DELAY_ON = 0x06, 0x24, 0x25, 0x08, 0x07
CG_MODES = {'move': 0, 'vca': 1, 'mute_only': 2}
CG_MODE_NAMES = {v: k for k, v in CG_MODES.items()}
SRC_TYPES = {'group': 0x06, 'aux': 0x05, 'input': 0x01}
SRC_KINDS = {v: k for k, v in SRC_TYPES.items()}
STRIP_KIND = {0x01: 'in', 0x05: 'aux', 0x06: 'grp', 0x10: 'mtx', 0x0a: 'cg', 0x0c: 'tb'}
# file family -> [(bay label, section 212 table)] where the real editor's Fader Banks screen confirmed the map
BAY_MAP = {'Q2': [('Left', 3), ('Right', 2)], 'SDC': [('Left', 3), ('Right', 2)]}
LAYERS, BANKS_PER_LAYER, LAYER_STRIDE = 3, 4, 6
OFF_DB, MAX_DB = S.OFF_DB, S.MAX_DB
NAME_MAX = S.NAME_MAX
MAX_DELAY_MS = 1000.0


# ---------------------------------------------------------------------------------------------------- small helpers
def _f(ses, off):
    return struct.unpack_from('<f', ses.d, off)[0]


def _r(x, nd=1):
    """A float for JSON: rounded, an int when whole (shorter), None when not finite."""
    if x is None or x != x or x in (float('inf'), float('-inf')):
        return None
    v = round(float(x), nd)
    return int(v) if v == int(v) else v


def _get(ses, o, module, param, band=0, default=None):
    return _f(ses, o.slot(module, param, band)) if o is not None and o.has(module, param, band) else default


def _by_type(objs, typ):
    return [objs[k] for k in sorted(k for k in objs if k >> 8 == typ)]


def _band_number(ses, kind):
    """{band: surface number} for 'aux' | 'group' | 'matrix'."""
    return {r['id'] & 0xff: r['number'] for r in ses.groups201.get(S.KINDS[kind], [])}


def _rside_map(ses):
    """{right-side object id: (kind, surface number)} of the stereo auxes and groups."""
    out = {}
    for kind in ('aux', 'group'):
        for r in ses.groups201.get(S.KINDS[kind], []):
            if r['width'] == 2:
                rid = struct.unpack_from('<H', ses.d, r['off'] + S.BUSSID_AT)[0]
                if rid:
                    out[rid] = (kind, r['number'])
    return out


def _label(kind, n, name):
    """'Aux 7 (Drums IEM)', 'Grp 1', 'Matrix 2 (RIGHT)', 'CG 2 (VOX)': the name only when it is not the default."""
    short = {'aux': 'Aux', 'group': 'Grp', 'matrix': 'Matrix', 'cg': 'CG'}[kind]
    nm = (name or '').strip()
    dflt = {'%s %d' % (w, n) for w in ('aux', 'grp', 'group', 'matrix', 'mtx', 'cg', 'control group')}
    if not nm or nm.lower() in dflt:
        return '%s %d' % (short, n)
    return '%s %d (%s)' % (short, n, nm)


def bus_label(ses, kind, n):
    if kind == 'cg':
        o = cg_object(ses, n)
        return _label('cg', n, o.name)
    return _label(kind, n, S.bus(ses, kind, n)['name'])


def counts(ses):
    """{'cg', 'mtx_in', 'mtx_out'} from the header (they match the objects in every file seen)."""
    d = ses.d
    return {'cg': d[CG_COUNT_AT], 'mtx_in': d[MTX_IN_AT], 'mtx_out': d[MTX_OUT_AT]}


# ---------------------------------------------------------------------------------------------------- objects
def cg_objects(ses):
    return _by_type(S.objects(ses), T_CG)


def cg_object(ses, k):
    objs = cg_objects(ses)
    o = S.objects(ses).get((T_CG << 8) | (int(k) - 1)) if 1 <= int(k) <= 256 else None
    if o is None:
        raise KeyError('This session has %d control groups, so there is no CG %d.' % (len(objs), k))
    return o


def mtx_in_objects(ses):
    return _by_type(S.objects(ses), T_MTX_IN)


def mtx_in_object(ses, n):
    lst = mtx_in_objects(ses)
    if not 1 <= int(n) <= len(lst):
        raise KeyError('This session has %d matrix inputs, so there is no input %d.' % (len(lst), n))
    return lst[int(n) - 1]


def member_oids(ses, kind, n):
    """Object ids that carry the CG membership of a channel or bus: 'in' (surface channel n), 'aux' | 'group' |
    'matrix' (both sides of a stereo bus)."""
    if kind == 'in':
        idx = ses.ch(n)
        if idx not in ses.by_index:
            raise KeyError('There is no channel %d in this session.' % n)
        return [(T_INPUT << 8) | (idx - 1)]
    b = S.bus(ses, kind, n)
    return [o.id for o in S._sides(b)]


# ---------------------------------------------------------------------------------------------------- group graph
def _routes(ses):
    """{group n: [groups it routes to]} (sends.bus_routes, read once)."""
    out = {}
    for g in ses.groups:
        try:
            out[g['number']] = S.bus_routes(ses, g['number'])
        except (KeyError, ValueError):
            out[g['number']] = []
    return out


def master_main(ses, routes=None):
    """(master group n, main group n). main starts at the master and follows single routes to the sink; it stops at
    a group with no routes or with more than one, and on a cycle. (None, None) when the session has no master."""
    m = S.master_group(ses)
    if m is None:
        return None, None
    routes = _routes(ses) if routes is None else routes
    cur, seen = m, {m}
    while len(routes.get(cur, [])) == 1:
        nxt = routes[cur][0]
        if nxt in seen:
            break
        seen.add(nxt)
        cur = nxt
    return m, cur


def _reaches(routes, a, b):
    """True when group a reaches group b through the routes (a == b counts)."""
    if a == b:
        return True
    stack, seen = [a], {a}
    while stack:
        for x in routes.get(stack.pop(), []):
            if x == b:
                return True
            if x not in seen:
                seen.add(x)
                stack.append(x)
    return False


def would_cycle(ses, group_n, to_ns, routes=None):
    """True when routing group `group_n` to `to_ns` would make a loop (a target that already reaches it)."""
    routes = _routes(ses) if routes is None else routes
    return any(_reaches(routes, t, group_n) for t in to_ns)


def _cycle(routes):
    for g in routes:
        for t in routes[g]:
            if _reaches(routes, t, g):
                return g
    return None


# ---------------------------------------------------------------------------------------------------- readers
def _out_map(ses):
    """{raw source route: [socket names]} of every output socket, read once."""
    out = {}
    try:
        socks = S.output_sockets(ses)
    except (ValueError, KeyError, struct.error, TypeError):
        return out
    objs = S.objects(ses)
    for s in socks:
        o = objs.get(s['id'])
        if o is None or not o.has(S.SOCKET, S.SK_SOURCE):
            continue
        q = o.slot(S.SOCKET, S.SK_SOURCE)
        raw = bytes(ses.d[q:q + 4])
        if raw != b'\0\0\0\0':
            out.setdefault(raw, []).append(s['name'])
    return out


def _outputs(omap, b):
    sides = [omap.get(S._route(o.id & 0xff, o.id >> 8), []) for o in S._sides(b)]
    return sides if any(sides) else None


def cg_members(ses):
    """({object id: [CG k]}, {CG k: [object id]}) from every live object's membership bits."""
    by_obj, by_cg = {}, {}
    for oid, o in sorted(S.objects(ses).items()):
        ks = []
        for band in (0, 1):
            if o.has(MEMBER[0], MEMBER[1], band):
                v = struct.unpack_from('<I', ses.d, o.slot(MEMBER[0], MEMBER[1], band))[0]
                ks += [band * 24 + bit + 1 for bit in range(24) if v >> bit & 1]
        if ks:
            by_obj[oid] = ks
            for k in ks:
                by_cg.setdefault(k, []).append(oid)
    return by_obj, by_cg


def _aux_role(feeds, stereo, active, pre):
    if feeds:
        return 'fx'
    if not active:
        return 'unused'
    if stereo and pre * 2 >= active:
        return 'iem'
    if not stereo and pre * 2 >= active:
        return 'wedge'
    return 'mix'


def read_channel_ext(ses, cgs_by_obj=None, master=None):
    """{internal idx: {'sends_all': [[level_db, on01, pre, pan | None]] aligned to the auxes by number,
    'main': routed to the master group, 'cgs': [k]}} of every live input."""
    if cgs_by_obj is None:
        cgs_by_obj = cg_members(ses)[0]
    if master is None:
        master = S.master_group(ses)
    mband = ses.group_band.get(master) if master is not None else None
    auxes = [(a['band'], a['width'] == 2) for a in ses.auxes]
    out = {}
    for c in ses.inputs:
        rs = c.records.get(S.SEND)
        sl = rs.slots if rs is not None else {}
        row = []
        for band, st in auxes:
            q = sl.get((S.S_LEVEL, band))
            lv = _f(ses, q) if q is not None else OFF_DB
            q = sl.get((S.S_ON, band))
            on = 1 if q is not None and _f(ses, q) > .5 else 0
            q = sl.get((S.S_PREPOST, band))
            pp = int(round(_f(ses, q))) if q is not None else 0
            pan = None
            if st:
                q = sl.get((S.S_PAN, band))
                pan = _r(_f(ses, q), 2) if q is not None else None
            row.append([_r(max(OFF_DB, lv)), on, pp, pan])
        rg = c.records.get(S.GROUPS)
        main = False
        if rg is not None and mband is not None and (S.G_ASSIGN, mband) in rg.slots:
            main = _f(ses, rg.slots[(S.G_ASSIGN, mband)]) > .5
        out[c.index] = {'sends_all': row, 'main': main, 'cgs': cgs_by_obj.get((T_INPUT << 8) | (c.index - 1), [])}
    return out


def read_bus_side(ses, model=None, members=None, chan_ext=None):
    """The model's bus_side block: masters, routing, matrix, control groups and surface placement."""
    objs = S.objects(ses)
    by_obj, by_cg = members if members is not None else cg_members(ses)
    routes = _routes(ses)
    master, main = master_main(ses, routes)
    omap = _out_map(ses)
    feeds_m = {}
    for a in (model or {}).get('auxes') or []:
        if isinstance(a, dict) and isinstance(a.get('n'), int):
            feeds_m[a['n']] = a.get('feeds_fx') or []
    if chan_ext is None:
        chan_ext = read_channel_ext(ses, by_obj, master)
    # active sends per aux position, for the role rule
    nax = len(ses.auxes)
    act, pre = [0] * nax, [0] * nax
    for row in chan_ext.values():
        for j, (lv, on, pp, _) in enumerate(row['sends_all']):
            if on and lv is not None and lv > OFF_DB:
                act[j] += 1
                if pp in (1, 2):
                    pre[j] += 1
    out = {'v': 1, 'master': master, 'main': main, 'aux': [], 'group': [], 'matrix_out': [], 'matrix_in': [],
           'cg': [], 'talkback': []}
    for j, b in enumerate(S.buses(ses, 'aux')):
        o, st = b['obj'], b['width'] == 2
        if b['number'] in feeds_m:
            feeds = feeds_m[b['number']]
        else:
            feeds = []
            for x in S._sides(b):
                if x.has(S.OUT, S.O_ROUTE):
                    q = x.slot(S.OUT, S.O_ROUTE)
                    if ses.d[q + 3] == FX_TYPE:
                        feeds = [ses.d[q + 2] + 1]
        lp = int(round(_get(ses, o, S.FADER, S.F_LINKPANS, default=0) or 0)) if st else 0
        out['aux'].append({'id': 'aux:%d' % b['number'], 'n': b['number'], 'name': b['name'], 'stereo': st,
                           'fader_db': _r(_get(ses, o, S.FADER, S.F_FADER, default=OFF_DB)),
                           'muted': (_get(ses, o, S.FADER, S.F_MUTE, default=0) or 0) > .5,
                           'link_pans': S.LINK_NAMES.get(lp, 'off'), 'feeds_fx': list(feeds),
                           'outputs': _outputs(omap, b), 'cgs': by_obj.get(o.id, []),
                           'role': _aux_role(feeds, st, act[j] if j < nax else 0, pre[j] if j < nax else 0)})
    gins = {}
    mband = {g['band']: g['number'] for g in ses.groups}
    for c in ses.inputs:
        rg = c.records.get(S.GROUPS)
        if rg is None:
            continue
        for (p, band), q in rg.slots.items():
            if p == S.G_ASSIGN and band in mband and _f(ses, q) > .5:
                gins.setdefault(mband[band], []).append(c.index)
    surf = {idx: n for n, idx in ses.display.items()}
    aux_bands = [(a['band'], a['width'] == 2) for a in ses.auxes]
    for b in S.buses(ses, 'group'):
        o, st, n = b['obj'], b['width'] == 2, b['number']
        sides = S._sides(b)
        snd = []
        for band, ast in aux_bands:
            lv = _get(ses, o, S.SEND, S.S_LEVEL, band, OFF_DB)
            on = 1 if (_get(ses, o, S.SEND, S.S_ON, band, 0) or 0) > .5 else 0
            pp = int(round(_get(ses, o, S.SEND, S.S_PREPOST, band, 0) or 0))
            pan = None
            if ast:
                pans = [_r(_get(ses, x, S.SEND, S.S_PAN, band, 0), 2) for x in sides]
                pan = pans if st else pans[0]
            snd.append([_r(max(OFF_DB, lv if lv is not None else OFF_DB)), on, pp, pan])
        rts = routes.get(n, [])
        ins = sorted(gins.get(n, []), key=lambda i: surf.get(i, 10 ** 6))
        out['group'].append({'id': 'grp:%d' % n, 'n': n, 'name': b['name'], 'stereo': st,
                             'fader_db': _r(_get(ses, o, S.FADER, S.F_FADER, default=OFF_DB)),
                             'muted': (_get(ses, o, S.FADER, S.F_MUTE, default=0) or 0) > .5,
                             'routes': rts, 'main': master is not None and master in rts,
                             'reaches_main': main is not None and _reaches(routes, n, main),
                             'inputs': ['c%d' % i for i in ins], 'outputs': _outputs(omap, b),
                             'cgs': by_obj.get(o.id, []), 'sends': snd})
    mouts = S.buses(ses, 'matrix')
    for b in mouts:
        o = b['obj']
        out['matrix_out'].append({'id': 'mtx:%d' % b['number'], 'n': b['number'], 'name': b['name'],
                                  'fader_db': _r(_get(ses, o, S.FADER, S.F_FADER, default=OFF_DB)),
                                  'muted': (_get(ses, o, S.FADER, S.F_MUTE, default=0) or 0) > .5,
                                  'outputs': _outputs(omap, b), 'cgs': by_obj.get(o.id, [])})
    aux_n, grp_n = _band_number(ses, 'aux'), _band_number(ses, 'group')
    for k, o in enumerate(mtx_in_objects(ses)):
        src = None
        if o.has(*MI_SRC):
            q = o.slot(*MI_SRC)
            raw = bytes(ses.d[q:q + 4])
            if raw != b'\0\0\0\0':
                kind = SRC_KINDS.get(raw[3], 'other')
                n = None
                if kind == 'group':
                    n = grp_n.get(raw[2])
                elif kind == 'aux':
                    n = aux_n.get(raw[2])
                elif kind == 'input':
                    n = surf.get(raw[2] + 1)
                if n is None:
                    kind = 'other'
                src = {'kind': kind, 'n': n, 'side': raw[1]}
        snd = []
        for b in mouts:
            band = b['band']
            lv = _get(ses, o, XP, XP_LEVEL, band, OFF_DB)
            on = 1 if (_get(ses, o, XP, XP_ON, band, 0) or 0) > .5 else 0
            don = (_get(ses, o, XP, XP_DELAY_ON, band, 0) or 0) > .5
            dl = _get(ses, o, XP, XP_DELAY, band, 0) or 0
            snd.append([_r(max(OFF_DB, lv if lv is not None else OFF_DB)), on, _r(dl * 1000.0, 2) if don else 0])
        out['matrix_in'].append({'n': k + 1, 'name': o.name, 'source': src, 'sends': snd})
    rmap = _rside_map(ses)
    for o in cg_objects(ses):
        k = (o.id & 0xff) + 1
        mem = []
        for oid in by_cg.get(k, []):
            t = oid >> 8
            if t == T_INPUT:
                mem.append({'t': 'in', 'id': 'c%d' % ((oid & 0xff) + 1)})
            elif t in (S.T_AUX, S.T_GROUP, S.T_MATRIX):
                kind = {S.T_AUX: 'aux', S.T_GROUP: 'group', S.T_MATRIX: 'matrix'}[t]
                n = _band_number(ses, kind).get(oid & 0xff)
                if n is not None:
                    mem.append({'t': {'aux': 'aux', 'group': 'grp', 'matrix': 'mtx'}[kind], 'n': n})
            elif t == T_TB:
                mem.append({'t': 'tb', 'n': (oid & 0xff) + 1})
            elif t == S.T_RSIDE and oid not in rmap:
                continue
        mode = _get(ses, o, CGM, CG_MODE, default=1)
        out['cg'].append({'id': 'cg:%d' % k, 'k': k, 'name': o.name,
                          'fader_db': _r(_get(ses, o, CGM, CG_FADER, default=0)),
                          'muted': (_get(ses, o, CGM, CG_MUTE, default=0) or 0) > .5,
                          'mode': CG_MODE_NAMES.get(int(round(mode or 0)), 'vca'),
                          'aux_send_enable': (_get(ses, o, CGM, CG_AUXSEND, default=0) or 0) > .5,
                          'members': mem})
    try:
        tbs = sorted({i + 1 for b in ses.banks() for t, i in b['strips'] if t == T_TB})
    except (ValueError, struct.error, IndexError):
        tbs = []
    out['talkback'] = [{'id': 'tb:%d' % n, 'n': n, 'name': 'Talkback %d' % n} for n in tbs]
    return out


# ---------------------------------------------------------------------------------------------------- the surface
def _strip(ses, typ, idx, maps):
    aux_n, grp_n, mtx_n, rmap = maps
    if typ == T_INPUT:
        return {'t': 'in', 'id': 'c%d' % (idx + 1)} if idx + 1 in ses.by_index else None
    if typ == S.T_AUX:
        n = aux_n.get(idx)
        return {'t': 'aux', 'n': n} if n is not None else None
    if typ == S.T_GROUP:
        n = grp_n.get(idx)
        return {'t': 'grp', 'n': n} if n is not None else None
    if typ == S.T_MATRIX:
        n = mtx_n.get(idx)
        return {'t': 'mtx', 'n': n} if n is not None else None
    if typ == T_CG:
        return {'t': 'cg', 'n': idx + 1}
    if typ == T_TB:
        return {'t': 'tb', 'n': idx + 1}
    if typ == S.T_RSIDE:
        hit = rmap.get((S.T_RSIDE << 8) | idx)
        if hit:
            return {'t': 'aux' if hit[0] == 'aux' else 'grp', 'n': hit[1]}
    return None


def _kind(strips):
    ts = {s['t'] for s in strips if s}
    if not ts:
        return 'empty'
    return ts.pop() if len(ts) == 1 else 'mixed'


def default_banks(ses):
    """Banks of 12 when the file has none: inputs in surface order, then aux, group, matrix and CG masters."""
    out = []

    def add(label_kind, items, t):
        for k in range(0, len(items), 12):
            chunk = items[k:k + 12]
            strips = [({'t': t, 'id': x} if t == 'in' else {'t': t, 'n': x}) for x in chunk]
            first, last = k + 1, k + len(chunk)
            label = '%s %d-%d' % (label_kind, first, last) if last > first else '%s %d' % (label_kind, first)
            out.append({'i': len(out), 'label': label, 'kind': t, 'strips': strips + [None] * (12 - len(strips)),
                        'views': ['sd'] * 12})
    add('Ch', ['c%d' % ses.display[n] for n in sorted(ses.display)], 'in')
    add('Aux', [a['number'] for a in ses.auxes], 'aux')
    add('Grp', [g['number'] for g in ses.groups], 'grp')
    add('Mtx', sorted(r['number'] for r in ses.groups201.get(S.T_MATRIX, [])), 'mtx')
    add('CG', [(o.id & 0xff) + 1 for o in cg_objects(ses)], 'cg')
    return out


def read_surface(ses, family):
    """The model's surface block: banks from section 243, bays from section 212 where the map is confirmed."""
    skin = 'q' if family in layout.QUANTUM_FAMILIES else 'sd'
    try:
        raw = ses.banks()
    except (ValueError, struct.error, IndexError):
        raw = []
    if not raw:
        return {'v': 1, 'skin': skin, 'source': 'default', 'banks': default_banks(ses), 'bays': None}
    maps = (_band_number(ses, 'aux'), _band_number(ses, 'group'), _band_number(ses, 'matrix'), _rside_map(ses))
    banks = []
    for i, b in enumerate(raw):
        strips = [_strip(ses, t, x, maps) for t, x in b['strips']]
        views = ['mustard' if ses.d[b['view'] + j] == ses.VIEW_MUSTARD else 'sd' for j in range(12)]
        banks.append({'i': i, 'label': b['name'] or 'Bank %d' % (i + 1), 'kind': _kind(strips), 'strips': strips,
                      'views': views})
    bays = None
    if family in BAY_MAP:
        sp = ses.section_span(212)
        if sp is not None:
            try:
                tabs = layout._tables(bytes(ses.d[sp[0]:sp[1]]))
                bays = []
                for label, u in BAY_MAP[family]:
                    tab = tabs[u]
                    layers = [[(tab[LAYER_STRIDE * L + j] if tab[LAYER_STRIDE * L + j] < len(banks) else None)
                               for j in range(BANKS_PER_LAYER)] for L in range(LAYERS)]
                    bays.append({'label': label, 'layers': layers})
            except (struct.error, IndexError):
                bays = None
    return {'v': 1, 'skin': skin, 'source': 'session', 'banks': banks, 'bays': bays}


# ---------------------------------------------------------------------------------------------------- checks
def routing_errors(ses):
    """Hard routing errors, as sentences: a loop in group routing, an assign or route that names a band with no
    group, a matrix input source that names a missing object. [] on every real session and editor default."""
    errs = []
    objs = S.objects(ses)
    gb = {g['band'] for g in ses.groups}
    for oid, o in objs.items():
        if oid >> 8 not in (T_INPUT, S.T_GROUP, S.T_RSIDE):
            continue
        for (p, band), q in o.mods.get(S.GROUPS, {}).items():
            if p == S.G_ASSIGN and band not in gb and _f(ses, q) > .5:
                errs.append('%s is routed to group band %d, which is not in the session' % (o.name, band))
                break
    routes = _routes(ses)
    g = _cycle(routes)
    if g is not None:
        errs.append('group %d routes back into itself' % g)
    for o in mtx_in_objects(ses):
        if o.has(*MI_SRC):
            q = o.slot(*MI_SRC)
            raw = bytes(ses.d[q:q + 4])
            if raw != b'\0\0\0\0' and ((raw[3] << 8) | raw[2]) not in objs:
                errs.append('%s takes its source from %s, which is not in the session' % (o.name, raw.hex()))
    return errs


def _names(xs, limit=3):
    xs = list(xs)
    if len(xs) <= limit:
        return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' and ' + xs[-1]
    return '%s and %d more' % (', '.join(xs[:limit]), len(xs) - limit)


def routing_notes(ses, ns=None, groups=None):
    """Soft warnings after a routing change: channels `ns` (surface numbers) that now feed nothing (no group and no
    active aux send), and groups `groups` that do not reach the main bus or whose fader is off."""
    notes = []
    master = S.master_group(ses)
    routes = _routes(ses)
    _, main = master_main(ses, routes)
    if ns:
        dead = []
        for n in ns:
            idx = ses.ch(n)
            c = ses.by_index.get(idx)
            if c is None:
                continue
            if S.groups_of(ses, n):
                continue
            rs = c.records.get(S.SEND)
            live = False
            if rs is not None:
                for a in ses.auxes:
                    ql, qo = rs.slots.get((S.S_LEVEL, a['band'])), rs.slots.get((S.S_ON, a['band']))
                    if ql is not None and qo is not None and _f(ses, qo) > .5 and _f(ses, ql) > OFF_DB:
                        live = True
                        break
            if not live:
                dead.append(c.name.strip() or 'Channel %d' % n)
        if dead:
            notes.append('%s now feed%s nothing.' % (_names(dead), 's' if len(dead) == 1 else ''))
    for g in groups or []:
        if g in (master, main):
            continue
        try:
            b = S.bus(ses, 'group', g)
        except KeyError:
            continue
        lab = _label('group', g, b['name'])
        if main is not None and not _reaches(routes, g, main):
            notes.append('%s does not reach the Master.' % lab)
        if _get(ses, b['obj'], S.FADER, S.F_FADER, default=0) <= OFF_DB:
            notes.append("%s's fader is off." % lab)
    return notes


# ---------------------------------------------------------------------------------------------------- writers
def set_cg_member(ses, oid, k, on):
    """Set or clear CG k's bit on object `oid` (one side; member_oids gives both sides of a stereo bus)."""
    k = int(k)
    o = S.objects(ses).get(oid)
    band, bit = (k - 1) // 24, (k - 1) % 24
    if o is None or not o.has(MEMBER[0], MEMBER[1], band):
        raise KeyError('That channel can not join control group %d.' % k)
    q = o.slot(MEMBER[0], MEMBER[1], band)
    v = struct.unpack_from('<I', ses.d, q)[0]
    v = v | (1 << bit) if on else v & ~(1 << bit)
    struct.pack_into('<I', ses.d, q, v & 0xffffffff)
    return v


def is_cg_member(ses, oid, k):
    o = S.objects(ses).get(oid)
    band, bit = (int(k) - 1) // 24, (int(k) - 1) % 24
    if o is None or not o.has(MEMBER[0], MEMBER[1], band):
        return False
    return bool(struct.unpack_from('<I', ses.d, o.slot(MEMBER[0], MEMBER[1], band))[0] >> bit & 1)


def set_cg_master(ses, k, fader_db=None, mute=None, mode=None, aux_send_enable=None):
    o = cg_object(ses, k)
    m = None
    if mode is not None:
        m = CG_MODES.get(mode) if isinstance(mode, str) else int(mode)
        if m not in (0, 1, 2):
            raise ValueError('A control group mode is vca, move or mute only.')
    for p, v in ((CG_FADER, fader_db), (CG_MUTE, mute), (CG_MODE, m), (CG_AUXSEND, aux_send_enable)):
        if v is not None and not o.has(CGM, p):
            raise KeyError('Control group %d has no %02x setting in this file.' % (k, p))
    if fader_db is not None:
        struct.pack_into('<f', ses.d, o.slot(CGM, CG_FADER), S._db(fader_db))
    if mute is not None:
        struct.pack_into('<f', ses.d, o.slot(CGM, CG_MUTE), 1.0 if mute else 0.0)
    if m is not None:
        struct.pack_into('<f', ses.d, o.slot(CGM, CG_MODE), float(m))
    if aux_send_enable is not None:
        struct.pack_into('<f', ses.d, o.slot(CGM, CG_AUXSEND), 1.0 if aux_send_enable else 0.0)
    return o


def records_named(ses, names):
    """Every module record in the file (live, snapshot or library copy) whose name field is one of `names`."""
    out = {}
    for nm in names:
        try:
            nb = nm.encode('latin1')
        except UnicodeEncodeError:
            continue
        if not nb or len(nb) > 31:
            continue
        pat = re.compile(re.escape(layout.REC) + b'..\x00\x00' + re.escape(bytes([len(nb)]) + nb), re.S)
        for m in pat.finditer(ses.d):
            p = m.start()
            if p not in out and Record.valid(ses.d, p):
                out[p] = Record(ses.d, p)
    return [out[p] for p in sorted(out)]


def _clean_name(name):
    name = (name or '').strip()
    if not name:
        raise ValueError('Say the new name.')
    if len(name) > NAME_MAX:
        raise ValueError('Bus names are %d characters at most.' % NAME_MAX)
    try:
        name.encode('latin1')
    except UnicodeEncodeError:
        raise ValueError('Use plain letters and numbers in the name.')
    return name


def _rename(ses, o, name):
    """sends._rename_object with ses.records narrowed to the records carrying the object's current name."""
    saved = ses.records
    ses.records = records_named(ses, {o.name})
    try:
        n = S._rename_object(ses, o.id, name)
    finally:
        ses.records = saved
    for recs in ses.groups201.values():
        for r in recs:
            if r['id'] == o.id:
                r['name'] = name
    o.name = name
    return n


def cg_name(ses, k, name):
    """Rename control group k (every copy: its module records, trailer and channel record). -> copies written."""
    name = _clean_name(name)
    return _rename(ses, cg_object(ses, k), name)


def matrix_input_name(ses, n, name):
    name = _clean_name(name)
    return _rename(ses, mtx_in_object(ses, n), name)


def source_raw(ses, kind, src_n, side=0):
    """The raw source route for a matrix input: 00 <side> <idx> <type>."""
    if kind in (None, 'none'):
        return b'\0\0\0\0'
    if kind not in SRC_TYPES:
        raise ValueError('A matrix input takes a group, an aux or an input.')
    if kind == 'input':
        idx = ses.ch(int(src_n))
        if idx not in ses.by_index:
            raise KeyError('There is no channel %d in this session.' % src_n)
        return bytes((0, side, (idx - 1) & 0xff, SRC_TYPES[kind]))
    b = S.bus(ses, kind, int(src_n))
    return bytes((0, side, b['band'], SRC_TYPES[kind]))


def source_width(ses, kind, src_n):
    if kind in (None, 'none'):
        return 1
    if kind == 'input':
        return ses.width.get(int(src_n), 1)
    return S.bus(ses, kind, int(src_n))['width']


def set_matrix_source(ses, n, kind, src_n=None, side=0):
    o = mtx_in_object(ses, n)
    raw = source_raw(ses, kind, src_n, side)
    if not o.has(*MI_SRC):
        raise KeyError('Matrix input %d has no source setting in this file.' % n)
    q = o.slot(*MI_SRC)
    ses.d[q:q + 4] = raw
    return raw


def matrix_source(ses, n):
    o = mtx_in_object(ses, n)
    if not o.has(*MI_SRC):
        return b'\0\0\0\0'
    q = o.slot(*MI_SRC)
    return bytes(ses.d[q:q + 4])


def set_matrix_send(ses, in_n, out_n, level_db=None, on=None, delay_ms=None):
    o = mtx_in_object(ses, in_n)
    b = S.bus(ses, 'matrix', int(out_n))
    band = b['band']
    for p in (XP_LEVEL, XP_ON, XP_DELAY, XP_DELAY_ON):
        if not o.has(XP, p, band):
            raise KeyError('Matrix input %d has no crosspoint to matrix %d in this file.' % (in_n, out_n))
    if delay_ms is not None:
        delay_ms = float(delay_ms)
        if not 0 <= delay_ms <= MAX_DELAY_MS:
            raise ValueError('A matrix delay is 0 to %d ms.' % MAX_DELAY_MS)
    if level_db is not None:
        struct.pack_into('<f', ses.d, o.slot(XP, XP_LEVEL, band), S._db(level_db))
    if on is not None:
        struct.pack_into('<f', ses.d, o.slot(XP, XP_ON, band), 1.0 if on else 0.0)
    if delay_ms is not None:
        struct.pack_into('<f', ses.d, o.slot(XP, XP_DELAY, band), delay_ms / 1000.0)
        struct.pack_into('<f', ses.d, o.slot(XP, XP_DELAY_ON, band), 1.0 if delay_ms > 0 else 0.0)
    return read_matrix_send(ses, in_n, out_n)


def read_matrix_send(ses, in_n, out_n):
    o = mtx_in_object(ses, in_n)
    band = S.bus(ses, 'matrix', int(out_n))['band']
    don = _get(ses, o, XP, XP_DELAY_ON, band, 0) > .5
    return {'level': _get(ses, o, XP, XP_LEVEL, band, OFF_DB), 'on': _get(ses, o, XP, XP_ON, band, 0) > .5,
            'delay_ms': (_get(ses, o, XP, XP_DELAY, band, 0) * 1000.0) if don else 0.0}


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: python3 -m sessionmaker.busside file.ses  (bus side as JSON: masters, matrix, control groups, surface)')
        sys.exit(0 if len(sys.argv) > 1 else 2)
    import json
    from ses import Session
    s = Session(sys.argv[1])
    print(json.dumps({'bus_side': read_bus_side(s), 'surface': read_surface(s, s.model),
                      'errors': routing_errors(s)}, indent=1)[:6000])
