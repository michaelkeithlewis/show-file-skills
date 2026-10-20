#!/usr/bin/env python3
"""build.py - a session request -> a DiGiCo .ses, a read-back of what the file holds, checks and a report.

usage: python3 -m sessionmaker.build <req.json> <out.ses>      (from digico/scripts)

Request (the web app and the CLI send the same dict):
  {'console': 'q225', 'version': 2242, 'title': 'Club Night 5/14',
   'channels': [{'name': 'Kick In', 'stereo': False, 'category': 'kick_in', 'phantom': None, 'source': 'Beta 91',
                 'notes': None, 'full_name': optional long name}, ...],
   'processing': 'templates' | 'none',
   'role': 'foh' | 'mon' (optional, default foh: monitor templates where the data has them),
   'overflow': 'error' | 'truncate' (optional, default error: too many channels raises ValueError),
   optional blocks, see options.py (absent = the console default, the file is the same as without them):
   'buses': 'auto' | {'aux_mono', 'aux_stereo', 'grp_mono', 'grp_stereo'},
   'fx': [{'kind', 'feed_aux', 'return', 'name', 'sends'}],
   'mixes': {'stereo', 'mono', 'click', 'outputs', 'names'},  ('monitor mixes' preset: IEM / wedge sends)
   'sends': [{'ch', 'aux', 'level_db', 'pre', 'pan'}],
   'patch': {'mode': 'rack' | 'local' | 'none', 'start', 'gain_db', 'phantom'}}

Steps:
  1. Take the console's editor-saved default session for that build (consoles.py).
  2. Relayout it to the request: channel count, order, stereo flags, names (layout.relayout), title as the
     session notes. Names written to the console are 8 characters at most; the report keeps the full name.
  3. Write per-instrument processing (process.py), Mustard only on Quantum and within the console's cap.
  With option blocks: the default is restructured to the bus layout first (buses.py), FX return channels join the
  layout, FX units are added after the relayout (fx.py), and mixes, sends and the input patch are written after the
  processing (sends.py, patch.py). options.py holds the order and the starting values.
  4. Check the structure (validate.py), write the file, parse it back with ses.py and decode every channel.
Errors a user can fix (unknown console, no channels, too many channels) raise ValueError with a plain sentence.
"""
import datetime
import json
import os
import re
import sys
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ROOT  # ses.py and dlive2digico.py sit next to this package
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from ses import Session  # noqa: E402

from . import consoles, layout, options, process, validate  # noqa: E402

NAME_MAX = 8      # longer names are console-untested (FORMAT.md); the report keeps the long name

# Abbreviations, matched on whole words, case-insensitive. LONG words go first; SHORT ones only when squeezing
# out the spaces was not enough.
ABBREV_LONG = [('acoustic', 'Ac'), ('electric', 'El'), ('guitar', 'Gtr'), ('vocals', 'Vox'), ('vocal', 'Vox'),
               ('voice', 'Vox'), ('keyboards', 'Keys'), ('keyboard', 'Keys'), ('overheads', 'OH'), ('overhead', 'OH'),
               ('bottom', 'Bot'), ('left', 'L'), ('right', 'R'), ('tracks', 'Trx'), ('track', 'Trk'),
               ('talkback', 'TB'), ('audience', 'Aud'), ('piano', 'Pno'), ('synth', 'Syn'), ('organ', 'Org'),
               ('trumpet', 'Tpt'), ('trombone', 'Tbn'), ('saxophone', 'Sax'), ('percussion', 'Perc'),
               ('reverb', 'Verb'), ('return', 'Rtn'), ('delay', 'Dly'), ('hi-hat', 'HH'), ('hihat', 'HH'),
               ('background', 'BG'), ('backing', 'BG'), ('playback', 'PB'), ('music', 'Mus'), ('stereo', 'St'),
               ('microphone', 'Mic'), ('measurement', 'Meas'), ('wireless', 'RF'), ('ambient', 'Amb'),
               ('walk-in', 'WalkIn'), ('guest', 'Gst'), ('spare', 'Spr')]
ABBREV_SHORT = [('snare', 'Snr'), ('floor', 'Flr'), ('lead', 'Ld'), ('bass', 'Bs'), ('kick', 'Kik')]


def clean_text(s, limit=None):
    """Plain printable ASCII: accents folded, control characters dropped, runs of spaces collapsed."""
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^\x20-\x7e]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:limit] if limit else s


def _abbrev(s, table):
    for word, ab in table:
        s = re.sub(r'(?i)\b%s\b' % re.escape(word), ab, s)
    return s


def _squeeze(s):
    """Drop spaces from the left until the name fits."""
    while len(s) > NAME_MAX and ' ' in s:
        s = s.replace(' ', '', 1)
    return s


def _devowel(s):
    """Drop lower-case vowels from the right, never a word's first letter."""
    chars = list(s)
    for i in range(len(chars) - 1, 0, -1):
        if len(chars) <= NAME_MAX:
            break
        if chars[i] in 'aeiou' and chars[i - 1].isalnum():
            del chars[i]
    return ''.join(chars)


def short_name(name, n):
    """A console name of at most 8 characters. -> (short, changed?). The first candidate that fits wins:
    long words abbreviated, then spaces squeezed, then short words abbreviated, then vowels dropped, then cut."""
    s = clean_text(name)
    if not s:
        return 'Ch %d' % n, True
    if len(s) <= NAME_MAX:
        return s, False
    a = _abbrev(s, ABBREV_LONG)
    b = _abbrev(a, ABBREV_SHORT)
    for cand in (a, _squeeze(a), b, _squeeze(b), _devowel(_squeeze(b))):
        if len(cand) <= NAME_MAX:
            return cand, True
    return _devowel(_squeeze(b))[:NAME_MAX].rstrip() or 'Ch %d' % n, True


def _plan(req):
    """Validate and normalise the request. -> (console, version, baseline path, title, plan, warnings, opts).
    opts is {} without option blocks; with them options.prepare() may append FX return channels to the plan and
    restructure the default (opts['data'])."""
    if not isinstance(req, dict):
        raise ValueError('The request is empty.')
    console = consoles.get(req.get('console'))
    if not console['versions']:
        raise ValueError('No baseline session exists yet for the %s.' % console['name'])
    try:
        version = int(str(req.get('version') or next(iter(console['versions']))).lstrip('Vv'))
    except ValueError:
        raise ValueError('Pick a firmware version.')
    base = console['versions'].get(version)
    if not base or not os.path.exists(base):
        raise ValueError('V%d is not available for the %s.' % (version, console['name']))
    chans = req.get('channels')
    if not isinstance(chans, list) or not chans:
        raise ValueError('Add at least one channel.')
    warnings = []
    cap = min(console['max_inputs'], layout.MAX_INPUT_IDS)
    if len(chans) > cap:
        if req.get('overflow') != 'truncate':
            raise ValueError('The %s holds %d inputs. This list has %d.' % (console['name'], cap, len(chans)))
        warnings.append('The %s holds %d inputs: channels %d-%d were left out.' % (
            console['name'], cap, cap + 1, len(chans)))
        chans = chans[:cap]
    cats = process.templates()['categories']
    plan = []
    for n, ch in enumerate(chans, 1):
        if not isinstance(ch, dict):
            ch = {'name': str(ch)}
        full = clean_text(ch.get('full_name') or ch.get('name'), 80)
        short, changed = short_name(ch.get('name') or full, n)
        typed = re.sub(r'\s+', ' ', str(ch.get('name') or '')).strip()
        if changed and clean_text(ch.get('name')):
            warnings.append('Ch %d: %r is shortened to %r (8 characters on the console).' % (n, full, short))
        elif typed and typed != short:
            warnings.append('Ch %d: %r is written as %r (the console gets plain letters).' % (n, typed, short))
        cat = ch.get('category') or 'other'
        if cat != 'other' and cat not in cats:
            warnings.append('Ch %d %s: unknown category %r, no processing written.' % (n, short, cat))
            cat = 'other'
        plan.append({'n': n, 'idx': n, 'name': short, 'full_name': full or short, 'stereo': bool(ch.get('stereo')),
                     'category': cat, 'phantom': ch.get('phantom') if isinstance(ch.get('phantom'), bool) else None,
                     'source': clean_text(ch.get('source'), 64) or None,
                     'notes': clean_text(ch.get('notes'), 200) or None})
    opts = options.prepare(req, console, open(base, 'rb').read(), plan, warnings) if options.present(req) else {}
    # Engine channels: a stereo channel takes 2, and the inputs must fit the room the default session leaves them
    # (layout.engine_room: below the aux/matrix buses on SD models, below TB In on Quantum). A new bus layout moves
    # that room on SD models, so it is read from the restructured default then.
    room = console.get('engine_room')
    if opts.get('data') is not None:
        r = layout.engine_room(opts['data'])
        room = r['room'] if r else None
    elif room is None:
        r = layout.engine_room(open(base, 'rb').read())
        room = r['room'] if r else None
    need = sum(2 if p['stereo'] else 1 for p in plan)
    if room is not None and need > room:
        if req.get('overflow') != 'truncate' or opts:
            nst, extra = sum(p['stereo'] for p in plan), need - room
            chs = lambda k, w='channel': '%d %s%s' % (k, w, '' if k == 1 else 's')   # noqa: E731
            if nst >= extra:
                fix = 'Make %s mono, or remove %s.' % (chs(extra, 'stereo channel'), chs((extra + 1) // 2, 'stereo channel'))
            elif nst:
                fix = 'Remove channels or make stereo ones mono until it needs %d or fewer.' % room
            else:
                fix = 'Remove %s.' % chs(extra)
            nret = sum(1 for p in plan if p.get('fx_return') and p['n'] > len(chans))
            what = chs(len(plan) - nret) + (' plus %d FX return%s' % (nret, '' if nret == 1 else 's') if nret else '')
            raise ValueError('The %s has room for %d input paths%s, and a stereo channel takes 2. This plan needs %d '
                             '(%s%s). %s' % (console['name'], room,
                                             '' if console['family'] in layout.QUANTUM_FAMILIES else ' next to its buses',
                                             need, what, ', %d stereo' % nst if nst else '', fix))
        while plan and sum(2 if p['stereo'] else 1 for p in plan) > room:
            plan.pop()
        warnings.append('The %s has room for %d input paths (a stereo channel takes 2): channels %d-%d were left '
                        'out.' % (console['name'], room, len(plan) + 1, len(chans)))
    title = clean_text(req.get('title'), 60) or 'Session'
    return console, version, base, title, plan, warnings, opts


def _check(name, ok, detail):
    return {'name': name, 'ok': bool(ok), 'detail': detail}


def _close(a, b):
    """Equal as the float32 the file stores."""
    return abs(a - b) <= 1e-6 * max(1.0, abs(b))


def build_session(req, out_path):
    t0 = time.perf_counter()
    console, version, base, title, plan, warnings, opts = _plan(req)
    processing = req.get('processing') if req.get('processing') in ('templates', 'none') else 'templates'
    role = 'mon' if req.get('role') == 'mon' else 'foh'

    # 1-2. layout: names, widths, order, count, notes
    data = opts['data'] if opts.get('data') is not None else open(base, 'rb').read()
    spec = [{'name': p['name'], 'width': 2 if p['stereo'] else 1} for p in plan]
    ses = Session(layout.relayout(data, spec, session_notes=title))
    options.apply_fx(ses, opts)
    # 3. processing (internal index = surface number: relayout keeps 1..N in order)
    rows, mustard_used = process.apply(ses, plan, console, processing, role)
    options.apply_rest(ses, opts, plan, warnings)
    out = bytes(ses.d)

    # 4. structure, write, read back
    errs, info = validate.check(out)
    if errs:
        raise RuntimeError('generated session failed its structure check: ' + '; '.join(errs[:3]))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + '.part'
    with open(tmp, 'wb') as f:
        f.write(out)
    os.replace(tmp, out_path)
    rs = Session(open(out_path, 'rb').read())

    # check names and details are shown to engineers as-is (web page Checks tab, report): plain words, 1-based
    checks = [_check('File structure', not errs, 'The channel list, channel data and bank layout agree (%d inputs, '
                     '%d banks).' % (info['inputs'], info['banks']))]
    em = layout.engine_map(layout.Container(out).sec(201)[1])
    if em:
        ins = layout._engines(em[layout.T_INPUT])
        tb = [e for e, _ in em.get(layout.T_TB, [])]
        eng_errs = validate.engine_pool_errors(rs.model, em, ins)
        bus = sorted(e for e in layout._engines(sum((em.get(t, []) for t in layout.BUS_TYPES), [])) if e > max(ins))
        npaths = len(ins)
        checks.append(_check('Processing paths', not eng_errs, ' '.join(
            e[:1].upper() + e[1:] + '.' for e in eng_errs) or
            'The inputs use %d processing path%s (a stereo channel takes 2), clear of the talkback%s.' % (
                npaths, '' if npaths == 1 else 's',
                ' and the buses' if bus and rs.model not in layout.QUANTUM_FAMILIES else '')))
    base_s = open(base, 'rb').read(0x24)
    same_head = rs.model == base_s[11:15].decode('latin1').strip() and rs.version == version
    checks.append(_check('Console and software', same_head and rs.header_counts()['inputs'] == len(plan),
                         '%s file, V%d, %d inputs in the header.' % (console['name'], rs.version,
                                                                    rs.header_counts()['inputs'])))
    by_n = {n: rs.display.get(n) for n in range(1, len(plan) + 1)}
    parsed = len(rs.inputs) == len(plan) and all(by_n.values())
    nfound = sum(1 for v in by_n.values() if v)
    checks.append(_check('Read back', parsed, ('All %d channels found when the file is read again.' % len(plan))
                         if nfound == len(plan) else '%d of %d channels found when the file is read again.'
                         % (nfound, len(plan))))
    bad_names = [p['n'] for p in plan if not by_n[p['n']] or rs.by_index[by_n[p['n']]].name != p['name']]
    checks.append(_check('Names', not bad_names, 'All %d names read back.' % len(plan) if not bad_names else
                         'Wrong name on channel %s.' % ', '.join(map(str, bad_names[:8]))))
    bad_st = [p['n'] for p in plan if rs.width.get(p['n']) != (2 if p['stereo'] else 1)]
    nst = sum(1 for p in plan if p['stereo'])
    checks.append(_check('Stereo', not bad_st, '%d stereo, %d mono.' % (nst, len(plan) - nst) if not bad_st else
                         'Wrong width on channel %s.' % ', '.join(map(str, bad_st[:8]))))
    nvals, bad_vals = 0, []
    for p in plan:
        idx = by_n[p['n']]
        for (m, prm, b), v in rows[p['n']]['written'].items():
            nvals += 1
            if idx is None or not _close(rs.get(idx, m, prm, b), v):
                bad_vals.append(p['n'])
                break
    checks.append(_check('Processing', not bad_vals, '%d settings written and read back.' % nvals if not bad_vals
                         else 'Settings differ on channel %s.' % ', '.join(map(str, bad_vals[:8]))))
    if console['mustard']:
        on = [p for p in plan if rows[p['n']]['mustard'] == 'on']
        cap = console['mustard_cap']
        rb_used = sum(2 if rs.width.get(p['n']) == 2 else 1 for p in plan
                      if rs.has_module(0x1d, by_n[p['n']]) and rs.get(by_n[p['n']], 0x1d, 0x02, 0) == 1.0)
        checks.append(_check('Mustard', rb_used == mustard_used and (cap is None or rb_used <= cap),
                             '%d channels, %d of %d instances (a stereo channel uses 2).%s' % (
                                 len(on), rb_used, cap, '' if console['mustard_cap_verified'] else
                                 ' The limit is a safe guess for this console.')))
    checks += options.checks(rs, opts, out)
    checks.append(_check('Session notes', layout.notes(out) == title, 'The session name is saved in the session '
                         'notes.'))

    readback = {'console': console['key'], 'console_name': console['name'], 'version': version,
                'inputs': len(rs.inputs), 'stereo': sum(1 for w in rs.width.values() if w == 2),
                'mustard_used': mustard_used, 'mustard_cap': console['mustard_cap'], 'channels': []}
    for p in plan:
        idx = by_n[p['n']]
        rb = process.readback_channel(rs, idx) if idx else {}
        readback['channels'].append(dict({'n': p['n'], 'name': rs.by_index[idx].name if idx else None,
                                          'full_name': p['full_name'], 'stereo': rs.width.get(p['n']) == 2,
                                          'category': p['category'], 'template': rows[p['n']]['source']}, **rb))
        for note in rows[p['n']]['notes']:
            if 'no Mustard instance left' in note:
                warnings.append('Ch %d %s: %s.' % (p['n'], p['name'], note))
    _readback_more(readback, out, plan, opts)
    over = sum(1 for p in plan if rows[p['n']]['mustard'] == 'over')
    if over and console['mustard']:
        warnings.insert(0, '%d channels wanted Mustard past the %d-instance cap; they got the SD compressor.'
                        % (over, console['mustard_cap']))
    ms = (time.perf_counter() - t0) * 1000
    report = report_md(console, version, title, plan, rows, readback, checks, warnings, processing, role, ms, opts)
    return {'path': out_path, 'report_md': report, 'readback': readback, 'checks': checks, 'warnings': warnings,
            'ms': round(ms, 1)}


def _md(s):
    return str(s).replace('|', '/')


def _readback_more(readback, out, plan, opts):
    """Buses, FX, I/O and per-channel patch / sends / groups from the Session Checker's reader (inspect.py), so the
    page shows a made session the way it shows a checked one. Adds 'options' (what the option blocks wrote)."""
    from . import inspect as _inspect
    ro = _inspect.inspect(out)
    if not ro.get('ok'):
        return
    for k in ('auxes', 'groups', 'fx', 'devices'):
        readback[k] = ro.get(k)
    by_n = {c['n']: c for c in ro.get('channels') or []}
    for ch in readback['channels']:
        c = by_n.get(ch['n'], {})
        for k in ('patch', 'sends', 'groups'):
            if c.get(k) is not None:
                ch[k] = c[k]
        if any(p['n'] == ch['n'] and p.get('fx_return') for p in plan):
            ch['fx_return'] = True
    if opts:
        done = opts.get('done') or {}
        readback['options'] = {
            'layout': opts.get('layout'),
            'fx': [{'unit': u.get('unit'), 'name': u['name'], 'kind': u['key'], 'aux': u['feed_aux'],
                    'return_ch': u.get('return_ch')} for u in opts.get('fx', [])],
            'mixes': [{'aux': m['aux'], 'name': m['name'], 'stereo': m['stereo'], 'own': m['own'],
                       'click': m.get('click'), 'outputs': done.get('outputs', {}).get(m['aux'])}
                      for m in opts.get('mixes_plan') or []],
            'fx_sends': len(opts.get('fx_sends') or []),
            'patch': {'mode': opts['patch']['mode'], 'channels': len(done.get('patch') or []),
                      'phantom': sum(1 for e in done.get('patch') or [] if e['phantom']),
                      'first': (done.get('patch') or [{}])[0].get('main'),
                      'devices': list(dict.fromkeys(e['device'] for e in done.get('patch') or []))}
            if opts.get('patch') else None,
        }


def report_md(console, version, title, plan, rows, readback, checks, warnings, processing, role, ms, opts=None):
    nst = readback['stereo']
    lines = ['# %s' % _md(title), '',
             '%s, V%d. %d inputs (%d stereo). Built %s in %.0f ms.' % (
                 console['name'], version, len(plan), nst, datetime.date.today().isoformat(), ms), '']
    if processing == 'templates':
        lines += ['Processing is a starting point per instrument: the median settings from 39 real touring sessions'
                  '%s. Thresholds assume a normal gain structure. Check every channel at line check.' % (
                      ', monitor versions where they exist' if role == 'mon' else ''), '']
        if console['mustard']:
            lines += ['Mustard comp on %d channels (%d of %d instances). Those strips open on the M view.' % (
                sum(1 for p in plan if rows[p['n']]['mustard'] == 'on'), readback['mustard_used'],
                console['mustard_cap']), '']
    else:
        lines += ['Names and layout only. No processing written.', '']
    lines += ['| Ch | Name | From your list | St | Instrument | Written |', '| --- | --- | --- | --- | --- | --- |']
    for p, rb in zip(plan, readback['channels']):
        notes = rows[p['n']]['notes']
        summ = process.summary(rb) if rb.get('eq') is not None else ''
        lines.append('| %d | %s | %s | %s | %s | %s |' % (
            p['n'], _md(rb.get('name') or p['name']), _md(p['full_name'] if p['full_name'] != p['name'] else ''),
            'St' if p['stereo'] else '', _md(process.category_label(p['category'])),
            _md(summ + ('. ' + '; '.join(notes) if notes else ''))))
    ph = [p for p in plan if p['phantom']]
    lines += ['', '## Set these on the console', '']
    if opts and opts.get('patch'):
        lines.append('- Check the input patch, preamp gain and 48V at line check. They are starting points.')
    else:
        lines.append('- Preamp gain, 48V and the input patch. The file leaves every channel unpatched.')
    if opts and (opts.get('fx') or opts.get('mixes_plan')):
        lines.append('- Group sends, matrix and the main outputs stay at the console defaults. Set the FX return '
                     'and input faders: they start off.')
    else:
        lines.append('- Aux and group sends, FX and outputs. They stay at the console defaults.')
    if ph and not (opts and opts.get('patch')):
        lines.append('- 48V on: ' + ', '.join('%d %s' % (p['n'], _md(p['name'])) for p in ph) + '.')
    srcs = [p for p in plan if p['source']]
    if srcs:
        lines.append('- Sources from your list: ' + ', '.join('%d %s (%s)' % (p['n'], _md(p['name']), _md(p['source']))
                                                            for p in srcs[:64]) + '.')
    lines += [_md(x) for x in options.report_lines(opts, plan)]
    if warnings:
        lines += ['', '## Warnings', ''] + ['- ' + _md(w) for w in warnings]
    lines += ['', '## Checks', ''] + ['- %s %s: %s' % ('OK' if c['ok'] else 'FAILED', c['name'], _md(c['detail']))
                                      for c in checks]
    if not console['tested'].get(version):
        lines += ['', 'This console and version have not been load-tested in the DiGiCo editor yet. '
                      'Open the file in the offline editor before the show.']
    return '\n'.join(lines) + '\n'


def main(argv):
    if len(argv) != 3:
        print('usage: python3 -m sessionmaker.build <req.json> <out.ses>', file=sys.stderr)
        return 2
    req = json.load(open(argv[1]))
    try:
        res = build_session(req, argv[2])
    except ValueError as e:
        print('error: %s' % e, file=sys.stderr)
        return 1
    stem = os.path.splitext(argv[2])[0]
    with open(stem + '.md', 'w') as f:
        f.write(res['report_md'])
    with open(stem + '.json', 'w') as f:
        json.dump({k: res[k] for k in ('readback', 'checks', 'warnings', 'ms')}, f, indent=1)
    failed = [c for c in res['checks'] if not c['ok']]
    print('wrote %s: %s V%s, %d inputs (%d stereo), %d checks failed, %d warnings, %.0f ms' % (
        argv[2], res['readback']['console'], res['readback']['version'], res['readback']['inputs'],
        res['readback']['stereo'], len(failed), len(res['warnings']), res['ms']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
