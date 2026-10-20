#!/usr/bin/env python3
"""ses.py - structural reader/writer for DiGiCo SD/Quantum .SES session files.

Works on any session (any console model, channel count or software version since
at least V1455) because it walks the file by structure instead of fixed offsets.

File layout (format version 0x1c8):
  0x000  header, 0x100 bytes ("DiGiCo     " + model + ".SES vO   \\r", versions)
         u16 @0x22 software build (2242), u16 @0x26 input count, @0x36/@0x38 mono/stereo auxes,
         @0x46/@0x48 mono/stereo groups.
  0x100  section table: int32 offsets [40], section ids u8[40] at 0x1a0;
         the editor checks offsets ascend and the last one equals the file size.
Every console module is a record (the slot type is DiGiCo's tControllerSnapshot):
  da 00 | 3a 00 (header length from `type`) | type u16 | 00 00 | name ShortString[31] (32 B)
  | TDateTime | count u16 | ... | count x [param u8][module u8][band u8][flags u8][float32 value]
  | ff x8 00 x4
An input channel is its run of module records followed by a trailer
  27 00 | id u16 (0x0100 | index) | name ShortString[31] ...
and a channel record in section 201: cb 00 hl 00 | id u16 | number u16 | name ShortString[31] | 00 | width u8 ...
The channel record header length hl depends on the build: 0x50 in V1455, 0x58 in V1619-V2025, 0x79 in V2242.
Section 201 groups the channel records by type: ca 00 6c 00 | type u8 | name ShortString ... | u32 count @+0x70
| count channel records (01 inputs, 05 auxes, 06 groups, ...). The band byte of an input's aux send (module 02)
or group assign (module 03) is the bus's internal index (id & 0xff), not its surface number.
All copies of a channel name are fixed 32-byte fields, so renames never move offsets
(20 copies on Quantum, 15 on SD consoles, which have no Mustard modules 0x1a-0x1e).
"""
import json
import os
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS_PATH = os.path.join(HERE, '..', 'keys_from_offsets.json')

REC_MAGIC = b'\xda\x00\x3a\x00'
TRAILER_TAG = b'\x27\x00'
CHREC_MAGIC = b'\xcb\x00\x79\x00'            # V2242 only; kept for older callers, use CHREC_RE
CHREC_HL = (0x50, 0x58, 0x78, 0x79)           # channel record header length: V1455 / V1619-V2126 / Q112+Q852 V1926-V2126 / V2232+
CHREC_RE = re.compile(rb'\xcb\x00[\x50\x58\x78\x79]\x00')
GROUP_RE = re.compile(rb'\xca\x00\x6c\x00')   # section 201 group header (type, name, count @+0x70)

# section 201 group / channel record types (id >> 8)
T_INPUT, T_AUX, T_GROUP = 0x01, 0x05, 0x06
MUSTARD_COMP = 0x1d                           # first Mustard module a writer usually needs


class Record:
    __slots__ = ('off', 'type', 'name', 'count', 'slot0', 'end', 'slots')

    def __init__(self, d, off):
        self.off = off
        self.type = struct.unpack_from('<H', d, off + 4)[0]
        n = d[off + 8]
        self.name = bytes(d[off + 9:off + 9 + n]).decode('latin1')
        self.count = struct.unpack_from('<H', d, off + 0x30)[0]
        self.slot0 = off + 4 + 0x3a
        self.end = self.slot0 + 8 * self.count
        self.slots = {}
        for k in range(self.count):
            s = self.slot0 + 8 * k
            self.slots[(d[s], d[s + 2])] = s + 4      # (param, band) -> float offset

    @staticmethod
    def valid(d, off):
        if off + 0x40 > len(d) or d[off + 8] > 31:
            return False
        typ = struct.unpack_from('<H', d, off + 4)[0]
        cnt = struct.unpack_from('<H', d, off + 0x30)[0]
        s = off + 4 + 0x3a
        if s + 8 * cnt + 12 > len(d):
            return False
        return all(d[s + 8 * k + 1] == typ for k in range(cnt))


class Channel:
    def __init__(self, index, records, trailer):
        self.index = index            # 1-based
        self.records = {r.type: r for r in records}
        self.trailer = trailer        # offset of the 27 00 tag

    def __repr__(self):
        return 'Channel(%d, %r)' % (self.index, self.name)

    @property
    def name(self):
        return next(iter(self.records.values())).name

    def has(self, module):
        return module in self.records


def chrec_ok(d, p):
    """True when a cb record candidate at p looks real: known header length, name fits, width 1 or 2."""
    return (p + 42 <= len(d) and d[p + 2] in CHREC_HL and d[p + 8] <= 31 and d[p + 41] in (1, 2))


class Session:
    def __init__(self, path_or_bytes):
        if isinstance(path_or_bytes, (bytes, bytearray)):
            self.d = bytearray(path_or_bytes)
        else:
            self.d = bytearray(open(path_or_bytes, 'rb').read())
        self.keys = json.load(open(KEYS_PATH)) if os.path.exists(KEYS_PATH) else {}
        self._parse()

    # ---- structure -------------------------------------------------------
    @property
    def model(self):
        """File-family code at 0x0b ('Q2', 'SD9', 'SDC', ...). SD10 saves as SD8, SD11 as SD9, SD5CS as SD5."""
        return bytes(self.d[11:15]).decode('latin1').strip()

    @property
    def version(self):
        """Software build that saved the file (u16 @0x22): 1619, 2025, 2242, ..."""
        return struct.unpack_from('<H', self.d, 0x22)[0]

    def header_counts(self):
        """Counts kept in the header. They match the section 201 records in every file seen."""
        u = lambda o: struct.unpack_from('<H', self.d, o)[0]
        return {'inputs': u(0x26), 'aux_mono': u(0x36), 'aux_stereo': u(0x38),
                'group_mono': u(0x46), 'group_stereo': u(0x48)}

    def sections(self):
        out = []
        for i in range(1, 40):
            sid = self.d[0x1a0 + i]
            off = struct.unpack_from('<i', self.d, 0x100 + 4 * i)[0]
            if sid == 0 and off == len(self.d):
                break
            out.append((i, sid, off))
        return out

    def section_span(self, sid):
        """(start, end) of the first section with id `sid`, or None."""
        secs = self.sections()
        for k, (_, s, o) in enumerate(secs):
            if s == sid:
                return o, (secs[k + 1][2] if k + 1 < len(secs) else len(self.d))
        return None

    def _parse(self):
        d = self.d
        self.records = [Record(d, m.start()) for m in re.finditer(re.escape(REC_MAGIC), d)
                        if Record.valid(d, m.start())]
        # input channels: records followed (after the ff*8 00*4 tail) by a 27 00 <0x01xx> trailer
        self.inputs = []
        run = []
        for r in self.records:
            if run and (r.name != run[-1].name or r.off != run[-1].end + 12):
                run = []
            run.append(r)
            t = r.end + 12
            if d[t:t + 2] != TRAILER_TAG or d[t + 3] != 0x01:
                continue
            n = d[t + 4]
            if n > 31 or bytes(d[t + 5:t + 5 + n]).decode('latin1') != r.name:
                continue
            firsts = [i for i, x in enumerate(run) if x.type == 0x01]
            if firsts:
                self.inputs.append(Channel(d[t + 2] + 1, run[firsts[-1]:], t))
            run = []
        # section 211 holds the live channels; section 219 holds snapshot copies of them
        live = [(o, n) for (_, sid, o), (_, _, n) in zip(self.sections(), self.sections()[1:] + [(0, 0, len(d))])
                if sid == 211]
        in_live = lambda c: any(o <= c.trailer < n for o, n in live)
        self.snapshot_inputs = [c for c in self.inputs if not in_live(c)]
        self.inputs = sorted((c for c in self.inputs if in_live(c)), key=lambda c: c.index)
        self.by_index = {c.index: c for c in self.inputs}
        self._parse_201()

    def _parse_201(self):
        """Section 201 channel records: cb 00 hl 00 | id (type << 8 | idx) | display number | name[32] | 00 | width
        (01 mono, 02 stereo). The display number is the channel number on the surface; after a channel-order
        restructure it differs from the internal index. Walked group by group; a plain scan is the fallback."""
        d = self.d
        self.display = {}     # display number -> internal index
        self.width = {}       # display number -> 1 mono / 2 stereo
        self.chrec_off = {}   # internal index -> offset of its section 201 record
        self.groups201 = {}   # record type -> [{'off', 'id', 'number', 'name', 'width'}] in surface order
        span = self.section_span(201)
        lo, hi = span if span else (0, len(d))
        for m in GROUP_RE.finditer(d, lo, hi):
            p = m.start()
            n = d[p + 5]
            if n > 31 or p + 0x74 > hi:
                continue
            typ, cnt, q, recs = d[p + 4], struct.unpack_from('<I', d, p + 0x70)[0], p + 0x74, []
            for _ in range(cnt):
                if q + 42 > hi or d[q:q + 2] != b'\xcb\x00' or not chrec_ok(d, q):
                    recs = None
                    break
                cid, num = struct.unpack_from('<HH', d, q + 4)
                recs.append({'off': q, 'id': cid, 'number': num, 'width': d[q + 41],
                             'name': bytes(d[q + 9:q + 9 + d[q + 8]]).decode('latin1')})
                q += 4 + d[q + 2]
            if recs is not None and recs and all(r['id'] >> 8 == typ for r in recs):
                self.groups201.setdefault(typ, []).extend(recs)
        inputs = self.groups201.get(T_INPUT)
        if not inputs:   # fallback: scan every channel record in the file
            inputs = []
            for m in CHREC_RE.finditer(d):
                p = m.start()
                if not chrec_ok(d, p):
                    continue
                cid, num = struct.unpack_from('<HH', d, p + 4)
                if cid >> 8 == T_INPUT:
                    inputs.append({'off': p, 'id': cid, 'number': num, 'width': d[p + 41]})
        for r in inputs:
            idx = (r['id'] & 0xff) + 1
            if idx not in self.by_index:
                continue
            self.display[r['number']] = idx
            self.width[r['number']] = r['width']
            self.chrec_off[idx] = r['off']
        # bus maps: surface number -> band byte used by the input's send (module 02) / group (module 03) slots
        self.auxes = [{'number': r['number'], 'band': r['id'] & 0xff, 'name': r['name'], 'width': r['width']}
                      for r in sorted(self.groups201.get(T_AUX, []), key=lambda r: r['number'])]
        self.groups = [{'number': r['number'], 'band': r['id'] & 0xff, 'name': r['name'], 'width': r['width']}
                       for r in sorted(self.groups201.get(T_GROUP, []), key=lambda r: r['number'])]
        self.aux_band = {a['number']: a['band'] for a in self.auxes}
        self.group_band = {g['number']: g['band'] for g in self.groups}

    def ch(self, number):
        """Internal channel index for surface channel `number` (falls back to the index itself)."""
        return self.display.get(number, number)

    def has_module(self, module, ch=None):
        """True when input `ch` (or, with no ch, every live input) carries `module`.
        SD consoles have no Mustard modules (0x1a-0x1e); Quantum consoles have them on every input."""
        if ch is not None:
            c = self.by_index.get(ch)
            return c is not None and module in c.records
        return bool(self.inputs) and all(module in c.records for c in self.inputs)

    @property
    def has_mustard(self):
        return self.has_module(MUSTARD_COMP)

    def spice_rack(self):
        """Live Spice Rack slots (type 0x1f records with 67 slots: Chilli 6), in slot order. Empty on SD consoles."""
        span = self.section_span(211)
        return [r for r in self.records if r.type == 0x1f and r.count == 67
                and (span is None or span[0] <= r.off < span[1])]

    # ---- surface banks ---------------------------------------------------------
    # Section 243: u16 | u32 bank count | banks. A bank is u16 size (0x169) | u16 index | name ShortString[15]
    # | ... | 12 strips of (index u8, type u8) at +0x23 | ... | 12 view bytes at the end of the bank.
    # Strip type 01 = input channel (index = internal index - 1), 05 aux, 06 group, 0a CG, 10 matrix.
    # View byte: 0 = strip shows SD processing, 2 = strip shows Mustard processing (the SD/M buttons).
    STRIP_INPUT, VIEW_SD, VIEW_MUSTARD = 0x01, 0, 2

    def banks(self):
        st = next((o for _, sid, o in self.sections() if sid == 243), None)
        if st is None:
            return []
        out, p = [], st + 6
        for _ in range(struct.unpack_from('<I', self.d, st + 2)[0]):
            size, idx = struct.unpack_from('<HH', self.d, p)
            if size != 0x169:
                raise ValueError('unexpected surface bank size %#x at %#x' % (size, p))
            out.append({'off': p, 'name': bytes(self.d[p + 5:p + 5 + min(self.d[p + 4], 15)]).decode('latin1'),
                        'strips': [(self.d[p + 0x24 + 2 * j], self.d[p + 0x23 + 2 * j]) for j in range(12)],
                        'view': p + size - 12})
            p += size
        return out

    def set_strip_view(self, ch, view):
        """Show input channel `ch` (internal index) on the SD or Mustard view on every bank that holds it."""
        n = 0
        for b in self.banks():
            for j, (typ, idx) in enumerate(b['strips']):
                if typ == self.STRIP_INPUT and idx + 1 == ch:
                    self.d[b['view'] + j] = view
                    n += 1
        return n

    # ---- slot access -----------------------------------------------------
    def slot(self, ch, module, param, band=0):
        rec = self.by_index[ch].records.get(module)
        if rec is None:
            raise KeyError('channel %d has no module %#x' % (ch, module))
        off = rec.slots.get((param, band))
        if off is None:
            raise KeyError('channel %d module %#x has no param %#x band %d' % (ch, module, param, band))
        return off

    def has_slot(self, ch, module, param, band=0):
        rec = self.by_index[ch].records.get(module)
        return rec is not None and (param, band) in rec.slots

    def get(self, ch, module, param, band=0):
        return struct.unpack_from('<f', self.d, self.slot(ch, module, param, band))[0]

    def set(self, ch, module, param, band, value):
        struct.pack_into('<f', self.d, self.slot(ch, module, param, band), float(value))

    def key(self, field):
        k = self.keys[field]
        return k['module'], k['param'], k['band']

    def fget(self, ch, field):
        return self.get(ch, *self.key(field))

    def fset(self, ch, field, value):
        self.set(ch, *self.key(field), value)

    # ---- names -------------------------------------------------------------
    @staticmethod
    def _sstr31(name):
        b = name.encode('latin1')
        if len(b) > 31:
            raise ValueError('name longer than 31 bytes: %r' % name)
        return bytes([len(b)]) + b + b'\x00' * (31 - len(b))

    def rename(self, ch, name, max_len=8):
        """Write `name` into every copy for input channel `ch`. Names over 8 chars are
        untested on a console, so they are refused unless max_len is raised."""
        if len(name) > max_len:
            raise ValueError('%r is longer than %d chars' % (name, max_len))
        c = self.by_index[ch]
        field = self._sstr31(name)
        n = 0
        for r in c.records.values():
            self.d[r.off + 8:r.off + 40] = field
            n += 1
        self.d[c.trailer + 4:c.trailer + 36] = field
        n += 1
        # every channel record for this id, any build (section 201 and any snapshot copies)
        chid = struct.pack('<H', 0x0100 | (ch - 1))
        for m in re.finditer(rb'\xcb\x00[\x50\x58\x78\x79]\x00' + re.escape(chid), self.d):
            p = m.start()
            if not chrec_ok(self.d, p):
                continue
            self.d[p + 8:p + 40] = field
            n += 1
        for r in c.records.values():
            r.name = name
        return n

    def save(self, path):
        with open(path, 'wb') as f:
            f.write(self.d)


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: ses.py <file.ses>   (summary: model, build, channels and the modules of the first and last inputs)')
        sys.exit(0 if len(sys.argv) == 2 else 2)
    s = Session(sys.argv[1])
    print('model %s V%d, %d bytes, %d module records, %d input channels (%d stereo), %d auxes, %d groups%s'
          % (s.model, s.version, len(s.d), len(s.records), len(s.inputs),
             sum(1 for w in s.width.values() if w == 2), len(s.auxes), len(s.groups),
             ', Mustard' if s.has_mustard else ''))
    for c in s.inputs[:4] + s.inputs[-2:]:
        print('  ch %2d %-10r modules %s' % (c.index, c.name, ' '.join('%02x' % t for t in c.records)))
