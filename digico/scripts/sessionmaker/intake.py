"""intake.py - an input list and/or a show description -> the channel plan build.py writes.

Entry points (all return plain dicts, never raise on bad user input):

  parse_input_list(filename, data, text) -> {'channels', 'warnings', 'notes', 'skipped', 'meta'}
      Any list: CSV/TSV/XLSX/XLS/DOCX/PDF/HTML bytes, or pasted text. L/R pairs become one stereo
      channel, names are cut to 8 characters, bare spare / blank rows are dropped (their list numbers
      go in 'notes' and 'skipped'). Categories here come from the rules only.
  classify(channels) -> channels with 'category', 'confidence', 'via' ('rule'|'jev'|'fallback')
      Rules first (taxonomy.rule_category). Channels the rules are not sure of go to the optional
      classifier hook (CLASSIFIER below, not included) when one is set. A classifier answer with
      p >= 0.6 is accepted; below that the rules' weak guess (or 'other') stays, and the classifier's
      top pick is attached as 'suggestion'.
  describe_to_channels(description) -> {'channels', 'answers'}
      Description only: 18 closed-set questions (QUESTIONS) answered by explicit numbers in the text
      (regex), then the optional classifier, then the show style's defaults, then a list in house order.
  plan_from(description, filename, data, text) -> combined plan (channels, warnings, options).

The classifier is optional everywhere and not part of this repo: with none set (the default), or SM_JEV=0,
every step runs on the rules.

Channel dict (what build.py reads, plus fields for the UI and the report):
  {'name' <= 8 chars, 'full_name', 'stereo', 'category' (50 template ids or 'other'),
   'confidence', 'via', 'phantom' (True/False/None = list did not say), 'source' (mic/DI text),
   'source_type', 'notes', 'list_ch' (list channel numbers), 'section', 'who', 'stand', 'flags'}
"""
import json
import logging
import os
import re
import threading
import time
import unicodedata

from sessionmaker import listparse as L
from sessionmaker import taxonomy as T

log = logging.getLogger('sessionmaker.intake')

MAX_NAME = 8
JEV_TIMEOUT = float(os.environ.get('SM_JEV_TIMEOUT', '3.0'))   # seconds, wall clock, whole classifier step
JEV_ACCEPT = 0.6            # averaged probability needed to take the classifier's channel category
JEV_Q_ACCEPT = 0.55         # same for a questionnaire answer (a wrong one is visible and cheap)

# per-process counters
STATS = {'calls': 0, 'errors': 0, 'timeouts': 0, 'last_ms': None}
_lock = threading.Lock()


# --------------------------------------------------------------------------------------------
# optional classifier hook ("the classifier" in the names below)
# --------------------------------------------------------------------------------------------
# The original tool asked an external closed-set classifier about the channels the rules were not sure of.
# That service is not part of this repo. Without it everything runs on the rules (taxonomy.rule_category) and
# the description regexes, which is the documented fallback. To plug in your own classifier, set CLASSIFIER to
# a callable (state, questions, timeout) -> ({qid: {'choice', 'p', 'orders', 'probs'}}, info), where
# questions = {qid: (instructions, {option: description})} and p is the probability of 'choice' (0..1).
# 'orders' = 2 tells the callers the answer is stable when the option order is reversed.

CLASSIFIER = None


def jev_enabled():
    return CLASSIFIER is not None and os.environ.get('SM_JEV', '1') != '0'


def jev_choices(state, questions, timeout=None):
    """Ask the optional classifier closed-set questions. Returns ({qid: {'choice', 'p', 'orders', 'probs'}}, info).
    Never raises: no classifier, an error or a timeout all return no answers."""
    info = {'calls': 0, 'ok': 0, 'ms': 0.0, 'error': None}
    if not questions or not jev_enabled():
        info['error'] = 'disabled' if questions else None
        return {}, info
    t0 = time.time()
    try:
        out, extra = CLASSIFIER(state, questions, JEV_TIMEOUT if timeout is None else timeout)
        info.update(extra or {})
        info['ok'] = info.get('ok') or 1
    except Exception as e:      # noqa: BLE001 - any failure means "no answer"
        with _lock:
            STATS['errors'] += 1
        info['error'] = type(e).__name__
        out = {}
    info['ms'] = round((time.time() - t0) * 1000, 1)
    with _lock:
        STATS['calls'] += info.get('calls', 0)
        STATS['last_ms'] = info['ms']
    return out or {}, info


# --------------------------------------------------------------------------------------------
# names
# --------------------------------------------------------------------------------------------

# Letters NFKD does not split into a base letter + accent.
TRANSLIT = str.maketrans({'Ł': 'L', 'ł': 'l', 'Ø': 'O', 'ø': 'o', 'ß': 'ss', 'Æ': 'AE', 'æ': 'ae', 'Œ': 'OE',
                          'œ': 'oe', 'Đ': 'D', 'đ': 'd', 'Þ': 'Th', 'þ': 'th', 'ı': 'i', 'Ð': 'D', 'ð': 'd'})


def console_name(s, max_len=MAX_NAME):
    """A name the writer accepts: printable ASCII, <= 8 characters. Accents fold to the plain letter
    ("Snäre" -> "Snare") and emoji drop out, the same as build.py does, so the page shows what the
    console will show (Latin-1 names are untested on a console)."""
    s = unicodedata.normalize('NFKC', s or '').translate(TRANSLIT)
    s = s.replace('\u2013', '-').replace('\u2014', '-').replace('\u2019', "'").replace('\u2018', "'")
    out = []
    for ch in s:
        if ord(ch) < 32 or ord(ch) == 127:
            continue
        if ord(ch) > 126:
            out.append(unicodedata.normalize('NFKD', ch).encode('ascii', 'ignore').decode('ascii'))
            continue
        out.append(ch)
    return re.sub(r'\s+', ' ', ''.join(out)).strip()[:max_len].rstrip()


def _uniquify(chans):
    names = L.uniquify([c['name'] for c in chans])
    for c, n in zip(chans, names):
        c['name'] = n


# --------------------------------------------------------------------------------------------
# input lists
# --------------------------------------------------------------------------------------------

def _ranges(nums):
    """[17, 18, 19, 23] -> '17-19, 23'."""
    nums = sorted(set(n for n in nums if n is not None))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else '%d-%d' % (nums[i], nums[j]))
        i = j + 1
    return ', '.join(out)


def _from_parser(c, k):
    """A listparse channel -> an intake channel (rule category filled in later by classify)."""
    src = c.get('source') or {}
    return {
        'n': k,
        'name': console_name(c['name']),
        'full_name': c.get('full_name') or c['name'],
        'stereo': bool(c.get('stereo')),
        'category': None,
        'confidence': None,
        'via': None,
        'phantom': c.get('phantom'),
        'source': src.get('mic'),
        'source_type': src.get('type'),
        'patch': src.get('patch'),
        'list_ch': [x for x in (c.get('list_channels') or []) if x is not None],
        'section': c.get('section'),
        'who': c.get('who'),
        'stand': c.get('stand'),
        'notes': c.get('notes'),
        'flags': list(c.get('flags') or []),
        'raw': c.get('raw'),
    }


# Console names for inputs pulled out of a sentence ("I'll need a bass DI and a vocal mic").
DEFAULT_NAMES = {
    'kick_in': 'Kick', 'kick_out': 'Kick Out', 'kick_sub': 'Sub Kick', 'snare_top': 'Snare', 'snare_bottom': 'Snr Bot',
    'hihat': 'Hi Hat', 'rack_tom': 'Rack', 'floor_tom': 'Floor', 'overheads': 'OH', 'ride': 'Ride',
    'drum_trigger': 'Trigger', 'sample_pad': 'Pad', 'hand_perc': 'Perc', 'bass_di': 'Bass DI', 'bass_amp': 'Bass Amp',
    'synth_bass': 'Syn Bass', 'electric_guitar': 'Gtr', 'acoustic_guitar': 'AG', 'folk_strings': 'Mando',
    'strings': 'Strings', 'horns': 'Horn', 'keys': 'Keys', 'piano': 'Piano', 'organ': 'Organ', 'synth': 'Synth',
    'lead_vocal': 'Lead Vox', 'vocal_generic': 'Vox', 'choir': 'Choir', 'speech_mic': 'Speech',
    'tracks_music': 'Tracks', 'tracks_drums_perc': 'Trx Drum', 'tracks_bass': 'Trx Bass', 'tracks_vocals': 'Trx Vox',
    'click': 'Click', 'cues_guide': 'Cues', 'timecode': 'LTC', 'media_playback': 'Media', 'audience': 'Aud',
    'talkback': 'TB', 'comms_radio': 'Comms', 'test_signal': 'Pink', 'measurement_ref': 'Ref',
}
SPLIT_RX = re.compile(r'\s*(?:,|;|\+|&|\band\b|\bplus\b|\bwith\b)\s*', re.I)
PROSE_FILLER = re.compile(r"(?i)^(?:(?:i'?ll|we'?ll|i|we|you)\s+(?:need|want|have|bring|use|will need|would like)|"
                          r"(?:and|also|plus|maybe|potentially|possibly|probably|then|a|an|the|our|my|his|her)\b)\s*")


def _clean_piece(t):
    t = t.strip(' .:-')
    for _ in range(4):
        t2 = PROSE_FILLER.sub('', t).strip(' .:-')
        if t2 == t:
            break
        t = t2
    return t


def split_rows(rows):
    """Rows that hold more than one input -> one row per input.

    - a sentence ("I'll need a bass DI, vocal mic and potentially a DI for acoustic"): split on commas
      and "and"; keep the pieces the rules place with confidence >= 0.8 under a house name;
    - a name joined with + or & ("Laptop tracks stereo + click"): split when both sides are sure and
      different sources ("Kick In + Out" stays one row).
    Returns (rows, set of raw lines that were split)."""
    out, split_raw = [], set()
    for r in rows:
        if r.get('_prose') or r.get('_described'):
            text = L.BULLET.sub('', r.get('raw') or r['name'])
            text = re.sub(r'\([^)]*\)', ' ', text)
            m = re.match(r'^\s*([A-Z][a-z]+)\s*[-:]\s+(.+)$', text)      # "Sam - lead vocal ..." -> who = Sam
            who = m.group(1) if m and L.is_person(m.group(1)) else ''
            body = m.group(2) if who else text
            body = re.sub(r'(?i)^\s*(?:di|di line|line|mic|xlr|input)\s*:\s*', '', body)
            pieces = []
            for part in SPLIT_RX.split(body):
                part = _clean_piece(part)
                if not part:
                    continue
                cat, p, _ = T.rule_category(part, '', r.get('section'))
                if p >= 0.8 and cat != 'other':
                    pieces.append((part, cat))
            if pieces:
                for part, cat in pieces:
                    nr = dict(r, name=part, mic='', short=DEFAULT_NAMES.get(cat), who=who or r.get('who', ''))
                    nr.pop('_prose', None)
                    nr.pop('_described', None)
                    if re.search(r'(?i)\bstereo\b', part):
                        nr['name'] = re.sub(r'(?i)\s*\bstereo\b', '', part) + ' stereo'
                        nr.pop('short', None)
                    out.append(nr)
                split_raw.add(r.get('raw'))
                continue
        if re.search(r'\s(?:\+|&)\s|\s\+', r['name']) and not r.get('_prose'):
            parts = [p.strip() for p in re.split(r'\s*(?:\+|&)\s*', r['name']) if p.strip()]
            cats = [T.rule_category(p, '', r.get('section')) for p in parts]
            if len(parts) >= 2 and all(c[1] >= 0.8 and c[0] != 'other' for c in cats) and len({c[0] for c in cats}) == len(cats):
                for p_ in parts:
                    out.append(dict(r, name=p_))
                split_raw.add(r.get('raw'))
                continue
        out.append(r)
    return out, split_raw


# "add a talkback for the MD, an audience pair", "plus a vocal mic for the bassist", "extra AG DI"
ADD_VERB = re.compile(r"(?i)\b(?:also add|add in|add|adding|throw in|include|plus(?= (?:an?|one|two|three|\d+|a pair of)\b)|"
                      r"an? extra|another|(?:we|i)(?:'ll| will)? (?:also )?need)\b")
FOR_WHO = re.compile(r"(?i)\s+(?:for|from|on|by)\s+(?:the\s+|our\s+|my\s+)?([\w'’ ]{1,24})$")


def additions_from(desc):
    """Channels a description asks to add on top of an uploaded list ("Same list but add a talkback for the MD, an
    audience pair, and the bass player sings BGVs so add a vocal mic for him").

    Text after an add-word, split at commas and "and", one input per piece. A piece counts only when the rules
    are sure of it and it is not a clause ("the bass player sings BGVs so" is skipped). "pair" / "stereo" / "L/R"
    makes it stereo, a leading count repeats it ("add 2 vocal mics"). -> intake channels, in the order written."""
    out = []
    for sent in re.split(r'(?<=[.!?;])\s+|\n+', desc or ''):
        ms = list(ADD_VERB.finditer(sent))
        for k, m in enumerate(ms):
            seg = sent[m.end():ms[k + 1].start() if k + 1 < len(ms) else len(sent)]
            for piece in re.split(r'\s*,\s*|\s+and\s+|\s+plus\s+|\s+so\s*$', seg):
                piece = _clean_piece(piece.strip(' .;!?'))
                if not piece or L.PROSE_RX.search(re.sub(r'(?i)\b(him|her|them)\b', '', piece)):
                    continue
                who = FOR_WHO.search(piece)
                core = piece[:who.start()].strip() if who else piece
                n = 1
                cm = re.match(r'(?i)^(\d{1,2}|one|two|three|four|five|six)\s+(.+)$', core)
                if cm:
                    n, core = min(8, _n(cm.group(1)) or 1), cm.group(2)
                stereo = bool(re.search(r'(?i)\b(pair|stereo|l ?/ ?r)\b', core))
                cat, p, _ = T.rule_category(re.sub(r'(?i)\b(pair|stereo|mics?)\b', ' ', core).strip() or core)
                if cat == 'other' or p < 0.8:
                    continue
                for i in range(n):
                    nm = DEFAULT_NAMES.get(cat) or console_name(core)
                    ch = _ch(nm if n == 1 else '%s %d' % (nm, i + 1), cat, stereo=stereo, via='rule',
                             notes='added from the description')
                    ch['full_name'] = piece
                    ch['confidence'] = round(p, 2)
                    ch['flags'] = ['from_description']
                    out.append(ch)
    return out


def channels_from_rows(rows, artist=None, stereo=True):
    """Rows (listparse) -> intake channels, one per parser channel, in list order. Bare spare and
    blank rows are kept here with flag 'skip' (the benchmark aligns on them); parse_input_list drops them."""
    rows, split_raw = split_rows(rows)
    chans, _ = L.build_channels(rows, stereo, artist, initials=True)
    out = []
    for k, c in enumerate(chans, start=1):
        ch = _from_parser(c, k)
        if T.is_bare_spare(ch['full_name']) or (not ch['full_name'].strip()):
            ch['flags'].append('skip')
        if c.get('raw') and c['raw'][0] in split_raw:
            ch['flags'].append('from_sentence')
        out.append(ch)
    return out


def guess_artist(filename=None, description=None):
    """The act's name from the file name ("Sam Rivers 2026 IP List.xlsx" -> "Sam Rivers")."""
    if filename:
        stem = os.path.splitext(os.path.basename(filename))[0]
        stem = re.sub(r'(?i)\b(input|inputs|ip|io|i/o|list|lists|channel|channels|rider|tech|audio|plan|rev\w*|v\d+|final|'
                      r'copy|draft|stage|plot|foh|mon|monitors?|sheet|tour|show|live|\d{2,4}|\d+[-/.]\d+([-/.]\d+)?)\b',
                      ' ', stem.replace('_', ' '))
        stem = re.sub(r'[|()\[\]{}]+', ' ', stem)
        stem = re.sub(r'\s+', ' ', stem).strip(' -.,')
        if 2 <= len(stem) <= 40:
            return stem
    return None


# Rows that are not inputs: a time or date ("9:30 AM CT", "1:30 - 3:00 PM", "Thu 9/17"), which is what a run
# sheet or schedule PDF turns into, and a header line that came through as a row ("Ch,Name,Mic" in a CSV with
# no data under it).
TZ = r'(?:ct|mt|et|pt|cst|cdt|mst|mdt|est|edt|pst|pdt|utc|gmt|bst|cet|local)'
TIME_ROW = re.compile(r'(?i)^[\W_]*(?:(?:mon|tue|wed|thu|fri|sat|sun)\w*\.?\s*)?'
                      r'(?:\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?\s*(?:-|to|until)?\s*)+'
                      r'(?:a\.?m\.?|p\.?m\.?)?\s*' + TZ + r'?[\W_]*$')
DATE_ROW = re.compile(r'(?i)^[\W_]*(?:(?:mon|tue|wed|thu|fri|sat|sun)\w*\.?,?\s*)?'
                      r'(?:\d{1,4}[/.-]\d{1,2}(?:[/.-]\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+\d{1,2}'
                      r'(?:,?\s*\d{4})?)[\W_]*$')
HEADER_WORDS = {'ch', 'chan', 'channel', 'channels', '#', 'no', 'num', 'number', 'input', 'inputs', 'name', 'names',
                'source', 'sources', 'instrument', 'mic', 'mics', 'microphone', 'di', 'stand', 'stands', '48v', '+48',
                'phantom', 'notes', 'note', 'patch', 'sub', 'subsnake', 'snake', 'insert', 'comments', 'comment',
                'position', 'pos', 'label', 'description', 'type', 'ip', 'i/o', 'line', 'stage', 'box', 'socket'}


def not_an_input(name, first=False):
    """'time' / 'date' / 'header' when a parsed row is plainly not an input, else None."""
    n = (name or '').strip()
    if not n or not re.search(r'\d', n) and not first and not re.search(r'[,;|\t]', n):
        return None
    if re.search(r'\d', n) and TIME_ROW.match(n) and re.search(r'(?i)\d:\d\d|\d\s*[ap]\.?m\b', n):
        return 'time'
    if DATE_ROW.match(n):
        return 'date'
    toks = [t for t in re.split(r'[\s,;|\t]+', n.lower()) if t]
    if len(toks) >= 2 and all(t.strip('().:') in HEADER_WORDS for t in toks) and (first or re.search(r'[,;|\t]', n)):
        return 'header'
    return None


def parse_input_list(filename=None, data=None, text=None, artist=None):
    """Read an input list into channels (rules-only categories). Never raises on bad input: a file
    that cannot be read comes back with no channels and the reason in 'warnings'."""
    t0 = time.time()
    warnings, notes = [], []
    try:
        rows, meta = L.load_rows_from(filename, data, text)
    except ValueError as e:
        msg = str(e)
        if not (msg[:1].isupper() and msg.endswith('.')):        # a reader's internal note, not a sentence
            msg = "That file couldn't be read. Save it as CSV or XLSX, or paste the channel names."
        return {'channels': [], 'warnings': [msg], 'notes': [], 'skipped': [], 'meta': {'error': 'unreadable'}}
    except Exception as e:      # noqa: BLE001 - a broken file must not take the page down
        log.warning('input list reader failed: %s', type(e).__name__)
        return {'channels': [], 'warnings': ['That file could not be read. Try CSV, XLSX or pasted text.'],
                'notes': [], 'skipped': [], 'meta': {'error': type(e).__name__}}
    if not rows:
        msg = 'No input rows found.'
        if meta.get('error') == 'no input table found':
            msg += ' No sheet had a column called Input, Name or Source.'
        return {'channels': [], 'warnings': [msg + ' Paste the list as text, one input per line.'], 'notes': [],
                'skipped': [], 'meta': _meta_out(meta, t0)}
    artist = artist or guess_artist(filename)
    chans = channels_from_rows(rows, artist)
    junk = {}
    for k, c in enumerate(chans):
        why = 'skip' not in c['flags'] and not_an_input(c['full_name'], first=(k == 0))
        if why:
            junk[id(c)] = why
    skipped = [{'list_ch': c['list_ch'], 'text': c['full_name'], 'why': junk.get(id(c), 'spare')}
               for c in chans if 'skip' in c['flags'] or id(c) in junk]
    skipped += [{'list_ch': [s['ch']], 'text': '', 'why': 'blank'} for s in meta.get('skipped') or []]
    live = [c for c in chans if 'skip' not in c['flags'] and id(c) not in junk]
    if junk and len(junk) >= len(live):
        # mostly times, dates or a lone header line: a schedule, a run sheet or an empty template, not an input list
        only_header = all(w == 'header' for w in junk.values())
        msg = ('The list has a header row but no channels under it.' if only_header and not live else
               "That file doesn't look like an input list.")
        return {'channels': [], 'warnings': [msg + ' Upload the input list, or paste one channel per line.'],
                'notes': [], 'skipped': skipped, 'meta': _meta_out(meta, t0)}
    if junk:
        notes.append('%d line%s that look like times, dates or column headings %s left out.' % (
            len(junk), '' if len(junk) == 1 else 's', 'was' if len(junk) == 1 else 'were'))
    chans = live
    for k, c in enumerate(chans, start=1):
        c['n'] = k
        c['category'], c['confidence'], why = T.rule_category(c['full_name'], c['source'] or '', c['section'],
                                                               c['stereo'], artist)
        c['via'] = 'rule' if c['confidence'] >= JEV_ACCEPT else 'fallback'
    _uniquify(chans)
    nums = [n for s in skipped if s['why'] in ('spare', 'blank') for n in s['list_ch']]
    if nums:
        notes.append('List ch %s %s blank or spare, so %s.' % (
            _ranges(nums), 'is' if len(nums) == 1 else 'are',
            'it is not a channel' if len(nums) == 1 else 'they are not channels'))
    if meta.get('blocks'):
        notes.append('The list is in %d parts, read in order: %s.' % (len(meta['blocks']), '; '.join(meta['blocks'])))
    for u in meta.get('unused') or []:
        warnings.append('Not read: %s (%d rows). If it holds more inputs, add them to the table.' % (u['label'], u['rows']))
    for d in (meta.get('dropped') or [])[:3]:
        notes.append('Left out a note, not an input: "%s".' % d['text'])
    prose = [c for c in chans if ('prose_line' in c['flags'] or 'described_line' in c['flags'] or 'from_sentence' in c['flags'])
             and (c['confidence'] < 0.8 or 'from_sentence' in c['flags'])]
    if prose:
        warnings.append('%d input%s came from a sentence. Check: %s.' % (
            len(prose), '' if len(prose) == 1 else 's', ', '.join(c['name'] for c in prose[:6])))
    short = sum('name_shortened' in c['flags'] for c in chans)
    if short:
        notes.append('%d name%s cut to 8 characters (the full name stays in the report).' % (short, '' if short == 1 else 's'))
    opts = [c for c in chans if 'option' in c['flags']]
    if opts:
        notes.append('%d option row%s kept as channels: %s.' % (len(opts), '' if len(opts) == 1 else 's',
                                                               ', '.join(c['name'] for c in opts[:8])))
    st = sum(c['stereo'] for c in chans)
    if st:
        notes.append('%d L/R pair%s joined into stereo channels.' % (st, '' if st == 1 else 's'))
    return {'channels': chans, 'warnings': warnings, 'notes': notes, 'skipped': skipped, 'meta': _meta_out(meta, t0)}


def _meta_out(meta, t0):
    keep = ('source', 'sheet', 'header_row', 'columns', 'text_chars', 'error')
    m = {k: meta[k] for k in keep if k in meta}
    m['ms'] = round((time.time() - t0) * 1000, 1)
    return m


# --------------------------------------------------------------------------------------------
# classify
# --------------------------------------------------------------------------------------------

JEV_CLASSIFY_INSTR = ('A live-sound input list for a mixing console names input {k} "{name}"{extra}. '
                      'Inputs just before it: {before}. Inputs just after it: {after}. '
                      'What source feeds input {k}?')

BGV_WORDS = re.compile(r'(?i)\b(bgv|bgvs|bv|bvs|harm\w*|backing|background|bkg|choir|guest|gst|spare|spr|tb|talkback|'
                       r'trx|trax|tracks?|iem|ears|fx|dist)\b')


def _jev_classify_questions(chans, idx, description=None):
    names = [c['full_name'] or c['name'] for c in chans]
    qs = {}
    for i in idx:
        c = chans[i]
        extra = []
        if c.get('source'):
            extra.append('fed by "%s"' % c['source'][:40])
        if c.get('section'):
            extra.append('listed under "%s"' % str(c['section'])[:40])
        if c.get('stereo'):
            extra.append('stereo')
        ctx = c.get('context')                  # benchmark: neighbours from the real session
        bn = ctx['before'] if ctx else names[max(0, i - 2):i]
        an = ctx['after'] if ctx else names[i + 1:i + 3]
        before = ', '.join('"%s"' % n[:24] for n in bn) or 'none'
        after = ', '.join('"%s"' % n[:24] for n in an) or 'none'
        ins = JEV_CLASSIFY_INSTR.format(k=i + 1, name=(c['full_name'] or c['name'])[:40],
                                        extra=(' (' + '; '.join(extra) + ')') if extra else '', before=before, after=after)
        qs['c%d' % i] = (ins, T.JEV_OPTIONS)
    state = {'console': 'DiGiCo', 'inputs': [n[:24] for n in names]}
    if description:
        state['show'] = description[:600]
    return state, qs


def classify(channels, artist=None, description=None, use_jev=None):
    """Fill 'category', 'confidence', 'via' on copies of the channels. Rules first; the rest go to the classifier.
    use_jev=None follows SM_JEV; False forces rules only (benchmark)."""
    chans = [dict(c) for c in channels]
    t0 = time.time()
    left = []
    for i, c in enumerate(chans):
        c['flags'] = [f for f in (c.get('flags') or []) if f not in ('lead_guess',)]
        c.pop('suggestion', None)
        if c.get('category_locked'):            # set by the user in the UI: keep it
            c['via'] = c.get('via') or 'user'
            continue
        cat, p, why = T.rule_category(c.get('full_name') or c.get('name'), c.get('source') or '', c.get('section'),
                                      bool(c.get('stereo')), artist)
        c['category'], c['confidence'], c['via'] = cat, round(p, 2), 'rule'
        if p < JEV_ACCEPT:
            left.append(i)
    info = {'asked': len(left), 'accepted': 0, 'calls': 0, 'ms': 0.0, 'error': None}
    want_jev = jev_enabled() if use_jev is None else (use_jev and jev_enabled())
    res = {}
    if left and want_jev:
        state, qs = _jev_classify_questions(chans, left, description)
        res, ji = jev_choices(state, qs)
        info.update(calls=ji['calls'], ms=ji['ms'], error=ji['error'])
    for i in left:
        c = chans[i]
        r = res.get('c%d' % i)
        need = JEV_ACCEPT if (r and r['orders'] == 2) else 0.75
        if r and r['p'] >= need and r['choice'] in T.JEV_OPTIONS and r['choice'] != 'other':
            c['category'], c['confidence'], c['via'] = r['choice'], r['p'], 'jev'
            info['accepted'] += 1
        else:
            c['via'] = 'fallback'
            if c['category'] is None:
                c['category'] = 'other'
            if r and r['choice'] != 'other':
                c['suggestion'] = {'category': r['choice'], 'p': r['p']}
            elif r:
                c['category'] = 'other'          # the classifier says none of the templates: a flat channel, marked as a guess
    _lead_pass(chans)
    _tom_pass(chans)
    info['ms_total'] = round((time.time() - t0) * 1000, 1)
    classify.last_info = info
    return chans


classify.last_info = {}


def _tom_pass(chans):
    """Numbered toms and no floor tom on the list ("Tom 1", "Tom 2"): the last one is the floor tom.
    Same rule the templates were built with (templates.json meta.taxonomy.floor_tom)."""
    toms = [c for c in chans if c['category'] in ('rack_tom', 'floor_tom', 'roto_tom') and not c.get('category_locked')]
    if len(toms) < 2 or any(c['category'] == 'floor_tom' for c in toms):
        return
    numbered = [c for c in toms if c['category'] == 'rack_tom' and
                re.search(r'(?i)\b(?:tom|t|rack)\s*\d\b|\btom\s*\d', c.get('full_name') or c['name'])]
    if len(numbered) >= 2:
        last = numbered[-1]
        last['category'] = 'floor_tom'
        last['flags'] = last['flags'] + ['floor_guess']


def _lead_pass(chans):
    """No lead vocal on the list: the first plain vocal channel (not a BGV, guest, spare or TB) is
    the lead. Lists put the artist's vocal first among the vocals far more often than not. Only a sure
    vocal counts: a fallback guess ("TT", "Vibes" read as a person's mic) is never promoted."""
    if any(c['category'] == 'lead_vocal' for c in chans):
        return
    for c in chans:
        if c['category'] == 'vocal_generic' and not BGV_WORDS.search(c.get('full_name') or c['name']) \
                and not c.get('category_locked') and c.get('via') != 'fallback':
            c['category'] = 'lead_vocal'
            c['confidence'] = min(c['confidence'] or 0.6, 0.6)
            c['flags'] = c['flags'] + ['lead_guess']
            return


# --------------------------------------------------------------------------------------------
# description -> channels
# --------------------------------------------------------------------------------------------

STYLES = ('rock_pop', 'worship_band', 'traditional_church', 'singer_songwriter', 'jazz', 'hiphop', 'country', 'corporate')

# (qid, question, {option: description}). 'not_said' means "use the style default".
QUESTIONS = [
    ('style', 'What kind of show does the description in `description` describe?', {
        'rock_pop': 'A rock, pop, indie or punk band',
        'worship_band': 'A contemporary worship band leading a church service',
        'traditional_church': 'A traditional church service (organ, piano, choir, readings, no band)',
        'singer_songwriter': 'A singer-songwriter, acoustic act or small acoustic duo',
        'jazz': 'A jazz combo or big band',
        'hiphop': 'A hip-hop, rap, R&B or electronic act built on tracks or a DJ',
        'country': 'A country, americana, folk or bluegrass band',
        'corporate': 'A corporate event, conference, panel or speech-only event'}),
    ('drums', 'Read `description`. Is there a drum kit on stage?', {
        'not_said': 'The description does not say anything about drums',
        'full_kit': 'An acoustic drum kit / a drummer',
        'small_kit': 'A small or jazz kit (kick, snare, cymbals)',
        'electronic': 'Only an electronic drum kit',
        'hand_perc_only': 'No kit, only a cajon or hand percussion',
        'none': 'No drums at all'}),
    ('kick', 'Read `description`. How many kick drum mics does it ask for?', {
        'not_said': 'It does not say',
        'one': 'One kick mic',
        'in_out': 'Kick in and kick out (two mics)',
        'in_out_sub': 'Kick in, kick out and a sub kick'}),
    ('snare', 'Read `description`. Which snare mics does it ask for?', {
        'not_said': 'It does not say',
        'top': 'Snare top only',
        'top_bottom': 'Snare top and snare bottom',
        'two_snares': 'Two snare drums'}),
    ('toms', 'Read `description`. How many toms does the drum kit have?', {
        'not_said': 'It does not say',
        't0': 'No toms', 't1': 'One tom', 't2': 'Two toms (rack and floor)', 't3': 'Three toms', 't4': 'Four toms'}),
    ('drum_extras', 'Read `description`. What is there besides the drum kit itself?', {
        'none': 'Nothing more, or it does not say',
        'sample_pad': 'A sample pad (SPD-SX) or drum pad',
        'triggers': 'Drum triggers',
        'perc': 'A percussionist or hand percussion (congas, cajon, shaker)',
        'pad_perc': 'A sample pad and a percussionist'}),
    ('bass', 'Read `description`. What bass is there?', {
        'not_said': 'It does not say',
        'none': 'No bass at all',
        'di': 'A bass guitar (DI)',
        'di_amp': 'A bass guitar with a DI and an amp mic',
        'synth': 'Only a synth bass or key bass',
        'upright': 'An upright or double bass'}),
    ('egtr', 'Read `description`. How many electric guitars are there?', {
        'not_said': 'It does not say',
        'g0': 'No electric guitar', 'g1': 'One electric guitar', 'g2': 'Two electric guitars',
        'g3': 'Three electric guitars'}),
    ('agtr', 'Read `description`. How many acoustic guitars are there?', {
        'not_said': 'It does not say',
        'a0': 'No acoustic guitar', 'a1': 'One acoustic guitar', 'a2': 'Two acoustic guitars'}),
    ('keys', 'Read `description`. How many keyboard or synth rigs are there (not an acoustic piano or an organ)?', {
        'not_said': 'It does not say',
        'k0': 'No keyboards', 'k1': 'One keyboard rig', 'k2': 'Two keyboard rigs or players',
        'k3': 'Three or more keyboard rigs'}),
    ('piano_organ', 'Read `description`. Is there an acoustic piano or an organ?', {
        'not_said': 'It does not say',
        'none': 'Neither',
        'piano': 'An acoustic or grand piano',
        'organ': 'An organ (Hammond B3 or a church organ)',
        'both': 'A piano and an organ'}),
    ('horns_strings', 'Read `description`. Are there horn or string players?', {
        'none': 'No horns or strings, or it does not say',
        'horns2': 'One or two horn players (sax, trumpet, trombone)',
        'horns3': 'A horn section of three or more',
        'strings2': 'One or two string players (violin, cello)',
        'quartet': 'A string quartet or string section',
        'both': 'Horns and strings'}),
    ('tracks', 'Read `description`. Is there playback from a computer or a DJ?', {
        'not_said': 'It does not say',
        'none': 'No playback at all',
        'stereo': 'Stereo backing tracks',
        'stereo_click': 'Stereo backing tracks and a click for the band',
        'stems': 'Multitrack stems (several stereo pairs) with click and cues',
        'dj': 'A DJ'}),
    ('vocals', 'Read `description`. How many people sing in total, counting the lead singer and backing singers but not a choir?', {
        'not_said': 'It does not say',
        'v0': 'Nobody sings (instrumental)', 'v1': 'One singer', 'v2': 'Two singers', 'v3': 'Three singers',
        'v4': 'Four singers', 'v5': 'Five singers', 'v6': 'Six or more singers'}),
    ('leads', 'Read `description`. Who sings lead?', {
        'not_said': 'It does not say',
        'one': 'One lead singer',
        'two': 'Two singers share the lead equally (a duo)'}),
    ('choir', 'Read `description`. Is there a choir?', {
        'none': 'No choir, or it does not say',
        'small': 'A small choir or vocal team on two mics',
        'medium': 'A choir on about four mics',
        'large': 'A large choir on six or more mics'}),
    ('speech', 'Read `description`. How many people speak into a mic without singing (pastor, host, MC, panel)?', {
        's0': 'Nobody, or it does not say', 's1': 'One (a pastor, host or MC)', 's2': 'Two speakers',
        's3': 'Three or more speakers (a panel)'}),
    ('audience', 'Read `description`. Does it want audience or crowd mics?', {
        'not_said': 'It does not say',
        'none': 'No audience mics',
        'pair': 'Yes, an audience or crowd pair'}),
]
QUESTION_IDS = [q for q, _, _ in QUESTIONS]

# style -> default answer for every question (used when neither the text nor the classifier settles it)
STYLE_DEFAULTS = {
    'rock_pop': dict(drums='full_kit', kick='in_out', snare='top_bottom', toms='t2', drum_extras='none', bass='di',
                     egtr='g2', agtr='a0', keys='k1', piano_organ='none', horns_strings='none', tracks='none',
                     vocals='v3', leads='one', choir='none', speech='s0', audience='pair'),
    'worship_band': dict(drums='full_kit', kick='in_out', snare='top_bottom', toms='t2', drum_extras='none', bass='di',
                         egtr='g1', agtr='a1', keys='k1', piano_organ='none', horns_strings='none', tracks='stereo_click',
                         vocals='v4', leads='one', choir='none', speech='s1', audience='pair'),
    'traditional_church': dict(drums='none', kick='one', snare='top', toms='t0', drum_extras='none', bass='none',
                               egtr='g0', agtr='a0', keys='k0', piano_organ='both', horns_strings='none', tracks='none',
                               vocals='v1', leads='one', choir='medium', speech='s2', audience='none'),
    'singer_songwriter': dict(drums='none', kick='one', snare='top', toms='t0', drum_extras='none', bass='none',
                              egtr='g0', agtr='a1', keys='k0', piano_organ='none', horns_strings='none', tracks='none',
                              vocals='v1', leads='one', choir='none', speech='s0', audience='none'),
    'jazz': dict(drums='small_kit', kick='one', snare='top', toms='t1', drum_extras='none', bass='upright',
                 egtr='g0', agtr='a0', keys='k0', piano_organ='piano', horns_strings='none', tracks='none',
                 vocals='v0', leads='one', choir='none', speech='s1', audience='none'),
    'hiphop': dict(drums='none', kick='in_out', snare='top', toms='t0', drum_extras='none', bass='none',
                   egtr='g0', agtr='a0', keys='k0', piano_organ='none', horns_strings='none', tracks='stems',
                   vocals='v2', leads='one', choir='none', speech='s0', audience='pair'),
    'country': dict(drums='full_kit', kick='in_out', snare='top_bottom', toms='t2', drum_extras='none', bass='di',
                    egtr='g2', agtr='a1', keys='k1', piano_organ='none', horns_strings='none', tracks='none',
                    vocals='v3', leads='one', choir='none', speech='s0', audience='pair'),
    'corporate': dict(drums='none', kick='one', snare='top', toms='t0', drum_extras='none', bass='none',
                      egtr='g0', agtr='a0', keys='k0', piano_organ='none', horns_strings='none', tracks='none',
                      vocals='v0', leads='one', choir='none', speech='s3', audience='none'),
}

NUM_WORDS = {'a': 1, 'an': 1, 'one': 1, 'single': 1, 'solo': 1, 'two': 2, 'pair': 2, 'couple': 2, 'double': 2, 'three': 3,
             'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'twelve': 12}
NUM = r'(\d{1,2}|a|an|one|single|two|pair of|couple of|three|four|five|six|seven|eight|nine|ten|twelve)'
NUM_STRICT = r'(\d{1,2}|one|two|pair of|couple of|three|four|five|six|seven|eight|nine|ten|twelve)'   # no "a"
ABSENT = {'none', 'not_said', 'g0', 'a0', 'k0', 't0', 's0', 'v0'}


def _n(tok):
    tok = tok.lower().replace(' of', '')
    return int(tok) if tok.isdigit() else NUM_WORDS.get(tok)


def _count(rx, t, strict=False):
    m = re.search((NUM_STRICT if strict else NUM) + r'\s+' + rx, t)
    return _n(m.group(1)) if m else None


def _tom_split(t):
    """(rack, floor) when the text counts rack and/or floor toms, else None.

    '2 rack toms and a floor' -> (2, 1); 'one rack, two floor toms' -> (1, 2); '2 rack toms' -> (2, 0).
    A bare 'floor'/'rack' only counts next to a tom count, so '4 floor wedges' or 'a rack of gear' never
    adds a tom. A plain '3 toms' is left to the caller (no split)."""
    rack = _count(r'rack toms?\b', t)
    floor = _count(r'floor toms?\b', t)
    if rack is None and floor is None:
        return None
    not_gear = r'(?! ?(wedges?|monitors?|mons?|units?|mounts?|cases?|of))'
    if floor is None:                                      # "and a floor", "plus 2 floors", ", floor tom"
        floor = _count(r'floors?\b' + not_gear, t)
        if floor is None:
            floor = 1 if re.search(r'\bfloor toms?\b|(\band|&|plus|\+|,) (a |one )?floor\b' + not_gear, t) else 0
    if rack is None:                                       # "a rack and 2 floor toms", "rack, 2 floor toms"
        rack = _count(r'racks?\b' + not_gear, t)
        if rack is None:
            rack = 1 if re.search(r'\brack toms?\b|\brack( tom)? ?(and|&|plus|\+|,)', t) else 0
    return (rack, floor) if rack + floor else None


def regex_answers(text):
    """Answers the text gives in so many words.

    Returns (answers, weak, extras). answers: {qid: option}. weak: the qids answered only by a
    mention ("keys" -> one keyboard rig, "choir" -> a 4-mic choir); a confident the classifier answer that is
    still a "present" option may refine those. Strong answers (counts, "no drums", "kick in and
    out", "upright bass") always win. extras: named instruments the questions do not cover, the band
    size of an "N-piece", and media / cajon hints."""
    t = ' ' + re.sub(r'\s+', ' ', (text or '').lower()) + ' '
    t = t.replace('-', ' ').replace('/', ' / ')
    a, weak, x = {}, set(), {'named': []}

    def put(q, v, is_weak=False):
        a[q] = v
        if is_weak:
            weak.add(q)
        else:
            weak.discard(q)

    # style
    if re.search(r'\b(worship|praise)\b', t):
        put('style', 'worship_band')
    elif re.search(r'\b(church|mass|liturgy|hymns?|cathedral|chapel)\b', t) and re.search(r'\b(organ|choir|hymn)', t) \
            and not re.search(r'\b(band|drums|drummer|electric)\b', t):
        put('style', 'traditional_church')
    elif re.search(r'\b(hip hop|hiphop|rap|rapper|mc and dj|r&b|edm|electronic act|dj set)\b', t):
        put('style', 'hiphop')
    elif re.search(r'\bjazz\b|\bbig band\b|\bbebop\b', t):
        put('style', 'jazz')
    elif re.search(r'\b(singer songwriter|songwriter|acoustic (duo|act|set|show)|in the round)\b', t):
        put('style', 'singer_songwriter')
    elif re.search(r'\b(country|americana|bluegrass|folk)\b', t):
        put('style', 'country')
    elif re.search(r'\b(conference|corporate|keynote|panel|summit|seminar|lecture|town hall|gala|award)\b', t) and \
            not re.search(r'\bband\b', t):
        put('style', 'corporate')
    elif re.search(r'\b(theatre|theater|play|drama|panto|pantomime|lavs?|lavaliers?|lapel|handhelds?|headsets?|podium|'
                   r'lectern)\b', t) and not re.search(r'\b(band|drums?|drummer|bass|guitars?|gtrs?|keys|keyboards?|piano|'
                                                     r'organ|synths?|singers?|vocals?|vox|choir|horns?|sax|trumpets?|'
                                                     r'strings|violins?|fiddle|musical|orchestra|pit|tracks)\b', t):
        put('style', 'corporate')                 # speech mics and no instrument: "Theatre show: 12 wireless lavs"
    elif re.search(r'\b(rock|pop|indie|punk|metal|band)\b', t):
        put('style', 'rock_pop', True)
    m = re.search(r'\b(\d|two|three|four|five|six|seven|eight|nine|ten) piece\b', t)
    if m:
        x['members'] = _n(m.group(1))
    elif re.search(r'\btrio\b', t):
        x['members'] = 3
    elif re.search(r'\bquartet\b', t) and not re.search(r'string quartet', t):
        x['members'] = 4
    elif re.search(r'\bduo\b', t):
        x['members'] = 2
    # drums
    if re.search(r'\bno (drums|drummer|kit)\b|\bwithout (drums|a drummer)\b', t):
        put('drums', 'none')
    elif re.search(r'\b(electronic|e) ?(drum )?kit\b|\be drums\b|\broland td\b|\bedrums\b', t):
        put('drums', 'electronic')
    elif re.search(r'\b(jazz kit|small kit|brushes|bop kit|cocktail kit)\b', t):
        put('drums', 'small_kit')
    elif re.search(r'\b(drums|drummer|drum kit|kit)\b', t):
        put('drums', 'full_kit', True)
    elif re.search(r'\b(cajon|djembe|hand percussion|percussion)\b', t):
        put('drums', 'hand_perc_only', True)
    elif re.search(r'\b(kick|snare|toms?|hi ?hats?|hats|overheads?|cymbals?)\b', t):
        put('drums', 'full_kit', True)                   # "kick in and out, snare top and bottom": a kit
    if re.search(r'\bsub ?kick\b|\bkick sub\b', t):
        put('kick', 'in_out_sub')
    elif re.search(r'\bkick in (and|&|/) ?(kick )?out\b|\bkick (in|inside) and (outside|out)\b|\b(2|two) kick mics?\b', t):
        put('kick', 'in_out')
    elif re.search(r'\b(one|1|single) kick mic\b', t):
        put('kick', 'one')
    if re.search(r'\b(two|2) snares\b|\bsnare 2\b|\bsecond snare\b', t):
        put('snare', 'two_snares')
    elif re.search(r'\bsnare (top )?(and|&|/) ?(snare )?(bottom|bot|under)\b|\btop and bottom snare\b', t):
        put('snare', 'top_bottom')
    split = _tom_split(t)
    if split:
        put('toms', 't%d' % min(4, sum(split)))
        x['tom_split'] = split
    else:
        k = _count(r'(rack |floor )?toms?\b', t)
        if k is not None:
            put('toms', 't%d' % min(4, k))
        elif re.search(r'\brack (tom )?(and|&) floor\b', t):
            put('toms', 't2')
    pad = re.search(r'\b(spd|sample pad|drum pad|octapad|sampler|pads? for the drummer)\b', t)
    perc = re.search(r'\b(percussion(ist)?|congas?|bongos?|cajon|shaker|tambourine|timbales|djembe)\b', t) and \
        a.get('drums') not in (None, 'hand_perc_only')
    trig = re.search(r'\btrigger', t)
    if pad and perc:
        put('drum_extras', 'pad_perc')
    elif pad:
        put('drum_extras', 'sample_pad')
    elif perc:
        put('drum_extras', 'perc')
    elif trig:
        put('drum_extras', 'triggers')
    # bass
    if re.search(r'\bno bass\b', t):
        put('bass', 'none')
    elif re.search(r'\b(upright|double|stand up|acoustic) bass\b', t):
        put('bass', 'upright')
    elif re.search(r'\b(synth|key|moog) bass\b|\bbass synth\b', t) and not re.search(r'\bbass (guitar|player|di)\b', t):
        put('bass', 'synth')
    elif re.search(r'\bbass (amp|cab|mic)\b|\bbass (di )?(and|&|\+) ?(an )?amp\b', t):
        put('bass', 'di_amp')
    elif re.search(r'\bbass(ist| guitar| player)?\b', t) and not re.search(r'\bbass drum\b', t):
        put('bass', 'di', True)
    # guitars
    e = _count(r'(electric )?(guitars?|gtrs?|guitarists?|guitar players)\b', t)
    e_said = _count(r'electric (guitars?|gtrs?|guitarists?|guitar players)\b', t)   # "2 electric guitars"
    ac = _count(r'(acoustic|acoustics|acoustic guitars?|ags?)\b', t)
    if e_said is not None:
        put('egtr', 'g%d' % min(3, e_said))   # stated outright, even with "and an acoustic" next to it
        x['n_egtr'] = e_said
    elif e is not None and not re.search(NUM + r'\s+acoustic', t):
        put('egtr', 'g%d' % min(3, e))         # "3 guitars", unless an acoustic count may be part of it
        x['n_egtr'] = e
    elif re.search(r'\b(electric guitar|electric|eg|guitarist|lead guitar)\b', t):
        put('egtr', 'g1', True)
    elif re.search(r'\bguitar\b', t) and not re.search(r'\bacoustic( guitar)?\b', t):
        put('egtr', 'g1', True)
    if ac is not None:
        put('agtr', 'a%d' % min(2, ac))
        x['n_agtr'] = ac
    elif re.search(r'\bacoustic( guitar)?\b', t) and not re.search(r'\bacoustic (duo|act|set|show|bass)\b', t):
        put('agtr', 'a1', True)
    if re.search(r'\b(no|without) (electric )?guitars?\b', t):
        put('egtr', 'g0')
    # keys
    kk = _count(r'(keys|keyboards?|keyboard players?|synths?|key players?)\b', t)
    if kk is not None:
        put('keys', 'k%d' % min(3, kk))
        x['n_keys'] = kk
    elif re.search(r'\b(keys|keyboards?|synths?|nord|rhodes|wurli\w*|keyboardist)\b', t):
        put('keys', 'k1', True)
    pno = re.search(r'\b(piano|grand)\b', t) and not re.search(r'\b(electric|digital|stage) piano\b', t)
    org = re.search(r'\b(organ|b3|hammond)\b', t)
    if pno or org:
        put('piano_organ', 'both' if (pno and org) else ('piano' if pno else 'organ'))
    # horns / strings and named instruments
    horns = [w for w in ('trumpet', 'sax', 'saxophone', 'trombone', 'flute', 'clarinet', 'flugelhorn')
             if re.search(r'\b%s(?:e?s)?\b' % w, t)]
    strs = [w for w in ('violin', 'viola', 'cello') if re.search(r'\b%ss?\b' % w, t)]
    # "5 saxes, 4 trumpets": one channel each (house_order), not one per instrument type
    x['n_horns'] = {w: n for w in horns for n in [_count(r'%s(?:e?s)?\b' % w, t, strict=True)] if n}
    x['n_strings'] = {w: n for w in strs for n in [_count(r'%ss?\b' % w, t, strict=True)] if n}
    hs = re.search(r'\bhorn section\b|\bhorns\b', t)
    sq = re.search(r'\bstring (quartet|section)\b|\bstrings\b', t)
    if (horns or hs) and (strs or sq):
        put('horns_strings', 'both')
    elif hs or len(horns) >= 3:
        put('horns_strings', 'horns3' if (len(horns) >= 3 or re.search(r'\bhorn section\b', t)) else 'horns2')
    elif horns:
        put('horns_strings', 'horns2')
    elif sq and re.search(r'\bstring (quartet|section)\b', t):
        put('horns_strings', 'quartet')
    elif strs or sq:
        put('horns_strings', 'strings2')
    x['horns'] = horns
    x['strings'] = strs
    for w, nm, cat in (('fiddle', 'Fiddle', 'folk_strings'), ('mandolin', 'Mando', 'folk_strings'),
                       ('banjo', 'Banjo', 'folk_strings'), ('dobro', 'Dobro', 'folk_strings'),
                       ('pedal steel', 'Steel', 'electric_guitar'), ('lap steel', 'LapSteel', 'electric_guitar'),
                       ('harmonica', 'Harmnca', 'horns'), ('accordion', 'Accrdn', 'keys'), ('ukulele', 'Uke', 'folk_strings')):
        if re.search(r'\b%s\b' % w, t):
            x['named'].append((nm, cat))
    # playback
    stems = re.search(r'\b(stems|multitrack|multi track)\b', t)
    trk = re.search(r'\b(tracks|playback|ableton|backing track|track rig|laptop rig|sequence|stems)\b', t)
    clk = re.search(r'\b(click|in ear click|metronome)\b', t)
    media = re.search(r'\b(walk ?in|video|propresenter|pro presenter|announcement video)\b', t)
    media_only = trk and media and not re.search(r'\b(tracks|ableton|backing track|track rig|sequence|stems|click)\b', t)
    if media_only:
        trk = None                                         # "walk-in music and video playback": the Media channel
    if re.search(r'\bno (tracks|playback)\b', t) or media_only:
        put('tracks', 'none')
    elif re.search(r'\bdj\b', t) and not trk:
        put('tracks', 'dj')
    elif stems:
        put('tracks', 'stems')
    elif trk:
        put('tracks', 'stereo_click' if clk else 'stereo')
    elif clk:
        put('tracks', 'stereo_click')
    # vocals
    v = _count(r'(singers?|vocalists?|vocal mics?|vocals|voices|vox)\b', t, strict=True)
    bg = _count(r'(bgvs?|backing (vocals?|vocalists|singers)|background (vocals?|vocalists|singers)|harmony (vocals?|singers))\b', t)
    lead_said = re.search(r'\b(lead (vocal|singer|vox)|singer|sings|vocalist|rapper|mc|worship leader|frontman|frontwoman)\b', t)
    two_leads = re.search(r'\b(both sing lead|two lead|2 lead|share (the )?lead|co lead|duet)\b', t)
    sings = len(re.findall(r'\b(sings|sing)\b', t))
    hm = re.search(NUM_STRICT + r' (?:of (?:the|us|them) )?(?:guys|girls|players|members|others|band members|of us)? ?'
                   r'(?:also )?sing (?:harmony|harmonies|bgvs?|backing( vocals)?|backups?)\b', t)
    if hm and bg is None:
        bg = _n(hm.group(1))
    # "a fiddle player who sings harmony": one harmony singer per mention that gives no number; "the guitar players
    # sing harmonies" (plural subject, "sing") counts two
    harm = sum(1 if v_ == 'sings' else 2 for v_ in
               re.findall(r'\b(sings?) (?:harmony|harmonies|bgvs?|backing(?: vocals)?|backups?|background)\b', t))
    if bg is None and harm and not hm:
        bg = harm
    if two_leads:
        put('leads', 'two')
    if bg is not None:
        lead = 2 if two_leads else (1 if lead_said or a.get('style') != 'jazz' else 0)
        put('vocals', 'v%d' % min(6, lead + bg))
        x['n_vocals'] = lead + bg
    elif v is not None:
        put('vocals', 'v%d' % min(6, v))
        x['n_vocals'] = v
    elif re.search(r'\b(instrumental|no (vocals|singers))\b', t):
        put('vocals', 'v0')
    elif two_leads:
        put('vocals', 'v2', True)
    elif sings >= 2:
        put('vocals', 'v%d' % min(6, sings), True)
    m = re.search(r'\b(\d{1,3}) (voice|person|member|piece|singer|strong) (choir|ensemble)\b', t)
    ch = _count(r'(choir mics?)\b', t, strict=True)
    if m:
        n = int(m.group(1))
        put('choir', 'small' if n <= 6 else ('medium' if n <= 15 else 'large'))
    elif ch is not None:
        put('choir', 'small' if ch <= 2 else ('medium' if ch <= 4 else 'large'))
        x['n_choir'] = ch
    elif re.search(r'\b(large|big|mass|full) (choir|chorus)\b', t):
        put('choir', 'large')
    elif re.search(r'\b(choir|chorus)\b', t):
        put('choir', 'medium', True)
    plan = _speech_plan(t)
    if plan:
        x['speech_plan'] = plan
    sp = _count(SPEECH_ADJ + r'(speakers|presenters|panelists?|panellists?|lavs?|lavaliers|headsets|speech mics?)\b', t,
                strict=True)
    if plan:
        put('speech', 's%d' % min(3, len(plan)))
    elif sp is not None:
        put('speech', 's%d' % min(3, sp))
    elif re.search(r'\bpanel\b', t):
        put('speech', 's3', True)
    else:
        talkers = re.findall(r'\b(pastor|preacher|priest|host|emcee|mc|announcer|speaker|presenter|officiant|reader|'
                             r'narrator|minister|lector|bandleader talks|talks between)\b', t)
        if talkers:
            put('speech', 's%d' % min(3, len(set(talkers))), True)
    if re.search(r'\b(audience|crowd|ambient) (mics?|pair)\b', t):
        put('audience', 'pair')
    elif re.search(r'\bno (audience|crowd) mics?\b', t):
        put('audience', 'none')
    x['media'] = bool(re.search(r'\b(walk ?in|video|propresenter|pro presenter|laptop|media|announcement video|playback for)\b', t))
    x['said_choir'] = bool(re.search(r'\b(choir|chorus|ensemble|vocal team|praise team)\b', t))
    x['said_audience'] = bool(re.search(r'\b(audience|crowd|ambient|ambience|room mics?)\b', t))
    x['cajon'] = bool(re.search(r'\bcajon\b', t))
    return a, weak, x


# Speech mics a description lists one by one. (kind, regex after an optional count, console name). Earlier kinds
# win where matches overlap, so "a moderator with a handheld" is one mic and "6 panelists on lavs" is six.
SPEECH_KINDS = [
    ('role', r'(moderator|host|emcee|mc|pastor|presenter|officiant|preacher|priest|minister|reader|lector|narrator|'
             r'announcer|keynote speaker)s?(?: (?:with|on|using|at) (?:an? |the )?(?:handheld|hand held|lav|lavalier|'
             r'headset|wireless|podium mic|podium|lectern|pulpit)s?)?', None),
    ('panel', r'(?:panelists?|panellists?)(?: (?:lavs?|lavaliers?|headsets?|mics?)| (?:on|with) (?:lavs?|lavaliers?|'
              r'headsets?|handhelds?))?', 'Panel'),
    ('podium', r'(?:podium|lectern|pulpit)(?: mics?)?', None),
    ('handheld', r'(?:handheld|hand held)s?(?: (?:wireless|radio|mics?))*', 'HH'),
    ('lav', r'(?:lavs?|lavaliers?|lapel mics?)', 'Lav'),
    ('headset', r'headsets?(?: mics?)?', 'Headset'),
]
# Words that may stand between a count and the mic kind: "12 wireless lav mics", "2 radio handhelds".
SPEECH_ADJ = r'(?:(?:wireless|radio|rf|cordless|lapel|headworn|head-worn|omni|countryman|dpa|shure|sennheiser)\s+)*'
ROLE_NAMES = {'moderator': 'Mod', 'host': 'Host', 'emcee': 'MC', 'mc': 'MC', 'pastor': 'Pastor', 'presenter': 'Presenter',
              'officiant': 'Officiant', 'preacher': 'Preacher', 'announcer': 'Announcer', 'keynote speaker': 'Keynote',
              'priest': 'Priest', 'minister': 'Minister', 'reader': 'Reader', 'lector': 'Lector', 'narrator': 'Narrator',
              'podium': 'Podium', 'lectern': 'Lectern', 'pulpit': 'Pulpit'}


def _speech_plan(t):
    """[(console name, full name)] for speech mics the text names or counts ("podium mic, 2 handheld wireless,
    4 panelist lavs" -> Podium, HH 1, HH 2, Panel 1..4), or [] when it names none. A plural with no number counts
    as two ("panelists on lavs")."""
    taken, found = [], []
    for kind, rx, base in SPEECH_KINDS:
        for m in re.finditer(r'\b(?:' + NUM_STRICT + r'\s+' + SPEECH_ADJ + r')?(' + rx + r')\b', t):
            if any(m.start() < b and a < m.end() for a, b in taken):
                continue
            taken.append(m.span())
            head = m.group(2).split()[0]
            if m.group(1):
                n = _n(m.group(1)) or 1
            else:
                n = 2 if kind in ('panel', 'handheld', 'lav', 'headset') and head.endswith('s') else 1
            if kind in ('role', 'podium'):
                word = re.match(r'(keynote speaker|\w+?)s?\b', m.group(2)).group(1)
                word = word if word in ROLE_NAMES else word + 's' if word + 's' in ROLE_NAMES else word
                name = ROLE_NAMES.get(word, word.title())
            else:
                name = base
            found.append((m.start(), name, min(n, 12), m.group(0).strip()))
    out = []
    for _, name, n, full in sorted(found):
        out += [(name if n == 1 else '%s %d' % (name, i + 1), full) for i in range(n)]
    return out


# Who fills the seats of an N-piece band after drums, bass and any named instruments, in order.
SEAT_ORDER = {'rock_pop': ['egtr', 'egtr', 'keys', 'agtr'], 'country': ['egtr', 'agtr', 'keys', 'egtr'],
              'worship_band': ['egtr', 'keys', 'agtr', 'egtr']}


def _band_size_defaults(d, members, style, named=0):
    """An N-piece band with no instrument counts: drums and bass take two seats, named instruments
    (fiddle, steel) one each, the rest are guitars and keys in SEAT_ORDER. The lead singer is
    assumed to play one of them; vocals default to the lead plus up to two harmony singers."""
    if not members or style not in SEAT_ORDER:
        return d
    d = dict(d)
    seats = max(0, members - 2 - named)
    n = {'egtr': 0, 'agtr': 0, 'keys': 0}
    for k in range(seats):
        n[SEAT_ORDER[style][k % len(SEAT_ORDER[style])]] += 1
    d.update(egtr='g%d' % min(3, n['egtr']), agtr='a%d' % min(2, n['agtr']), keys='k%d' % min(3, n['keys']),
             vocals='v%d' % min(3, max(1, members - 2)))
    return d


def _ch(name, cat, stereo=False, phantom=None, via='fallback', notes=None):
    return {'name': console_name(name), 'full_name': name, 'stereo': stereo, 'category': cat,
            'confidence': None, 'via': via, 'phantom': phantom, 'source': None, 'source_type': None,
            'notes': notes, 'list_ch': [], 'section': None, 'who': None, 'stand': None, 'flags': ['from_description']}


def house_order(ans, via, extras):
    """The channel list for a set of answers, in house order: drums top down, bass, guitars,
    keys, horns/strings, playback, vocals (lead first), choir, speech, talkback, audience."""
    out = []

    def add(name, cat, q, stereo=False, phantom=None):
        out.append(_ch(name, cat, stereo, phantom, via.get(q, 'fallback')))

    style = ans['style']
    drums = ans['drums']
    if drums in ('full_kit', 'small_kit'):
        k = ans['kick'] if drums == 'full_kit' or ans['kick'] != 'in_out_sub' else 'one'
        if drums == 'small_kit' and via.get('kick') == 'fallback':
            k = 'one'
        if k == 'one':
            add('Kick', 'kick_in', 'kick')
        else:
            add('Kick In', 'kick_in', 'kick')
            add('Kick Out', 'kick_out', 'kick')
            if k == 'in_out_sub':
                add('Sub Kick', 'kick_sub', 'kick')
        s = ans['snare'] if not (drums == 'small_kit' and via.get('snare') == 'fallback') else 'top'
        if s == 'top':
            add('Snare', 'snare_top', 'snare')
        elif s == 'top_bottom':
            add('Snr Top', 'snare_top', 'snare')
            add('Snr Bot', 'snare_bottom', 'snare')
        else:
            add('Snr1 Top', 'snare_top', 'snare')
            add('Snr1 Bot', 'snare_bottom', 'snare')
            add('Snr2 Top', 'snare_top', 'snare')
        if drums == 'full_kit' or via.get('drums') != 'fallback':
            add('Hi Hat', 'hihat', 'drums', phantom=True)
        toms = int(ans['toms'][1:])
        names = {1: ['Rack'], 2: ['Rack', 'Floor'], 3: ['Rack 1', 'Rack 2', 'Floor'],
                 4: ['Rack 1', 'Rack 2', 'Floor 1', 'Floor 2']}.get(toms, [])
        split = extras.get('tom_split')
        if split and sum(split) == toms and via.get('toms') == 'rule':     # the text said racks vs floors
            r, f = split
            names = (['Rack'] if r == 1 else ['Rack %d' % (i + 1) for i in range(r)]) + \
                    (['Floor'] if f == 1 else ['Floor %d' % (i + 1) for i in range(f)])
        for nm in names:
            add(nm, 'floor_tom' if nm.startswith('Floor') else 'rack_tom', 'toms')
        add('OH', 'overheads', 'drums', stereo=True, phantom=True)
    elif drums == 'electronic':
        add('E-Kit', 'sample_pad', 'drums', stereo=True)
    elif drums == 'hand_perc_only':
        add('Cajon' if extras.get('cajon') else 'Perc', 'hand_perc', 'drums')
    ex = ans['drum_extras']
    if drums != 'none' and ex in ('sample_pad', 'pad_perc'):
        add('SPD', 'sample_pad', 'drum_extras', stereo=True)
    if drums in ('full_kit', 'small_kit') and ex == 'triggers':
        add('Kick Trg', 'drum_trigger', 'drum_extras')
        add('Snr Trg', 'drum_trigger', 'drum_extras')
    if ex in ('perc', 'pad_perc') and drums != 'hand_perc_only':
        add('Perc 1', 'hand_perc', 'drum_extras')
        add('Perc 2', 'hand_perc', 'drum_extras')
    b = ans['bass']
    if b == 'di':
        add('Bass DI', 'bass_di', 'bass')
    elif b == 'di_amp':
        add('Bass DI', 'bass_di', 'bass')
        add('Bass Amp', 'bass_amp', 'bass')
    elif b == 'synth':
        add('Syn Bass', 'synth_bass', 'bass')
    elif b == 'upright':
        add('Upr DI', 'bass_di', 'bass')
        add('Upr Mic', 'bass_amp', 'bass', phantom=True)
    g = extras.get('n_egtr', int(ans['egtr'][1:]))
    for i in range(g):
        add('Gtr' if g == 1 else 'Gtr %d' % (i + 1), 'electric_guitar', 'egtr')
    for nm, cat in extras.get('named', []):
        if cat == 'electric_guitar':
            add(nm, cat, 'egtr')
    a = extras.get('n_agtr', int(ans['agtr'][1:]))
    for i in range(a):
        add('AG' if a == 1 else 'AG %d' % (i + 1), 'acoustic_guitar', 'agtr')
    for nm, cat in extras.get('named', []):
        if cat == 'folk_strings':
            add(nm, cat, 'agtr')
    k = extras.get('n_keys', int(ans['keys'][1:]))
    for i in range(k):
        add('Keys' if k == 1 else 'Keys %d' % (i + 1), 'keys', 'keys', stereo=True)
    po = ans['piano_organ']
    if po in ('piano', 'both'):
        add('Piano', 'piano', 'piano_organ', stereo=True, phantom=True)
    if po in ('organ', 'both'):
        add('Organ', 'organ', 'piano_organ', stereo=True)
    for nm, cat in extras.get('named', []):
        if cat in ('keys', 'horns'):
            add(nm, cat, 'keys')
    hs = ans['horns_strings']
    named_h = {'trumpet': 'Tpt', 'sax': 'Sax', 'saxophone': 'Sax', 'trombone': 'Tbn', 'flute': 'Flute',
               'clarinet': 'Clarinet', 'flugelhorn': 'Flugel'}
    named_s = {'violin': 'Violin', 'viola': 'Viola', 'cello': 'Cello'}
    if hs in ('horns2', 'horns3', 'both'):
        hn = list(dict.fromkeys(named_h[w] for w in extras.get('horns', [])))
        if not hn:
            hn = ['Tpt', 'Sax', 'Tbn'] if hs == 'horns3' else ['Horn 1', 'Horn 2']
        counts = {named_h[w]: min(COUNT_CAP, n) for w, n in (extras.get('n_horns') or {}).items()}
        for nm in hn:
            n = counts.get(nm, 1)
            for i in range(n):
                add(nm if n == 1 else '%s %d' % (nm, i + 1), 'horns', 'horns_strings')
    if hs in ('strings2', 'quartet', 'both'):
        sn = list(dict.fromkeys(named_s[w] for w in extras.get('strings', [])))
        if hs == 'quartet' and len(sn) < 4:
            sn = ['Vln 1', 'Vln 2', 'Viola', 'Cello']
        elif not sn:
            sn = ['Violin', 'Cello']
        counts = {named_s[w]: min(COUNT_CAP, n) for w, n in (extras.get('n_strings') or {}).items()}
        for nm in sn:
            n = counts.get(nm, 1)
            for i in range(n):
                add(nm if n == 1 else '%s %d' % (nm, i + 1), 'strings', 'horns_strings', phantom=True)
    tr = ans['tracks']
    if tr in ('stereo', 'stereo_click'):
        add('Tracks', 'tracks_music', 'tracks', stereo=True)
        if tr == 'stereo_click':
            add('Click', 'click', 'tracks')
    elif tr == 'stems':
        add('Trx Drum', 'tracks_drums_perc', 'tracks', stereo=True)
        add('Trx Bass', 'tracks_bass', 'tracks')
        add('Trx Keys', 'tracks_music', 'tracks', stereo=True)
        add('Trx Vox', 'tracks_vocals', 'tracks', stereo=True)
        add('Click', 'click', 'tracks')
        add('Cues', 'cues_guide', 'tracks')
    elif tr == 'dj':
        add('DJ', 'tracks_music', 'tracks', stereo=True)
    if extras.get('media') or (style in ('worship_band', 'traditional_church', 'corporate') and
                               not extras.get('inventory')):
        add('Media', 'media_playback', 'style', stereo=True)
    v = extras.get('n_vocals', int(ans['vocals'][1:]))
    leads = 2 if (ans['leads'] == 'two' and v >= 2) else (1 if v >= 1 else 0)
    if leads == 2:
        add('Vox 1', 'lead_vocal', 'leads')
        add('Vox 2', 'lead_vocal', 'leads')
    elif leads == 1:
        add('Lead Vox', 'lead_vocal', 'vocals')
    for i in range(v - leads):
        add('BGV %d' % (i + 1), 'vocal_generic', 'vocals')
    c = extras.get('n_choir') or {'small': 2, 'medium': 4, 'large': 6}.get(ans['choir'], 0)
    for i in range(c):
        add('Choir %d' % (i + 1), 'choir', 'choir', phantom=True)
    s = int(ans['speech'][1:])
    sp_names = {'worship_band': ['Pastor', 'Speech 2', 'Speech 3'], 'traditional_church': ['Pulpit', 'Lectern', 'Speech 3'],
                'corporate': ['Podium', 'HH 1', 'HH 2', 'HH 3']}.get(style, ['MC', 'Speech 2', 'Speech 3'])
    if extras.get('speech_plan'):                 # the text named them: "podium, 2 handhelds, 4 panelist lavs"
        for nm, full in extras['speech_plan']:
            add(nm, 'speech_mic', 'speech')
            out[-1]['full_name'] = '%s (%s)' % (nm, full) if full.lower() != nm.lower() else nm
        s = len(extras['speech_plan'])
    else:
        if style == 'corporate' and s >= 3:
            s = 4                                 # a panel: podium + three handhelds
        for i in range(s):
            add(sp_names[i] if i < len(sp_names) else 'Speech %d' % (i + 1), 'speech_mic', 'speech')
    if style != 'corporate' or s:
        add('TB', 'talkback', 'style')
    if ans['audience'] == 'pair':
        add('Aud', 'audience', 'audience', stereo=True, phantom=True)
    _uniquify(out)
    for k, ch in enumerate(out, start=1):
        ch['n'] = k
    return out


# Questions whose answer adds inputs. When a description names three or more of them it is an inventory: the
# ones it does not name are absent (not the style default, not a guess from the classifier).
INVENTORY_QS = ('drums', 'drum_extras', 'bass', 'egtr', 'agtr', 'keys', 'piano_organ', 'horns_strings', 'tracks', 'vocals',
                'choir', 'speech', 'audience')
SILENT_ABSENT = {'drums': 'none', 'drum_extras': 'none', 'bass': 'none', 'egtr': 'g0', 'agtr': 'a0', 'keys': 'k0',
                 'piano_organ': 'none', 'horns_strings': 'none', 'tracks': 'none', 'choir': 'none', 'audience': 'none',
                 'speech': 's0'}
COUNT_CAP = 24        # most channels one stated count may add ("8 singers", "5 saxes")


def describe_to_channels(description, use_jev=None):
    """A show description -> {'channels', 'answers', 'info'}. Every question is answered by the
    text itself when it states it, else by the classifier (p >= JEV_Q_ACCEPT), else by the style default.

    Limits on the classifier and the defaults: a description that names three or more parts of the show (an inventory)
    gets nothing it does not name, and the classifier never adds a choir or audience mics the text does not mention."""
    t0 = time.time()
    rx, weak, extras = regex_answers(description)
    kinds = {nm.split()[0] for nm, _ in extras.get('speech_plan') or []}
    inventory = sum(q in rx for q in INVENTORY_QS) + bool(extras.get('media')) + max(0, len(kinds) - 1) >= 3
    want_jev = jev_enabled() if use_jev is None else (use_jev and jev_enabled())
    jres, ji = ({}, {'calls': 0, 'ms': 0.0, 'error': 'disabled' if not want_jev else None})
    if want_jev and (description or '').strip():
        qs = {q: (ins, opts) for q, ins, opts in QUESTIONS}
        jres, ji = jev_choices({'description': description[:2000]}, qs)
    ans, via, detail = {}, {}, {}

    def settle(q, default):
        r = jres.get(q)
        need = JEV_Q_ACCEPT if (r and r['orders'] == 2) else 0.75
        jev_ok = r and r['p'] >= need and r['choice'] != 'not_said'
        if jev_ok and r['choice'] not in ABSENT and ((q == 'choir' and not extras['said_choir']) or
                                                      (q == 'audience' and not extras['said_audience'])):
            jev_ok = False                                    # "8 singers" is not a choir
        if q not in rx and inventory and q in SILENT_ABSENT:
            ans[q], via[q] = SILENT_ABSENT[q], 'fallback'     # an inventory leaves it out (an assumption)
            detail[q] = {'answer': ans[q], 'via': 'fallback', 'not_said': True,
                         'jev': ({'choice': r['choice'], 'p': r['p']} if r else None)}
            return
        if q in rx and q not in weak:
            ans[q], via[q] = rx[q], 'rule'                    # the text says it outright
        elif q in rx and jev_ok and r['choice'] not in ABSENT and (rx[q] in ABSENT) == (r['choice'] in ABSENT):
            ans[q], via[q] = r['choice'], 'jev'               # a mention, refined by the classifier ("choir" -> large)
        elif q in rx:
            ans[q], via[q] = rx[q], 'rule'
        elif jev_ok:
            ans[q], via[q] = r['choice'], 'jev'
        else:
            ans[q], via[q] = default, 'fallback'
        detail[q] = {'answer': ans[q], 'via': via[q], 'jev': ({'choice': r['choice'], 'p': r['p']} if r else None)}

    settle('style', 'rock_pop')
    defaults = _band_size_defaults(STYLE_DEFAULTS[ans['style']], extras.get('members'), ans['style'],
                                   len(extras.get('named', [])))
    for q in QUESTION_IDS[1:]:
        settle(q, defaults[q])
    # keep the answers consistent with each other
    if ans['drums'] in ('none', 'electronic', 'hand_perc_only'):
        for q in ('kick', 'snare', 'toms'):
            detail[q]['used'] = False
    if ans['vocals'] == 'v0' and ans['leads'] == 'two':
        ans['leads'] = 'one'
    if ans['vocals'] == 'v1' and ans['leads'] == 'two':
        ans['vocals'] = 'v2'
    if extras.get('named') and ans['horns_strings'] in ('strings2', 'quartet') and via['horns_strings'] == 'jev' \
            and not extras.get('strings') and not re.search(r'(?i)\bstrings?\b', description):
        ans['horns_strings'], via['horns_strings'] = 'none', 'rule'     # a fiddle or mandolin is not a string section
        detail['horns_strings'].update(answer='none', via='rule')
    extras['inventory'] = inventory
    # counts the options cap ("Six or more singers", "Three electric guitars") stay exact when the text gave them
    counts = {'vocals': 'n_vocals', 'egtr': 'n_egtr', 'agtr': 'n_agtr', 'keys': 'n_keys', 'choir': 'n_choir'}
    dropped = []
    for q, k in counts.items():
        n = extras.get(k)
        if n is None or via.get(q) != 'rule':
            extras.pop(k, None)
            continue
        if n > COUNT_CAP:
            dropped.append('%d %s, kept %d' % (n, CHIP_NOUNS.get(q, q), COUNT_CAP))
            extras[k] = COUNT_CAP
        detail[q]['text'] = '%d %s' % (extras[k], CHIP_NOUNS.get(q, q))
    if via.get('speech') != 'rule':
        extras.pop('speech_plan', None)
    elif extras.get('speech_plan'):
        detail['speech']['text'] = '%d speech mics' % len(extras['speech_plan'])
    if via.get('horns_strings') == 'rule' and (extras.get('n_horns') or extras.get('n_strings')):
        detail['horns_strings']['text'] = ', '.join('%d %s' % (n, w) for w, n in
                                                    list(extras.get('n_horns', {}).items()) +
                                                    list(extras.get('n_strings', {}).items()))
    chans = house_order(ans, via, extras)
    info = {'jev_calls': ji['calls'], 'jev_ms': ji['ms'], 'jev_error': ji['error'], 'ms': round((time.time() - t0) * 1000, 1),
            'members': extras.get('members'), 'inventory': inventory, 'dropped': dropped}
    return {'channels': chans, 'answers': detail, 'info': info}


CHIP_NOUNS = {'vocals': 'singers', 'egtr': 'electric guitars', 'agtr': 'acoustic guitars', 'keys': 'keyboard rigs',
              'choir': 'choir mics'}


# --------------------------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------------------------

# An item that describes the band rather than naming an input: a count of a plural ("2 guitars", "three vocals"),
# or a player or the whole kit ("drums", "a drummer", "band", "singers").
DESC_ITEM = re.compile(r"(?i)^(?:(?:\d{1,2}|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twelve|a couple of|a pair of)"
                       r"\s+(?:\w+\s+)?\w+s\b|.*\b(?:drums|drummer|kit|band|piece|players?|musicians?|bassist|guitarists?|"
                       r"keyboardists?|singers?|vocalists?|rapper|trio|quartet|duo|section)\b)")
NUMBERED_LINE = re.compile(r'^\s*(?:ch\.?\s*)?(\d{1,3})(?:\s*[-–/&+]\s*\d{1,3})?\s*[-.):\t ]\s*\S', re.I)


def _list_items(items):
    """True when every item reads like one input on a list: short, not a sentence, not a description of the band,
    and most of them name a source the rules know."""
    if not items:
        return False
    known = 0
    for it in items:
        t = L.BULLET.sub('', it).strip()
        sentence = re.search(r'[.!?]\s+\S', t)                  # two sentences in one item
        joined = re.search(r'(?i)\b(and|with|plus)\b', t)      # "Vocal and guitar" describes, a list splits it
        if not t or len(t.split()) > 5 or sentence or joined or L.PROSE_RX.search(t) or DESC_ITEM.match(t):
            return False
        known += T.rule_category(t)[1] >= 0.6
    return known >= 0.7 * len(items)


def looks_like_list(text):
    """'lines' or 'commas' when pasted text is an input list rather than a description of the show, else None.

    lines   numbered lines in order ("1 Kick", "2 Snare"; two lines are enough), or two or more short lines that
            each name one source ("Kik", "Sn T", "OH L/R", "Vox 1 (Sam)")
    commas  one or more lines of comma-separated sources ("Kick, Snare, Hat, OH L/R, Bass DI, Gtr, Vox 2"), at
            least 4 of them. A count of a plural ("2 guitars") or a player ("drummer") makes it a description."""
    lines = [l for l in (text or '').splitlines() if l.strip()]
    if not lines:
        return None
    nums = [int(m.group(1)) for m in (NUMBERED_LINE.match(l) for l in lines) if m]
    if len(nums) >= 2 and len(nums) >= 0.6 * len(lines) and all(b > a for a, b in zip(nums, nums[1:])) and \
            not all(DESC_ITEM.match(l.strip()) for l in lines):
        return 'lines'
    numbered = sum(bool(re.match(r'^\s*(?:ch\.?\s*)?\d{1,3}\s*[-.):\t ]\s*\S', l, re.I)) for l in lines)
    if numbered >= 3 and numbered >= 0.5 * len(lines):
        return 'lines'
    if len(lines) >= 2 and not any(',' in l for l in lines) and _list_items(lines):
        return 'lines'
    items = [i for l in lines for i in COMMA_SPLIT.split(l.strip().rstrip('.')) if i.strip()]
    if len(items) >= 4 and any(',' in l or ';' in l for l in lines) and _list_items(items):
        return 'commas'
    return None


COMMA_SPLIT = re.compile(r'\s*[,;]\s*(?:and\s+)?|\s+and\s+(?=\S+$|\S+\s+\S+$)')   # "..., Hat and OH" -> Hat, OH


def plan_from(description=None, filename=None, data=None, text=None, max_inputs=None):
    """The editable channel plan for the page.

    An uploaded file or pasted list is the source of channels (the description only adds context
    for the classifier and the artist name). A description alone goes through the questionnaire, unless it is
    itself a pasted list. Returns {'channels', 'warnings', 'notes', 'source', 'answers', 'skipped',
    'title', 'stats', 'options'}. 'options' holds the option blocks the show asks for (options.suggest:
    {'fx': [{'kind'}], 'mixes': {'stereo', 'mono'}, 'role': 'mon'}) or None."""
    t0 = time.time()
    desc = (description or '').strip()
    out = {'channels': [], 'warnings': [], 'notes': [], 'source': None, 'answers': None, 'skipped': [],
           'title': None, 'stats': {}, 'options': None}
    listed = data is not None or bool((text or '').strip())
    kind = looks_like_list(desc) if not listed and desc else None
    if kind:
        # a pasted list: one channel per line (a comma list is split into lines first)
        text = '\n'.join(i.strip() for l in desc.splitlines() for i in COMMA_SPLIT.split(l.strip().rstrip('.'))
                         if i.strip()) if kind == 'commas' else desc
        listed, desc_is_list = True, True
    else:
        desc_is_list = False
    if listed:
        artist = guess_artist(filename) if filename else None
        p = parse_input_list(filename, data, text, artist=artist)
        out['warnings'] += p['warnings']
        out['notes'] += p['notes']
        out['skipped'] = p['skipped']
        out['stats']['parse'] = p['meta']
        if p['channels']:
            ctx = None if desc_is_list else (desc or None)
            out['channels'] = classify(p['channels'], artist=artist, description=ctx)
            out['stats']['classify'] = dict(classify.last_info)
            out['source'] = 'text-list' if desc_is_list or data is None else ('list+description' if desc else 'list')
            out['title'] = artist
            n_fb = sum(c['via'] == 'fallback' for c in out['channels'])
            if n_fb:
                out['notes'].append('%d channel%s had no sure match and got the closest template or none. Check the '
                                    'type column.' % (n_fb, '' if n_fb == 1 else 's'))
            ci = out['stats']['classify']
            if ci.get('asked') and ci.get('error'):
                out['notes'].append('The fast matcher did not answer (%s), so the name rules decided.' % ci['error'])
            if desc and not desc_is_list:
                added = additions_from(desc)
                if added:
                    n0 = len(out['channels'])
                    for k, ch in enumerate(added, start=n0 + 1):
                        ch['n'] = k
                    out['channels'] += added
                    _uniquify(out['channels'])
                    out['notes'].append('Added from your description, at the end of the list: %s.' % ', '.join(
                        '%s (%s)' % (c['name'], c['full_name']) for c in added))
                else:
                    out['notes'].append('Your description was read for context only. Add or remove channels in the '
                                        'table.')
        elif not desc:
            pass
        else:
            out['warnings'].append('Nothing usable in the list, so the description was used instead.')
    if not out['channels'] and desc and not desc_is_list:
        r = describe_to_channels(desc)
        out['channels'] = r['channels']
        out['answers'] = r['answers']
        out['source'] = 'description'
        out['stats']['describe'] = r['info']
        out['notes'].append('Read as a description of the show and built in house order. Check the counts. To use '
                            'your own list exactly, paste one channel per line.')
        if r['info'].get('dropped'):
            out['warnings'].append('Capped: %s. Add the rest in the table.' % '; '.join(r['info']['dropped']))
        if r['info'].get('jev_error') and r['info']['jev_error'] != 'disabled':
            out['notes'].append('The fast matcher did not answer, so only what the text says outright and the '
                                'style defaults were used.')
    if not out['channels'] and not out['warnings']:
        out['warnings'].append('Describe the show or add an input list.')
    if max_inputs and len(out['channels']) > max_inputs:
        out['warnings'].append('%d channels, but this console has %d inputs. Remove %d or pick a bigger console.' % (
            len(out['channels']), max_inputs, len(out['channels']) - max_inputs))
    # options the show asks for (IEM / wedge mixes, reverbs and delays, a monitor desk), from the description text
    # and the FX return rows of a list (options.suggest; never raises into the plan)
    try:
        from sessionmaker import options as _opts
        sug, note = _opts.suggest(None if desc_is_list else desc, out['channels'])
        if sug:
            out['options'] = sug
            if note:
                out['notes'].append(note)
    except Exception:  # noqa: BLE001 - suggestions are a convenience; the channel plan stands without them
        log.warning('option suggestions failed', exc_info=False)
    blank = [c for c in out['channels'] if not (c.get('name') or '').strip()]
    for c in blank:                  # nothing printable left (only emoji): the instrument's house name, else Ch N
        c['name'] = DEFAULT_NAMES.get(c.get('category')) or 'Ch %d' % c.get('n', 0)
    if blank:
        _uniquify(out['channels'])
    for c in out['channels']:
        c.pop('raw', None)
    out['stats']['ms'] = round((time.time() - t0) * 1000, 1)
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('usage: python3 -m sessionmaker.intake (LIST_FILE | "description" | -)')
        sys.exit(2)
    arg = sys.argv[1]
    if arg == '-':
        res = plan_from(text=sys.stdin.read())
    elif os.path.exists(arg):
        with open(arg, 'rb') as f:
            res = plan_from(filename=arg, data=f.read())
    else:
        res = plan_from(description=arg)
    for c in res['channels']:
        print('%3d %-8s %-2s %-18s %-8s %-5s %s' % (c['n'], c['name'], 'ST' if c['stereo'] else '', c['category'], c['via'],
                                                   '' if c['confidence'] is None else '%.2f' % c['confidence'],
                                                   c['full_name']))
    print(json.dumps({k: res[k] for k in ('source', 'warnings', 'notes', 'stats', 'title')}, indent=1))
