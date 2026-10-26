#!/usr/bin/env python3
"""s6l_tool.py: read Avid VENUE | S6L show files (.dsh) and make the few changes VENUE has loaded.

An S6L show (VENUE 5.0 and later) is a "Digidesign Storage - 1.0" file: a typed key/value tree with no compression
at the top level and no checksum. This tool reads the header, every strip (name, stereo, colour, fader, input patch,
HPF, EQ, dynamics, aux sends), the plug-in racks (type, rack slot, insert point, readable settings) and the snapshot
list, the same way idontownapc.com/s6l does. Format notes: ../references/S6L-FORMAT.md.

Commands:
  s6l_tool.py info      SHOW.dsh                 header, engine, counts, and what edit may change in this show
  s6l_tool.py strips    SHOW.dsh [--kind KIND] [--proc] [--sends]
  s6l_tool.py plugins   SHOW.dsh [--params]      used rack slots; --params prints the readable settings
  s6l_tool.py snapshots SHOW.dsh                 snapshot names and the plug-in copies each one keeps
  s6l_tool.py check     SHOW.dsh                 the file checks that edit runs on every file it writes
  s6l_tool.py json      SHOW.dsh                 everything above as JSON
  s6l_tool.py edit      SHOW.dsh OUT.dsh CHANGES [--dry-run]

Strip ids are 1-based, as on the VENUE screen: in1, fx1, aux1, grp1, mtx1, mains1 to mains3, pq1, vca1 (a plain
number is an input). In an L-R plus Mono show mains1 is Left, mains2 is Right and mains3 is Mono (VENUE shows them
in the order Left, Mono, Right). A rack slot is RACK.POSITION, for example 2.3 (racks 1 to 5, positions 1 to 25).

CHANGES for edit (repeat any of them):
  --rename ID=NAME        a strip name, 16 characters at most, Windows-1252
  --names FILE            input names from a file: a .csv with a Name column (a Ch column sets the input number),
                          or a text file with one name a line (line 1 is input 1, a blank line keeps that input)
  --colour ID=COLOUR      0 to 8, or grey green blue yellow orange cyan purple red white
  --fader ID=DB           -144 to +12 dB in 0.1 dB steps, or -inf
  --clear RACK.POSITION   take a plug-in out of a rack slot: the slot, its routing and its sidechain key

edit makes only the changes that VENUE 8.2 Standalone loaded with Filing > Load and showed on its own pages. It
refuses everything else, and one refused change stops the whole run:
  - VENUE 8.2 shows from an E6L-192 engine with no snapshots;
  - names on inputs, auxes, groups, matrixes, the mains and VCAs, and faders and colours on the same six kinds,
    inside the E6L-192 counts (192 inputs, 80 auxes, 16 groups, 24 matrixes, 3 mains, 48 VCAs); the mains only in
    an L-R plus Mono show; never FX returns or PQ strips;
  - clearing a slot that is inserted on an input, group or matrix, or is not routed, with no sidechain key, at rack
    positions 1 to 25, while VENUE's current state keeps no copy of it.
No patch, processing, send, snapshot or plug-in setting is ever written. edit writes a new file, never the input. It
writes nothing unless the new file parses, writes back byte for byte, passes every check, holds the values asked
for, and differs from the input only in the records the changes name.

Python 3.8 or later, standard library only. Not affiliated with or endorsed by Avid. No warranty: open every file
this tool writes in VENUE Standalone and save it there before it goes near a console.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import struct
import sys
import zlib

# ---- the container ---------------------------------------------------------------------------------------------------
MAGIC = b'\x0aDigidesign Storage - 1.0\x00'
MAX_BYTES = 64 * 1024 * 1024        # the largest show seen is 15 MB
MAX_DEPTH = 16                      # real shows nest 4 levels
MAX_NODES = 50000                   # the largest show seen holds 10 823 values
MAX_KEY = 256                       # bytes in one key (48 at most seen)
MAX_TOPS = 8
MAX_SNAPSHOT = 16 * 1024 * 1024     # inflated bytes of one snapshot (1.46 MB at most seen)
MAX_SNAPSHOTS_TOTAL = 256 * 1024 * 1024  # inflated bytes of every snapshot in a show (35.8 MB at most seen)
MAX_STRIPS = 512                    # strips in one strip array
MAX_ALL_STRIPS = 1536               # strips in every array together
MAX_SNAPSHOTS = 1000
MAX_TEXT = 64                       # characters of any name read (cut before it is decoded)

T_STR, T_DICT, T_ARR, T_BLOB = 0x0A, 0x0B, 0x0C, 0x0D
T_I32, T_U32, T_I64, T_U64 = 0x06, 0x07, 0x08, 0x09
SCALAR = {0x01: '<B', 0x02: '<b', 0x03: '<B', 0x04: '<h', 0x05: '<H', 0x06: '<i', 0x07: '<I', 0x08: '<q', 0x09: '<Q'}
SIZE = {t: struct.calcsize(f) for t, f in SCALAR.items()}
WORDS = (T_I32, T_U32)

MSG_NOT_DSH = 'This is not a VENUE show file (no "Digidesign Storage - 1.0" at the start).'
MSG_NOT_SHOW = 'This is a VENUE file, but not a show.'
MSG_DAMAGED = 'This file is damaged or in a layout this tool can not read. Open it in VENUE and save it again.'
MSG_TOO_BIG = 'This file is larger than any VENUE show seen, so it was not read.'


class ShowError(Exception):
    """A file or a change this tool will not take, with one plain sentence."""


class Node:
    """One value. t: the type byte. v: an int, bytes (a string or a blob), [(key, Node)] for a dictionary, or
    [Node] for an array. et: an array's element type."""
    __slots__ = ('t', 'v', 'et', 'ix')

    def __init__(self, t, v, et=None):
        self.t, self.v, self.et, self.ix = t, v, et, None

    def get(self, key):
        if self.t != T_DICT:
            return None
        if self.ix is None or len(self.ix) != len(self.v):
            self.ix = {k: i for i, (k, _) in enumerate(self.v)}
        i = self.ix.get(key)
        return self.v[i][1] if i is not None and self.v[i][0] == key else None


class _Reader:
    def __init__(self, d):
        self.d, self.n, self.nodes = d, len(d), 0

    def need(self, i, k):
        if k < 0 or i + k > self.n:
            raise ShowError(MSG_DAMAGED)

    def count(self, at, least):
        """The u32 count at `at`, checked against the bytes left (each entry takes `least` bytes or more)."""
        self.need(at, 4)
        c = struct.unpack_from('<I', self.d, at)[0]
        if c * least > self.n - at - 4:
            raise ShowError(MSG_DAMAGED)
        self.nodes += c
        if self.nodes > MAX_NODES:
            raise ShowError(MSG_DAMAGED)
        return c

    def value(self, i, depth):
        if depth > MAX_DEPTH:
            raise ShowError(MSG_DAMAGED)
        d = self.d
        self.need(i, 1)
        t = d[i]
        i += 1
        if t in SCALAR:
            self.need(i, SIZE[t])
            return Node(t, struct.unpack_from(SCALAR[t], d, i)[0]), i + SIZE[t]
        if t == T_STR:
            j = d.find(b'\0', i)
            if j < 0:
                raise ShowError(MSG_DAMAGED)
            return Node(t, d[i:j]), j + 1
        if t == T_DICT:
            c = self.count(i, 4)
            i += 4
            items, seen = [], set()
            for _ in range(c):
                self.need(i, 1)
                if d[i] != T_STR:
                    raise ShowError(MSG_DAMAGED)
                j = d.find(b'\0', i + 1, i + 2 + MAX_KEY)
                if j < 0:
                    raise ShowError(MSG_DAMAGED)
                key = d[i + 1:j].decode('latin-1')
                if key in seen:
                    raise ShowError(MSG_DAMAGED)
                seen.add(key)
                v, i = self.value(j + 1, depth + 1)
                items.append((key, v))
            return Node(t, items), i
        if t == T_ARR:
            self.need(i, 5)
            et = d[i]
            c = self.count(i + 1, 2)
            i += 5
            items = []
            for _ in range(c):
                v, i = self.value(i, depth + 1)
                if v.t != et:
                    raise ShowError(MSG_DAMAGED)
                items.append(v)
            return Node(t, items, et), i
        if t == T_BLOB:
            self.need(i, 4)
            k = struct.unpack_from('<I', d, i)[0]
            self.need(i + 4, k)
            return Node(t, d[i + 4:i + 4 + k]), i + 4 + k
        raise ShowError(MSG_DAMAGED)


def parse(data):
    """The file -> its top-level values (a show has two dictionaries: the header and the body)."""
    if len(data) > MAX_BYTES:
        raise ShowError(MSG_TOO_BIG)
    if not data.startswith(MAGIC):
        raise ShowError(MSG_NOT_DSH)
    r = _Reader(data)
    i, tops = len(MAGIC), []
    try:
        while i < len(data):
            if len(tops) >= MAX_TOPS:
                raise ShowError(MSG_DAMAGED)
            v, i = r.value(i, 1)
            tops.append(v)
    except (struct.error, IndexError, RecursionError, MemoryError):
        raise ShowError(MSG_DAMAGED)
    if not tops:
        raise ShowError(MSG_DAMAGED)
    return tops


def _write(n, out):
    out.append(bytes((n.t,)))
    if n.t in SCALAR:
        out.append(struct.pack(SCALAR[n.t], n.v))
    elif n.t == T_STR:
        if b'\0' in n.v:
            raise ValueError('a string holds a NUL byte')
        out.append(bytes(n.v) + b'\0')
    elif n.t == T_DICT:
        out.append(struct.pack('<I', len(n.v)))
        for k, v in n.v:
            out.append(b'\x0a' + k.encode('latin-1') + b'\0')
            _write(v, out)
    elif n.t == T_ARR:
        out.append(bytes((n.et,)) + struct.pack('<I', len(n.v)))
        for v in n.v:
            if v.t != n.et:
                raise ValueError('an array element of the wrong type')
            _write(v, out)
    elif n.t == T_BLOB:
        out.append(struct.pack('<I', len(n.v)) + bytes(n.v))
    else:
        raise ValueError('unknown type %r' % n.t)


def serialize(tops):
    out = [MAGIC]
    for n in tops:
        _write(n, out)
    return b''.join(out)


def all_nodes(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if n.t == T_DICT:
            stack.extend(v for _, v in n.v)
        elif n.t == T_ARR:
            stack.extend(n.v)


def key_order_ok(node):
    """VENUE writes every dictionary sorted by value type byte, then by key bytes."""
    for n in all_nodes(node):
        if n.t == T_DICT:
            ks = [(v.t, k.encode('latin-1')) for k, v in n.v]
            if ks != sorted(ks):
                return False
    return True


def _sig(n):
    return (n.t, n.v if n.t not in (T_DICT, T_ARR) else len(n.v))


def _paths(n, p):
    stack = [(n, p)]
    while stack:
        x, q = stack.pop()
        yield q
        if x.t == T_DICT:
            stack.extend((v, q + '/' + k) for k, v in x.v)
        elif x.t == T_ARR:
            stack.extend((v, '%s[%d]' % (q, i)) for i, v in enumerate(x.v))


def diff(a_tops, b_tops):
    """The paths ('1/All Strips/MicLine Strips[0]/Strip') whose value, type or presence differs, sorted."""
    out = set()
    for ti in range(max(len(a_tops), len(b_tops))):
        if ti >= len(a_tops) or ti >= len(b_tops):
            out.add(str(ti))
            continue
        stack = [(a_tops[ti], b_tops[ti], str(ti))]
        while stack:
            a, b, p = stack.pop()
            if a is None or b is None:
                out.update(_paths(a if b is None else b, p))
                continue
            if _sig(a) != _sig(b):
                out.add(p)
            if a.t == T_DICT and b.t == T_DICT:
                for k, av in a.v:
                    stack.append((av, b.get(k), p + '/' + k))
                stack.extend((None, bv, p + '/' + k) for k, bv in b.v if a.get(k) is None)
            elif a.t == T_ARR and b.t == T_ARR:
                for i in range(max(len(a.v), len(b.v))):
                    stack.append((a.v[i] if i < len(a.v) else None, b.v[i] if i < len(b.v) else None,
                                  '%s[%d]' % (p, i)))
            else:
                for n in (a, b):
                    if n.t in (T_DICT, T_ARR):
                        out.update(q for q in _paths(n, p) if q != p)
    return sorted(out)


# ---- strip records ---------------------------------------------------------------------------------------------------
FADER_INF = -1440                   # 0.1 dB units; -1440 is -inf
FADER_TOP = 120                     # +12.0 dB
MAX_NAME = 16                       # VENUE keeps 16 characters of a name
# the colour each number shows as on VENUE 8.2's Overview, measured from its screen
COLOURS = (('grey', (51, 51, 51)), ('green', (21, 171, 21)), ('blue', (21, 21, 171)), ('yellow', (171, 151, 21)),
           ('orange', (153, 84, 35)), ('cyan', (21, 171, 171)), ('purple', (105, 21, 136)), ('red', (171, 21, 21)),
           ('white', (171, 171, 171)))
# where VENUE 8.2 Standalone's screen showed each number; anything else is the same palette by inference
COLOUR_SEEN = {'input': range(9), 'aux': range(9), 'group': range(9), 'matrix': range(9), 'vca': range(9),
               'mains': (0, 1, 2, 7)}
OUT_EQ = (14, 28, 42, 56, 111, 125, 139)    # the seven output EQ bands in AudioMasterStrip
MAINS_ROLES = ('Left', 'Right', 'Mono')


def text(raw, most=MAX_TEXT):
    """Windows-1252 bytes -> text, cut to `most` bytes before decoding."""
    return bytes(raw[:most]).decode('cp1252', 'replace')


def strip_parts(raw):
    """The Strip record: u8 stereo, the name (C string), 5 flag bytes, i32 fader in 0.1 dB, u8, u8 colour number.
    -> {'stereo', 'name', 'name_end', 'fader', 'colour'} or None. name_end is the offset after the name's NUL."""
    if len(raw) < 2:
        return None
    e = raw.find(b'\0', 1)
    if e < 0:
        return None
    n = e + 1
    out = {'stereo': raw[0] == 1, 'name': text(raw[1:min(e, 1 + MAX_TEXT)]), 'name_end': n, 'fader': None,
           'colour': None}
    if len(raw) >= n + 11:
        out['fader'] = struct.unpack_from('<i', raw, n + 5)[0]
        out['colour'] = raw[n + 10]
    return out


def db10(v):
    return '-inf' if v <= FADER_INF else round(v / 10.0, 1)


def eq_band(raw, o):
    on, typ = raw[o], raw[o + 1]
    gain, freq, q = struct.unpack_from('<iii', raw, o + 2)
    return {'on': bool(on), 'type': typ, 'gain_db': round(gain / 10.0, 1), 'freq': freq, 'q': round(q / 100.0, 2)}


def comp_block(raw, o):
    thr, ratio, att, rel, knee, gain = struct.unpack_from('<6i', raw, o)
    return {'thr_db': round(thr / 10.0, 1), 'ratio': round(ratio / 100.0, 2), 'attack_ms': att / 1000.0,
            'release_ms': rel, 'knee': knee, 'gain_db': round(gain / 10.0, 1)}


def gate_block(raw, o):
    thr, ratio, att, rel, hold, rng = struct.unpack_from('<6i', raw, o)
    return {'thr_db': round(thr / 10.0, 1), 'ratio': round(ratio / 100.0, 2), 'attack_ms': att / 1000.0,
            'release_ms': rel, 'hold_ms': hold, 'range_db': round(rng / 10.0, 1)}


def bus_levels(raw, most):
    """BusAssigns: u32 count, then 6-byte entries; bytes 4-5 of an entry are the level in 0.1 dB. -> the first
    `most` levels, or None when the count does not fit the record."""
    if len(raw) < 4:
        return None
    count = struct.unpack_from('<I', raw, 0)[0]
    if 4 + count * 6 != len(raw):
        return None
    return [struct.unpack_from('<h', raw, 4 + 6 * k + 4)[0] for k in range(min(count, most))]


# ---- plug-ins --------------------------------------------------------------------------------------------------------
SLOTS = 400
CHUNK_HEADER = 56
MAX_CHUNKS = 64
MAX_PARAMS = 4096
DEFAULT_MARK = b'\x01\x01\x01\x01'
DEFAULT_IDS = ('elck', 'Infl')      # chunk IDs seen in the AAX SDK default format
NOT_ROUTED = 0x0000000F
SIDECHAIN_EMPTY = 0x10000000
ROUTING_KEYS = ('Effects Main Routing 2', 'Effects Main Routing 3')
SIDECHAIN_KEYS = ('Effects SideChain Routing', 'Effects SideChain Routing 2')
ROUTE_KIND = {1: 'input', 3: 'aux', 4: 'group', 5: 'matrix'}
# the category bits seen in the survey shows (S6L-FORMAT.md 4.1); any other set bit prints as hex
CATEGORY = ((0x1, 'EQ'), (0x2, 'Dynamics'), (0x4, 'Pitch Shift'), (0x8, 'Reverb'), (0x10, 'Delay'),
            (0x20, 'Modulation'), (0x40, 'Harmonic'), (0x80, 'Noise Reduction'), (0x200, 'Sound Field'),
            (0x2000, 'Effect'))
CATEGORY_BITS = sum(bit for bit, _ in CATEGORY)


def categories(word):
    """The category bits of a type entry as words; a bit with no word in CATEGORY prints as hex."""
    out = [w for bit, w in CATEGORY if word & bit]
    rest = word & ~CATEGORY_BITS & 0xFFFFFFFF
    return out + ['0x%X' % (1 << k) for k in range(32) if rest >> k & 1]


class ChunkError(ValueError):
    """A slot record or a chunk that does not walk cleanly: the slot is shown as stored, copy only."""


def fourcc(b):
    """A type ID is a u32 stored little-endian, so its four characters read backwards in the file."""
    return bytes(b[::-1]).decode('latin-1')


def type_hex(ids):
    """The 12 stored ID bytes -> 24 hex digits: manufacturer, product, plug-in ID ('AVID' is 41564944)."""
    return ''.join(bytes(ids[k:k + 4][::-1]).hex() for k in (0, 4, 8))


def split_chunks(buf):
    """Chunk records back to back: i32 size (the 56-byte header counted), i32 version, three type IDs, the chunk ID,
    a 32-byte name, then the data."""
    out, p = [], 0
    while p < len(buf):
        if len(out) >= MAX_CHUNKS or p + CHUNK_HEADER > len(buf):
            raise ChunkError('chunk header past the end')
        size, ver = struct.unpack_from('<Ii', buf, p)
        if size < CHUNK_HEADER or p + size > len(buf):
            raise ChunkError('bad chunk size')
        out.append({'id': fourcc(buf[p + 20:p + 24]), 'version': ver, 'ids': bytes(buf[p + 8:p + 20]),
                    'name': bytes(buf[p + 24:p + 56]).split(b'\0', 1)[0].decode('cp1252', 'replace'),
                    'data': bytes(buf[p + CHUNK_HEADER:p + size])})
        p += size
    return out


def parse_slot(raw):
    """A Rack Assignments record: 12 type ID bytes, two flag bytes, u32 length L, then L bytes of chunks. None for
    an empty slot."""
    if not raw:
        return None
    if len(raw) < 18:
        raise ChunkError('short slot')
    length = struct.unpack_from('<I', raw, 14)[0]
    if 18 + length != len(raw):
        raise ChunkError('slot length does not match')
    return {'ids': bytes(raw[:12]), 'flags': [raw[12], raw[13]], 'length': length, 'chunks': split_chunks(raw[18:])}


def _pad4(i):
    return (i + 3) & ~3


def decode_default(data, most=MAX_PARAMS):
    """The AAX SDK default chunk format: 01 01 01 01, then entries of a type character, '_', the parameter ID, NUL,
    zero pad to a multiple of 4, then the value big-endian ('d' 8 bytes, 'f' and 'l' 4, 's' 2 plus 2 pad, 'r' a
    NUL-terminated string padded to 4). Strict: the entries must fill the data exactly."""
    if len(data) < 4 or data[:4] != DEFAULT_MARK:
        raise ChunkError('not the default format')
    out, i, n = [], 4, len(data)
    while i < n:
        if len(out) >= most:
            raise ChunkError('too many entries')
        j = data.find(b'\0', i, min(n, i + 256))
        if j < 0 or j - i < 3:
            raise ChunkError('entry key')
        key = data[i:j]
        if key[1:2] != b'_' or not all(32 <= c < 127 for c in key):
            raise ChunkError('entry key')
        t = chr(key[0])
        p = _pad4(j + 1)
        if p > n or any(data[j + 1:p]):
            raise ChunkError('entry pad')
        if t in 'dfl':
            size = 8 if t == 'd' else 4
            if p + size > n:
                raise ChunkError('short value')
            v = struct.unpack_from({'d': '>d', 'f': '>f', 'l': '>i'}[t], data, p)[0]
        elif t == 's':
            if p + 4 > n or any(data[p + 2:p + 4]):
                raise ChunkError('short value')
            v, size = struct.unpack_from('>h', data, p)[0], 4
        elif t == 'r':
            k = data.find(b'\0', p, min(n, p + 4096))
            if k < 0:
                raise ChunkError('string value')
            e = _pad4(k + 1)
            if e > n or any(data[k + 1:e]):
                raise ChunkError('string pad')
            v, size = data[p:k].decode('latin-1')[:MAX_TEXT], e - p
        else:
            raise ChunkError('entry type')
        if t in 'df' and v != v:
            raise ChunkError('not a number')
        out.append({'id': key.decode('ascii')[:MAX_TEXT], 'type': t, 'value': v})
        i = p + size
    return out


def parse_type(raw):
    """An Effect Type List entry: name, NUL, family, NUL, 12 type ID bytes, u32 input channels, u32 output channels,
    u32 input stem, u32 output stem, u32 (meaning not known), u32 category bits, then flag bytes."""
    a = raw.find(b'\0')
    c = raw.find(b'\0', a + 1) if a >= 0 else -1
    if a < 0 or c < 0 or c + 13 + 24 > len(raw):
        raise ChunkError('type entry')
    ids = bytes(raw[c + 1:c + 13])
    f = struct.unpack_from('<6I', raw, c + 13)
    return {'ids': ids, 'id': type_hex(ids), 'name': text(raw[:a]), 'family': text(raw[a + 1:c]),
            'inputs': f[0], 'outputs': f[1], 'category': categories(f[5])}


def routing(word):
    """An Effects Main Routing 2 word: 0x0F not routed; else bits 31-26 the type (1 input, 3 aux, 4 group, 5 matrix;
    +0x10 for a bus-fed slot), bits 25-18 the strip index, bits 17-16 a sub field, bits 15-0 the insert position
    (0-based) or, for a bus-fed slot, the return strip (high byte its type, low byte its index)."""
    v = word & 0xFFFFFFFF
    if v == NOT_ROUTED:
        return {'routed': False}
    t, idx, lo = v >> 26, (v >> 18) & 0xFF, v & 0xFFFF
    if t & 0x10:
        src = ROUTE_KIND.get(t & 0xF)
        if not src:
            return {'routed': True, 'undecoded': True}
        rk = ROUTE_KIND.get(lo >> 8) if lo else None
        return {'routed': True, 'bus_fed': True, 'from_kind': src, 'from_index': idx, 'return_kind': rk,
                'return_index': (lo & 0xFF) if rk else None}
    kind = ROUTE_KIND.get(t)
    if not kind or (v >> 16) & 3 or lo > 4:      # insert positions 1 to 5 are the ones VENUE wrote in real shows
        return {'routed': True, 'undecoded': True}
    return {'routed': True, 'kind': kind, 'index': idx, 'position': lo + 1}


def rack_of(slot):
    """Slots 0 to 124 are racks 1 to 5 in blocks of 25. Above 124 the map is not proven."""
    if 0 <= slot < 125:
        return slot // 25 + 1, slot % 25 + 1
    return None, None


# ---- snapshots and VENUE 8 Current State -----------------------------------------------------------------------------
# a plug-in record: u32 slot (1-based), 4 bytes, 'L', u32 length, then chunks. The regex finds an 'L' with a slot
# number under 512 eight bytes before it and twelve printable type ID bytes where the first chunk's IDs sit.
_RECORD = re.compile(rb'L(?<=[\x00\x01]\x00\x00[\x00-\xff]{4}L)(?=[\x00-\xff]{12}[\x20-\x7e]{12})')


class ScanBudget:
    """One show's allowance for the record scan, so a hostile file can not make it slow."""
    def __init__(self):
        self.scan, self.ls, self.cands, self.steps, self.records = 64 << 20, 4 << 20, 50000, 200000, 20000


def inflate(blob, left):
    """One snapshot (a zlib stream) -> (bytes or None, 'ok' | 'cap' | 'total' | 'broken'). Never inflates more than
    MAX_SNAPSHOT, or more than left[0] for the whole show; every attempt is charged to left[0]."""
    if left[0] <= 0:
        return None, 'total'
    limit = min(MAX_SNAPSHOT, left[0])
    d = zlib.decompressobj()
    out, buf = bytearray(), bytes(blob)
    try:
        while True:
            piece = d.decompress(buf, limit + 1 - len(out))
            out += piece
            if len(out) > limit:
                left[0] -= limit + 1
                return None, ('total' if limit < MAX_SNAPSHOT else 'cap')
            buf = d.unconsumed_tail
            if d.eof or not buf:
                break
    except zlib.error:
        left[0] -= len(out) + 1
        return None, 'broken'
    left[0] -= len(out)
    return (bytes(out), 'ok') if d.eof else (None, 'broken')


def snapshot_name(raw):
    """A snapshot starts with u8 0, a u32 length, then its name (C string)."""
    if not raw or len(raw) < 6 or raw[0] != 0:
        return None
    end = raw.find(b'\0', 5, min(len(raw), 5 + 4096))
    return text(raw[5:end]) if end >= 0 else None


def _walks(raw, p, end, budget):
    k = 0
    while p < end:
        budget.steps -= 1
        if budget.steps < 0:
            return None
        if k >= MAX_CHUNKS or p + CHUNK_HEADER > end:
            return False
        size = struct.unpack_from('<I', raw, p)[0]
        if size < CHUNK_HEADER or p + size > end or not all(32 <= c < 127 for c in raw[p + 8:p + 20]):
            return False
        p += size
        k += 1
    return True


def plugin_records(raw, budget):
    """[{'slot': 0-based, 'digest'}] for the plug-in records in a snapshot or Current State, or None when the scan
    allowance ran out (then the blob counts as not read). A record counts only when its chunks walk to the exact end
    and its slot number is 1 to 400."""
    budget.scan -= len(raw)
    budget.ls -= raw.count(b'L')
    if budget.scan < 0 or budget.ls < 0:
        return None
    out, nxt, tried = [], 0, 0
    for m in _RECORD.finditer(raw, 9):
        i = m.start()
        if i < nxt:
            continue
        tried += 1
        budget.cands -= 1
        if tried > 20000 or budget.cands < 0 or len(out) >= 4000:
            return None
        tot, fsize = struct.unpack_from('<II', raw, i + 1)
        if not (CHUNK_HEADER <= fsize <= tot and i + 5 + tot <= len(raw)):
            continue
        slot1 = struct.unpack_from('<I', raw, i - 8)[0]
        if not 1 <= slot1 <= SLOTS:
            continue
        ok = _walks(raw, i + 5, i + 5 + tot, budget)
        if ok is None:
            return None
        if ok:
            budget.records -= 1
            if budget.records < 0:
                return None
            out.append({'slot': slot1 - 1, 'digest': digest(raw[i + 5:i + 5 + tot])})
            nxt = i + 5 + tot
    return out


def digest(buf):
    return hashlib.blake2b(bytes(buf), digest_size=16).digest()


# ---- the show --------------------------------------------------------------------------------------------------------
SHOW_TYPE = b'Digidesign D-Show File'
INPUT_ARRAYS = (('MicLine Strips', 'in', 'input'), ('FX Return Strips', 'fx', 'fx_return'))
OUTPUT_ARRAYS = (('Aux Strips', 'aux', 'aux'), ('Group Strips', 'grp', 'group'),
                 ('Matrix Strips v2.5', 'mtx', 'matrix'), ('LCR Strips', 'mains', 'mains'),
                 ('PQ Strips v2.5', 'pq', 'pq'), ('VCA Strips', 'vca', 'vca'))
ARRAYS = INPUT_ARRAYS + OUTPUT_ARRAYS
PREFIX = {kind: prefix for _, prefix, kind in ARRAYS}
ARRAY_OF = {kind: key for key, _, kind in ARRAYS}
KIND_LABEL = {'input': 'Input', 'fx_return': 'FX Return', 'aux': 'Aux', 'group': 'Group', 'matrix': 'Matrix',
              'mains': 'Mains', 'pq': 'PQ', 'vca': 'VCA'}
KINDS_LABEL = {'input': 'inputs', 'fx_return': 'FX returns', 'aux': 'auxes', 'group': 'groups', 'matrix': 'matrixes',
               'mains': 'the mains', 'pq': 'PQ strips', 'vca': 'VCAs'}
# Main Rack Type: 0, 2, 3 proven on Avid's own demo shows; 4, 5, 7 strong (input and matrix counts match the engine)
ENGINES = {0: ('FOH Rack (D-Show, Profile)', 'proven'), 2: ('SC48', 'proven'), 3: ('E3 (S3L-X)', 'proven'),
           4: ('E6L-144', 'strong'), 5: ('E6L-192', 'strong'), 7: ('E6L-112', 'strong')}
KNOWN_VERSIONS = ('7.0', '7.2', '8.2')
# how sure each read is: proven (a VENUE load or a public format source matched it), strong (the data fits, no
# controlled test), none (not read)
READ = {'names': 'proven', 'faders': 'proven', 'colours': 'proven', 'stereo': 'strong', 'patch': 'strong',
        'hpf': 'strong', 'eq': 'strong', 'comp': 'strong', 'gate': 'strong', 'sends': 'strong',
        'snapshots': 'strong', 'plugins': 'proven', 'plugin_params': 'proven', 'vca_members': 'none',
        'preamps': 'none', 'output_patch': 'none', 'mutes': 'none'}


def vword(v):
    """A version word: bytes low to high 01, x, minor, major -> (major, minor)."""
    b = (v & 0xFFFFFFFF).to_bytes(4, 'little')
    return b[3], b[2]


class Show:
    def __init__(self, data):
        data = bytes(data)
        if not data.startswith(MAGIC):
            raise ShowError(MSG_NOT_DSH)
        self.raw = data
        self.tops = parse(data)
        if len(self.tops) < 2 or self.tops[0].t != T_DICT or self.tops[1].t != T_DICT:
            raise ShowError(MSG_DAMAGED)
        self.h, self.b = self.tops[0], self.tops[1]
        ft = self.h.get('File Type')
        ftv = ft.v if ft is not None and ft.t == T_STR else b''
        if b'Scope Set' in ftv:
            raise ShowError('This is a VENUE scope set, not a show.')
        if ftv != SHOW_TYPE:
            raise ShowError(MSG_NOT_SHOW)
        total = 0
        for key, _, _ in ARRAYS:
            total += len(self.arr(key))
            if len(self.arr(key)) > MAX_STRIPS or total > MAX_ALL_STRIPS:
                raise ShowError(MSG_TOO_BIG)
        if self.snapshot_count() > MAX_SNAPSHOTS:
            raise ShowError(MSG_TOO_BIG)
        self._snaps = self._current = self._catalog = self._racknames = None
        self.warnings = []

    # ---- header ----
    def hv(self, key, types=None, most=MAX_TEXT):
        n = self.h.get(key)
        if n is None or (types and n.t not in types):
            return None
        return text(n.v, most) if n.t == T_STR else n.v

    @property
    def version(self):
        v = self.hv('Full Support SW Version', WORDS)
        return '%d.%d' % vword(v) if v is not None else None

    @property
    def major(self):
        v = self.hv('Full Support SW Version', WORDS)
        return vword(v)[0] if v is not None else None

    @property
    def rack_type(self):
        return self.hv('Main Rack Type', (T_I32,))

    @property
    def console_type(self):
        dc = self.b.get('Devices Configuration')
        n = dc.get('Console Type') if dc is not None else None
        return n.v if n is not None and n.t in SCALAR else None

    @property
    def family(self):
        rack, ct, major = self.rack_type, self.console_type, self.major
        if rack == 3 or ct == 4:
            return 's3l'
        if major is not None and major >= 5 and rack not in (0, 2):
            return 's6l'
        return 'classic'

    @property
    def mains_mode(self):
        """'lr_mono' when the header's 'LCR not LRM' is 0 (L-R plus Mono), 'lcr' for any other number, None."""
        v = self.hv('LCR not LRM', tuple(SCALAR))
        return None if v is None else 'lr_mono' if v == 0 else 'lcr'

    # ---- strips ----
    def arr(self, key):
        a = self.b.get('All Strips')
        n = a.get(key) if a is not None else None
        return n.v if n is not None and n.t == T_ARR else []

    def record(self, kind, i, name):
        a = self.arr(ARRAY_OF[kind])
        if i >= len(a) or a[i].t != T_DICT:
            return None
        n = a[i].get(name)
        return n if n is not None and n.t == T_BLOB else None

    def strip_label(self, kind, i):
        st = self.record(kind, i, 'Strip')
        p = strip_parts(st.v) if st is not None else None
        base = '%s %d (%s%d)' % (KIND_LABEL[kind], i + 1, PREFIX[kind], i + 1)
        return '"%s", %s' % (p['name'], base) if p and p['name'] else base

    # ---- plug-ins ----
    def catalog(self):
        if self._catalog is None:
            pb = self.b.get('Plug-In PatchBay')
            etl = pb.get('Effect Type List') if pb is not None else None
            out = []
            for n in (etl.v if etl is not None and etl.t == T_ARR else [])[:4096]:
                if n.t == T_BLOB:
                    try:
                        out.append(parse_type(n.v))
                    except ChunkError:
                        pass
            self._catalog = out
        return self._catalog

    def rack_slots(self):
        pb = self.b.get('Plug-In PatchBay')
        ra = pb.get('Rack Assignments') if pb is not None else None
        return ra.v if ra is not None and ra.t == T_ARR else []

    def words(self, key='Effects Main Routing 2'):
        r = self.b.get(key)
        if r is None or r.t != T_ARR or r.et not in WORDS:
            return []
        return [n.v for n in r.v]

    def rack_names(self):
        if self._racknames is None:
            co = self.b.get('Console Options')
            rn = co.get('Rack Column Names') if co is not None else None
            names = []
            if rn is not None and rn.t == T_BLOB:
                v, p = rn.v, 0
                while len(names) < 5 and p <= len(v):
                    e = v.find(b'\0', p)
                    e = len(v) if e < 0 else e
                    names.append(text(v[p:min(e, p + MAX_TEXT)]))
                    p = e + 1
            self._racknames = [names[k] if k < len(names) and names[k] else 'Rack %d' % (k + 1) for k in range(5)]
        return self._racknames

    def slot_label(self, slot):
        rack, pos = rack_of(slot)
        if rack is None:
            return 'slot index %d (past rack position 25)' % slot
        return 'rack %d "%s", position %d (%d.%d)' % (rack, self.rack_names()[rack - 1], pos, rack, pos)

    def has_strip(self, kind, i):
        return 0 <= i < len(self.arr(ARRAY_OF[kind]))

    # ---- snapshots ----
    def snapshot_count(self):
        lst = self.b.get('Snapshot List Compressed')
        if lst is None:
            return 0
        return len(lst.v) if lst.t == T_ARR else 1

    def snapshots(self):
        """[{'n', 'name', 'read', 'records'}]; also reads VENUE 8 Current State into self._current ([] when there is
        none, None when it could not be read in full)."""
        if self._snaps is None:
            lst = self.b.get('Snapshot List Compressed')
            left, budget, out = [MAX_SNAPSHOTS_TOTAL], ScanBudget(), []
            for k, n in enumerate(lst.v if lst is not None and lst.t == T_ARR else []):
                raw, why = inflate(n.v, left) if n.t == T_BLOB else (None, 'broken')
                recs = plugin_records(raw, budget) if raw else None
                name = snapshot_name(raw) if raw else None
                if raw is None:
                    self.warnings.append('Snapshot %d %s, so it is listed without its contents.' % (
                        k + 1, 'is larger than any seen' if why in ('cap', 'total') else 'could not be read'))
                out.append({'n': k + 1, 'name': name if name is not None else 'Snapshot %d' % (k + 1),
                            'read': recs is not None, 'records': recs or []})
            cs = self.b.get('Current State')
            if cs is None:
                self._current = []
            else:
                self._current = plugin_records(cs.v, budget) if cs.t == T_BLOB else None
            self._snaps = out
        return self._snaps

    def current_records(self):
        self.snapshots()
        return self._current


# ---- the read model --------------------------------------------------------------------------------------------------
def colour_of(sh, kind, index):
    if index is None:
        return None
    seen = sh.version == '8.2' and index in COLOUR_SEEN.get(kind, ())
    name, rgb = COLOURS[index] if 0 <= index < len(COLOURS) else (None, None)
    return {'index': index, 'name': name, 'hex': '#%02x%02x%02x' % rgb if rgb else None,
            'sure': 'proven' if seen else 'strong'}


def strip_model(sh, kind, i, node, inserts, n_aux):
    def rec(name):
        n = node.get(name)
        return n.v if n is not None and n.t == T_BLOB else None
    st = strip_parts(rec('Strip') or b'')
    sid = '%s%d' % (PREFIX[kind], i + 1)
    m = {'id': sid, 'kind': kind, 'n': i + 1, 'name': st['name'] if st else '', 'stereo': bool(st and st['stereo']),
         'colour': colour_of(sh, kind, st['colour']) if st else None,
         'fader_db': db10(st['fader']) if st and st['fader'] is not None else None}
    if kind == 'mains' and i < 3 and sh.mains_mode == 'lr_mono':
        m['role'] = MAINS_ROLES[i]
    if kind == 'vca':
        return m
    m.update({'patch': None, 'hpf': None, 'eq': None, 'comp': None, 'gate': None, 'sends': [],
              'inserts': inserts.get(sid, [])})
    inp, ml, am, ba = rec('InputStrip'), rec('MicLineInputStrip'), rec('AudioMasterStrip'), rec('BusAssigns')
    if inp is not None and len(inp) >= 90:
        m['patch'] = {'port': inp[88], 'device_code': inp[89]}
        m['eq'] = [dict(band=4 - k, **eq_band(inp, 24 + 14 * k)) for k in range(4)]
    if ml is not None and len(ml) >= 72:
        m['hpf'] = {'freq': struct.unpack_from('<i', ml, 1)[0]}
        m['comp'] = comp_block(ml, 7)
        m['gate'] = gate_block(ml, 48)
    if am is not None and len(am) >= 153:
        m['eq'] = [dict(band=k + 1, **eq_band(am, o)) for k, o in enumerate(OUT_EQ)]
        m['comp'] = comp_block(am, 71)
    if ba is not None:
        # entries past the auxes belong to the groups; VENUE rewrites their level bytes on every save, so they are
        # not read as send levels
        for k, lv in enumerate(bus_levels(ba, n_aux) or ()):
            if lv > FADER_INF:
                m['sends'].append({'bus': 'aux%d' % (k + 1), 'level_db': db10(lv)})
    return m


def plugin_model(sh, gate):
    by_ids = {}
    for t in sh.catalog():
        by_ids.setdefault(t['ids'], t)
    words = sh.words()
    copies = {}
    for s in sh.snapshots():
        for r in s['records']:
            copies.setdefault(r['slot'], {}).setdefault(s['n'], []).append(r['digest'])
    current = sh.current_records()
    slots, inserts = [], {}
    for idx, n in enumerate(sh.rack_slots()[:SLOTS]):
        if n.t != T_BLOB or not n.v:
            continue
        rack, pos = rack_of(idx)
        rec = {'slot': idx, 'at': '%d.%d' % (rack, pos) if rack else None, 'rack': rack, 'position': pos,
               'type': None, 'state': 'stored', 'format': None, 'bytes': len(n.v), 'flags': None, 'params': None,
               'insert': None, 'snapshot_copies': [], 'current_state_copy': None}
        try:
            s = parse_slot(n.v)
        except ChunkError:
            s = None
            rec['state'] = 'stored, copy only'
        if s is not None:
            t = by_ids.get(s['ids'])
            rec['type'] = ({k: t[k] for k in ('name', 'family', 'id', 'category', 'inputs', 'outputs')} if t else
                           {'name': None, 'family': None, 'id': type_hex(s['ids']), 'category': [], 'inputs': None,
                            'outputs': None})
            rec['flags'], rec['bytes'] = s['flags'], s['length']
            if not s['chunks']:
                rec['state'] = 'empty'
            else:
                rec['format'] = s['chunks'][0]['id']
                params = []
                for c in s['chunks']:
                    if c['id'] not in DEFAULT_IDS:
                        continue
                    try:
                        params.extend(decode_default(c['data']))
                    except ChunkError:
                        params = None
                        break
                if params:
                    rec['state'], rec['params'] = 'readable', params
            body = digest(n.v[18:])
            rec['snapshot_copies'] = [{'snapshot': sn, 'same': all(d == body for d in ds)}
                                      for sn, ds in sorted(copies.get(idx, {}).items())]
            if current is None:
                rec['current_state_copy'] = None
            else:
                held = [r for r in current if r['slot'] == idx]
                rec['current_state_copy'] = ({'same': all(r['digest'] == body for r in held)} if held else False)
        if idx < len(words):
            r = routing(words[idx])
            if r.get('kind'):
                kind, i = r['kind'], r['index']
                if sh.has_strip(kind, i):
                    sid = '%s%d' % (PREFIX[kind], i + 1)
                    rec['insert'] = {'strip': sid, 'position': r['position']}
                    inserts.setdefault(sid, []).append({'position': r['position'], 'slot': idx, 'at': rec['at']})
            elif r.get('bus_fed'):
                src = (r['from_kind'], r['from_index'])
                ret = (r['return_kind'], r['return_index']) if r.get('return_kind') else None
                rec['insert'] = {'bus_fed': True,
                                 'from': '%s%d' % (PREFIX[src[0]], src[1] + 1) if sh.has_strip(*src) else None,
                                 'return': '%s%d' % (PREFIX[ret[0]], ret[1] + 1) if ret and sh.has_strip(*ret)
                                 else None}
            elif r.get('undecoded'):
                rec['insert'] = {'undecoded': True}
        why = clear_refusal(sh, idx, gate)
        rec['clear'] = {'ok': why is None, 'why': why}
        slots.append(rec)
    names = sh.rack_names()
    racks = [{'n': k + 1, 'name': names[k]} for k in range(5)]
    types = [{k: t[k] for k in ('id', 'name', 'family', 'inputs', 'outputs', 'category')} for t in sh.catalog()]
    return {'racks': racks, 'slots': slots, 'types': types}, inserts


def filetime(q):
    if not isinstance(q, int) or not q:
        return None
    import datetime
    try:
        t = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=q // 10)
    except (OverflowError, ValueError):
        return None
    return t.strftime('%Y-%m-%dT%H:%M:%SZ') if 2000 <= t.year <= 2100 else None


def model(sh, name='Show.dsh'):
    fam, fmt = sh.family, sh.version or '?'
    lka = sh.hv('Last Known As', (T_STR,)) or ''
    partial = sh.hv('Partial Support SW Version', WORDS)
    rack = sh.rack_type
    gate = edit_gate(sh)
    out = {
        'file': {'name': name, 'bytes': len(sh.raw)},
        'show': {'family': fam, 'created_by': sh.hv('File Created by', (T_STR,)) or '', 'version': fmt,
                 'partial_support': '%d.%d' % vword(partial) if partial is not None else None,
                 'saved_on': ('console' if lka.upper().startswith('D:\\D-SHOW\\') else
                              'standalone' if lka.upper().startswith('C:\\USERS\\') else None),
                 'comment': sh.hv('User Comment', (T_STR,), 256) or '',
                 'last_load': filetime(sh.hv('Last Load Time', (T_U64, T_I64))),
                 'version_known': fmt in KNOWN_VERSIONS, 'mains': sh.mains_mode},
        'engine': {'rack_type': rack, 'name': ENGINES.get(rack, (None, None))[0],
                   'sure': ENGINES.get(rack, (None, None))[1], 'inputs': sh.hv('Channel Count', (T_I32,)),
                   'dsp_cards': sh.hv('DSP Card count', (T_I32,))},
        'surface': {'console_type': sh.console_type, 'name': None},
        'sample_rate': sh.hv('Sample Rate', (T_I32,)),
        'counts': {'inputs': len(sh.arr('MicLine Strips')), 'fx_returns': len(sh.arr('FX Return Strips')),
                   'aux': len(sh.arr('Aux Strips')), 'groups': len(sh.arr('Group Strips')),
                   'matrix': len(sh.arr('Matrix Strips v2.5')), 'mains': len(sh.arr('LCR Strips')),
                   'vca': len(sh.arr('VCA Strips')), 'snapshots': sh.snapshot_count(),
                   'plugins_used': sum(1 for n in sh.rack_slots() if n.t == T_BLOB and n.v),
                   'plugin_types': len(sh.catalog())},
        'read': dict(READ, colours='proven' if fmt == '8.2' else 'strong') if fam == 's6l' else {},
        'inputs': [], 'outputs': [], 'snapshots': [], 'plugins': {'racks': [], 'slots': [], 'types': []},
        'edit': {'open': gate is None, 'why': gate},
        'warnings': [],
    }
    if fam != 's6l':
        out['warnings'].append({'classic': 'This is a classic VENUE show (D-Show, Profile or SC48). It is read here '
                                           'as a summary only.',
                                's3l': 'This is an S3L-X show. It is read here as a summary only.'}[fam])
        return out
    if fmt not in KNOWN_VERSIONS:
        out['warnings'].append('Made by %s. The shows checked so far are VENUE 7.0, 7.2 and 8.2.' %
                               (out['show']['created_by'] or 'VENUE ' + fmt))
    n_aux = min(len(sh.arr('Aux Strips')), 128)
    out['plugins'], inserts = plugin_model(sh, gate)
    for group, arrays in (('inputs', INPUT_ARRAYS), ('outputs', OUTPUT_ARRAYS)):
        for key, _, kind in arrays:
            for i, node in enumerate(sh.arr(key)):
                if node.t == T_DICT:
                    out[group].append(strip_model(sh, kind, i, node, inserts, n_aux))
    out['snapshots'] = [{'n': s['n'], 'name': s['name'], 'read': s['read'],
                         'plugin_copies': len({r['slot'] for r in s['records']}) if s['read'] else None}
                        for s in sh.snapshots()]
    out['warnings'].extend(sh.warnings)
    return out


# ---- checks ----------------------------------------------------------------------------------------------------------
def strip_value_problem(raw):
    """What VENUE would rewrite in a Strip record, in words, or None."""
    p = strip_parts(raw)
    if not p or p['fader'] is None:
        return 'nothing that can be read'
    nb = raw[1:p['name_end'] - 1]
    if len(nb) > MAX_NAME:
        return 'a name over %d characters' % MAX_NAME
    if any(c < 32 or c == 127 for c in nb):
        return 'a control character in its name'
    if not 0 <= p['colour'] <= 8:
        return 'a colour number outside 0 to 8'
    if not FADER_INF <= p['fader'] <= FADER_TOP:
        return 'a fader level outside -inf to +12 dB'
    return None


def structure(sh):
    """Problems in a parsed show, as sentences ([] when there are none)."""
    out = []
    if not all(key_order_ok(n) for n in sh.tops):
        out.append('A dictionary is out of VENUE order.')
    if sh.family != 's6l':
        return out
    for key, _, kind in ARRAYS:
        for i, node in enumerate(sh.arr(key)):
            if node.t != T_DICT:
                out.append('%s %d is not a dictionary.' % (KIND_LABEL[kind], i + 1))
                continue
            st = node.get('Strip')
            bad = strip_value_problem(st.v) if st is not None and st.t == T_BLOB else 'no Strip record'
            if bad:
                out.append('%s %d holds %s.' % (KIND_LABEL[kind], i + 1, bad))
            ba = node.get('BusAssigns')
            if ba is not None and (ba.t != T_BLOB or bus_levels(ba.v, 0) is None):
                out.append('%s %d has a send list that does not fit.' % (KIND_LABEL[kind], i + 1))
    slots = sh.rack_slots()
    if len(slots) != SLOTS:
        out.append('The plug-in racks do not hold 400 slots.')
    words = sh.words()
    if words and len(words) != SLOTS:
        out.append('The plug-in routing does not hold 400 slots.')
    for key in ROUTING_KEYS:
        r = sh.b.get(key)
        if r is not None and (r.t != T_ARR or r.et not in WORDS):
            out.append('The plug-in routing is not a list of numbers.')
    r3 = sh.b.get('Effects Main Routing 3')
    if r3 is not None and r3.t == T_ARR and [n.v for n in r3.v] != words:
        out.append('The two copies of the plug-in routing differ.')
    known = {t['ids'] for t in sh.catalog()}
    for i, n in enumerate(slots[:SLOTS]):
        if n.t != T_BLOB:
            out.append('Rack slot index %d is not a blob.' % i)
            continue
        try:
            s = parse_slot(n.v)
        except ChunkError:
            out.append('Rack slot index %d does not walk to its end.' % i)
            continue
        if s is None:
            continue
        if s['ids'] not in known:
            out.append('Rack slot index %d holds a plug-in that is not in the show\'s plug-in list.' % i)
        if i < len(words):
            r = routing(words[i])
            if r.get('kind') and not sh.has_strip(r['kind'], r['index']):
                out.append('Rack slot index %d is routed to a strip the show does not have.' % i)
    return out


def checks(sh):
    """[(ok, sentence)] for the check command."""
    same = serialize(sh.tops) == sh.raw
    probs = structure(sh)
    out = [(same, 'The file reads to its last byte and writes back identical.'),
           (not any('order' in p for p in probs), 'Every dictionary keeps VENUE\'s key order.')]
    if sh.family == 's6l':
        used = sum(1 for n in sh.rack_slots() if n.t == T_BLOB and n.v)
        out.append((not any('Rack slot' in p or 'racks' in p for p in probs),
                    'Every used rack slot walks to its end and is in the plug-in list (%d used).' % used))
        out.append((not any('routing' in p or 'routed' in p for p in probs),
                    'The plug-in routing holds 400 words, both copies agree, every insert names a strip.'))
        out.append((not any(' holds ' in p or 'send list' in p or 'dictionary.' in p for p in probs),
                    'Every strip record reads, with values VENUE keeps.'))
    return out, probs


# ---- the gate: what edit may change ----------------------------------------------------------------------------------
PROVEN_VERSION = '8.2'
PROVEN_ENGINE = 5                   # E6L-192, the engine VENUE Standalone simulates
LIMITS = {'input': 192, 'aux': 80, 'group': 16, 'matrix': 24, 'mains': 3, 'vca': 48}
STRIP_KINDS = ('input', 'aux', 'group', 'matrix', 'mains', 'vca')
CLEAR_KINDS = ('input', 'group', 'matrix', 'none')


def edit_gate(sh):
    """None when edit may change this show at all, else the sentence that says why not."""
    fam = sh.family
    if fam == 'classic':
        return ('This is a classic VENUE show (D-Show, Profile or SC48). s6l_tool.py only reads it. '
                'See dshow_tool.py and FORMAT.md.')
    if fam == 's3l':
        return 'This is an S3L-X show. s6l_tool.py only reads it.'
    v = sh.version
    if v != PROVEN_VERSION:
        if v in ('7.0', '7.2'):
            return ('VENUE %s shows are read-only here: no VENUE %s Standalone has loaded a file this tool wrote. If '
                    'your console runs VENUE 8.2, load the show in VENUE 8.2 Standalone, save it, and edit that '
                    'save (the show then needs VENUE 8.2).' % (v, v))
        return 'VENUE %s shows are read-only here. Only VENUE 8.2 shows have been load-tested.' % v
    if sh.rack_type != PROVEN_ENGINE:
        name = ENGINES.get(sh.rack_type, ('engine type %s' % sh.rack_type, None))[0]
        return ('Changes are load-tested on E6L-192 shows only, and this show is for %s. It is read-only here.'
                % name)
    if sh.snapshot_count():
        return ('This show has snapshots. Until the snapshot record is decoded, every snapshot may keep its own copy '
                'of a strip or a rack slot, so the show is read-only here.')
    return None


def strip_refusal(sh, what, kind, i):
    """None when `what` ('name', 'fader', 'colour') may change on strip kind/i, else the sentence."""
    if kind not in STRIP_KINDS:
        return 'Changing %s on %s waits for a load test in VENUE Standalone.' % (
            'names' if what == 'name' else what + 's', KINDS_LABEL[kind])
    if i >= LIMITS[kind]:
        return 'Changing %s past %s %d waits for a load test in VENUE Standalone.' % (
            'names' if what == 'name' else what + 's', KIND_LABEL[kind].lower(), LIMITS[kind])
    if kind == 'mains' and sh.mains_mode != 'lr_mono':
        return ("This show's mains are L-C-R (or the layout could not be read). Changing the mains waits for a load "
                'test of such a show in VENUE Standalone.')
    return None


def clear_kind(sh, slot):
    """How a slot is routed, as the clear gate sees it: 'none', 'input', 'aux', 'group', 'matrix', 'bus_fed',
    'undecoded', 'unplaced' (past position 25), or 'keyed_<kind>' when a sidechain key is set."""
    if rack_of(slot)[0] is None:
        return 'unplaced'
    words = sh.words()
    if slot >= len(words):
        return 'undecoded'
    r = routing(words[slot])
    if not r.get('routed'):
        kind = 'none'
    elif r.get('kind'):
        kind = r['kind']
        if not sh.has_strip(kind, r['index']):
            return 'undecoded'
    else:
        return 'bus_fed' if r.get('bus_fed') else 'undecoded'
    r3 = sh.b.get('Effects Main Routing 3')
    if r3 is not None and (r3.t != T_ARR or r3.et not in WORDS or len(r3.v) != len(words) or
                           r3.v[slot].v != words[slot]):
        return 'undecoded'
    keyed = False
    for key in SIDECHAIN_KEYS:
        n = sh.b.get(key)
        if n is None:
            continue
        if n.t != T_ARR or n.et not in WORDS or len(n.v) != SLOTS:
            return 'undecoded'
        if n.v[slot].v != SIDECHAIN_EMPTY:
            keyed = True
    return 'keyed_' + kind if keyed else kind


CLEAR_WHY = {
    'unplaced': 'sits past position 25 of its rack, where the slot map is not proven',
    'bus_fed': 'is fed from a bus; clearing one made VENUE rewrite the input that takes its return',
    'undecoded': 'is routed in a way this tool can not read',
    'aux': 'is inserted on an aux; clearing an aux insert is not load-tested on VENUE 8.2',
    'keyed': 'has a sidechain key; clearing a keyed slot is not load-tested on VENUE 8.2',
}


def clear_refusal(sh, slot, gate):
    """None when the slot can be cleared now, else the sentence."""
    if gate:
        return gate
    ra = sh.rack_slots()
    if len(ra) != SLOTS or not 0 <= slot < SLOTS or ra[slot].t != T_BLOB:
        return 'This show has plug-in racks this tool can not read.'
    where = sh.slot_label(slot)
    if not ra[slot].v:
        return 'The slot at %s is already empty.' % where
    kind = clear_kind(sh, slot)
    if kind not in CLEAR_KINDS:
        why = CLEAR_WHY['keyed'] if kind.startswith('keyed_') else CLEAR_WHY.get(kind, 'can not be cleared here')
        return 'The plug-in at %s %s. Clear it in VENUE.' % (where, why)
    cur = sh.current_records()
    if cur is None:
        return "VENUE's current state in this show could not be read in full, so the slot at %s stays." % where
    if any(r['slot'] == slot for r in cur):
        return "VENUE's current state keeps a copy of the slot at %s, so it stays. Clear it in VENUE." % where
    return None


# ---- edit ------------------------------------------------------------------------------------------------------------
FOLD = str.maketrans({'\u2018': "'", '\u2019': "'", '\u201a': "'", '\u201c': '"', '\u201d': '"', '\u201e': '"',
                      '\u2013': '-', '\u2014': '-', '\u2026': '...'})


def clean_name(v):
    """A name as VENUE keeps it -> (text, bytes); ShowError when it can not be kept."""
    v = ' '.join(v.translate(FOLD).split())
    if not v:
        raise ShowError('Type a name.')
    if len(v) > MAX_NAME:
        raise ShowError('Names on S6L hold %d characters. "%s" is %d.' % (MAX_NAME, v, len(v)))
    try:
        b = v.encode('cp1252')
    except UnicodeEncodeError:
        raise ShowError('"%s" has a character VENUE can not show. Use plain letters, numbers and punctuation.' % v)
    if any(c < 32 or c == 127 for c in b):
        raise ShowError('Names can not hold control characters.')
    if any(0x80 <= c <= 0x9F for c in b):
        raise ShowError('"%s" has a character no VENUE load test has kept yet. Use plain letters, numbers and '
                        'punctuation.' % v)
    return v, b


ID_RE = re.compile(r'^(in|ch|fx|aux|grp|mtx|mains|pq|vca)?(\d+)$', re.I)
KIND_OF = {'in': 'input', 'ch': 'input', 'fx': 'fx_return', 'aux': 'aux', 'grp': 'group', 'mtx': 'matrix',
           'mains': 'mains', 'pq': 'pq', 'vca': 'vca'}


def strip_of(sh, sid):
    m = ID_RE.match(sid.strip())
    if not m or int(m.group(2)) < 1:
        raise ShowError('"%s" is not a strip id. Use in1, aux1, grp1, mtx1, mains1, vca1, fx1 or pq1.' % sid)
    kind, i = KIND_OF[(m.group(1) or 'in').lower()], int(m.group(2)) - 1
    if not sh.has_strip(kind, i):
        raise ShowError('This show has no %s %d.' % (KIND_LABEL[kind].lower(), i + 1))
    return kind, i


def slot_of(text_):
    m = re.match(r'^\s*([1-5])\.(\d+)\s*$', text_)
    if not m or not 1 <= int(m.group(2)) <= 25:
        raise ShowError('"%s" is not a rack slot. Use RACK.POSITION, racks 1 to 5, positions 1 to 25.' % text_)
    return (int(m.group(1)) - 1) * 25 + int(m.group(2)) - 1


def colour_number(v):
    v = v.strip().lower()
    names = [n for n, _ in COLOURS]
    if v in names:
        return names.index(v)
    if v.isdigit() and 0 <= int(v) <= 8:
        return int(v)
    raise ShowError('"%s" is not a VENUE colour. Use 0 to 8 or %s.' % (v, ', '.join(names)))


def fader_tenths(v):
    s = v.strip().lower().replace('db', '').strip()
    if s in ('-inf', 'inf', 'off'):
        return FADER_INF
    try:
        f = float(s)
    except ValueError:
        raise ShowError('"%s" is not a fader level. Use a number of dB or -inf.' % v)
    if f != f:
        raise ShowError('"%s" is not a fader level.' % v)
    if f > FADER_TOP / 10.0:
        raise ShowError('Faders go up to +12 dB on S6L.')
    return FADER_INF if f <= -144 else int(round(f * 10))


def names_from(path):
    """[(input number, name)] from a .csv with a Name column (and maybe Ch), or a text file of one name a line."""
    with open(path, encoding='utf-8-sig', newline='') as f:
        body = f.read()
    out = []
    if path.lower().endswith('.csv'):
        rows = list(csv.reader(body.splitlines()))
        if not rows:
            return out
        head = [h.strip().lower() for h in rows[0]]
        name_col = next((k for k, h in enumerate(head) if h in ('name', 'channel name', 'ch name', 'input name')), None)
        ch_col = next((k for k, h in enumerate(head) if h in ('ch', 'channel', 'input', '#', 'ch#')), None)
        if name_col is None:
            raise ShowError('%s has no Name column.' % os.path.basename(path))
        for k, row in enumerate(rows[1:]):
            name = row[name_col].strip() if name_col < len(row) else ''
            if not name:
                continue
            n = k + 1
            if ch_col is not None and ch_col < len(row) and row[ch_col].strip():
                try:
                    n = int(row[ch_col].strip())
                except ValueError:
                    raise ShowError('Row %d: "%s" is not an input number.' % (k + 2, row[ch_col].strip()))
            out.append((n, name))
    else:
        for k, line in enumerate(body.splitlines()):
            if line.strip():
                out.append((k + 1, line.strip()))
    return out


def make_edits(data, changes):
    """changes: [('name', sid, text) | ('colour', sid, n) | ('fader', sid, tenths) | ('clear', slot)].
    -> (new bytes, [what changed]). ShowError with every refusal joined when any change can not be made."""
    sh = Show(data)
    gate = edit_gate(sh)
    if gate:
        raise ShowError(gate)
    said, refused, allowed, expect = [], [], set(), {}
    for ch in changes:
        try:
            if ch[0] == 'clear':
                slot = ch[1]
                why = clear_refusal(sh, slot, None)
                if why:
                    raise ShowError(why)
                ra = sh.rack_slots()
                ra[slot].v = b''
                allowed.add('1/Plug-In PatchBay/Rack Assignments[%d]' % slot)
                for key in ROUTING_KEYS + SIDECHAIN_KEYS:
                    n = sh.b.get(key)
                    if n is None:
                        continue
                    n.v[slot].v = NOT_ROUTED if key in ROUTING_KEYS else SIDECHAIN_EMPTY
                    allowed.add('1/%s[%d]' % (key, slot))
                said.append('The slot at %s is empty now, not routed, with no sidechain key.' % sh.slot_label(slot))
                expect[('slot', slot)] = True
                continue
            what, sid, value = ch
            kind, i = strip_of(sh, sid)
            why = strip_refusal(sh, what, kind, i)
            if why:
                raise ShowError(why)
            n = sh.record(kind, i, 'Strip')
            p = strip_parts(n.v) if n is not None else None
            if p is None or p['fader'] is None:
                raise ShowError('%s has a strip record this tool can not read.' % sh.strip_label(kind, i))
            label = sh.strip_label(kind, i)
            if what == 'name':
                t, b = clean_name(value)
                n.v = n.v[:1] + b + n.v[p['name_end'] - 1:]
                said.append('%s is now "%s".' % (label, t))
            elif what == 'colour':
                b = bytearray(n.v)
                b[p['name_end'] + 10] = value
                n.v = bytes(b)
                said.append('%s colour %d (%s).' % (label, value, COLOURS[value][0]))
            elif what == 'fader':
                b = bytearray(n.v)
                struct.pack_into('<i', b, p['name_end'] + 5, value)
                n.v = bytes(b)
                said.append('%s fader %s.' % (label, '-inf' if value <= FADER_INF else '%+.1f dB' % (value / 10.0)))
            expect[(kind, i, what)] = value
            allowed.add('1/All Strips/%s[%d]/Strip' % (ARRAY_OF[kind], i))
        except ShowError as e:
            refused.append(str(e))
    if refused:
        raise ShowError('Nothing was written:\n  ' + '\n  '.join(refused))
    new = serialize(sh.tops)
    problems = verify(data, new, allowed, expect)
    if problems:
        raise ShowError('The changed show did not pass the checks, so nothing was written:\n  ' +
                        '\n  '.join(problems))
    return new, said


def verify(old_data, new_data, allowed, expect):
    """[] when the written show parses, writes back byte for byte, passes structure(), changed only the allowed
    records (a Strip record only in its name, fader and colour bytes) and holds the values asked for."""
    try:
        old, new = Show(old_data), Show(new_data)
    except ShowError as e:
        return [str(e)]
    probs = []
    if serialize(new.tops) != new_data:
        probs.append('The written show does not write back byte for byte.')
    probs.extend(structure(new))
    for path in diff(old.tops, new.tops):
        if path not in allowed:
            probs.append('A part of the show that no change names would change: %s' % path)
            continue
        m = re.match(r'^1/All Strips/(.+)\[(\d+)\]/Strip$', path)
        if m:
            a = old.b.get('All Strips').get(m.group(1)).v[int(m.group(2))].get('Strip').v
            b = new.b.get('All Strips').get(m.group(1)).v[int(m.group(2))].get('Strip').v
            pa, pb = strip_parts(a), strip_parts(b)
            ea, eb = pa['name_end'], pb['name_end']
            if a[0] != b[0] or a[ea:ea + 5] != b[eb:eb + 5] or a[ea + 9] != b[eb + 9] or a[ea + 11:] != b[eb + 11:]:
                probs.append('A strip record would change outside its name, fader and colour: %s' % path)
    for key, value in expect.items():
        if key[0] == 'slot':
            if new.rack_slots()[key[1]].v != b'':
                probs.append('A cleared slot is not empty.')
            continue
        kind, i, what = key
        p = strip_parts(new.record(kind, i, 'Strip').v)
        got = {'name': p['name'], 'colour': p['colour'], 'fader': p['fader']}[what]
        want = clean_name(value)[0] if what == 'name' else value
        if got != want:
            probs.append('%s %d did not read back as written.' % (KIND_LABEL[kind], i + 1))
    return probs


# ---- printing --------------------------------------------------------------------------------------------------------
def load(path):
    try:
        with open(path, 'rb') as f:
            data = f.read(MAX_BYTES + 1)
    except OSError as e:
        raise ShowError('%s: %s' % (path, e.strerror))
    return data, Show(data)


def fmt_fader(v):
    return '-inf' if v == '-inf' else '%+.1f' % v if v is not None else '?'


def print_info(m):
    s, e, c = m['show'], m['engine'], m['counts']
    fam = {'s6l': 'S6L show', 'classic': 'classic VENUE show', 's3l': 'S3L-X show'}[s['family']]
    where = {'console': 'saved on a console', 'standalone': 'saved by VENUE Standalone'}
    print('%s, saved by %s (format %s), %s' % (fam, s['created_by'] or '?', s['version'],
                                              where.get(s['saved_on'], 'save location not recorded')))
    print('engine: %s (Main Rack Type %s, %s)  inputs %s  DSP cards %s  surface code %s  %s Hz' % (
        e['name'] or 'unknown', e['rack_type'], e['sure'] or 'not known', e['inputs'], e['dsp_cards'],
        m['surface']['console_type'], m['sample_rate']))
    print('mains: %s' % {'lr_mono': 'L-R plus Mono', 'lcr': 'L-C-R'}.get(s['mains'], 'not read'))
    print('strips: %d inputs, %d FX returns, %d auxes, %d groups, %d matrixes, %d mains, %d VCAs' % (
        c['inputs'], c['fx_returns'], c['aux'], c['groups'], c['matrix'], c['mains'], c['vca']))
    print('snapshots: %d   plug-ins: %d used slots, %d types in the show\'s list' % (
        c['snapshots'], c['plugins_used'], c['plugin_types']))
    if s['comment']:
        print('comment: %s' % s['comment'])
    if s['last_load']:
        print('last load: %s' % s['last_load'])
    print('edit: %s' % ('open (names, faders, colours, slot clears inside the proven limits; see --help)'
                        if m['edit']['open'] else 'closed. ' + m['edit']['why']))
    for w in m['warnings']:
        print('note: %s' % w)


def print_strips(m, kind=None, proc=False, sends=False):
    rows = [x for x in m['inputs'] + m['outputs'] if kind is None or x['kind'] == kind]
    for x in rows:
        col = x['colour']
        cs = '%d %-6s%s' % (col['index'], col['name'] or '?', '' if col['sure'] == 'proven' else '?') if col else '?'
        role = ' (%s)' % x['role'] if x.get('role') else ''
        print('%-7s %-17s %s %-10s %7s%s' % (x['id'], '"%s"' % x['name'] if x['name'] else '-',
                                             'ST' if x['stereo'] else '  ', cs, fmt_fader(x['fader_db']), role))
        if proc:
            if x.get('patch'):
                print('        patch byte: port %d, device code %d (a copy; see S6L-FORMAT.md)' % (
                    x['patch']['port'] + 1, x['patch']['device_code']))
            if x.get('hpf'):
                print('        HPF %d Hz' % x['hpf']['freq'])
            if x.get('eq'):
                print('        EQ ' + '  '.join('%d:%s%+.1fdB %dHz Q%.2f' % (b['band'], '' if b['on'] else 'off ',
                                                                             b['gain_db'], b['freq'], b['q'])
                                               for b in x['eq']))
            if x.get('comp'):
                c = x['comp']
                print('        comp thr %+.1f dB, ratio %.2f:1, attack %g ms, release %d ms, knee %d, gain %+.1f dB'
                      % (c['thr_db'], c['ratio'], c['attack_ms'], c['release_ms'], c['knee'], c['gain_db']))
            if x.get('gate'):
                g = x['gate']
                print('        gate thr %+.1f dB, ratio %.2f:1, attack %g ms, release %d ms, hold %d ms, range %+.1f dB'
                      % (g['thr_db'], g['ratio'], g['attack_ms'], g['release_ms'], g['hold_ms'], g['range_db']))
            for ins in x.get('inserts') or ():
                print('        insert %d: rack slot %s' % (ins['position'], ins['at'] or 'index %d' % ins['slot']))
        if sends and x.get('sends'):
            print('        sends: ' + ', '.join('%s %s' % (s['bus'], fmt_fader(s['level_db'])) for s in x['sends']))


def print_plugins(m, params=False):
    racks = m['plugins']['racks']
    for x in m['plugins']['slots']:
        t = x['type'] or {}
        where = ('%s (rack "%s")' % (x['at'], racks[x['rack'] - 1]['name'])) if x['rack'] else 'index %d' % x['slot']
        ins = x['insert']
        if not ins:
            route = 'not routed'
        elif ins.get('strip'):
            route = 'insert %d on %s' % (ins['position'], ins['strip'])
        elif ins.get('bus_fed'):
            route = 'bus-fed from %s, returns to %s' % (ins['from'] or '?', ins['return'] or '?')
        else:
            route = 'routing not decoded'
        snaps = ''
        if x['snapshot_copies']:
            differ = sum(1 for c in x['snapshot_copies'] if not c['same'])
            snaps = ', in %d snapshots (%d differ)' % (len(x['snapshot_copies']), differ)
        if x['current_state_copy']:
            snaps += ', in current state'
        print('%-22s %-28s %s, %s %d bytes%s%s' % (
            where, t.get('name') or t.get('id') or '?', route, x['state'], x['bytes'],
            ', ' + x['format'] if x['format'] else '', snaps))
        if m['edit']['open']:
            print('%22s clear: %s' % ('', 'yes' if x['clear']['ok'] else 'no. ' + x['clear']['why']))
        if params and x['params']:
            for p in x['params']:
                print('%26s%s = %s' % ('', p['id'], ('%g' % p['value']) if isinstance(p['value'], float)
                                         else p['value']))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='s6l_tool.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')
    sub.required = True
    p = sub.add_parser('info', help='header, engine, counts, what edit may change')
    p.add_argument('show')
    p = sub.add_parser('strips', help='every strip: name, stereo, colour, fader')
    p.add_argument('show')
    p.add_argument('--kind', choices=sorted(PREFIX), help='one kind of strip only')
    p.add_argument('--proc', action='store_true', help='also the patch byte, HPF, EQ, compressor, gate, inserts')
    p.add_argument('--sends', action='store_true', help='also the aux sends that are not at -inf')
    p = sub.add_parser('plugins', help='used rack slots')
    p.add_argument('show')
    p.add_argument('--params', action='store_true', help='print the readable plug-in settings')
    p = sub.add_parser('snapshots', help='snapshot names and plug-in copies')
    p.add_argument('show')
    p = sub.add_parser('check', help='the file checks edit runs on its output')
    p.add_argument('show')
    p = sub.add_parser('json', help='the whole read as JSON')
    p.add_argument('show')
    p = sub.add_parser('edit', help='proven changes only, into a new file')
    p.add_argument('show')
    p.add_argument('out')
    p.add_argument('--rename', action='append', default=[], metavar='ID=NAME')
    p.add_argument('--names', metavar='FILE', help='input names from a .csv (Name column) or a text file')
    p.add_argument('--colour', '--color', action='append', default=[], metavar='ID=COLOUR', dest='colour')
    p.add_argument('--fader', action='append', default=[], metavar='ID=DB')
    p.add_argument('--clear', action='append', default=[], metavar='RACK.POSITION')
    p.add_argument('--dry-run', action='store_true', help='check and print the changes, write nothing')
    a = ap.parse_args(argv)
    try:
        data, sh = load(a.show)
        if a.cmd == 'edit':
            return do_edit(a, data, sh)
        m = model(sh, os.path.basename(a.show))
        if a.cmd == 'info':
            print_info(m)
        elif a.cmd == 'strips':
            print_strips(m, a.kind, a.proc, a.sends)
        elif a.cmd == 'plugins':
            print_plugins(m, a.params)
            if not m['plugins']['slots']:
                print('no used rack slots')
        elif a.cmd == 'snapshots':
            for s in m['snapshots']:
                print('%4d  %-32s %s' % (s['n'], '"%s"' % s['name'], 'not read' if not s['read'] else
                                         '%d plug-in copies' % s['plugin_copies']))
            if not m['snapshots']:
                print('no snapshots')
        elif a.cmd == 'check':
            rows, probs = checks(sh)
            for ok, line in rows:
                print('%s  %s' % ('ok  ' if ok else 'FAIL', line))
            for line in probs:
                print('      %s' % line)
            return 0 if all(ok for ok, _ in rows) and not probs else 1
        elif a.cmd == 'json':
            json.dump(m, sys.stdout, indent=1, ensure_ascii=False)
            print()
        return 0
    except ShowError as e:
        print(str(e), file=sys.stderr)
        return 1


def do_edit(a, data, sh):
    if os.path.abspath(a.out) == os.path.abspath(a.show) or (
            os.path.exists(a.out) and os.path.samefile(a.out, a.show)):
        raise ShowError('Refusing to overwrite the input. Write a new file.')
    changes = []

    def pair(v, flag):
        if '=' not in v:
            raise ShowError('%s takes ID=VALUE, for example in1=%s.' % (flag, 'Kick In' if flag == '--rename' else '3'))
        k, val = v.split('=', 1)
        return k.strip(), val
    if a.names:
        for n, name in names_from(a.names):
            changes.append(('name', 'in%d' % n, name))
    for v in a.rename:
        k, val = pair(v, '--rename')
        changes.append(('name', k, val))
    for v in a.colour:
        k, val = pair(v, '--colour')
        changes.append(('colour', k, colour_number(val)))
    for v in a.fader:
        k, val = pair(v, '--fader')
        changes.append(('fader', k, fader_tenths(val)))
    for v in a.clear:
        changes.append(('clear', slot_of(v)))
    if not changes:
        raise ShowError('Say what to change: --rename, --names, --colour, --fader or --clear.')
    new, said = make_edits(data, changes)
    for line in said:
        print(line)
    print('checks passed: the new show parses, writes back byte for byte, and only the named records changed.')
    if a.dry_run:
        print('dry run, nothing written')
        return 0
    with open(a.out, 'wb') as f:
        f.write(new)
    print('wrote %s (%d bytes). Open it in VENUE Standalone with Filing > Load and save it there before a console '
          'sees it.' % (a.out, len(new)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
