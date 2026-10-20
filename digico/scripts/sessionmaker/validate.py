#!/usr/bin/env python3
"""validate.py - structural invariants every generated session must meet.

Every invariant holds in all 58 editor-saved files checked
(39 real sessions V1455-V2025, the editor-made baselines and the 15 editor-saved default sessions), and in every
relayout candidate the Quantum 225 V2242 editor loaded and re-saved unchanged. The engine-pool rules
(engine_pool_errors) also hold in the 91 editor-saved files that include the editors' boot re-saves.

usage: python3 -m sessionmaker.validate file.ses [...]
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


def engine_pool_errors(family, em, taken):
    """The inputs' engine channels (taken) against the rest of the pool (layout.py "engine channels"): never on the
    Talkback Input's channel; on SD models never on an aux, group or matrix channel nor past the top of the pool;
    on Quantum never past 255."""
    if not em or not taken:
        return []
    errs = []
    tb = {e for e, _ in em.get(layout.T_TB, [])}
    if taken & tb:
        errs.append('an input shares engine channel %d with the Talkback Input' % min(taken & tb))
    if family in layout.QUANTUM_FAMILIES:
        if max(taken) >= layout.QUANTUM_POOL:
            errs.append('input engine channels run to %d, past the end of the pool (%d)'
                        % (max(taken), layout.QUANTUM_POOL - 1))
        return errs
    bus = set().union(*({e + k for e, w in em.get(t, []) for k in range(w)} for t in layout.BUS_TYPES))
    if taken & bus:
        errs.append('%d input engine channels collide with aux, group or matrix channels (first %d)'
                    % (len(taken & bus), min(taken & bus)))
    if bus and max(taken) > max(bus):
        errs.append('input engine channels run to %d, past the top of the pool (%d)' % (max(taken), max(bus)))
    return errs


# Header counts (tConsoleRec) against the section 201 records they count: (header offset, struct format, record type,
# width or None for any, label). Equal in all 716 editor-saved files (116+ defaults, 39 real sessions,
# 557 boot re-saves;. The editors trust the header: the Quantum 225 V2242 editor crashed
# (access violation in Quantum2.exe) on a file whose header said 7 mono auxes over 6 aux records, and threw away a
# file whose header said 255 (decode notes, not published).
HEADER_COUNTS = [(0x36, 'H', 0x05, 1, 'mono auxes'), (0x38, 'H', 0x05, 2, 'stereo auxes'),
                 (0x46, 'H', 0x06, 1, 'mono groups'), (0x48, 'H', 0x06, 2, 'stereo groups'),
                 (0x93, 'B', 0x10, None, 'matrix outputs'), (0x94, 'B', 0x0a, None, 'control groups'),
                 (0x96, 'B', 0x0f, None, 'matrix inputs'), (0x97, 'B', 0x11, None, 'graphic EQs')]
T_BUS_RIGHT = 0x07


def header_count_errors(d, s201):
    """The bus, matrix, control group and graphic EQ counts of the header against the section 201 records, and the
    right-side records (type 07) against the stereo auxes plus stereo groups."""
    s201 = bytes(s201)
    g = layout.groups201(s201)
    errs = []
    width = lambda t, w: sum(1 for p in g.get(t, []) if w is None or s201[p + 41] == w)  # noqa: E731
    for off, fmt, typ, w, label in HEADER_COUNTS:
        want = struct.unpack_from('<' + fmt, d, off)[0]
        got = width(typ, w)
        if want != got:
            errs.append('header count mismatch: %d %s in the header, %d in the channel list' % (want, label, got))
    st = struct.unpack_from('<H', d, 0x38)[0] + struct.unpack_from('<H', d, 0x48)[0]
    if not errs and width(T_BUS_RIGHT, None) != st:
        errs.append('header count mismatch: %d stereo buses in the header, %d right sides in the channel list'
                    % (st, width(T_BUS_RIGHT, None)))
    return errs


def check(path_or_bytes):
    """-> (errors, info). errors is a list of plain sentences; empty means every invariant holds."""
    d = bytes(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, 'rb').read()
    errs = []
    if d[:11] != b'DiGiCo     ' or d[0x0f:0x15] != b'.SES v':
        return ['not a DiGiCo session header'], {}
    offs = struct.unpack_from('<40i', d, 0x100)
    n = next((i for i in range(1, 40) if offs[i] == len(d)), None)
    if n is None:
        return ['no section offset equals the file size'], {}
    if any(offs[i + 1] < offs[i] for i in range(n)):
        errs.append('section offsets do not ascend')
    try:
        c = layout.Container(d)
        if c.build() != d:
            errs.append('container does not round-trip')
        s201 = c.sec(201)[1]
        gq, g0, g1, cbs = layout.input_group(s201)
        objs, tail = layout.objects(c.sec(211)[1])
        bl, _ = layout.banks(c.sec(243)[1])
        t212 = bytes(c.sec(212)[1])
    except (ValueError, StopIteration, struct.error) as e:
        return errs + ['structure walk failed: %s' % e], {}

    nin_hdr = struct.unpack_from('<H', d, 0x26)[0]
    if not (nin_hdr == len(cbs) == struct.unpack_from('<I', s201, gq + 0x70)[0]):
        errs.append('input counts disagree: header %d, channel records %d' % (nin_hdr, len(cbs)))
    errs += header_count_errors(d, s201)
    nums = [struct.unpack_from('<H', r, 6)[0] for r in cbs]
    if nums != list(range(1, len(cbs) + 1)):
        errs.append('channel record surface numbers are not 1..N in order')
    cumulative = None
    if layout.cb_has_engine(cbs[0]):
        # EngineChannel: after a Restructure it is first + running sum of widths (surface order); a later
        # per-channel flip takes the next free engine channels instead (seen in a real SD8 session). The hard
        # invariant is that the ranges [eng, eng + width) never overlap.
        acc = struct.unpack_from('<H', cbs[0], 84)[0]
        cumulative = True
        taken = set()
        for r in cbs:
            e = struct.unpack_from('<H', r, 84)[0]
            if e != acc:
                cumulative = False
            acc += r[41]
            rng = set(range(e, e + r[41]))
            if rng & taken:
                errs.append('EngineChannel overlap at surface %d' % struct.unpack_from('<H', r, 6)[0])
            taken |= rng
        errs += engine_pool_errors(d[11:15].decode('latin1').strip(), layout.engine_map(s201), taken)
    if struct.unpack_from('<I', c.sec(211)[1], 2)[0] != len(objs):
        errs.append('section 211 object count wrong')
    ids = [layout.obj_id(o) for o in objs]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        errs.append('section 211 objects not sorted/unique by id')
    total_cb = len(re.findall(re.escape(b'\xcb\x00' + bytes([len(cbs[0]) - 4]) + b'\x00'), bytes(s201)))
    if total_cb < len(objs):
        errs.append('fewer channel records (%d) than section 211 objects (%d)' % (total_cb, len(objs)))
    in_objs = {layout.obj_id(o): o for o in objs if layout.obj_id(o) >> 8 == 1}
    cb_ids = [struct.unpack_from('<H', r, 4)[0] for r in cbs]
    if sorted(cb_ids) != sorted(in_objs):
        errs.append('channel record ids != section 211 input ids')
    for r in cbs:
        o = in_objs.get(struct.unpack_from('<H', r, 4)[0])
        if o is None:
            continue
        w = r[41]
        if w not in (1, 2):
            errs.append('bad width %d for id %#x' % (w, struct.unpack_from('<H', r, 4)[0]))
        if o[-1] != w:
            errs.append('trailer width != StereoMode for id %#x' % struct.unpack_from('<H', r, 4)[0])
        for (m, p, b), (mono, st) in layout.STEREO_SLOTS.items():
            q = layout.obj_slot(o, m, p, b)
            v = struct.unpack_from('<f', o, q)[0] if q is not None else None
            # stereo must carry the stereo value; real mono channels hold the mono value or 0.0
            if q is not None and not (v == st if w == 2 else v in (mono, 0.0)):
                errs.append('slot %02x/%02x/%d inconsistent with width for id %#x'
                            % (m, p, b, struct.unpack_from('<H', r, 4)[0]))
    if struct.unpack_from('<I', c.sec(243)[1], 2)[0] != len(bl):
        errs.append('bank count wrong')
    if [struct.unpack_from('<H', b, 2)[0] for b in bl] != list(range(len(bl))):
        errs.append('bank keys not 0..n-1')
    placed = []
    for b in bl:
        for j in range(12):
            if b[0x24 + 2 * j] == 1:
                placed.append(0x0100 | b[0x23 + 2 * j])
    missing = set(cb_ids) - set(placed)
    dangling = set(placed) - set(cb_ids)
    if dangling:
        errs.append('bank strips point at missing inputs %s' % sorted(hex(x) for x in dangling))
    if bytes(tail).find(t212) < 0:
        errs.append('section 211 tail does not hold a copy of section 212')
    used = [v for tab in layout._tables(t212) for v in tab]
    if any(v != 0xffff and v >= len(bl) for v in used):
        errs.append('section 212 references a bank that does not exist')
    if len([v for v in used if v != 0xffff]) != len({v for v in used if v != 0xffff}):
        errs.append('section 212 places a bank twice')
    stereo = sum(1 for r in cbs if r[41] == 2)
    eng = sum(r[41] for r in cbs)
    return errs, dict(inputs=len(cbs), stereo=stereo, engine=eng, cumulative=cumulative, banks=len(bl),
                      unbanked=len(missing), size=len(d))


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: python3 -m sessionmaker.validate file.ses [...]')
        sys.exit(0 if len(sys.argv) > 1 else 2)
    bad = 0
    for p in sys.argv[1:]:
        errs, info = check(p)
        bad += bool(errs)
        print('%-40s %s %s' % (os.path.basename(p)[-40:], 'OK ' if not errs else 'BAD', info), '; '.join(errs[:4]))
    sys.exit(1 if bad else 0)
