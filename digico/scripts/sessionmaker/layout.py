#!/usr/bin/env python3
"""layout.py - rewrite a DiGiCo .ses input-channel layout (count, order, mono/stereo) by bytes.

Its relayout was load-tested in the real
Quantum 225 V2242 editor: 13 candidates, including 64 -> 40 inputs renamed with 8 stereo, loaded and re-saved
masked-identical. Works on every build from V1455 to V2242 (the channel record length is read from the file).

What a layout change touches (verified on editor-saved baselines and 39 real sessions):
  header 0x26        u16 number of input channels
  section 0          session notes: 00 00 | u16 length | latin-1 text (Files > Session Notes)
  section 201        input group: 'ca 00 6c 00 01 0e "Input Channels"' + u32 count @+0x70 + count cb records
                     (one per channel, in SURFACE order): cb 00 hl 00 | id u16 (0x0100|idx) | num u16 (surface
                     number) | name[32] | +40 00 | +41 width (1/2) | ... | +84 i16 EngineChannel | +86 i16 Tidal
                     (Mustard) channel. hl = 0x79 in V2242 (and V2232 Q112/Q852), 0x78 in Q112/Q852 V1926-V2126,
                     0x58 in V1619-V2025, 0x50 in V1455 (no +84/+86).
                     EngineChannel = first + sum of the widths of the channels before it (surface order).
                     The inputs must fit the engine pool (engine_room); the Talkback Input record (type 0c)
                     moves to last input + 1 where it sat there in the baseline (SD models, Q112, Q852)
  section 211        'd3 00' + u32 object count, then objects sorted by id:
                     d5 00 01 00 01 | u32 nrec | nrec module records | 27 00 id name[32] ff ff ff ff | width
                     a stereo input also has (08,e8,0)=(08,e8,1)=(0e,e8,0)=2.0 and, on Quantum, (1d,3f,0)=1.0
                     after the objects: a tail that holds a copy of section 212 (bank placement)
  section 243        'f3 00' + u32 bank count + banks of 0x169 bytes (strips name inputs by idx)
  section 212        bank placement: 8 fader-section tables of 42 u16 bank numbers (+15 B each), copied in the
                     211 tail. A table position is a layer: 0-5 input layers, 6-11 output layers (every default
                     session). Input banks are dealt round-robin over the sections. The two copies must stay equal.
  section table      int32 offsets[40] @0x100 + ids u8[40] @0x1a0, last offset = file size
"""
import re
import struct
from collections import Counter

REC = b'\xda\x00\x3a\x00'
SEC_TABLE, SEC_IDS, NSEC = 0x100, 0x1a0, 40
BANK_SIZE = 0x169
NO_POS = 0xffffffff                       # OverviewPosition x of a bank that is not on the overview grid
GRID_W, GRID_H, GRID_COLS = 170, 250, 6   # overview grid: x = 1 + 170 * col, y = 2 + 250 * row
# (module, param, band): (mono value, stereo value). (1d,3f,0) exists only on Quantum (Mustard).
STEREO_SLOTS = {(0x08, 0xe8, 0): (1.0, 2.0), (0x08, 0xe8, 1): (1.0, 2.0), (0x0e, 0xe8, 0): (1.0, 2.0),
                (0x1d, 0x3f, 0): (0.0, 1.0)}
MAX_INPUT_IDS = 0x100                     # the id low byte is idx - 1, so 256 inputs at most


# ---------------------------------------------------------------------------- container
class Container:
    """The file as a header + an ordered list of [section id, bytearray]. build() rewrites the section table."""

    def __init__(self, data):
        d = bytes(data)
        self.head = bytearray(d[:SEC_TABLE])
        offs = struct.unpack_from('<%di' % NSEC, d, SEC_TABLE)
        ids = d[SEC_IDS:SEC_IDS + NSEC]
        self.gap = d[SEC_IDS + NSEC:offs[0]]          # bytes between id table and the first section
        n = next(i for i in range(1, NSEC) if offs[i] == len(d))
        self.sections = [[ids[i], bytearray(d[offs[i]:offs[i + 1]])] for i in range(n)]

    def sec(self, sid):
        return next(s for s in self.sections if s[0] == sid)

    def build(self):
        out = bytearray(self.head)
        offs, p = [], SEC_TABLE + 4 * NSEC + NSEC + len(self.gap)
        for _, b in self.sections:
            offs.append(p)
            p += len(b)
        offs.append(p)
        offs += [0] * (NSEC - len(offs))
        out += struct.pack('<%di' % NSEC, *offs)
        ids = [s[0] for s in self.sections] + [0] * (NSEC - len(self.sections))
        out += bytes(ids)
        out += self.gap
        for _, b in self.sections:
            out += b
        assert len(out) == p
        return bytes(out)


# ---------------------------------------------------------------------------- section 201
def input_group(s201):
    """(group header offset, first record, end of records, [record bytes]) of the Input Channels group."""
    m = re.search(rb'\xca\x00\x6c\x00\x01\x0eInput Channels', bytes(s201))
    if m is None:
        raise ValueError('no Input Channels group in section 201')
    q = m.start()
    cnt = struct.unpack_from('<I', s201, q + 0x70)[0]
    p, recs = q + 0x74, []
    for _ in range(cnt):
        if s201[p:p + 2] != b'\xcb\x00':
            raise ValueError('broken channel record at %#x in section 201' % p)
        ln = 4 + struct.unpack_from('<H', s201, p + 2)[0]
        recs.append(bytearray(s201[p:p + ln]))
        p += ln
    return q, q + 0x74, p, recs


def cb_has_engine(r):
    """V1619+ records carry EngineChannel (+84) and TidalChannel (+86); V1455 records stop before them."""
    return len(r) >= 88


# ---------------------------------------------------------------------------- engine channels
# cb +84 EngineChannel numbers the DSP paths. Measured on all 91 editor-saved files (39 real sessions,
# editor-made baselines, every default session and the editors' boot re-saves in:
#   SD models   one pool for the inputs and the mix buses. Groups (06) sit at the bottom, then the inputs, then the
#               Talkback Input (0c) at last input + 1. Aux (05) and Matrix (10) outputs sit at the top (SD9/SD11/
#               SD12 end at 191, SD5/SD7/SD8/SD10 at 255); 07 (right side of a stereo aux or group) sits inside
#               those ranges. No input ever shares an engine channel with 05/06/07/10 or 0c.
#   Quantum     the inputs have a pool of their own from 0 (the buses reuse 0..). TB In sits at 254 on Q2/Q3/Q5/Q7
#               and at last input + 1 on Q1/Q8. No engine number above 255 was seen.
# After a relayout the editor moves TB In to last input + 1 wherever it sat there before, and leaves 254 alone
# (boot re-saves: sd5 126->80, sd12 66->80, q112 48->59, q852 72->62; q225..q7 kept 254). relayout() does the same.
GROUP_HDR = b'\xca\x00\x6c\x00'
T_INPUT, T_TB = 0x01, 0x0c
BUS_TYPES = (0x05, 0x06, 0x07, 0x10)     # aux, group, right side of stereo aux/group, matrix output
QUANTUM_FAMILIES = {'Q1', 'Q2', 'Q3', 'Q5', 'Q8', 'SDQ'}
QUANTUM_POOL = 256                       # engine numbers 0..255 on a Quantum input pool
# Channel record header lengths. 0x78 is the Quantum 112 and 852 at V1926-V2126; before 2026-10-13 groups201 left it
# out, so engine_room() found no engine channels there and relayout() left TB In at the default's 72 (Q852) or 48
# (Q112), which the editors then rewrote to last input + 1 on load (decode notes, not published).
CB_HL = (0x50, 0x58, 0x78, 0x79)


def groups201(s201):
    """{record type: [offset of each cb record in s201]} for every well-formed group in section 201."""
    s, out = bytes(s201), {}
    for m in re.finditer(re.escape(GROUP_HDR), s):
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


def engine_map(s201):
    """{record type: [(EngineChannel, width)]} in record order, or None for V1455 records (no EngineChannel)."""
    g = groups201(s201)
    if not g.get(T_INPUT) or s201[g[T_INPUT][0] + 2] < 0x58:
        return None
    return {t: [(struct.unpack_from('<h', s201, p + 84)[0], s201[p + 41]) for p in offs] for t, offs in g.items()}


def _engines(pairs):
    return {e + k for e, w in pairs for k in range(w)}


def engine_room(data):
    """Where the inputs may sit in this baseline's engine pool. -> dict or None (no EngineChannel in the file).

    first      EngineChannel of surface channel 1
    limit      first engine channel the inputs (and a trailing TB In) must stay below
    tb         TB In's EngineChannel; tb_follows: it sits right after the inputs (and moves with them)
    room       engine channels the inputs may use: limit - first - (1 when TB In follows)
    shared     True on SD models (inputs share the pool with the buses)"""
    c = data if isinstance(data, Container) else Container(data)
    em = engine_map(c.sec(201)[1])
    if em is None:
        return None
    ins = em[T_INPUT]
    first = ins[0][0]
    in_set = _engines(ins)
    bus = set().union(*(_engines(em.get(t, [])) for t in BUS_TYPES))
    tb = em[T_TB][0][0] if em.get(T_TB) else None
    tb_follows = tb is not None and tb == first + sum(w for _, w in ins)
    family = bytes(c.head[11:15]).decode('latin1').strip()
    shared = family not in QUANTUM_FAMILIES
    if shared:
        above = [e for e in bus if e > max(in_set | {tb if tb_follows else first})]
        limit = min(above) if above else max(bus | in_set) + 1
    else:
        limit = QUANTUM_POOL if tb is None or tb_follows else tb
    return {'first': first, 'limit': limit, 'tb': tb, 'tb_follows': tb_follows, 'shared': shared,
            'room': limit - first - (1 if tb_follows else 0)}


# ---------------------------------------------------------------------------- section 211
def objects(s211):
    """([object bytes] sorted by id, tail bytes) of the live channel objects."""
    if s211[:2] != b'\xd3\x00':
        raise ValueError('section 211 does not start with d3 00')
    n = struct.unpack_from('<I', s211, 2)[0]
    p, out = 6, []
    for _ in range(n):
        o = p
        dl = struct.unpack_from('<H', s211, p + 2)[0]
        p += 4 + dl
        nrec = struct.unpack_from('<I', s211, p)[0]
        p += 4
        for _ in range(nrec):
            if s211[p:p + 4] != REC:
                raise ValueError('broken module record at %#x in section 211' % p)
            cnt = struct.unpack_from('<H', s211, p + 0x30)[0]
            p += 4 + 0x3a + 8 * cnt + 12
        if s211[p:p + 2] != b'\x27\x00':
            raise ValueError('broken object trailer at %#x in section 211' % p)
        p += 41
        out.append(bytearray(s211[o:p]))
    return out, bytearray(s211[p:])


def obj_id(o):
    return struct.unpack_from('<H', o, len(o) - 39)[0]


def obj_records(o):
    """[(record offset, type, count)] inside one object."""
    dl = struct.unpack_from('<H', o, 2)[0]
    p = 4 + dl
    nrec = struct.unpack_from('<I', o, p)[0]
    p += 4
    out = []
    for _ in range(nrec):
        typ = struct.unpack_from('<H', o, p + 4)[0]
        cnt = struct.unpack_from('<H', o, p + 0x30)[0]
        out.append((p, typ, cnt))
        p += 4 + 0x3a + 8 * cnt + 12
    return out


def obj_slot(o, module, param, band):
    """Offset of the float for (module, param, band) inside object o, or None."""
    for p, typ, cnt in obj_records(o):
        if typ != module:
            continue
        s0 = p + 4 + 0x3a
        for k in range(cnt):
            q = s0 + 8 * k
            if o[q] == param and o[q + 2] == band:
                return q + 4
    return None


def sstr31(name):
    b = name.encode('latin1')[:31]
    return bytes([len(b)]) + b + b'\x00' * (31 - len(b))


def obj_set(o, idx, name=None, width=None):
    """Set the trailer id (internal index, 1-based), the name copies and the width of one input object."""
    t = len(o) - 41
    struct.pack_into('<H', o, t + 2, 0x0100 | (idx - 1))
    if name is not None:
        f = sstr31(name)
        o[t + 4:t + 36] = f
        for p, _, _ in obj_records(o):
            o[p + 8:p + 40] = f
    if width is not None:
        o[t + 40] = width
        for (m, prm, b), (mono, st) in STEREO_SLOTS.items():
            q = obj_slot(o, m, prm, b)
            if q is not None:
                struct.pack_into('<f', o, q, st if width == 2 else mono)


def _mask_obj(o):
    o = bytearray(o)
    for p, _, _ in obj_records(o):
        o[p + 8:p + 48] = b'\0' * 40          # name + TDateTime
    t = len(o) - 41
    o[t + 2:t + 36] = b'\0' * 34              # id + name
    return bytes(o)


def default_object(in_objs):
    """The most common mono input object (ignoring id, names and timestamps): an untouched default channel."""
    monos = [o for o in in_objs if o[-1] == 1] or list(in_objs)
    best = Counter(_mask_obj(o) for o in monos).most_common(1)[0][0]
    return next(o for o in monos if _mask_obj(o) == best)


def default_cb(cbs):
    def m(r):
        r = bytearray(r)
        r[4:40] = b'\0' * 36
        if cb_has_engine(r):
            r[84:86] = b'\0\0'
        return bytes(r)
    monos = [r for r in cbs if r[41] == 1] or list(cbs)
    best = Counter(m(r) for r in monos).most_common(1)[0][0]
    return next(r for r in monos if m(r) == best)


# ---------------------------------------------------------------------------- banks (243) and placement (212)
def banks(s243):
    n = struct.unpack_from('<I', s243, 2)[0]
    return [bytearray(s243[6 + BANK_SIZE * k:6 + BANK_SIZE * (k + 1)]) for k in range(n)], \
        bytearray(s243[6 + BANK_SIZE * n:])


def is_input_bank(b):
    # strip j: internal index - 1 at +0x23+2j, strip type at +0x24+2j (01 = input channel)
    return any(b[0x24 + 2 * j] == 0x01 for j in range(12))


def bank_slot(b):
    """Overview grid slot of a bank (col + 6 * row), or None when the bank is not on the grid."""
    x, y = struct.unpack_from('<I', b, 0x1a)[0], struct.unpack_from('<H', b, 0x1e)[0]
    if x == NO_POS:
        return None
    return (x - 1) // GRID_W + GRID_COLS * ((y - 2) // GRID_H)


def set_bank_slot(b, slot):
    struct.pack_into('<I', b, 0x1a, 1 + GRID_W * (slot % GRID_COLS))
    struct.pack_into('<H', b, 0x1e, 2 + GRID_H * (slot // GRID_COLS))


def make_input_banks(template_full, ids_in_order):
    """Banks of 12 input strips in surface order. Empty strips copy the layout of a partial editor bank."""
    out = []
    for k in range(0, len(ids_in_order), 12):
        chunk = ids_in_order[k:k + 12]
        b = bytearray(template_full)
        first, last = k + 1, k + len(chunk)
        nm = 'Ch %d-%d' % (first, last) if last > first else 'Ch %d' % first
        b[4:4 + 16] = (bytes([len(nm)]) + nm.encode() + b'\x00' * 15)[:16]
        for j in range(12):
            if j < len(chunk):
                b[0x23 + 2 * j] = chunk[j] - 1
                b[0x24 + 2 * j] = 0x01
            else:
                b[0x23 + 2 * j] = 0
                b[0x24 + 2 * j] = 0
                b[0x6b + 16 * j:0x6b + 16 * (j + 1)] = b'\x00' * 16
                b[0x12b + j] = 0
        out.append(b)
    return out


def place_banks(new_banks, old_banks, old_in, new_in):
    """Keys = list position. Input bank k sits at overview slot k. Every later bank keeps its old slot shifted by
    the change in input banks (same as the editor's grid when the slots ran on from the inputs, and it keeps model
    layouts such as SD8's that start the outputs on a new row). Banks off the grid stay off it."""
    delta = new_in - old_in
    for k, b in enumerate(new_banks):
        struct.pack_into('<H', b, 2, k)
        if k < new_in:
            set_bank_slot(b, k)
        else:
            slot = bank_slot(old_banks[k - delta])
            if slot is not None and delta:
                set_bank_slot(b, slot + delta)


def _tables(t212):
    return [[struct.unpack_from('<H', t212, 2 + 99 * u + 2 * j)[0] for j in range(42)] for u in range(8)]


INPUT_LAYERS = 6   # in each fader-section table, positions 0-5 are input layers and 6-11 output layers


def remap_placement(t212, old_in, new_in):
    """Bank numbers in the 212 table. Every table position keeps its layer; only bank numbers change.
    Shrink: input banks >= new_in leave their layer empty (the state the editor accepted in the load tests).
    Every later bank shifts by new_in - old_in. Grow: the editor deals input banks round-robin over the fader
    sections (bank k at section order[k % m], input layer k // m; Q225: left, right, left, ...). Each new input
    bank takes that layer when it is free; otherwise it stays unplaced, the editor's 'Restructure without
    Rebuild Banks' state."""
    t = bytearray(t212)
    tables = _tables(t)
    pos = {v: (u, j) for u, tab in enumerate(tables) for j, v in enumerate(tab) if v != 0xffff}
    order = []
    for k in range(old_in):
        if k in pos and pos[k][0] not in order:
            order.append(pos[k][0])
    for tab in tables:
        for j, v in enumerate(tab):
            if v == 0xffff:
                continue
            tab[j] = (v if v < new_in else 0xffff) if v < old_in else v - old_in + new_in
    for k in range(old_in, new_in):
        if not order:
            break
        u, j = order[k % len(order)], k // len(order)
        if j < INPUT_LAYERS and tables[u][j] == 0xffff:
            tables[u][j] = k
    for u, tab in enumerate(tables):
        for j, v in enumerate(tab):
            struct.pack_into('<H', t, 2 + 99 * u + 2 * j, v)
    return t


# ---------------------------------------------------------------------------- session notes (section 0)
def set_notes(c, text):
    """Session notes (section 0): 00 00 | u16 length | latin-1 text, as Files > Session Notes saves them."""
    b = text.encode('latin1', 'replace')[:255]
    c.sections[0][1] = bytearray(b'\x00\x00' + struct.pack('<H', len(b)) + b)


def notes(data):
    c = Container(data)
    s = c.sections[0][1]
    if len(s) < 4:
        return ''
    n = struct.unpack_from('<H', s, 2)[0]
    return bytes(s[4:4 + n]).decode('latin1')


# ---------------------------------------------------------------------------- the operation
def relayout(data, spec, session_notes=None):
    """Rebuild the input layout. spec: list in SURFACE order of dicts {name, width (1/2), src (optional existing
    internal index to copy processing from), idx (optional internal index to use)}. Returns new bytes.
    Internal indices: explicit idx, else src, else the lowest free one, so a plain list keeps 1..N."""
    spec = [dict(e) for e in spec]
    if not spec:
        raise ValueError('a session needs at least one input channel')
    c = Container(data)
    s201 = c.sec(201)[1]
    gq, g0, g1, cbs = input_group(s201)
    cb_by_id = {struct.unpack_from('<H', r, 4)[0]: r for r in cbs}
    s211 = c.sec(211)[1]
    objs, tail = objects(s211)
    in_objs = {obj_id(o): o for o in objs if obj_id(o) >> 8 == 1}
    other = [o for o in objs if obj_id(o) >> 8 != 1]
    mono_t = default_object(list(in_objs.values()))
    cb_t = default_cb(cbs)

    used = {e['idx'] for e in spec if e.get('idx')}
    nxt = 1
    for e in spec:
        if not e.get('idx'):
            if e.get('src') and e['src'] not in used:
                e['idx'] = e['src']
            else:
                while nxt in used:
                    nxt += 1
                e['idx'] = nxt
            used.add(e['idx'])
    if len(used) != len(spec) or max(used) > MAX_INPUT_IDS:
        raise ValueError('input indices must be unique and at most %d' % MAX_INPUT_IDS)

    # 211: one object per channel, cloned from its source (or the default mono object), sorted by id
    new_in = []
    for e in spec:
        src = in_objs.get(0x0100 | ((e.get('src') or e['idx']) - 1))
        o = bytearray(src if src is not None else mono_t)
        obj_set(o, e['idx'], e['name'], e['width'])
        new_in.append(o)
    new_in.sort(key=obj_id)
    head = bytearray(s211[:6])
    struct.pack_into('<I', head, 2, len(new_in) + len(other))
    body = b''.join(new_in) + b''.join(other)

    # 201: cb records in surface order, EngineChannel = first + running sum of widths. The inputs must fit below
    # the first bus (SD) or the fixed TB In (Quantum); TB In that sat right after the inputs moves with them.
    room = engine_room(c)
    need = sum(e['width'] for e in spec)
    if room is not None and need > room['room']:
        raise ValueError('the inputs need %d engine channels; this session has room for %d'
                         % (need, room['room']))
    path0 = struct.unpack_from('<H', cbs[0], 84)[0] if cb_has_engine(cbs[0]) else None
    new_cb, acc = [], path0
    for n, e in enumerate(spec, 1):
        r = bytearray(cb_by_id.get(0x0100 | ((e.get('src') or e['idx']) - 1), cb_t))
        struct.pack_into('<HH', r, 4, 0x0100 | (e['idx'] - 1), n)
        r[8:40] = sstr31(e['name'])
        r[41] = e['width']
        if acc is not None:
            struct.pack_into('<H', r, 84, acc)
            acc += e['width']
        new_cb.append(r)
    s201n = bytearray(s201[:g0]) + b''.join(new_cb) + s201[g1:]
    struct.pack_into('<I', s201n, gq + 0x70, len(spec))
    if room is not None and room['tb_follows']:
        for p in groups201(s201n).get(T_TB, []):
            struct.pack_into('<h', s201n, p + 84, acc)
    c.sec(201)[1] = s201n

    # 243: input banks rebuilt in surface order, later banks renumbered
    s243 = c.sec(243)[1]
    bl, btail = banks(s243)
    old_in = sum(1 for b in bl if is_input_bank(b))
    if any(is_input_bank(b) for b in bl[old_in:]):
        raise ValueError('input banks are not the first banks; this baseline needs a bank rebuild in the editor')
    full = next(b for b in bl if is_input_bank(b))
    ib = make_input_banks(full, [e['idx'] for e in spec])
    nbl = ib + [bytearray(b) for b in bl[old_in:]]
    place_banks(nbl, bl, old_in, len(ib))
    c.sec(243)[1] = bytearray(s243[:2]) + struct.pack('<I', len(nbl)) + b''.join(nbl) + btail

    # 212 and its copy in the 211 tail
    t212 = c.sec(212)[1]
    t212n = remap_placement(t212, old_in, len(ib))
    c.sec(212)[1] = t212n
    i = bytes(tail).find(bytes(t212))
    if i < 0:
        raise ValueError('section 211 tail holds no copy of section 212')
    tail[i:i + len(t212)] = t212n
    c.sec(211)[1] = head + body + tail

    if session_notes is not None:
        set_notes(c, session_notes)
    struct.pack_into('<H', c.head, 0x26, len(spec))
    return c.build()


def flip(data, surface_numbers, width=2):
    """Flip channels (by surface number) to stereo/mono in place. File length does not change."""
    c = Container(data)
    s201 = c.sec(201)[1]
    gq, g0, g1, cbs = input_group(s201)
    s211 = c.sec(211)[1]
    objs, tail = objects(s211)
    p, acc = g0, None
    for r in cbs:
        num = struct.unpack_from('<H', r, 6)[0]
        if num in surface_numbers:
            r[41] = width
        if cb_has_engine(r):
            acc = struct.unpack_from('<H', r, 84)[0] if acc is None else acc
            struct.pack_into('<H', r, 84, acc)
            acc += r[41]
        s201[p:p + len(r)] = r
        p += len(r)
    ids = {struct.unpack_from('<H', r, 4)[0] for r in cbs if struct.unpack_from('<H', r, 6)[0] in surface_numbers}
    out = bytearray(s211[:6])
    for o in objs:
        if obj_id(o) in ids:
            obj_set(o, (obj_id(o) & 0xff) + 1, None, width)
        out += o
    out += tail
    c.sec(211)[1] = out
    return c.build()
