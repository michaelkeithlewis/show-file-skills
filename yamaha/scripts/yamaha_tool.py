#!/usr/bin/env python3
"""Read Yamaha console show files, and make only the edits that a black-box test proved.

Generation 1 is CL and QL (.CLF). Generation 2 is DM7, DM5, DM3 and TF (.dm7f, .dmxf, .dm3f, .tff), all in the
'#YAMAHA MBDF' container. ../references/FORMAT.md has the layout and the test behind every fact used here.
Python 3.8 or later, standard library only.

Read:
  yamaha_tool.py show  SHOW [--console cl5] [--json]   channels, buses, DCAs, scenes, and what this file can change
  yamaha_tool.py check SHOW                            the container, every checksum or schema, every entry
  yamaha_tool.py ports SHOW [--console ql1]            the patch sources this tool can write on this console

Write (each one reads IN, writes a new file OUT, and keeps every byte it does not change):
  yamaha_tool.py rename  IN OUT CHANNELS NAME [NAME ...]          one name per channel, in order
  yamaha_tool.py colour  IN OUT CHANNELS COLOUR                   blue, orange, red, ... (see 'show --json')
  yamaha_tool.py icon    IN OUT CHANNELS ICON                     CL and QL only: kick, snare, dynamic, ...
  yamaha_tool.py fader   IN OUT CHANNELS DB                       a number of dB, or off (-inf)
  yamaha_tool.py on      IN OUT CHANNELS on|off                   the channel ON key (off = muted)
  yamaha_tool.py hpf     IN OUT CHANNELS [--on | --off] [--freq HZ]
  yamaha_tool.py patch   IN OUT CHANNELS SOURCE                   "DANTE 3", "OMNI 2", "INPUT 12", none
  yamaha_tool.py preamp  IN OUT CHANNELS [--gain DB] [--48v on|off]   the head amp the channel is patched to
  yamaha_tool.py dca     IN OUT CHANNELS DCA [--mode add|remove|only] CL and QL only
  yamaha_tool.py busname IN OUT BUS NAME                          CL and QL only: mix3, matrix1, dca2, mute1
  yamaha_tool.py apply   IN OUT OPS.json                          several changes in one pass

CHANNELS: 3 | 1-8 | 1,3,5-8 | st1l / st1r (CL and QL ST IN 1L / 1R) | all.
Every write takes --dry-run (check everything, write nothing), --console (CL/QL: the file does not record the model)
and --all-scenes (CL scene format 7 only: names, colours and patch also go to every stored scene).

OPS.json is a list of changes, run in order:
  [{"op": "rename", "target": {"channels": [1, 2]}, "names": ["Kick In", "Kick Out"]},
   {"op": "set", "target": {"ids": ["ch1"]}, "colour": "red", "fader_db": -5, "on": true,
    "hpf": {"on": true, "freq": 80}},
   {"op": "patch", "target": {"channels": [1]}, "source": "DANTE 1"},
   {"op": "preamp", "target": {"channels": [65]}, "gain_db": 30, "phantom": true},
   {"op": "dca", "target": {"channels": [1, 2]}, "dca": 1, "mode": "add"},
   {"op": "name_bus", "bus": "mix1", "name": "Vox Wdg"}]
A channel op also takes "scenes": "current" (default) or "all".

The tool refuses, with one sentence, any file or change it can not make safely: user key files, scene-only and
library files, RIVAGE PM files, and every write that no editor test covered. If any change is refused, nothing is
written. It never changes the file type, the firmware version or the scene format.

Open every written file in the matching Yamaha editor, check it, and save it there. Load only that save on a console,
at prep, never first at the show.
"""
import argparse
import hashlib
import json
import math
import os
import struct
import sys
import zlib


class Refused(ValueError):
    """A file or a change this tool will not take. The text is one plain sentence."""


MSG_NOT_YAMAHA = ("This isn't a Yamaha show file. Use the file the console or the Yamaha editor saved: .CLF for CL "
                  "and QL, .dm7f or .dmxf for DM7 and DM5, .dm3f for DM3 or .tff for TF.")
MSG_DAMAGED = ("This Yamaha file is damaged or in a layout this tool can't read. Open it in the Yamaha editor and save "
               "it again.")
MSG_USER_KEY = ("This is a Yamaha user key file. It holds passwords, so this tool does not open it. Use the show file "
                "instead (.CLF, .dm7f, .dmxf, .dm3f or .tff).")
MAX_BYTES = 32 * 1024 * 1024


def _damaged():
    return Refused(MSG_DAMAGED)


def _text(raw):
    return ''.join(chr(c) if 0x20 <= c < 0x7f else '?' for c in raw)


def clean_name(s, limit):
    """Typed text -> a channel name, or Refused. Printable ASCII only; a longer name is refused, never cut."""
    if not isinstance(s, str):
        raise Refused('A name must be text.')
    s = s.strip()
    if any(not (0x20 <= ord(c) < 0x7f) for c in s):
        raise Refused('names use plain letters, numbers and symbols only.')
    if len(s) > limit:
        raise Refused('names hold %d characters on this console. Make it shorter.' % limit)
    return s


def _id_label(i):
    """'ch80' -> 'CH 80', 'st1l' -> 'ST IN 1L', for a sentence."""
    i = str(i)[:12]
    if i.startswith('ch') and i[2:].isdigit():
        return 'CH %s' % i[2:]
    if i.startswith('st') and i[2:-1].isdigit() and i[-1:] in ('l', 'r'):
        return 'ST IN %s%s' % (i[2:-1], i[-1].upper())
    return 'channel %s' % i


def _bool_field(v, what):
    if not isinstance(v, bool):
        raise Refused('%s is true or false.' % what)
    return v


def _number(v, what):
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        raise Refused(what)
    if x != x:
        raise Refused(what)
    return x


# =====================================================================================================================
# Generation 1: CL and QL (.CLF). Container facts: FORMAT.md section 2. Value facts: FORMAT.md section 3.
# =====================================================================================================================
HEAD, INDEX, DATA = 0x0100, 0x0200, 0x0300
OUTER_FAMILY = 0x0170
KIND_ALL, KIND_SCENE, KIND_USER_KEY = 0x05c0, 0x1040, 0x04c0
SCENE_BLOCK, CURRENT = 0x10, 0xFFFE
SECTION_MAGIC = 0x6cff
CLF_MAX_DEPTH, CLF_MAX_RECORDS, CLF_MAX_SECTIONS = 8, 40000, 8


def word_sum(b):
    """The checksum of a data block: NOT(sum of its big-endian 32-bit words) mod 2**32."""
    if len(b) % 4:
        b = bytes(b) + b'\0' * (4 - len(b) % 4)
    total = sum(struct.unpack('>%dI' % (len(b) // 4), b)) if b else 0
    return (~total) & 0xffffffff


def _u16(d, o):
    return (d[o] << 8) | d[o + 1]


def clf_kind(data):
    """The outer head's kind word, or None when the bytes do not start like a .CLF."""
    if len(data) < 16 or _u16(data, 0) != HEAD or _u16(data, 2) != 0 or _u16(data, 8) != OUTER_FAMILY:
        return None
    return _u16(data, 10)


class Clf:
    def __init__(self, data):
        self.data = data
        self.kind = None
        self.comment = b''
        self.leaves = []            # (path, body offset, body size) of every data record
        self.scenes = {}            # scene id -> (body offset, [(tag, data offset, data size)])
        self.bad_checksums = 0
        self.checked = 0

    def memapi(self, sid):
        """(absolute offset, size) of a scene's MEMAPI data, or None."""
        s = self.scenes.get(sid)
        if not s:
            return None
        for tag, off, size in s[1]:
            if tag == 'MEMAPI':
                return off, size
        return None

    def stored_ids(self):
        return sorted(i for i in self.scenes if 1 <= i <= 300)


def _scene_sections(off, length, d):
    out, o = [], 0
    while o < length:
        if length - o < 20 or len(out) >= CLF_MAX_SECTIONS:
            raise _damaged()
        a = off + o
        magic, zero, hl = struct.unpack_from('<HHI', d, a)
        size = struct.unpack_from('<I', d, a + 16)[0]
        if magic != SECTION_MAGIC or zero != 0 or hl != 20 or size > length - o - hl:
            raise _damaged()
        raw = bytes(d[a + 8:a + 16])
        tag = raw.split(b'\0', 1)[0]
        if not tag or not all(0x20 < c < 0x7f for c in tag) or raw[len(tag):].strip(b'\0'):
            raise _damaged()
        out.append((tag.decode('ascii'), a + hl, size))
        o += hl + size
    return out


def clf_parse(data, verify=True):
    """Walk a .CLF record tree to its exact end and check every checksum."""
    d = bytes(data)
    if len(d) > MAX_BYTES:
        raise Refused('The file is over 32 MB. Yamaha show files are smaller than that.')
    kind = clf_kind(d)
    if kind is None:
        raise _damaged()
    if kind == KIND_USER_KEY:
        raise Refused(MSG_USER_KEY)
    if kind == KIND_SCENE:
        raise Refused('This is a CL or QL scene file, not a whole show. Save the show in the editor with File > Save '
                      'and use that.')
    if kind != KIND_ALL:
        raise Refused('This CL or QL file is not a whole show (it may be a library file). Use the show file instead.')
    c = Clf(d)
    c.kind = kind
    spans, visited, n = [], set(), len(d)

    def record(off):
        if off < 0 or off > n - 8 or off in visited:
            raise _damaged()
        visited.add(off)
        if len(visited) > CLF_MAX_RECORDS:
            raise _damaged()
        t, z, ln = struct.unpack_from('>HHI', d, off)
        if z != 0 or ln > n - off - 8:
            raise _damaged()
        spans.append((off, off + 8 + ln))
        return t, ln

    def container(off, depth, path, outer):
        if depth > CLF_MAX_DEPTH:
            raise _damaged()
        t, ln = record(off)
        if t != HEAD or (outer and ln != 40) or (not outer and ln != 8):
            raise _damaged()
        fam, ckind, count, z = struct.unpack_from('>HHHH', d, off + 8)
        if z != 0:
            raise _damaged()
        if outer:
            c.comment = d[off + 16:off + 48]
        io = off + 8 + ln
        t2, ln2 = record(io)
        if t2 != INDEX or ln2 != count * 8:
            raise _damaged()
        for i in range(count):
            eid, z2, eo = struct.unpack_from('>HHI', d, io + 8 + i * 8)
            if z2 != 0 or eo > n - 8:
                raise _damaged()
            et = _u16(d, eo)
            p = path + ((ckind, eid),)
            if et == HEAD:
                container(eo, depth + 1, p, False)
            elif et == DATA:
                _, eln = record(eo)
                c.leaves.append((p, eo + 8, eln))
            else:
                raise _damaged()

    container(0, 0, (), True)
    spans.sort()
    pos = 0
    for a, b in spans:
        if a != pos:
            raise _damaged()
        pos = b
    if pos != n:
        raise _damaged()
    for path, off, size in c.leaves:
        if not size:
            continue
        if size >= 2 and d[off:off + 2] == b'\xff\x6c':
            secs = _scene_sections(off, size, d)
            if path[0][1] == SCENE_BLOCK and len(path) == 2:
                c.scenes[path[-1][1]] = (off, secs)
            for tag, a, sz in secs:
                if tag == 'MEMAPI':
                    if sz < 8 or sz % 4:
                        raise _damaged()
                    c.checked += 1
                    if word_sum(d[a:a + sz - 4]) != struct.unpack_from('>I', d, a + sz - 4)[0]:
                        c.bad_checksums += 1
        else:
            if size < 4 or size % 4:
                raise _damaged()
            c.checked += 1
            if word_sum(d[off:off + size - 4]) != struct.unpack_from('>I', d, off + size - 4)[0]:
                c.bad_checksums += 1
    if verify and c.bad_checksums:
        raise Refused("This file's checksums don't match, so the Yamaha editor would refuse it too. Save it again in "
                      "the editor.")
    if c.memapi(CURRENT) is None:
        raise _damaged()
    return c


def clf_rewrite(c, scenes):
    """scenes: {scene id: new MEMAPI data (same size)}. Each scene that changed gets its checksum fixed. Nothing
    moves: every other byte of the file stays as it was."""
    buf = bytearray(c.data)
    for sid, new in scenes.items():
        base, size = c.memapi(sid)
        if len(new) != size:
            raise _damaged()
        if bytes(new[:size - 4]) != bytes(buf[base:base + size - 4]):
            buf[base:base + size - 4] = new[:size - 4]
            struct.pack_into('>I', buf, base + size - 4, word_sum(bytes(buf[base:base + size - 4])))
    return bytes(buf)


# ---- CL/QL scene values (offsets from the start of a scene's MEMAPI data, big-endian). Test ids: FORMAT.md 1.2 ------
SCENE_FORMATS = {38824: 5, 39448: 6, 39452: 7}    # MEMAPI data size -> scene format (BB-RESAVE)
VERSION_OFF = 16                                   # u16 scene format (BB-RESAVE)
NAME_LEN = 8
IN_NAMES = (29240, 96)          # BB-CSV-1: characters 1-4 of every slot, then 5-8 of every slot
MIX_NAMES = (30604, 24)         # BB-CSV-1
MTX_NAMES = (30796, 8)          # BB-CSV-1
STM_NAMES = (30860, 3)          # BB-CSV-1: ST L, ST R, MONO
DCA_NAMES = (21524, 16)         # BB-CSV-1
MUTE_NAMES = (34392, 8)         # BB-LOAD-G
IN_ICON, IN_COLOUR, IN_PATCH = 30008, 30104, 28971   # BB-CSV-1, BB-CSV-1, BB-CSV-2 (u8 per slot)
MIX_ICON, MIX_COLOUR = 30884, 30908                  # BB-CSV-1
MTX_ICON, MTX_COLOUR = 30932, 30940                  # BB-CSV-1
STM_ICON, STM_COLOUR = 30948, 30951                  # BB-CSV-1
HPF_FREQ = 6704                 # BB-LOAD-F: u8 index per slot
CH_ON, HPF_ON = 2382, 6692      # BB-LOAD-F: 12-byte masks, slot n = bit (n-1)%8 of byte (n-1)//8, 1 = on
DCA_ASSIGN = 10004              # BB-LOAD-G: DCA k mask at 10004 + 12(k-1)
MUTE_ASSIGN = 9908              # BB-SAVE-H: mute group k mask at 9908 + 12(k-1) (read only here)
MASK_LEN = 12
FADER, FADER_MAX = 2586, 1023   # BB-LOAD-F: u16 per slot
HA_PHANTOM, HA_GAIN = 1373, 1377  # BB-LOAD-F, BB-QL: 4-byte mask and u8 per local port (dB = value - 6)
HA_MIN_DB, HA_MAX_DB = -6, 66   # BB-LOAD-F, BB-LOAD-R

HPF_HZ = dict(zip(range(4, 64), (
    20.0, 21.2, 22.4, 23.6, 25.0, 26.5, 28.0, 30.0, 31.5, 33.5, 35.5, 37.5, 40.0, 42.5, 45.0, 47.5, 50.0, 53.0, 56.0,
    60.0, 63.0, 67.0, 71.0, 75.0, 80.0, 85.0, 90.0, 95.0, 100.0, 106.0, 112.0, 118.0, 125.0, 132.0, 140.0, 150.0,
    160.0, 170.0, 180.0, 190.0, 200.0, 212.0, 224.0, 236.0, 250.0, 265.0, 280.0, 300.0, 315.0, 335.0, 355.0, 375.0,
    400.0, 425.0, 450.0, 475.0, 500.0, 530.0, 560.0, 600.0)))   # BB-LOAD-F: what the editor showed for each index


def fader_db(v):
    """Stored CL/QL fader value -> dB as CL Editor shows it; None for -inf (0). BB-LOAD-F, BB-LOAD-R."""
    if v <= 0:
        return None
    if v <= 15:
        return -141.0 + 3 * v
    if v <= 33:
        return -111.0 + v
    if v <= 223:
        return round(-78.0 + 0.2 * (v - 33), 2)
    if v <= 423:
        return round(-40.0 + 0.1 * (v - 223), 2)
    return round(0.05 * (v - 823), 2)


FADER_TABLE = [fader_db(v) for v in range(FADER_MAX + 1)]


def fader_value(db):
    """dB -> the stored value whose shown dB is nearest."""
    best, err = 0, None
    for v in range(1, FADER_MAX + 1):
        e = abs(FADER_TABLE[v] - db)
        if err is None or e < err - 1e-9:
            best, err = v, e
    return best


def hpf_index(hz):
    return min(HPF_HZ, key=lambda i: abs(math.log(HPF_HZ[i]) - math.log(max(1.0, hz))))


# BB-CSV-1: stored colour code -> (our key, label); the CSV word is the label's Yamaha CSV spelling
CL_COLOURS = [('blue', 'Blue'), ('orange', 'Orange'), ('yellow', 'Yellow'), ('purple', 'Purple'),
              ('cyan', 'Sky blue'), ('magenta', 'Pink'), ('red', 'Red'), ('green', 'Green'), ('off', 'Off (black)')]
# BB-CSV-1: stored icon code -> Yamaha's CSV icon word (code 0 to 39)
CL_ICONS = ['Kick', 'Snare', 'Hi-Hat', 'Tom', 'DrumKit', 'Perc.', 'A.Bass', 'Strings', 'E.Bass', 'A.Guitar',
            'E.Guitar', 'BassAmp', 'GuitarAmp', 'Trumpet', 'Trombone', 'Saxophone', 'Piano', 'Organ', 'Keyboard',
            'Male', 'Female', 'Choir', 'Dynamic', 'Condenser', 'Wireless', 'Podium', 'Wedge', '2way', 'In-Ear',
            'Effector', 'Media1', 'Media2', 'Video', 'Mixer', 'PC', 'Processor', 'Audience', 'Star1', 'Star2', 'Blank']


def icon_key(word):
    return word.lower().replace('.', '').replace('-', '')


def cl_port_label(code, family):
    """(label, group) of a stored CL/QL patch code, or None when no test named it. BB-CSV-2."""
    if code == 0:
        return ('None', 'None')
    if 1 <= code <= 64:
        return ('DANTE %d' % code, 'Dante')
    if 65 <= code <= 72:
        return (('INPUT %d' if family == 'QL' else 'OMNI %d') % (code - 64), 'Local' if family == 'QL' else 'OMNI')
    if code in (73, 74):
        return ('PB %s' % ('L' if code == 73 else 'R'), 'Playback')
    if 75 <= code <= 122:
        s, k = divmod(code - 75, 16)
        return ('SLOT%d %d' % (s + 1, k + 1), 'Slot %d' % (s + 1))
    if 123 <= code <= 138:
        k, ab = divmod(code - 123, 2)
        return ('FX %d%s' % (k + 1, 'AB'[ab]), 'Effect rack')
    if 139 <= code <= 154:
        k, ab = divmod(code - 139, 2)
        return ('PRFX %d%s' % (k + 1, 'AB'[ab]), 'Premium rack')
    if 155 <= code <= 170 and family != 'QL':
        k, ab = divmod(code - 155, 2)
        return ('GEQ %d%s' % (k + 1, 'AB'[ab]), 'GEQ rack')
    if 193 <= code <= 216 and family == 'QL':
        return ('INPUT %d' % (code - 184), 'Local')
    return None


def cl_local_port(code, family):
    """The head amp port (1 to 32) a patch code reaches on the console itself, or None."""
    if 65 <= code <= 72:
        return code - 64
    if family == 'QL' and 193 <= code <= 216:
        return code - 184
    return None


def cl_writable(code, family):
    """Rack outputs are named on read, but the editor turned a written GEQ 4A and FX 3B into NONE (they exist only
    as the show's rack is set up), so they are never written."""
    lab = cl_port_label(code, family)
    return bool(lab) and lab[1] not in ('GEQ rack', 'Effect rack', 'Premium rack')


CL_MODELS = {'cl5': ('CL', 'CL5', 72, 24), 'cl3': ('CL', 'CL3', 64, 24), 'cl1': ('CL', 'CL1', 48, 24),
             'ql5': ('QL', 'QL5', 64, 16), 'ql1': ('QL', 'QL1', 32, 16)}
QL_LOCAL = {'ql5': 32, 'ql1': 16}
ST_IN, MATRICES, DCAS, MUTE_GROUPS = 8, 8, 16, 8


def cl_ports(family, key):
    out = []
    for code in range(0, 217):
        lab = cl_port_label(code, family)
        if not lab or not cl_writable(code, family):
            continue
        if family == 'QL' and lab[1] == 'Local' and cl_local_port(code, family) > QL_LOCAL.get(key, 32):
            continue
        out.append({'code': code, 'label': lab[0], 'group': lab[1]})
    return out


def _split_name(b, off, count, i):
    raw = bytes(b[off + 4 * i:off + 4 * i + 4]) + bytes(b[off + 4 * count + 4 * i:off + 4 * count + 4 * i + 4])
    return _text(raw.split(b'\0', 1)[0])


def _name_edits(off, count, i, name):
    raw = name.encode('ascii').ljust(8, b'\0')
    return [(off + 4 * i, raw[:4]), (off + 4 * count + 4 * i, raw[4:])]


def _bit(b, off, slot):
    i = slot - 1
    return bool(b[off + i // 8] >> (i % 8) & 1)


# Which writes an editor test opened (FORMAT.md section 5). Keys: rename colour icon patch gain phantom hpf fader on
# dca name_bus, and 'scenes' for the stored scenes.
GEN1_KEYS = ('rename', 'colour', 'icon', 'patch', 'gain', 'phantom', 'hpf', 'fader', 'on', 'dca', 'name_bus')
GEN1_FORMATS = {'CL': (5, 6, 7), 'QL': (6, 7)}
GEN1_SCENE_KEYS = ('rename', 'colour', 'patch')        # BB-SCENE: CL format 7 only


class Gen1Show:
    generation = 1

    def __init__(self, data, console=None):
        self.data = bytes(data)
        self.c = clf_parse(self.data)
        base, size = self.c.memapi(CURRENT)
        self.fmt = SCENE_FORMATS.get(size)
        if self.fmt is None:
            raise Refused('This CL or QL file uses a scene layout this tool can\'t read. Open it in CL Editor or QL '
                          'Editor and save it again.')
        cur = self.data[base:base + size]
        if struct.unpack_from('>H', cur, VERSION_OFF)[0] != self.fmt:
            raise Refused('This CL or QL file uses a scene layout this tool can\'t read. Open it in CL Editor or QL '
                          'Editor and save it again.')
        self.cur = cur
        comment = self.c.comment.split(b'\0', 1)[0]
        # BB-MODEL: a .CLF does not record the model. The editor's default comment ("CL [" / "QL [") or a patch to
        # INPUT 9 to 32 (QL only, BB-CSV-2) is a hint, never proof.
        ql_codes = any(193 <= cur[IN_PATCH + i] <= 216 for i in range(88))
        self.said = 'QL' if comment.startswith(b'QL') or ql_codes else 'CL' if comment.startswith(b'CL') else None
        self.hint = self.said or 'CL'
        if console in CL_MODELS:
            self.key, self.model_from = console, 'you'
        else:
            self.key, self.model_from = ('ql5' if self.hint == 'QL' else 'cl5'), 'guess'
        self.family, self.model_name, self.inputs, self.mixes = CL_MODELS[self.key]
        self._scene_cache = {}

    # ---- gates ------------------------------------------------------------------------------------------------------
    def write_why(self, key):
        """None when an editor test opened this write here, else the sentence that says why not."""
        if key == 'send':
            return 'Sends are not read from CL and QL files yet, so this tool does not change them.'
        if key == 'scenes':
            if self.family != 'CL' or self.fmt != 7:
                return ('Stored scenes were tested on CL files in scene format 7 only. Leave out --all-scenes to change '
                        'the current scene.')
            return None
        if key not in GEN1_KEYS:
            return 'That change is not available for this console.'
        if self.fmt not in GEN1_FORMATS[self.family]:
            return ('%s files in scene format %d open read-only here: no %s show in that format has been through the '
                    'editor test yet.' % (self.family, self.fmt, self.family))
        return None

    # ---- reading ----------------------------------------------------------------------------------------------------
    def scene(self, sid):
        if sid not in self._scene_cache:
            loc = self.c.memapi(sid)
            out = None
            if loc and SCENE_FORMATS.get(loc[1]) is not None:
                b = self.data[loc[0]:loc[0] + loc[1]]
                if struct.unpack_from('>H', b, VERSION_OFF)[0] == SCENE_FORMATS[loc[1]]:
                    out = b
            self._scene_cache[sid] = out
        return self._scene_cache[sid]

    def slots(self):
        """[(id, kind, n, label, slot)]: CH 1..N, then ST IN 1L, 1R ... 8R (slots 73 to 88, BB-CSV-1)."""
        out = [('ch%d' % n, 'input', n, 'CH %d' % n, n) for n in range(1, self.inputs + 1)]
        for k in range(1, ST_IN + 1):
            for j, side in enumerate('LR'):
                out.append(('st%d%s' % (k, side.lower()), 'stin', k, 'ST IN %d%s' % (k, side),
                            72 + 2 * (k - 1) + j + 1))
        return out

    def name(self, b, slot):
        return _split_name(b, IN_NAMES[0], IN_NAMES[1], slot - 1)

    @staticmethod
    def colour(code):
        return {'key': CL_COLOURS[code][0] if 0 <= code < len(CL_COLOURS) else None, 'code': code}

    @staticmethod
    def icon(code):
        return {'key': icon_key(CL_ICONS[code]) if 0 <= code < len(CL_ICONS) else None, 'code': code}

    def patch(self, code):
        lab = cl_port_label(code, self.family)
        return {'code': code, 'label': lab[0] if lab else None, 'known': bool(lab)}

    @staticmethod
    def strip_slot(slot):
        """An ST IN strip shows its L slot's fader, on and HPF (BB-LOAD-G)."""
        return slot - 1 if slot > 72 and (slot - 73) % 2 == 1 else slot

    def channel(self, sid, kind, n, label, slot, diffs):
        b = self.cur
        code = b[IN_PATCH + slot - 1]
        port = cl_local_port(code, self.family)
        if port and self.family == 'QL' and port > QL_LOCAL.get(self.key, 32):
            port = None
        pre = None
        if port:
            pre = {'port': self.patch(code)['label'], 'port_n': port, 'gain_db': float(b[HA_GAIN + port - 1] - 6),
                   'phantom': _bit(b, HA_PHANTOM, port)}
        s = self.strip_slot(slot)
        fv = struct.unpack_from('>H', b, FADER + 2 * (s - 1))[0]
        fader = {'inf': True} if fv == 0 else ({'db': FADER_TABLE[fv]} if fv <= FADER_MAX else None)
        return {
            'n': n, 'id': sid, 'kind': kind, 'label': label, 'slot': slot,
            'name': self.name(b, slot),
            'colour': self.colour(b[IN_COLOUR + slot - 1]),
            'icon': self.icon(b[IN_ICON + slot - 1]),
            'patch': self.patch(code),
            'preamp': pre,
            'hpf': {'on': _bit(b, HPF_ON, s), 'freq': HPF_HZ.get(b[HPF_FREQ + s - 1])},
            'fader': fader,
            'on': _bit(b, CH_ON, s),
            'dcas': [k for k in range(1, DCAS + 1) if _bit(b, DCA_ASSIGN + MASK_LEN * (k - 1), s)],
            'mute_groups': [k for k in range(1, MUTE_GROUPS + 1) if _bit(b, MUTE_ASSIGN + MASK_LEN * (k - 1), slot)],
            'sends': None,
            'scene_diff': diffs.get(slot, 0),
        }

    def bus_names(self, b):
        return [_split_name(b, off, count, i) for (off, count), have in (
            (MIX_NAMES, self.mixes), (MTX_NAMES, MATRICES), (DCA_NAMES, DCAS), (MUTE_NAMES, MUTE_GROUPS))
            for i in range(have)]

    def scene_list(self):
        """Stored scenes: title, and whether each holds other channel names, colours, patch or bus names."""
        cur = self.cur
        listed = {s[4] for s in self.slots()}
        cur_bus = self.bus_names(cur)
        rows, per_slot, totals = [], {}, {'names': 0, 'colours': 0, 'patch': 0, 'bus_names': 0}
        for sid in self.c.stored_ids():
            b = self.scene(sid)
            if b is None:
                rows.append({'n': sid, 'title': None, 'differs': None})
                continue
            d = {'names': False, 'colours': False, 'patch': False, 'bus_names': self.bus_names(b) != cur_bus}
            for slot in listed:
                hit = False
                if self.name(b, slot) != self.name(cur, slot):
                    d['names'] = hit = True
                if b[IN_COLOUR + slot - 1] != cur[IN_COLOUR + slot - 1]:
                    d['colours'] = hit = True
                if b[IN_PATCH + slot - 1] != cur[IN_PATCH + slot - 1]:
                    d['patch'] = hit = True
                if hit:
                    per_slot[slot] = per_slot.get(slot, 0) + 1
            for k in totals:
                totals[k] += 1 if d[k] else 0
            rows.append({'n': sid, 'title': _text(bytes(b[0:16]).split(b'\0', 1)[0].rstrip(b' ')), 'differs': d})
        return rows, per_slot, totals

    def model(self):
        b = self.cur
        rows, per_slot, totals = self.scene_list()
        chans = [self.channel(*s, diffs=per_slot) for s in self.slots()]
        buses = []
        for kind, label, (off, count), have, icon_off, col_off in (
                ('mix', 'MIX', MIX_NAMES, self.mixes, MIX_ICON, MIX_COLOUR),
                ('matrix', 'MATRIX', MTX_NAMES, MATRICES, MTX_ICON, MTX_COLOUR)):
            for i in range(have):
                buses.append({'id': '%s%d' % (kind, i + 1), 'kind': kind, 'n': i + 1, 'label': '%s %d' % (label, i + 1),
                              'name': _split_name(b, off, count, i), 'colour': self.colour(b[col_off + i]),
                              'icon': self.icon(b[icon_off + i])})
        for i, (bid, kind, n, label) in enumerate([('stl', 'stereo', 1, 'ST L'), ('str', 'stereo', 2, 'ST R'),
                                                   ('mono', 'mono', 1, 'MONO')]):
            buses.append({'id': bid, 'kind': kind, 'n': n, 'label': label,
                          'name': _split_name(b, STM_NAMES[0], STM_NAMES[1], i),
                          'colour': self.colour(b[STM_COLOUR + i]), 'icon': self.icon(b[STM_ICON + i])})
        dcas = [{'n': k, 'name': _split_name(b, DCA_NAMES[0], DCA_NAMES[1], k - 1)} for k in range(1, DCAS + 1)]
        mutes = [{'n': k, 'name': _split_name(b, MUTE_NAMES[0], MUTE_NAMES[1], k - 1)}
                 for k in range(1, MUTE_GROUPS + 1)]
        warnings = []
        differ = sum(1 for r in rows if r['differs'] and any(r['differs'][k] for k in ('names', 'colours', 'patch')))
        if differ:
            one = differ == 1
            w = '%d stored scene%s %s own channel names, colours or patch. Changes go to the current scene only, ' \
                'so recalling %s brings the old ones back.' % (differ, '' if one else 's',
                                                              'holds its' if one else 'hold their', 'it' if one else 'one')
            if not self.write_why('scenes'):
                w += ' Add --all-scenes to send names, colours and patch to every stored scene too.'
            warnings.append(w)
        bus_any = sum(1 for r in rows if r['differs'] and r['differs']['bus_names'])
        if bus_any:
            warnings.append('%d stored scene%s %s own mix, matrix, DCA or mute group names. busname changes the '
                            'current scene only, so a recall may bring the old names back.' % (
                                bus_any, '' if bus_any == 1 else 's', 'holds its' if bus_any == 1 else 'hold their'))
        if self.model_from != 'you':
            warnings.append("CL and QL save the same .CLF file, and it doesn't record which console made it. This "
                            'read guesses %s. Pass --console (cl5, cl3, cl1, ql5, ql1) for the right channel count.'
                            % self.model_name)
        elif self.said and self.said != self.family:
            warnings.append('This file looks like a %s show, but it is open as a %s. Check --console.' % (
                self.said, self.model_name))
        title = _text(bytes(b[0:16]).split(b'\0', 1)[0].rstrip(b' '))
        writes = {k: self.write_why(k) for k in GEN1_KEYS + ('scenes',)}
        return {
            'file': {'bytes': len(self.data), 'generation': 1, 'container': 'clf', 'kind': 'all',
                     'checksums': self.c.checked},
            'console': {'family': self.family, 'model': self.model_name, 'model_key': self.key,
                        'model_from': self.model_from, 'hint': self.said},
            'firmware': {'label': 'Scene format %d' % self.fmt, 'format': self.fmt},
            'summary': '%s show. %d inputs, %d mixes, %d stored scene%s.' % (
                self.model_name, self.inputs, self.mixes, len(rows), '' if len(rows) == 1 else 's'),
            'counts': {'inputs': self.inputs, 'stereo_inputs': ST_IN, 'mixes': self.mixes, 'matrices': MATRICES,
                       'dcas': DCAS, 'mute_groups': MUTE_GROUPS, 'scenes': len(rows)},
            'channels': chans, 'buses': buses, 'dcas': dcas, 'mute_groups': mutes,
            'scenes': {'count': len(rows), 'current': {'title': title}, 'differ': totals, 'list': rows},
            'ports': cl_ports(self.family, self.key),
            'palette': {'colours': [{'key': k, 'label': lab, 'code': i} for i, (k, lab) in enumerate(CL_COLOURS)],
                        'icons': [{'key': icon_key(w), 'label': w, 'code': i} for i, w in enumerate(CL_ICONS)],
                        'name_max': NAME_LEN,
                        'ranges': {'gain': [HA_MIN_DB, HA_MAX_DB], 'hpf': [20, 600], 'fader': [-138, 10]}},
            'unproven': ['scenes'] if self.fmt == 6 else [],      # stored scene titles: formats 5 and 7 only
            'writes': {k: {'ok': True} if v is None else {'ok': False, 'why': v} for k, v in writes.items()},
            'warnings': warnings,
        }

    # ---- writing ----------------------------------------------------------------------------------------------------
    def apply(self, ops):
        """Run ops in order. -> (new bytes, changes, refused). Nothing is kept from a call with a refused op."""
        work = {}
        changes, refused = [], []
        by_id = {s[0]: s for s in self.slots()}

        def buf(sid):
            if sid not in work:
                b = self.scene(sid)
                if b is None:
                    raise Refused('Stored scene %d uses a layout this tool can not write.' % sid)
                if sid != CURRENT and SCENE_FORMATS[len(b)] != 7:
                    raise Refused('Stored scene %d uses an older scene layout that the scene test did not cover. Leave '
                                  'out --all-scenes to change the current scene only.' % sid)
                work[sid] = bytearray(b)
            return work[sid]

        def put(sid, off, raw):
            buf(sid)[off:off + len(raw)] = raw

        def setbit(sid, off, slot, v):
            b = buf(sid)
            i = slot - 1
            b[off + i // 8] = (b[off + i // 8] | (1 << (i % 8))) if v else (b[off + i // 8] & ~(1 << (i % 8)) & 0xff)

        for op in ops:
            try:
                if not isinstance(op, dict):
                    raise Refused('That change is malformed.')
                self._op(op, by_id, put, setbit, buf, changes)
            except Refused as e:
                refused.append(str(e))
            except (ValueError, KeyError, IndexError, TypeError):
                refused.append('That value is out of range for this console.')
        if refused or not work:
            return self.data, changes, refused
        return clf_rewrite(self.c, work), changes, refused

    def _need(self, key):
        why = self.write_why(key)
        if why:
            raise Refused(why)

    def _targets(self, op, by_id):
        t = op.get('target')
        if not isinstance(t, dict):
            raise Refused('Pick the channels to change.')
        out = []
        if t.get('all') is True:
            out = list(by_id.values())
        elif isinstance(t.get('ids'), list):
            for i in t['ids']:
                if i not in by_id:
                    raise Refused('There is no %s on a %s.' % (_id_label(i), self.model_name))
                out.append(by_id[i])
        elif isinstance(t.get('channels'), list):
            for n in t['channels']:
                if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= self.inputs:
                    raise Refused('There is no CH %s on a %s.' % (str(n)[:6], self.model_name))
                out.append(by_id['ch%d' % n])
        if not out:
            raise Refused('Pick the channels to change.')
        return out

    def _scenes(self, op, keys):
        sc = op.get('scenes', 'current')
        if sc in (None, 'current'):
            return [CURRENT]
        self._need('scenes')
        bad = [k for k in keys if k not in GEN1_SCENE_KEYS]
        if bad:
            raise Refused('Stored scenes take names, colours and patch only. Leave out --all-scenes for this change.')
        if sc == 'all':
            return [CURRENT] + self.c.stored_ids()
        raise Refused('Scenes is "current" or "all".')

    def _op(self, op, by_id, put, setbit, buf, changes):
        name = op.get('op')
        if name == 'rename':
            self._need('rename')
            targets = self._targets(op, by_id)
            scenes = self._scenes(op, ['rename'])
            names = op['names'] if isinstance(op.get('names'), list) else [op.get('name')]
            if len(names) != len(targets):
                raise Refused('Give one name for each channel.')
            for (sid, kind, n, label, slot), nm in zip(targets, names):
                try:
                    nm = clean_name(nm, NAME_LEN)
                except Refused as e:
                    raise Refused('%s: %s' % (label, e))
                for sc in scenes:
                    for off, raw in _name_edits(IN_NAMES[0], IN_NAMES[1], slot - 1, nm):
                        put(sc, off, raw)
                changes.append('%s renamed %s.' % (label, nm) if nm else '%s name cleared.' % label)
        elif name == 'set':
            targets = self._targets(op, by_id)
            fields = [k for k in ('colour', 'icon', 'fader_db', 'on', 'hpf') if k in op]
            if not fields:
                raise Refused('Say what to set.')
            keys = [{'fader_db': 'fader'}.get(f, f) for f in fields]
            for k in keys:
                self._need(k)
            scenes = self._scenes(op, keys)
            for (sid, kind, n, label, slot) in targets:
                s = self.strip_slot(slot)
                pair = [s, s + 1] if kind == 'stin' else [s]     # BB-LOAD-G: the editor's ON click changes L and R
                for f in fields:
                    v = op[f]
                    if f == 'colour':
                        code = next((i for i, c in enumerate(CL_COLOURS) if c[0] == v), None)
                        if code is None:
                            raise Refused('Pick a colour: %s.' % ', '.join(c[0] for c in CL_COLOURS))
                        for sc in scenes:
                            put(sc, IN_COLOUR + slot - 1, bytes([code]))
                        changes.append('%s colour set to %s.' % (label, CL_COLOURS[code][1]))
                    elif f == 'icon':
                        code = next((i for i, w in enumerate(CL_ICONS) if icon_key(w) == icon_key(str(v))), None)
                        if code is None:
                            raise Refused('Pick an icon: %s.' % ', '.join(icon_key(w) for w in CL_ICONS))
                        for sc in scenes:
                            put(sc, IN_ICON + slot - 1, bytes([code]))
                        changes.append('%s icon set to %s.' % (label, CL_ICONS[code]))
                    elif f == 'fader_db':
                        if v in ('-inf', 'off', None):
                            fv, txt = 0, '-inf'
                        else:
                            db = _number(v, 'A fader level is a number of dB, or off.')
                            if db > 10.0 or db < -138.0:
                                raise Refused('%s: CL and QL faders go from -138 dB to +10 dB, or off.' % label)
                            fv = fader_value(db)
                            txt = '%+.2f dB' % FADER_TABLE[fv] if FADER_TABLE[fv] else '0.00 dB'
                        for sc in scenes:
                            for p in pair:
                                put(sc, FADER + 2 * (p - 1), struct.pack('>H', fv))
                        changes.append('%s fader set to %s.' % (label, txt))
                    elif f == 'on':
                        _bool_field(v, 'Channel on')
                        for sc in scenes:
                            for p in pair:
                                setbit(sc, CH_ON, p, v)
                        changes.append('%s turned %s.' % (label, 'on' if v else 'off'))
                    elif f == 'hpf':
                        if not isinstance(v, dict) or not ({'on', 'freq'} & set(v)):
                            raise Refused('Say HPF on, off, or a frequency.')
                        if 'on' in v:
                            _bool_field(v['on'], 'HPF on')
                            for sc in scenes:
                                for p in pair:
                                    setbit(sc, HPF_ON, p, v['on'])
                            changes.append('%s HPF %s.' % (label, 'on' if v['on'] else 'off'))
                        if 'freq' in v:
                            hz = _number(v['freq'], 'An HPF frequency is a number of Hz.')
                            if hz < 20 or hz > 600:
                                raise Refused('%s: the HPF goes from 20 Hz to 600 Hz on a %s.' % (label, self.family))
                            idx = hpf_index(hz)
                            for sc in scenes:
                                for p in pair:
                                    put(sc, HPF_FREQ + p - 1, bytes([idx]))
                            changes.append('%s HPF set to %s Hz.' % (label, ('%.1f' % HPF_HZ[idx]).rstrip('0')
                                                                     .rstrip('.')))
        elif name == 'patch':
            self._need('patch')
            targets = self._targets(op, by_id)
            scenes = self._scenes(op, ['patch'])
            code = self.port_code(op.get('source'))
            if not cl_writable(code, self.family):
                raise Refused('Rack outputs (FX, PRFX, GEQ) can only be patched in the Yamaha editor, where the rack is '
                              'set up.')
            if self.family == 'QL' and cl_local_port(code, 'QL') and cl_local_port(code, 'QL') > QL_LOCAL[self.key]:
                raise Refused('A %s has %d inputs.' % (self.model_name, QL_LOCAL[self.key]))
            lab = cl_port_label(code, self.family)[0]
            for (sid, kind, n, label, slot) in targets:
                for sc in scenes:
                    put(sc, IN_PATCH + slot - 1, bytes([code]))
                changes.append('%s patched to %s.' % (label, lab) if code else '%s unpatched.' % label)
        elif name == 'preamp':
            fields = [k for k in ('gain_db', 'phantom') if k in op]
            if not fields:
                raise Refused('Say the gain or 48V.')
            for k in fields:
                self._need('gain' if k == 'gain_db' else 'phantom')
            targets = self._targets(op, by_id)
            if op.get('scenes', 'current') not in (None, 'current'):
                raise Refused('Stored scenes take names, colours and patch only. Leave out --all-scenes for this '
                              'change.')
            for (sid, kind, n, label, slot) in targets:
                code = buf(CURRENT)[IN_PATCH + slot - 1]          # the patch as edited so far in this call
                port = cl_local_port(code, self.family)
                if not port or (self.family == 'QL' and port > QL_LOCAL[self.key]):
                    lab = cl_port_label(code, self.family)
                    raise Refused('%s comes from %s. Its head amp is not in this file: set it on the stage box or its '
                                  'own device.' % (label, lab[0] if lab and code else 'no input'))
                plab = cl_port_label(code, self.family)[0]
                if 'gain_db' in op:
                    g = _number(op['gain_db'], 'Gain is a number of dB.')
                    if g < HA_MIN_DB or g > HA_MAX_DB:
                        raise Refused('%s: head amp gain goes from -6 dB to +66 dB.' % label)
                    v = int(round(g)) + 6
                    put(CURRENT, HA_GAIN + port - 1, bytes([v]))
                    changes.append('%s gain set to %+d dB (%s).' % (plab, v - 6, label))
                if 'phantom' in op:
                    _bool_field(op['phantom'], '48V')
                    setbit(CURRENT, HA_PHANTOM, port, op['phantom'])
                    changes.append('%s 48V %s (%s).' % (plab, 'on' if op['phantom'] else 'off', label))
        elif name == 'dca':
            self._need('dca')
            targets = self._targets(op, by_id)
            if op.get('scenes', 'current') not in (None, 'current'):
                raise Refused('Stored scenes take names, colours and patch only. Leave out --all-scenes for this '
                              'change.')
            k, mode = op.get('dca'), op.get('mode', 'add')
            if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= DCAS:
                raise Refused('Pick a DCA from 1 to 16.')
            if mode not in ('add', 'remove', 'only'):
                raise Refused('Say add, remove or only.')
            for (sid, kind, n, label, slot) in targets:
                if kind == 'stin':
                    raise Refused('%s: DCA assigns on ST IN wait for a load test. Set them in %s Editor for now.' % (
                        label, self.family))
            for (sid, kind, n, label, slot) in targets:
                for j in range(1, DCAS + 1):
                    if j == k:
                        setbit(CURRENT, DCA_ASSIGN + MASK_LEN * (j - 1), slot, mode != 'remove')
                    elif mode == 'only':
                        setbit(CURRENT, DCA_ASSIGN + MASK_LEN * (j - 1), slot, False)
                changes.append('%s %s DCA %d.' % (label, {'add': 'added to', 'remove': 'taken out of',
                                                          'only': 'now only in'}[mode], k))
        elif name == 'name_bus':
            self._need('name_bus')
            bus = op.get('bus')
            try:
                nm = clean_name(op.get('name'), NAME_LEN)
            except Refused as e:
                raise Refused('%s: %s' % (bus, e))
            table = {'mix': (MIX_NAMES, self.mixes, 'MIX'), 'matrix': (MTX_NAMES, MATRICES, 'MATRIX'),
                     'dca': (DCA_NAMES, DCAS, 'DCA'), 'mute': (MUTE_NAMES, MUTE_GROUPS, 'Mute group')}
            kind = next((k for k in table if isinstance(bus, str) and bus.startswith(k) and bus[len(k):].isdigit()
                         and 1 <= len(bus) - len(k) <= 2), None)
            if not kind:
                raise Refused('Pick a bus: mix1, matrix1, dca1 or mute1.')
            (off, count), have, word = table[kind]
            i = int(bus[len(kind):])
            if not 1 <= i <= have:
                raise Refused('There is no %s %d on a %s.' % (word, i, self.model_name))
            for o, raw in _name_edits(off, count, i - 1, nm):
                put(CURRENT, o, raw)
            changes.append('%s %d renamed %s.' % (word, i, nm))
        elif name == 'send':
            raise Refused(self.write_why('send'))
        else:
            raise Refused('That change is not available for this console.')

    def port_code(self, src):
        """A patch source (stored code, or a label such as 'DANTE 3' or 'none') -> its stored code."""
        if src in ('none', 'None', 0):
            return 0
        if isinstance(src, int) and not isinstance(src, bool):
            if cl_port_label(src, self.family):
                return src
        elif isinstance(src, str):
            want = src.replace(' ', '').upper()
            for code in range(0, 217):
                lab = cl_port_label(code, self.family)
                if lab and lab[0].replace(' ', '').upper() == want:
                    return code
        raise Refused('Pick a source from the patch list (run "ports").')


# =====================================================================================================================
# Generation 2: the '#YAMAHA MBDF' container (DM7, DM5, DM3, TF, RIVAGE PM). FORMAT.md section 4.
# =====================================================================================================================
MAGIC = b'#YAMAHA MBDF'
MAX_ENTRY_INFLATED = 4 * 1024 * 1024
MAX_TOTAL_INFLATED = 160 * 1024 * 1024
MAX_DEPTH, MAX_RECORDS = 3, 4000
MAX_COLLECTIONS, MAX_PRS, MAX_COL_DEPTH = 5000, 4096, 16          # per schema
MAX_FILE_COLLECTIONS, MAX_FILE_PRS = 250000, 600000               # every schema of a file, each use counted
MAX_BUILT_COLLECTIONS, MAX_BUILT_PRS = 16000, 32000               # schemas parsed fresh (a repeat is reused)
END_TAIL = 24
_PRINTABLE = bytes(range(0x20, 0x7f))


def _cstr(b):
    raw = bytes(b).split(b'\0', 1)[0]
    if raw.translate(None, _PRINTABLE):
        raise _damaged()
    return raw.decode('ascii')


def is_mbdf(data):
    return data[:12] == MAGIC


def mbdf_header(data):
    """{'kind', 'model', 'version'} from the fixed header, or None."""
    if len(data) < 0x48 or not is_mbdf(data):
        return None
    kind = bytes(data[12:24]).split(b'\0')[0].decode('latin-1')
    model = bytes(data[0x24:0x34]).split(b'\0')[0].decode('latin-1')
    v = data[0x34:0x38]
    version = '%s%d.%02d' % (chr(v[0]), v[1], v[2]) if 0x40 < v[0] < 0x5b else bytes(v).hex()
    return {'kind': kind, 'model': model, 'version': version}


class Budget:
    """What one file and its entries may still parse. A schema already parsed (the same bytes) is reused."""

    def __init__(self):
        self.cols, self.prs = MAX_FILE_COLLECTIONS, MAX_FILE_PRS
        self.built_cols, self.built_prs = MAX_BUILT_COLLECTIONS, MAX_BUILT_PRS
        self.schemas = {}

    def charge(self, cols, prs, built):
        self.cols -= cols
        self.prs -= prs
        if built:
            self.built_cols -= cols
            self.built_prs -= prs
        if min(self.cols, self.prs, self.built_cols, self.built_prs) < 0:
            raise _damaged()


class Col:
    __slots__ = ('name', 'off', 'size', 'count', 'prs', 'kids', 'prend', 'byname', 'prbyname')


class PR:
    __slots__ = ('name', 'typ', 'size', 'count', 'off', 'bit')


def _layout(col):
    """Parameters packed in order; consecutive 1-bit parameters share one bit stream (least significant bit first);
    the next wider parameter starts on the next byte."""
    pos, bitpos = 0, None
    for pr in col.prs:
        if pr.size == 0:
            if bitpos is None:
                bitpos = pos * 8
            pr.off, pr.bit = bitpos // 8, bitpos % 8
            bitpos += pr.count
            pos = (bitpos + 7) // 8
        else:
            bitpos = None
            pr.off, pr.bit = pos, None
            pos += pr.size * pr.count
    col.prend = pos


def parse_schema(d, start, end, budget):
    """The COL0/PR tree in d[start:end] -> root Col. The root must fill the range exactly."""
    key = bytes(d[start:end])
    hit = budget.schemas.get(key)
    if hit is not None:
        budget.charge(hit[1], hit[2], False)
        return hit[0]
    n = [0, 0]

    def col(o, depth):
        if depth > MAX_COL_DEPTH or o + 48 > end or d[o:o + 4] != b'COL0':
            raise _damaged()
        n[0] += 1
        budget.charge(1, 0, True)
        if n[0] > MAX_COLLECTIONS:
            raise _damaged()
        prb, kidb, off, size, count = struct.unpack_from('<5I', d, o + 28)
        if prb % 32 or prb > end - o - 48 or kidb > end - o - 48 - prb:
            raise _damaged()
        k = prb // 32
        n[1] += k
        budget.charge(0, k, True)
        if n[1] > MAX_PRS:
            raise _damaged()
        c = Col()
        c.name = _cstr(d[o + 4:o + 28])
        c.off, c.size, c.count, c.prs, c.kids = off, size, count, [], []
        p = o + 48
        for _ in range(k):
            if d[p:p + 3] != b'PR ':
                raise _damaged()
            pr = PR()
            pr.typ = d[p + 3]
            pr.size, pr.count = struct.unpack_from('<HH', d, p + 4)
            pr.name = _cstr(d[p + 8:p + 32])
            if pr.typ not in (0, 1, 2) or (pr.typ == 0 and pr.size == 0) or pr.size > 4096:
                raise _damaged()
            c.prs.append(pr)
            p += 32
        stop = p + kidb
        while p < stop:
            kid, p = col(p, depth + 1)
            c.kids.append(kid)
        if p != stop:
            raise _damaged()
        _layout(c)
        if c.count == 0 or c.size == 0 or c.prend > c.size:
            raise _damaged()
        for kid in c.kids:
            if kid.off + kid.size * kid.count > c.size:
                raise _damaged()
        c.byname = {kid.name: kid for kid in c.kids}
        c.prbyname = {pr.name: pr for pr in c.prs}
        return c, p

    root, p = col(start, 0)
    if p != end:
        raise _damaged()
    if len(budget.schemas) < 256:
        budget.schemas[key] = (root, n[0], n[1])
    return root


class Section:
    """One self-describing '#MMS' section: its schema, and values read and written by schema path."""

    def __init__(self, data, rec, budget):
        self.data, self.field = data, rec['name']
        b, d = rec['body'], data
        self.function = _cstr(d[b + 8:b + 24])
        md5 = bytes(d[b + 44:b + 76]).decode('latin-1')
        z, slen, dlen = struct.unpack_from('<3I', d, b + 76)
        if z != 0 or 88 + slen + dlen != rec['len']:
            raise _damaged()
        self.schema_off, self.data_off, self.data_len = b + 88, b + 88 + slen, dlen
        if hashlib.md5(d[self.schema_off:self.schema_off + slen]).hexdigest() != md5:
            raise _damaged()
        self.root = parse_schema(d, self.schema_off, self.schema_off + slen, budget)
        if self.root.size * self.root.count > dlen:
            raise _damaged()

    def coll(self, path):
        cur = self.root
        for part in [p for p in path.split('/') if p]:
            cur = cur.byname.get(part)
            if cur is None:
                return None
        return cur

    def has(self, path, prname):
        c = self.coll(path)
        return c is not None and prname in c.prbyname

    def count(self, path):
        c = self.coll(path)
        return c.count if c else 0

    def locate(self, path, prname, idx=(), arr=0):
        cur, off = self.root, self.data_off
        parts = [p for p in path.split('/') if p]
        idx = list(idx) + [0] * (len(parts) - len(idx))
        for part, i in zip(parts, idx):
            cur = cur.byname.get(part)
            if cur is None or not isinstance(i, int) or not 0 <= i < cur.count:
                raise KeyError('%s[%s]' % (part, i))
            off += cur.off + i * cur.size
        pr = cur.prbyname.get(prname)
        if pr is None or not 0 <= arr < pr.count:
            raise KeyError(prname)
        if pr.size == 0:
            k = pr.bit + arr
            o, bit = off + pr.off + k // 8, k % 8
        else:
            o, bit = off + pr.off + arr * pr.size, None
        if not self.data_off <= o < self.data_off + self.data_len - (pr.size - 1 if pr.size else 0):
            raise KeyError(prname)
        return pr, o, bit

    def get(self, path, prname, idx=(), arr=0, d=None):
        d = self.data if d is None else d
        pr, o, bit = self.locate(path, prname, idx, arr)
        if bit is not None:
            return (d[o] >> bit) & 1
        raw = bytes(d[o:o + pr.size])
        if pr.typ == 0:
            return raw.split(b'\0', 1)[0].decode('utf-8', 'replace')
        return int.from_bytes(raw, 'little', signed=(pr.typ == 1))

    def put(self, buf, path, prname, value, idx=(), arr=0):
        pr, o, bit = self.locate(path, prname, idx, arr)
        if bit is not None:
            buf[o] = (buf[o] & ~(1 << bit) & 0xff) | ((1 if value else 0) << bit)
        elif pr.typ == 0:
            raw = value.encode('utf-8')
            if len(raw) > pr.size - 1:
                raise ValueError('too long')
            buf[o:o + pr.size] = raw + b'\0' * (pr.size - len(raw))
        else:
            if pr.typ == 1:
                lo, hi = -(1 << (8 * pr.size - 1)), (1 << (8 * pr.size - 1)) - 1
            else:
                lo, hi = 0, (1 << (8 * pr.size)) - 1
            v = int(value)
            if not lo <= v <= hi:
                raise ValueError('out of range')
            buf[o:o + pr.size] = v.to_bytes(pr.size, 'little', signed=(pr.typ == 1))


class Mbdf:
    def __init__(self, data, budget):
        self.data, self.budget = data, budget
        self.kind = self.model = self.version = None
        self.records = []
        self._parsed = {}
        self._names = None

    def sections(self):
        return [self._section_at(i) for i, r in enumerate(self.records) if r['type'] == 'mms']

    def _section_at(self, i):
        if i not in self._parsed:
            self._parsed[i] = Section(self.data, self.records[i], self.budget)
        return self._parsed[i]

    def section(self, name):
        """The first section whose field or function name is name, or None."""
        if self._names is None:
            first = {}
            for i, r in enumerate(self.records):
                if r['type'] == 'mms':
                    first.setdefault(r['name'], i)
                    first.setdefault(_cstr(self.data[r['body'] + 8:r['body'] + 24]), i)
            self._names = first
        i = self._names.get(name)
        return self._section_at(i) if i is not None else None

    def entries(self):
        return [r for r in self.records if r['type'] == 'file']


def mbdf_parse(data, depth=0, budget=None):
    """Walk an MBDF file record by record to its exact end."""
    d = bytes(data)
    if len(d) > (MAX_ENTRY_INFLATED if depth else MAX_BYTES) or depth > MAX_DEPTH:
        raise _damaged()
    if len(d) < 0x48 + 12 + END_TAIL or not is_mbdf(d) or struct.unpack_from('>I', d, 0x18)[0] != 0x24:
        raise _damaged()
    if d[0x1c:0x24].strip(b'\0'):
        raise _damaged()
    m = Mbdf(d, budget if budget is not None else Budget())
    m.kind = _cstr(d[12:24])
    m.model = _cstr(d[0x24:0x34])
    m.version = mbdf_header(d)['version']
    pos, n = 0x48, len(d)
    while True:
        if len(m.records) > MAX_RECORDS or pos > n - 12:
            raise _damaged()
        tag = d[pos:pos + 12]
        if tag in (b'#MMS FIELD\0\0', b'#MMS FACADE\0'):
            if pos > n - 36:
                raise _damaged()
            name = _cstr(d[pos + 12:pos + 24]) if d[pos + 12:pos + 24].strip(b'\0') else ''
            ext, ln, z = struct.unpack_from('>III', d, pos + 24)
            body = pos + 36 + ext
            if z != 0 or ext > n - pos - 36 or ln > n - body or ln < 88:
                raise _damaged()
            if d[body:body + 8] != b'MMSXLIT\0':
                raise _damaged()             # a body with no schema of its own (RIVAGE PM's compressed fields)
            size = 36 + ext + ln
            size += (-size) % 4
            if pos + size > n:
                raise _damaged()
            m.records.append({'type': 'mms', 'off': pos, 'size': size, 'name': name, 'len': ln, 'body': body})
            pos += size
        elif tag == b'#FILE\0\0\0\0\0\0\0':
            if pos > n - 44:
                raise _damaged()
            group = _cstr(d[pos + 12:pos + 24])
            hl, zl, z0, fnl, z1, eight = struct.unpack_from('>IIIHHI', d, pos + 24)
            if hl != fnl + 8 or eight != 8 or z1 != 0 or z0 != 0 or not 0 < fnl <= 200:
                raise _damaged()
            name = _cstr(d[pos + 44:pos + 44 + fnl])
            if len(name) != fnl or '/' in name or '\\' in name or name in ('.', '..'):
                raise _damaged()
            ds = pos + 44 + ((fnl + 3) & ~3)
            if zl > n - ds:
                raise _damaged()
            size = ds - pos + zl + ((-zl) % 4)
            if pos + size > n:
                raise _damaged()
            m.records.append({'type': 'file', 'off': pos, 'size': size, 'group': group, 'name': name, 'zoff': ds,
                              'zlen': zl})
            pos += size
        elif tag == b'#END' + b'\0' * 8:
            if n - pos != 12 + END_TAIL or d[pos + 12:].strip(b'\0'):
                raise _damaged()
            m.records.append({'type': 'end', 'off': pos, 'size': n - pos})
            break
        else:
            raise _damaged()
    return m


def inflate(m, rec, left):
    """The inner bytes of one '#FILE' record. left: a one-item list, the bytes all entries may still inflate to."""
    z = m.data[rec['zoff']:rec['zoff'] + rec['zlen']]
    cap = min(MAX_ENTRY_INFLATED, left[0])
    try:
        do = zlib.decompressobj()
        out = do.decompress(z, cap + 1)
        if len(out) > cap or do.unconsumed_tail or not do.eof:
            raise _damaged()
    except zlib.error:
        raise _damaged()
    if do.unused_data.strip(b'\0'):
        raise _damaged()
    left[0] -= len(out)
    return out


def mbdf_build(m, replace):
    """The file with some '#FILE' entries given new inner bytes (zlib level 1). Every other record is copied byte for
    byte, so a build with nothing replaced is the input file."""
    d = m.data
    out = bytearray(d[:0x48])
    for i, r in enumerate(m.records):
        if r['type'] == 'file' and i in replace:
            z = zlib.compress(replace[i], 1)
            hdr = bytearray(d[r['off']:r['zoff']])
            struct.pack_into('>I', hdr, 28, len(z))
            out += hdr + z + b'\0' * ((-len(z)) % 4)
        else:
            out += d[r['off']:r['off'] + r['size']]
    return bytes(out)


# ---- generation-2 values. Test ids: FORMAT.md 4.4 --------------------------------------------------------------------
# The shape (type, sizes, most) every file read so far gives each parameter used here (BB-DM-SHAPE). Type 0 text,
# 1 signed, 2 unsigned; size 0 is one bit. Any other shape is refused as damaged, so nothing is read or written as
# the wrong kind of value.
_NAME, _COLOR = (0, (64,), 1), (0, (8,), 1)
SHAPES = {
    'Mixing': {
        'InputChannel/Label': {'Name': _NAME, 'Color': _COLOR, 'Icon': (0, (12,), 1)},
        'InputChannel/Fader': {'Level': (1, (2,), 1), 'On': (2, (0,), 1)},
        'InputChannel/InPatch': {'Select': (2, (0,), 1)},
        'InputChannel/InPatch/Bank': {'Source': (2, (4,), 1)},
        'InputChannel/HPF': {'On': (2, (0,), 1), 'Frequency': (2, (4,), 1)},
        'InputChannel/PEQ': {'ActorSelect': (2, (1,), 1)},
        'InputChannel/DCA': {'Assign': (2, (0,), 64)},
        'Mix/Label': {'Name': _NAME, 'Color': _COLOR}, 'StMix/Label': {'Name': _NAME, 'Color': _COLOR},
        'Matrix/Label': {'Name': _NAME, 'Color': _COLOR}, 'Stereo/Label': {'Name': _NAME, 'Color': _COLOR},
        'DCA/Label': {'Name': _NAME, 'Color': _COLOR},
    },
    'Processing': {'Omni/InputPort/HeadAmp': {'Gain': (1, (2,), 1), '48V': (2, (0,), 1)}},
    'SceneInfo': {'Info': {'Title': _NAME}},
    'ProjectInfo': {'Info': {'ProductName': (0, (32,), 1), 'ProductSubName': (0, (32,), 1)}},
}
FLAT_ON = (2, (0, 1), 1)          # TF Editor and DM3 Editor files store channel on as one byte


def check_shapes(sec, family=None):
    if sec is None:
        return
    for path, want in (SHAPES.get(sec.function) or SHAPES.get(sec.field) or {}).items():
        c = sec.coll(path)
        if c is None:
            continue
        for name, (typ, sizes, most) in want.items():
            if name == 'On' and path == 'InputChannel/Fader' and family in ('TF', 'DM3'):
                typ, sizes, most = FLAT_ON
            pr = c.prbyname.get(name)
            if pr is not None and (pr.typ != typ or pr.size not in sizes or not 1 <= pr.count <= most):
                raise _damaged()


# BB-DM-MODEL: the header model is DM7 for DM7, DM7 Compact, DM5 and DM5 Compact; ProjectInfo tells them apart.
# Only the ProductSubName values an editor-made file showed are here (BB-DM-MODEL, and the DM3 and TF5 sessions of
# BB-G2-WALK). Any other value falls back to the family name.
FAMILY_OF = {'DM7': 'DM7', 'DM5': 'DM5', 'DM3': 'DM3', 'TF': 'TF'}
SUB_MODELS = {'DM7': ('DM7', 'DM7', 'dm7'), 'DM7C': ('DM7', 'DM7 Compact', 'dm7c'), 'DM5': ('DM5', 'DM5', 'dm5'),
              'DM5C': ('DM5', 'DM5 Compact', 'dm5c'), 'DM3': ('DM3', 'DM3', 'dm3'), 'TF5': ('TF', 'TF5', 'tf5')}
G2_BUSES = {'DM7': [('Mix', 'mix', 'MIX'), ('Matrix', 'matrix', 'MATRIX'), ('Stereo', 'stereo', 'ST')],
            'TF': [('Mix', 'mix', 'AUX'), ('StMix', 'mix', 'ST AUX'), ('Matrix', 'matrix', 'MATRIX'),
                   ('Stereo', 'stereo', 'ST')],
            'DM3': [('Mix', 'mix', 'MIX'), ('Matrix', 'matrix', 'MATRIX'), ('Stereo', 'stereo', 'ST')]}
G2_BUSES['DM5'] = G2_BUSES['DM7']
G2_NAME_MAX = 8                   # BB-DM-LOAD: DM Editor's name field shows 8 characters
# BB-DM-SAVE: the words stored in Label.Color, in DM Editor's Channel List column order -> (our key, label)
G2_COLOURS = [('Blue', 'blue', 'Blue'), ('Orange', 'orange', 'Orange'), ('Yellow', 'yellow', 'Yellow'),
              ('Purple', 'purple', 'Purple'), ('SkyBlue', 'cyan', 'Sky blue'), ('Pink', 'magenta', 'Pink'),
              ('Red', 'red', 'Red'), ('Green', 'green', 'Green'), ('LtGreen', 'lightgreen', 'Light green'),
              ('White', 'white', 'White'), ('OFF', 'off', 'Off')]
G2_FADER_MIN, G2_FADER_MAX = -138, 10        # BB-DM-RANGE: Fader.Level 0.01 dB, -32768 = -inf
G2_HA_MIN, G2_HA_MAX = -6, 66                # BB-DM-LOAD: HeadAmp.Gain 0.01 dB, whole dB written
G2_HPF_MIN, G2_HPF_MAX = 20, 2000            # BB-DM-RANGE: HPF.Frequency 0.1 Hz
G2_KEYS = ('rename', 'colour', 'patch', 'gain', 'phantom', 'hpf', 'fader', 'on')
CURRENT_NAMES = ('CurrentBackupFile.bup', 'CurrentBackupFile.bup.old')
MAX_INPUTS, MAX_BUSES, MAX_SCENES = 144, 128, 1000


def g2_colour_key(word):
    return next((k for w, k, _ in G2_COLOURS if w == word), None)


def g2_port_label(code):
    """BB-DM-LOAD: (0x0140 << 16) + 0x1000 + n-1 = OMNI n; (0x01a0 << 16) + n-1 = DANTE n; 0 = none."""
    if code is None:
        return None
    if code == 0:
        return 'None'
    grp, low = code >> 16, code & 0xffff
    if grp == 0x0140 and 0x1000 <= low < 0x1000 + 32:
        return 'OMNI %d' % (low - 0x1000 + 1)
    if grp == 0x01a0 and low < 144:
        return 'DANTE %d' % (low + 1)
    return None


def g2_local_port(code):
    if code and code >> 16 == 0x0140 and 0x1000 <= (code & 0xffff) < 0x1000 + 32:
        return (code & 0xffff) - 0x1000 + 1
    return None


def g2_ports():
    out = [{'code': 0, 'label': 'None', 'group': 'None'}]
    out += [{'code': (0x0140 << 16) | (0x1000 + i), 'label': 'OMNI %d' % (i + 1), 'group': 'OMNI'} for i in range(32)]
    out += [{'code': (0x01a0 << 16) | i, 'label': 'DANTE %d' % (i + 1), 'group': 'Dante'} for i in range(144)]
    return out


class Gen2Show:
    generation = 2

    def __init__(self, data, console=None):
        self.data = bytes(data)
        h = mbdf_header(self.data)
        if h and h['model'] in ('Rivage', 'PM10', 'PM7', 'PM5', 'PM3'):
            raise Refused('RIVAGE PM files are not read by this tool yet. It reads CL, QL, DM7, DM5, DM3 and TF files.')
        self.m = mbdf_parse(self.data)
        if self.m.kind == 'UserKey':
            raise Refused(MSG_USER_KEY)
        if self.m.kind != 'ProjectFile':
            raise Refused('This is a Yamaha %s file, not a whole show. Save the show in the editor and use that file.'
                          % {'Scene': 'scene', 'Preset': 'library'}.get(self.m.kind, 'part'))
        fam = FAMILY_OF.get(self.m.model)
        if not fam:
            raise Refused('This console is not supported. This tool reads CL, QL, DM7, DM5, DM3 and TF files.')
        info = self.m.section('ProjectInfo')
        check_shapes(info)
        sub = pname = None
        if info is not None and info.has('Info', 'ProductSubName'):
            sub = info.get('Info', 'ProductSubName')
        if info is not None and info.has('Info', 'ProductName'):
            pname = info.get('Info', 'ProductName')
        if sub in SUB_MODELS:
            self.family, self.model_name, self.model_key = SUB_MODELS[sub]
        else:
            f = FAMILY_OF.get(pname) or fam
            self.family, self.model_name = f, f
            self.model_key = {'DM7': 'dm7', 'DM5': 'dm5', 'DM3': 'dm3'}.get(f)
        self.version = self.m.version
        left = [MAX_TOTAL_INFLATED]
        self.current, self.backups, self.scene_recs, seen = None, [], [], set()
        for i, r in enumerate(self.m.records):
            if r['type'] != 'file':
                continue
            if r['name'] in CURRENT_NAMES:
                if r['name'] in seen:
                    raise _damaged()
                seen.add(r['name'])
                inner = self._inner(i, left)
                self.backups.append((i, inner))
                if r['name'] == CURRENT_NAMES[0]:
                    self.current = (i, inner)
            elif r['group'].startswith(('Scn', 'Scene')) and r['name'].lower().endswith(('.dm7s', '.dm3s', '.tfs')):
                self.scene_recs.append(i)
        if self.current is None or len(self.scene_recs) > MAX_SCENES:
            raise _damaged()
        self.mix = self.current[1].section('Mixing')
        self.proc = self.current[1].section('Processing')
        self.buses_of = G2_BUSES[self.family]
        if self.count() > MAX_INPUTS or any(self.mix.count(c) > MAX_BUSES for c, _, _ in self.buses_of) or \
                self.mix.count('DCA') > MAX_BUSES:
            raise _damaged()
        self._scene_rows = None

    def _inner(self, i, left):
        inner = mbdf_parse(inflate(self.m, self.m.records[i], left), 1, self.m.budget)
        if inner.section('Mixing') is None:
            raise _damaged()
        check_shapes(inner.section('Mixing'), self.family)
        if self.m.records[i]['name'] in CURRENT_NAMES:
            check_shapes(inner.section('Processing'), self.family)
        else:
            check_shapes(inner.section('SceneInfo'), self.family)
        return inner

    # ---- gates ------------------------------------------------------------------------------------------------------
    def write_why(self, key):
        if key == 'scenes':
            return ('Stored scenes on DM7 wait for a scene recall test in DM Editor. Leave out --all-scenes to change '
                    'the current scene.')
        if self.family in ('DM3', 'TF'):
            return ('%s files open read-only here: no write has been tested in %s Editor yet.' % (
                self.family, self.family))
        if self.version and self.version.startswith('V1.'):
            return ('This file is from DM7 firmware 1.x. It opens read-only here: no write has been tested in DM7 '
                    'Editor 1.7.5, the editor for firmware 1.x.')
        if self.model_key != 'dm7':
            return ('%s files open read-only here: only DM7 sessions were loaded in DM Editor after a write.'
                    % self.model_name)
        if self.version != 'V2.01':
            return ('Writes were tested on DM7 files from firmware V2.01 only. This file is %s, so it opens read-only.'
                    % self.version)
        if key == 'icon':
            return 'DM7 icons are read-only here: no icon write has been tested in DM Editor.'
        if key == 'dca':
            return 'DM7 DCA assigns are read-only here: no DCA write has been tested in DM Editor.'
        if key == 'name_bus':
            return 'DM7 mix, matrix and DCA names are read-only here: no bus name write has been tested in DM Editor.'
        if key == 'send':
            return 'Sends are not read from DM7 files yet, so this tool does not change them.'
        if key not in G2_KEYS:
            return 'That change is not available for this console.'
        return None

    def unproven(self):
        """What this read prints without an editor test behind it for this console and firmware (shown with ?)."""
        if self.family in ('DM7', 'DM5') and self.model_key == 'dm7' and self.version == 'V2.01':
            return ['icons', 'bus_names', 'dca_names', 'scenes']
        if self.family in ('DM7', 'DM5'):
            return ['names', 'colours', 'icons', 'patch', 'preamp', 'hpf', 'fader', 'on', 'dcas', 'bus_names',
                    'dca_names', 'scenes']
        return ['names', 'colours', 'icons', 'fader', 'on', 'bus_names', 'dca_names', 'scenes']

    # ---- reading ----------------------------------------------------------------------------------------------------
    def count(self):
        return self.mix.count('InputChannel')

    @staticmethod
    def _get(sec, path, name, idx=(), arr=0):
        try:
            return sec.get(path, name, idx, arr)
        except KeyError:
            return None

    def source(self, ch, sec=None, d=None):
        """The patch code of channel ch: InPatch/Bank[Select].Source. d: the file's bytes as edited so far."""
        sec = sec or self.mix
        try:
            sel = sec.get('InputChannel/InPatch', 'Select', [ch], 0, d) or 0
            return sec.get('InputChannel/InPatch/Bank', 'Source', [ch, 0, sel], 0, d)
        except KeyError:
            return None

    @staticmethod
    def hpf_bank(sec, ch):
        """BB-DM-SAVE: on the default EQ (PEQ.ActorSelect 0) the editor writes HPF[0]. Another EQ type: None."""
        try:
            b = sec.get('InputChannel/PEQ', 'ActorSelect', [ch])
        except KeyError:
            return None
        return 0 if b == 0 else None

    def channel(self, ch, diffs):
        s = self.mix

        def g(path, name, idx=(), arr=0):
            return self._get(s, path, name, [ch] + list(idx), arr)

        name, colour, icon = g('InputChannel/Label', 'Name'), g('InputChannel/Label', 'Color'), \
            g('InputChannel/Label', 'Icon')
        fl, on = g('InputChannel/Fader', 'Level'), g('InputChannel/Fader', 'On')
        out = {'n': ch + 1, 'id': 'ch%d' % (ch + 1), 'kind': 'input', 'label': 'CH %d' % (ch + 1), 'name': name,
               'colour': {'key': g2_colour_key(colour), 'code': colour} if colour is not None else None,
               'icon': {'key': icon.lower() if icon else None, 'code': icon} if icon is not None else None,
               'patch': None, 'preamp': None, 'hpf': None,
               'fader': None if fl is None else ({'inf': True} if fl <= -32768 else {'db': fl / 100.0}),
               'on': None if on is None else bool(on), 'dcas': None, 'mute_groups': None, 'sends': None,
               'scene_diff': diffs.get(ch, 0)}
        if self.family in ('DM7', 'DM5'):
            src = self.source(ch)
            lab = g2_port_label(src)
            out['patch'] = {'code': src, 'label': lab, 'known': lab is not None}
            port = g2_local_port(src)
            if port is not None and self.proc is not None:
                gain = self._get(self.proc, 'Omni/InputPort/HeadAmp', 'Gain', [0, port - 1])
                ph = self._get(self.proc, 'Omni/InputPort/HeadAmp', '48V', [0, port - 1])
                if gain is not None:
                    out['preamp'] = {'port': lab, 'port_n': port, 'gain_db': gain / 100.0, 'phantom': bool(ph)}
            b = self.hpf_bank(s, ch)
            hon = g('InputChannel/HPF', 'On', [b]) if b is not None else None
            hf = g('InputChannel/HPF', 'Frequency', [b]) if b is not None else None
            if hon is not None and hf is not None:
                out['hpf'] = {'on': bool(hon), 'freq': hf / 10.0}
            dc = s.coll('InputChannel/DCA')
            if dc is not None and 'Assign' in dc.prbyname:
                out['dcas'] = [k + 1 for k in range(dc.prbyname['Assign'].count) if g('InputChannel/DCA', 'Assign',
                                                                                      (), k)]
        return out

    def scene_list(self):
        if self._scene_rows is not None:
            return self._scene_rows
        rows, per, totals = [], {}, {'names': 0, 'colours': 0, 'patch': 0}
        n = self.count()
        patch = self.family in ('DM7', 'DM5')

        def values(s):
            return [(self._get(s, 'InputChannel/Label', 'Name', [ch]), self._get(s, 'InputChannel/Label', 'Color', [ch]),
                     self.source(ch, s) if patch else None) for ch in range(n)]
        cur = values(self.mix) if self.scene_recs else []
        left = [MAX_TOTAL_INFLATED]
        for k, i in enumerate(self.scene_recs):
            inner = self._inner(i, left)
            s = inner.section('Mixing')
            d = {'names': False, 'colours': False, 'patch': False}
            if s.count('InputChannel') == n:
                for ch, (a, b) in enumerate(zip(values(s), cur)):
                    hit = False
                    for j, key in enumerate(('names', 'colours', 'patch')):
                        if a[j] != b[j]:
                            d[key] = hit = True
                    if hit:
                        per[ch] = per.get(ch, 0) + 1
            for key in totals:
                totals[key] += 1 if d[key] else 0
            si = inner.section('SceneInfo')
            rows.append({'n': k + 1, 'title': self._get(si, 'Info', 'Title') if si else None, 'differs': d})
        self._scene_rows = (rows, per, totals)
        return self._scene_rows

    def buses(self):
        out = []
        for coll, kind, label in self.buses_of:
            c = self.mix.coll(coll)
            if c is None or 'Label' not in c.byname:
                continue
            for i in range(c.count):
                col = self._get(self.mix, coll + '/Label', 'Color', [i])
                out.append({'id': '%s%d' % (kind, i + 1), 'kind': kind, 'n': i + 1, 'label': '%s %d' % (label, i + 1),
                            'name': self._get(self.mix, coll + '/Label', 'Name', [i]),
                            'colour': {'key': g2_colour_key(col), 'code': col} if col else None, 'icon': None})
        return out

    def dcas(self):
        c = self.mix.coll('DCA')
        if c is None or 'Label' not in c.byname:
            return []
        return [{'n': i + 1, 'name': self._get(self.mix, 'DCA/Label', 'Name', [i])} for i in range(c.count)]

    def model(self):
        rows, per, totals = self.scene_list()
        chans = [self.channel(ch, per) for ch in range(self.count())]
        buses, dcas = self.buses(), self.dcas()
        warnings = []
        differ = sum(1 for r in rows if any(r['differs'].values()))
        if differ:
            one = differ == 1
            warnings.append('%d stored scene%s %s own channel names, colours or patch. Changes go to the current '
                            'scene only, so recalling %s brings the old ones back.' % (
                                differ, '' if one else 's', 'holds its' if one else 'hold their', 'it' if one else 'one'))
        ro = self.write_why('rename')
        if ro:
            warnings.append(ro)
        writes = {k: self.write_why(k) for k in G2_KEYS + ('icon', 'dca', 'name_bus', 'scenes')}
        dm = self.family in ('DM7', 'DM5')
        return {
            'file': {'bytes': len(self.data), 'generation': 2, 'container': 'mbdf', 'kind': 'project',
                     'entries': len(self.m.entries())},
            'console': {'family': self.family, 'model': self.model_name, 'model_key': self.model_key,
                        'model_from': 'file', 'hint': None},
            'firmware': {'label': 'Firmware %s' % self.version, 'format': self.version},
            'summary': '%s show, firmware %s. %d inputs, %d stored scene%s.' % (
                self.model_name, self.version, len(chans), len(rows), '' if len(rows) == 1 else 's'),
            'counts': {'inputs': len(chans), 'stereo_inputs': 0, 'mixes': sum(1 for b in buses if b['kind'] == 'mix'),
                       'matrices': sum(1 for b in buses if b['kind'] == 'matrix'), 'dcas': len(dcas),
                       'mute_groups': None, 'scenes': len(rows)},
            'channels': chans, 'buses': buses, 'dcas': dcas, 'mute_groups': [],
            'scenes': {'count': len(rows), 'current': None, 'differ': totals, 'list': rows},
            'ports': g2_ports() if dm else [],
            'palette': {'colours': [{'key': k, 'label': lab, 'code': w} for w, k, lab in G2_COLOURS], 'icons': [],
                        'name_max': G2_NAME_MAX if dm else 63,
                        'ranges': {'gain': [G2_HA_MIN, G2_HA_MAX], 'hpf': [G2_HPF_MIN, G2_HPF_MAX],
                                   'fader': [G2_FADER_MIN, G2_FADER_MAX]}},
            'unproven': self.unproven(),
            'writes': {k: {'ok': True} if v is None else {'ok': False, 'why': v} for k, v in writes.items()},
            'warnings': warnings,
        }

    # ---- writing ----------------------------------------------------------------------------------------------------
    def apply(self, ops):
        """Run ops in order on the current backup and its '.old' copy. -> (new bytes, changes, refused)."""
        changes, refused, bufs = [], [], {}
        inners = dict(self.backups)

        def buf(i):
            if i not in bufs:
                bufs[i] = bytearray(inners[i].data)
            return bufs[i]

        for op in ops:
            try:
                if not isinstance(op, dict):
                    raise Refused('That change is malformed.')
                self._op(op, buf, changes)
            except Refused as e:
                refused.append(str(e))
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                refused.append('That value is out of range for this console.')
        if refused:
            return self.data, changes, refused
        replace = {i: bytes(b) for i, b in bufs.items() if bytes(b) != inners[i].data}
        if not replace:
            return self.data, changes, refused
        return mbdf_build(self.m, replace), changes, refused

    def _need(self, key):
        why = self.write_why(key)
        if why:
            raise Refused(why)

    def _targets(self, op):
        t = op.get('target')
        n = self.count()
        if not isinstance(t, dict):
            raise Refused('Pick the channels to change.')
        if t.get('all') is True:
            return list(range(n))
        out = []
        if isinstance(t.get('ids'), list):
            for x in t['ids']:
                if not (isinstance(x, str) and x.startswith('ch') and x[2:].isdigit() and 1 <= int(x[2:]) <= n):
                    raise Refused('There is no %s on a %s.' % (_id_label(x), self.model_name))
                out.append(int(x[2:]) - 1)
        elif isinstance(t.get('channels'), list):
            for x in t['channels']:
                if not isinstance(x, int) or isinstance(x, bool) or not 1 <= x <= n:
                    raise Refused('There is no CH %s on a %s.' % (str(x)[:6], self.model_name))
                out.append(x - 1)
        if not out:
            raise Refused('Pick the channels to change.')
        return out

    def _dst(self, op):
        if op.get('scenes', 'current') not in (None, 'current'):
            self._need('scenes')
        return list(self.backups)

    def _op(self, op, buf, changes):
        name = op.get('op')
        if name == 'rename':
            self._need('rename')
            targets = self._targets(op)
            names = op['names'] if isinstance(op.get('names'), list) else [op.get('name')]
            if len(names) != len(targets):
                raise Refused('Give one name for each channel.')
            dst = self._dst(op)
            for ch, nm in zip(targets, names):
                try:
                    nm = clean_name(nm, G2_NAME_MAX)
                except Refused as e:
                    raise Refused('CH %d: %s' % (ch + 1, e))
                for i, inner in dst:
                    inner.section('Mixing').put(buf(i), 'InputChannel/Label', 'Name', nm, [ch])
                changes.append('CH %d renamed %s.' % (ch + 1, nm) if nm else 'CH %d name cleared.' % (ch + 1))
        elif name == 'set':
            targets = self._targets(op)
            if 'icon' in op:
                self._need('icon')
            fields = [k for k in ('colour', 'fader_db', 'on', 'hpf') if k in op]
            if not fields:
                raise Refused('Say what to set.')
            for f in fields:
                self._need({'fader_db': 'fader'}.get(f, f))
            dst = self._dst(op)
            for ch in targets:
                for f in fields:
                    v = op[f]
                    if f == 'colour':
                        word = next((w for w, k, _ in G2_COLOURS if k == v), None)
                        if word is None:
                            raise Refused('Pick a colour: %s.' % ', '.join(k for _, k, _ in G2_COLOURS))
                        for i, inner in dst:
                            inner.section('Mixing').put(buf(i), 'InputChannel/Label', 'Color', word, [ch])
                        changes.append('CH %d colour set to %s.' % (ch + 1, next(lab for w, _, lab in G2_COLOURS
                                                                               if w == word)))
                    elif f == 'fader_db':
                        if v in ('-inf', 'off', None):
                            lv = -32768
                        else:
                            db = _number(v, 'A fader level is a number of dB, or off.')
                            if db > G2_FADER_MAX or db < G2_FADER_MIN:
                                raise Refused('CH %d: faders go from %d dB to +%d dB, or off.' % (
                                    ch + 1, G2_FADER_MIN, G2_FADER_MAX))
                            lv = int(round(db * 100))
                        for i, inner in dst:
                            inner.section('Mixing').put(buf(i), 'InputChannel/Fader', 'Level', lv, [ch])
                        changes.append('CH %d fader set to %s.' % (ch + 1, '-inf' if lv <= -32768 else '%+.2f dB' % (
                            lv / 100.0)))
                    elif f == 'on':
                        _bool_field(v, 'Channel on')
                        for i, inner in dst:
                            inner.section('Mixing').put(buf(i), 'InputChannel/Fader', 'On', v, [ch])
                        changes.append('CH %d turned %s.' % (ch + 1, 'on' if v else 'off'))
                    elif f == 'hpf':
                        if not isinstance(v, dict) or not ({'on', 'freq'} & set(v)):
                            raise Refused('Say HPF on, off, or a frequency.')
                        hz = None
                        if 'on' in v:
                            _bool_field(v['on'], 'HPF on')
                        if 'freq' in v:
                            hz = _number(v['freq'], 'An HPF frequency is a number of Hz.')
                            if hz < G2_HPF_MIN or hz > G2_HPF_MAX:
                                raise Refused('CH %d: the HPF goes from %d Hz to %d Hz.' % (ch + 1, G2_HPF_MIN,
                                                                                         G2_HPF_MAX))
                            hz = round(hz * 10) / 10.0
                        for i, inner in dst:
                            sec = inner.section('Mixing')
                            b = self.hpf_bank(sec, ch)
                            if b is None:
                                raise Refused('CH %d uses another EQ type. Set its HPF in DM Editor.' % (ch + 1))
                            if 'on' in v:
                                sec.put(buf(i), 'InputChannel/HPF', 'On', v['on'], [ch, b])
                            if hz is not None:
                                sec.put(buf(i), 'InputChannel/HPF', 'Frequency', int(round(hz * 10)), [ch, b])
                        if 'on' in v:
                            changes.append('CH %d HPF %s.' % (ch + 1, 'on' if v['on'] else 'off'))
                        if hz is not None:
                            changes.append('CH %d HPF set to %g Hz.' % (ch + 1, hz))
        elif name == 'patch':
            self._need('patch')
            targets = self._targets(op)
            code = self.port_code(op.get('source'))
            dst = self._dst(op)
            for ch in targets:
                for i, inner in dst:
                    sec = inner.section('Mixing')
                    sel = sec.get('InputChannel/InPatch', 'Select', [ch])
                    sec.put(buf(i), 'InputChannel/InPatch/Bank', 'Source', code, [ch, 0, sel])
                changes.append('CH %d patched to %s.' % (ch + 1, g2_port_label(code)) if code
                               else 'CH %d unpatched.' % (ch + 1))
        elif name == 'preamp':
            fields = [k for k in ('gain_db', 'phantom') if k in op]
            if not fields:
                raise Refused('Say the gain or 48V.')
            for k in fields:
                self._need('gain' if k == 'gain_db' else 'phantom')
            gdb = None
            if 'gain_db' in op:
                gdb = _number(op['gain_db'], 'Gain is a number of dB.')
            if 'phantom' in op:
                _bool_field(op['phantom'], '48V')
            dst = self._dst(op)
            ci, cur = self.current
            for ch in self._targets(op):
                # BB-DM-ORDER: the port this channel is patched to now, as edited so far in this call
                src = self.source(ch, cur.section('Mixing'), buf(ci))
                port, lab = g2_local_port(src), g2_port_label(src)
                if port is None:
                    raise Refused('CH %d comes from %s. Its head amp is not in the console: set it on the stage box or '
                                  'its own device.' % (ch + 1, lab if src else 'no input'))
                if gdb is not None and (gdb < G2_HA_MIN or gdb > G2_HA_MAX):
                    raise Refused('CH %d: head amp gain goes from %d dB to +%d dB.' % (ch + 1, G2_HA_MIN, G2_HA_MAX))
                for i, inner in dst:
                    sec = inner.section('Processing')
                    if sec is None:
                        raise Refused('This file has no head amp section.')
                    if gdb is not None:
                        sec.put(buf(i), 'Omni/InputPort/HeadAmp', 'Gain', int(round(gdb)) * 100, [0, port - 1])
                    if 'phantom' in op:
                        sec.put(buf(i), 'Omni/InputPort/HeadAmp', '48V', op['phantom'], [0, port - 1])
                if gdb is not None:
                    changes.append('%s gain set to %+d dB (CH %d).' % (lab, int(round(gdb)), ch + 1))
                if 'phantom' in op:
                    changes.append('%s 48V %s (CH %d).' % (lab, 'on' if op['phantom'] else 'off', ch + 1))
        elif name in ('send', 'dca', 'name_bus'):
            self._need(name)
            raise Refused('That change is not available for this console.')
        else:
            raise Refused('That change is not available for this console.')

    def port_code(self, src):
        if src in ('none', 'None', 0):
            return 0
        if isinstance(src, int) and not isinstance(src, bool):
            if g2_port_label(src):
                return src
        elif isinstance(src, str):
            want = src.replace(' ', '').upper()
            for p in g2_ports():
                if p['label'].replace(' ', '').upper() == want:
                    return p['code']
        raise Refused('Pick a source from the patch list (run "ports").')


# =====================================================================================================================
# Open, check, write
# =====================================================================================================================
def open_show(data, console=None):
    if clf_kind(data) is not None:
        return Gen1Show(data, console)
    if is_mbdf(data):
        return Gen2Show(data, console)
    raise Refused(MSG_NOT_YAMAHA)


def check(data):
    """[(ok, sentence)] for the whole file: the container, every checksum or schema, and every entry."""
    out = []
    if clf_kind(data) is not None:
        c = clf_parse(data, verify=False)
        out.append((True, 'The record tree reads to its exact end (%d data records).' % len(c.leaves)))
        out.append((c.bad_checksums == 0, 'Checksums: %d of %d blocks match.' % (c.checked - c.bad_checksums,
                                                                                 c.checked)))
        if not c.bad_checksums:
            s = Gen1Show(data)
            out.append((True, 'Scene format %d. %d stored scene%s.' % (s.fmt, len(c.stored_ids()),
                                                                     '' if len(c.stored_ids()) == 1 else 's')))
        return out
    if is_mbdf(data):
        h = mbdf_header(data)
        if h and h['model'] in ('Rivage', 'PM10', 'PM7', 'PM5', 'PM3'):
            raise Refused('RIVAGE PM files are not read by this tool yet. It reads CL, QL, DM7, DM5, DM3 and TF files.')
        m = mbdf_parse(data)
        out.append((True, 'Every record reads to its exact end (%d records).' % len(m.records)))
        out.append((mbdf_build(m, {}) == bytes(data), 'The container rebuilds byte for byte.'))
        left = [MAX_TOTAL_INFLATED]
        sections = len(m.sections())
        for r in m.entries():
            inner = mbdf_parse(inflate(m, r, left), 1, m.budget)
            if inner.kind in ('Backup', 'Scene'):
                sections += len(inner.sections())
        out.append((True, 'Every entry inflates (%d entries, %d bytes) and every schema matches its MD5 (%d '
                          'sections).' % (len(m.entries()), MAX_TOTAL_INFLATED - left[0], sections)))
        Gen2Show(data)
        return out
    raise Refused(MSG_NOT_YAMAHA)


def verify_written(old, new, show, console):
    """Re-read the written bytes with every check of `check` before they reach a disk."""
    if any(not ok for ok, _ in check(new)):
        raise Refused('That change did not pass the file check, so nothing was written.')
    again = open_show(new, console)
    if isinstance(show, Gen1Show):
        same_tree = [(p, o, s) for p, o, s in show.c.leaves] == [(p, o, s) for p, o, s in again.c.leaves]
        if len(old) != len(new) or again.fmt != show.fmt or not same_tree:
            raise Refused('That change did not pass the file check, so nothing was written.')
    elif (again.version, again.model_name, again.m.kind) != (show.version, show.model_name, show.m.kind):
        raise Refused('That change did not pass the file check, so nothing was written.')
    return again


# =====================================================================================================================
# Command line
# =====================================================================================================================
def parse_channels(spec):
    """'1,3,5-8' / 'st1l' / 'all' -> a target."""
    spec = spec.strip().lower()
    if spec == 'all':
        return {'all': True}
    ids = []
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if part.startswith('st') or part.startswith('ch'):
            ids.append(part)
        elif '-' in part:
            a, b = part.split('-', 1)
            if not (a.isdigit() and b.isdigit()) or int(a) > int(b):
                raise Refused('Channels look like 3, 1-8, 1,3,5-8, st1l or all.')
            ids += ['ch%d' % n for n in range(int(a), int(b) + 1)]
        elif part.isdigit():
            ids.append('ch%d' % int(part))
        else:
            raise Refused('Channels look like 3, 1-8, 1,3,5-8, st1l or all.')
    if not ids:
        raise Refused('Pick the channels to change.')
    return {'ids': ids}


def onoff(v, what):
    v = str(v).lower()
    if v in ('on', 'true', '1', 'yes'):
        return True
    if v in ('off', 'false', '0', 'no'):
        return False
    raise Refused('%s is on or off.' % what)


def ops_from_args(a):
    scenes = 'all' if getattr(a, 'all_scenes', False) else 'current'
    if a.cmd == 'apply':
        try:
            with open(a.ops, encoding='utf-8') as f:
                ops = json.load(f)
        except (OSError, ValueError) as e:
            raise Refused('Could not read %s: %s' % (a.ops, e))
        if not isinstance(ops, list):
            raise Refused('OPS.json holds a list of changes.')
        if scenes == 'all':
            for op in ops:
                if isinstance(op, dict) and op.get('op') not in ('name_bus',):
                    op.setdefault('scenes', 'all')
        return ops
    if a.cmd == 'busname':
        return [{'op': 'name_bus', 'bus': a.bus.lower(), 'name': a.name}]
    target = parse_channels(a.channels)
    base = {'target': target, 'scenes': scenes}
    if a.cmd == 'rename':
        return [dict(base, op='rename', names=a.names)]
    if a.cmd == 'colour':
        return [dict(base, op='set', colour=a.colour.lower())]
    if a.cmd == 'icon':
        return [dict(base, op='set', icon=icon_key(a.icon))]
    if a.cmd == 'fader':
        v = a.db.lower()
        return [dict(base, op='set', fader_db='-inf' if v in ('off', '-inf') else _number(
            v, 'A fader level is a number of dB, or off.'))]
    if a.cmd == 'on':
        return [dict(base, op='set', on=onoff(a.state, 'Channel on'))]
    if a.cmd == 'hpf':
        h = {}
        if a.hpf_on is not None:
            h['on'] = a.hpf_on
        if a.freq is not None:
            h['freq'] = a.freq
        if not h:
            raise Refused('Say --on, --off or --freq HZ.')
        return [dict(base, op='set', hpf=h)]
    if a.cmd == 'patch':
        src = a.source
        return [dict(base, op='patch', source=int(src) if src.isdigit() else src)]
    if a.cmd == 'preamp':
        op = dict(base, op='preamp')
        if a.gain is not None:
            op['gain_db'] = a.gain
        if a.phantom is not None:
            op['phantom'] = onoff(a.phantom, '48V')
        if len(op) == 3:
            raise Refused('Say --gain DB, --48v on or --48v off.')
        return [op]
    if a.cmd == 'dca':
        return [dict(base, op='dca', dca=a.dca, mode=a.mode)]
    raise Refused('Unknown command.')


def _fmt_db(f):
    if f is None:
        return '-'
    if f.get('inf'):
        return '-inf'
    return '%+.2f' % f['db'] if f['db'] else '0.00'


def print_show(m):
    unp = set(m.get('unproven') or ())

    def q(key):
        return '?' if key in unp else ''
    con, fw = m['console'], m['firmware']
    print('Yamaha %s, %s. %s' % (con['model'], fw['label'], m['summary']))
    print('File: %d bytes, generation %d (%s).' % (m['file']['bytes'], m['file']['generation'], m['file']['container']))
    if con['model_from'] == 'guess':
        print('Model: a guess (the file does not record it). Pass --console.')
    print()
    head = ('CH', 'Name' + q('names'), 'Colour' + q('colours'), 'Icon' + q('icons'), 'Patch' + q('patch'),
            'Head amp' + q('preamp'), 'HPF' + q('hpf'), 'Fader' + q('fader'), 'On' + q('on'), 'DCA' + q('dcas'))
    rows = [head]
    for c in m['channels']:
        pa = c['patch']
        pre = c['preamp']
        h = c['hpf']
        rows.append((
            c['label'], c['name'] if c['name'] is not None else '-',
            (c['colour'] or {}).get('key') or str((c['colour'] or {}).get('code', '-')),
            (c['icon'] or {}).get('key') or str((c['icon'] or {}).get('code', '-')),
            '-' if pa is None else (pa['label'] or 'code %s' % pa['code']),
            '-' if pre is None else '%+d dB%s' % (pre['gain_db'], ' 48V' if pre['phantom'] else ''),
            '-' if h is None else '%s %s' % ('on' if h['on'] else 'off', ('%g Hz' % h['freq']) if h['freq'] else '?'),
            _fmt_db(c['fader']), '-' if c['on'] is None else ('on' if c['on'] else 'OFF'),
            '-' if c['dcas'] is None else (','.join(str(k) for k in c['dcas']) or '')))
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(head))]
    for r in rows:
        print('  '.join(str(v).ljust(w) for v, w in zip(r, widths)).rstrip())
    print()
    for kind, title in (('mix', 'Mixes'), ('matrix', 'Matrices'), ('stereo', 'Stereo'), ('mono', 'Mono')):
        bs = [b for b in m['buses'] if b['kind'] == kind]
        if bs:
            print('%s%s: %s' % (title, q('bus_names'), ', '.join('%s %s' % (b['label'], b['name'] or '-') for b in bs)))
    if m['dcas']:
        print('DCAs%s: %s' % (q('dca_names'), ', '.join('%d %s' % (d['n'], d['name'] or '-') for d in m['dcas'])))
    if m['mute_groups']:
        print('Mute groups: %s' % ', '.join('%d %s' % (d['n'], d['name'] or '-') for d in m['mute_groups']))
    sc = m['scenes']
    print('Stored scenes%s: %d%s' % (q('scenes'), sc['count'], ('. %d hold other names, %d other colours, %d other '
                                                                'patch.' % (sc['differ']['names'],
                                                                            sc['differ']['colours'],
                                                                            sc['differ']['patch'])) if sc['count']
                                     else '.'))
    opened = [k for k, v in m['writes'].items() if v['ok']]
    print('Writes open for this file: %s.' % (', '.join(opened) if opened else 'none'))
    if unp:
        print('? = read by the same path, but no editor test has checked this field on this console, firmware or '
              'scene format.')
    for w in m['warnings']:
        print('Note: ' + w)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='yamaha_tool.py', description=__doc__,
                                 epilog='Format notes: ../references/FORMAT.md',
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')
    sub.required = True

    def add(name, helptext, write=True):
        p = sub.add_parser(name, help=helptext, description=helptext)
        if write:
            p.add_argument('input', help='the show file to read')
            p.add_argument('output', help='the new file to write (same file type)')
            p.add_argument('--dry-run', action='store_true', help='check everything, write nothing')
            p.add_argument('--all-scenes', action='store_true',
                           help='CL scene format 7 only: send names, colours and patch to every stored scene too')
        else:
            p.add_argument('input', help='the show file to read')
        p.add_argument('--console', choices=sorted(CL_MODELS),
                       help='CL/QL only: the console model (a .CLF does not record it)')
        return p

    p = add('show', 'print the show: channels, buses, DCAs, scenes, and what can change', write=False)
    p.add_argument('--json', action='store_true', help='print the whole model as JSON')
    add('check', 'check the container, every checksum or schema, and every entry', write=False)
    add('ports', 'list the patch sources this tool can write on this console', write=False)
    p = add('rename', 'rename channels (8 characters, plain ASCII)')
    p.add_argument('channels')
    p.add_argument('names', nargs='+', help='one name per channel, in order')
    p = add('colour', 'set the channel colour')
    p.add_argument('channels')
    p.add_argument('colour')
    p = add('icon', 'set the channel icon (CL and QL)')
    p.add_argument('channels')
    p.add_argument('icon')
    p = add('fader', 'set the channel fader in dB (off = -inf)')
    p.add_argument('channels')
    p.add_argument('db')
    p = add('on', 'turn the channel ON key on or off')
    p.add_argument('channels')
    p.add_argument('state', help='on or off')
    p = add('hpf', 'set the high-pass filter')
    p.add_argument('channels')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--on', dest='hpf_on', action='store_const', const=True)
    g.add_argument('--off', dest='hpf_on', action='store_const', const=False)
    p.add_argument('--freq', type=float, help='Hz')
    p = add('patch', 'patch channels to a source ("DANTE 3", "OMNI 2", "INPUT 12", none)')
    p.add_argument('channels')
    p.add_argument('source')
    p = add('preamp', 'set gain and 48V of the head amp each channel is patched to (console inputs only)')
    p.add_argument('channels')
    p.add_argument('--gain', type=float, help='dB, whole steps')
    p.add_argument('--48v', dest='phantom', help='on or off')
    p = add('dca', 'assign channels to a DCA (CL and QL)')
    p.add_argument('channels')
    p.add_argument('dca', type=int)
    p.add_argument('--mode', choices=('add', 'remove', 'only'), default='add')
    p = add('busname', 'rename a mix, matrix, DCA or mute group (CL and QL)')
    p.add_argument('bus', help='mix3, matrix1, dca2 or mute1')
    p.add_argument('name')
    p = add('apply', 'run a JSON list of changes (see the top of this file)')
    p.add_argument('ops', help='OPS.json')
    a = ap.parse_args(argv)

    try:
        with open(a.input, 'rb') as f:
            data = f.read(MAX_BYTES + 1)
        if a.cmd == 'check':
            results = check(data)
            for ok, text in results:
                print('%s %s' % ('ok  ' if ok else 'FAIL', text))
            return 0 if all(ok for ok, _ in results) else 1
        show = open_show(data, a.console)
        if a.cmd == 'show':
            m = show.model()
            if a.json:
                print(json.dumps(m, indent=1))
            else:
                print_show(m)
            return 0
        if a.cmd == 'ports':
            ports = cl_ports(show.family, show.key) if isinstance(show, Gen1Show) else (
                g2_ports() if show.family in ('DM7', 'DM5') else [])
            if not ports:
                print('No patch is read or written for %s files.' % show.family)
            for p in ports:
                code = ('0x%08X' % p['code']) if p['code'] > 255 else str(p['code'])
                print('%-10s %-12s %s' % (code, p['label'], p['group']))
            return 0
        if os.path.exists(a.output) and os.path.samefile(a.input, a.output):
            raise Refused('Write a new file. This tool does not overwrite the show it reads.')
        if os.path.splitext(a.input)[1].lower() != os.path.splitext(a.output)[1].lower():
            raise Refused('Keep the file type: give the output the same extension as the input (%s).' % (
                os.path.splitext(a.input)[1] or 'none'))
        ops = ops_from_args(a)
        new, changes, refused = show.apply(ops)
        if refused:
            for r in refused:
                print('refused: ' + r, file=sys.stderr)
            print('Nothing was written.', file=sys.stderr)
            return 1
        if new != data:
            verify_written(data, new, show, a.console)
        for c in changes:
            print(c)
        if new == data:
            print('Every value was already set, so no byte changed: the output is a copy of the input.')
        elif isinstance(show, Gen1Show):
            n = sum(1 for x, y in zip(data, new) if x != y)
            print('%d bytes changed (checksums included), size unchanged.' % n)
        else:
            print('%d of %d entries rewritten, firmware %s kept.' % (
                sum(1 for _ in show.backups), len(show.m.entries()), show.version))
        if a.dry_run:
            print('Dry run: nothing written.')
            return 0
        with open(a.output, 'wb') as f:
            f.write(new)
        print('Wrote %s. Open it in the Yamaha editor and save it there before it goes near a console.' % a.output)
        return 0
    except Refused as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print('Could not read or write the file: %s' % e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
