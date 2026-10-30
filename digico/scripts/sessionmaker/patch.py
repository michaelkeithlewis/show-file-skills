#!/usr/bin/env python3
"""patch.py - I/O devices, input patch, preamp gain, 48V and pad, by bytes.

Research and editor proofs: the decode notes (not published). Every structure below holds in all 116 editor-written default
sessions (14 consoles, V1455-V2242) and in real touring sessions. Names come from the editor itself: the
controller library (tControllerLibrary records in Quantum2.exe V2242 around file offset 0x8480dc / 0x852090) and
the device-type name switch (Quantum2.exe V2242, function at VA 0xc1f9ec, jump table at VA 0xc1fa0f).

I/O devices (section 246, fixed size in every file):
  f6 00 | u16 10500 | 50 records x 210 bytes. Record k is "port" k and owns the input socket type 0x1c + k and the
  output socket type 0x4e + k (record 0 = Local I/O, 0x1c / 0x4e). INTERNAL sockets (oscillator, noise, talk mic)
  are type 0x1b / 0x4d and have no record.
  +0 device type (DEVICE_TYPES)   +1 device id (rack number, MADI port, 0x80 | Optocore id - 1)
  +2 channel count byte           +3, +4, +5 flags / position (copied, never interpreted)
  +8 card slots: 6 bytes each, card type code in the first byte (0x16 = 8 mic inputs, 0x01 / 0x03 output cards)
  +0xd0 link class (1 local, 2 MADI port, 3 Waves, 4 USB, 5 DMI slot, 6 Optocore)   +0xd1 link index
  The socket names in section 201 / 211 ("1:Mic 5", "2:MADI 3") come with the device; a socket with an empty
  name does not exist on the hardware (an MQ-Rack declares 56 sockets and names 48).

Input sockets (section 211 objects, id = type << 8 | index, types 0x1b-0x2f), one module 0x11 record:
  86 analog gain (dB in 0.5 dB steps: -20 .. +60, or +10 .. +60 on D-Rack, D2-Rack and the SD9/SD11 Local I/O)
  83 phantom (48V, 0/1)   89 input pad (0/1)   81 line-mic   84 input SRC (default 1)   80 listen safe   8b AES42 pre-pad   fe copy to route (raw)
  ff name flag   c8 / c9 external integration type / id (V2232+ only)
  Gain, 48V and pad live on the socket, not on the channel: two channels on one socket share them.

Input channel, module 01 (the channel's input stage):
  (00, band 0) source route = main input, (00, band 1) alt source route = alt input. Raw 4 bytes
  00 00 <socket index> <socket type> (00 00 00 00 = not patched). The same encoding names an FX unit return
  (type 0x0e) or an INTERNAL socket (0x1b).
  (0e, 0) main/alt in (0 main, 1 alt)   (01, 0) trim dB   (01, 1) alt trim dB   (02, 0) phase
  A stereo channel stores only its LEFT socket in (00, 0); the right side is the next socket of the same device
  (see the decode notes (not published), "Stereo"). A stereo channel has no alt input: the editor clears (00, 1) on load, and it
  is 0 in every real session (567 of 567).

Surface channel numbers are used throughout (ch = the strip number, mapped with ses.ch()).
"""
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ROOT
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from ses import Session

try:
    from . import sends as _sends
except ImportError:
    import sends as _sends

SEC_IO, IO_HDR, IO_REC, IO_N = 246, 4, 0xd2, 50
IN_BASE, OUT_BASE = 0x1c, 0x4e
T_INTERNAL_IN, T_INTERNAL_OUT, T_FX = 0x1b, 0x4d, 0x0e
INPUT_SOCKET_TYPES = range(0x1b, 0x30)

INPUT, P_ROUTE, P_MAINALT, P_TRIM, P_PHASE = 0x01, 0x00, 0x0e, 0x01, 0x02
SOCKET = 0x11
P_GAIN, P_LINEMIC, P_PHANTOM, P_SRC, P_PAD = 0x86, 0x81, 0x83, 0x84, 0x89
P_LSAFE, P_AES42PAD, P_COPYTO, P_NAMEFLAG = 0x80, 0x8b, 0xfe, 0xff
GAIN_MIN, GAIN_MAX, GAIN_STEP = -20.0, 60.0, 0.5

DEVICE_TYPES = {
    0x00: 'Local I/O', 0x01: 'DiGiRack', 0x02: 'SD Rack', 0x03: 'MiniRack', 0x04: 'D-Rack', 0x05: 'SD MiniRack',
    0x06: 'NanoRack', 0x07: 'D2-Rack', 0x08: 'OrangeBox', 0x09: 'OrangeBox2', 0x0a: '4rea4', 0x0b: 'MQ-Rack',
    0x0d: 'A20-Opto', 0x0e: 'Fourier Interface', 0x0f: 'Local Dante', 0x14: 'Konductor', 0x17: 'DD32R',
    0x18: 'X6R', 0x19: 'Std MADI', 0x1a: 'Console', 0x1c: 'Waves', 0x1d: 'Opto Send', 0x1e: 'Opto Rcv',
    0x1f: 'DD2/4 mad1', 0x20: 'DD2/4 mad2', 0x21: 'MADI 64', 0x22: 'Hydra', 0x23: 'PG16', 0x24: 'PG32-AES',
    0x25: 'PG2-madi1', 0x26: 'PG2-madi2', 0x27: 'USB', 0x28: 'DMI MADI', 0x29: 'DMI ADC', 0x2a: 'DMI DAC',
    0x2b: 'DMI AES', 0x2c: 'DMI Cat5', 0x2d: 'DMI Waves', 0x2e: 'DMI Aviom', 0x2f: 'DMI Dante', 0x30: 'DMI Opto',
    0x31: 'DMI Hydra', 0x32: 'DMI Mic', 0x33: 'DMI Dante64', 0x34: 'DMI A3232', 0x35: 'DMI AMM', 0x36: 'DMI ME',
    0x38: 'DMI KLANG', 0x39: 'DMI AVB', 0x4f: 'DMI Dante64b',
}
PREAMP_DEVICES = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0d, 0x32}
PLUS10_DEVICES, PLUS10_LOCAL_MODELS, PLUS10_MIN = {0x04, 0x07}, {'SD9'}, 10.0
ROUTE_PARAMS = {0x00, 0xfe, 0xe2, 0x16}
LINK_CLASS = {1: 'local', 2: 'MADI port', 3: 'Waves', 4: 'USB', 5: 'DMI slot', 6: 'Optocore'}


def _route(idx, typ):
    return bytes((0, 0, idx & 0xff, typ & 0xff))


def _ref(raw):
    """Raw route 00 00 <index> <type> -> (type, index), or None when unpatched / not a route."""
    if raw is None or raw == b'\0\0\0\0' or raw[:2] != b'\0\0':
        return None
    return raw[3], raw[2]


def _getf(ses, off):
    return struct.unpack_from('<f', ses.d, off)[0]


def _setf(ses, off, v):
    struct.pack_into('<f', ses.d, off, float(v))


def _group_names(ses):
    """{socket type: (group name, record count)} from the section 201 group headers."""
    out = {}
    lo, hi = ses.section_span(201)
    p = lo
    while True:
        p = ses.d.find(b'\xca\x00\x6c\x00', p, hi)
        if p < 0:
            break
        n = ses.d[p + 5]
        if n <= 31 and p + 0x74 <= hi:
            out.setdefault(ses.d[p + 4], (bytes(ses.d[p + 6:p + 6 + n]).decode('latin1'),
                                          struct.unpack_from('<I', ses.d, p + 0x70)[0]))
        p += 4
    return out


def io_records(ses):
    """The 50 raw section 246 records: [(k, offset, bytes)]."""
    span = ses.section_span(SEC_IO)
    if span is None:
        raise ValueError('this session has no I/O device section (246)')
    lo, hi = span
    if ses.d[lo:lo + 2] != b'\xf6\x00' or struct.unpack_from('<H', ses.d, lo + 2)[0] != IO_N * IO_REC:
        raise ValueError('unexpected I/O device section header %s' % ses.d[lo:lo + 4].hex())
    return [(k, lo + IO_HDR + k * IO_REC, bytes(ses.d[lo + IO_HDR + k * IO_REC:lo + IO_HDR + (k + 1) * IO_REC]))
            for k in range(IO_N)]


def _sockets_of(ses, typ):
    return [o for oid, o in sorted(_sends.objects(ses).items()) if oid >> 8 == typ and SOCKET in o.mods]


def list_io(ses):
    """The I/O devices this session declares, in port order:
    [{port, device, device_code, id, name, in_type, out_type, inputs, outputs, mic_inputs, preamps, link, cards}]
    inputs / outputs count the sockets that exist (have a name); mic_inputs count the "Mic" sockets.
    The INTERNAL sources (oscillator, noise, talk mic) come first as port None."""
    groups = _group_names(ses)
    out = []
    internal = _sockets_of(ses, T_INTERNAL_IN)
    if internal:
        out.append({'port': None, 'device': 'INTERNAL', 'device_code': None, 'id': None, 'name': 'INTERNAL',
                    'in_type': T_INTERNAL_IN, 'out_type': T_INTERNAL_OUT,
                    'inputs': sum(1 for o in internal if o.name and o.name != 'unused'), 'outputs': 0,
                    'mic_inputs': 0, 'preamps': False, 'link': None, 'cards': None,
                    'sources': [o.name for o in internal if o.name and o.name != 'unused']})
    for k, off, r in io_records(ses):
        tin, tout = IN_BASE + k, OUT_BASE + k
        if tout >= 0x60 or tin >= 0x30:
            break
        if tin not in groups and tout not in groups:
            continue
        ins = [o for o in _sockets_of(ses, tin) if o.name]
        outs = [o for oid, o in sorted(_sends.objects(ses).items()) if oid >> 8 == tout and o.name]
        mics = [o for o in ins if re.search(r'\bmic\b', o.name, re.I)]
        code = r[0]
        out.append({
            'port': k, 'device': DEVICE_TYPES.get(code, 'device %#04x' % code), 'device_code': code, 'id': r[1],
            'name': (groups.get(tin) or groups.get(tout))[0], 'in_type': tin, 'out_type': tout,
            'inputs': len(ins), 'outputs': len(outs), 'mic_inputs': len(mics),
            'preamps': code in PREAMP_DEVICES and bool(mics),
            'link': {'kind': LINK_CLASS.get(r[0xd0], r[0xd0]), 'index': r[0xd1]} if r[0xd0] else None,
            'cards': [r[8 + 6 * j] for j in range(15)],
        })
    return out


def devices_summary(ses):
    """One plain line per device, for reports: 'Rack 1: MQ-Rack, 48 mic inputs, 56 outputs'."""
    lines = []
    for d in list_io(ses):
        if d['port'] is None:
            continue
        what = '%d mic inputs' % d['mic_inputs'] if d['mic_inputs'] else '%d inputs' % d['inputs']
        lines.append('%s: %s, %s, %d outputs' % (d['name'], d['device'], what, d['outputs']))
    return lines


def input_sockets(ses, existing_only=True):
    """[{id, type, idx, number, name, group, port, device, gain_db, phantom, pad}] of the input sockets."""
    groups = _group_names(ses)
    devs = {d['in_type']: d for d in list_io(ses)}
    out = []
    for oid, o in sorted(_sends.objects(ses).items()):
        t = oid >> 8
        if t not in INPUT_SOCKET_TYPES or SOCKET not in o.mods:
            continue
        if existing_only and (not o.name or o.name == 'unused'):
            continue
        d = devs.get(t, {})
        out.append({'id': oid, 'type': t, 'idx': oid & 0xff, 'number': (oid & 0xff) + 1, 'name': o.name,
                    'group': groups.get(t, ('%#04x' % t, 0))[0], 'port': d.get('port'), 'device': d.get('device'),
                    **read_preamp(ses, {'type': t, 'idx': oid & 0xff})})
    return out


def find_input_socket(ses, spec):
    """Input socket from a spec:
      ('Rack 1', 5) or 'Rack 1:5'   5th socket of that I/O group (group name from section 201, or the device name,
                                    e.g. ('MQ-Rack', 5), ('Local I/O', 1), ('MADI', 12), ('INTERNAL', 3))
      '1:Mic 5'                     the socket's own name
      {'type': 0x1d, 'idx': 4}      raw (index is 0-based)
    Sockets with no name do not exist on the hardware and are refused."""
    socks = input_sockets(ses, existing_only=False)
    hit = None
    if isinstance(spec, dict):
        hit = next((s for s in socks if s['type'] == spec['type'] and s['idx'] == spec['idx']), None)
    else:
        grp = num = None
        if isinstance(spec, (tuple, list)):
            grp, num = spec
        elif isinstance(spec, str) and ':' in spec and spec.rsplit(':', 1)[1].strip().isdigit():
            g, k = spec.rsplit(':', 1)
            if any(g.strip().lower() in (s['group'].lower(), (s['device'] or '').lower()) for s in socks):
                grp, num = g.strip(), int(k)
        if grp is not None:
            g = str(grp).lower()
            types = [t for t in dict.fromkeys(s['type'] for s in socks if s['group'].lower() == g)]
            if not types:
                types = [t for t in dict.fromkeys(s['type'] for s in socks if (s['device'] or '').lower() == g)]
            if len(types) > 1:
                raise ValueError('%r matches %d devices; use the socket name instead (%s)' % (
                    grp, len(types), ', '.join('%d:... ' % (t - IN_BASE) for t in types).strip()))
            hit = next((s for s in socks if types and s['type'] == types[0] and s['number'] == int(num)), None)
        else:
            hit = next((s for s in socks if s['name'] == spec), None)
    if hit is None:
        raise KeyError('no input socket %r in this session' % (spec,))
    if not hit['name'] or hit['name'] == 'unused':
        raise ValueError('input socket %r does not exist on this I/O (no name)' % (spec,))
    return hit


def socket_from_text(ses, text):
    """Map an input-list patch cell to a socket of this session, or None when it names a stage box slot ("A 1",
    "DM64 - 17", "DX1.3") or nothing the console has. Understands 'Local 3' / 'Local I/O 3', 'Rack 2 5' /
    'Rack 2:5' / 'Rack 2.5' / 'R2-5', 'MADI 12', 'Mic 5' (first rack with mic preamps)."""
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not t:
        return None
    pats = [(r'^local(?: i/o)?\s*(?:mic\s*)?[ :#-]?\s*(\d+)$', lambda m: ('Local I/O', int(m.group(1)))),
            (r'^(?:rack|r)\s*(\d+)\s*[ :.\-/]\s*(?:mic\s*)?(\d+)$',
             lambda m: ('Rack %s' % m.group(1), int(m.group(2)))),
            (r'^madi\s*[ :#-]?\s*(\d+)$', lambda m: ('MADI', int(m.group(1)))),
            (r'^mic\s*[ :#-]?\s*(\d+)$', None)]
    for rx, f in pats:
        m = re.match(rx, t, re.I)
        if not m:
            continue
        if f is None:
            devs = sorted((d for d in list_io(ses) if d['port'] and d['preamps']), key=lambda d: d['port'])
            spec = (devs[0]['name'], int(m.group(1))) if devs else None
        else:
            spec = f(m)
        try:
            return find_input_socket(ses, spec) if spec else None
        except (KeyError, ValueError):
            return None
    return None


def _socket_obj(ses, spec):
    s = spec if isinstance(spec, dict) and 'id' in spec else find_input_socket(ses, spec)
    return s, _sends.objects(ses)[s['id']]


def read_preamp(ses, socket_ref):
    """{'gain_db', 'phantom', 'pad'} of an input socket."""
    if isinstance(socket_ref, dict) and 'type' in socket_ref and 'id' not in socket_ref:
        o = _sends.objects(ses).get((socket_ref['type'] << 8) | socket_ref['idx'])
    else:
        o = _socket_obj(ses, socket_ref)[1]
    if o is None or SOCKET not in o.mods:
        return {'gain_db': None, 'phantom': None, 'pad': None}
    g = lambda p: _getf(ses, o.slot(SOCKET, p)) if o.has(SOCKET, p) else None
    gain, ph, pad = g(P_GAIN), g(P_PHANTOM), g(P_PAD)
    return {'gain_db': None if gain is None else round(gain, 2), 'phantom': None if ph is None else ph > 0.5,
            'pad': None if pad is None else pad > 0.5}


def gain_range(ses, socket_ref):
    """(lowest, highest) analog gain in dB the editor keeps on this socket. -20..+60 (IPAD_Q2.DOSC), except D-Rack and
    D2-Rack sockets and the SD9/SD11 Local I/O, which start at +10: the SD9 and SD12 V2242 editors raised -20 and +8
    to +10 on load (decode notes, not published), and every real gain on those preamps is +10 or more."""
    s = socket_ref if isinstance(socket_ref, dict) and 'id' in socket_ref else find_input_socket(ses, socket_ref)
    dev = next((d for d in list_io(ses) if d['in_type'] == s['type']), None)
    code = dev['device_code'] if dev else None
    if code in PLUS10_DEVICES or (code == 0x00 and ses.model in PLUS10_LOCAL_MODELS):
        return PLUS10_MIN, GAIN_MAX
    return GAIN_MIN, GAIN_MAX


def set_preamp(ses, socket_ref, gain_db=None, phantom=None, pad=None, force=False, clamp=False):
    """Write gain (dB, rounded to 0.5), 48V and pad on an input socket. None leaves a value alone.
    A gain outside gain_range() raises ValueError, or with clamp=True is moved to the nearest end.
    Sockets on devices without mic preamps (MADI, Waves, USB, Dante, line and AES inputs) are refused unless
    force=True. Returns (socket name, gain written or None)."""
    s, o = _socket_obj(ses, socket_ref)
    if not force:
        dev = next((d for d in list_io(ses) if d['in_type'] == s['type']), None)
        mic = re.search(r'\bmic\b', s['name'], re.I) or not re.match(r'^\d+:', s['name'])
        if dev is None or dev['device_code'] not in PREAMP_DEVICES or not mic:
            raise ValueError('%s (%s) has no mic preamp; gain, 48V and pad do nothing there' % (
                s['name'], (dev or {}).get('device', s['group'])))
    g = None
    if gain_db is not None:
        lo, hi = gain_range(ses, s)
        g = round(float(gain_db) / GAIN_STEP) * GAIN_STEP
        if not lo <= g <= hi:
            if not clamp:
                raise ValueError('gain %+.1f dB on %s is outside %+g..%+g dB' % (g, s['name'], lo, hi))
            g = min(max(g, lo), hi)
        _setf(ses, o.slot(SOCKET, P_GAIN), g)
    if phantom is not None:
        _setf(ses, o.slot(SOCKET, P_PHANTOM), 1.0 if phantom else 0.0)
    if pad is not None:
        _setf(ses, o.slot(SOCKET, P_PAD), 1.0 if pad else 0.0)
    return s['name'], g


def _input_rec(ses, ch):
    idx = ses.ch(ch)
    c = ses.by_index.get(idx)
    if c is None or INPUT not in c.records:
        raise KeyError('no input channel %d in this session' % ch)
    return idx, c.records[INPUT]


def _stereo(ses, ch):
    return ses.width.get(ch, 1) == 2


def right_socket(ses, left):
    """The socket a stereo channel's right side takes: the next socket of the same device.
    ValueError when that socket does not exist (the left one is the last socket of its device)."""
    try:
        return find_input_socket(ses, {'type': left['type'], 'idx': left['idx'] + 1})
    except (KeyError, ValueError):
        raise ValueError('%s is the last socket of its device, so a stereo channel there has no right side'
                         % left['name']) from None


def patch_input(ses, ch, socket_ref, alt_ref=None, use_alt=False):
    """Patch surface input `ch`: main input = socket_ref, alt input = alt_ref (None = no alt input), and select
    main (use_alt False) or alt. socket_ref None unpatches the main input.
    A stereo channel takes socket_ref as its LEFT side and the next socket of the same device as its right side;
    that socket must exist. -> {'main': name, 'right': name or None, 'alt': name or None,
    'refs': {'main', 'right', 'alt'} socket dicts} (socket names repeat in some real sessions; the refs do not)"""
    idx, rec = _input_rec(ses, ch)
    out = {'main': None, 'right': None, 'alt': None}
    main = find_input_socket(ses, socket_ref) if socket_ref is not None else None
    alt = find_input_socket(ses, alt_ref) if alt_ref is not None else None
    right = right_socket(ses, main) if main is not None and _stereo(ses, ch) else None
    out['right'] = right['name'] if right else None
    if alt is not None and _stereo(ses, ch):
        raise ValueError('input %d is stereo; a stereo channel has no alt input on DiGiCo' % ch)
    for band, s in ((0, main), (1, alt)):
        q = rec.slots[(P_ROUTE, band)]
        ses.d[q:q + 4] = _route(s['idx'], s['type']) if s else b'\0\0\0\0'
    if (P_MAINALT, 0) in rec.slots:
        _setf(ses, rec.slots[(P_MAINALT, 0)], 1.0 if (use_alt and alt is not None) else 0.0)
    out['main'] = main['name'] if main else None
    out['alt'] = alt['name'] if alt else None
    out['refs'] = {'main': main, 'right': right, 'alt': alt}
    return out


def patch_fx_return(ses, ch, unit):
    """Patch surface input `ch` to the return of FX unit `unit` (1-based; the FX track owns the units)."""
    idx, rec = _input_rec(ses, ch)
    q = rec.slots[(P_ROUTE, 0)]
    ses.d[q:q + 4] = _route(unit - 1, T_FX)


def input_of(ses, ch):
    """Read back surface input `ch`: {'main', 'right', 'alt', 'use_alt', 'gain_db', 'phantom', 'pad', 'main_ref',
    'alt_ref'} (gain / 48V / pad of the main socket; None when unpatched)."""
    idx, rec = _input_rec(ses, ch)
    out = {'main': None, 'right': None, 'alt': None, 'use_alt': False, 'gain_db': None, 'phantom': None,
           'pad': None, 'main_ref': None, 'alt_ref': None}
    objs = _sends.objects(ses)
    for band, key in ((0, 'main'), (1, 'alt')):
        q = rec.slots.get((P_ROUTE, band))
        ref = _ref(bytes(ses.d[q:q + 4])) if q is not None else None
        if ref is None:
            continue
        out[key + '_ref'] = {'type': ref[0], 'idx': ref[1]}
        o = objs.get((ref[0] << 8) | ref[1])
        if ref[0] == T_FX:
            out[key] = 'FX %d' % (ref[1] + 1)
        else:
            out[key] = o.name if o is not None else '%#04x:%d' % ref
        if key == 'main' and o is not None and SOCKET in o.mods:
            out.update(read_preamp(ses, {'type': ref[0], 'idx': ref[1]}))
            if _stereo(ses, ch):
                r = objs.get((ref[0] << 8) | (ref[1] + 1))
                out['right'] = r.name if r is not None else None
    if (P_MAINALT, 0) in rec.slots:
        out['use_alt'] = _getf(ses, rec.slots[(P_MAINALT, 0)]) > 0.5
    return out


def patch_errors(ses, warnings=None):
    """Every patched route must name an object that exists. -> list of sentences (empty = consistent).
    Pass a list as `warnings` to collect softer findings: a stereo channel whose right-hand socket does not exist
    (seen once in the real sessions: a stereo input on the last socket of a rack, so its right side is silent)."""
    errs, objs = [], _sends.objects(ses)
    for n in sorted(ses.display):
        try:
            idx, rec = _input_rec(ses, n)
        except KeyError:
            continue
        for band, side in ((0, 'main'), (1, 'alt')):
            q = rec.slots.get((P_ROUTE, band))
            ref = _ref(bytes(ses.d[q:q + 4])) if q is not None else None
            if ref is None:
                continue
            if ((ref[0] << 8) | ref[1]) not in objs:
                errs.append('input %d %s input names %02x:%d, which is not in the session' % (n, side, ref[0], ref[1]))
            elif side == 'main' and _stereo(ses, n) and ref[0] != T_FX and warnings is not None:
                r = objs.get((ref[0] << 8) | (ref[1] + 1))
                left = objs[(ref[0] << 8) | ref[1]].name
                kind = lambda nm: re.sub(r'^\d+:|\s*\d+$', '', nm or '').strip().lower()
                if r is None or not r.name:
                    warnings.append('input %d is stereo on %s, the last socket of its device, so its right side '
                                    'is silent' % (n, left))
                elif re.match(r'^\d+:', left) and re.match(r'^\d+:', r.name) and kind(left) != kind(r.name):
                    warnings.append('input %d is stereo on %s, so its right side is %s' % (n, left, r.name))
            elif side == 'alt' and _stereo(ses, n):
                errs.append('input %d is stereo and has an alt input; the editor drops it' % n)
    return errs


def patch_inputs(ses, plan, gain=True):
    """Apply a list of {'ch', 'socket', 'alt'?, 'use_alt'?, 'gain_db'?, 'phantom'?, 'pad'?} in order. A stereo channel's
    preamp settings go to both of its sockets. A gain outside the socket's range is moved to the limit.
    -> list of plain-text notes (refused preamp writes, moved gains)."""
    notes = []
    for e in plan:
        r = patch_input(ses, e['ch'], e.get('socket'), e.get('alt'), use_alt=e.get('use_alt', False))
        if not gain or e.get('socket') is None:
            continue
        if any(e.get(k) is not None for k in ('gain_db', 'phantom', 'pad')):
            sides = [r['refs']['main']] + ([r['refs']['right']] if r['refs']['right'] else [])
            for sock in sides:
                name = sock['name']
                try:
                    _, g = set_preamp(ses, sock, e.get('gain_db'), e.get('phantom'), e.get('pad'), clamp=True)
                except ValueError as err:
                    notes.append(str(err))
                    continue
                if g is not None and e.get('gain_db') is not None and abs(g - float(e['gain_db'])) > GAIN_STEP / 2:
                    notes.append('input %d: gain %+.1f dB set to %+.1f dB, the limit of %s' % (
                        e['ch'], float(e['gain_db']), g, name))
    return notes


def default_plan(ses, chans, device=None, start=1, skip_stereo_odd=True):
    """A starting patch: surface channels in order onto the mic sockets of the stage racks (port order, then the
    console's Local I/O), channel n -> socket start + n - 1, a stereo channel taking two sockets that start on an
    odd socket. When one device is full the next one takes over, and after the last one the first device's sockets
    below `start` are used; channels past every free mic socket stay unpatched. `start` past the first device's mic
    sockets is a ValueError with a plain sentence.
    device: a group or device name to use only that one. chans: [{'ch', 'stereo'?, 'phantom'?, 'gain_db'?, 'pad'?}]
    -> plan for patch_inputs()."""
    devs = sorted((d for d in list_io(ses) if d['port'] is not None and d['preamps']),
                  key=lambda d: (d['port'] == 0, d['port']))
    if device is not None:
        devs = [d for d in devs if device in (d['name'], d['device'])]
    socks = {d['in_type']: [x for x in input_sockets(ses) if x['type'] == d['in_type']
                            and re.search(r'\bmic\b', x['name'], re.I)] for d in devs}
    devs = [d for d in devs if socks[d['in_type']]]
    segs = []
    for i, d in enumerate(devs):
        lst = socks[d['in_type']]
        if i == 0 and start > len(lst):
            raise ValueError('The first mic input is %d, but %s has %d mic inputs. Pick 1 to %d.' % (
                start, d['name'] or d['device'], len(lst), len(lst)))
        segs.append((lst, start - 1 if i == 0 else 0, len(lst)))
    if devs and start > 1:
        segs.append((socks[devs[0]['in_type']], 0, start - 1))
    plan, si = [], 0
    k = segs[0][1] if segs else 0
    for c in chans:
        st = bool(c.get('stereo')) or _stereo(ses, c['ch'])
        while si < len(segs):
            if st and skip_stereo_odd and k % 2:
                k += 1
            if k + (2 if st else 1) <= segs[si][2]:
                break
            si += 1
            k = segs[si][1] if si < len(segs) else 0
        if si >= len(segs):
            break
        x = segs[si][0][k]
        e = {'ch': c['ch'], 'socket': {'type': x['type'], 'idx': x['idx']}}
        for key in ('gain_db', 'phantom', 'pad'):
            if c.get(key) is not None:
                e[key] = c[key]
        plan.append(e)
        k += 2 if st else 1
    return plan


def read_patch(ses):
    """Plain-data view of every input's patch, gain, 48V and pad, plus the devices."""
    return {'devices': list_io(ses),
            'inputs': [dict(ch=n, name=ses.by_index[ses.ch(n)].name, stereo=_stereo(ses, n), **input_of(ses, n))
                       for n in sorted(ses.display)]}


MADI_LINKS = {'SD9': range(0, 3), 'SDC': range(0, 2)}
SEC_DEVICE_DONORS = {
    'SD Rack': ('q338', 1), 'MQ-Rack': ('q225', 1), 'D-Rack': ('sd9', 1), 'D2-Rack': ('sd12', 1),
    'Std MADI': ('q225', 2), 'MADI 64': ('sd12', 2), 'USB': ('sd12', 3), 'Local Dante': ('q112', 3),
}
RACK_ALIASES = {'sd-rack': 'SD Rack', 'sdrack': 'SD Rack', 'sd rack': 'SD Rack', 'mq-rack': 'MQ-Rack',
                'mq rack': 'MQ-Rack', 'd-rack': 'D-Rack', 'drack': 'D-Rack', 'd2-rack': 'D2-Rack',
                'd2 rack': 'D2-Rack', 'madi': 'Std MADI', 'madi 64': 'MADI 64'}


def _blocks(s201):
    """The two patch-bay page blocks at the head of section 201 -> ([{'lines', 'ids'}] x 2, end offset)."""
    p, out = 2, []
    for _ in range(2):
        n = struct.unpack_from('<I', s201, p)[0]
        lines = bytes(s201[p + 4:p + 4 + n]).split(b'\r\n')
        if lines and lines[-1] == b'':
            lines = lines[:-1]
        q = p + 4 + n
        ids = [bytes(s201[q + 4 * i:q + 4 * i + 4]) for i in range(len(lines))]
        out.append({'lines': lines, 'ids': ids})
        p = q + 4 * len(lines)
    return out, p


def _blocks_bytes(blocks):
    out = bytearray()
    for b in blocks:
        txt = b''.join(x + b'\r\n' for x in b['lines'])
        out += struct.pack('<I', len(txt)) + txt + b''.join(b['ids'])
    return out


def _walk_groups(s201, lo):
    """[(header offset, type, records end)] of the section 201 groups from offset lo. Groups start 'ca 00 6c 00';
    Quantum files also hold one 'd1 00 6c 00' group (type 0x14, "Nodal Processing", no records), which is why the
    group count is one higher there."""
    out, p = [], lo
    while p + 0x74 <= len(s201) and s201[p] in (0xca, 0xd1) and s201[p + 1:p + 4] == b'\x00\x6c\x00':
        cnt = struct.unpack_from('<I', s201, p + 0x70)[0]
        q = p + 0x74
        for _ in range(cnt):
            q += 4 + struct.unpack_from('<H', s201, q + 2)[0]
        out.append((p, s201[p + 4], q))
        p = q
    return out


def _is_io(t):
    return 0x1b <= t <= 0x2f or 0x4d <= t <= 0x5f


def _renumber(name, k):
    return re.sub(r'^\d+:', '%d:' % k, name) if name else name


def template_from(data, port):
    """A device template from an editor-written file: its section 246 record, socket names, page labels, group
    headers and socket slot values (port = record index k >= 1)."""
    from . import layout
    s = Session(data)
    c = layout.Container(bytes(s.d))
    s201 = c.sec(201)[1]
    tin, tout = IN_BASE + port, OUT_BASE + port
    blocks, gstart = _blocks(s201)
    groups = {t: (p, e) for p, t, e in _walk_groups(s201, gstart + 4)}
    if tin not in groups or tout not in groups:
        raise ValueError('port %d has no socket groups in the template file' % port)
    objs = _sends.objects(s)

    def side(t, mod):
        p, e = groups[t]
        hdr = bytes(s201[p:p + 0x74])
        q, names = p + 0x74, []
        while q < e:
            names.append(bytes(s201[q + 9:q + 9 + s201[q + 8]]).decode('latin1'))
            q += 4 + struct.unpack_from('<H', s201, q + 2)[0]
        vals = []
        for i in range(len(names)):
            o = objs.get((t << 8) | i)
            vals.append({k: bytes(s.d[off:off + 4]) for k, off in (o.mods.get(mod, {}) if o else {}).items()})
        labels = [(blocks[0 if t < 0x4d else 1]['lines'][j], blocks[0 if t < 0x4d else 1]['ids'][j])
                  for j in range(len(blocks[0 if t < 0x4d else 1]['ids']))
                  if blocks[0 if t < 0x4d else 1]['ids'][j][1] == t]
        return {'header': hdr, 'names': names, 'values': vals, 'labels': labels}
    rec = io_records(s)[port][2]
    return {'record': rec, 'device': DEVICE_TYPES.get(rec[0], '%#04x' % rec[0]), 'port': port,
            'in': side(tin, SOCKET), 'out': side(tout, 0x12), 'build': s.version, 'model': s.model}


def free_ports(ses):
    """Record indexes k >= 1 with no device and no socket groups."""
    groups = _group_names(ses)
    return [k for k, _, r in io_records(ses)
            if 1 <= k <= 0x13 and not any(r[:6]) and not r[0xd0] and IN_BASE + k not in groups
            and OUT_BASE + k not in groups]


def add_device(data, template, port=None, dev_id=None, link_index=None, name=None):
    """Add the template's device to a session (bytes in, bytes out). port: record index (default: the first free
    one); dev_id / link_index: the device id byte and link index (default: the first ones no other device of the
    same link class uses); name: the I/O group name (default "Rack <id>" for racks, else the template's).
    Returns (new bytes, info dict)."""
    from . import layout
    s = Session(data)
    if port is None:
        fp = free_ports(s)
        if not fp:
            raise ValueError('this session has no free I/O port')
        port = fp[0]
    elif port not in free_ports(s):
        raise ValueError('port %d is in use' % port)
    tin, tout = IN_BASE + port, OUT_BASE + port
    rec = bytearray(template['record'])
    cls = rec[0xd0]
    taken = {(r[0xd0], r[0xd1]) for _, _, r in io_records(s) if r[0xd0]}
    if link_index is None:
        link_index = next(i for i in range(0, 64) if (cls, i) not in taken)
    if (cls, link_index) in taken:
        raise ValueError('link %s %d is in use' % (LINK_CLASS.get(cls, cls), link_index))
    if dev_id is None:
        dev_id = link_index + 1 if cls == 2 else rec[1]
    rec[1] = dev_id
    rec[0xd1] = link_index
    rec[5] = 0
    is_rack = rec[0] in PREAMP_DEVICES
    gname = name or ('Rack %d' % dev_id if is_rack else
                     bytes(template['in']['header'][6:6 + template['in']['header'][5]]).decode('latin1'))

    c = layout.Container(bytes(s.d))
    s246 = c.sec(SEC_IO)[1]
    s246[IO_HDR + port * IO_REC:IO_HDR + (port + 1) * IO_REC] = rec
    s201 = c.sec(201)[1]
    blocks, gend = _blocks(s201)
    for b, side, t in ((blocks[0], template['in'], tin), (blocks[1], template['out'], tout)):
        want = [(lab, bytes((pid[0], t, 0, 0))) for lab, pid in side['labels']]
        have = [j for j, pid in enumerate(b['ids']) if pid[1] == t]
        for j, (lab, pid) in zip(have, want):
            b['lines'][j] = lab
        for lab, pid in want[len(have):]:
            b['lines'].append(lab)
            b['ids'].append(pid)
    groups = _walk_groups(s201, gend + 4)
    io = [g for g in groups if _is_io(g[1])]
    if not io:
        raise ValueError('no I/O groups in section 201')
    tmpl_in = next((g for g in io if 0x1c < g[1] <= 0x2f), None)
    tmpl_out = next((g for g in io if 0x4e < g[1] <= 0x5f), None)
    if tmpl_in is None or tmpl_out is None:
        raise ValueError('add_device needs one stage device besides the Local I/O to copy the record layout from')
    cb_in = bytes(s201[tmpl_in[0] + 0x74:tmpl_in[0] + 0x74 + 4 + s201[tmpl_in[0] + 0x76]])
    cb_out = bytes(s201[tmpl_out[0] + 0x74:tmpl_out[0] + 0x74 + 4 + s201[tmpl_out[0] + 0x76]])

    def group(side, t, cb_t):
        hdr = bytearray(s201[(tmpl_in if t < 0x4d else tmpl_out)[0]:][:0x74])
        th = side['header']
        hdr[0x6c:0x70] = th[0x6c:0x70]
        hdr[4] = t
        hdr[5:0x26] = bytes([len(gname)]) + gname.encode('latin1') + b'\0' * (32 - len(gname))
        struct.pack_into('<I', hdr, 0x70, len(side['names']))
        out = bytearray(hdr)
        for i, nm in enumerate(side['names']):
            r = bytearray(cb_t)
            struct.pack_into('<HH', r, 4, (t << 8) | i, i + 1)
            nm = _renumber(nm, port)
            r[8:40] = bytes([len(nm)]) + nm.encode('latin1') + b'\0' * (31 - len(nm))
            if len(r) >= 88:
                struct.pack_into('<H', r, 84, i)
            out += r
        return out
    new_groups = group(template['in'], tin, cb_in) + group(template['out'], tout, cb_out)
    ins_at = io[-1][2]
    cnt_at = gend
    head = _blocks_bytes(blocks)
    body = bytearray(s201[2:])
    body = body[:ins_at - 2] + new_groups + body[ins_at - 2:]
    old_head_len = gend - 2
    rest = body[old_head_len:]
    struct.pack_into('<I', rest, 0, struct.unpack_from('<I', rest, 0)[0] + 2)
    c.sec(201)[1] = bytearray(s201[:2]) + head + rest
    s211 = c.sec(211)[1]
    objs, tail = layout.objects(s211)
    def tmpl_obj(lo, hi, mod):
        return next(o for o in objs if lo <= layout.obj_id(o) >> 8 <= hi and layout.obj_id(o) >> 8 not in
                    (T_INTERNAL_IN, T_INTERNAL_OUT, IN_BASE, OUT_BASE) and
                    any(t == mod for _, t, _ in layout.obj_records(o)))
    o_in, o_out = tmpl_obj(0x1d, 0x2f, SOCKET), tmpl_obj(0x4f, 0x5f, 0x12)
    new = []
    for side, t, ot in ((template['in'], tin, o_in), (template['out'], tout, o_out)):
        for i, nm in enumerate(side['names']):
            o = bytearray(ot)
            for p_, typ, cnt in layout.obj_records(o):
                s0 = p_ + 4 + 0x3a
                for k in range(cnt):
                    q = s0 + 8 * k
                    v = side['values'][i].get((o[q], o[q + 2]))
                    if o[q] in ROUTE_PARAMS:
                        o[q + 4:q + 8] = b'\0\0\0\0'
                    elif v is not None:
                        o[q + 4:q + 8] = v
                    elif o[q] in (0xc8, 0xc9, P_GAIN, P_PHANTOM, P_PAD):
                        o[q + 4:q + 8] = b'\0\0\0\0'
            nm = _renumber(nm, port)
            f = bytes([len(nm)]) + nm.encode('latin1') + b'\0' * (31 - len(nm))
            tt = len(o) - 41
            struct.pack_into('<H', o, tt + 2, (t << 8) | i)
            o[tt + 4:tt + 36] = f
            for p_, _, _ in layout.obj_records(o):
                o[p_ + 8:p_ + 40] = f
            new.append(o)
    allo = sorted(objs + new, key=layout.obj_id)
    out = bytearray(s211[:6])
    struct.pack_into('<I', out, 2, len(allo))
    for o in allo:
        out += o
    out += tail
    c.sec(211)[1] = out
    data2 = c.build()
    lim = MADI_LINKS.get(s.model) if cls == 2 else None
    return data2, {'port': port, 'device': template['device'], 'id': dev_id, 'link': (cls, link_index),
                   'name': gname, 'inputs': len(template['in']['names']), 'outputs': len(template['out']['names']),
                   'connected': None if lim is None else link_index in lim, 'template_build': template['build']}


def remove_device(data, port):
    """Remove the device on `port` (record index >= 1): its section 246 record, both socket groups, every socket
    object, its patch-bay page labels (the page ids stay, as on the defaults' empty ports) and every route to its
    sockets (input patches, insert sends/returns, direct outs, key inputs, bus outputs, socket copies).
    Returns (new bytes, number of routes cleared)."""
    from . import layout
    if port < 1:
        raise ValueError('port 0 is the console\'s Local I/O')
    tin, tout = IN_BASE + port, OUT_BASE + port
    c = layout.Container(bytes(data))
    s246 = c.sec(SEC_IO)[1]
    empty = next(bytes(s246[IO_HDR + k * IO_REC:IO_HDR + (k + 1) * IO_REC]) for k in range(IO_N - 1, 0, -1)
                 if not any(s246[IO_HDR + k * IO_REC:IO_HDR + k * IO_REC + 8]))
    s246[IO_HDR + port * IO_REC:IO_HDR + (port + 1) * IO_REC] = empty
    s201 = c.sec(201)[1]
    blocks, gend = _blocks(s201)
    for b in blocks:
        for j, pid in enumerate(b['ids']):
            if pid[1] in (tin, tout):
                b['lines'][j] = b''
    groups = _walk_groups(s201, gend + 4)
    gone = [(p_, e) for p_, t, e in groups if t in (tin, tout)]
    if not gone:
        raise ValueError('port %d has no socket groups' % port)
    rest = bytearray(s201[gend:])
    for p_, e in sorted(gone, reverse=True):
        del rest[p_ - gend:e - gend]
    struct.pack_into('<I', rest, 0, struct.unpack_from('<I', rest, 0)[0] - len(gone))
    c.sec(201)[1] = bytearray(s201[:2]) + _blocks_bytes(blocks) + rest
    s211 = c.sec(211)[1]
    objs, tail = layout.objects(s211)
    keep = [o for o in objs if layout.obj_id(o) >> 8 not in (tin, tout)]
    cleared = 0
    for o in keep:
        for p_, typ, cnt in layout.obj_records(o):
            s0 = p_ + 4 + 0x3a
            for k in range(cnt):
                q = s0 + 8 * k
                if o[q] in ROUTE_PARAMS and o[q + 4:q + 6] == b'\0\0' and o[q + 7] in (tin, tout):
                    o[q + 4:q + 8] = b'\0\0\0\0'
                    cleared += 1
    out = bytearray(s211[:6])
    struct.pack_into('<I', out, 2, len(keep))
    for o in keep:
        out += o
    out += tail
    c.sec(211)[1] = out
    return c.build(), cleared


def replace_device(data, port, rack_type, name=None):
    """Swap the device on `port` for `rack_type`, on the same link (MADI port) and with the same id when the link
    class matches. Routes to the old device's sockets are cleared. Returns (new bytes, info)."""
    s = Session(data)
    old = io_records(s)[port][2]
    tmpl = _template(rack_type, s.version)
    data2, cleared = remove_device(data, port)
    same = old[0xd0] == tmpl['record'][0xd0] and old[0xd0]
    data3, info = add_device(data2, tmpl, port=port, dev_id=old[1] if same and old[1] else None,
                             link_index=old[0xd1] if same else None, name=name)
    info['replaced'] = DEVICE_TYPES.get(old[0], '%#04x' % old[0])
    info['routes_cleared'] = cleared
    return data3, info


DEVICE_MIN_BUILD = {'Local Dante': 2126}


def _template(rack_type, build):
    dev = RACK_ALIASES.get(str(rack_type).strip().lower(), rack_type)
    if dev not in SEC_DEVICE_DONORS:
        raise ValueError('no template for %r; known: %s' % (rack_type, ', '.join(sorted(SEC_DEVICE_DONORS))))
    if build < DEVICE_MIN_BUILD.get(dev, 0):
        raise ValueError('the V%d editor does not know the %s; it needs V%d or later' % (
            build, dev, DEVICE_MIN_BUILD[dev]))
    for path, port in _donor_paths(dev, build):
        t = template_from(open(path, 'rb').read(), port)
        if t['device'] == dev:
            return t
    raise ValueError('no editor-written default carries a %s' % dev)


def _donor_paths(device, build):
    """Donor defaults for a device: the target build first, then the other builds newest first."""
    key, port = SEC_DEVICE_DONORS[device]
    d = (os.environ.get('SM_BASELINES') or os.path.join(ROOT, 'baselines'))
    files = os.listdir(d) if os.path.isdir(d) else []
    builds = sorted((int(m.group(1)) for m in (re.match(r'^%s_v(\d+)\.ses$' % key, f) for f in files) if m),
                    reverse=True)
    order = ([build] if build in builds else []) + [b for b in builds if b != build]
    return [(os.path.join(d, '%s_v%d.ses' % (key, b)), port) for b in order]


def add_rack(data, rack_type, count=1):
    """Add `count` devices of `rack_type` ('SD Rack', 'D-Rack', 'D2-Rack', 'MQ-Rack', 'Std MADI', 'MADI 64', 'USB',
    'Local Dante'; common spellings like 'SD-Rack' work) to a session on free I/O ports, each on the first free link
    of its class. The template comes from the editor-written default of a console that ships with that device, same
    build when one exists. Returns (new bytes, [info per device]).
    The editor keeps the device when that link exists on the console (Q225: MADI link 1); on a link the console
    lacks it keeps the device but marks it not connected (SD9: link 3, id set to 0). Use replace_device() to swap an
    existing device instead (decode notes, not published)."""
    tmpl = _template(rack_type, Session(data).version)
    infos = []
    for _ in range(count):
        data, info = add_device(data, tmpl)
        infos.append(info)
    return data, infos


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: python3 -m sessionmaker.patch file.ses [rows]  (I/O devices and the input patch)')
        sys.exit(0 if len(sys.argv) > 1 else 2)
    import json
    s = Session(sys.argv[1])
    for line in devices_summary(s):
        print(line)
    rows = read_patch(s)['inputs']
    for r in rows[:int(sys.argv[2]) if len(sys.argv) > 2 else 12]:
        print(json.dumps({k: r[k] for k in ('ch', 'name', 'stereo', 'main', 'right', 'alt', 'gain_db', 'phantom',
                                            'pad')}))
