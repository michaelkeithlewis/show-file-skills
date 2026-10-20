#!/usr/bin/env python3
"""inspect.py - the Session Checker: read ANY DiGiCo SD/Quantum session (.ses) and describe it in plain terms.

    python3 -m sessionmaker.inspect file.ses [--json] [--limit SECONDS] [--max-mem MB]     (from digico/scripts)

inspect(data_or_path) never raises. It returns {'ok': True, ...readout} or {'ok': False, 'error': '<plain sentence>',
'code': 'not_ses' | 'too_big' | 'empty' | 'broken' | 'too_slow' | 'too_complex'}. Hostile input is expected (the web
checker takes uploads from anyone), so the reader:
  - refuses files over 32 MB and anything without the DiGiCo header and a sane section table;
  - walks the file by its own structure in one linear pass (section 211 objects in order, section 201 channel records
    in order) instead of scanning for magic bytes, so work and memory grow with the file size only (a 28 MB show
    reads in about a second at ~2x the file size in memory; ses.Session needs ~13x);
  - checks a deadline inside every loop and under a CLI run also arms SIGALRM and RLIMIT_AS as a hard stop;
  - runs sessionmaker.validate only after checking the counts validate trusts (bank count, object count) against
    the section sizes, and treats any failure in it as a finding, not a crash. validate also compares the header's
    bus, matrix, control group and graphic EQ counts with the section 201 records (validate.HEADER_COUNTS): the
    editor crashes or drops a file where they differ, so a mismatch fails the compatibility line.

What it reads (field map, all verified on the 116 editor-saved defaults and 39 real sessions, see
the decode notes (not published):
  header        0x0b family code ('Q2', 'SD9', 'SDC'...), 0x15 revision letter, u16 0x22 build that saved the file,
                tConsoleRec from 0x24 (Delphi RTTI field names): 0x26 inputs, 0x36/0x38 mono/stereo auxes,
                0x46/0x48 mono/stereo groups, float32 0x77 SampleFrequency (48000 or 96000), 0x93 matrix outputs,
                0x94 control groups, 0x96 matrix inputs, 0x97 graphic EQs.
  section 0     session notes: 00 00 | u16 length | text.
  section 201   channel list: groups 'ca 00 6c 00 | type | name' + u32 count @+0x70 + count cb records
                (cb 00 hl 00 | id | surface number | name[32] | +41 width | +84 EngineChannel | +86 TidalChannel).
                Types: 01 inputs, 05 aux, 06 group, 07 bus right sides, 0a control groups, 0c talkback input,
                0e FX, 0f matrix inputs, 10 matrix outputs, 11 graphic EQ, 18 Spice Rack, 1b-21 input sockets
                (INTERNAL, Local I/O, Rack n, MADI, USB, Waves...), 4d-53 the matching output sockets.
  section 210   snapshots: one 'd3 00 | u32 n | d5 00 01 00' object list per stored snapshot.
  section 211   live objects: d5 00 | u16 len | ... | u32 nrec | nrec module records | trailer
                27 00 | id u16 (type << 8 | index) | name[32] | u32 | width. Module record: da 00 3a 00 | type u16 |
                00 00 | name[32] | TDateTime | u16 count @+0x30 | count x [param][module][band][flags][float32].
  input patch   slot (01, 00, band 0) main, band 1 alt: raw 00 <side> <index> <type> -> the object with id
                (type << 8 | index): a socket (record 0x11: gain 0x86 dB, phantom 0x83, pad 0x89) or an FX unit (0e;
                side 01 = its right output). (01, 0e, 0) = 1.0 when the channel runs on its alt input: gain, 48V and
                pad then come from the alt socket.
  inserts       module 08: in (02, band 0 A / 1 B), send (fe, band), return (00, band): raw 00 00 <slot> 18 = Spice
                Rack slot.
  aux sends     module 02, band = aux internal index (section 201 aux id & 0xff): level 0x01 dB (-150 off), on 0x02,
                pan 0x03 (stereo aux), pre/post 0x04 (0 post, 1 pre, 2 pre-mute, 3 mid-EQ, 4 pre-EQ, 5 pre-processing).
  bus masters   aux / group objects: module 0c fader 21, mute 22, link pans 0f; module 03 param 09 = group routing;
                output sockets (types 4d-5f, module 12 (00,0)) name their source bus; the right side of a stereo bus is
                the 201 record's BussID partner (+54). devices: section 246, 50 x 210-byte records, record k = input
                sockets 0x1c + k and output sockets 0x4e + k (decode notes, not published).
  group assign  module 03, param 09, band = group internal index.
  FX unit       object type 0e, record 0x15 named after its preset: feed (00, band 0/1) raw .. .. <index> <type>
                (05 aux, 07 right side of a stereo bus, 01 input direct out, 06 group). Kind from its keys
                (FX_KIND_KEYS): reverb predelay (0f) s, decay (12) s, mix (01) %, lo filter (14, 1), hi filter
                (14, 0), hi damping (37); delay time (02) s, feedback (03) %; chorus delay (11) s, depth (03) s.
  model         SD8/SD10 and SD9/SD11 share a family code; MODEL_SIG tells them apart from fixed header counts and
                ALSO_LOADS_ON lists the bigger model that also opens the smaller one's file.
  Mustard       modules 1a tube, 1c EQ, 1d comp, 1e gate with on/in at param 02; cb +86 TidalChannel != -1 is the
                editor's own instance allocation. A stereo channel uses 2 instances.
"""
import json
import os
import re
import signal
import struct
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ROOT  # ses.py and sesproc.py sit next to this package
for _p in (TOOLS, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ses as _ses  # noqa: E402

MAX_BYTES = 32 * 1024 * 1024
TIME_LIMIT = 10.0
NAME_SHOWN = 8                      # characters a channel strip is known to show (FORMAT.md, ses.rename default)
MAGIC = b'DiGiCo     '
SEC_TABLE, SEC_IDS, NSEC = 0x100, 0x1a0, 40
REC = b'\xda\x00\x3a\x00'
CHREC_HL = (0x50, 0x58, 0x78, 0x79)
MAX_OBJECTS = 60000                 # real sessions: 425-4,000 live objects
MAX_RECS_PER_OBJECT = 512
MAX_GROUPS_201 = 256
MAX_CB = 20000

# file-family code at 0x0b -> console keys that write it (consoles.py) and the plain label
FAMILY = {
    'Q1': (['q112'], 'Quantum 112'), 'Q2': (['q225', 'q225p'], 'Quantum 225'), 'Q3': (['q338', 'q338p'], 'Quantum 326 or 338'),
    'Q5': (['q5'], 'Quantum 5'), 'SDQ': (['q7'], 'Quantum 7'), 'Q8': (['q852'], 'Quantum 852'),
    'SD5': (['sd5', 'sd5cs'], 'SD5 or SD5 CS'), 'SD7': (['sd7'], 'SD7'), 'SD8': (['sd8', 'sd10'], 'SD8 or SD10'),
    'SD9': (['sd9', 'sd11'], 'SD9 or SD11'), 'SDC': (['sd12'], 'SD12 or SD12-96'),
}
QUANTUM = {'Q1', 'Q2', 'Q3', 'Q5', 'SDQ', 'Q8'}
# Models that share a family code are told apart by header fields that are fixed per model (tConsoleRec
# nMatrixOutputs 0x93, nControlGroups 0x94, nMatrixInputs 0x96, nGraphicEQs 0x97; the same values in every default
# V1455-V2242 and in every real session whose file name names the model). This matters, because the bigger model's
# file does not load on the smaller one: the SD8 editor silently starts its own empty session instead of an SD10
# file, and the SD11 editor does the same with an SD9 file. The other way works: the SD10 editor keeps an SD8 file
# and the SD9 editor an SD11 file (editor proofs 2026-10-13, the decode notes (not published). SD5 and SD5CS files are
# identical, and the SD5 editor keeps an SD5CS file, so both stay candidates.
MODEL_SIG = {
    'SD8': [('sd8', {0x93: 16, 0x96: 16}), ('sd10', {0x93: 24, 0x96: 24})],
    'SD9': [('sd9', {0x94: 12, 0x96: 12, 0x97: 16}), ('sd11', {0x94: 8, 0x96: 8, 0x97: 12})],
}
ALSO_LOADS_ON = {'sd8': ['sd10'], 'sd11': ['sd9']}
# Public software releases per console the decode notes (not published), firmware_matrix.json). Some trains shipped
# for one model only (V1229 Q338, V1246 Q5, V1454 Q225, V1861/V1879/V1889 Q852), so the oldest release that opens a
# file depends on the console.
_SD_TRAIN = [987, 1069, 1090, 1143, 1280, 1455, 1528, 1619, 1742, 1926, 2025, 2126, 2232, 2242]
_MAIN_TRAIN = [1455, 1528, 1619, 1742, 1926, 2025, 2126, 2232, 2242]
RELEASES_BY_KEY = dict({k: _SD_TRAIN for k in ('sd5', 'sd5cs', 'sd7', 'sd8', 'sd9', 'sd10', 'sd11', 'sd12')},
                       q7=[1069, 1090, 1143, 1280] + _MAIN_TRAIN, q338=[1229, 1280] + _MAIN_TRAIN,
                       q5=[1246, 1280] + _MAIN_TRAIN, q225=[1454] + _MAIN_TRAIN, q225p=_MAIN_TRAIN[3:], q338p=_MAIN_TRAIN[3:],
                       q852=[1861, 1879, 1889] + _MAIN_TRAIN[4:], q112=[2126, 2232, 2242])
RELEASES = sorted(set().union(*RELEASES_BY_KEY.values()))
# console software builds seen in real files that DiGiCo never published as an offline editor (two real Q5
# sessions were saved by V1623 on the console itself)
SEEN_BY_KEY = {'q5': {1623}}
SEEN_BUILDS = set().union(*SEEN_BY_KEY.values())
# header revision letter at 0x15 per build, from every editor-saved file (V18 Q852 builds unseen)
REV = {1455: 'G', 1528: 'H', 1619: 'I', 1623: 'I', 1742: 'J', 1926: 'K', 2025: 'M', 2126: 'N', 2232: 'O', 2242: 'O'}

T_INPUT, T_AUX, T_GROUP, T_BUSR, T_CG, T_TB, T_FX, T_MTX_IN, T_MTX_OUT, T_GEQ, T_SPICE = (
    0x01, 0x05, 0x06, 0x07, 0x0a, 0x0c, 0x0e, 0x0f, 0x10, 0x11, 0x18)
SOCKET_REC = 0x11
FX_REC = 0x15
MUSTARD_MODS = {0x1a: 'tube', 0x1c: 'EQ', 0x1d: 'comp', 0x1e: 'gate'}
# FX algorithm from the unit's own parameter keys (the factory presets' key sets, the same in every default
# V1455-V2242; the decode notes (not published). Checked in this order: every delay has (56,0), the pitch shifter (02,1), the
# Audio Enhancer (63,0), every reverb (0f,0) predelay; the choruses carry (12,0) too but no (0f,0).
FX_KIND_KEYS = [('delay', (0x56, 0)), ('pitch', (0x02, 1)), ('special', (0x63, 0)), ('reverb', (0x0f, 0)),
                ('chorus', (0x11, 0))]
FX_KIND_LABEL = {'reverb': 'Reverb', 'delay': 'Delay', 'chorus': 'Chorus', 'pitch': 'Pitch shifter',
                 'special': 'Enhancer', 'other': 'Effect'}
# A name that ends in a side: "Keys L", "OH_R", "Pad-left" (a separator before it), or "KeysL" / "Gtr2R" (a capital
# L or R straight after a lower-case letter or a digit). A lower-case l or r straight after a letter is part of the
# word ("Hall", "Choir", "Guitar", "Wurl"), never a side.
PAIR_RE = re.compile(r'^(.*?)[\s_.-]*(?:\b|(?<=_)|(?<=[a-z0-9])(?=[LR]))(L|R|Left|Right|LEFT|RIGHT|left|right|l|r)$')
BOTH_SIDES_RE = re.compile(r'(?i)(?:^|[^a-z])L\s*[/&+-]?\s*R$')      # "Trx L/R", "Keys LR": a stereo name


class Stop(Exception):
    """A plain-sentence refusal: (code, message)."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


class _Clock:
    def __init__(self, limit):
        self.t0 = time.monotonic()
        self.deadline = self.t0 + limit

    def tick(self):
        if time.monotonic() > self.deadline:
            raise Stop('too_slow', 'Reading this file took too long. It may be damaged.')

    def ms(self):
        return round((time.monotonic() - self.t0) * 1000)


# ------------------------------------------------------------------------------------------------ small readers
def _u8(d, p):
    if not 0 <= p < len(d):
        raise Stop('broken', 'The file ends early. It may be damaged or cut short.')
    return d[p]


def _u16(d, p):
    if not 0 <= p <= len(d) - 2:
        raise Stop('broken', 'The file ends early. It may be damaged or cut short.')
    return struct.unpack_from('<H', d, p)[0]


def _u32(d, p):
    if not 0 <= p <= len(d) - 4:
        raise Stop('broken', 'The file ends early. It may be damaged or cut short.')
    return struct.unpack_from('<I', d, p)[0]


def _sstr(d, p, cap=31):
    n = _u8(d, p)
    if n > cap:
        return None
    return bytes(d[p + 1:p + 1 + n]).decode('latin1')


def _f(x, nd=1):
    if x is None or x != x or x in (float('inf'), float('-inf')):
        return None
    return round(float(x), nd)


def _clean_name(s):
    """Names come from the file: show printable text only."""
    return ''.join(ch if 32 <= ord(ch) < 127 or ord(ch) >= 160 else '?' for ch in (s or ''))


# ------------------------------------------------------------------------------------------------ structure
def _header(d):
    if len(d) == 0:
        raise Stop('empty', 'The file is empty.')
    if len(d) > MAX_BYTES:
        raise Stop('too_big', 'The file is over 32 MB. DiGiCo sessions are smaller than that.')
    if len(d) < 0x1c8 or d[:11] != MAGIC or d[0x0f:0x15] != b'.SES v':
        raise Stop('not_ses', "This isn't a DiGiCo session. Pick the .ses file the console or offline editor saved.")
    code = bytes(d[11:15]).decode('latin1').strip()
    offs = struct.unpack_from('<%di' % NSEC, d, SEC_TABLE)
    ids = d[SEC_IDS:SEC_IDS + NSEC]
    n = next((i for i in range(1, NSEC) if offs[i] == len(d)), None)
    if n is None or offs[0] < SEC_IDS + NSEC or any(offs[i + 1] < offs[i] for i in range(n)):
        raise Stop('broken', 'This DiGiCo session is damaged: its table of contents does not match the file. '
                   'It may be cut short. Copy it from the console again.')
    sections = [(ids[i], offs[i], offs[i + 1]) for i in range(n)]
    return code, sections


def _span(sections, sid):
    return next(((a, b) for s, a, b in sections if s == sid), None)


def _walk_211(d, span, clock):
    """Every live object in section 211, in file order: {id, type, index, name, width, recs: [offset], trailer}."""
    a, b = span
    if b - a < 6 or d[a:a + 2] != b'\xd3\x00':
        raise Stop('broken', 'This DiGiCo session is damaged: the channel data does not start where it should.')
    n = _u32(d, a + 2)
    if n > MAX_OBJECTS:
        raise Stop('too_complex', 'This file lists more channels and objects than any console holds.')
    p, out = a + 6, []
    for k in range(n):
        if not k & 0xff:
            clock.tick()
        if p + 8 > b or d[p:p + 2] != b'\xd5\x00':
            raise Stop('broken', 'This DiGiCo session is damaged: channel %d of %d is cut short.' % (k + 1, n))
        p += 4 + _u16(d, p + 2)
        nrec = _u32(d, p)
        if nrec > MAX_RECS_PER_OBJECT:
            raise Stop('broken', 'This DiGiCo session is damaged: one channel holds too many modules.')
        p += 4
        recs = []
        for _ in range(nrec):
            if p + 0x3e > b or d[p:p + 4] != REC:
                raise Stop('broken', 'This DiGiCo session is damaged: a processing block is broken.')
            recs.append(p)
            p += 4 + 0x3a + 8 * _u16(d, p + 0x30) + 12
        if p + 41 > b or d[p:p + 2] != b'\x27\x00':
            raise Stop('broken', 'This DiGiCo session is damaged: a channel ends in the wrong place.')
        oid = _u16(d, p + 2)
        out.append({'id': oid, 'type': oid >> 8, 'index': oid & 0xff, 'name': _sstr(d, p + 4) or '',
                    'width': d[p + 40], 'recs': recs, 'trailer': p})
        p += 41
    return out


def _walk_201(d, span, clock):
    """{type: {'name': group name, 'recs': [{id, number, name, width, engine, tidal}]}} in record (surface) order.
    Walked from group header to group header; a header whose records do not chain is skipped."""
    a, b = span
    out, steps, pos = {}, 0, a
    groups = 0
    while True:
        q = d.find(b'\xca\x00\x6c\x00', pos, b)
        if q < 0:
            break
        pos = q + 4
        if q + 0x74 > b or d[q + 5] > 31:
            continue
        typ, cnt = d[q + 4], _u32(d, q + 0x70)
        if cnt > MAX_CB:
            continue
        p, recs = q + 0x74, []
        for _ in range(cnt):
            steps += 1
            if not steps & 0x3ff:
                clock.tick()
            if steps > 4 * MAX_CB:
                raise Stop('too_complex', 'This file has more channel records than any console holds.')
            if p + 42 > b or d[p:p + 2] != b'\xcb\x00' or d[p + 2] not in CHREC_HL or d[p + 8] > 31 \
                    or d[p + 41] not in (1, 2) or _u16(d, p + 4) >> 8 != typ:
                recs = None
                break
            hl = d[p + 2]
            recs.append({'id': _u16(d, p + 4), 'number': _u16(d, p + 6), 'name': _sstr(d, p + 8) or '',
                         'width': d[p + 41], 'partner': _u16(d, p + 54) if p + 56 <= b else 0,
                         'engine': struct.unpack_from('<h', d, p + 84)[0] if hl >= 0x58 and p + 88 <= b else None,
                         'tidal': struct.unpack_from('<h', d, p + 86)[0] if hl >= 0x58 and p + 88 <= b else None})
            p += 4 + hl
        if recs is None:
            continue
        groups += 1
        if groups > MAX_GROUPS_201:
            raise Stop('too_complex', 'This file has more channel groups than any console holds.')
        g = out.setdefault(typ, {'name': _sstr(d, q + 5) or '', 'recs': []})
        g['recs'].extend(recs)
        pos = p
    return out


def _snapshots(d, span):
    if not span:
        return 0
    a, b = span
    return len(re.findall(rb'\xd3\x00....\xd5\x00\x01\x00', d[a:b], flags=re.S))


def _notes(d, sections):
    s = _span(sections, 0) or ((sections[0][1], sections[0][2]) if sections and sections[0][0] == 0 else None)
    if not s or s[1] - s[0] < 4:
        return ''
    n = _u16(d, s[0] + 2)
    return _clean_name(bytes(d[s[0] + 4:min(s[0] + 4 + n, s[1])]).decode('latin1'))[:255]


# ------------------------------------------------------------------------------------------------ a lean ses.Session
def _lean_session(d, objs):
    """A ses.Session built from the linear walk: only the live input channels get Records (enough for
    process.readback_channel and ses.get), so memory stays near the file size."""
    s = _ses.Session.__new__(_ses.Session)
    s.d, s.keys, s.records, s.snapshot_inputs = d, {}, [], []
    s.inputs = []
    for o in objs:
        if o['type'] != T_INPUT:
            continue
        recs = [_ses.Record(d, r) for r in o['recs']]
        s.inputs.append(_ses.Channel(o['index'] + 1, recs, o['trailer']))
    s.inputs.sort(key=lambda c: c.index)
    s.by_index = {c.index: c for c in s.inputs}
    return s


def _rec_slots(d, off):
    """{(param, band): float offset} of one module record (non-input objects, parsed on demand)."""
    cnt = _u16(d, off + 0x30)
    s0, out = off + 0x3e, {}
    for k in range(cnt):
        q = s0 + 8 * k
        out[(d[q], d[q + 2])] = q + 4
    return out


def _fget(d, slots, key):
    q = slots.get(key)
    return struct.unpack_from('<f', d, q)[0] if q is not None else None


def _raw(d, slots, key):
    q = slots.get(key)
    return bytes(d[q:q + 4]) if q is not None else None


# ------------------------------------------------------------------------------------------------ the readout
def _ref(raw):
    """Raw 4-byte route 00 <side> <index> <type> -> (type, index, side) or None (unpatched / not a route). Side 01 is
    the right leg of a stereo source, e.g. an input patched to an FX unit's right output."""
    if raw is None or raw == b'\0\0\0\0' or raw[0] != 0 or raw[1] > 1:
        return None
    return raw[3], raw[2], raw[1]


# Pulse (V1742+, Quantum 225 and 338 only) sets bit 0x10 of the header's ExtensionsUsed byte (0x25); a Pulse session
# only opens on a console or editor with the Pulse extension enabled, a standard one opens on both.
PULSE_KEYS = {'Q2': ('q225', 'q225p'), 'Q3': ('q338', 'q338p')}


def _models(code, d, keys):
    """-> (made_for, loads_on): the console keys a file with family code `code` was made for (narrowed by MODEL_SIG
    when one model matches) and the keys whose editors open it (made_for plus ALSO_LOADS_ON), made_for first."""
    if code in PULSE_KEYS and len(d) > 0x25:
        std, pulse = PULSE_KEYS[code]
        if d[0x25] & 0x10:
            return [pulse], [pulse]
        return [std], [std] + ([pulse] if pulse in keys else [])
    sig = MODEL_SIG.get(code)
    if not sig:
        return list(keys), list(keys)
    hit = [k for k, want in sig if all(d[o] == v for o, v in want.items())]
    if len(hit) != 1:
        return list(keys), list(keys)
    return hit, hit + [k for k in ALSO_LOADS_ON.get(hit[0], []) if k in keys]


def _bus_label(kind, b):
    """'Aux 3' or 'Aux 3: Vox verb' (no repeat when the name is the default 'Aux 3')."""
    if not b:
        return kind
    base = '%s %d' % (kind, b['n'])
    nm = (b.get('name') or '').strip()
    return base if not nm or nm.lower() == base.lower() else '%s: %s' % (base, nm)


def inspect(src, name=None, time_limit=TIME_LIMIT):
    """Read a session (bytes or path) and describe it. Never raises."""
    clock = _Clock(time_limit)
    try:
        if isinstance(src, (bytes, bytearray, memoryview)):
            d = bytes(src)
        else:
            st = os.stat(src)
            if st.st_size > MAX_BYTES:
                raise Stop('too_big', 'The file is over 32 MB. DiGiCo sessions are smaller than that.')
            with open(src, 'rb') as f:
                d = f.read(MAX_BYTES + 1)
            name = name or os.path.basename(src)
        if d[:2] == b'\x1f\x8b':                # gzip: a dLive show (.tar.gz), read by dlive/check.py
            from dlive import check as dlive_check
            out = dlive_check.readout(d, _clean_name(name or ''))
            out['ms'] = clock.ms()
            return _finite(out)
        out = _inspect(d, clock)
        out.update(ok=True, file={'name': _clean_name(name or '')[:120], 'bytes': len(d)}, ms=clock.ms())
        return _finite(out)
    except Stop as e:
        return {'ok': False, 'code': e.code, 'error': e.msg, 'ms': clock.ms()}
    except MemoryError:
        return {'ok': False, 'code': 'too_complex', 'error': 'This file is too large to read here.', 'ms': clock.ms()}
    except RecursionError:
        return {'ok': False, 'code': 'broken', 'error': 'This DiGiCo session is damaged.', 'ms': clock.ms()}
    except Exception as e:  # noqa: BLE001 - hostile input must never take the caller down
        return {'ok': False, 'code': 'broken', 'error': 'This DiGiCo session is damaged or in a layout we can not read '
                'yet.', 'detail': type(e).__name__, 'ms': clock.ms()}


def _inspect(d, clock):
    code, sections = _header(d)
    build = _u16(d, 0x22)
    rev = chr(d[0x15]) if 0x41 <= d[0x15] <= 0x5a else '?'
    hdr = {'inputs': _u16(d, 0x26), 'aux_mono': _u16(d, 0x36), 'aux_stereo': _u16(d, 0x38),
           'group_mono': _u16(d, 0x46), 'group_stereo': _u16(d, 0x48), 'matrix_outputs': d[0x93],
           'control_groups': d[0x94], 'matrix_inputs': d[0x96], 'graphic_eqs': d[0x97]}
    sr = struct.unpack_from('<f', d, 0x77)[0]
    sample_rate = int(sr) if sr in (44100.0, 48000.0, 88200.0, 96000.0) else None

    s211, s201 = _span(sections, 211), _span(sections, 201)
    if not s211 or not s201:
        raise Stop('broken', 'This DiGiCo session is damaged: the channel sections are missing.')
    objs = _walk_211(d, s211, clock)
    clock.tick()
    g201 = _walk_201(d, s201, clock)
    clock.tick()
    by_id = {o['id']: o for o in objs}

    fam_keys, fam_label = FAMILY.get(code, ([], None))
    model_keys, load_keys = _models(code, d, fam_keys)
    quantum = code in QUANTUM
    facts = _console_facts(fam_keys)
    name_of = lambda k: facts[k]['name'] if k in facts else k.upper()  # noqa: E731
    loads_label = fam_label
    if len(model_keys) < len(fam_keys):
        fam_label = name_of(model_keys[0])
        parts = [x.strip() for k in load_keys for x in name_of(k).split('/')]
        loads_label = ', '.join(parts[:-1]) + ' or ' + parts[-1] if len(parts) > 1 else parts[0]

    # ---- buses from section 201 (surface order) ----
    def busses(t):
        return [{'n': r['number'], 'band': r['id'] & 0xff, 'name': _clean_name(r['name']), 'stereo': r['width'] == 2,
                 'id': r['id'], 'partner': r.get('partner') if r['width'] == 2 else 0}
                for r in sorted((g201.get(t) or {}).get('recs', []), key=lambda r: r['number'])]
    auxes, groups = busses(T_AUX), busses(T_GROUP)
    aux_by_band = {a['band']: a for a in auxes}
    grp_by_band = {g['band']: g for g in groups}
    io_names = {t: _clean_name(g['name']) for t, g in g201.items()}

    # ---- inputs ----
    ses = _lean_session(d, objs)
    in201 = (g201.get(T_INPUT) or {}).get('recs', [])
    if not in201:
        in201 = [{'id': 0x0100 | (c.index - 1), 'number': c.index, 'name': c.name, 'width': 1, 'engine': None,
                  'tidal': None} for c in ses.inputs]
    from . import process
    socket_cache = {}

    def socket(t, i):
        """(label, info) for a route target object (socket, FX unit, Spice Rack slot, bus)."""
        o = by_id.get((t << 8) | i)
        key = (t, i)
        if key in socket_cache:
            return socket_cache[key]
        info = {'type': t, 'index': i, 'io': io_names.get(t)}
        if t == T_FX:
            info['label'] = 'FX %d%s' % (i + 1, (': ' + _clean_name(o['name'])) if o and o['name'] else '')
        elif t == T_SPICE:
            info['label'] = 'Spice Rack %d%s' % (i + 1, (': ' + _clean_name(o['name'])) if o and o['name'] else '')
        elif t == T_AUX:
            info['label'] = _bus_label('Aux', aux_by_band.get(i))
        elif t == T_GROUP:
            info['label'] = _bus_label('Group', grp_by_band.get(i))
        elif o is not None:
            info['label'] = _clean_name(o['name']) or '%s %d' % (io_names.get(t, 'socket'), i + 1)
            if o['recs'] and _u16(d, o['recs'][0] + 4) == SOCKET_REC:
                sl = _rec_slots(d, o['recs'][0])
                g, ph, pad = _fget(d, sl, (0x86, 0)), _fget(d, sl, (0x83, 0)), _fget(d, sl, (0x89, 0))
                info.update(gain_db=_f(g), phantom=None if ph is None else ph == 1.0,
                            pad=None if pad is None else pad == 1.0)
        else:
            info['label'] = '%s %d' % (io_names.get(t) or 'socket type %02x' % t, i + 1)
        socket_cache[key] = info
        return info

    channels, warn = [], []
    names_seen = {}
    engine_paths = 0
    mustard_inst, mustard_ch = 0, []
    fx_returns, spice_users = {}, {}
    for k, r in enumerate(in201):
        if not k & 0x1f:
            clock.tick()
        idx = (r['id'] & 0xff) + 1
        c = ses.by_index.get(idx)
        stereo = r['width'] == 2
        engine_paths += r['width']
        nm = _clean_name(r['name'] or (c.name if c else ''))
        ch = {'n': r['number'], 'idx': idx, 'name': nm, 'stereo': stereo}
        if c is None:
            ch['problem'] = 'no channel data'
            channels.append(ch)
            continue
        recs = c.records

        def slots(mod):
            rec = recs.get(mod)
            return rec.slots if rec else {}
        m01, m08, m02, m03 = slots(0x01), slots(0x08), slots(0x02), slots(0x03)
        # patch, gain, 48V: (01,0e,0) = 1.0 when the channel runs on its alt input, and then gain, 48V and pad
        # come from the alt socket (the main socket's values are not in use)
        patch = {}
        use = 'alt' if _fget(d, m01, (0x0e, 0)) == 1.0 else 'main'
        for side, band in (('main', 0), ('alt', 1)):
            ref = _ref(_raw(d, m01, (0x00, band)))
            if ref:
                info = socket(ref[0], ref[1])
                lab = info['label']
                if ref[0] == T_FX:
                    lab += ' (right output)' if ref[2] else ''
                    if band == 0:
                        fx_returns.setdefault(ref[1], []).append(r['number'])
                patch[side] = lab
                if side == use:
                    for kk in ('io', 'gain_db', 'phantom', 'pad'):
                        if info.get(kk) is not None:
                            patch[kk] = info[kk]
        if use == 'alt':
            patch['active'] = 'alt'
        ch['patch'] = patch or None
        trim = _fget(d, m01, (0x01, 0))
        ch['trim_db'] = _f(trim) if trim else None
        # inserts
        ins = []
        for letter, band in (('A', 0), ('B', 1)):
            ref = _ref(_raw(d, m08, (0xfe, band))) or _ref(_raw(d, m08, (0x00, band)))
            if ref:
                info = socket(ref[0], ref[1])
                ins.append({'slot': letter, 'to': info['label'], 'in': _fget(d, m08, (0x02, band)) == 1.0})
                if ref[0] == T_SPICE:
                    spice_users.setdefault(ref[1], []).append(r['number'])
        ch['inserts'] = ins or None
        # processing (sessionmaker.process readback; keys from data/templates.json)
        try:
            ch.update(process.readback_channel(ses, idx))
        except (KeyError, struct.error, IndexError, TypeError, ValueError):
            ch['processing'] = 'unreadable'
        # Mustard
        if 0x1d in recs:
            on = [nm_ for mod, nm_ in MUSTARD_MODS.items() if mod in recs and _fget(d, slots(mod), (0x02, 0)) == 1.0]
            tidal = r.get('tidal')
            if on or (tidal is not None and tidal >= 0):
                ch['mustard_modules'] = on or ['allocated']
                mustard_inst += r['width']
                mustard_ch.append(r['number'])
        # sends and groups
        sends = []
        for (p, b), q in m02.items():
            if p == 0x01 and b in aux_by_band:
                lvl = struct.unpack_from('<f', d, q)[0]
                if lvl > -150 and _fget(d, m02, (0x02, b)) == 1.0:
                    snd = {'aux': aux_by_band[b]['n'], 'level_db': _f(lvl)}
                    pp = _fget(d, m02, (0x04, b))
                    if pp is not None and pp == pp and pp in PREPOST:
                        snd['pre'] = PREPOST[pp]
                    pan = _fget(d, m02, (0x03, b)) if aux_by_band[b]['stereo'] else None
                    if _f(pan, 2) is not None:
                        snd['pan'] = _f(pan, 2)
                    sends.append(snd)
        ch['sends'] = sorted(sends, key=lambda s: s['aux']) or None
        ga = sorted(grp_by_band[b]['n'] for (p, b), q in m03.items()
                    if p == 0x09 and b in grp_by_band and struct.unpack_from('<f', d, q)[0] == 1.0)
        ch['groups'] = ga or None
        fader, mute = _fget(d, slots(0x0c), (0x21, 0)), _fget(d, slots(0x0c), (0x22, 0))
        ch['fader_db'] = _f(fader)
        ch['muted'] = None if mute is None else mute == 1.0
        channels.append(ch)
        names_seen.setdefault(nm.strip().lower(), []).append(r['number'])

    # ---- FX units, Spice Rack ----
    # An FX input (00, band) is fed by an aux (05), the right side of a stereo bus (07, the partner of band 0's
    # source), an input channel's direct out (01) or a group (06). Real sessions carry a non-zero first byte on
    # direct-out and group feeds (05, 07, 08, 09), so only the index and type bytes are read here.
    in_by_idx = {(x['id'] & 0xff): x for x in in201}
    fx, fx_feeds = [], {}
    for o in objs:
        if o['type'] != T_FX or not o['recs']:
            continue
        sl = _rec_slots(d, o['recs'][0])
        feeds = []
        for band in (0, 1):
            raw = _raw(d, sl, (0x00, band))
            if raw is None or raw == b'\0\0\0\0':
                continue
            t, i = raw[3], raw[2]
            if t == T_AUX and i in aux_by_band:
                lab = _bus_label('Aux', aux_by_band[i])
                if o['index'] + 1 not in fx_feeds.setdefault(i, []):
                    fx_feeds[i].append(o['index'] + 1)
            elif t == T_GROUP and i in grp_by_band:
                lab = _bus_label('Group', grp_by_band[i])
            elif t == T_INPUT and i in in_by_idx:
                x = in_by_idx[i]
                nm_ = _clean_name(x['name']).strip()
                lab = 'Input %d%s' % (x['number'], (': ' + nm_) if nm_ else '')
            elif t == T_FX:
                lab = 'FX %d' % (i + 1)
            else:
                continue                       # 07: the right leg of the bus already named by band 0
            if lab not in feeds:
                feeds.append(lab)
        keys = set(sl)
        kind = next((k for k, key in FX_KIND_KEYS if key in keys), 'other')
        unit = {'n': o['index'] + 1, 'name': _clean_name(o['name']), 'stereo': o['width'] == 2, 'kind': kind,
                'kind_label': FX_KIND_LABEL[kind], 'fed_by': feeds or None, 'returns_on': fx_returns.get(o['index'])}
        g = lambda k, b=0: _fget(d, sl, (k, b))  # noqa: E731
        ms = lambda v: _f(v * 1000 if v is not None else None)  # noqa: E731
        mix = _f(g(0x01))
        if kind == 'reverb':
            unit['reverb'] = {'decay_s': _f(g(0x12), 2), 'predelay_ms': ms(g(0x0f)), 'mix_pct': mix,
                              'lo_cut_hz': _f(g(0x14, 1)), 'hi_cut_hz': _f(g(0x14)), 'hi_damp_hz': _f(g(0x37))}
        elif kind == 'delay':
            unit['params'] = {'time_ms': ms(g(0x02)), 'feedback_pct': _f(g(0x03)), 'mix_pct': mix}
        elif kind == 'chorus':
            unit['params'] = {'delay_ms': ms(g(0x11)), 'depth_ms': ms(g(0x03)), 'mix_pct': mix}
        elif kind == 'pitch':
            unit['params'] = {'pitch_left': _f(g(0x02), 3), 'pitch_right': _f(g(0x02, 1), 3), 'mix_pct': mix}
        elif mix is not None:
            unit['params'] = {'mix_pct': mix}
        if unit.get('params'):
            unit['params'] = {k: v for k, v in unit['params'].items() if v is not None} or None
        fx.append(unit)
    spice = [{'slot': o['index'] + 1, 'name': _clean_name(o['name']), 'used_by': spice_users.get(o['index'])}
             for o in objs if o['type'] == T_SPICE]
    clock.tick()
    _bus_details(d, objs, by_id, auxes, groups, grp_by_band, fx_feeds)
    devices = _devices(d, sections, g201)

    counts = {
        'inputs': len(in201), 'inputs_stereo': sum(1 for r in in201 if r['width'] == 2),
        'engine_paths': engine_paths,
        'aux': len(auxes), 'aux_stereo': sum(1 for a in auxes if a['stereo']),
        'groups': len(groups), 'groups_stereo': sum(1 for g in groups if g['stereo']),
        'matrix_outputs': len((g201.get(T_MTX_OUT) or {}).get('recs', [])) or hdr['matrix_outputs'],
        'matrix_inputs': len((g201.get(T_MTX_IN) or {}).get('recs', [])) or hdr['matrix_inputs'],
        'control_groups': len((g201.get(T_CG) or {}).get('recs', [])) or hdr['control_groups'],
        'graphic_eqs': len((g201.get(T_GEQ) or {}).get('recs', [])) or hdr['graphic_eqs'],
        'snapshots': _snapshots(d, _span(sections, 210)),
        'fx_units': len(fx), 'spice_rack_slots': len(spice),
        'spice_rack_used': sum(1 for s in spice if s['used_by']),
    }
    counts['inputs_mono'] = counts['inputs'] - counts['inputs_stereo']
    # patch and monitor mixes at a glance: inputs on a socket, 48V on, and auxes that carry a pre-fader mix (two or
    # more inputs sent pre-fader, and not an FX feed)
    def _on_socket(c):
        pt = c.get('patch') or {}
        lab = str(pt.get('alt' if pt.get('active') == 'alt' else 'main') or '')
        return bool(pt.get('io')) and not lab.startswith(('FX ', 'Spice Rack'))
    counts['patched'] = sum(1 for c in channels if _on_socket(c))
    counts['phantom'] = sum(1 for c in channels if (c.get('patch') or {}).get('phantom'))
    pre_by_aux = {}
    for c in channels:
        for snd in c.get('sends') or []:
            if snd.get('pre') and snd['pre'] != 'post':
                pre_by_aux[snd['aux']] = pre_by_aux.get(snd['aux'], 0) + 1
    fx_aux = {a['n'] for a in auxes if fx_feeds.get(a['band'])}
    counts['mixes'] = sum(1 for a, k in pre_by_aux.items() if k >= 2 and a not in fx_aux)
    clock.tick()
    damaged = _nonfinite(d, objs, {r['id']: r['number'] for r in in201}, clock)

    # ---- structure check (sessionmaker.validate), guarded ----
    structure = _structure(d, sections, g201)
    clock.tick()

    # ---- console, version, compatibility ----
    cands = [{'key': k, 'name': name_of(k)} for k in load_keys]
    console = {'code': code or '?', 'label': fam_label or 'an unknown console (%s)' % (code or 'blank'),
               'loads_on': loads_label or fam_label, 'candidates': cands, 'quantum': quantum, 'known': bool(fam_keys),
               'model': model_keys[0] if len(model_keys) == 1 else None}
    rel = sorted(set().union(*(RELEASES_BY_KEY.get(k, RELEASES) for k in load_keys))) if load_keys else RELEASES
    seen = set().union(*(SEEN_BY_KEY.get(k, set()) for k in load_keys))
    version = {'build': build, 'label': 'V%d' % build, 'rev': rev, 'public': build in rel,
               'console_build': build in seen, 'newest_known': max(RELEASES)}
    exp_rev = REV.get(build)
    compat = _compat(console, build, rel, seen)
    if structure['errors']:
        compat['line'] = ('Made for %s on V%d or newer, but the structure check found problems (listed below). The '
                          'console may refuse it.' % (_a(console['label']), compat['min_build']))
        compat['ok'] = False
    else:
        compat['ok'] = console['known']

    # ---- Mustard vs cap ----
    caps = sorted({facts[k]['mustard_cap'] for k in model_keys if k in facts and facts[k].get('mustard_cap')})
    mustard = None
    if quantum:
        cap = caps[0] if caps else None
        mustard = {'instances': mustard_inst, 'cap': cap, 'channels': mustard_ch,
                   'cap_verified': any(facts[k].get('mustard_cap_verified') for k in model_keys if k in facts)}

    # ---- warnings ----
    W = lambda level, text: warn.append({'level': level, 'text': text})  # noqa: E731
    for e in structure['errors']:
        W('error', e)
    if damaged:
        W('error', '%s hold%s damaged values (not a number). Editor-saved sessions never do, and the DiGiCo editor '
          'crashed loading a file like this in our tests.' % (_list(damaged), '' if len(damaged) > 1 else 's'))
    if not fam_keys:
        W('warn', "The console code '%s' is not one we know. This may not be an SD or Quantum session." % code)
    if build > max(RELEASES):
        W('info', 'V%d is newer than any software we know (newest V%d).' % (build, max(RELEASES)))
    elif build not in rel and build not in seen:
        W('info', 'V%d is not a public DiGiCo release%s.' % (build, ' for this console' if fam_keys else ''))
    if exp_rev and rev != exp_rev:
        W('warn', 'The header version letter (%s) does not match V%d. The header may have been edited.' % (rev, build))
    if hdr['inputs'] != counts['inputs']:
        W('warn', 'The header says %d inputs but the file holds %d.' % (hdr['inputs'], counts['inputs']))
    long_names = [c for c in channels if len(c['name']) > NAME_SHOWN]
    if long_names:
        ex = ', '.join('%d %s' % (c['n'], c['name']) for c in long_names[:4])
        W('info', '%d input name%s over %d characters (%s%s). The channel strip may not show the whole name.' % (
            len(long_names), 's are' if len(long_names) > 1 else ' is', NAME_SHOWN, ex,
            ', ...' if len(long_names) > 4 else ''))
    blank = [c['n'] for c in channels if not c['name'].strip()]
    if blank:
        W('warn', 'Input%s %s %s no name.' % ('s' if len(blank) > 1 else '', _nums(blank),
                                            'have' if len(blank) > 1 else 'has'))
    dups = [(nm, ns) for nm, ns in names_seen.items() if nm and len(ns) > 1]
    for nm, ns in dups[:6]:
        W('info', 'Inputs %s share the name "%s".' % (_nums(ns), next(c['name'] for c in channels if c['n'] == ns[0])))
    if len(dups) > 6:
        W('info', '%d more names are used more than once.' % (len(dups) - 6))
    for text in _pair_findings(channels):
        W('info', text)
    if mustard and mustard['cap'] is not None and mustard['instances'] > mustard['cap']:
        if mustard['cap_verified']:
            over, used = [], 0
            for c in channels:
                if c.get('mustard_modules'):
                    used += 2 if c['stereo'] else 1
                    if used > mustard['cap']:
                        over.append(c['n'])
            W('error', 'Mustard is on for %d instances (a stereo channel uses 2). %s runs %d. On load the console '
              'turns off the rest in channel order (inputs %s).' % (mustard['instances'], _A(fam_label),
                                                                  mustard['cap'], _nums(over)))
        else:
            W('info', 'Mustard is on for %d instances (a stereo channel uses 2). We have confirmed the Mustard limit '
              'only on the Quantum 225 (24), so check this on the console.' % mustard['instances'])
    for k in model_keys:
        f = facts.get(k)
        if f and f.get('max_inputs') and counts['inputs'] > f['max_inputs']:
            if f.get('max_inputs_verified'):
                W('warn', 'This session has %d inputs. %s runs %d.' % (counts['inputs'], _A(f['name']),
                                                                      f['max_inputs']))
            else:
                W('info', 'This session has %d inputs. DiGiCo lists %d for %s. Check it on the console.' % (
                    counts['inputs'], f['max_inputs'], _a(f['name'])))
        if f and quantum and f.get('engine_room') and engine_paths > f['engine_room']:
            W('warn', 'The inputs need %d processing paths (stereo counts 2). %s has room for %d.' % (
                engine_paths, _A(f['name']), f['engine_room']))
    if not quantum and any(c.get('mustard_modules') for c in channels):
        W('warn', 'Mustard processing is set on an SD console session.')

    return {
        'console': console, 'version': version, 'compat': compat, 'sample_rate': sample_rate,
        'counts': counts, 'header_counts': hdr, 'notes': _notes(d, sections),
        'channels': channels, 'auxes': [{k: v for k, v in a.items() if k not in BUS_PRIVATE} for a in auxes],
        'groups': [{k: v for k, v in g.items() if k not in BUS_PRIVATE} for g in groups], 'devices': devices,
        'fx': fx, 'spice_rack': spice if quantum or spice else None, 'mustard': mustard,
        'structure': structure, 'damaged': damaged or None, 'warnings': warn,
        'summary': _summary(console, version, counts, sample_rate),
    }


BUS_PRIVATE = ('band', 'id', 'partner')
PREPOST = {0.0: 'post', 1.0: 'pre', 2.0: 'pre-mute', 3.0: 'mid-EQ', 4.0: 'pre-EQ', 5.0: 'pre-processing'}
LINK_PANS = {0.0: 'off', 1.0: 'on', 2.0: 'reverse'}
IO_SEC, IO_REC, IO_N = 246, 0xd2, 50


def _bus_details(d, objs, by_id, auxes, groups, grp_by_band, fx_feeds):
    """Fader, mute, link pans, group routing and output patch of every aux and group master, in place.
    Output sockets (types 4d-5f) name their source in module 12 (00, 0) as raw 00 00 <idx> <type>; a stereo bus's
    right side is its own object (type 07, found through the section 201 BussID partner)."""
    out_src = {}
    for o in objs:
        if 0x4d <= o['type'] <= 0x5f and o['recs'] and o['name'] and o['name'] != 'unused':
            raw = _raw(d, _rec_slots(d, o['recs'][0]), (0x00, 0))
            if raw and raw != b'\0\0\0\0' and raw[:2] == b'\0\0':
                out_src.setdefault((raw[3] << 8) | raw[2], []).append(_clean_name(o['name']))
    for kind, lst in (('aux', auxes), ('group', groups)):
        for bus in lst:
            o = by_id.get(bus['id'])
            if not o:
                continue
            mods = {}
            for r in o['recs']:
                mods.setdefault(_u16(d, r + 4), _rec_slots(d, r))
            fz = mods.get(0x0c, {})
            bus['fader_db'] = _f(_fget(d, fz, (0x21, 0)))
            mu = _fget(d, fz, (0x22, 0))
            bus['muted'] = None if mu is None else mu == 1.0
            if kind == 'aux':
                lp = _fget(d, fz, (0x0f, 0))
                bus['link_pans'] = LINK_PANS.get(lp) if lp is not None and lp == lp else None
                bus['feeds_fx'] = fx_feeds.get(bus['band'])
            else:
                bus['routes'] = sorted(grp_by_band[b]['n'] for (p, b), q in mods.get(0x03, {}).items()
                                       if p == 0x09 and b in grp_by_band and b != bus['band']
                                       and struct.unpack_from('<f', d, q)[0] == 1.0) or None
            outs = list(out_src.get(bus['id'], []))
            if bus['stereo'] and bus.get('partner'):
                outs += out_src.get(bus['partner'], [])
            bus['outputs'] = outs or None


def _devices(d, sections, g201):
    """The I/O devices the session declares (section 246: 50 records of 210 bytes; record k owns input socket type
    0x1c + k and output socket type 0x4e + k): [{port, name, device, inputs, mics, outputs}]."""
    span = _span(sections, IO_SEC)
    if not span or span[1] - span[0] < 4 + IO_N * IO_REC or d[span[0]:span[0] + 2] != b'\xf6\x00':
        return None
    from .patch import DEVICE_TYPES
    out = []
    for k in range(IO_N):
        tin, tout = 0x1c + k, 0x4e + k
        if tin >= 0x30 or tout >= 0x60:
            break
        gi, go = g201.get(tin), g201.get(tout)
        if not gi and not go:
            continue
        code = d[span[0] + 4 + k * IO_REC]
        ins = [r['name'] for r in (gi or {}).get('recs', []) if r['name'] and r['name'] != 'unused']
        outs = [r['name'] for r in (go or {}).get('recs', []) if r['name'] and r['name'] != 'unused']
        out.append({'port': k, 'name': _clean_name((gi or go)['name']),
                    'device': DEVICE_TYPES.get(code, 'device %02x' % code), 'inputs': len(ins),
                    'mics': sum(1 for n in ins if re.search(r'\bmic\b', n, re.I)), 'outputs': len(outs)})
    return out


OBJ_LABEL = {T_INPUT: 'Input', T_AUX: 'Aux', T_GROUP: 'Group', T_FX: 'FX', T_MTX_OUT: 'Matrix', T_CG: 'CG',
             T_SPICE: 'Spice Rack slot'}


def _nonfinite(d, objs, in_numbers, clock):
    """Labels of objects holding NaN or infinity in any slot. None of the 12.6 million slots in the 275 editor-saved
    files is non-finite, and a file with them crashed the Quantum 225 editor (decode notes, not published).
    float32 is non-finite when its exponent bits are all ones: byte 3 & 0x7f == 0x7f and byte 2 & 0x80."""
    out = []
    for k, o in enumerate(objs):
        if not k & 0xff:
            clock.tick()
        hit = False
        for r in o['recs']:
            s0 = r + 0x3e
            blk = d[s0:s0 + 8 * _u16(d, r + 0x30)]
            x3 = blk[7::8]
            if b'\x7f' not in x3 and b'\xff' not in x3:
                continue
            if any((b3 & 0x7f) == 0x7f and b2 & 0x80 for b2, b3 in zip(blk[6::8], x3)):
                hit = True
                break
        if hit:
            if o['type'] == T_INPUT:
                out.append('Input %d' % in_numbers.get(o['id'], o['index'] + 1))
            else:
                out.append('%s %d' % (OBJ_LABEL.get(o['type'], 'Object type %02x' % o['type']), o['index'] + 1))
    return out


def _list(items, n=6):
    items = list(items)
    if len(items) > n:
        return ', '.join(items[:n]) + ' and %d more' % (len(items) - n)
    return ', '.join(items[:-1]) + (' and ' if len(items) > 1 else '') + items[-1]


def _finite(x):
    """NaN and infinity (garbage floats in a damaged file) -> None, so the readout is strict JSON."""
    if isinstance(x, float):
        return x if x == x and x not in (float('inf'), float('-inf')) else None
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_finite(v) for v in x]
    return x


def _nums(ns):
    ns = sorted(ns)
    if len(ns) > 8:
        return ', '.join(map(str, ns[:8])) + ' and %d more' % (len(ns) - 8)
    return ', '.join(map(str, ns[:-1])) + (' and ' if len(ns) > 1 else '') + str(ns[-1])


def _pair_findings(channels):
    """Stereo/mono mismatches: 'Keys L' + 'Keys R' on two mono channels next to each other, or a stereo channel
    whose name ends in L or R."""
    out = []
    for a, b in zip(channels, channels[1:]):
        ma, mb = PAIR_RE.match(a['name'].strip()), PAIR_RE.match(b['name'].strip())
        if not (ma and mb) or b['n'] != a['n'] + 1:
            continue
        sa, sb = ma.group(2)[0].upper(), mb.group(2)[0].upper()
        if sa == 'L' and sb == 'R' and ma.group(1).strip().lower() == mb.group(1).strip().lower() \
                and ma.group(1).strip():
            if not a['stereo'] and not b['stereo']:
                out.append('Inputs %d and %d (%s, %s) look like a stereo pair on two mono channels. That is fine if '
                           'you want them separate.' % (a['n'], b['n'], a['name'], b['name']))
            elif a['stereo'] != b['stereo']:
                out.append('Inputs %d and %d (%s, %s) look like a pair, but one is stereo and one is mono.' % (
                    a['n'], b['n'], a['name'], b['name']))
    for c in channels:
        m = PAIR_RE.match(c['name'].strip())
        if c['stereo'] and m and m.group(1).strip() and len(c['name'].strip()) > 2 \
                and not BOTH_SIDES_RE.search(c['name'].strip()):
            out.append('Input %d (%s) is stereo but its name ends in %s.' % (c['n'], c['name'], m.group(2)))
    return out[:8]


def _a(label):
    return ('an ' if label[:2] in ('SD', 'S ') else 'a ') + label


def _A(label):
    a = _a(label)
    return a[:1].upper() + a[1:]


def _console_facts(keys):
    try:
        from . import consoles
        return {k: consoles.CONSOLES[k] for k in keys if k in consoles.CONSOLES}
    except Exception:  # noqa: BLE001 - facts are optional extras
        return {}


CONVERT = 'To use it on another console model, convert it with DiGiCo SD/Q Convert.'


def _compat(console, build, rel=None, seen=()):
    """The compatibility line. rel: the public releases of the file's console (RELEASES_BY_KEY), seen: console builds
    that were never published as an editor (SEEN_BY_KEY)."""
    if not console['known']:
        return {'line': 'We could not tell which console this file is for.', 'min_build': build}
    rel = rel or RELEASES
    a = _a(console.get('loads_on') or console['label'])
    newer = [v for v in rel if v >= build]
    first = newer[0] if newer else None
    if build in seen:
        line = ('Loads on %s running V%d or newer. V%d is console software that DiGiCo did not publish as an offline '
                'editor%s.' % (a, build, build, (', so the oldest editor that opens it is V%d' % first) if first else ''))
        return {'line': line, 'min_build': build, 'editor_min_build': first, 'convert': CONVERT,
                'convert_url': 'https://digico.biz/'}
    if first and first != build:
        line = ('Loads on %s running V%d or newer (saved by V%d, which DiGiCo did not publish for this console). Will not '
                'load on older software.' % (a, first, build))
    else:
        line = 'Loads on %s running V%d or newer. Will not load on older software.' % (a, build)
    return {'line': line, 'min_build': first or build, 'convert': CONVERT, 'convert_url': 'https://digico.biz/'}


def _summary(console, version, counts, sr):
    st = counts['inputs_stereo']
    return '%s, %s. %d inputs%s, %d auxes, %d groups%s.' % (
        console['label'], version['label'], counts['inputs'], (' (%d stereo)' % st) if st else '', counts['aux'],
        counts['groups'], (', %d kHz' % (sr // 1000)) if sr else '')


def _structure(d, sections, g201):
    """sessionmaker.validate on a file whose counts were checked against its section sizes first (validate trusts
    them and would loop or allocate on a hostile count). -> {'ok', 'errors', 'info', 'ran'}"""
    s243, s211 = _span(sections, 243), _span(sections, 211)
    errs = []
    if not s243 or not _span(sections, 212):
        return {'ok': False, 'ran': False, 'errors': ['The bank layout sections are missing.'], 'info': {}}
    nb = _u32(d, s243[0] + 2)
    if 6 + nb * 0x169 > s243[1] - s243[0]:
        return {'ok': False, 'ran': False, 'info': {},
                'errors': ['The surface bank list says %d banks but holds fewer.' % nb]}
    if not (g201.get(T_INPUT) or {}).get('recs'):
        return {'ok': False, 'ran': False, 'info': {}, 'errors': ['No input channel list was found.']}
    try:
        from . import validate
        errs, info = validate.check(d)
    except Exception as e:  # noqa: BLE001
        return {'ok': False, 'ran': False, 'info': {}, 'errors': ['The structure check could not finish (%s).'
                                                                  % type(e).__name__]}
    idmap = {r['id']: r['number'] for r in (g201.get(T_INPUT) or {}).get('recs', [])}
    plain = []
    for e in errs:
        t = _plain(e, idmap)
        if t not in plain:
            plain.append(t)
    return {'ok': not errs, 'ran': True, 'errors': plain[:20], 'detail': [str(e) for e in errs][:20],
            'info': {k: v for k, v in (info or {}).items() if k in ('inputs', 'stereo', 'engine', 'banks',
                                                                     'unbanked', 'cumulative')}}


PLAIN = [
    (r'header count mismatch: (\d+) stereo buses in the header, (\d+) right sides',
     'The header says {0} stereo buses but the file holds {1}. The DiGiCo editor crashed on files like this in our '
     'tests.'),
    (r'header count mismatch: (\d+) (.+?) in the header, (\d+) in the channel list',
     'The header says {0} {1} but the file holds {2}. The DiGiCo editor crashed on files like this in our tests.'),
    (r'an input shares engine channel', 'An input shares a processing path with the talkback input.'),
    (r'input engine channels run to \d+, past the (end|top) of the pool',
     'The inputs need more processing paths than this console layout has.'),
    (r'input engine channels collide', 'Some inputs overlap the processing paths of the aux, group or matrix buses.'),
    (r'section offsets do not ascend', 'The table of contents is out of order.'),
    (r'container does not round-trip', 'The file does not read back the same way it was written.'),
    (r'input counts disagree', 'The input count in the header does not match the channel list.'),
    (r'surface numbers are not', 'The input numbers are not 1 to N in order.'),
    (r'EngineChannel overlap at surface (\d+)', 'Input {0} shares a processing path with another input.'),
    (r'section 211 object count wrong', 'The channel count does not match the channel data.'),
    (r'section 211 objects not sorted', 'The channel data is out of order.'),
    (r'fewer channel records', 'Some channels have data but no entry in the channel list.'),
    (r'channel record ids != section 211 input ids', 'The input list and the input data do not match.'),
    (r'bad width \d+ for id (0x[0-9a-f]+)', 'Input {0} is neither mono nor stereo.'),
    (r'trailer width != StereoMode for id (0x[0-9a-f]+)', 'Input {0} is marked both mono and stereo.'),
    (r'slot .* inconsistent with width for id (0x[0-9a-f]+)', 'Input {0} mixes mono and stereo settings.'),
    (r'bank', 'The surface bank layout does not match the channels.'),
    (r'section 212', 'The surface bank layout does not match the channels.'),
]


def _plain(e, idmap=None):
    """validate.py's developer sentence -> a plain one (raw text kept for the record)."""
    e = str(e)
    for pat, text in PLAIN:
        m = re.search(pat, e)
        if m:
            args = []
            for g in m.groups():
                if g and g.startswith('0x') and idmap is not None:
                    args.append(str(idmap.get(int(g, 16), int(g, 16) & 0xff)))
                else:
                    args.append(g or '')
            return text.format(*args)
    return e[:1].upper() + e[1:] + ('' if e.endswith('.') else '.')


# ------------------------------------------------------------------------------------------------ CLI
def _text(r):
    if not r.get('ok'):
        return 'NOT OK: %s' % r['error']
    lines = [r['summary'], r['compat']['line']]
    c = r['counts']
    lines.append('matrix %d out / %d in, %d CGs, %d graphic EQs, %d snapshots, %d FX, Spice Rack %d/%d used' % (
        c['matrix_outputs'], c['matrix_inputs'], c['control_groups'], c['graphic_eqs'], c['snapshots'],
        c['fx_units'], c['spice_rack_used'], c['spice_rack_slots']))
    if r['mustard']:
        lines.append('Mustard %d of %s' % (r['mustard']['instances'], r['mustard']['cap']))
    lines.append('structure: %s' % ('OK' if r['structure']['ok'] else '; '.join(r['structure']['errors'][:3])))
    for w in r['warnings']:
        lines.append('[%s] %s' % (w['level'], w['text']))
    lines.append('%d ms' % r['ms'])
    return '\n'.join(lines)


def _arm(limit, max_mem_mb):
    """Hard stops for a CLI run (the web checker runs this in a child process): SIGALRM past the time limit,
    RLIMIT_AS past the memory cap. Both turn into a clean JSON error."""
    if max_mem_mb:
        try:
            import resource
            b = int(max_mem_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        except (ValueError, OSError):
            pass

    def on_alarm(*_):
        raise Stop('too_slow', 'Reading this file took too long. It may be damaged.')
    try:
        signal.signal(signal.SIGALRM, on_alarm)
        signal.setitimer(signal.ITIMER_REAL, limit + 1.0)
    except (ValueError, OSError):
        pass


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--limit', type=float, default=TIME_LIMIT)
    ap.add_argument('--max-mem', type=int, default=0, help='MB of address space (RLIMIT_AS) for this process')
    ap.add_argument('--name', default=None, help='file name to report (the web checker passes the upload name)')
    a = ap.parse_args(argv)
    _arm(a.limit * len(a.files), a.max_mem)
    bad = 0
    for p in a.files:
        try:
            r = inspect(p, name=a.name, time_limit=a.limit)
        except Stop as e:                       # SIGALRM outside inspect's own handler
            r = {'ok': False, 'code': e.code, 'error': e.msg}
        bad += not r.get('ok')
        if a.json:
            sys.stdout.write(json.dumps(r, separators=(',', ':'), allow_nan=False) + '\n')
        else:
            print('== %s' % os.path.basename(p))
            print(_text(r))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
