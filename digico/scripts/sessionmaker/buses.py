#!/usr/bin/env python3
"""buses.py - change the bus layout of a DiGiCo .ses by bytes (what Files > Session Structure does for buses).

    restructure(data, aux_mono, aux_stereo, grp_mono, grp_stereo, matrix=None, cgs=None, console=None) -> bytes
    describe(data) -> dict
    bus_limit(data, console=None) -> int | None     (mono-equivalent bus budget of the console)

Editor-proved on all 14 consoles at V2242 (FOH 8 mono aux + 8 stereo groups, monitor 2 mono + 16 stereo aux).
The Session Structure dialog stops at the bus budget. On load the editor keeps a file up to budget + 4 and replaces
it with its default session from budget + 5 (Q112, SD11, Q225, SD12 at V2242; Q225 V1455/V1619, SD12 V1619 the
same), so restructure() refuses anything over the budget.

Research and proofs: the decode notes (not published). Field map (V2242 offsets; the same fields exist back to V1455):

  header     tConsoleRec at 0x24: u16 nAuxes[0..1] @0x36/0x38 (mono, stereo), nGroups[0..2] @0x46/0x48/0x4a
             (mono, stereo, LCR), MasterGroupID u8 @0x5c (the master is group 0x0600 | id, always stereo),
             nMatrixOutputs @0x93, nControlGroups @0x94, nMatrixInputs @0x96.
  sect. 201  channel records (cb 00 hl 00) grouped by type: 05 'Aux Outputs', 06 'Group Outputs', 07 'Busses'
             (the right side of every stereo aux and group: aux R first, then group R, each in surface order).
             Record order = surface order, mono buses first. +4 id (type << 8 | internal index), +6 surface
             number, +8 name[32], +41 width, +54 BussID (stereo L -> its R id, R -> its L id, mono 0),
             +84 EngineChannel (R = L + 1). The last byte of a group record is GroupAuxSendEnabled (0 on Master).
  sect. 211  one object per bus (05 aux, 06 group, 07 right side), sorted by id; 'd3 00' + u32 object count.
             Every bus has (05,0x14,0) = the other side's id (raw 00 00 idx type) when stereo. Per-bus modules
             in other objects grow and shrink with the layout: module 02 (aux sends, 12 params per aux,
             aux-major) on inputs, groups, group R sides and TB In; module 03 (group assign, 1 param per group;
             TB In 2 params, param-major) on the same objects; module 21 (talkback to aux, 1 param per aux
             after 2 fixed slots) on the Talkback Outputs. Bands are internal indices, in surface order.
  sect. 243  banks of 12 strips (type 05 aux, 06 group, index = internal index); aux and group banks are
             rebuilt in surface order and named 'Aux 1-12', 'Grp 1-8', ...
  sect. 212  bank placement (also copied in the 211 tail): output banks are dealt over the positions they used.
  engine     Quantum: groups from 0 (surface order, stereo takes 2), then auxes, then the 2 solo buses (+0, +8).
             SD: groups from 0, then the inputs and TB In (they move when the group width changes), auxes end
             right below the first matrix output; the 2 solo buses at 0 and min(8, 126 - total bus width).

The editor's rules this copies (proved by GUI captures of Session Structure, see the research note):
  - removed buses come off the end of each width class; the master group is never removed (min 1 stereo group);
  - new buses get the lowest internal index no bus of that type used before the change (right sides from 8)
    and default names; buses with default names ('Aux 7', 'Grp 8 R') are renamed to their new surface
    number, other names are kept;
  - send/assign slots of kept buses keep their values; new ones get the editor default (the most common value).
References to a removed bus (input patch, sidechain keys, FX unit inputs, matrix inputs, output sockets) are
cleared. Matrix and control-group counts are not changed: the editor greys them out on Q112, Q225, Q338, SD5CS,
SD8, SD9, SD10, SD11 and SD12 and lets you set them on Q5, Q7, Q852, SD5 and SD7 (not mapped yet), so `matrix`
and `cgs` are only checked against the file.
"""
import os
import re
import struct
from collections import Counter

from .layout import Container, objects, obj_id, obj_records, sstr31, banks as split_banks, bank_slot, \
    set_bank_slot, QUANTUM_FAMILIES

T_INPUT, T_AUX, T_GROUP, T_RIGHT, T_CG, T_SOLO, T_TB, T_MTX_IN, T_MTX_OUT = 1, 5, 6, 7, 0x0a, 0x0b, 0x0c, 0x0f, 0x10
CB_HL = (0x50, 0x58, 0x78, 0x79)
GROUP_HDR = b'\xca\x00\x6c\x00'
HDR_AUX, HDR_GRP, HDR_MASTER = 0x36, 0x46, 0x5c
HDR_MTX_OUT, HDR_CG, HDR_MTX_IN = 0x93, 0x94, 0x96
PER_AUX = (0x02, 0x21)         # modules whose slots run once per aux (band = aux internal index)
PER_GRP = (0x03,)              # modules whose slots run once per group
FIXED = {(0x21, 0xff), (0x21, 0xe3)}   # fixed slots inside per-bus modules
BAND_MAJOR = (0x02,)           # aux sends run aux by aux; group assigns (TB In) run param by param
KEY_ROUTE = (0x05, 0x14, 0)
# slots that hold a raw channel id (00 00 idx type): (object type or None for any, module, param)
REF_SLOTS = [(None, 0x01, 0x00), (None, 0x05, 0x14), (None, 0x05, 0x16), (T_SOLO, 0x17, 0x00),
             (0x0e, 0x15, 0x00), (T_MTX_IN, 0x01, 0x00), (0x18, 0x1f, 0x16)] + \
            [(t, 0x12, 0x00) for t in range(0x4d, 0x55)]
DEFAULT_NAME = re.compile(r'^(Aux|Grp) \d+( R)?$')
# Session Structure 'busses' budget per console (mono equivalents, 48 kHz): used + the dialog's spare counter in
# the V2242 editor (decode notes, not published). The editor loads up to budget + 4 and drops the layout (default session)
# from budget + 5. The older editors tested load to the same point (Q225 V1455/V1619 and SD12 V1619: 42 kept, 43
# dropped; Q338 V2025 drops 74), so the budget is applied at every build. 96 kHz budgets are not measured.
BUS_LIMIT = {'q112': 26, 'q225': 38, 'q225p': 50, 'q338': 66, 'q338p': 74, 'q5': 130, 'q7': 130, 'q852': 194, 'sd5': 124, 'sd5cs': 58,
             'sd7': 124, 'sd8': 50, 'sd9': 50, 'sd10': 66, 'sd11': 26, 'sd12': 38}
BUS_LIMIT_BUILD = 2242          # build the budgets were read at
FAMILY_CONSOLES = {'Q1': ['q112'], 'Q2': ['q225', 'q225p'], 'Q3': ['q338', 'q338p'], 'Q5': ['q5'], 'SDQ': ['q7'], 'Q8': ['q852'],
                   'SD5': ['sd5', 'sd5cs'], 'SD7': ['sd7'], 'SD8': ['sd8', 'sd10'], 'SD9': ['sd9', 'sd11'],
                   'SDC': ['sd12']}


def bus_limit(data, console=None):
    """Bus budget for this session's console (None when unknown). SD8/SD10, SD9/SD11 and SD5/SD5CS share a file
    family, so pass `console` (the consoles.py key); without it the smaller budget is used. Read at V2242 and
    applied at every build (older editors tested drop over-budget files at the same point)."""
    c = data if isinstance(data, Container) else Container(data)
    keys = [console] if console else FAMILY_CONSOLES.get(bytes(c.head[11:15]).decode('latin1').strip(), [])
    vals = [BUS_LIMIT.get(k) for k in keys]
    if not vals or None in vals:
        return None
    return min(vals)


u16 = lambda b, o: struct.unpack_from('<H', b, o)[0]
u32 = lambda b, o: struct.unpack_from('<I', b, o)[0]


# ---------------------------------------------------------------------------- section 201
def groups(s):
    """{type: [header offset, first record, end, [record bytearrays]]} for the well-formed groups of section 201."""
    s, out = bytes(s), {}
    for m in re.finditer(re.escape(GROUP_HDR), s):
        q = m.start()
        if q + 0x74 > len(s) or s[q + 5] > 31:
            continue
        typ, cnt, p, recs = s[q + 4], u32(s, q + 0x70), q + 0x74, []
        for _ in range(cnt):
            if p + 8 > len(s) or s[p:p + 2] != b'\xcb\x00' or s[p + 2] not in CB_HL or u16(s, p + 4) >> 8 != typ:
                recs = None
                break
            recs.append(bytearray(s[p:p + 4 + s[p + 2]]))
            p += 4 + s[p + 2]
        if recs is not None and typ not in out:
            out[typ] = [q, q + 0x74, p, recs]
    return out


def rec_name(r):
    return bytes(r[9:9 + min(r[8], 31)]).decode('latin1')


def has_engine(r):
    return len(r) >= 88


class Bus:
    __slots__ = ('kind', 'id', 'width', 'name', 'rid', 'rec', 'rrec', 'new', 'master')

    def __init__(self, kind, cid, width, name, rid=None, rec=None, rrec=None, new=False, master=False):
        self.kind, self.id, self.width, self.name, self.rid = kind, cid, width, name, rid
        self.rec, self.rrec, self.new, self.master = rec, rrec, new, master

    def __repr__(self):
        return '%s%04x%s' % (self.kind, self.id, 'S' if self.width == 2 else 'M')


def bus_lists(c):
    s = c.sec(201)[1]
    g = groups(s)
    for t in (T_AUX, T_GROUP):
        if t not in g:
            raise ValueError('section 201 has no %s group' % ('aux' if t == T_AUX else 'group'))
    rights = {u16(r, 4): r for r in g.get(T_RIGHT, [0, 0, 0, []])[3]}
    master = 0x0600 | c.head[HDR_MASTER]
    out = {}
    for t, kind in ((T_AUX, 'aux'), (T_GROUP, 'grp')):
        lst = []
        for r in g[t][3]:
            cid, w = u16(r, 4), r[41]
            rid = u16(r, 54) if w == 2 else None
            if w == 2 and rid not in rights:
                raise ValueError('stereo bus %04x has no right side record' % cid)
            lst.append(Bus(kind, cid, w, rec_name(r), rid, r, rights.get(rid), master=(cid == master)))
        out[kind] = lst
    return out, g


# ---------------------------------------------------------------------------- describe
def describe(data):
    """Bus layout of a session: counts, surface lists (internal index, width, name) and the header counts."""
    c = Container(data)
    b, g = bus_lists(c)
    h = c.head
    return {
        'model': bytes(h[11:15]).decode('latin1').strip(), 'build': u16(h, 0x22),
        'aux_mono': sum(1 for x in b['aux'] if x.width == 1), 'aux_stereo': sum(1 for x in b['aux'] if x.width == 2),
        'grp_mono': sum(1 for x in b['grp'] if x.width == 1), 'grp_stereo': sum(1 for x in b['grp'] if x.width == 2),
        'header': {'aux': [u16(h, HDR_AUX), u16(h, HDR_AUX + 2)], 'grp': [u16(h, HDR_GRP), u16(h, HDR_GRP + 2),
                   u16(h, HDR_GRP + 4)], 'master_group': h[HDR_MASTER], 'matrix_out': h[HDR_MTX_OUT],
                   'matrix_in': h[HDR_MTX_IN], 'cgs': h[HDR_CG]},
        'matrix': len(g.get(T_MTX_OUT, [0, 0, 0, []])[3]), 'cgs': len(g.get(T_CG, [0, 0, 0, []])[3]),
        'aux': [(x.id & 0xff, x.width, x.name) for x in b['aux']],
        'grp': [(x.id & 0xff, x.width, x.name) for x in b['grp']],
        'master': next((x.name for x in b['grp'] if x.master), None),
    }


# ---------------------------------------------------------------------------- planning
def _plan(old, kind, n_mono, n_stereo, new_id, new_rid):
    """New surface list for one bus kind. Keeps the first n of each width (the master always), adds the rest.
    new_id() / new_rid() hand out internal ids for added buses and their right sides."""
    monos = [x for x in old if x.width == 1]
    sts = [x for x in old if x.width == 2]
    keep_m = monos[:n_mono]
    master = [x for x in sts if x.master]
    others = [x for x in sts if not x.master]
    keep_s = set(map(id, master + others[:max(0, n_stereo - len(master))]))
    keep_s = [x for x in sts if id(x) in keep_s]
    new_m = [Bus(kind, new_id(), 1, '', new=True) for _ in range(n_mono - len(keep_m))]
    new_s = []
    for _ in range(n_stereo - len(keep_s)):
        cid = new_id()
        new_s.append(Bus(kind, cid, 2, '', rid=new_rid(), new=True))
    mono_first = [x.width for x in old] == sorted(x.width for x in old)
    if mono_first:
        lst = keep_m + new_m + keep_s + new_s
    else:   # custom order: keep it, new mono after the last kept mono, new stereo at the end
        kept = [x for x in old if any(x is y for y in keep_m + keep_s)]
        last_m = max((i for i, x in enumerate(kept) if x.width == 1), default=-1)
        lst = kept[:last_m + 1] + new_m + kept[last_m + 1:] + new_s
    prefix = 'Aux' if kind == 'aux' else 'Grp'
    for n, x in enumerate(lst, 1):
        if x.new or DEFAULT_NAME.match(x.name):
            x.name = '%s %d' % (prefix, n)
    removed = [x for x in old if not any(x is y for y in lst)]
    return lst, removed


# ---------------------------------------------------------------------------- per-bus slot runs
def _reband(slots, module, old, new):
    """slots: list of 8-byte slots of one record. Rebuild the per-bus runs for bands old -> new (surface order)."""
    order = []
    by_param = {}
    for k, s in enumerate(slots):
        if s[0] not in by_param:
            order.append(s[0])
        by_param.setdefault(s[0], []).append((k, s[2]))
    per = [p for p in order if [b for _, b in by_param[p]] == list(old) and (module, p) not in FIXED]
    if not per or list(old) == list(new):
        return slots
    perset = set(per)
    fixed = [s for s in slots if s[0] not in perset]
    first_per = min(k for p in per for k, _ in by_param[p])
    if any(k > first_per for k, s in enumerate(slots) if s[0] not in perset):
        raise ValueError('module %02x: fixed slots after the per-bus run' % module)
    body = [s for s in slots if s[0] in perset]
    band_major = [(s[2], s[0]) for s in body] == [(b, p) for b in old for p in per]
    param_major = [(s[2], s[0]) for s in body] == [(b, p) for p in per for b in old]
    if not (band_major or param_major):
        raise ValueError('module %02x: per-bus slots in an unknown order' % module)
    if band_major and param_major:          # one bus or one param: both orders read the same
        band_major = module in BAND_MAJOR
    have = {(s[0], s[2]): s for s in body}
    dflt = {p: Counter(bytes(have[(p, b)][3:8]) for b in old).most_common(1)[0][0] for p in per}
    mk = lambda p, b: have[(p, b)] if (p, b) in have else bytes([p, module, b]) + dflt[p]
    pairs = [(p, b) for b in new for p in per] if band_major else [(p, b) for p in per for b in new]
    return fixed + [mk(p, b) for p, b in pairs]


def _rebuild_object(o, rules):
    """Rebuild object o with per-bus runs changed. rules: {module: (old bands, new bands)}."""
    dl = u16(o, 2)
    head_end = 4 + dl + 4
    recs = obj_records(o)
    out = bytearray(o[:head_end])
    end = head_end
    for p, typ, cnt in recs:
        s0 = p + 0x3e
        rend = s0 + 8 * cnt + 12
        if typ in rules:
            old, new = rules[typ]
            slots = [bytes(o[s0 + 8 * k:s0 + 8 * k + 8]) for k in range(cnt)]
            ns = _reband(slots, typ, old, new)
            if ns is not slots:
                r = bytearray(o[p:s0]) + b''.join(ns) + o[s0 + 8 * cnt:rend]
                struct.pack_into('<H', r, 0x30, len(ns))
                out += r
                end = rend
                continue
        out += o[p:rend]
        end = rend
    out += o[end:]
    return out


def _obj_name(o, name):
    f = sstr31(name)
    t = len(o) - 41
    o[t + 4:t + 36] = f
    for p, _, _ in obj_records(o):
        o[p + 8:p + 40] = f


def _obj_name_get(o):
    t = len(o) - 41
    return bytes(o[t + 5:t + 5 + min(o[t + 4], 31)]).decode('latin1')


def _set_raw(o, module, param, band, raw):
    for p, typ, cnt in obj_records(o):
        if typ != module:
            continue
        for k in range(cnt):
            q = p + 0x3e + 8 * k
            if o[q] == param and o[q + 2] == band:
                o[q + 4:q + 8] = raw
                return True
    return False


def _clear_refs(o, dead):
    """Zero every reference slot that points at a removed channel id. Returns the number cleared."""
    t = obj_id(o) >> 8
    n = 0
    for p, typ, cnt in obj_records(o):
        for k in range(cnt):
            q = p + 0x3e + 8 * k
            prm = o[q]
            if not any((ot is None or ot == t) and m == typ and pr == prm for ot, m, pr in REF_SLOTS):
                continue
            v = o[q + 4:q + 8]
            if v[0] == 0 and v[1] == 0 and (v[2] | (v[3] << 8)) in dead:
                o[q + 4:q + 8] = b'\0\0\0\0'
                n += 1
    return n


def _mask_obj(o):
    o = bytearray(o)
    for p, _, _ in obj_records(o):
        o[p + 8:p + 48] = b'\0' * 40
    t = len(o) - 41
    o[t + 2:t + 36] = b'\0' * 34
    return bytes(o)


STEREO_SLOTS = {(0x08, 0xe8, 0): (1.0, 2.0, 1.0), (0x08, 0xe8, 1): (1.0, 2.0, 1.0), (0x0e, 0xe8, 0): (1.0, 2.0, 1.0),
                (0x1d, 0x3f, 0): (0.0, 1.0, 1.0)}   # (mono, stereo left, right side); 1d only on Quantum


def _convert(o, width):
    """Turn a bus object into a mono (1), stereo left (2) or right-side ('R') object: the same 4 slots that
    separate them in every default session, the trailer width and the partner key."""
    o = bytearray(o)
    col = {1: 0, 2: 1, 'R': 2}[width]
    for (m, prm, band), vals in STEREO_SLOTS.items():
        for p, typ, cnt in obj_records(o):
            if typ != m:
                continue
            for k in range(cnt):
                q = p + 0x3e + 8 * k
                if o[q] == prm and o[q + 2] == band:
                    struct.pack_into('<f', o, q + 4, vals[col])
    o[-1] = 2 if width == 2 else 1
    _set_raw(o, *KEY_ROUTE, b'\0\0\0\0')
    return o


def _pick_template(objs):
    """Most common object among candidates once ids, names, timestamps and partner keys are masked."""
    if not objs:
        return None
    def m(o):
        o = bytearray(o)
        _set_raw(o, *KEY_ROUTE, b'\0\0\0\0')
        return _mask_obj(o)
    best = Counter(m(o) for o in objs).most_common(1)[0][0]
    return next(o for o in objs if m(o) == best)


# ---------------------------------------------------------------------------- banks
def _bank_kind(b):
    kinds = {b[0x24 + 2 * j] for j in range(12)} - {0}
    if kinds == {T_AUX}:
        return 'aux'
    if kinds == {T_GROUP}:
        return 'grp'
    return None


def _make_banks(tmpl, buses, prefix, kind_type):
    out = []
    filled = next(j for j in range(12) if tmpl[0x24 + 2 * j] == kind_type)
    lock = bytes(tmpl[0x6b + 16 * filled:0x6b + 16 * (filled + 1)])
    view = tmpl[0x12b + filled]   # +0x12b: which of the slot's locked encoder rows (+0x6b) are locked; the SD / M view is +0x15d
    for k in range(0, len(buses), 12):
        chunk = buses[k:k + 12]
        b = bytearray(tmpl)
        a, z = k + 1, k + len(chunk)
        nm = '%s %d-%d' % (prefix, a, z) if z > a else ('%s %d' % (prefix, a) if a > 1 else prefix)
        b[4:20] = (bytes([len(nm)]) + nm.encode('latin1') + b'\0' * 15)[:16]
        for j in range(12):
            if j < len(chunk):
                b[0x23 + 2 * j] = chunk[j].id & 0xff
                b[0x24 + 2 * j] = kind_type
                b[0x6b + 16 * j:0x6b + 16 * (j + 1)] = lock
                b[0x12b + j] = view
            else:
                b[0x23 + 2 * j] = 0
                b[0x24 + 2 * j] = 0
                b[0x6b + 16 * j:0x6b + 16 * (j + 1)] = b'\0' * 16
                b[0x12b + j] = 0
        out.append(b)
    return out


def _tables(t212):
    return [[u16(t212, 2 + 99 * u + 2 * j) for j in range(42)] for u in range(8)]


def _rebuild_banks(c, new_aux, new_grp):
    """Rebuild every run of pure aux / pure group banks. Returns old key -> [new keys] for the 212 remap."""
    s243 = c.sec(243)[1]
    bl, btail = split_banks(s243)
    out, origin = [], []          # origin: old key for kept banks, ('new', old key of the run) for added ones
    k = 0
    while k < len(bl):
        kind = _bank_kind(bl[k])
        if kind is None:
            out.append(bl[k])
            origin.append(k)
            k += 1
            continue
        run = [k]
        while k + len(run) < len(bl) and _bank_kind(bl[k + len(run)]) == kind and \
                bl[k + len(run)][0x23] != bl[k][0x23]:      # a bank that starts over is a second copy
            run.append(k + len(run))
        lst = new_aux if kind == 'aux' else new_grp
        made = _make_banks(bl[k], lst, 'Aux' if kind == 'aux' else 'Grp', T_AUX if kind == 'aux' else T_GROUP)
        for i, b in enumerate(made):
            if i < len(run):
                b[0x3b:0x6b] = bl[run[i]][0x3b:0x6b]        # keep the old heap words (save noise anyway)
                b[0x1a:0x20] = bl[run[i]][0x1a:0x20]
                origin.append(run[i])
            else:
                origin.append(('new', run[-1]))
            out.append(b)
        k += len(run)
    # strips of other banks that show a removed bus become empty
    aux_set, grp_set = {x.id & 0xff for x in new_aux}, {x.id & 0xff for x in new_grp}
    for b, org in zip(out, origin):
        if isinstance(org, tuple) or _bank_kind(bl[org]) is not None:
            continue
        for j in range(12):
            typ, idx = b[0x24 + 2 * j], b[0x23 + 2 * j]
            if (typ == T_AUX and idx not in aux_set) or (typ == T_GROUP and idx not in grp_set):
                b[0x23 + 2 * j] = b[0x24 + 2 * j] = 0
                b[0x6b + 16 * j:0x6b + 16 * (j + 1)] = b'\0' * 16
                b[0x12b + j] = 0
    # locked rows (4 per strip: param, module, band, 0) that show a send to a removed bus point at the first buses
    # that are left, the way the editor re-points them (rows 1-2 of an input strip show Aux 1 and Aux 2 sends)
    for b in out:
        for j in range(12):
            for mods, bands in ((PER_AUX, [x.id & 0xff for x in new_aux]), (PER_GRP, [x.id & 0xff for x in new_grp])):
                k = 0
                for r in range(4):
                    q = 0x6b + 16 * j + 4 * r
                    if b[q + 1] in mods and (b[q] or b[q + 1]):
                        if b[q + 2] not in bands:
                            b[q + 2] = bands[k] if k < len(bands) else 0
                        k += 1
    # keys and overview slots: kept banks move by (banks added before them - banks removed before them),
    # an added bank takes the slot after the bank before it
    old_slots = [bank_slot(b) for b in bl]
    kept = {o for o in origin if not isinstance(o, tuple)}
    added, prev = 0, None
    for nk, (b, org) in enumerate(zip(out, origin)):
        struct.pack_into('<H', b, 2, nk)
        if isinstance(org, tuple):
            added += 1
            sl = prev + 1 if prev is not None else None
            if sl is None or sl < 0 or sl // 6 > 250:
                struct.pack_into('<I', b, 0x1a, 0xffffffff)
                sl = None
            else:
                set_bank_slot(b, sl)
        else:
            sl = old_slots[org]
            delta = added - sum(1 for k in range(org) if k not in kept)
            if sl is not None and delta and 0 <= sl + delta and (sl + delta) // 6 <= 250:
                sl += delta
                set_bank_slot(b, sl)
        prev = sl
    c.sec(243)[1] = bytearray(s243[:2]) + struct.pack('<I', len(out)) + b''.join(out) + btail
    return origin, len(bl)


def _remap_212(t212, origin, n_old):
    """Re-deal the banks from the first changed key onward over the positions the old banks from that key used
    (in key order), the way Rebuild Banks did in the captures. Extra banks continue the pattern; banks whose
    run was not placed stay unplaced."""
    t = bytearray(t212)
    if origin == list(range(n_old)):
        return t
    tabs = _tables(t)
    pos = {}
    for u, tab in enumerate(tabs):
        for j, v in enumerate(tab):
            if v != 0xffff:
                pos.setdefault(v, (u, j))
    first = next((nk for nk, o in enumerate(origin) if o != nk), len(origin))
    src = lambda o: o[1] if isinstance(o, tuple) else o
    slots = [pos[k] for k in range(first, n_old) if k in pos]
    place = [nk for nk in range(first, len(origin)) if src(origin[nk]) in pos]
    for u, j in slots:
        tabs[u][j] = 0xffff
    used = {(u, j) for u, tab in enumerate(tabs) for j, v in enumerate(tab) if v != 0xffff}
    # a fader-section table is paged in layers of 6; each table uses the first few positions of every page
    # (Q338 master section: 4, i.e. 0-3, 6-9, 12; Q5 inputs: 5). Extra banks continue the pattern.
    top = {u: max([3] + [j % 6 for j, v in enumerate(tab) if v != 0xffff]) for u, tab in enumerate(_tables(t))}
    m = len({u for u, _ in slots}) or 1
    while slots and len(slots) < len(place):
        u, j = slots[-m] if len(slots) >= m else slots[-1]
        j += 1
        while j < 42 and ((u, j) in used or (u, j) in slots or j % 6 > top[u]):
            j += 1
        if j >= 42:
            break
        slots.append((u, j))
    for nk, (u, j) in zip(place, slots):
        tabs[u][j] = nk
    for u, tab in enumerate(tabs):
        for j, v in enumerate(tab):
            struct.pack_into('<H', t, 2 + 99 * u + 2 * j, v)
    return t


# ---------------------------------------------------------------------------- engine channels
def _engine_plan(c, g, new_aux, new_grp):
    """{record id: EngineChannel} for buses, plus a delta for inputs/TB In on SD models. None on V1455 files."""
    recs = g[T_AUX][3] + g[T_GROUP][3]
    if not recs or not has_engine(recs[0]):
        return None, 0, None
    family = bytes(c.head[11:15]).decode('latin1').strip()
    quantum = family in QUANTUM_FAMILIES
    eng = {}
    e = 0
    for x in new_grp:
        eng[x.id] = e
        if x.width == 2:
            eng[x.rid] = e + 1
        e += x.width
    gw = e
    a_w = sum(x.width for x in new_aux)
    if quantum:
        a0 = e
        solo_shift = (gw + a_w) - _old_bus_width(g)
    else:
        mtx = [struct.unpack_from('<h', r, 84)[0] for r in g.get(T_MTX_OUT, [0, 0, 0, []])[3]]
        old_aux = [struct.unpack_from('<h', r, 84)[0] for r in g[T_AUX][3]]
        old_r = [struct.unpack_from('<h', r, 84)[0] for r in g.get(T_RIGHT, [0, 0, 0, []])[3]
                 if u16(r, 54) >> 8 == T_AUX]
        top = min(mtx) if mtx else max(old_aux + old_r) + 1
        a0 = top - a_w
        solo_shift = None
    if not quantum:
        ins = g.get(T_INPUT, [0, 0, 0, []])[3]
        old_gw = sum(r[41] for r in g[T_GROUP][3])
        tops = [struct.unpack_from('<h', r, 84)[0] + r[41] for r in ins]
        tb = g.get(T_TB, [0, 0, 0, []])[3]
        if tb and _tb_in_input_region(g):
            tops.append(struct.unpack_from('<h', tb[0], 84)[0] + 1)
        need = max(tops + [old_gw]) - old_gw + gw
        if need > a0 or a0 < 0:
            raise ValueError('the inputs and groups need %d engine channels below the auxes; this layout leaves %d'
                             % (need, max(a0, 0)))
    for x in new_aux:
        eng[x.id] = a0
        if x.width == 2:
            eng[x.rid] = a0 + 1
        a0 += x.width
    old_gw = sum(r[41] for r in g[T_GROUP][3])
    return eng, (0 if quantum else gw - old_gw), solo_shift


def _old_bus_width(g):
    return sum(r[41] for r in g[T_AUX][3]) + sum(r[41] for r in g[T_GROUP][3])


SD_SOLO_TOP = 126   # SD: solo 2 sits at min(8, 126 - total aux + group width); 138 of 138 SD files, and the
                    # V2242 SD5/SD7 editors moved it to 2/3/4 for widths 124/123/122 (decode notes, not published)


def _sd_solo(g, width):
    """SD models: EngineChannel of the 2 solo buses for a total aux + group width, or None when the file does not
    follow the rule (then they are left as they are)."""
    so = g.get(T_SOLO, [0, 0, 0, []])[3]
    if len(so) != 2 or not all(has_engine(r) for r in so):
        return None
    cur = [struct.unpack_from('<h', r, 84)[0] for r in so]
    if cur != [0, min(8, SD_SOLO_TOP - _old_bus_width(g))]:
        return None
    return [0, min(8, SD_SOLO_TOP - width)]


# ---------------------------------------------------------------------------- the operation
def snapshot_count(c):
    """Snapshot object lists in section 210 ('d3 00' u32 'd5 00 01 00'). The default sessions have none."""
    try:
        s = bytes(c.sec(210)[1])
    except StopIteration:
        return 0
    return len(re.findall(rb'\xd3\x00....\xd5\x00\x01\x00', s, re.S))


def restructure(data, aux_mono, aux_stereo, grp_mono, grp_stereo, matrix=None, cgs=None, check_limit=True,
                snapshots='refuse', report=None, console=None):
    """Return a copy of the session with the given bus layout. grp_stereo counts the master (at least 1).
    A session with snapshots is refused (snapshots='refuse'): its snapshot copies of every channel would keep the
    old send layout. snapshots='keep' leaves them as they are (not editor-tested). Pass a dict as `report` to get
    the added and removed buses (surface lists before/after) and the number of cleared references. `console` (a
    consoles.py key such as 'sd11') picks the bus budget where a file family covers two consoles."""
    c = Container(data)
    n_snap = snapshot_count(c)
    if n_snap and snapshots != 'keep':
        raise ValueError('this session has %d snapshots; clear them (Session Structure > clear snapshots) or '
                         'restructure it in the editor' % n_snap)
    family = bytes(c.head[11:15]).decode('latin1').strip()
    b, g = bus_lists(c)
    if any(n < 0 for n in (aux_mono, aux_stereo, grp_mono, grp_stereo)):
        raise ValueError('bus counts must be 0 or more')
    if aux_mono + aux_stereo < 1 or not b['aux']:
        raise ValueError('a session needs at least one aux (the send layout is copied from the existing ones)')
    has_master = any(x.master for x in b['grp'])
    if has_master and grp_stereo < 1:
        grp_stereo = 1           # the master stereo group cannot be removed (the editor's minimum is 1)
    if u16(c.head, HDR_GRP + 4):
        raise ValueError('LCR groups are not supported')
    for want, typ, name in ((matrix, T_MTX_OUT, 'matrix outputs'), (cgs, T_CG, 'control groups')):
        have = len(g.get(typ, [0, 0, 0, []])[3])
        if want is not None and want != have:
            raise ValueError('changing %s is not supported; this session has %d' % (name, have))
    limit = bus_limit(c, console)
    width = aux_mono + 2 * aux_stereo + grp_mono + 2 * grp_stereo
    if check_limit and limit is not None and width > limit:
        raise ValueError('the layout needs %d busses (stereo counts 2); this console has %d' % (width, limit))

    s211 = c.sec(211)[1]
    objs, tail = objects(s211)
    by_id = {obj_id(o): o for o in objs}
    def allocator(typ, used, start=0):
        """Lowest internal index not used by any old channel of this type (kept or removed), as the editor does.
        Right sides start at 8: 0x0700 is the master's right side and 0x0701-0x0707 are never used."""
        used = set(used)
        def nxt():
            k = start
            while k in used:
                k += 1
            if k > 0xff:
                raise ValueError('ran out of internal bus indices')
            used.add(k)
            return (typ << 8) | k
        return nxt
    olds = [x for x in b['aux'] + b['grp']]
    used_r = {x.rid & 0xff for x in olds if x.rid is not None} | {i & 0xff for i in by_id if i >> 8 == T_RIGHT}
    new_r = allocator(T_RIGHT, used_r, 8)
    new_aux, rm_aux = _plan(b['aux'], 'aux', aux_mono, aux_stereo,
                            allocator(T_AUX, {i & 0xff for i in by_id if i >> 8 == T_AUX}), new_r)
    new_grp, rm_grp = _plan(b['grp'], 'grp', grp_mono, grp_stereo,
                            allocator(T_GROUP, {i & 0xff for i in by_id if i >> 8 == T_GROUP}), new_r)
    old_aux_b = [x.id & 0xff for x in b['aux']]
    old_grp_b = [x.id & 0xff for x in b['grp']]
    new_aux_b = [x.id & 0xff for x in new_aux]
    new_grp_b = [x.id & 0xff for x in new_grp]
    dead = {x.id for x in rm_aux + rm_grp} | {x.rid for x in rm_aux + rm_grp if x.rid is not None}

    # ---- 201 records
    eng, in_shift, solo_shift = _engine_plan(c, g, new_aux, new_grp)
    tmpl_rec = {}
    for kind, lst in (('aux', b['aux']), ('grp', b['grp'])):
        for x in lst:
            if x.master:
                continue
            tmpl_rec.setdefault((kind, x.width), x.rec)
            if x.width == 2:
                tmpl_rec.setdefault((kind, 'R'), x.rrec)

    def rec_for(x, n, right=False):
        key = (x.kind, 'R') if right else (x.kind, x.width)
        src = (x.rrec if right else x.rec) if not x.new else tmpl_rec.get(key)
        if src is None:
            src = _fallback_rec(c, b, x.kind, 'R' if right else x.width)
        r = bytearray(src)
        cid = x.rid if right else x.id
        struct.pack_into('<HH', r, 4, cid, n)
        if x.new or x.name != rec_name(x.rec):
            r[8:40] = sstr31(x.name + (' R' if right else ''))
        r[41] = 1 if right else x.width
        struct.pack_into('<H', r, 54, x.id if right else (x.rid if x.width == 2 else 0))
        if eng is not None and has_engine(r):
            struct.pack_into('<h', r, 84, eng[cid])
        return r

    new_recs = {T_AUX: [rec_for(x, n) for n, x in enumerate(new_aux, 1)],
                T_GROUP: [rec_for(x, n) for n, x in enumerate(new_grp, 1)]}
    rights = [x for x in new_aux if x.width == 2] + [x for x in new_grp if x.width == 2]
    new_recs[T_RIGHT] = [rec_for(x, n, right=True) for n, x in enumerate(rights, 1)]
    s201 = bytearray(c.sec(201)[1])
    if T_RIGHT not in g:
        raise ValueError('section 201 has no Busses group')
    for typ in sorted(new_recs, key=lambda t: -g[t][0]):           # back to front keeps offsets valid
        q, p0, p1, _ = g[typ]
        s201[p0:p1] = b''.join(new_recs[typ])
        struct.pack_into('<I', s201, q + 0x70, len(new_recs[typ]))
    if in_shift or solo_shift:
        g2 = groups(s201)
        for typ, shift in ((T_INPUT, in_shift), (T_TB, in_shift), (T_SOLO, solo_shift)):
            if not shift or typ not in g2:
                continue
            if typ == T_TB and not _tb_in_input_region(g):
                continue
            p = g2[typ][1]
            for r in g2[typ][3]:
                if has_engine(r):
                    struct.pack_into('<h', s201, p + 84, struct.unpack_from('<h', r, 84)[0] + shift)
                p += len(r)
    if eng is not None and family not in QUANTUM_FAMILIES:
        want = _sd_solo(g, sum(x.width for x in new_aux + new_grp))
        g2 = groups(s201)
        if want and T_SOLO in g2:
            p = g2[T_SOLO][1]
            for r, e in zip(g2[T_SOLO][3], want):
                struct.pack_into('<h', s201, p + 84, e)
                p += len(r)
    c.sec(201)[1] = s201

    # ---- 211 objects
    rules_aux = {m: (old_aux_b, new_aux_b) for m in PER_AUX}
    rules_grp = {m: (old_grp_b, new_grp_b) for m in PER_GRP}
    rules = {**rules_aux, **rules_grp}
    kept_names = {}             # kept buses whose default name follows a new surface number
    for x in new_aux + new_grp:
        if not x.new and x.name != rec_name(x.rec):
            kept_names[x.id] = x.name
            if x.width == 2:
                kept_names[x.rid] = x.name + ' R'
    tmpl_obj = {}
    for kind, lst in (('aux', b['aux']), ('grp', b['grp'])):
        for w in (1, 2, 'R'):
            if w == 'R':
                cands = [by_id[x.rid] for x in lst if x.width == 2 and not x.master and x.rid in by_id]
            else:
                cands = [by_id[x.id] for x in lst if x.width == w and not x.master and x.id in by_id]
            if cands:
                tmpl_obj[(kind, w)] = (_pick_template(cands), old_aux_b, old_grp_b)

    out = []
    cleared = 0
    for o in objs:
        oid = obj_id(o)
        if oid in dead:
            continue
        o = _rebuild_object(o, rules)
        if oid in kept_names and _obj_name_get(o) != kept_names[oid]:
            _obj_name(o, kept_names[oid])
        cleared += _clear_refs(o, dead)
        out.append(o)
    for x in new_aux + new_grp:
        if not x.new:
            continue
        for right in ((False, True) if x.width == 2 else (False,)):
            key = (x.kind, 'R') if right else (x.kind, x.width)
            t, ab, gb = tmpl_obj.get(key, (None, None, None))
            if t is None:
                t, ab, gb = _fallback_obj(c, b, by_id, x.kind, 'R' if right else x.width, old_aux_b, old_grp_b)
            o = _rebuild_object(bytearray(t), {**{m: (ab, new_aux_b) for m in PER_AUX},
                                                 **{m: (gb, new_grp_b) for m in PER_GRP}})
            cid = x.rid if right else x.id
            struct.pack_into('<H', o, len(o) - 39, cid)
            _obj_name(o, x.name + (' R' if right else ''))
            if x.width == 2:
                _set_raw(o, *KEY_ROUTE, b'\0\0' + struct.pack('<H', x.id if right else x.rid))
            _set_raw(o, 0x0e, 0xfe, 0, b'\0\0\0\0')           # no output patch on a new bus
            out.append(o)
    out.sort(key=obj_id)
    head = bytearray(s211[:6])
    struct.pack_into('<I', head, 2, len(out))

    # ---- 243 banks, 212 placement (and its copy in the 211 tail)
    origin, n_old = _rebuild_banks(c, new_aux, new_grp)
    t212 = c.sec(212)[1]
    t212n = _remap_212(t212, origin, n_old)
    i = bytes(tail).find(bytes(t212))
    if i < 0:
        raise ValueError('section 211 tail holds no copy of section 212')
    tail[i:i + len(t212)] = t212n
    c.sec(212)[1] = t212n
    c.sec(211)[1] = head + b''.join(out) + tail

    # ---- header counts
    for off, v in ((HDR_AUX, aux_mono), (HDR_AUX + 2, aux_stereo), (HDR_GRP, grp_mono), (HDR_GRP + 2, grp_stereo)):
        struct.pack_into('<H', c.head, off, v)
    if report is not None:
        report.update({'removed': [(x.kind, x.name) for x in rm_aux + rm_grp],
                       'added': [(x.kind, x.name) for x in new_aux + new_grp if x.new],
                       'renamed': len(kept_names), 'cleared_refs': cleared,
                       'aux': [(x.id & 0xff, x.width, x.name) for x in new_aux],
                       'grp': [(x.id & 0xff, x.width, x.name) for x in new_grp]})
    return c.build()


def _tb_in_input_region(g):
    """SD models: TB In sits above the groups with the inputs (right after them in every default session, a few
    channels later or inside the block in some real sessions), so it moves when the groups change width."""
    tb = g.get(T_TB, [0, 0, 0, []])[3]
    if not tb or not has_engine(tb[0]):
        return False
    return struct.unpack_from('<h', tb[0], 84)[0] >= sum(r[41] for r in g[T_GROUP][3])


def _tb_follows(g):
    ins = g.get(T_INPUT, [0, 0, 0, []])[3]
    tb = g.get(T_TB, [0, 0, 0, []])[3]
    if not ins or not tb or not has_engine(ins[0]):
        return False
    first = struct.unpack_from('<h', ins[0], 84)[0]
    return struct.unpack_from('<h', tb[0], 84)[0] == first + sum(r[41] for r in ins)


# ---------------------------------------------------------------------------- fallbacks (pristine defaults)
FAMILY_KEY = {'Q1': 'q112', 'Q2': 'q225', 'Q3': 'q338', 'Q5': 'q5', 'SDQ': 'q7', 'Q8': 'q852', 'SD5': 'sd5',
              'SD7': 'sd7', 'SD8': 'sd8', 'SD9': 'sd9', 'SDC': 'sd12'}
DEFAULTS = os.environ.get('SM_BASELINES') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'baselines')


def _defaults_container(c):
    key = FAMILY_KEY.get(bytes(c.head[11:15]).decode('latin1').strip())
    path = os.path.join(DEFAULTS, '%s_v%d.ses' % (key, u16(c.head, 0x22)))
    if key is None or not os.path.exists(path):
        raise ValueError('no template for a new bus of this kind and no default session %s' % path)
    return Container(open(path, 'rb').read())


def _fallback_rec(c, b, kind, width):
    """Record template for a kind of bus the session does not have: the default session of the same console and
    build, else the master's record (with GroupAuxSendEnabled set, as on every other group)."""
    w = 2 if width == 'R' else width
    try:
        d = _defaults_container(c)
        db, _ = bus_lists(d)
        for x in db[kind]:
            if not x.master and x.width == w:
                return x.rrec if width == 'R' else x.rec
    except (ValueError, OSError):
        pass
    for master_ok in (False, True):
        for x in b[kind]:
            if x.master and not master_ok:
                continue
            r = bytearray(x.rrec if width == 'R' and x.width == 2 else x.rec)
            if kind == 'grp' and len(r) >= 125:
                r[124] = 1
            return r
    raise ValueError('no template for a new %s bus' % kind)


def _fallback_obj(c, b, by_id, kind, width, old_aux_b, old_grp_b):
    """Object template for a kind of bus the session does not have: the default session of the same console and
    build, else another width of the same kind in this session converted with _convert (the master last).
    Returns (object, its aux bands, its group bands) so the per-bus runs can be rebuilt for this session."""
    w = 2 if width == 'R' else width
    try:
        d = _defaults_container(c)
        db, _ = bus_lists(d)
        objs, _ = objects(d.sec(211)[1])
        dby = {obj_id(o): o for o in objs}
        cands = [dby[x.rid if width == 'R' else x.id] for x in db[kind] if not x.master and x.width == w]
        if cands:
            return _pick_template(cands), [x.id & 0xff for x in db['aux']], [x.id & 0xff for x in db['grp']]
    except (ValueError, OSError):
        pass
    for master_ok in (False, True):
        for x in b[kind]:
            if x.master and not master_ok:
                continue
            for src in ([x.id] + ([x.rid] if x.width == 2 else [])):
                if src in by_id:
                    o = _convert(by_id[src], width)
                    if x.master:
                        _set_raw(o, 0x0e, 0xfe, 0, b'\0\0\0\0')
                    return o, old_aux_b, old_grp_b
    raise ValueError('no template for a new %s bus' % kind)


if __name__ == '__main__':
    import json
    import sys
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: python3 -m sessionmaker.buses file.ses  (describe)  |  src.ses dst.ses aux_mono aux_stereo grp_mono grp_stereo  (restructure)')
        sys.exit(0 if len(sys.argv) > 1 else 2)
    if len(sys.argv) == 2:
        print(json.dumps(describe(open(sys.argv[1], 'rb').read()), indent=1))
    elif len(sys.argv) == 7:
        src, dst, am, ast, gm, gs = sys.argv[1:7]
        out = restructure(open(src, 'rb').read(), int(am), int(ast), int(gm), int(gs))
        open(dst, 'wb').write(out)
        d = describe(out)
        print('%s: aux %d+%d, groups %d+%d, %d bytes' % (dst, d['aux_mono'], d['aux_stereo'], d['grp_mono'],
                                                        d['grp_stereo'], len(out)))
    else:
        print('usage: python3 -m sessionmaker.buses <in.ses> [<out.ses> aux_mono aux_stereo grp_mono grp_stereo]')
