#!/usr/bin/env python3
"""consoles.py - the console models the session maker can write, and the baseline file behind each version.

A baseline is an editor-saved DEFAULT session: open the console's offline editor, start a new session, save it as
digico/scripts/baselines/<key>_v<build>.ses (or the folder SM_BASELINES names). Versions are discovered from those file names, so dropping in a
new baseline adds the version (call refresh() in a running process).

Facts per model:
  family            file-family code at 0x0b. SD10 saves as SD8, SD11 as SD9, SD5CS as SD5, SD12 as SDC,
                    Quantum 7 as SDQ (from the editors' own lookup table, the decode notes (not published).
  max_inputs        input channels (a stereo channel counts as one). DiGiCo's published figures, NOT checked in the
                    editors yet (max_inputs_verified False), except the SD8 (_MAX_VERIFIED). Where unsure the number
                    is the lower, safe one.
  mustard_cap       Mustard instances (a stereo channel uses 2). Quantum 225 = 24 is editor-verified: on load the
                    editor turns off the excess in channel order. The manual gives no per-model table ("dependent on
                    the model of console") and no limit string exists in the editors, so the other Quantums use 24
                    too: every Mustard count seen in a real session (Q5 22, Q338 16, Q225 7) fits it. Unverified.
  spice_rack_slots  live Chilli 6 slots in the default session (type 0x1f records with 67 slots).
  engine_room       input engine channels that fit in the default session (a stereo channel takes 2): on SD models
                    the inputs share one pool with the aux, group and matrix buses, on Quantum TB In caps it at 254
                    (or 255). From layout.engine_room() on the newest baseline; None when no baseline has the field.
  tested            {build: True} when output for that model and build has been loaded in the real editor.

Overrides without code changes: baselines/console_facts.json, e.g.
  {"q112": {"max_inputs": 72, "max_inputs_verified": true}, "q338": {"tested": {"2242": true}}}
"""
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS = (os.environ.get('SM_BASELINES') or os.path.join(ROOT, 'baselines'))
TOOLS = ROOT  # ses.py and dlive2digico.py sit next to this package
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
FACTS = os.path.join(DEFAULTS, 'console_facts.json')
BASELINE_RE = re.compile(r'^([a-z0-9]+)_v(\d{3,5})\.ses$')

# key, name, family, default inputs (fallback), max inputs, Mustard, Spice Rack slots, note for the UI
_MODELS = [
    ('q112', 'Quantum 112', 'Q1', 48, 48, True, 6, ''),
    ('q225', 'Quantum 225', 'Q2', 48, 72, True, 6, ''),
    ('q225p', 'Quantum 225 Pulse', 'Q2', 48, 96, True, 6, 'Needs the Pulse extension on the console (V1742 or newer).'),
    ('q338', 'Quantum 326/338', 'Q3', 48, 128, True, 8, ''),
    ('q338p', 'Quantum 338 Pulse', 'Q3', 48, 156, True, 8, 'Needs the Pulse extension on the console (V1742 or newer).'),
    ('q5', 'Quantum 5', 'Q5', 108, 124, True, 12, ''),
    ('q7', 'Quantum 7', 'SDQ', 72, 253, True, 16, ''),
    ('q852', 'Quantum 852', 'Q8', 72, 253, True, 32, ''),
    ('sd5', 'SD5', 'SD5', 108, 124, False, 0, ''),
    ('sd5cs', 'SD5 CS', 'SD5', 108, 124, False, 0, ''),
    ('sd7', 'SD7', 'SD7', 72, 253, False, 0, 'Theatre and Broadcast extensions use the same file'),
    ('sd8', 'SD8', 'SD8', 60, 120, False, 0, ''),       # 120: editor-proven, see _MAX_VERIFIED
    ('sd9', 'SD9', 'SD9', 48, 96, False, 0, ''),
    ('sd10', 'SD10', 'SD8', 96, 96, False, 0, ''),
    ('sd11', 'SD11 / SD11i', 'SD9', 32, 32, False, 0, ''),
    ('sd12', 'SD12', 'SDC', 48, 72, False, 0, 'SD12-96 uses the same file'),
]
# max_inputs proven in the console's own editor. SD8: DiGiCo lists 60, but the SD8 editors V1455, V1619 and V2242
# booted 120-input sessions built on their own defaults and re-saved all 120 names,
# the decode notes (not published), and a real 65-input SD8 show loads in full. The default session has 60.
_MAX_VERIFIED = {'sd8'}
MUSTARD_CAP_Q225 = 24          # editor-verified (README: the editor turns Mustard off past 24 instances)
MUSTARD_CAP_DEFAULT = 24       # other Quantums: unverified, see module docstring
# DiGiCo's V1742 release notes (Pulse table): Q338 36, Q338 Pulse 48, Q225 Pulse 36 Mustard channels.
MUSTARD_CAP_SPEC = {'q225': MUSTARD_CAP_Q225, 'q225p': 36, 'q338': 36, 'q338p': 48}

# Builds whose generated output has been loaded in the real editor (Quantum 225 V2242: the relayout candidates
# s01-s13 and the dLive translations v2-v7 all loaded in the offline editor).
_TESTED = {('q225', 2242)}

CONSOLES = {}


def _discover():
    """{key: {build: abs path}} from the baseline file names."""
    out = {}
    try:
        names = os.listdir(DEFAULTS)
    except OSError:
        return out
    for fn in names:
        m = BASELINE_RE.match(fn)
        if m:
            out.setdefault(m.group(1), {})[int(m.group(2))] = os.path.join(DEFAULTS, fn)
    return out


_readable_cache = {}       # path -> ((size, mtime), ok)
UNREADABLE = {}            # key -> {build: why}, versions left out of the table (for logs and the selftest)


def _readable(path):
    """True when ses.py can map every input of this baseline: each section-201 channel record carries a header
    length the reader knows (ses.CHREC_HL). A baseline saved by a build with a new record length (Q1 and Q8 at
    V2126 use 0x78) would otherwise build a file whose read-back finds no channels. ~1 ms, cached per file."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    sig = (st.st_size, st.st_mtime)
    hit = _readable_cache.get(path)
    if hit and hit[0] == sig:
        return hit[1]
    try:
        from ses import CHREC_HL
        from . import layout
        with open(path, 'rb') as f:
            d = f.read()
        recs = layout.input_group(layout.Container(d).sec(201)[1])[3]
        ok = bool(recs) and len(recs) == _header_inputs(path) and all(r[2] in CHREC_HL for r in recs)
    except Exception:  # noqa: BLE001 - a half-written or foreign file is simply not offered
        ok = False
    _readable_cache[path] = (sig, ok)
    return ok


_room_cache = {}           # path -> ((size, mtime), room)


def _engine_room(path):
    """Input engine channels the default session has room for (layout.engine_room: SD inputs share the pool with
    the buses, a stereo channel takes 2), or None for a file without EngineChannel (V1455). Newest baseline first,
    so a V1455 version gets the same limit as the console's newer builds. Cached per file."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    sig = (st.st_size, st.st_mtime)
    hit = _room_cache.get(path)
    if hit and hit[0] == sig:
        return hit[1]
    try:
        from . import layout
        with open(path, 'rb') as f:
            r = layout.engine_room(f.read())
        room = r['room'] if r else None
    except Exception:  # noqa: BLE001 - unreadable files are already left out by _readable()
        room = None
    _room_cache[path] = (sig, room)
    return room


def _header_inputs(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(0x28)
        return struct.unpack_from('<H', head, 0x26)[0]
    except (OSError, struct.error):
        return None


def _load_facts():
    try:
        with open(FACTS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def refresh():
    """Rebuild CONSOLES in place from the files on disk (and console_facts.json)."""
    found, facts = _discover(), _load_facts()
    table = {}
    UNREADABLE.clear()
    for key, name, family, def_in, max_in, mustard, spice, note in _MODELS:
        for v, path in list(found.get(key, {}).items()):
            if not _readable(path):
                del found[key][v]
                UNREADABLE.setdefault(key, {})[v] = 'channel records the reader does not know'
        versions = dict(sorted(found.get(key, {}).items(), reverse=True))
        newest = next(iter(versions.values()), None)
        room = next((r for r in (_engine_room(pth) for pth in versions.values()) if r is not None), None)
        e = {
            'key': key, 'name': name, 'family': family,
            'versions': versions,
            'default_inputs': (_header_inputs(newest) if newest else None) or def_in,
            'max_inputs': max_in, 'max_inputs_verified': key in _MAX_VERIFIED,
            'mustard': mustard,
            'mustard_cap': MUSTARD_CAP_SPEC.get(key, MUSTARD_CAP_DEFAULT) if mustard else None,
            'mustard_cap_verified': key == 'q225',
            'spice_rack_slots': spice,
            'engine_room': room,
            'tested': {v: (key, v) in _TESTED for v in versions},
            'note': note,
        }
        f = facts.get(key) or {}
        for k in ('max_inputs', 'max_inputs_verified', 'mustard_cap', 'mustard_cap_verified', 'spice_rack_slots',
                  'name', 'note'):
            if k in f:
                e[k] = f[k]
        for v, ok in (f.get('tested') or {}).items():
            if int(v) in versions:
                e['tested'][int(v)] = bool(ok)
        table[key] = e
    CONSOLES.clear()
    CONSOLES.update(table)
    return CONSOLES


def get(key):
    """The console entry, or ValueError with a sentence a user can read."""
    c = CONSOLES.get(key)
    if c is None:
        raise ValueError('Unknown console %r.' % (key,))
    return c


def console_list():
    """Consoles that have at least one baseline, in picker order (Quantum first), for the UI."""
    out = []
    for key, *_ in _MODELS:
        c = CONSOLES.get(key)
        if not c or not c['versions']:
            continue
        out.append({'key': key, 'name': c['name'], 'family': c['family'],
                    'versions': list(c['versions']), 'tested': dict(c['tested']),
                    'mustard': c['mustard'], 'mustard_cap': c['mustard_cap'],
                    'max_inputs': c['max_inputs'], 'default_inputs': c['default_inputs'],
                    'spice_rack_slots': c['spice_rack_slots'], 'engine_room': c['engine_room'],
                    'note': c['note']})
    return out


refresh()

if __name__ == '__main__':
    for c in console_list():
        print('%-6s %-18s %-4s in %3d max %3d room %-4s mustard %-5s cap %-4s spice %2d versions %s tested %s' % (
            c['key'], c['name'], c['family'], c['default_inputs'], c['max_inputs'], c['engine_room'], c['mustard'],
            c['mustard_cap'], c['spice_rack_slots'], c['versions'], [v for v, t in c['tested'].items() if t]))
