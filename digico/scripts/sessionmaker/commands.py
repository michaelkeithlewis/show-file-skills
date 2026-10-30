#!/usr/bin/env python3
"""commands.py - plain language -> DiGiCo Lite edit ops (the sessionmaker/edit.py contract).

    parse(text, model, use_jev=None) -> {'ops': [Op], 'summary': str, 'confidence': 0..1,
                                         'unrecognized': [phrase], 'examples': [3 commands, only when nothing parsed],
                                         'ask': [question], 'jev': {'calls', 'ms', 'used'}, 'ms': float}
    python3 -m sessionmaker.commands <model.json | file.ses> "hpf vox 120, gate the toms"     (from digico/scripts)

model is the Model of edit.open_session (the Session Checker readout, inspect.py, plus channel ids). parse() reads
channels (n, name, stereo, category if present, sends, patch, fader_db, muted, trim_db, polarity), auxes (n, name,
stereo, feeds_fx), groups (n, name), fx (n, name, kind, fed_by, returns_on), console.quantum and counts. Missing
fields are fine.

How a command is read:
  1. Clean the text (ASCII quotes, dashes), fix typos of the command words (difflib against VOCAB; channel-name words
     are never "fixed"), cut it into clauses at ; . then also, and at commas / "and" when the next words start a new
     action ("hpf vox 120, gate the toms" is two clauses, "gate the toms and the kick" is one).
  2. Each clause goes through the grammar recognizers in order (rename, mixes, buses, FX, add/remove channels, move,
     stereo, patch, preamp, sends and groups, templates, processing, faders and mutes, EQ recipes). The first one that
     reads the clause wins. Targets resolve against the model: channel numbers and ranges, "all"/"everything", exact
     channel names, instrument words (vocals, toms, OHs...) through the categories taxonomy.py gives the names,
     partial and close names, "except"/"but" exclusions. A clause without a target borrows the one next to it
     ("gate the toms and hpf them at 100").
  3. The optional classifier (intake.CLASSIFIER, not included; intake.jev_choices, p >= 0.6, SM_JEV=0 off) answers
     only what the grammar left open: the kind of edit for a clause nothing read, and the channel or group a target
     phrase means. Everything goes in one call, under JEV_BUDGET_S seconds. With no classifier set, step 3 is
     skipped.
  4. Anything still open is asked, never guessed: the clause lands in 'unrecognized' and 'ask' says what to type.

Targets are always resolved here: an op's target is {'all': True} or {'channels': [surface numbers]}, never a group
word, so edit.py and this file cannot disagree on what "the vocals" means. Ops in one command run in order, and the
channel numbers of a later op are the numbers after the earlier ops (add, remove, move and stereo pairs renumber;
parse() simulates that). Relative wishes ("more verb on the lead", "bring the tracks up 3") become absolute values per
channel from the model, one op per distinct result.

Op shapes (every field in display units, as the readout shows them):
  set        {'op': 'set', 'target', + one field}:
             'hpf' / 'lpf': {'on': bool, 'freq': Hz (optional)}
             'eq': {'band': 1-4, 'type': 'bell'|'low_shelf'|'high_shelf', 'freq', 'gain', 'q', 'on': True}  'eq_on': bool
             'gate': {'on', 'thr', 'range', 'attack', 'hold', 'release'} (dB, ms; only the keys the text gave)
             'comp': {'on', 'thr', 'ratio', 'attack', 'release', 'knee', 'makeup'}
             'mustard': {'on', 'model': classic|vca|fet|optical|levamp, 'thr', 'ratio', 'attack', 'release', 'out', 'mix' 0-1}
             'delay_ms' (0 = off), 'polarity' (True = inverted), 'trim_db', 'fader_db', 'mute', 'view': 'sd'|'mustard'
  rename     {'op': 'rename', 'target': {'channels': [n]}, 'name': str as typed (edit.py fits it to 8 characters)}
  name_bus   {'op': 'name_bus', 'bus': 'aux'|'group', 'n': int, 'name': str}
  stereo     {'op': 'stereo', 'target': {'channels': [a, b]}, 'on': True}  two adjacent mono channels -> one stereo
             {'op': 'stereo', 'target': {'channels': [n]}, 'on': True}     a mono channel made stereo
             {'op': 'stereo', 'target': {'channels': [n]}, 'on': False, 'split': bool}  split = two mono channels
  move       {'op': 'move', 'target': {'channels': [...]}, 'to': surface number the first moved channel ends up on}
  add_channels    {'op': 'add_channels', 'count': n, 'stereo': bool, 'names': [str], 'at': surface number | None (end)}
  remove_channels {'op': 'remove_channels', 'target'}
  apply_template  {'op': 'apply_template', 'target', 'category': template id | None (each channel's own)}
  send       {'op': 'send', 'target', 'aux': n, 'on': bool, + optional 'level_db', 'pre': 'pre'|'post', 'pan'}
             {'op': 'send', 'target', 'group': n, 'on': bool}       group routing (the Master is a group too)
  patch      {'op': 'patch', 'target', 'mode': 'rack'|'local'|'none', 'start': first socket | None}
  preamp     {'op': 'preamp', 'target', + 'gain_db' | 'phantom': bool | 'pad': bool}
  add_fx     {'op': 'add_fx', 'kind': options.FX_CHOICES key, 'feed_aux': n | None, 'return': 'auto' | n,
              'name': str | None, 'sends': 'auto' | 'target', 'target' (only with 'sends': 'target')}
  remove_fx  {'op': 'remove_fx', 'fx': unit number}
  mixes      {'op': 'mixes', + 'stereo': total IEM mixes and/or 'mono': total wedge mixes (a kind left out stays)}
  buses      {'op': 'buses', 'aux_mono', 'aux_stereo', 'grp_mono', 'grp_stereo'} | {'op': 'buses', 'auto': True}

"""
import difflib
import functools
import json
import os
import re
import sys
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sessionmaker import taxonomy as T

JEV_ACCEPT = 0.6
JEV_BUDGET_S = float(os.environ.get('SM_CMD_JEV_TIMEOUT', '1.5'))
MAX_TEXT = 2000
STEP_DB = 3.0
MIX_START_DB, FX_START_DB = -10.0, -5.0

VOCAB = sorted(set('''
mustard compressor compressors compression compress comp comps gate gates gating threshold ratio attack release
overheads overhead vocals vocal guitars guitar keyboards keys tracks talkback phantom polarity rename reverb verb
delay channels channel everything except stereo mono patch unpatch monitor mixes wedges wedge snare snares kick kicks
toms bass acoustic electric filter highpass lowpass shelf notch boost optical classic leveling fader faders unity mute
unmute aux auxes group groups template templates remove delete insert plate hall room slap chorus doubler thicken trim
gain preamp invert flip link pair move swap after before called named percussion audience crowd cymbals hihat drums
singer singers backing background harmony harmonies lead input inputs everyone mixer louder quieter release makeup
output return returns effects effect apply reset turn bring push pull lower raise engage bypass disable enable
'''.split()))
NUMW = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'twenty': 20,
        'twenty four': 24, 'thirty two': 32}

CANON = [(re.compile(p), r) for p, r in [
    (r'\bhigh[- ]?pass(?:ed|ing)?(?: filters?)?\b|\bhi[- ]?pass(?: filters?)?\b|\blow[- ]?cuts?\b|\blo[- ]?cuts?\b|'
     r'\broll[- ]?off\b|\bhp filters?\b|\bhpfs\b|\bhighpass\b|\bhi[- ]?pf\b', 'hpf'),
    (r'\blow[- ]?pass(?:ed|ing)?(?: filters?)?\b|\blo[- ]?pass(?: filters?)?\b|\bhigh[- ]?cuts?\b|\bhi[- ]?cuts?\b|'
     r'\btop[- ]?cut\b|\blp filters?\b|\blpfs\b|\blowpass\b', 'lpf'),
    (r'\bw/o\b', 'without'), (r'\bw/\s*', 'with '),
    (r'(?<![\w.])\+48(?:v|\b)|\b48 ?v(?:olts?)?\b|\bp48\b|\bphantom(?: power)?\b|\b48 volt\b', '48v'),
    (r'\bcompressors?\b|\bcompression\b|\bcompress(?:ed|ing|es)?\b|\bcomps\b|\bcompresser\b', 'comp'),
    (r'\bgates\b|\bgating\b', 'gate'),
    (r'\bmustard comp(?:ressor)?s?\b|\bmustards\b', 'mustard'),
    (r'\breverbs?\b|\bverbs\b|\brvb\b', 'verb'),
    (r'\bmilli ?seconds?\b|\bmsecs?\b', 'ms'), (r'\bdecibels?\b|\bdbs\b', 'db'),
    (r'\bkilo ?hertz\b|\bkhz\b', 'k'), (r'\bhertz\b', 'hz'),
    (r'\bminus\s+(?=\d)', '-'), (r'\bnegative\s+(?=\d)', '-'), (r'\bplus\s+(?=\d)', '+'),
    (r'\bchannels?\b|\bchans?\b|\bch\.', 'ch'), (r'\bch(\d)', r'ch \1'),
    (r'\bthrough\b|\bthru\b', 'thru'),
    (r'\bauxes\b|\bauxs\b|\bauxiliar(?:y|ies)\b', 'aux'),
    (r'\bin[- ]ears?\b|\biems\b', 'iem'),
    (r'\bpre[- ]fader\b|\bprefader\b', 'pre'), (r'\bpost[- ]fader\b|\bpostfader\b', 'post'),
    (r"\blet'?s\b|\bplease\b|\bpls\b|\bcan (?:you|we|i)\b|\bcould (?:you|we)\b|\bi (?:want|need|'d like)\b|"
     r"\bi would like\b|\bgo ahead and\b|\bgo ahead\b|\bfor me\b", ' '),
    (r'\bhi[- ]?hats?\b|\bhigh[- ]?hats?\b', 'hihat'),
    (r'\bover[- ]heads?\b', 'overheads'),
    (r'\bstereo[- ]link(?:ed)?\b', 'stereo link'),
]]
NUM_RX = re.compile(r'\b(%s)\b' % '|'.join(sorted(NUMW, key=len, reverse=True)))

ACTION_START = re.compile(
    r'^(?:then\s+|also\s+|and\s+)?(?:hpf|lpf|gate|comp|mustard|eq|boost|cut|notch|delay|flip|invert|polarity|mute|'
    r'unmute|rename|name|call|label|move|swap|add|insert|remove|delete|drop|kill|turn|set|put|use|make|give|send|'
    r'route|assign|patch|unpatch|repatch|48v|pad|gain|trim|fader|faders|pull|push|bring|raise|lower|link|unlink|pair|'
    r'split|apply|reset|more|less|take|bypass|engage|enable|disable|fet|vca|opto|optical|lose|ditch|get rid|'
    r'solo|throw|flatten|scoop|swap)\b')

VOCAL = {'lead_vocal', 'vocal_generic', 'vocal_fx_mic', 'vocal_ear_split', 'choir'}
DRUMS = {'kick_in', 'kick_out', 'kick_sub', 'snare_top', 'snare_bottom', 'hihat', 'rack_tom', 'floor_tom', 'roto_tom',
         'overheads', 'ride', 'drum_crotch', 'drum_trigger', 'sample_pad', 'hand_perc'}
KEYS = {'keys', 'piano', 'organ', 'synth'}
TRACKS = {'tracks_music', 'tracks_drums_perc', 'tracks_bass', 'tracks_vocals'}
FXRET = {'fx_reverb', 'fx_delay', 'fx_modulation', 'fx_other'}
INSTR = DRUMS | {'bass_di', 'bass_amp', 'synth_bass', 'electric_guitar', 'acoustic_guitar', 'folk_strings', 'strings',
                 'horns'} | KEYS
GROUPS = [
    ('lead', 'lead vocal', r'(?:the )?(?:lead|main|front)(?: (?:vocals?|vox|vx|singer|vocalist|voc|mic))?|lv|ld vox|'
                           r'(?:lead )?singer|vocalist|artist(?: vocal| vox| mic)?', {'lead_vocal'}),
    ('bgvs', 'backing vocals', r'bgvs?|bvs?|bv mics?|bgv mics?|b ?vox|backing (?:vocals?|vox|singers?|vocalists?|mics?)|'
                               r'background (?:vocals?|vox|singers?)|harmony (?:vocals?|vox|mics?)|harmonies|'
                               r'backups?|bg (?:vocals?|vox)|backing vox|other (?:vocals?|vox|singers)',
     lambda c: c.cat in VOCAL and c.cat != 'lead_vocal'),
    ('vocals', 'vocals', r'vocals?|vox|voxes|vocs?|vx|singers|vocal mics?|voices|mics? for (?:the )?singers|vocalists',
     VOCAL),
    ('drums', 'drums', r'drums?|kit|drum ?kit|drum mics?|drum channels?', DRUMS),
    ('kick', 'kick', r'kicks?|kik|kck|bd|bass ?drums?|kick drums?|kick mics?', {'kick_in', 'kick_out', 'kick_sub'}),
    ('snare', 'snare', r'snares?|snr|sn|snare mics?|snare drums?', {'snare_top', 'snare_bottom'}),
    ('toms', 'toms', r'toms?|tom mics?|tom toms?', {'rack_tom', 'floor_tom', 'roto_tom'}),
    ('rack_tom', 'rack toms', r'rack toms?|rack', {'rack_tom'}),
    ('floor_tom', 'floor toms', r'floor toms?|floors?|flr toms?', {'floor_tom'}),
    ('hihat', 'hi-hat', r'hats?|hh|hihat|hihats|hat mic', {'hihat'}),
    ('overheads', 'overheads', r'overheads?|ohs?|o ?h|cymbals?|cymbal mics?|overs', {'overheads', 'ride'}),
    ('bass', 'bass', r'bass(?:es)?|bass guitars?|bass channels?|bass ins?', {'bass_di', 'bass_amp', 'synth_bass'}),
    ('electric', 'electric guitars', r'electrics?|electric (?:guitars?|gtrs?)|egs?|e ?gtrs?|elec gtrs?|guitar amps?|'
                                     r'amps?|electric', {'electric_guitar'}),
    ('acoustic', 'acoustic guitars', r'acoustics?|acoustic (?:guitars?|gtrs?)|ac ?gtrs?|ags?|acus?|acos?',
     {'acoustic_guitar'}),
    ('guitars', 'guitars', r'guitars?|gtrs?|geetars?|gits?|guitar channels?',
     {'electric_guitar', 'acoustic_guitar', 'folk_strings'}),
    ('keys', 'keys', r'keys|keyboards?|keyboard|key channels?|ivories', KEYS),
    ('synth', 'synths', r'synths?|syns?', {'synth', 'synth_bass'}),
    ('piano', 'piano', r'pianos?|pno|grand', {'piano'}),
    ('organ', 'organ', r'organs?|b3|hammond', {'organ'}),
    ('tracks', 'tracks', r'tracks?|trax|trx|playback|stems?|pb|backing tracks?|loops|ableton|sequences?|tracks rig',
     TRACKS),
    ('click', 'click', r'clicks?|clk|metronome|click tracks?|click channels?', {'click'}),
    ('talkback', 'talkbacks', r'talk ?backs?|tbs?|talkback mics?|tb mics?|shout mics?', {'talkback', 'comms_radio'}),
    ('fx_returns', 'FX returns', r'(?:fx|effects?|verb|delay) returns?|returns|rtns?|fx rtns?|fx channels?|'
                                 r'effects channels?', FXRET),
    ('audience', 'audience mics', r'audience(?: mics?)?|crowd(?: mics?)?|aud|ambience mics?|amb(?: mics?)?|'
                                  r'ambient mics?', {'audience'}),
    ('horns', 'horns', r'horns?|brass|sax(?:es|ophones?)?|trumpets?|trombones?|tpts?|horn section', {'horns'}),
    ('strings', 'strings', r'strings|violins?|cellos?|violas?|fiddles?|string section', {'strings', 'folk_strings'}),
    ('choir', 'choir', r'choirs?|choir mics?', {'choir'}),
    ('perc', 'percussion', r'perc(?:ussion)?|percs|hand perc|shakers?|congas?|cajons?|bongos?', {'hand_perc'}),
    ('speech', 'speech mics', r'speech(?: mics?)?|pastor|host|mc|podium|lectern|lavs?|lavaliers?|presenters?|'
                              r'speakers? mics?', {'speech_mic'}),
    ('instruments', 'instruments', r'instruments?|the band|band (?:inputs?|channels?)|instrument channels?', INSTR),
    ('mono', 'mono channels', r'mono (?:ch|inputs?|ones|sources)', lambda c: not c.stereo),
    ('stereo', 'stereo channels', r'stereo (?:ch|inputs?|ones|sources)', lambda c: c.stereo),
]
GROUPS = [(k, lab, re.compile(r'^(?:%s)$' % rx), sel) for k, lab, rx, sel in GROUPS]
ALL_RX = re.compile(r'^(?:everything|every ?(?:thing|ch|input|one)|all(?: the)?(?: ch| inputs?| of (?:them|it|the ch|'
                    r'the inputs))?|all inputs|whole (?:session|desk|console|show)|the whole thing|across the board|'
                    r'everywhere|the lot|everything else|all of them|all sources)$')
TEMPLATE_OF_GROUP = {'lead': 'lead_vocal', 'bgvs': 'vocal_generic', 'vocals': 'vocal_generic', 'kick': 'kick_in',
                     'snare': 'snare_top', 'toms': 'rack_tom', 'rack_tom': 'rack_tom', 'floor_tom': 'floor_tom',
                     'hihat': 'hihat', 'overheads': 'overheads', 'bass': 'bass_di', 'electric': 'electric_guitar',
                     'acoustic': 'acoustic_guitar', 'guitars': 'electric_guitar', 'keys': 'keys', 'synth': 'synth',
                     'piano': 'piano', 'organ': 'organ', 'tracks': 'tracks_music', 'click': 'click',
                     'talkback': 'talkback', 'audience': 'audience', 'horns': 'horns', 'strings': 'strings',
                     'choir': 'choir', 'perc': 'hand_perc', 'speech': 'speech_mic', 'drums': None}

SEAT_WORDS = [
    (r'drummer|drums?|kit|drum mix', r'drum|kit|dr\b|dms'),
    (r'bass(?:ist| player)?|bass mix', r'bass|\bbs\b|\bbg\b'),
    (r'guitar(?:ist| player)?s?|gtr|guitar mix|eg', r'gtr|guitar|\beg\b|git'),
    (r'acoustic(?: player)?|ag', r'\bac|acou|\bag\b'),
    (r'keys(?: player)?|keyboard(?:ist| player)?|key player|pianist|md', r'key|kbd|pno|piano|md\b'),
    (r'(?:lead )?singer|lead(?: singer| vocal(?:ist)?| vox)?|vocalist|artist|lv|front ?man|front ?woman',
     r'lead|\blv\b|vox|vocal|singer|artist'),
    (r'bgvs?|backing (?:vocals?|singers?)|bv', r'bgv|\bbv|backing|harm'),
    (r'perc(?:ussion|ussionist)?', r'perc'),
    (r'horns?|brass|sax', r'horn|brass|sax|tpt'),
    (r'wedges?|the wedge', r'wedge|wdg|mon\b'),
    (r'tech|techs|crew|stage manager|sm', r'tech|crew|\bsm\b'),
]
SEAT_WORDS = [(re.compile(r'^(?:the )?(?:%s)$' % a), re.compile(b)) for a, b in SEAT_WORDS]
MIXWORD = r'(?:mix(?:es)?|ears?|iems?|in ?ears?|wedges?|monitors?|mons?|aux)'

FX_KIND_WORDS = [
    (r'vocal plate|vox plate|vocal verb', 'vocal plate'), (r'drum plate', 'drum plate'),
    (r'gated verb|gate verb|gated|non ?-?lin(?:ear)?', 'gated'), (r'drum verb|drum room|room verb|room', 'room'),
    (r'hall verb|hall|cathedral|church', 'hall'), (r'plate verb|plate', 'plate'),
    (r'slap ?back|slap delay|slap', 'slap'),
    (r'tape delay|tap delay|quarter note delay|eighth note delay|delay|echo|dly', 'delay'),
    (r'chorus', 'chorus'), (r'thicken(?:er)?|doubler|double|adt|harmoni[sz]er', 'thicken'),
    (r'verb', None),
]
FX_KIND_WORDS = [(re.compile(r'\b(?:%s)\b' % a), b) for a, b in FX_KIND_WORDS]
FX_ANY = re.compile(r'\b(?:verb|plate|hall|room|slap ?back|slap|delay|echo|dly|chorus|thicken(?:er)?|doubler|adt|'
                    r'gated verb|non ?-?lin|cathedral|fx|effects?)\b')
FX_KIND_OF_MODEL = {'reverb': ('verb',), 'delay': ('delay', 'echo', 'slap', 'dly'), 'chorus': ('chorus',),
                    'pitch': ('thicken', 'doubler', 'adt', 'double'), 'special': ()}

MUSTARD_MODELS = [(r'\bfet\b|\b1176\b|\bfet comp', 'fet'), (r'\bvca\b|\bssl\b|\bdbx\b|\bbus comp\b', 'vca'),
                  (r'\bopto\b|\boptical\b|\bla ?-?2 ?a\b|\bla2a\b', 'optical'),
                  (r'\blev ?amp\b|\blevell?ing amp(?:lifier)?\b|\blevamp\b', 'levamp'), (r'\bclassic\b', 'classic')]
MUSTARD_MODELS = [(re.compile(a), b) for a, b in MUSTARD_MODELS]

RECIPES = [
    (r'boom(?:y|iness)|too much (?:low|bottom)(?: end)?|less (?:low|bottom)(?: end)?|less boom', 250, -3.0, 'bell', 1.4),
    (r'mudd?(?:y|iness)?|less mud|cloudy', 350, -3.0, 'bell', 1.4),
    (r'box(?:y|iness)|cardboard', 600, -3.0, 'bell', 1.4),
    (r'honk(?:y)?|nasal|less nose', 1000, -3.0, 'bell', 1.4),
    (r'harsh(?:ness)?|brittle|edgy|piercing|ice ?picky?|too bright', 3000, -3.0, 'bell', 1.4),
    (r'sibilan(?:t|ce)|ess(?:y|es)|too much s', 7000, -3.0, 'bell', 2.0),
    (r'more (?:air|sparkle|shimmer|top(?: end)?)|airy|airier|dull|dark|needs? (?:air|top)', 10000, 3.0, 'high_shelf', 0.85),
    (r'more (?:presence|bite|cut|clarity|definition)|cut through|clearer|more articulate', 4000, 3.0, 'bell', 1.0),
    (r'more (?:beater|attack|click|knock|snap|crack)', 4000, 3.0, 'bell', 1.4),
    (r'more (?:low|bottom|low end|weight|thump|oomph|boom|body|warmth)|thin|warmer|fatter|beef(?:y|ier)? ?(?:it )?up',
     120, 3.0, 'bell', 1.0),
]
RECIPES = [(re.compile(r'\b(?:%s)\b' % a), f, g, ty, q) for a, f, g, ty, q in RECIPES]

INTENTS = {
    'hpf': 'Turn on, move or remove the high-pass filter (low cut) on channels',
    'lpf': 'Turn on, move or remove the low-pass filter (high cut) on channels',
    'eq': 'Change the EQ of channels (boost or cut a frequency, shelf, notch, less boomy, more air)',
    'gate': 'Add, change or remove a noise gate on channels',
    'comp': 'Add, change or remove the compressor on channels (threshold, ratio, squash)',
    'mustard': 'Use a Mustard processing compressor model (classic, VCA, FET, optical, leveling amp) on channels',
    'fader': 'Change the fader level of channels (louder, quieter, turn up or down, unity)',
    'mute': 'Mute or unmute channels',
    'send_fx': 'Change how much of a channel goes to a reverb or delay effect (more or less verb, slap, echo)',
    'send_mix': 'Change how much of a channel a musician hears in their monitor mix or in-ear mix',
    'route_group': 'Route channels to a group or subgroup, or take them out of one or out of the PA',
    'rename': 'Rename a channel, aux or group',
    'stereo': 'Make two channels one stereo pair, make a channel stereo, or split a stereo channel',
    'move': 'Move channels to another position on the console (reorder)',
    'add_channels': 'Add new input channels',
    'remove_channels': 'Delete input channels from the session',
    'add_fx': 'Add a new reverb, delay or other effect unit',
    'remove_fx': 'Delete an effect unit',
    'mixes': 'Set how many monitor mixes the session has (IEM mixes or wedge mixes for the players)',
    'patch': 'Patch channels to stage rack or local inputs, or unpatch them',
    'phantom': 'Turn 48V phantom power on or off',
    'gain': 'Change the analog preamp gain',
    'delay_polarity': 'Delay a channel in time (milliseconds) or flip its polarity or phase',
    'template': 'Apply the starting-point processing template to channels',
    'vague': 'A wish about the sound with no clear console setting (make it better, fix it, sounds bad)',
    'not_edit': 'A question or remark that asks for no change to the session',
}
ASK_FOR = {
    'hpf': 'Say where, like "hpf the vocals at 120".', 'lpf': 'Say where, like "lpf the bass at 5k".',
    'eq': 'Say the move, like "cut 3 dB at 400 on the kick".', 'gate': 'Say which channels, like "gate the toms".',
    'comp': 'Say which channels, like "comp the bass 4:1 at -20".',
    'mustard': 'Say which channels, like "Mustard FET on the kick in".',
    'fader': 'Say how much, like "bring the tracks up 3".', 'mute': 'Say which channels, like "mute the click".',
    'send_fx': 'Say which effect and channels, like "more verb on the lead".',
    'send_mix': 'Say whose mix and what, like "more click in the drums mix".',
    'route_group': 'Say which group, like "drums to group 1".', 'rename': 'Say it like "rename 12 to Keys L".',
    'stereo': 'Say which channels, like "make 15 and 16 a stereo pair".', 'move': 'Say it like "move 12 to 1".',
    'add_channels': 'Say it like "add 2 channels after 12".', 'remove_channels': 'Say it like "delete 26".',
    'add_fx': 'Say it like "add a hall on aux 5".', 'remove_fx': 'Say which effect, like "remove FX 2".',
    'mixes': 'Say it like "8 IEM mixes" or "4 wedges".', 'patch': 'Say it like "patch 1-24 to the rack from 1".',
    'phantom': 'Say which channels, like "48v on the overheads".', 'gain': 'Say how much, like "gain 30 on the vox".',
    'delay_polarity': 'Say it like "delay the OH 2 ms" or "flip polarity on the snare bottom".',
    'template': 'Say it like "apply the templates to everything".',
}



def _ascii(s):
    s = str(s or '').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    s = s.replace('–', '-').replace('—', ', ').replace('−', '-').replace(' ', ' ')
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[ \t]+', ' ', re.sub(r'[^\x20-\x7e\n]', ' ', s)).strip()


def _split_camel(name):
    """'SnareTop' -> 'Snare Top', 'VoxPlate' -> 'Vox Plate' (8-character console names squeeze the spaces out)."""
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name or '')


def _norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


@functools.lru_cache(maxsize=4096)
def _category(display, stereo):
    try:
        cat, p, _ = T.rule_category(display, stereo=stereo)
        return cat, p
    except Exception:
        return 'other', 0.0


class Ch:
    __slots__ = ('n', 'name', 'disp', 'norm', 'squash', 'toks', 'stereo', 'cat', 'p', 'raw')

    def __init__(self, n, name, stereo, cat, p, raw):
        self.n, self.name, self.stereo, self.cat, self.p, self.raw = n, name, stereo, cat, p, raw
        self.disp = _split_camel(name)
        self.norm = _norm(self.disp)
        self.squash = self.norm.replace(' ', '')
        self.toks = self.norm.split()


class Index:
    """The model as parse() needs it: channels with categories, auxes with what they are, groups, FX units."""

    def __init__(self, model):
        self.model = model or {}
        fx_ret = {}
        self.fx = []
        for u in self.model.get('fx') or []:
            aux = None
            for f in u.get('fed_by') or []:
                m = re.match(r'Aux (\d+)', str(f))
                if m:
                    aux = int(m.group(1))
            ent = {'n': u.get('n'), 'name': u.get('name') or '', 'kind': u.get('kind') or 'other', 'aux': aux,
                   'returns_on': list(u.get('returns_on') or [])}
            self.fx.append(ent)
            for r in ent['returns_on']:
                fx_ret[r] = ent['kind']
        self.chans = []
        for c in self.model.get('channels') or []:
            try:
                n = int(c.get('n'))
            except (TypeError, ValueError):
                continue
            name, st = str(c.get('name') or ''), bool(c.get('stereo'))
            cat, p = c.get('category'), 1.0
            if n in fx_ret:
                cat = {'reverb': 'fx_reverb', 'delay': 'fx_delay', 'chorus': 'fx_modulation',
                       'pitch': 'fx_modulation'}.get(fx_ret[n], 'fx_other')
            elif not cat:
                cat, p = _category(_split_camel(name), st)
            self.chans.append(Ch(n, name, st, cat, p, c))
        self.chans.sort(key=lambda c: c.n)
        self.by_n = {c.n: c for c in self.chans}
        self.count = len(self.chans)
        self.auxes = []
        for a in self.model.get('auxes') or []:
            try:
                an = int(a.get('n'))
            except (TypeError, ValueError):
                continue
            feeds = list(a.get('feeds_fx') or [])
            nm = str(a.get('name') or '')
            kinds = [u['kind'] for u in self.fx if u['n'] in feeds or u['aux'] == an]
            self.auxes.append({'n': an, 'name': nm, 'norm': _norm(_split_camel(nm)), 'stereo': bool(a.get('stereo')),
                               'fx': kinds, 'fx_names': [u['name'] for u in self.fx if u['aux'] == an],
                               'default': re.fullmatch(r'aux ?\d+', nm.strip().lower()) is not None})
        self.aux_by_n = {a['n']: a for a in self.auxes}
        self.groups = []
        for g in self.model.get('groups') or []:
            try:
                self.groups.append({'n': int(g.get('n')), 'name': str(g.get('name') or ''),
                                    'norm': _norm(_split_camel(str(g.get('name') or '')))})
            except (TypeError, ValueError):
                continue
        con = self.model.get('console') or {}
        self.quantum = bool(con.get('quantum'))
        self.name_words = set(w for c in self.chans for w in c.toks) | set(
            w for a in self.auxes for w in a['norm'].split()) | set(w for g in self.groups for w in g['norm'].split())

    def chan_list(self, ns):
        return [self.by_n[n] for n in ns if n in self.by_n]

    def sends(self, n):
        c = self.by_n.get(n)
        out = {}
        for s in (c.raw.get('sends') if c else None) or []:
            try:
                out[int(s.get('aux'))] = s
            except (TypeError, ValueError):
                continue
        return out

    def mix_auxes(self):
        return [a for a in self.auxes if not a['fx'] and not a['default']]

    def master(self):
        for g in self.groups:
            if re.search(r'\b(master|main|mains|lr|l r|pa)\b', g['norm']):
                return g['n']
        return None


_IX_CACHE = {}


def index(model):
    key = id(model)
    hit = _IX_CACHE.get(key)
    if hit is not None and hit[0] is model:
        return hit[1]
    ix = Index(model)
    if len(_IX_CACHE) > 16:
        _IX_CACHE.clear()
    _IX_CACHE[key] = (model, ix)
    return ix


STOP_EDGE = re.compile(r'^(?:(?:the|a|an|on|to|at|for|in|into|of|my|our|your|his|her|their|just|also|with|from|'
                       r'across|onto|its|is|are|and|both|each|those|these|them|it|that|this|some|any|only|over|up|'
                       r'down|out|off|now|then|too|as well|please|by|via)\s+)+|(?:\s+(?:the|a|an|on|to|at|for|in|of|'
                       r'and|too|as well|please|now|then|also|both|each|please|only|channels?|ch|inputs?|'
                       r'mics?|again))+$')
EXCEPT = re.compile(r'\s*\b(?:except(?: for)?|but(?: not)?|other than|apart from|excluding|minus|save for|besides|'
                    r'not including|leave out|leaving out|not)\b\s*')
SPLIT_PARTS = re.compile(r'\s*(?:,|\band\b|&|\+|\bplus\b|/|\bor\b)\s*')
PRONOUN = re.compile(r'^(?:them|it|those|these|that|this|same|the same(?: ones?)?|those ones|these ones|em|\'em)$')


class Target:
    def __init__(self):
        self.chans, self.all, self.labels, self.conf = [], False, [], 1.0
        self.missing, self.notes, self.pronoun, self.excluded = [], [], False, []

    @property
    def empty(self):
        return not self.all and not self.chans

    def selector(self, ix):
        if self.all and not self.excluded:
            return {'all': True}
        return {'channels': sorted(set(self.chans))}

    def ns(self, ix):
        return [c.n for c in ix.chans] if (self.all and not self.excluded) else sorted(set(self.chans))


def _clean_part(p):
    p = re.sub(r"'s\b", '', p.strip())
    for _ in range(3):
        q = STOP_EDGE.sub('', p).strip(' ,.-')
        if q == p:
            break
        p = q
    return re.sub(r'^(?:all|every|each|both)\s+(?:the\s+|of the\s+)?', '', p).strip()


def _num_part(p, ix):
    """'12', 'ch 12', '1-8', '1 thru 8', '1 to 8', '9 10' -> [numbers] or None."""
    q = re.sub(r'^(?:ch|input|inputs|#|no\.?|number)\s*', '', p).strip()
    m = re.fullmatch(r'(\d{1,3})\s*(?:-|thru|to|\.\.)\s*(?:ch\s*)?(\d{1,3})', q)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            a, b = b, a
        return list(range(a, b + 1))
    if re.fullmatch(r'\d{1,3}(?:\s+\d{1,3})*', q):
        return [int(x) for x in q.split()]
    return None


def _group_match(part, ix):
    for key, lab, rx, sel in GROUPS:
        if rx.match(part):
            if callable(sel):
                chans = [c.n for c in ix.chans if sel(c)]
            else:
                chans = [c.n for c in ix.chans if c.cat in sel]
            if key == 'fx_returns':
                chans = sorted(set(chans) | {n for u in ix.fx for n in u['returns_on'] if n in ix.by_n})
            return key, lab, chans
    return None


def _name_match(part, ix):
    """Channels whose name is the part (exact), else whose name words start with every part word."""
    np_ = _norm(part)
    if not np_:
        return [], 0.0
    sq = np_.replace(' ', '')
    exact = [c.n for c in ix.chans if c.norm == np_ or c.squash == sq or _norm(c.name) == np_]
    if exact:
        return exact, 1.0
    words = np_.split()
    hits = [c.n for c in ix.chans if all(any(t.startswith(w) for t in c.toks) for w in words)]
    if hits and (len(words) > 1 or len(words[0]) >= 2):
        return hits, 0.9
    return [], 0.0


def _fuzzy(part, ix):
    np_ = _norm(part)
    if len(np_) < 3:
        return []
    names = {c.norm: c.n for c in ix.chans}
    best = difflib.get_close_matches(np_, list(names), n=3, cutoff=0.78)
    return [names[b] for b in best]


def resolve_target(phrase, ix, allow_all=True):
    """A target phrase -> Target. Unresolved parts land in .missing (the classifier or a question settles them)."""
    tg = Target()
    ph = re.sub(r'\s+', ' ', (phrase or '').strip(' ,.'))
    if not ph:
        return tg
    base, excl = ph, ''
    m = EXCEPT.search(' ' + ph + ' ')
    if m:
        cut = ' ' + ph + ' '
        base, excl = cut[:m.start()].strip(), cut[m.end():].strip()
    b = _clean_part(base)
    if PRONOUN.match(b):
        tg.pronoun = True
        b = ''
    if ALL_RX.match(b) or (not b and excl):
        if allow_all:
            tg.all = True
            tg.labels.append('every channel')
    elif b:
        _resolve_parts(b, ix, tg)
    if excl:
        ex = Target()
        _resolve_parts(_clean_part(excl), ix, ex)
        if ex.missing:
            tg.missing += ex.missing
        drop = set(ex.chans)
        if tg.all:
            tg.chans = [c.n for c in ix.chans if c.n not in drop]
            tg.excluded = sorted(drop)
        else:
            tg.chans = [n for n in tg.chans if n not in drop]
            tg.excluded = sorted(drop)
        tg.labels.append('except ' + ', '.join(ex.labels))
    return tg


def _resolve_parts(text, ix, tg):
    full, p = _name_match(text, ix)
    if full and p >= 1.0:
        tg.chans += full
        tg.labels.append(_names(ix, full))
        return
    nums = _num_list(text, ix)
    if nums is not None:
        _add_nums(nums, ix, tg)
        return
    for part in SPLIT_PARTS.split(text):
        part = _clean_part(part)
        if not part:
            continue
        if PRONOUN.match(part):
            tg.pronoun = True
            continue
        if ALL_RX.match(part):
            tg.all = True
            tg.labels.append('every channel')
            continue
        nums = _num_part(part, ix)
        if nums is not None:
            _add_nums(nums, ix, tg)
            continue
        hits, p = _name_match(part, ix)
        if hits and p >= 1.0:
            tg.chans += hits
            tg.labels.append(_names(ix, hits))
            continue
        g = _group_match(part, ix)
        if g:
            key, lab, chans = g
            if not chans:
                tg.notes.append('This session has no %s.' % lab)
                tg.missing.append(part)
                continue
            tg.chans += chans
            tg.labels.append('the ' + lab if not lab.startswith('every') else lab)
            continue
        if hits:
            tg.chans += hits
            tg.labels.append(_names(ix, hits))
            tg.conf = min(tg.conf, 0.9)
            continue
        fz = _fuzzy(part, ix)
        if len(fz) == 1:
            tg.chans += fz
            tg.labels.append(_names(ix, fz))
            tg.conf = min(tg.conf, 0.8)
            continue
        tg.missing.append(part)


def _num_list(text, ix):
    """'1-8 and 12', '9, 10 & 11', 'ch 3 thru 6' -> numbers, or None when the text holds words."""
    q = re.sub(r'\b(?:ch|input|inputs|#)\s*', ' ', text)
    if not re.fullmatch(r'[\d\s,&+/-]*(?:(?:and|thru|to|\.\.)[\d\s,&+/-]*)*', q.strip()):
        return None
    out = []
    for m in re.finditer(r'(\d{1,3})(?:\s*(?:-|thru|to|\.\.)\s*(\d{1,3}))?', q):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a > b:
            a, b = b, a
        out += list(range(a, b + 1))
    return out or None


def _add_nums(nums, ix, tg):
    bad = [n for n in nums if n not in ix.by_n]
    good = [n for n in nums if n in ix.by_n]
    if bad:
        tg.notes.append('There is no channel %s (the session has %d).' % (_numtext(bad), ix.count))
        tg.missing.append(_numtext(bad))
    tg.chans += good
    if good:
        tg.labels.append(_names(ix, good))


def _numtext(ns):
    ns = sorted(set(ns))
    runs, i = [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        runs.append(str(ns[i]) if i == j else ('%d, %d' % (ns[i], ns[j]) if j == i + 1 else '%d-%d' % (ns[i], ns[j])))
        i = j + 1
    return ', '.join(runs)


def _names(ix, ns, limit=5):
    ns = sorted(set(ns))
    if ix.count and len(ns) == ix.count:
        return 'every channel'
    if len(ns) <= limit:
        items = ['%s (%d)' % (ix.by_n[n].name, n) if n in ix.by_n else str(n) for n in ns]
        return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]
    return '%d channels (%s)' % (len(ns), _numtext(ns))


FREQ_UNIT = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(k|hz)(\d)?(?![a-z])')
AT_NUM = re.compile(r'\b(?:at|@|to|around|about|near|=)\s*(\d+(?:\.\d+)?)(?![\d.]|\s*(?:db|ms|%|:|to 1|-))')
DB_RX = re.compile(r'(?<![\w.])([+-]?\d+(?:\.\d+)?)\s*db\b')
MS_RX = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(ms|s|sec|secs|seconds?)\b')
PCT_RX = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|percent|pct)')
RATIO_RX = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(?::|to)\s*1(?![\d.])|\bratio\s*(?:of\s*|at\s*|to\s*)?'
                      r'(\d+(?:\.\d+)?)')
BARE_RX = re.compile(r'(?<![\w.])([+-]?\d+(?:\.\d+)?)(?![\w.]|\s*(?::|%))')
SIGNED_RX = re.compile(r'(?<![\w.])([+-]\d+(?:\.\d+)?)(?![\w.])')


def _freq_val(m):
    v = float(m.group(1))
    if m.group(2) == 'k':
        v *= 1000.0
        if m.group(3):
            v += float(m.group(3)) * 100.0
    return v


class Clause:
    """One clause. raw keeps the case (names), t is the canonical lower-case text, w is t with used spans blanked."""

    def __init__(self, raw, t):
        self.raw, self.t, self.w = raw, t, t
        self.fixes = 0

    def take(self, rx):
        m = rx.search(self.w)
        if m:
            self.w = self.w[:m.start()] + ' ' * (m.end() - m.start()) + self.w[m.end():]
        return m

    def take_all(self, rx):
        out = []
        while True:
            m = self.take(rx)
            if not m:
                return out
            out.append(m)

    def has(self, rx):
        return rx.search(self.w) is not None

    def blank(self, words):
        """Blank whole words (regex alternatives) wherever they stand."""
        self.w = re.sub(r'\b(?:%s)\b' % words, lambda m: ' ' * len(m.group(0)), self.w)

    def left(self):
        return re.sub(r'\s+', ' ', self.w).strip(' ,.')


def _w(p):
    return re.compile(p)


class R:
    """What a recognizer read: ops (target filled later when it needs one), a question, a confidence."""

    def __init__(self, kind, ops=None, ask=None, conf=0.95, target=None, need_target=False, intent=None):
        self.kind, self.ops, self.ask, self.conf = kind, ops or [], ask, conf
        self.target, self.need_target, self.intent = target, need_target, intent
        self.make = None
        self.tphrase = ''


def _ok(ops, conf=0.95, kind='op'):
    return R(kind, ops=ops, conf=conf)


def _ask(text, intent=None):
    return R('ask', ask=text, conf=0.0, intent=intent)


def _with_target(C, ix, make, kind='set', conf=0.95, allow_all=True):
    """A result whose ops are built once the clause's leftover words resolve to channels."""
    r = R(kind, conf=conf)
    r.tphrase = C.left()
    r.target = resolve_target(r.tphrase, ix, allow_all=allow_all)
    r.make = make
    return r


OFF_RX = re.compile(r'\b(?:off|kill|killing|remove|removing|no|bypass|bypassed|disable|disabled|lose|ditch|drop|'
                    r'take (?:out|off|away)|get rid of|turn off|switch off|without|delete|clear|out|disengage|'
                    r'strip|nix|zap|scrap|pull)\b')


def _onoff(C, default=True):
    if C.has(OFF_RX):
        C.take_all(OFF_RX)
        return False
    return default


def rec_rename(raw, C, ix, ctx):
    """'rename 12 to Keys L', 'name 14 Vox Gst', 'call aux 3 Jamie', 'rename Kick In to Kick', '12 is called X'."""
    s = raw.strip()
    m = re.match(r'(?i)^(?:re-?name|name|call|label|title|retitle)\s+(?P<rest>.+)$', s) or \
        re.match(r'(?i)^(?:change|set|update)\s+(?:the\s+)?name\s+(?:of|on|for)\s+(?P<rest>.+)$', s)
    if not m:
        m2 = re.match(r'(?i)^(?:ch(?:annel)?\.?\s*)?(?P<n>\d{1,3})\s+(?:should be|is now|becomes|is)\s+(?:called|named)'
                      r'\s+(?P<name>.+)$', s) or \
            re.match(r'(?i)^(?:ch(?:annel)?\.?\s*)?(?P<n>\d{1,3})\s*(?:=|->)\s*(?P<name>.+)$', s)
        if not m2:
            return None
        return _rename_one(m2.group('n'), m2.group('name'), ix)
    rest = m.group('rest').strip()
    multi = re.findall(r'(?i)(?:^|,|\band\b)\s*(?:ch(?:annel)?\.?\s*)?(\d{1,3})\s+(?:to\s+|as\s+)?(.+?)\s*(?=(?:,|\band\b)'
                       r'\s*(?:ch(?:annel)?\.?\s*)?\d{1,3}\s|$)', rest)
    if len(multi) > 1:
        ops, conf = [], 0.95
        for n, nm in multi:
            r = _rename_one(n, nm, ix)
            if r.kind == 'ask':
                return r
            ops += r.ops
        return _ok(ops, conf, 'rename')
    bm = re.match(r'(?i)^(?:the\s+)?(?P<kind>aux|auxiliary|mix|group|grp|sub ?group|vca|fx|effect)\s*(?P<n>\d{1,3})\s+'
                  r'(?:to\s+|as\s+|=\s*)?(?P<name>.+)$', rest)
    if bm:
        return _rename_bus(bm.group('kind'), int(bm.group('n')), bm.group('name'), ix)
    tm = re.match(r'(?i)^(?P<tgt>.+?)\s+(?:to|as|=|->|:)\s+(?P<name>.+)$', rest)
    if tm:
        tgt, name = tm.group('tgt'), tm.group('name')
    else:
        tm = re.match(r'(?i)^(?:ch(?:annel)?\.?\s*)?(?P<tgt>\d{1,3})\s+(?P<name>.+)$', rest)
        if not tm:
            return _ask('Say the new name, like "rename 12 to Keys L".', 'rename')
        tgt, name = tm.group('tgt'), tm.group('name')
    bus = _bus_by_phrase(tgt, ix)
    if bus:
        return _rename_bus(bus[0], bus[1], name, ix)
    t = resolve_target(_canon(tgt.lower()), ix, allow_all=False)
    if t.missing or t.empty:
        return _ask('I could not find "%s" in this session. Say the channel number, like "rename 12 to %s".' % (
            tgt.strip(), _clean_name(name)), 'rename')
    if len(set(t.chans)) != 1:
        return _ask('"%s" is %s. Rename one channel at a time, like "rename %d to %s".' % (
            tgt.strip(), _names(ix, t.chans), t.chans[0], _clean_name(name)), 'rename')
    return _rename_one(str(t.chans[0]), name, ix)


def _clean_name(nm):
    nm = _ascii(nm).strip().strip('.').strip()
    if len(nm) >= 2 and nm[0] == nm[-1] and nm[0] in '"\'':
        nm = nm[1:-1].strip()
    return nm


def _rename_one(n, name, ix):
    n = int(n)
    nm = _clean_name(name)
    if n not in ix.by_n:
        return _ask('There is no channel %d (the session has %d).' % (n, ix.count), 'rename')
    if not nm:
        return _ask('Say the new name for channel %d.' % n, 'rename')
    return _ok([{'op': 'rename', 'target': {'channels': [n]}, 'name': nm}], 0.95, 'rename')


def _rename_bus(kind, n, name, ix):
    kind = kind.lower()
    nm = _clean_name(name)
    if kind in ('fx', 'effect'):
        return _ask('FX units keep their preset names here. Rename the aux that feeds it instead.', 'rename')
    if kind in ('vca',):
        return _ask('Control groups are not editable here yet.', 'rename')
    b = 'aux' if kind in ('aux', 'auxiliary', 'mix') else 'group'
    have = ix.aux_by_n if b == 'aux' else {g['n']: g for g in ix.groups}
    if n not in have:
        return _ask('There is no %s %d (the session has %d).' % (b, n, len(have)), 'rename')
    if not nm:
        return _ask('Say the new name for %s %d.' % (b, n), 'rename')
    return _ok([{'op': 'name_bus', 'bus': b, 'n': n, 'name': nm}], 0.95, 'rename')


def _bus_by_phrase(p, ix):
    """'the drums mix', 'Jamie's ears', 'aux 5', 'group 1', 'the Hall aux' -> ('aux'|'group', n) or None."""
    q = _canon(p.lower()).strip()
    m = re.fullmatch(r"(?:the\s+)?(aux|mix|group|grp|sub ?group)\s*(\d{1,3})", q)
    if m:
        return ('aux' if m.group(1) in ('aux', 'mix') else 'group', int(m.group(2)))
    m = re.fullmatch(r"(?:the\s+)?(.+?)(?:'s)?\s+(%s|group|grp)" % MIXWORD, q)
    if m:
        if m.group(2) in ('group', 'grp'):
            g = [x['n'] for x in ix.groups if x['norm'] == _norm(m.group(1))]
            return ('group', g[0]) if len(g) == 1 else None
        a = _aux_by_who(m.group(1), ix)
        return ('aux', a[0]) if len(a) == 1 else None
    return None


def _aux_by_who(who, ix, mixes_only=False):
    """Auxes a phrase names: a name, a player ("the drummer"), 'everyone', a number. -> [n]."""
    w = re.sub(r"'s\b|\bs'$", '', _norm(who)).strip()
    w = re.sub(r'^(?:the|my|his|her|their|our)\s+', '', w)
    w = re.sub(r'\s+(?:mix(?:es)?|ears?|iems?|in ?ears?|wedges?|monitors?|mons?|aux)$', '', w).strip()
    pool = ix.mix_auxes() if mixes_only else ix.auxes
    if not w:
        return []
    m = re.fullmatch(r'(?:aux|mix)?\s*(\d{1,3})', w)
    if m:
        n = int(m.group(1))
        return [n] if n in ix.aux_by_n else []
    if re.fullmatch(r'every ?(?:one|body)|all(?: the)?(?: mixes| ears| iems| monitors| wedges| band| players)?|'
                    r'all of them|the band|everyone else|all mixes', w):
        return [a['n'] for a in ix.mix_auxes()]
    exact = [a['n'] for a in pool if a['norm'] == w]
    if exact:
        return exact
    part = [a['n'] for a in pool if a['norm'] and all(re.search(r'\b' + re.escape(x), a['norm']) for x in w.split())]
    if part:
        return part
    for who_rx, aux_rx in SEAT_WORDS:
        if who_rx.match(w):
            hits = [a['n'] for a in ix.mix_auxes() if aux_rx.search(a['norm'])]
            if hits:
                return hits
    return []


N_ = r'(\d{1,2})'


def rec_mixes(raw, C, ix, ctx):
    t = C.t
    if not re.search(r'\b(?:iem|ears?|wedges?|monitor|mon|mixes|mix)\b', t):
        return None
    if re.search(r'\b(?:in|into|to|from|out of)\s+(?:the\s+)?\S+(?:\'s)?\s+(?:mix|ears?|iem|wedge|monitor)', t) and \
            not re.search(r'\b\d+\s+(?:stereo\s+)?(?:iem|wedge)', t):
        return None
    more = re.search(r'\b(?:add|another|more|extra)\b', t)
    st = mo = None
    m = re.search(r'\b(?:iem|ear) ?(?:mix(?:es)?\s+)?for\s+(?:the\s+|all\s+|our\s+)?' + N_ + r'\b', t) or \
        re.search(r'\b' + N_ + r'\s+(?:more\s+|extra\s+)?(?:stereo\s+)?(?:iem|ears?)(?:\s+mix(?:es)?)?\b', t) or \
        re.search(r'\b' + N_ + r'\s+(?:more\s+|extra\s+)?stereo\s+(?:monitor\s+)?mix(?:es)?\b', t)
    if m:
        st = int(m.group(1))
    w = re.search(r'\b' + N_ + r'\s+(?:more\s+|extra\s+)?(?:mono\s+)?(?:monitor\s+)?(?:wedges?|wedge mix(?:es)?|'
                                 r'mono (?:monitor )?mix(?:es)?)\b', t) or \
        re.search(r'\bwedges?\s+(?:mix(?:es)?\s+)?for\s+(?:the\s+)?' + N_ + r'\b', t)
    if w:
        mo = int(w.group(1))
    if st is None and mo is None:
        g = re.search(r'\b' + N_ + r'\s+(?:more\s+|extra\s+)?(?:monitor|mon)\s+mix(?:es)?\b', t) or \
            re.search(r'\b(?:monitor|mon)\s+mix(?:es)?\s+for\s+' + N_ + r'\b', t) or \
            re.search(r'^(?:give me |set up |make |add )?' + N_ + r'\s+mix(?:es)?$', t.strip())
        if not g:
            if re.search(r'\b(?:iem|wedges?)\b', t) and re.search(r'\bmix(?:es)?\b', t):
                return _ask('Say how many, like "8 IEM mixes" or "4 wedges".', 'mixes')
            return None
        st = int(g.group(1))
    have_st = len([a for a in ix.mix_auxes() if a['stereo']])
    have_mo = len([a for a in ix.mix_auxes() if not a['stereo']])
    op = {'op': 'mixes'}
    if st is not None:
        op['stereo'] = st + (have_st if more else 0)
    if mo is not None:
        op['mono'] = mo + (have_mo if more else 0)
    if any(v > 24 for k, v in op.items() if k != 'op'):
        return _ask('That is more mixes than a console holds. Say up to 24.', 'mixes')
    return _ok([op], 0.9 if (st is not None or mo is not None) else 0.75, 'mixes')


def rec_buses(raw, C, ix, ctx):
    t = C.t
    if re.search(r'\bbus(?:ses)? layout\b.*\b(?:auto|automatic|default)\b|\b(?:auto|automatic)\s+bus(?:ses)?\b', t):
        return _ok([{'op': 'buses', 'auto': True}], 0.9, 'buses')
    am = re.search(r'\b(\d{1,3})\s+(mono\s+|stereo\s+)?aux\b(?!\s*\d)', t)
    gm = re.search(r'\b(\d{1,3})\s+(mono\s+|stereo\s+)?(?:groups?|grps?|sub ?groups?)\b(?!\s*\d)', t)
    if not am and not gm:
        return None
    if re.search(r'\b(?:send|to|into|feed|on)\s+(?:the\s+)?\d', t[:am.start()] if am else ''):
        return None
    cnt = ix.model.get('counts') or {}
    cur = {'aux_mono': (cnt.get('aux') or 0) - (cnt.get('aux_stereo') or 0), 'aux_stereo': cnt.get('aux_stereo') or 0,
           'grp_mono': (cnt.get('groups') or 0) - (cnt.get('groups_stereo') or 0),
           'grp_stereo': cnt.get('groups_stereo') or 0}
    op = dict({'op': 'buses'}, **cur)
    for m in re.finditer(r'\b(\d{1,3})\s+(mono\s+|stereo\s+)?(aux|groups?|grps?|sub ?groups?)\b(?!\s*\d)', t):
        n, kind = int(m.group(1)), (m.group(2) or '').strip()
        bus = 'aux' if m.group(3) == 'aux' else 'grp'
        if not kind:
            if re.search(r'\bstereo\b', t[m.end():m.end() + 40]) or re.search(r'\bstereo\b', t[:m.start()]):
                kind = 'mono'
            else:
                return _ask('Mono or stereo? Say it like "16 mono auxes and 8 stereo".', 'buses')
        op['%s_%s' % (bus, kind)] = n
    tail = re.search(r'\band\s+(\d{1,3})\s+stereo\b(?!\s+(?:aux|groups?))', t)
    if tail and am and not gm:
        op['aux_stereo'] = int(tail.group(1))
    return _ok([op], 0.9, 'buses')


def _fx_kind(t, target_cats=None):
    for rx, k in FX_KIND_WORDS:
        if rx.search(t):
            if k is None:
                cats = target_cats or set()
                if cats and cats <= VOCAL:
                    return 'vocal plate'
                if cats and cats <= DRUMS:
                    return 'room'
                return 'hall'
            return k
    return None


def _fx_units_like(t, ix):
    """Existing FX units a phrase names: 'fx 2', 'the hall', 'the vocal plate', 'the delay'. -> [unit n]."""
    m = re.search(r'\b(?:fx|effect|unit|engine)\s*(\d{1,2})\b', t)
    if m:
        n = int(m.group(1))
        return [u['n'] for u in ix.fx if u['n'] == n]
    hits = []
    for u in ix.fx:
        nm = _norm(u['name'])
        if nm and re.search(r'\b%s\b' % re.escape(nm), t):
            hits.append(u['n'])
    if hits:
        return hits
    for rx, k in FX_KIND_WORDS:
        if rx.search(t):
            if k is None:
                return [u['n'] for u in ix.fx if u['kind'] == 'reverb']
            words = {'vocal plate': r'vocal plate|vox plate', 'drum plate': r'drum plate', 'plate': r'plate',
                     'hall': r'hall', 'room': r'room', 'gated': r'gate|non', 'slap': r'slap',
                     'delay': r'delay|dly|echo|tap', 'chorus': r'chorus', 'thicken': r'thick|doub|adt'}.get(k)
            kind = {'slap': 'delay', 'delay': 'delay', 'chorus': 'chorus', 'thicken': 'pitch'}.get(k, 'reverb')
            same = [u['n'] for u in ix.fx if re.search(words, u['name'].lower())]
            if same:
                return same
            if k in ('delay', 'chorus', 'thicken'):
                return [u['n'] for u in ix.fx if u['kind'] == kind]
            return []
    return []


def _fx_aux(u, ix):
    return next((x['aux'] for x in ix.fx if x['n'] == u), None)


def rec_fx(raw, C, ix, ctx):
    """'add a hall on aux 5', 'add a slap on the lead vox', 'add 2 reverbs and a delay', 'remove the delay'."""
    t = C.t
    if not FX_ANY.search(t):
        return None
    adding = re.search(r'^(?:add|insert|put|set up|setup|spin up|create|give me|get|throw|use|load|new|need|want|make|'
                       r'i want|we need|bring in)\b|\b(?:another|a new|new|second|extra|an additional|additional)\s+'
                       r'(?:\w+\s+)?(?:verb|plate|hall|room|delay|slap|echo|chorus|doubler|thicken|fx|effect)', t)
    removing = re.search(r'^(?:remove|delete|kill|drop|lose|ditch|get rid of|scrap|nuke|take out|bin)\b', t)
    if removing and not re.search(r'\b(?:on|from|off|for)\s+(?:the\s+)?(?!aux|fx\b)\w', t):
        units = _fx_units_like(t, ix)
        if not units:
            if not ix.fx:
                return _ask('This session has no FX units to remove.', 'remove_fx')
            return _ask('Which FX? This session has %s.' % _fx_list(ix), 'remove_fx')
        if len(units) > 1 and not re.search(r'\b(?:all|both|every)\b', t):
            return _ask('Which one? This session has %s. Say it like "remove FX %d".' % (_fx_list(ix), units[0]),
                        'remove_fx')
        return _ok([{'op': 'remove_fx', 'fx': u} for u in units], 0.9, 'remove_fx')
    if not adding:
        return None
    if re.search(r'^(?:add|put|give|throw|use)\s+(?:some|a bit of|a little|a touch of|more|a little bit of)\s+', t):
        return None
    counted = re.search(r'\b(\d)\s+(?:verb|delays?|plates?|halls?|rooms?|fx|effects?)\b|\b(?:verb|delays|fx|effects)\b'
                        r'\s+and\b', t)
    if counted:
        from sessionmaker import options as O
        sug, _ = O.suggest(t, [])
        kinds = [u['kind'] for u in (sug.get('fx') or [])]
        if kinds:
            return _ok([_fx_op(k) for k in kinds], 0.85, 'add_fx')
    name = None
    nm = re.search(r'(?i)\b(?:called|named)\s+(["\']?)(.+?)\1\s*$', raw)
    if nm:
        name = _clean_name(nm.group(2))
        C.take(re.compile(r'\b(?:called|named)\s+.*$'))
    feed = None
    fm = C.take(_w(r'\b(?:on|to|from|via|using|off|fed (?:by|from)|in|into)\s+aux\s*(\d{1,3})\b|\baux\s*(\d{1,3})\b'))
    if fm:
        feed = int(fm.group(1) or fm.group(2))
        if feed not in ix.aux_by_n:
            return _ask('There is no aux %d (the session has %d).' % (feed, len(ix.auxes)), 'add_fx')
    ret = 'auto'
    rm = C.take(_w(r'\breturn(?:ing|ed)?\s+(?:on|to|in)\s+(?:ch\s*)?(\d{1,3})\b'))
    if rm:
        ret = int(rm.group(1))
    kind_m = None
    for rx, k in FX_KIND_WORDS:
        mm = rx.search(C.w)
        if mm:
            kind_m = (mm, k)
            break
    if not kind_m:
        return None
    C.take(kind_m[0].re)
    C.blank(r'add|insert|put|set up|setup|spin up|create|give me|get|throw|use|load|new|need|want|make|another|a new|'
            r'second|extra|an additional|additional|verb|reverb|unit|fx|effect|an?|some|for|on|to|the|with|please|'
            r'bring in|delay|echo|i|we')
    left = C.left()
    tg = resolve_target(left, ix, allow_all=True) if left else Target()
    if left and (tg.missing or tg.empty):
        if tg.notes:
            return _ask(' '.join(tg.notes), 'add_fx')
        return R('pending', conf=0.6, intent='add_fx')
    cats = {ix.by_n[n].cat for n in tg.ns(ix)} if not tg.empty else None
    kind = kind_m[1] or _fx_kind('verb', cats)
    explicit_new = re.search(r'\b(?:another|a new|new|second|extra|additional)\b', t)
    if not tg.empty and not explicit_new and feed is None:
        same = _fx_units_like(t, ix)
        if len(same) == 1 and _fx_aux(same[0], ix):
            aux = _fx_aux(same[0], ix)
            return _send_on(tg, ix, aux, 'the %s (aux %d)' % (_fx_name(ix, same[0]), aux), conf=0.85,
                            new_word='another %s' % kind_m[0].group(0))
    op = _fx_op(kind, feed, ret, name)
    if not tg.empty:
        op['sends'] = 'target'
        op['target'] = tg.selector(ix)
    return _ok([op], 0.9 * tg.conf, 'add_fx')


def _fx_op(kind, feed=None, ret='auto', name=None):
    return {'op': 'add_fx', 'kind': kind, 'feed_aux': feed, 'return': ret, 'name': name, 'sends': 'auto'}


def _fx_list(ix):
    return ', '.join('FX %d %s' % (u['n'], u['name']) for u in ix.fx[:8]) or 'no FX'


def _send_on(tg, ix, aux, label, conf=0.9, new_word='another'):
    """Turn on the sends from the target to an aux. When they all send there already, say so instead."""
    ns = tg.ns(ix)
    off = [n for n in ns if aux not in ix.sends(n)]
    if not off:
        return _ask('%s already %s to %s. Say "more" or "less" to change the level%s.' % (
            _names(ix, ns), 'sends' if len(ns) == 1 else 'send', label or _aux_label(ix, aux),
            ', or "add %s ..." for a second unit' % new_word if new_word else ''), 'send_fx')
    return _ok([{'op': 'send', 'target': {'channels': sorted(off)}, 'aux': aux, 'on': True}], conf, 'send')


def rec_add_channels(raw, C, ix, ctx):
    t = C.t
    if re.search(r'\b(?:ch|channels?|inputs?|lines?|strips?)\s*\d', t) and re.search(r'\b(?:mono|stereo)\b', t):
        return None
    m = re.match(r'^(?:add|insert|append|tack on|create|new|give me|i need|we need|need|make)\s+(?P<n>\d{1,3}|an?|'
                 r'another|one|some)?\s*(?:more\s+|new\s+|extra\s+)?(?P<st>stereo\s+|mono\s+)?(?P<what>ch|inputs?|'
                 r'lines?|strips?|channels?)\b(?P<rest>.*)$', t)
    names, at = [], None
    if not m:
        m2 = re.match(r'^(?:add|insert|i need|we need|need|give me)\s+(?:an?|another|one|a new|new)\s+'
                      r'(?P<st>stereo\s+|mono\s+)?(?P<what>[a-z][a-z0-9 ]{1,24}?)(?P<rest>\s+(?:after|before|at|'
                      r'on|called|named)\b.*)?$', t)
        if not m2:
            return None
        what = m2.group('what').strip()
        if FX_ANY.search(what) or re.search(r'\b(?:gate|comp|hpf|lpf|eq|mustard|mix|iem|wedge|aux|group|send|'
                                            r'shelf|boost|cut|notch|pad|48v|delay|channel|input)\b', what):
            return None
        cat, p = _category(what.title(), bool(m2.group('st') and 'stereo' in m2.group('st')))
        if p < 0.6 or cat == 'other':
            return None
        count, stereo = 1, bool(m2.group('st') and 'stereo' in m2.group('st'))
        names = [_short_title(raw, what)]
        rest = m2.group('rest') or ''
    else:
        nw = m.group('n') or 'a'
        count = int(nw) if nw.isdigit() else 1
        stereo = bool(m.group('st') and 'stereo' in m.group('st'))
        rest = m.group('rest') or ''
        nm = re.search(r'(?i)\b(?:called|named|for)\s+(.+?)\s*(?=\b(?:after|before|at (?:the )?(?:end|start|top|bottom|'
                       r'position|ch)|at \d)\b|$)', raw)
        if nm and re.search(r'\b(?:called|named)\b', t):
            names = [_clean_name(x) for x in re.split(r'(?i)\s*(?:,|\band\b|&)\s*', nm.group(1)) if _clean_name(x)]
        elif nm and re.search(r'\bfor\b', t):
            what = _clean_name(nm.group(1))
            if what:
                names = [what[:1].upper() + what[1:]] if count == 1 else []
    if count < 1 or count > 64:
        return _ask('Add 1 to 64 channels at a time.', 'add_channels')
    pm = re.search(r'\b(after|before|at|on)\s+(?:position\s+|slot\s+|ch\s*)?(\d{1,3})\b', rest) or \
        re.search(r'\b(after|before)\s+(?:the\s+)?(.+?)$', rest)
    if re.search(r'\bat the (?:start|top|beginning|front)\b|\bfirst\b', rest):
        at = 1
    elif re.search(r'\bat the (?:end|bottom)\b|\blast\b', rest):
        at = None
    elif pm:
        rel, what = pm.group(1), pm.group(2)
        if what.isdigit():
            k = int(what)
            if k not in ix.by_n and not (rel in ('at', 'on') and k == ix.count + 1):
                return _ask('There is no channel %d (the session has %d).' % (k, ix.count), 'add_channels')
            at = k + 1 if rel == 'after' else k
        else:
            tg = resolve_target(what, ix, allow_all=False)
            if tg.empty or tg.missing:
                return _ask('After which channel? Say it like "add 2 channels after 12".', 'add_channels')
            ns = tg.ns(ix)
            at = max(ns) + 1 if rel == 'after' else min(ns)
        if at is not None and at > ix.count:
            at = None
    if names and count == 1 and len(names) > 1:
        count = len(names)
    return _ok([{'op': 'add_channels', 'count': count, 'stereo': stereo, 'names': names, 'at': at}], 0.9,
               'add_channels')


def _short_title(raw, what):
    m = re.search(re.escape(what), raw, re.I)
    s = raw[m.start():m.end()] if m else what
    return s if any(ch.isupper() for ch in s) else ' '.join(w[:1].upper() + w[1:] for w in s.split())


def rec_remove_channels(raw, C, ix, ctx):
    t = C.t
    m = re.match(r'^(?:remove|delete|drop|lose|get rid of|ditch|scrap|bin|trash|nuke|take out)\s+(?P<rest>.+)$', t)
    if not m:
        return None
    rest = m.group('rest')
    if re.search(r'\b(?:hpf|lpf|gate|comp|mustard|eq|delay|polarity|48v|pad|send|sends|verb|plate|hall|slap|fx|'
                 r'effects?|patch|group|aux|mix|shelf|boost|notch|trim|template|processing|from|off|out of|in)\b',
                 rest):
        return None
    tg = resolve_target(re.sub(r'^(?:the\s+)?(?:ch|inputs?)\s+', '', rest), ix, allow_all=False)
    if tg.empty and not tg.missing:
        return None
    r = R('remove_channels', conf=0.9 * tg.conf)
    r.target = tg
    r.tphrase = rest
    r.make = lambda tg_: ([{'op': 'remove_channels', 'target': tg_.selector(ix)}], None)
    return r


def rec_move(raw, C, ix, ctx):
    t = C.t
    sw = re.match(r'^swap\s+(?P<a>.+?)\s+(?:and|with|&)\s+(?P<b>.+)$', t)
    if sw:
        ta, tb = resolve_target(sw.group('a'), ix, False), resolve_target(sw.group('b'), ix, False)
        if ta.missing or tb.missing or len(set(ta.chans)) != 1 or len(set(tb.chans)) != 1:
            return _ask('Swap two channels, like "swap 3 and 4".', 'move')
        a, b = sorted((ta.chans[0], tb.chans[0]))
        if a == b:
            return _ask('Those are the same channel.', 'move')
        ops = [{'op': 'move', 'target': {'channels': [b]}, '_to': ('pos', a)}]
        if b != a + 1:
            ops.append({'op': 'move', 'target': {'channels': [a]}, '_to': ('pos', b)})
        return _ok(ops, 0.95, 'move')
    m = re.match(r'^(?:move|drag|shift|reorder|put|place|slide|bump)\s+(?P<tgt>.+?)\s+(?P<rel>to|after|before|below|'
                 r'above|under|beneath|over|next to|right after|in front of|ahead of|behind|in place of|onto)\s+'
                 r'(?P<dst>.+)$', t)
    if not m:
        return None
    if re.search(r'\b(?:aux|group|grp|mix|iem|ears?|wedge|verb|plate|hall|slap|delay|fx|rack|local|socket|mic \d|'
                 r'input \d|gate|comp|mustard|hpf|lpf|eq|mustard|fet|vca|opto)\b', t):
        return None
    if m.group(0).startswith(('put', 'place')) and m.group('rel') in ('to', 'onto', 'over'):
        return None
    tg = resolve_target(m.group('tgt'), ix, allow_all=False)
    if tg.missing or tg.empty:
        return None if not re.match(r'^move\b', t) else _ask(
            'I could not find "%s". Say it like "move 12 to 1".' % m.group('tgt'), 'move')
    rel, dst = m.group('rel'), m.group('dst').strip()
    ns = sorted(set(tg.chans))
    if re.fullmatch(r'(?:the\s+)?(?:end|bottom|last|back)(?: of (?:the )?(?:session|list|desk|board))?', dst):
        spec = ('end',)
    elif re.fullmatch(r'(?:the\s+)?(?:start|top|front|beginning|first)(?: of (?:the )?(?:session|list|desk|board))?',
                      dst):
        spec = ('start',)
    else:
        dm = re.fullmatch(r'(?:position|slot|ch|spot|number)?\s*(\d{1,3})', dst)
        if dm and rel == 'to':
            to = int(dm.group(1))
            if to < 1 or to > ix.count:
                return _ask('There is no position %d (the session has %d).' % (to, ix.count), 'move')
            spec = ('pos', to)
        else:
            td = resolve_target(dst, ix, allow_all=False)
            if td.missing or td.empty:
                return _ask('I could not find "%s". Say it like "move 12 after 4".' % dst, 'move')
            anchor = [n for n in td.ns(ix) if n not in ns]
            if not anchor:
                return _ask('Move them next to another channel.', 'move')
            if rel in ('before', 'above', 'in front of', 'ahead of', 'in place of', 'to'):
                spec = ('before', min(anchor))
            else:
                spec = ('after', max(anchor))
    return _ok([{'op': 'move', 'target': {'channels': ns}, '_to': spec}], 0.95 * tg.conf, 'move')


def rec_stereo(raw, C, ix, ctx):
    t = C.t
    link = re.search(r'\b(?:stereo link|link(?:ed)?|pair(?:ed)?|gang|join|merge|combine|marry|stereo pair|'
                     r'into (?:a |one )?stereo|make .+ (?:a |one )?stereo(?: pair| channel| input)?|as (?:a )?stereo|'
                     r'stereo-?ize|to stereo)\b', t)
    split = re.search(r'\b(?:unlink|split|unpair|un-?pair|separate|break (?:up|apart)|break|make .+ mono|to mono|'
                      r'as mono|de-?stereo|unstereo|un-?link)\b', t)
    if not link and not split:
        return None
    if re.search(r'\b(?:aux|group|grp|mix|iem|wedge|link pans?|fx|verb)\b', t):
        return None
    C.blank(r'stereo link|link(?:ed)?|pair(?:ed)?|gang|join|merge|combine|marry|stereo pair|into|a|one|stereo|make|'
            r'as|stereo-?ize|to|unlink|split|unpair|un-?pair|separate|break up|break apart|break|mono|de-?stereo|'
            r'unstereo|un-?link|channel|ch|input|inputs|two|2|together|them|both|up|apart|please|the|pair')
    left = C.left()
    tg = resolve_target(left, ix, allow_all=False)
    if tg.missing or tg.empty:
        if tg.notes:
            return _ask(' '.join(tg.notes), 'stereo')
        return R('pending', conf=0.6, intent='stereo') if left else _ask(
            'Which channels? Say it like "make 15 and 16 a stereo pair".', 'stereo')
    ns = sorted(set(tg.chans))
    if split and not link:
        sts = [n for n in ns if ix.by_n[n].stereo]
        if not sts:
            return _ask('%s is already mono.' % _names(ix, ns), 'stereo')
        two = re.search(r'\b(?:split|separate|break|unlink|un-?link|unpair|un-?pair)\b', t) is not None
        return _ok([{'op': 'stereo', 'target': {'channels': [n]}, 'on': False, 'split': two} for n in sts], 0.9,
                   'stereo')
    if len(ns) == 1:
        if ix.by_n[ns[0]].stereo:
            return _ask('%s is already stereo.' % _names(ix, ns), 'stereo')
        return _ok([{'op': 'stereo', 'target': {'channels': ns}, 'on': True}], 0.9, 'stereo')
    if len(ns) == 2 and ns[1] == ns[0] + 1:
        if ix.by_n[ns[0]].stereo or ix.by_n[ns[1]].stereo:
            return _ask('%s is already stereo. Pair two mono channels.' % _names(ix, [n for n in ns if
                                                                                    ix.by_n[n].stereo]), 'stereo')
        return _ok([{'op': 'stereo', 'target': {'channels': ns}, 'on': True}], 0.95, 'stereo')
    if len(ns) == 2:
        return _ask('%s are not next to each other. Move them together first, like "move %d after %d".' % (
            _names(ix, ns), ns[1], ns[0]), 'stereo')
    if len(ns) % 2 == 0 and all(ns[i + 1] == ns[i] + 1 for i in range(0, len(ns), 2)) and \
            re.search(r'\bpairs\b', t):
        ops, shift = [], 0
        for i in range(0, len(ns), 2):
            ops.append({'op': 'stereo', 'target': {'channels': [ns[i] - shift, ns[i + 1] - shift]}, 'on': True})
            shift += 1
        return _ok(ops, 0.85, 'stereo')
    return _ask('Pair two channels at a time, like "make %d and %d a stereo pair".' % (ns[0], ns[0] + 1), 'stereo')


def rec_patch(raw, C, ix, ctx):
    t = C.t
    if not re.search(r'\b(?:un-?patch|re-?patch|patch(?:ed|ing)?)\b', t):
        return None
    mode, start = 'rack', None
    if re.search(r'\bun-?patch\b|\bpatch\s+(?:nothing|none)\b|\b(?:remove|clear|kill|delete)\s+(?:the\s+)?patch', t):
        mode = 'none'
        C.blank(r'un-?patch|remove|clear|kill|delete|the patch|patch|nothing|none|from|everything from')
    else:
        if re.search(r'\blocal(?: i ?/? ?o| inputs?| io)?\b|\bfoh (?:rack|io|i/o)\b|\bconsole inputs?\b', t):
            mode = 'local'
        sm = C.take(_w(r'\b(?:starting|start|beginning|from|at|on|to)\s+(?:at\s+|from\s+|with\s+)?(?:the\s+)?(?:stage\s+)?'
                       r'(?:rack|local(?: i ?/? ?o)?|mic|input|socket|in|line)?\s*(?:input\s+|mic\s+|socket\s+)?'
                       r'(\d{1,3})\b(?!\s*(?:-|thru))'))
        if sm:
            start = int(sm.group(1))
        C.blank(r're-?patch|patch(?:ed|ing)?|to|the|stage|racks?|local(?: i ?/? ?o| inputs?| io)?|foh|console inputs?|'
                r'in order|order|sockets?|mic inputs?|starting|start|from|at|on|beginning|with|i ?/? ?o|io|'
                r'inputs? on the rack|mics?|lines?')
    left = C.left()
    if not left:
        return _ask('Which channels? Say it like "patch 1-24 to the rack from 1".', 'patch')

    def make(tg):
        return [{'op': 'patch', 'target': tg.selector(ix), 'mode': mode, 'start': start}], None

    r = R('patch', conf=0.9)
    r.tphrase, r.target, r.make = left, resolve_target(left, ix), make
    return r


def rec_preamp(raw, C, ix, ctx):
    t = C.t
    if C.has(_w(r'\b48v\b')):
        C.take(_w(r'\b48v\b'))
        on = _onoff(C, True)
        C.blank(r'turn|switch|on|in|put|add|give|engage|enable|needs?|power|the|for|to|set|with|use|phantom')
        r = _with_target(C, ix, lambda tg: ([{'op': 'preamp', 'target': tg.selector(ix), 'phantom': on}], None),
                         'preamp')
        return r
    if re.search(r'^(?:pad|engage (?:the )?pad|hit (?:the )?pad|add (?:a |the )?pad|use (?:the )?pad|'
                 r'(?:turn|switch) (?:the )?pad)\b|\bpad (?:on|off|in)\b|\b(?:remove|kill|no|disengage|lose) (?:the )?'
                 r'pad\b', t) and not re.search(r'\bpad [lr]\b|\bpads\b', t):
        C.take(_w(r'\bpad\b'))
        on = _onoff(C, True)
        C.blank(r'engage|hit|add|use|turn|switch|on|in|a|the|for|to|put')
        return _with_target(C, ix, lambda tg: ([{'op': 'preamp', 'target': tg.selector(ix), 'pad': on}], None),
                            'preamp')
    gm = re.search(r'\b(?:gain|pre-?amp|preamps?|head ?amp|mic gain|analog(?:ue)? gain|input gain|mic pre)\b', t)
    if not gm or re.search(r'\b(?:\d+(?:\.\d+)?\s*k\b|\d+\s*hz|eq|shelf|band|boost|cut|bell|makeup|make up|output|'
                           r'trim|digital)\b', t):
        return None
    C.take(_w(r'\b(?:analog(?:ue)? |mic |input )?(?:gain|pre-?amps?|head ?amp|mic pre)\b'))
    return _level_change(C, ix, 'preamp', 'gain_db', lambda c: (c.raw.get('patch') or {}).get('gain_db'),
                         lo=-20.0, hi=60.0, what='gain')


def _step(C):
    """Relative amount and direction from 'more', 'a bit less', 'up 3', 'down 6 db', '+3', 'by 3'. -> dB or None."""
    w = C.w
    up = re.search(r'\b(?:more|louder|up|raise|boost|increase|push|hotter|bump|bring up|turn up|higher|add)\b', w)
    down = re.search(r'\b(?:less|quieter|softer|down|lower|decrease|reduce|pull|drop|cut|back off|bring down|'
                     r'turn down|tuck|take)\b', w)
    if not up and not down:
        return None
    sign = 1.0 if up and not down else -1.0 if down and not up else (1.0 if up.start() < down.start() else -1.0)
    amt = None
    m = C.take(_w(r'\b(?:by\s+)?(\d+(?:\.\d+)?)\s*(?:db\b|more|less)|\bby\s+(\d+(?:\.\d+)?)\b|(?:up|down)\s+(\d+(?:\.\d+)?)\b'
                  r'|(?<![\w.])([+-]\d+(?:\.\d+)?)(?![\w.])'))
    if m:
        v = next(g for g in m.groups() if g is not None)
        amt = abs(float(v))
        if v.startswith('-'):
            sign = -1.0
        elif v.startswith('+'):
            sign = 1.0
    if amt is None:
        if re.search(r'\b(?:a (?:little|bit|touch|tad|hair|smidge)|slightly|a little bit|a bit|touch)\b', w):
            amt = 2.0
        elif re.search(r'\b(?:a lot|way|much|tons|lots|heaps|loads|significantly|a bunch)\b', w):
            amt = 6.0
        else:
            amt = STEP_DB
    C.blank(r'more|louder|up|raise|boost|increase|push|hotter|bump|bring up|turn up|higher|add|less|quieter|softer|'
            r'down|lower|decrease|reduce|pull|drop|cut|back off|bring down|turn down|tuck|take|a little|a bit|a touch|'
            r'a tad|a hair|a smidge|slightly|a little bit|bit|touch|tad|a lot|way|much|tons|lots|heaps|loads|'
            r'significantly|a bunch|by|bring|turn|it|of|db|some')
    return sign * amt


def _level_change(C, ix, op, field, current, lo, hi, what):
    """'gain 30 on the vox' (absolute) or 'add 3 dB of gain to the kick' (relative per channel)."""
    absm = C.take(_w(r'\b(?:to|at|=|of)\s*([+-]?\d+(?:\.\d+)?)\s*(?:db)?\b'))
    step = None
    val = None
    if absm:
        val = float(absm.group(1))
    else:
        step = _step(C)
        if step is None:
            m = C.take(DB_RX) or C.take(BARE_RX)
            if m:
                val = float(m.group(1))
    C.blank(r'set|make|put|the|on|for|to|at|of|db|turn|bring|give|it|with|and|a|an')
    if val is None and step is None:
        return _ask('Say how much, like "%s 30 on the vox" or "%s up 3 on the kick".' % (what, what), op)
    if val is not None:
        if not lo <= val <= hi:
            return _ask('%s goes from %g to %g dB.' % (what.capitalize(), lo, hi), op)
        return _with_target(C, ix, lambda tg: ([dict({'op': op, 'target': tg.selector(ix)}, **{field: val})], None),
                            op)

    def make(tg):
        groups, skip = {}, []
        for n in tg.ns(ix):
            cur = current(ix.by_n[n])
            if cur is None or cur <= -150:
                skip.append(n)
                continue
            groups.setdefault(round(max(lo, min(hi, float(cur) + step)), 1), []).append(n)
        if skip and not groups:
            return [], '%s has no %s to move from. Say a level, like "%s to -5 on %s".' % (
                _names(ix, skip), what, what, ix.by_n[skip[0]].name)
        ops = [dict({'op': op, 'target': {'channels': ns}}, **{field: v}) for v, ns in sorted(groups.items(),
                                                                                         key=lambda kv: kv[1][0])]
        return ops, None
    return _with_target(C, ix, make, op)


def rec_send(raw, C, ix, ctx):
    t = C.t
    gm = re.search(r'\b(?:to|into|in|on|through|thru|via|out of|from|off)\s+(?:the\s+)?(?:group|grp|sub ?group|subgroup)\s*'
                   r'(\d{1,3})\b|\b(?:group|grp)\s*(\d{1,3})\b', t)
    pa = re.search(r'\b(?:out of|from|off|in|into|to)\s+(?:the\s+)?(?:pa|mains?|main mix|master|lr|l ?r|house|'
                   r'front of house|foh)\b', t)
    gname = re.search(r'\b(?:to|into|in|out of|from)\s+(?:the\s+)?(.+?)\s+(?:group|grp|sub ?group|subgroup)\b', t)
    if gm or pa or (gname and re.search(r'\b(?:route|assign|send|put|bus|take|pull|remove)\b|^\S', t)):
        if gm:
            g = int(gm.group(1) or gm.group(2))
            if g not in {x['n'] for x in ix.groups}:
                return _ask('There is no group %d (the session has %d).' % (g, len(ix.groups)), 'route_group')
            C.take(_w(r'\b(?:to|into|in|on|through|thru|via|out of|from|off)?\s*(?:the\s+)?(?:group|grp|sub ?group|'
                      r'subgroup)\s*\d{1,3}\b'))
        elif pa:
            g = ix.master()
            if g is None:
                return _ask('I could not find the Master group in this session.', 'route_group')
            C.take(_w(r'\b(?:out of|from|off|in|into|to)\s+(?:the\s+)?(?:pa|mains?|main mix|master|lr|l ?r|house|'
                      r'front of house|foh)\b'))
        else:
            cand = [x['n'] for x in ix.groups if x['norm'] and (x['norm'] == _norm(gname.group(1)) or
                                                                 x['norm'].startswith(_norm(gname.group(1))))]
            if len(cand) != 1:
                return _ask('Which group? Say it like "drums to group 1".', 'route_group')
            g = cand[0]
            C.take(_w(r'\b(?:to|into|in|out of|from)\s+(?:the\s+)?.+?\s+(?:group|grp|sub ?group|subgroup)\b'))
        on = not re.search(r'\b(?:out of|from|off|remove|take|pull|unassign|unroute|kill|no|not|without)\b', t)
        C.blank(r'route|routed|assign|assigned|send|sent|put|bus|bussed|take|pull|remove|unassign|unroute|kill|the|'
                r'all|and|to|into|out|of|from|off|no|not|in|it|them|make sure|is|are')
        return _with_target(C, ix, lambda tg: ([{'op': 'send', 'target': tg.selector(ix), 'group': g, 'on': on}], None),
                            'send')
    am = re.search(r'\b(?:aux|mix)\s*(\d{1,3})\b', t)
    if am and not re.search(r'\b(?:add|insert|new|create)\b.*\b(?:verb|plate|hall|room|delay|slap|chorus|fx)\b', t) \
            and not re.search(r'^(?:re-?name|name|call)\b', t):
        a = int(am.group(1))
        if a not in ix.aux_by_n:
            return _ask('There is no aux %d (the session has %d).' % (a, len(ix.auxes)), 'send')
        C.take(_w(r'\b(?:to|into|in|on|from|out of|off)?\s*(?:the\s+)?(?:aux|mix)\s*\d{1,3}\b'))
        return _send_fields(C, ix, a, t, 'aux %d %s' % (a, ix.aux_by_n[a]['name']))
    return _send_relative(raw, C, ix, ctx)


def _send_fields(C, ix, aux, t, label):
    on = not re.search(r'\b(?:out of|off|remove|take|pull|kill|no|not|without|mute)\b', t)
    pre = None
    pm = C.take(_w(r'\b(pre|post)(?:\s*-?\s*(?:fader|eq|mute))?\b'))
    if pm:
        pre = pm.group(1)
    pan = None
    level = None
    lm = C.take(_w(r'\b(?:at|to|@|=)\s*([+-]?\d+(?:\.\d+)?)\s*(?:db)?\b')) or C.take(DB_RX) or C.take(SIGNED_RX)
    if lm:
        level = float(lm.group(1))
        if not -150.0 <= level <= 10.0:
            return _ask('A send goes from -150 to +10 dB.', 'send')
    step = None
    if level is None and on:
        step = _step(C)
    C.blank(r'send|sent|sends|put|route|feed|give|turn on|turn|on|the|to|into|in|from|out|of|and|all|at|level|'
            r'fader|make|it|them|is|are|have|with|a|an|db|unity|send level')
    if re.search(r'\bunity\b', t) and level is None:
        level = 0.0

    def make(tg):
        if step is not None:
            return _relative_sends(tg, ix, aux, step, MIX_START_DB)
        op = {'op': 'send', 'target': tg.selector(ix), 'aux': aux, 'on': on}
        if level is not None and on:
            op['level_db'] = level
        if pre and on:
            op['pre'] = pre
        if pan is not None:
            op['pan'] = pan
        return [op], None
    return _with_target(C, ix, make, 'send')


def _relative_sends(tg, ix, aux, step, start):
    groups, missing = {}, []
    for n in tg.ns(ix):
        s = ix.sends(n).get(aux)
        if s is None or s.get('level_db') is None or s.get('level_db') <= -150:
            if step < 0:
                missing.append(n)
                continue
            lvl = start
        else:
            lvl = round(max(-150.0, min(10.0, float(s['level_db']) + step)), 1)
        groups.setdefault(lvl, []).append(n)
    if missing and not groups:
        return [], '%s does not send to %s.' % (_names(ix, missing), _aux_label(ix, aux))
    return [{'op': 'send', 'target': {'channels': ns}, 'aux': aux, 'on': True, 'level_db': v}
            for v, ns in sorted(groups.items(), key=lambda kv: kv[1][0])], None


def _aux_label(ix, aux):
    a = ix.aux_by_n.get(aux)
    return 'aux %d (%s)' % (aux, a['name']) if a and a['name'] else 'aux %d' % aux


DIR = (r'(?:(?:a (?:little|bit|touch|tad|lot|little bit|bunch|hair) |way |much |slightly |some |lots |tons )?'
       r'(?:more|less)|turn up|turn down|bring up|bring down|pull down|pull|push|raise|lower|boost|drop|reduce|'
       r'increase|decrease|tuck|bump(?: up)?|up|down|louder|quieter|kill|remove|lose|no|take out|get rid of|mute|'
       r'add(?: some| a bit of| a little)?|put(?: some)?|give(?: me)?(?: some)?|throw(?: some)?|some)')


def _send_relative(raw, C, ix, ctx):
    t = C.t
    m = re.match(r'^(?P<who>.+?)\s+(?:wants|needs|asked for|asks for|is asking for|would like|could use|can(?:no|\')?t '
                 r'hear (?:enough(?: of)?)?|cannot hear(?: enough(?: of)?)?|hears too much|has too much)\s+'
                 r'(?P<rest>.+)$', t)
    if m:
        who, rest = m.group('who'), m.group('rest')
        rest = re.sub(r'\s+in\s+(?:his|her|their|the|my)\s+%s$' % MIXWORD, '', rest)
        if re.search(r'\b(?:hears too much|has too much)\b', t):
            rest = 'less ' + rest
        elif re.search(r"\bcan(?:no|')?t hear|cannot hear", t) and not re.match(r'(?:more|less)\b', rest):
            rest = 'more ' + rest
        auxes = _aux_by_who(who, ix, mixes_only=True)
        fxm = FX_ANY.search(rest)
        if auxes and not fxm:
            return _mix_send(C, ix, auxes, rest, who)
        tw = resolve_target(who, ix, allow_all=False)
        if fxm and not tw.empty and not tw.missing:
            return _fx_send(C, ix, rest, tw)
        if not auxes:
            return _ask('Whose mix is "%s"? This session has %s.' % (who, _mix_list(ix)), 'send_mix')
    m = re.match(r'^(?P<pre>%s\s+)?(?P<what>.+?)\s+(?P<post>(?:%s)\s+)?(?:in|into|to|for|on)\s+(?P<who>(?:the\s+|my\s+|'
                 r'his\s+|her\s+|their\s+)?[\w\' ]+?(?:\'s)?)(?:\s+%s)?(?P<post2>\s+%s)?$' % (DIR, DIR, MIXWORD, DIR), t)
    if m and (m.group('pre') or m.group('post') or m.group('post2')):
        who = m.group('who')
        mixword = re.search(r'\b%s\s*(?:%s)?$' % (MIXWORD, DIR), t) is not None
        auxes = _aux_by_who(who, ix, mixes_only=not mixword)
        what = m.group('what')
        dirw = (m.group('pre') or m.group('post') or m.group('post2') or '').strip()
        if auxes and not FX_ANY.search(what) and (mixword or not resolve_target(who, ix, False).chans or
                                                  _aux_by_who(who, ix, True)):
            return _mix_send(C, ix, auxes, dirw + ' ' + what, who)
    fx = re.match(r'^(?P<dir>%s)\s+(?:the\s+|of the\s+)?(?P<fx>.+?)\s+(?:on|for|to|in|from|off)\s+(?P<what>.+)$' % DIR, t)
    if fx and FX_ANY.search(fx.group('fx')) and not re.search(r'\b(?:aux|group)\b', fx.group('fx')):
        tg = resolve_target(fx.group('what'), ix)
        return _fx_send(C, ix, fx.group('dir') + ' ' + fx.group('fx'), tg, phrase=fx.group('what'))
    fx2 = re.match(r'^(?P<what>.+?)\s+(?P<dir>%s)\s+(?P<fx>(?:the\s+)?(?:verb|plate|hall|room|delay|slap|echo|'
                   r'chorus|fx|effects?|doubler|thicken)\w*)$' % DIR, t)
    if fx2:
        tg = resolve_target(fx2.group('what'), ix)
        return _fx_send(C, ix, fx2.group('dir') + ' ' + fx2.group('fx'), tg, phrase=fx2.group('what'))
    fx3 = re.match(r'^(?:put|send|feed|add|throw|route)\s+(?P<what>.+?)\s+(?:in|into|to|through|on)\s+(?:the\s+)?'
                   r'(?P<fx>[\w ]+)$', t)
    if fx3 and FX_ANY.search(fx3.group('fx')):
        units = _fx_units_like(fx3.group('fx'), ix)
        if len(units) == 1 and _fx_aux(units[0], ix):
            aux = _fx_aux(units[0], ix)
            tg = resolve_target(fx3.group('what'), ix)

            def make_fx(tg_):
                r_ = _send_on(tg_, ix, aux, 'the %s (aux %d)' % (_fx_name(ix, units[0]), aux), new_word=None)
                return (r_.ops, None) if r_.kind != 'ask' else ([], r_.ask)
            return _target_result(tg, fx3.group('what'), ix, make_fx, 'send')
    if fx3 and not FX_ANY.search(fx3.group('fx')):
        auxes = _aux_by_who(fx3.group('fx'), ix, mixes_only=False)
        if auxes:
            tg = resolve_target(fx3.group('what'), ix)
            return _target_result(tg, fx3.group('what'), ix,
                                  lambda tg_: ([{'op': 'send', 'target': tg_.selector(ix), 'aux': a, 'on': True}
                                                for a in auxes], None), 'send')
    return None


def _target_result(tg, phrase, ix, make, kind):
    r = R(kind, conf=0.9 * tg.conf)
    r.target, r.tphrase, r.make = tg, phrase, make
    return r


def _mix_list(ix):
    mx = ix.mix_auxes()
    return ', '.join('aux %d %s' % (a['n'], a['name']) for a in mx[:10]) if mx else 'no monitor mixes'


def _mix_send(C, ix, auxes, rest, who):
    sub = Clause(rest, rest)
    step = _step(sub)
    off = re.search(r'\b(?:kill|remove|lose|no|take out|get rid of|mute)\b', rest)
    sub.blank(r'some|the|of|in|into|my|his|her|their|me|own|mix|ears?|iem|kill|remove|lose|no|take out|get rid of|mute')
    tg = resolve_target(sub.left(), ix)
    if re.fullmatch(r'\s*(?:me|myself|himself|herself|themselves|him|her|them)?\s*', sub.left() or ''):
        seat = [ix.aux_by_n[a]['norm'] for a in auxes]
        own = Target()
        for s in seat:
            r_ = resolve_target(s, ix, allow_all=False)
            own.chans += r_.chans
        if own.chans:
            tg = own
        else:
            return _ask('Which channels are "%s"? Say it like "more Lead Vox in the lead mix".' % (rest.strip() or who),
                        'send_mix')

    def make(tg_):
        ops = []
        for a in auxes:
            if off:
                ops.append({'op': 'send', 'target': tg_.selector(ix), 'aux': a, 'on': False})
                continue
            o, ask = _relative_sends(tg_, ix, a, step if step is not None else STEP_DB, MIX_START_DB)
            if ask and not o:
                return [], ask
            ops += o
        return ops, None
    return _target_result(tg, sub.left(), ix, make, 'send')


def _fx_send(C, ix, fxphrase, tg, phrase=''):
    """'more verb' / 'less slap' / 'kill the verb' on a target -> sends to the matching FX aux."""
    off = re.search(r'\b(?:kill|remove|lose|no|take out|get rid of|mute)\b', fxphrase)
    sub = Clause(fxphrase, fxphrase)
    step = None if off else _step(sub)
    if step is None and not off:
        step = STEP_DB
    units = _fx_units_like(fxphrase, ix)
    auxes = [(_fx_aux(u, ix), u) for u in units if _fx_aux(u, ix)]
    if not auxes:
        k = _fx_kind(fxphrase)
        if not ix.fx:
            return _ask('This session has no FX yet. Add one first, like "add a %s".' % (k or 'hall'), 'send_fx')
        return _ask('Which FX? This session has %s.' % _fx_list(ix), 'send_fx')

    def make(tg_):
        ns = tg_.ns(ix)
        cands = auxes
        if len(cands) > 1:
            used = [(a, u) for a, u in cands if any(a in ix.sends(n) for n in ns)]
            if len(used) == 1:
                cands = used
            else:
                cats = {ix.by_n[n].cat for n in ns}
                pref = [(a, u) for a, u in (used or cands)
                        if (cats <= VOCAL and re.search(r'vo[cx]|vocal|plate', _fx_name(ix, u).lower())) or
                        (cats <= DRUMS and re.search(r'drum|room|snare|kit', _fx_name(ix, u).lower()))]
                if len(pref) == 1:
                    cands = pref
                else:
                    return [], 'Which one? %s. Say it like "more %s on %s".' % (
                        ', '.join('%s is aux %d' % (_fx_name(ix, u), a) for a, u in cands),
                        _fx_name(ix, cands[0][1]).lower(), phrase or 'the lead')
        a = cands[0][0]
        if off:
            return [{'op': 'send', 'target': {'channels': ns}, 'aux': a, 'on': False}], None
        return _relative_sends(tg_, ix, a, step, FX_START_DB)
    return _target_result(tg, phrase, ix, make, 'send')


def _fx_name(ix, u):
    return next((x['name'] for x in ix.fx if x['n'] == u), 'FX %d' % u)


def rec_template(raw, C, ix, ctx):
    t = C.t
    if not re.search(r'\btemplates?\b|\bstarting (?:point|processing)\b|\bdefault processing\b|'
                     r'\breset\b.*\b(?:processing|to (?:the )?(?:defaults?|starting|template|scratch))\b|'
                     r'\bstart(?:ing)? (?:over|fresh|from scratch)\b', t):
        return None
    cat = None
    cm = C.take(_w(r'\b(?:the\s+|a\s+)?([a-z][a-z ]{1,24}?)\s+templates?\b'))
    if cm:
        word = _clean_part(cm.group(1))
        if word and word not in ('the', 'a', 'starting', 'default', 'processing', 'channel', 'own', 'their own',
                                 'each', 'its own', 'right', 'usual', 'session maker'):
            g = None
            for key, lab, rx, sel in GROUPS:
                if rx.match(word):
                    g = key
                    break
            if g:
                cat = TEMPLATE_OF_GROUP.get(g)
            else:
                c2, p = _category(word.title(), False)
                cat = c2 if p >= 0.6 and c2 != 'other' else None
            if cat is None:
                return _ask('I do not have a "%s" template. Say an instrument, like "use the snare template on 7".'
                            % word, 'template')
    C.blank(r'apply|use|load|give|put|reset|re-?apply|redo|start(?:ing)?|over|fresh|from scratch|scratch|templates?|'
            r'starting point|starting processing|default processing|processing|defaults?|the|to|on|for|with|of|'
            r'their own|its own|own|each|back|everything back|session maker|again')
    left = C.left() or 'everything'

    def make(tg):
        return [{'op': 'apply_template', 'target': tg.selector(ix), 'category': cat}], None
    r = R('apply_template', conf=0.9)
    r.tphrase, r.target, r.make = left, resolve_target(left, ix), make
    return r


PROC_WORDS = _w(r'\b(?:mustard|fet|vca|opto|optical|la ?-?2 ?a|1176|lev ?amp|levelling amp|leveling amp|classic comp|'
                r'comp|squash|squeeze|limit(?:er)?|ratio|makeup|make up|knee|gate|expander|duck(?:er)?|hpf|lpf|eq|'
                r'shelf|notch|boost|bell|delay|polarity|phase|invert|flip|trim|view|threshold|thresh|thr|attack|'
                r'release|hold|range)\b')


def rec_processing(raw, C, ix, ctx):
    t = C.t
    if not C.has(PROC_WORDS) and not re.search(r'\b(?:cut|scoop|dip)\s+(?:\d|some|a bit|a little)', t):
        return None
    if re.search(r'\b(?:add|insert|new)\s+(?:an?\s+)?(?:\w+\s+)?delay\b', t) and not MS_RX.search(t):
        return None
    for fn in (_p_view, _p_mustard, _p_gate, _p_comp, _p_hpf_lpf, _p_eq, _p_delay, _p_polarity, _p_trim):
        r = fn(C, ix, t)
        if r is not None:
            return r
    return None


def _p_view(C, ix, t):
    m = C.take(_w(r'\b(?:show|switch|flip|open|set|put)?\s*(?:the\s+|it\s+|them\s+)?(?:to\s+|on\s+)?(?:the\s+)?'
                  r'(m|mustard|sd)\s+view\b'))
    if not m:
        return None
    view = 'sd' if m.group(1) == 'sd' else 'mustard'
    C.blank(r'show|switch|flip|open|set|put|the|to|on|for|in|of')
    return _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'view': view}], None))


def _dyn_params(C, mustard=False):
    """Threshold, ratio, attack, release, hold, range, knee, makeup/out, mix from the clause."""
    p = {}
    m = C.take(RATIO_RX)
    if m:
        p['ratio'] = float(m.group(1) or m.group(2))
    m = C.take(_w(r'\b(?:thresh(?:old)?|thr)\s*(?:at|of|to|=|@)?\s*([+-]?\d+(?:\.\d+)?)\s*(?:db)?\b')) or \
        C.take(_w(r'(?<![\w.])(-\d+(?:\.\d+)?)\s*(?:db)?\s*(?:thresh(?:old)?|thr)\b'))
    if m:
        p['thr'] = -abs(float(m.group(1))) if float(m.group(1)) > 0 else float(m.group(1))
    for key, words in (('attack', 'attack|atk'), ('release', 'release|rel'), ('hold', 'hold')):
        m = C.take(_w(r'\b(?:%s)\s*(?:of|at|to|=)?\s*(\d+(?:\.\d+)?)\s*(ms|s)?\b' % words)) or \
            C.take(_w(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(ms|s)\s*(?:of\s+)?(?:%s)\b' % words))
        if m:
            v = float(m.group(1))
            p[key] = v * 1000.0 if m.group(2) == 's' else v
            continue
        m = C.take(_w(r'\b(fast(?:er|est)?|quick(?:er)?|slow(?:er|est)?|medium)\s+(?:%s)\b' % words))
        if m:
            fast = m.group(1).startswith(('fast', 'quick'))
            med = m.group(1) == 'medium'
            p[key] = {'attack': (1.0, 10.0, 30.0), 'release': (50.0, 150.0, 400.0),
                      'hold': (20.0, 100.0, 250.0)}[key][0 if fast else 1 if med else 2]
    m = C.take(_w(r'\brange\s*(?:of|at|to|=)?\s*-?(\d+(?:\.\d+)?)\s*(?:db)?\b')) or \
        C.take(_w(r'(?<![\w.])-?(\d+(?:\.\d+)?)\s*db\s+(?:of\s+)?range\b'))
    if m:
        p['range'] = float(m.group(1))
    m = C.take(_w(r'\b(soft|hard|medium)\s+knee\b'))
    if m:
        p['knee'] = m.group(1)
    m = C.take(_w(r'\b(?:make ?up|makeup gain|make-up|output|out gain|out)\s*(?:gain\s*)?(?:of|at|to|=)?\s*'
                  r'([+-]?\d+(?:\.\d+)?)\s*(?:db)?\b')) or \
        C.take(_w(r'(?<![\w.])\+?(\d+(?:\.\d+)?)\s*db\s+(?:of\s+)?(?:make ?up|makeup|output)\b'))
    if m:
        p['out' if mustard else 'makeup'] = float(m.group(1))
    m = C.take(_w(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|percent)\s*(?:mix|wet|parallel|blend)?')) or \
        C.take(_w(r'\b(?:mix|wet|parallel|blend)\s*(?:of|at|to|=)?\s*(\d+(?:\.\d+)?)\s*(?:%|percent)?'))
    if m and mustard:
        v = float(m.group(1))
        p['mix'] = round(v / 100.0 if v > 1 else v, 2)
    elif re.search(r'\b(?:parallel|half wet|50/50)\b', C.w) and mustard:
        p['mix'] = 0.5
        C.blank(r'parallel|half wet|50/50')
    if 'thr' not in p:
        m = C.take(_w(r'(?:\bat|\bto|@)?\s*(?<![\w.])(-\d+(?:\.\d+)?)\s*(?:db)?(?![\w.])'))
        if m:
            p['thr'] = float(m.group(1))
    return p


def _check_dyn(p):
    if 'thr' in p and not -60.0 <= p['thr'] <= 0.0:
        return 'A threshold goes from -60 to 0 dB.'
    if 'ratio' in p and not 1.0 <= p['ratio'] <= 50.0:
        return 'A ratio goes from 1:1 to 50:1.'
    if 'attack' in p and not 0.05 <= p['attack'] <= 300.0:
        return 'Attack goes from 0.05 to 300 ms.'
    if 'release' in p and not 5.0 <= p['release'] <= 10000.0:
        return 'Release goes from 5 ms to 10 s.'
    if 'range' in p and not 0.0 <= p['range'] <= 90.0:
        return 'Gate range goes from 0 to 90 dB.'
    return None


DYN_BLANK = (r'turn|switch|set|put|use|give|add|insert|engage|enable|the|on|in|for|to|at|with|a|an|and|please|it|'
             r'them|some|of|db|ms|instead|swap|change|go|going|run|swap out|replace|across|over|using|onto|our|'
             r'model|models|comp|style|type|mode|plugin|plug-in|unit|everywhere')


def _p_mustard(C, ix, t):
    model = None
    for rx, k in MUSTARD_MODELS:
        if rx.search(C.w):
            model = k
            break
    has_m = C.has(_w(r'\bmustard\b'))
    if not has_m and model is None:
        return None
    if not has_m and model == 'classic' and not re.search(r'\bclassic comp', C.w):
        return None
    if not ix.quantum and ix.model.get('console'):
        lab = (ix.model.get('console') or {}).get('label') or 'This console'
        return _ask('The %s has no Mustard processing (Quantum consoles only). Say "comp" for the SD compressor, '
                    'like "comp the bass 4:1 at -20".' % lab, 'mustard')
    C.take_all(_w(r'\bmustard\b|\bfet\b|\b1176\b|\bvca\b|\bssl\b|\bdbx\b|\bbus comp\b|\bopto\b|\boptical\b|'
                  r'\bla ?-?2 ?a\b|\bla2a\b|\blev ?amp\b|\blevell?ing amp(?:lifier)?\b|\blevamp\b|\bclassic\b'))
    on = _onoff(C, True)
    p = _dyn_params(C, mustard=True)
    bad = _check_dyn(p)
    if bad:
        return _ask(bad, 'mustard')
    swap = re.search(r'\b(?:swap|replace|change|convert|switch|turn)\b.*\b(?:sd )?comp\b|\b(?:sd )?comp\b.*\b(?:to|for|'
                     r'with|into)\b.*\bmustard\b', t)
    C.blank(DYN_BLANK + r'|sd|sds|swap|for|to|into|convert|replace|wherever|where|there is|there are|existing|current')
    fields = {'on': on}
    if on:
        if model:
            fields['model'] = model
        fields.update(p)
    view = None

    def make(tg):
        ops = [{'op': 'set', 'target': tg.selector(ix), 'mustard': dict(fields)}]
        return ops, None
    left = C.left()
    if not left and swap:
        ns = [c.n for c in ix.chans if c.raw.get('comp')]
        if not ns:
            return _ask('No channel has an SD comp on. Say which channels, like "Mustard on the vocals".', 'mustard')
        r = R('set', conf=0.85)
        tg = Target()
        tg.chans = ns
        tg.labels = ['the channels with an SD comp']
        r.target, r.tphrase, r.make = tg, 'channels with a comp', make
        return r
    del view
    return _with_target(C, ix, make, conf=0.95)


def _p_gate(C, ix, t):
    if not C.has(_w(r'\b(?:gate|noise gate|expander|duck(?:er|ing)?)\b')):
        return None
    C.take_all(_w(r'\b(?:noise )?gate\b|\bexpander\b|\bduck(?:er|ing)?\b'))
    on = _onoff(C, True)
    p = _dyn_params(C)
    bad = _check_dyn(p)
    if bad:
        return _ask(bad, 'gate')
    p.pop('ratio', None)
    p.pop('knee', None)
    p.pop('makeup', None)
    if re.search(r'\b(?:open (?:it |them )?up|open up|less)\b', C.w) and 'thr' not in p and on:
        return _ask('Say the threshold, like "gate threshold -50 on the toms".', 'gate')
    C.blank(DYN_BLANK + r'|tighten|tighter|threshold|thresh')
    fields = dict({'on': on}, **(p if on else {}))
    return _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'gate': dict(fields)}], None))


def _p_comp(C, ix, t):
    if not C.has(_w(r'\b(?:comp|squash|squeeze|limit(?:er)?|ratio|makeup|make up|knee|threshold|thresh|thr|attack|'
                    r'release)\b')) and not C.has(RATIO_RX):
        return None
    C.take_all(_w(r'\b(?:sd |sd7 |channel )?(?:comp|squash|squeeze|limit(?:er)?)\b'))
    on = _onoff(C, True)
    p = _dyn_params(C)
    bad = _check_dyn(p)
    if bad:
        return _ask(bad, 'comp')
    p.pop('range', None)
    p.pop('hold', None)
    if re.search(r'\b(?:squash|squeeze)\b', t) and 'ratio' not in p and on:
        p['ratio'] = 4.0
    if re.search(r'\blimit(?:er)?\b', t) and 'ratio' not in p and on:
        p['ratio'] = 20.0
    C.blank(DYN_BLANK + r'|harder|hard|more|heavier|threshold|thresh|thr|sd|lightly|gently|light')
    fields = dict({'on': on}, **(p if on else {}))
    return _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'comp': dict(fields)}], None))


def _p_hpf_lpf(C, ix, t):
    m = C.take(_w(r'\b(hpf|lpf)\b'))
    if not m:
        return None
    which = m.group(1)
    other = C.take(_w(r'\b(hpf|lpf)\b'))
    on = _onoff(C, True)
    freq = None
    fm = C.take(FREQ_UNIT)
    if fm:
        freq = _freq_val(fm)
    else:
        am = C.take(AT_NUM)
        if am:
            freq = float(am.group(1))
    if freq is None and on:
        nums = list(BARE_RX.finditer(C.w))
        words = re.sub(r'[\d\s.,+-]+', ' ', C.w).strip()
        words = re.sub(r'\b(?:the|on|at|to|all|and|for|ch|set|put|move|turn|make|it|them|filter|engage|in|with|a|an|'
                       r'use|everything|everyone)\b', '', words).strip()
        has_words = bool(re.search(r'[a-z]', words)) or re.search(r'\b(?:everything|all)\b', C.w)
        if nums:
            last = nums[-1]
            v = float(last.group(1))
            if len(nums) >= 2 or has_words:
                freq = v
                C.w = C.w[:last.start()] + ' ' * (last.end() - last.start()) + C.w[last.end():]
            elif v > ix.count or v >= 20 and v not in ix.by_n:
                freq = v
                C.w = C.w[:last.start()] + ' ' * (last.end() - last.start()) + C.w[last.end():]
    if freq is not None and not 20.0 <= freq <= 20000.0:
        return _ask('A filter goes from 20 Hz to 20 kHz.', which)
    C.blank(r'turn|switch|set|put|move|bring|make|engage|enable|add|give|use|the|on|in|for|to|at|of|with|a|an|it|'
            r'them|filter|filters|hz|up|down|everything up|and|both')
    fld = {'on': on}
    if on and freq is not None:
        fld['freq'] = freq
    keys = [which] + ([other.group(1)] if other else [])

    def make(tg):
        return [{'op': 'set', 'target': tg.selector(ix), k: dict(fld)} for k in keys], None
    return _with_target(C, ix, make)


EQ_WORDS = _w(r'\b(?:eq|shelf|notch|boost|cut|bell|scoop|dip|band\s*\d)\b')


def _p_eq(C, ix, t):
    if not C.has(EQ_WORDS):
        return None
    if C.has(_w(r'\beq\b')) and not C.has(FREQ_UNIT) and not re.search(r'\b(?:boost|cut|shelf|notch|band|scoop|dip|bell)'
                                                                          r'\b', C.w):
        C.take_all(_w(r'\beq\b|\bequali[sz]ers?\b|\bequali[sz]ation\b'))
        flat = C.take(_w(r'\b(?:flat|flatten|reset|zero|clear)\b'))
        on = _onoff(C, True) and not flat
        C.blank(r'turn|switch|set|put|the|on|in|for|to|it|them|and|of|engage|enable|use|out|everything')
        conf = 0.8 if flat else 0.95
        return _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'eq_on': on}], None),
                            conf=conf)
    fm = C.take(FREQ_UNIT)
    freq = _freq_val(fm) if fm else None
    band = None
    bm = C.take(_w(r'\bband\s*(\d)\b'))
    if bm:
        band = int(bm.group(1))
        if not 1 <= band <= 4:
            return _ask('The EQ has bands 1 to 4.', 'eq')
    typ = 'bell'
    sm = C.take(_w(r'\b(low|lo|bottom|high|hi|top)?\s*-?\s*shelf(?:ing)?\b'))
    if sm:
        side = sm.group(1) or ''
        if side in ('low', 'lo', 'bottom') or (not side and freq and freq < 1000):
            typ = 'low_shelf'
        else:
            typ = 'high_shelf'
    gain = None
    gm = C.take(DB_RX) or C.take(SIGNED_RX)
    if gm:
        gain = float(gm.group(1))
    q = None
    qm = C.take(_w(r'\b(?:q|width|bw)\s*(?:of|at|=)?\s*(\d+(?:\.\d+)?)\b'))
    if qm:
        q = float(qm.group(1))
    elif re.search(r'\b(?:narrow|tight|surgical)\b', C.w):
        q = 4.0
    elif re.search(r'\b(?:wide|broad|gentle)\b', C.w):
        q = 0.7
    cut = re.search(r'\b(?:cut|scoop|dip|notch|pull|take out|remove|reduce|less|duck|tame|carve)\b', C.w)
    boost = re.search(r'\b(?:boost|add|more|lift|bump|push|raise)\b', C.w)
    if freq is None:
        am = C.take(_w(r'\b(?:at|@|around|about|near)\s*(\d+(?:\.\d+)?)\b(?!\s*(?:db|ms))'))
        if am:
            freq = float(am.group(1))
        else:
            nums = [m for m in BARE_RX.finditer(C.w)]
            big = [m for m in nums if float(m.group(1)) >= 20 and float(m.group(1)) > ix.count]
            if big:
                mm = big[0]
                freq = float(mm.group(1))
                C.w = C.w[:mm.start()] + ' ' * (mm.end() - mm.start()) + C.w[mm.end():]
    if gain is None and freq is not None:
        mm = C.take(_w(r'\b(?:cut|boost|scoop|dip|pull|bump|lift|push|add|take out|remove)\s+(\d{1,2}(?:\.\d+)?)\b(?!\s*k)'))
        if mm:
            gain = float(mm.group(1))
    if freq is None:
        return _ask('Say the frequency, like "cut 3 dB at 400 on the kick".', 'eq')
    if not 20.0 <= freq <= 20000.0:
        return _ask('EQ goes from 20 Hz to 20 kHz.', 'eq')
    notch = re.search(r'\bnotch\b', t)
    if gain is None:
        gain = -10.0 if notch else 3.0
    gain = abs(gain)
    if cut or notch:
        gain = -gain
    elif not boost and gm and gm.group(1).startswith('-'):
        gain = -gain
    if not -18.0 <= gain <= 18.0:
        return _ask('EQ gain goes from -18 to +18 dB.', 'eq')
    if notch and q is None:
        q = 8.0
    if band is None:
        band = 1 if typ == 'low_shelf' else 4 if typ == 'high_shelf' else (
            1 if freq < 200 else 2 if freq < 1000 else 3 if freq < 5000 else 4)
    if typ == 'low_shelf' and band not in (1, 2) or typ == 'high_shelf' and band not in (3, 4):
        return _ask('Shelves sit on bands 1-2 (low) and 3-4 (high).', 'eq')
    C.blank(r'eq|cut|scoop|dip|notch|pull|take out|remove|reduce|less|duck|tame|carve|boost|add|more|lift|bump|push|'
            r'raise|out|narrow|tight|surgical|wide|broad|gentle|bell|the|on|in|for|to|at|of|with|a|an|it|them|and|'
            r'some|db|hz|around|about|near|band|q|by|little|bit|touch|set|put|give|make|frequency|freq')
    eq = {'band': band, 'type': typ, 'freq': freq, 'gain': gain, 'q': q if q is not None else (
        0.85 if typ != 'bell' else 1.4), 'on': True}
    return _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'eq': dict(eq)}], None))


def _p_delay(C, ix, t):
    if not C.has(_w(r'\bdelay(?:ed)?\b|\btime ?align')):
        return None
    if re.search(r'\btime ?align', C.w) and not MS_RX.search(C.w):
        return _ask('Say the time, like "delay the OH 2 ms".', 'delay_polarity')
    C.take_all(_w(r'\bdelay(?:ed)?\b|\btime ?align(?:ed|ment)?\b'))
    on = _onoff(C, True)
    ms = None
    m = C.take(MS_RX)
    if m:
        ms = float(m.group(1)) * (1000.0 if m.group(2).startswith('s') else 1.0)
    elif on:
        m = C.take(_w(r'\b(?:by|of|to|at)\s*(\d+(?:\.\d+)?)\b'))
        if m:
            ms = float(m.group(1))
    if on and ms is None:
        return R('pending', conf=0.5, intent='add_fx') if re.search(r'\b(?:add|on|a)\b', C.t) and \
            not re.search(r'\bms\b', C.t) else _ask('Say the time, like "delay the OH 2 ms".', 'delay_polarity')
    if ms is not None and not 0.0 <= ms <= 1300.0:
        return _ask('Channel delay goes up to 1300 ms.', 'delay_polarity')
    C.blank(r'set|put|add|give|the|on|in|for|to|at|of|with|a|an|it|them|and|by|ms|channel|input')
    val = 0.0 if not on else ms
    return _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'delay_ms': val}], None))


def _p_polarity(C, ix, t):
    if not C.has(_w(r'\b(?:polarity|phase|invert(?:ed)?|flip|reverse)\b')):
        return None
    if re.search(r'\bflip\b', C.w) and re.search(r'\bview\b', C.w):
        return None
    toggle = re.search(r'\b(?:flip|reverse|swap|toggle)\b', C.w) is not None
    C.take_all(_w(r'\b(?:polarity|phase|invert(?:ed)?|flip(?:ped)?|reverse(?:d)?|toggle|swap)\b'))
    off = re.search(r'\b(?:off|normal|back|undo|uninvert|un-invert|remove|kill|reset)\b', C.w) is not None
    C.blank(r'off|normal|back|undo|uninvert|un-invert|remove|kill|reset|on|the|in|for|to|of|it|them|and|set|put|180|'
            r'make|turn|switch|degrees?|please|channel|check')

    def make(tg):
        if not toggle:
            return [{'op': 'set', 'target': tg.selector(ix), 'polarity': not off}], None
        groups = {}
        for n in tg.ns(ix):
            cur = bool(ix.by_n[n].raw.get('polarity'))
            groups.setdefault(not cur, []).append(n)
        return [{'op': 'set', 'target': {'channels': ns} if len(groups) > 1 or not tg.all else tg.selector(ix),
                 'polarity': v} for v, ns in sorted(groups.items(), key=lambda kv: kv[1][0])], None
    return _with_target(C, ix, make)


def _p_trim(C, ix, t):
    if not C.has(_w(r'\b(?:trim|digital gain|digi gain)\b')):
        return None
    C.take_all(_w(r'\b(?:digital |digi )?(?:trim|gain)\b'))
    return _level_change(C, ix, 'set', 'trim_db', lambda c: c.raw.get('trim_db') if c.raw.get('trim_db') is not None
                         else 0.0, lo=-40.0, hi=40.0, what='trim')


def rec_fader_mute(raw, C, ix, ctx):
    t = C.t
    mm = re.match(r'^(?P<un>un-?)?mute\s+(?P<rest>.+)$', t) or re.match(r'^(?P<rest>.+?)\s+(?P<un>un-?)?muted?$', t) or \
        re.match(r'^(?P<kill>kill|silence|shut off|turn off|switch off|shut up)\s+(?P<rest>.+)$', t)
    if mm and not FX_ANY.search(t) and not re.search(r'\b(?:aux|mix|group|ears?|iem|wedge|pa|mains?)\b', t):
        on = not (mm.groupdict().get('un'))
        rest = mm.group('rest')
        tg = resolve_target(rest, ix, allow_all=True)
        if tg.empty and not tg.missing:
            return None
        return _target_result(tg, rest, ix, lambda tg_: ([{'op': 'set', 'target': tg_.selector(ix), 'mute': on}], None),
                              'set')
    fader = re.search(r'\b(?:fader|faders|level|levels|volume|vol)\b', t)
    unity = re.search(r'\b(?:unity|0 ?db|zero)\b', t)
    rel = re.search(r'^(?:turn|bring|push|pull|raise|lower|drop|bump|nudge|tuck|ride|make)\b|'
                    r'\b(?:louder|quieter|softer|up|down)\b', t)
    if not (fader or rel):
        return None
    if FX_ANY.search(t) or re.search(r'\b(?:aux|mix|ears?|iem|wedge|gain|trim|preamp|hpf|lpf|eq|gate|comp|threshold)\b',
                                     t):
        return None
    C.blank(r'fader|faders|level|levels|volume|vol')
    if unity and not re.search(r'\b(?:up|down|louder|quieter)\b\s*\d', t):
        C.blank(r'unity|0 ?db|zero|at|to|set|put|bring|push|pull|all|the|on|for|it|them')
        return _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'fader_db': 0.0}], None))
    return _level_change(C, ix, 'set', 'fader_db', lambda c: c.raw.get('fader_db'), lo=-150.0, hi=10.0,
                         what='fader')


def rec_recipe(raw, C, ix, ctx):
    t = C.t
    for rx, f, g, typ, q in RECIPES:
        m = rx.search(t)
        if not m:
            continue
        C.take(_w(re.escape(m.group(0))))
        C.blank(r'make|the|less|more|too|is|are|sounds?|sounding|a bit|a little|bit|little|way|much|so|very|it|them|'
                r'on|in|for|needs?|need|some|get|give|add|can|we|i|really|kinda|kind of|sort of|pretty|bit of|of|'
                r'a touch|touch|slightly|to|with|and|up|just|that|this|those|these|feels?|seem|seems|getting|got|'
                r'has|have|there|way too|too much|hey|yo|ok|okay|so')
        band = 1 if typ == 'low_shelf' else 4 if typ == 'high_shelf' else (
            1 if f < 200 else 2 if f < 1000 else 3 if f < 5000 else 4)
        eq = {'band': band, 'type': typ, 'freq': float(f), 'gain': g, 'q': q, 'on': True}
        r = _with_target(C, ix, lambda tg: ([{'op': 'set', 'target': tg.selector(ix), 'eq': dict(eq)}], None),
                         conf=0.7)
        r.kind = 'recipe'
        return r
    return None


RECOGNIZERS = [('rename', None), ('mixes', rec_mixes), ('buses', rec_buses), ('fx', rec_fx),
               ('add_channels', rec_add_channels), ('remove_channels', rec_remove_channels), ('move', rec_move),
               ('stereo', rec_stereo), ('patch', rec_patch), ('template', rec_template), ('send', rec_send),
               ('processing', rec_processing), ('preamp', rec_preamp), ('fader', rec_fader_mute),
               ('recipe', rec_recipe)]

FORCE = {'hpf': ('hpf ', rec_processing), 'lpf': ('lpf ', rec_processing), 'gate': ('gate ', rec_processing),
         'comp': ('comp ', rec_processing), 'mustard': ('mustard ', rec_processing),
         'eq': ('', rec_recipe), 'fader': ('', rec_fader_mute), 'mute': ('mute ', rec_fader_mute),
         'send_fx': ('', rec_send), 'send_mix': ('', rec_send), 'route_group': ('', rec_send),
         'phantom': ('48v ', rec_preamp), 'gain': ('gain ', rec_preamp), 'template': ('apply the templates to ',
                                                                                    rec_template),
         'stereo': ('', rec_stereo), 'mixes': ('', rec_mixes), 'add_fx': ('', rec_fx), 'remove_fx': ('', rec_fx),
         'remove_channels': ('', rec_remove_channels), 'add_channels': ('', rec_add_channels),
         'move': ('', rec_move), 'patch': ('', rec_patch), 'delay_polarity': ('', rec_processing)}


def _canon(t):
    t = ' ' + t + ' '
    for rx, rep in CANON:
        t = rx.sub(rep, t)
    t = NUM_RX.sub(lambda m: str(NUMW[m.group(1)]), t)
    t = re.sub(r'(?<=\d)\s*(?:st|nd|rd|th)\b', '', t)
    t = re.sub(r'\bch\s+(\d{1,3})\s*(?:-|thru|to)\s*ch\s+(\d)', r'ch \1-\2', t)
    return re.sub(r'\s+', ' ', t).strip()


def _fix_typos(raw, ix):
    """Fix misspelt command words (difflib, cutoff 0.82, words of 4+ letters). Names in quotes and channel-name words
    stay as typed. -> (text, number of fixes)."""
    out, fixes = [], 0
    quoted = False
    for tok in re.split(r'([A-Za-z]+)', raw):
        if '"' in tok and tok.count('"') % 2:
            quoted = not quoted
        if not tok or not tok.isalpha() or quoted or (len(tok) < 4 and tok.lower() not in SHORT_TYPOS):
            out.append(tok)
            continue
        lo = tok.lower()
        if lo in SHORT_TYPOS and lo not in ix.name_words:
            out.append(SHORT_TYPOS[lo])
            fixes += 1
            continue
        if lo in VOCAB_SET or lo in ix.name_words or lo in COMMON:
            out.append(tok)
            continue
        cand = difflib.get_close_matches(lo, VOCAB, n=1, cutoff=0.82)
        if cand:
            out.append(cand[0])
            fixes += 1
        else:
            out.append(tok)
    return ''.join(out), fixes


VOCAB_SET = set(VOCAB)
COMMON = set('''
with that this them they then than there their make sure some more less into onto from have want need give take turn
bring push pull drop pair link unlink split move swap name call label lead vocal vocals singer kick snare overheads
please every everything except only just also back over under above below after before when where which what across
each both make made like sound sounds sounding song songs show tour room hall plate slap echo verb delay mute unmute
gate gates comp comps fader faders group groups templates template stereo mono patch rack local input inputs start
starting first last end beginning bottom middle half quarter whole same other others another extra spare guest tracks
track click talkback audience crowd keys piano organ synth synths bass guitar guitars acoustic electric drums drum
toms floor rack hihat hats ride crash cymbals horns strings choir perc percussion loud louder quiet quieter boost
cut notch shelf high low band wide narrow fast slow soft hard knee ratio attack release hold range threshold
makeup output parallel blend wet dry phase polarity invert flip reverse trim gain preamp phantom view mustard fet
opto optical classic levamp leveling vca channel channels everyone everybody drummer bassist guitarist keyboardist
singers player players people musicians mixes mix ears wedge wedges monitor monitors stage local remove delete
insert apply reset ditch lose kill engage enable disable bypass create append tack scrap
'''.split())


SHORT_TYPOS = {'gat': 'gate', 'gats': 'gates', 'hpd': 'hpf', 'hfp': 'hpf', 'hpg': 'hpf', 'lfp': 'lpf', 'lpd': 'lpf',
               'vxo': 'vox', 'cmop': 'comp', 'cmp': 'comp', 'mtue': 'mute', 'muet': 'mute', 'eqq': 'eq', 'qe': 'eq',
               'verbb': 'verb', 'vebr': 'verb', 'vrb': 'verb', 'reanme': 'rename', 'renmae': 'rename',
               'mustrd': 'mustard', 'mstrd': 'mustard', 'phanton': 'phantom', 'gaet': 'gate', 'tmos': 'toms'}
FRAGILE = {'in', 'out', 'on', 'off', 'up', 'down', 'to', 'at', 'a', 'an', 'the', 'and', 'of', 'for', 'with', 'it', 'by',
           'no', 'all', 'more', 'less', 'mix', 'aux'}


def _protect_names(t, ix):
    """'put the fet on kick in' -> 'put the fet on ch 1': a channel name with a word the readers would strip ("In",
    "Out", "and", "/") becomes its number before the clause is read. Not when the name runs into an article
    ("put the kick in the slap" keeps its words)."""
    for c in sorted(ix.chans, key=lambda c: -len(c.norm)):
        if len(c.toks) < 2 or not (set(c.toks) & FRAGILE or re.search(r'[/&+,]', c.name)):
            continue
        rx = r'(?<![\w])' + r'[\s_./&+-]*'.join(re.escape(w) for w in c.toks) + \
            r'(?![\w])(?!\s+(?:the|a|an|his|her|their|my|our|your|everyone|every|all)\b)'
        t = re.sub(rx, 'ch %d' % c.n, t)
    return t


def _split_clauses(text):
    """Hard breaks (; newline . then also), then commas / 'and' where an action word starts the next part."""
    parts = []
    for seg in re.split(r'\s*(?:;|\n|(?<=[a-z])\.\s+|!\s*|\bthen\b|\band then\b|\balso\b|\bafter that\b)\s*', text,
                        flags=re.I):
        seg = seg.strip(' ,.')
        if not seg:
            continue
        cur = ''
        pieces = re.split(r'(\s*,\s*|\s+and\s+|\s*&\s*(?=[a-z]{3}))', seg, flags=re.I)
        i = 0
        while i < len(pieces):
            p = pieces[i]
            if i % 2 == 1:
                nxt = pieces[i + 1] if i + 1 < len(pieces) else ''
                if ACTION_START.match(_canon(nxt.strip().lower())) and cur.strip():
                    parts.append(cur.strip(' ,'))
                    cur = ''
                else:
                    cur += p
            else:
                cur += p
            i += 1
        if cur.strip(' ,'):
            parts.append(cur.strip(' ,'))
    return parts


def parse(text, model, use_jev=None):
    t0 = time.perf_counter()
    out = {'ops': [], 'summary': '', 'confidence': 0.0, 'unrecognized': [], 'examples': [], 'ask': [],
           'jev': {'calls': 0, 'ms': 0.0, 'used': False}, 'ms': 0.0}
    try:
        ix = index(model)
        _parse(text, ix, out, use_jev)
    except Exception as e:
        out['ops'] = []
        out['unrecognized'] = [str(text)[:200]]
        out['ask'] = ['I could not read that. Try one change at a time, like "hpf the vocals at 120".']
        out['error'] = '%s: %s' % (type(e).__name__, str(e)[:200])
        try:
            out['examples'] = examples(index(model))
        except Exception:
            out['examples'] = ['hpf the vocals at 120', 'gate the toms', 'rename 12 to Keys L']
    out['ms'] = round((time.perf_counter() - t0) * 1000, 1)
    return out


def _parse(text, ix, out, use_jev):
    text = _ascii(text)[:MAX_TEXT]
    if not text:
        out['examples'] = examples(ix)
        out['ask'].append('Tell it what to change, like "%s".' % out['examples'][0])
        return
    if re.match(r'(?i)^\s*(?:re-?name|name|call|label|title|retitle)\b|.*\b(?:called|named)\b', text):
        fixed, nfix = text, 0
    else:
        fixed, nfix = _fix_typos(text, ix)
    clauses = _split_clauses(fixed)
    results = []
    for raw in clauses:
        C = Clause(raw, _protect_names(_canon(raw.lower()), ix))
        C.fixes = nfix
        r = _read_clause(raw, C, ix, {})
        results.append([raw, C, r])
    want = _want_jev(use_jev)
    qs, plan = {}, []
    for i, (raw, C, r) in enumerate(results):
        if r is None or (r.kind == 'pending'):
            if want:
                qs['i%d' % i] = (_INTENT_Q.format(cmd=raw[:200]), INTENTS)
                qs['t%d' % i] = (_TARGET_Q.format(cmd=raw[:200], phrase=raw[:120]), _target_options(ix))
                plan.append(i)
        elif r.target is not None and r.target.missing and not r.target.notes:
            if want:
                ph = ' and '.join(r.target.missing)
                qs['t%d' % i] = (_TARGET_Q.format(cmd=raw[:200], phrase=ph[:120]), _target_options(ix))
                plan.append(i)
    jres = {}
    if qs:
        from sessionmaker import intake
        jres, info = intake.jev_choices({'console': (ix.model.get('console') or {}).get('label') or 'DiGiCo',
                                         'channels': [c.name for c in ix.chans][:96]}, qs, timeout=JEV_BUDGET_S)
        out['jev'] = {'calls': info.get('calls', 0), 'ms': info.get('ms', 0.0), 'used': True,
                      'error': info.get('error')}
    for i in plan:
        raw, C, r = results[i]
        it, tt = jres.get('i%d' % i), jres.get('t%d' % i)
        if r is None or r.kind == 'pending':
            intent = r.intent if (r is not None and r.intent) else None
            if it and it['p'] >= JEV_ACCEPT and it['orders'] == 2:
                intent = it['choice']
            if intent in ('vague', 'not_edit') or intent is None:
                continue
            pre, fn = FORCE.get(intent, ('', None))
            if fn is None:
                results[i][2] = _ask(ASK_FOR.get(intent, 'Say it another way.'), intent)
                continue
            C2 = Clause(pre + raw, _canon((pre + raw).lower()))
            r2 = fn(pre + raw, C2, ix, {})
            if r2 is None or r2.kind == 'pending':
                results[i][2] = _ask(ASK_FOR.get(intent, 'Say it another way.'), intent)
                continue
            r2.conf = min(r2.conf, it['p'] if it else 0.7)
            results[i][1], results[i][2] = C2, r2
            r = r2
        if r.target is not None and (r.target.missing or r.target.empty) and tt and tt['p'] >= JEV_ACCEPT and \
                tt['orders'] == 2 and tt['choice'] != 'none':
            got = _target_from_option(tt['choice'], ix)
            if got:
                r.target.missing = []
                r.target.chans += got
                r.target.labels.append(_names(ix, got))
                r.target.conf = min(r.target.conf, tt['p'])
                r.conf = min(r.conf, tt['p'])
    for i, item in enumerate(results):
        raw, C, r = item
        if r is None or r.make is None or r.target is None:
            continue
        if r.target.empty and not r.target.missing:
            src = None
            for j in list(range(i - 1, -1, -1)) + list(range(i + 1, len(results))):
                o = results[j][2]
                if o is not None and o.target is not None and not o.target.empty and not o.target.missing and \
                        (j < i or o.kind in ('set', 'recipe')):
                    src = o.target
                    break
            if src is not None:
                r.target = src
                r.conf = min(r.conf, 0.85)
    ops_all, sims = [], _Sim(ix)
    for raw, C, r in results:
        if r is None or r.kind == 'pending':
            out['unrecognized'].append(raw)
            continue
        if r.kind == 'ask':
            out['unrecognized'].append(raw)
            out['ask'].append(r.ask)
            continue
        ops = r.ops
        if r.make is not None:
            tg = r.target
            if tg is None or tg.missing or tg.empty:
                out['unrecognized'].append(raw)
                if tg is not None and tg.notes:
                    out['ask'].append(' '.join(tg.notes))
                else:
                    miss = ' and '.join(tg.missing) if tg is not None and tg.missing else ''
                    out['ask'].append(('Which channels are "%s"? Say names or numbers, like "%s".' % (
                        miss, _example_for(r, ix))) if miss else 'Which channels? Say names or numbers, like "%s".'
                        % _example_for(r, ix))
                continue
            ops, ask = r.make(tg)
            if ask:
                out['unrecognized'].append(raw)
                out['ask'].append(ask)
                continue
        conf = r.conf * (0.9 if C.fixes else 1.0) * (r.target.conf if r.target is not None else 1.0)
        for op in ops:
            op = sims.renumber(op)
            ops_all.append((op, conf, r.kind))
            sims.apply(op)
    out['ops'] = [o for o, _, _ in ops_all]
    out['summary'] = ' '.join(describe(o, ix) for o in out['ops'])
    if ops_all:
        out['confidence'] = round(min(c for _, c, _ in ops_all) * (0.8 if out['unrecognized'] else 1.0), 2)
        if any(k == 'recipe' for _, _, k in ops_all):
            out['summary'] += ' (A starting move. Undo it if it is not what you meant.)'
    else:
        out['confidence'] = 0.0
        out['examples'] = examples(ix)
        if not out['ask']:
            out['ask'].append('I did not catch that. Try one of these: %s.' % '; '.join(
                '"%s"' % e for e in out['examples']))


def _read_clause(raw, C, ix, ctx):
    r = rec_rename(raw, C, ix, ctx)
    if r is not None:
        return r
    for name, fn in RECOGNIZERS[1:]:
        C2 = Clause(C.raw, C.t)
        C2.fixes = C.fixes
        r = fn(raw, C2, ix, ctx)
        if r is not None:
            C.w = C2.w
            return r
    return None


def _example_for(r, ix):
    v = next((c for c in ix.chans if c.cat in VOCAL), ix.chans[0] if ix.chans else None)
    nm = v.name if v else '12'
    return {'set': 'the vocals', 'send': nm, 'preamp': '1-4', 'patch': '1-24'}.get(r.kind, nm)


def _want_jev(use_jev):
    from sessionmaker import intake
    on = intake.jev_enabled()
    return on if use_jev is None else bool(use_jev) and on


_INTENT_Q = ('A live sound engineer typed this command into a DiGiCo mixing console session editor: "{cmd}". '
             'Which kind of edit does it ask for?')
_TARGET_Q = ('A live sound engineer typed this command into a DiGiCo mixing console session editor: "{cmd}". '
             'Which channel or group of channels does "{phrase}" mean?')


def _target_options(ix):
    opts = {}
    seen = set()
    for key, lab, rx, sel in GROUPS:
        if key in ('mono', 'stereo', 'instruments'):
            continue
        g = _group_match(rx.pattern.strip('^$').split('|')[0].replace('(?:', '').replace(')', '').replace('?', ''), ix)
        chans = [c.n for c in ix.chans if (sel(c) if callable(sel) else c.cat in sel)]
        del g
        if chans and tuple(chans) not in seen and len(chans) > 1:
            seen.add(tuple(chans))
            opts['g_' + key] = 'All the %s: %s' % (lab, ', '.join(ix.by_n[n].name for n in chans[:8]))
    for c in ix.chans[:200]:
        opts['c%d' % c.n] = 'Channel %d "%s" (%s)' % (c.n, c.name, T.labels().get(c.cat, 'other') if c.cat else
                                                       'other')
    opts['none'] = 'None of these channels, or it is not clear'
    return opts


def _target_from_option(choice, ix):
    if choice.startswith('c') and choice[1:].isdigit():
        n = int(choice[1:])
        return [n] if n in ix.by_n else []
    if choice.startswith('g_'):
        key = choice[2:]
        for k, lab, rx, sel in GROUPS:
            if k == key:
                return [c.n for c in ix.chans if (sel(c) if callable(sel) else c.cat in sel)]
    return []


class _Sim:
    """Channel order while the ops of one command run, so each op names the surface numbers of its own moment.
    Ops are built against the model's numbers; renumber() maps them onto the order after the earlier ops (add,
    remove, move and stereo pairs change it) and turns a move's place ('_to') into the final position 'to'."""

    def __init__(self, ix):
        self.order = [c.n for c in ix.chans]

    def _pos(self, n):
        try:
            return self.order.index(n) + 1
        except ValueError:
            return None

    def renumber(self, op):
        op = dict(op)
        tg = op.get('target')
        if isinstance(tg, dict) and 'channels' in tg:
            op['target'] = {'channels': sorted(p for p in (self._pos(n) for n in tg['channels']) if p)}
        spec = op.pop('_to', None)
        if op['op'] == 'move' and spec is not None:
            moving = [self.order[p - 1] for p in op['target']['channels']]
            rest = [n for n in self.order if n not in moving]
            if spec[0] == 'end':
                to = len(rest) + 1
            elif spec[0] == 'start':
                to = 1
            elif spec[0] == 'pos':
                to = min(spec[1], len(rest) + 1)
            else:
                k = rest.index(spec[1]) + 1 if spec[1] in rest else len(rest)
                to = k + 1 if spec[0] == 'after' else k
            op['to'] = max(1, to)
        if op['op'] == 'add_channels' and op.get('at'):
            p = self._pos(op['at'])
            op['at'] = p if p else None
        return op

    def apply(self, op):
        k = op['op']
        if k == 'add_channels':
            at = op.get('at')
            add = [None] * int(op.get('count') or 1)
            if at is None:
                self.order += add
            else:
                self.order[at - 1:at - 1] = add
        elif k == 'remove_channels':
            tg = op.get('target') or {}
            if tg.get('all'):
                self.order = []
            else:
                drop = {p - 1 for p in tg.get('channels', []) if 0 < p <= len(self.order)}
                self.order = [n for i, n in enumerate(self.order) if i not in drop]
        elif k == 'move':
            ps = op['target']['channels']
            moving = [self.order[p - 1] for p in ps if 0 < p <= len(self.order)]
            rest = [n for i, n in enumerate(self.order) if i + 1 not in ps]
            to = max(1, min(op['to'], len(rest) + 1))
            self.order = rest[:to - 1] + moving + rest[to - 1:]
        elif k == 'stereo' and op.get('on') and len(op['target']['channels']) == 2:
            p2 = op['target']['channels'][1]
            if 0 < p2 <= len(self.order):
                del self.order[p2 - 1]
        elif k == 'stereo' and not op.get('on') and op.get('split'):
            p = op['target']['channels'][0]
            if 0 < p <= len(self.order):
                self.order[p:p] = [None]


def _tgt(op, ix):
    tg = op.get('target') or {}
    if tg.get('all'):
        return 'every channel'
    return _names(ix, tg.get('channels') or [])


def _hz(f):
    f = float(f)
    return ('%g kHz' % round(f / 1000.0, 2)) if f >= 1000 else '%g Hz' % round(f)


def _db(v):
    return '%+g dB' % round(float(v), 1) if float(v) != 0 else '0 dB'


def describe(op, ix=None):
    """One plain sentence for an op (no em dashes)."""
    ix = ix or Index({})
    k = op.get('op')
    on = lambda d: d.get('on', True)
    try:
        if k == 'set':
            tg = _tgt(op, ix)
            for f in ('hpf', 'lpf'):
                if f in op:
                    d = op[f]
                    if not on(d):
                        return '%s off on %s.' % (f.upper(), tg)
                    return '%s %s on %s.' % (f.upper(), 'at ' + _hz(d['freq']) if d.get('freq') else 'on', tg)
            if 'eq' in op:
                d = op['eq']
                kind = {'low_shelf': 'low shelf', 'high_shelf': 'high shelf'}.get(d.get('type'), 'bell')
                return 'EQ band %d %s %s at %s (Q %g) on %s.' % (d['band'], kind, _db(d['gain']), _hz(d['freq']),
                                                               d.get('q') or 1.0, tg)
            if 'eq_on' in op:
                return 'EQ %s on %s.' % ('in' if op['eq_on'] else 'out', tg)
            for f, lab in (('gate', 'Gate'), ('comp', 'Comp'), ('mustard', 'Mustard comp')):
                if f in op:
                    d = op[f]
                    if not on(d):
                        return '%s off on %s.' % (lab, tg)
                    bits = []
                    if d.get('model'):
                        bits.append({'fet': 'FET', 'vca': 'VCA', 'optical': 'Optical', 'levamp': 'Leveling Amp',
                                     'classic': 'Classic'}.get(d['model'], d['model']))
                    if 'thr' in d:
                        bits.append('threshold %g dB' % d['thr'])
                    if 'ratio' in d:
                        bits.append('%g:1' % d['ratio'])
                    for kk, nm in (('attack', 'attack'), ('release', 'release'), ('hold', 'hold')):
                        if kk in d:
                            bits.append('%s %g ms' % (nm, d[kk]))
                    if 'range' in d:
                        bits.append('range %g dB' % d['range'])
                    if 'knee' in d:
                        bits.append('%s knee' % d['knee'])
                    if 'makeup' in d:
                        bits.append('makeup %s' % _db(d['makeup']))
                    if 'out' in d:
                        bits.append('output %s' % _db(d['out']))
                    if 'mix' in d:
                        bits.append('mix %d%%' % round(d['mix'] * 100))
                    return '%s on %s%s.' % (lab, tg, (' (' + ', '.join(bits) + ')') if bits else '')
            if 'delay_ms' in op:
                return ('Delay off on %s.' % tg) if not op['delay_ms'] else 'Delay %g ms on %s.' % (op['delay_ms'], tg)
            if 'polarity' in op:
                return 'Polarity %s on %s.' % ('inverted' if op['polarity'] else 'normal', tg)
            if 'trim_db' in op:
                return 'Trim %s on %s.' % (_db(op['trim_db']), tg)
            if 'fader_db' in op:
                return 'Fader at %s on %s.' % (_db(op['fader_db']), tg)
            if 'mute' in op:
                return '%s %s.' % ('Mute' if op['mute'] else 'Unmute', tg)
            if 'view' in op:
                return '%s view on %s.' % ('Mustard' if op['view'] == 'mustard' else 'SD', tg)
            return 'Change %s.' % tg
        if k == 'rename':
            return 'Rename %s to "%s".' % (_tgt(op, ix), op.get('name'))
        if k == 'name_bus':
            return 'Rename %s %d to "%s".' % (op.get('bus'), op.get('n'), op.get('name'))
        if k == 'stereo':
            chs = (op.get('target') or {}).get('channels') or []
            if op.get('on') and len(chs) == 2:
                return 'Make %s one stereo channel.' % _tgt(op, ix)
            if op.get('on'):
                return 'Make %s stereo.' % _tgt(op, ix)
            return ('Split %s into two mono channels.' if op.get('split') else 'Make %s mono.') % _tgt(op, ix)
        if k == 'move':
            return 'Move %s to position %d.' % (_tgt(op, ix), op.get('to'))
        if k == 'add_channels':
            n = op.get('count', 1)
            what = '%d %s channel%s' % (n, 'stereo' if op.get('stereo') else 'mono', '' if n == 1 else 's')
            nm = (' named %s' % ', '.join('"%s"' % x for x in op['names'])) if op.get('names') else ''
            where = ' at position %d' % op['at'] if op.get('at') else ' at the end'
            return 'Add %s%s%s.' % (what, nm, where)
        if k == 'remove_channels':
            return 'Delete %s.' % _tgt(op, ix)
        if k == 'apply_template':
            cat = op.get('category')
            return 'Apply %s to %s.' % (('the %s template' % T.labels().get(cat, cat).split(' (')[0].lower())
                                        if cat else 'each channel\'s own template', _tgt(op, ix))
        if k == 'send':
            tg = _tgt(op, ix)
            if 'group' in op:
                g = next((x['name'] for x in ix.groups if x['n'] == op['group']), '')
                lab = 'group %d%s' % (op['group'], (' (%s)' % g) if g and g != 'Grp %d' % op['group'] else '')
                return ('Route %s to %s.' if op.get('on', True) else 'Take %s out of %s.') % (tg, lab)
            lab = _aux_label(ix, op.get('aux'))
            if not op.get('on', True):
                return 'Turn off the send from %s to %s.' % (tg, lab)
            bits = []
            if 'level_db' in op:
                bits.append('at %s' % _db(op['level_db']))
            if op.get('pre'):
                bits.append(op['pre'] + '-fader')
            return 'Send %s to %s%s.' % (tg, lab, (' ' + ', '.join(bits)) if bits else '')
        if k == 'patch':
            tg = _tgt(op, ix)
            if op.get('mode') == 'none':
                return 'Unpatch %s.' % tg
            return 'Patch %s to the %s%s.' % (tg, 'stage rack' if op.get('mode') == 'rack' else 'local inputs',
                                             (' from input %d' % op['start']) if op.get('start') else '')
        if k == 'preamp':
            tg = _tgt(op, ix)
            if 'gain_db' in op:
                return 'Preamp gain %s on %s.' % (_db(op['gain_db']), tg)
            if 'phantom' in op:
                return '48V %s for %s.' % ('on' if op['phantom'] else 'off', tg)
            if 'pad' in op:
                return 'Pad %s on %s.' % ('on' if op['pad'] else 'off', tg)
        if k == 'add_fx':
            from sessionmaker import options as O
            lab = O.FX_CHOICES.get(op.get('kind'), (None, None, None, None, op.get('kind')))[4]
            bits = []
            if op.get('feed_aux'):
                bits.append('fed by aux %d' % op['feed_aux'])
            if op.get('sends') == 'target' and op.get('target'):
                bits.append('with sends from %s' % _tgt(op, ix))
            return 'Add a %s%s.' % (lab.lower() if lab else 'effect', (' ' + ', '.join(bits)) if bits else '')
        if k == 'remove_fx':
            return 'Remove FX %d (%s).' % (op.get('fx'), _fx_name(ix, op.get('fx')))
        if k == 'mixes':
            bits = []
            if 'stereo' in op:
                bits.append('%d IEM mix%s' % (op['stereo'], '' if op['stereo'] == 1 else 'es'))
            if 'mono' in op:
                bits.append('%d wedge mix%s' % (op['mono'], '' if op['mono'] == 1 else 'es'))
            return 'Set up %s.' % ' and '.join(bits)
        if k == 'buses':
            if op.get('auto'):
                return 'Set the bus layout to automatic.'
            return 'Bus layout: %d mono and %d stereo auxes, %d mono and %d stereo groups.' % (
                op['aux_mono'], op['aux_stereo'], op['grp_mono'], op['grp_stereo'])
    except Exception:
        pass
    return 'Change: %s.' % json.dumps({x: y for x, y in op.items() if x != 'op'})[:120]


def examples(ix):
    """Three commands that work on this session, with its own names."""
    if not isinstance(ix, Index):
        ix = index(ix)
    voc = next((c for c in ix.chans if c.cat == 'lead_vocal'), None) or next((c for c in ix.chans if c.cat in VOCAL),
                                                                            None)
    kick = next((c for c in ix.chans if c.cat in ('kick_in', 'snare_top')), None)
    first = ix.chans[0] if ix.chans else None
    out = ['hpf the vocals at 120' if voc else 'hpf everything at 80']
    if kick and ix.quantum:
        out.append('Mustard FET on %s' % kick.name)
    elif kick:
        out.append('gate the toms' if any(c.cat in ('rack_tom', 'floor_tom') for c in ix.chans) else
                   'comp %s 4:1 at -20' % kick.name)
    else:
        out.append('48v on 1-4')
    out.append('rename %d to Keys L' % (first.n if first else 12))
    return out[:3]


def _load_model(path):
    if path.endswith('.json'):
        with open(path) as f:
            return json.load(f)
    from sessionmaker import inspect as I
    with open(path, 'rb') as f:
        return I.inspect(f.read())


def main(argv):
    if len(argv) < 3:
        print(__doc__.split('\n\n')[0])
        return 2
    model = _load_model(argv[1])
    res = parse(' '.join(argv[2:]), model)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
