"""taxonomy.py - the channel categories the session maker writes processing for.

The canonical set is the 50 template ids in data/templates.json (built from 39 real
sessions by a build script (not published)) plus 'other'. A channel's category picks its processing
template (HPF, LPF, EQ, gate, comp, Mustard) in build.py.

Three rule layers place a channel name, first hit wins:

  1. list-context rules (this file, LIST_RULES): things an INPUT LIST means differently from a
     session. On a stage input list "Room" is a drum room mic, not a reverb return; "Spare Vox" is
     a patched vocal, not an unused line.
  2. the template rules (templates.json meta.taxonomy.rules): the exact regexes that labelled the
     2,415 session channels the templates were measured on. Applied to the normalised name.
  3. the input-list parser's coarse rules (listparse.CAT_RULES, 28 ids), refined to the 50 ids by
     refine() with the words in the name ("snare" + "bot" -> snare_bottom).
  then mic hints (Beta 91 -> kick_in, e906 -> electric_guitar) and the section heading.

rule_category() returns (category, confidence, why). Confidence >= 0.6 means the rules are sure;
intake.classify() sends the rest to the classifier.

Also here: COARSE_TO_FINE / FINE_TO_COARSE (the parser's old 28 ids <-> the 50), the one-line
option texts the classifier sees (JEV_OPTIONS) and is_bare_spare() for rows that are not channels.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'templates.json')

_T = None


def _templates():
    global _T
    if _T is None:
        with open(TEMPLATES_JSON) as f:
            _T = json.load(f)
    return _T


# --------------------------------------------------------------------------------------------
# the category set
# --------------------------------------------------------------------------------------------

def category_ids():
    """The 50 template ids in group order (drums, bass, guitars_strings, keys, vocals, playback,
    ambience, fx_returns, comms), then 'other'."""
    t = _templates()
    return [c for g in t['groups'].values() for c in g] + ['other']


def labels():
    """{id: human label} for the UI dropdown."""
    t = _templates()
    out = {k: v['label'] for k, v in t['categories'].items()}
    out['other'] = 'Other (no template: flat channel)'
    return out


def options():
    """[{'id', 'label', 'group'}] in group order, for the page's category dropdown."""
    lab, grp = labels(), groups()
    return [{'id': c, 'label': lab[c], 'group': grp[c]} for c in category_ids()]


def groups():
    """{id: group name}."""
    t = _templates()
    out = {c: g for g, cs in t['groups'].items() for c in cs}
    out['other'] = 'other'
    return out


# Option texts for the classifier. Each says what the source is and lists the short names engineers use,
# because the classifier sees 8-character console names. Order matters only for display; intake asks in
# both orders and averages.
JEV_OPTIONS = {
    'kick_in': 'Kick drum mic inside the drum or the only kick mic (Kick, Kick In, KIK, BD, K In, Beta91)',
    'kick_out': 'Kick drum mic outside the front head (Kick Out, K Out, Kick 52)',
    'kick_sub': 'Sub kick (Subkick, Kick Sub, speaker-cone mic on the kick)',
    'snare_top': 'Snare drum top mic, or a second snare (Snare, Snr Top, SN1, Snare 2)',
    'snare_bottom': 'Snare drum bottom mic (Snr Bot, SN Btm, Snare Under)',
    'hihat': 'Hi-hat mic (HH, Hat, Hats)',
    'rack_tom': 'Rack tom mic (Tom 1, Rack, R Tom, T1)',
    'floor_tom': 'Floor tom mic (Floor, Flr, FT, Tom 3, Big Floor)',
    'roto_tom': 'Roto tom mic',
    'overheads': 'Drum overheads or drum room mics over / in front of the kit (OH, OH L, Cymbals, Room, VP88)',
    'ride': 'Ride cymbal mic',
    'drum_crotch': 'Drum crotch or knee mic between kick and snare',
    'drum_trigger': 'Drum trigger signal from a kick/snare/tom trigger (Kick Trig, KIK TG, Sn Trig)',
    'sample_pad': 'Electronic drum or sample pad output (SPD-SX, Octapad, drum pad, e-kit)',
    'hand_perc': 'Hand percussion (cajon, djembe, congas, shaker, tambourine, washboard, porch board, stomp box)',
    'bass_di': 'Bass guitar DI or clean bass line (Bass, Bass DI, B DI, Upright)',
    'bass_amp': 'Bass amp mic or dirty / drive bass DI (Bass Mic, Bass Amp, B Mic)',
    'synth_bass': 'Synth bass or key bass (Moog, Synth Bass, Key Bass)',
    'electric_guitar': 'Electric guitar amp mic, modeller or DI, lap or pedal steel (EG, Gtr 1, Ele, Amp, Kemper, Helix)',
    'acoustic_guitar': 'Acoustic guitar (AG, Acu, Aco, Acoustic)',
    'folk_strings': 'Mandolin, banjo, dulcimer, dobro, fiddle',
    'strings': 'Orchestral bowed strings (violin, viola, cello, string section)',
    'horns': 'Brass or woodwind (trumpet, sax, trombone, flute, horn section)',
    'keys': 'Keyboard, Nord or generic keys rig (Keys, Key 1, Nord, Keylargo)',
    'piano': 'Piano (grand or upright piano mics, digital piano)',
    'organ': 'Organ (Hammond B3, Leslie, church organ)',
    'synth': 'Synthesizer (Prophet, Juno, OB-6, synth)',
    'lead_vocal': "The lead singer's or artist's vocal mic (Lead Vox, LV, the artist's name + Vox)",
    'vocal_generic': 'A backing or other band vocal mic (BGV, Vox 2, a player name + Vox, Guest)',
    'vocal_fx_mic': 'A vocal effects or distortion mic used as an effect',
    'vocal_ear_split': 'A second split of a vocal mic used only for in-ear monitors',
    'choir': 'Choir or ensemble mics',
    'speech_mic': 'Spoken word: MC, host, emcee, pastor, presenter, panel, lectern or headset mic',
    'tracks_music': 'Backing tracks or stems of music from a playback rig (Trax, Tracks, Loops, Stems, PB 1)',
    'tracks_drums_perc': 'Backing track stem of drums or percussion (T Drums, Drum Trax, Perc Trx)',
    'tracks_bass': 'Backing track stem of bass (T Bass, Bass Trax)',
    'tracks_vocals': 'Backing track stem of vocals or BGVs (T BGV, Vox Trx)',
    'click': 'Click track (metronome for the band, never in the PA)',
    'cues_guide': 'Spoken cues or guide track for the band (Cues, Guide)',
    'timecode': 'SMPTE / LTC timecode signal',
    'media_playback': 'Walk-in music, video, ProPresenter, laptop or iPod playback for the audience',
    'audience': 'Audience or crowd mics (Aud, Crowd, Amb, shotguns)',
    'measurement_ref': 'Measurement or reference mic (Ref, RTA, Smaart)',
    'test_signal': 'Pink noise, tone or a signal generator',
    'fx_reverb': 'Reverb effect return (Verb, Plate, Hall, Room verb, Shimmer)',
    'fx_delay': 'Delay effect return (Delay, Slap, Throw, Echo)',
    'fx_modulation': 'Modulation effect return (ADT, doubler, chorus, thickener)',
    'fx_other': 'Another effect return (FX 1 Rtn, Inst FX)',
    'talkback': 'Talkback mic for band or crew, not sent to the audience (TB, Drum TB, FOH TB, Shout)',
    'comms_radio': 'Comms or radio feed (Comms, Radio, VOG)',
    'other': 'None of the above, or a spare / unused channel',
}


# --------------------------------------------------------------------------------------------
# coarse (parser, 28 ids) <-> fine (templates, 50 ids)
# --------------------------------------------------------------------------------------------

# Default fine id for each coarse id when nothing in the name refines it (see refine()).
COARSE_TO_FINE = {
    'kick': 'kick_in', 'snare': 'snare_top', 'tom': 'rack_tom', 'hihat': 'hihat', 'overhead': 'overheads',
    'drum_room': 'overheads',            # no room-mic template; overheads is the closest processing
    'drum_trigger': 'drum_trigger', 'drum_pad': 'sample_pad', 'percussion': 'hand_perc', 'bass': 'bass_di',
    'electric_guitar': 'electric_guitar', 'acoustic_guitar': 'acoustic_guitar', 'keys': 'keys', 'strings': 'strings',
    'brass_wind': 'horns', 'lead_vocal': 'lead_vocal', 'backing_vocal': 'vocal_generic', 'vocal': 'vocal_generic',
    'choir': 'choir', 'speech': 'speech_mic', 'talkback': 'talkback', 'playback': 'tracks_music',
    'click_timecode': 'click', 'music_playback': 'media_playback', 'audience': 'audience', 'fx_return': 'fx_reverb',
    'utility': 'test_signal', 'spare': 'other', 'other': 'other',
}

# For scoring against the hand-labelled ground truth (which uses the 28 coarse ids).
FINE_TO_COARSE = {
    'kick_in': 'kick', 'kick_out': 'kick', 'kick_sub': 'kick', 'snare_top': 'snare', 'snare_bottom': 'snare',
    'hihat': 'hihat', 'rack_tom': 'tom', 'floor_tom': 'tom', 'roto_tom': 'tom', 'overheads': 'overhead',
    'ride': 'overhead', 'drum_crotch': 'overhead', 'drum_trigger': 'drum_trigger', 'sample_pad': 'drum_pad',
    'hand_perc': 'percussion', 'bass_di': 'bass', 'bass_amp': 'bass', 'synth_bass': 'bass',
    'electric_guitar': 'electric_guitar', 'acoustic_guitar': 'acoustic_guitar', 'folk_strings': 'acoustic_guitar',
    'strings': 'strings', 'horns': 'brass_wind', 'keys': 'keys', 'piano': 'keys', 'organ': 'keys', 'synth': 'keys',
    'lead_vocal': 'lead_vocal', 'vocal_generic': 'backing_vocal', 'vocal_fx_mic': 'backing_vocal',
    'vocal_ear_split': 'lead_vocal', 'choir': 'choir', 'speech_mic': 'speech', 'tracks_music': 'playback',
    'tracks_drums_perc': 'playback', 'tracks_bass': 'playback', 'tracks_vocals': 'playback', 'click': 'click_timecode',
    'cues_guide': 'click_timecode', 'timecode': 'click_timecode', 'media_playback': 'music_playback',
    'audience': 'audience', 'measurement_ref': 'utility', 'test_signal': 'utility', 'fx_reverb': 'fx_return',
    'fx_delay': 'fx_return', 'fx_modulation': 'fx_return', 'fx_other': 'fx_return', 'talkback': 'talkback',
    'comms_radio': 'talkback', 'other': 'other',
}


def _has(rx, n):
    return re.search(rx, n) is not None


def refine(coarse, n, mic=''):
    """Fine id for a coarse id, from words in the normalised name n (and the mic text)."""
    m = (mic or '').lower()
    if coarse == 'kick':
        if _has(r'\bsub\b|subkick', n):
            return 'kick_sub'
        if _has(r'\b(out|outside|52|front|reso|ext|o)\b|kout\b', n):
            return 'kick_out'
        return 'kick_in'
    if coarse == 'snare':
        if _has(r'\b(bot|btm|bottom|bttm|under|b|bt)\b|bot\b', n):
            return 'snare_bottom'
        return 'snare_top'
    if coarse == 'tom':
        if _has(r'\broto', n):
            return 'roto_tom'
        if _has(r'\b(floor|flr|ft|fl|low|lo|big)\b|floor', n):
            return 'floor_tom'
        return 'rack_tom'
    if coarse == 'overhead':
        if _has(r'\bride\b', n):
            return 'ride'
        if _has(r'\bcrotch\b|\bknee\b', n):
            return 'drum_crotch'
        return 'overheads'
    if coarse == 'bass':
        if _has(r'\b(synth|syn|moog|key ?bass|keybass|sub ?bass)\b|bass ?syn', n):
            return 'synth_bass'
        if _has(r'\b(amp|mic|cab|dirty|drive|dist|b ?mic|grit|fuzz)\b', n) or \
                (_has(r'\b(e ?602|d ?112|beta ?52|re ?20|md ?421|sm ?7)\b', m) and not _has(r'\bdi\b', n)):
            return 'bass_amp'
        return 'bass_di'
    if coarse == 'acoustic_guitar':
        if _has(r'\b(mando\w*|banjo|dulcimer|dobro|fiddle|uke|ukulele|bouzouki|resonator|reso)\b', n):
            return 'folk_strings'
        return 'acoustic_guitar'
    if coarse == 'strings':
        if _has(r'\bfiddle\b', n):
            return 'folk_strings'
        return 'strings'
    if coarse == 'keys':
        if _has(r'\b(piano|pno|grand|upright piano|baby grand|yamaha cp\d*|cp\d+)\b', n):
            return 'piano'
        if _has(r'\b(organ|b3|hammond|leslie|org)\b', n):
            return 'organ'
        if _has(r'\b(moog)\b', n) and _has(r'\bbass\b', n):
            return 'synth_bass'
        if _has(r'\b(synth|synths|syn|prophet|proph|juno|ob ?6|ob ?x|minilogue|korg|moog|op ?1|mellotron|mello|sub ?37)\b', n):
            return 'synth'
        return 'keys'
    if coarse == 'playback':
        if _has(r'\b(drums?|perc\w*|kit|loops? drum|beat)\b', n):
            return 'tracks_drums_perc'
        if _has(r'\b(bass|sub|808)\b', n):
            return 'tracks_bass'
        if _has(r'\b(bgvs?|vox|vocals?|vx|choir|harm\w*|bv|bvs|vxtrx)\b', n):
            return 'tracks_vocals'
        return 'tracks_music'
    if coarse == 'click_timecode':
        if _has(r'\b(smpte|ltc|time ?code|tc|mtc|midi)\b|timecode', n):
            return 'timecode'
        if _has(r'\b(cues?|guide|count ?in|slate|vo|voice)\b', n):
            return 'cues_guide'
        return 'click'
    if coarse == 'fx_return':
        if _has(r'\b(delay|dly|slap|throw|echo|tape)\b', n):
            return 'fx_delay'
        if _has(r'\b(adt|chorus|doubler|double|thick\w*|lush|vibe|flange\w*|phase\w*|spread)\b', n):
            return 'fx_modulation'
        if _has(r'verb|\b(plate|hall|room|shimmer|chamber|rvb|vrb)\b', n):
            return 'fx_reverb'
        return 'fx_other'
    if coarse == 'utility':
        if _has(r'\b(ref|rta|smaart|meas\w*|measurement)\b', n):
            return 'measurement_ref'
        if _has(r'\b(pink|noise|tone|osc\w*|sig ?gen)\b', n):
            return 'test_signal'
        return 'other'                   # tuner feeds and the like: no template
    if coarse == 'talkback':
        if _has(r'\b(comms?|radio|vog|intercom|clear ?com|cc)\b', n):
            return 'comms_radio'
        return 'talkback'
    return COARSE_TO_FINE.get(coarse, 'other')


# --------------------------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------------------------

def normalise(name):
    """templates.json meta.taxonomy.normalise: lower case, every run outside [a-z0-9] -> one space."""
    return re.sub(r'[^a-z0-9]+', ' ', (name or '').lower()).strip()


# A row is not a channel when its name is only one of these ("Spare", "-", "N/A", "Ch 17").
BARE_SPARE = re.compile(r'^\s*(?:\(?spare\)?|spr|spares|-+|—|–|\.+|x|hole|n/?a|none|empty|unused|tbd|tbc|open|free|'
                        r'not used|nc|n/c|ch\.? ?\d+|channel ?\d+|input ?\d+|in ?\d+|\d+|'
                        r'(?:spare|spr)\.? ?#?\d{1,3})\s*$', re.I)          # "Spare 1" is a spare line too


# "Kit spares", "Generic spares": a line of spare gear on the list, not an input.
SPARE_GEAR = re.compile(r'^\s*(?:[\w.-]+ )?spares\s*$', re.I)


def is_bare_spare(name):
    return not (name or '').strip() or BARE_SPARE.match(name) is not None or SPARE_GEAR.match(name) is not None


# Layer 1: input-list context. (category, regex on the normalised name, confidence)
LIST_RULES = [
    # an effect return: "Acu 1 Return", "Plate Rtn" (refined to reverb/delay/modulation below);
    # a video or stream return is media, handled by MEDIA_WORDS in _rule_category
    ('fx_any', r'\b(return|rtn|ret|fx rt)\b', 0.85),
    # a mic'd room on a stage input list ("Room", "Drum Room", "Room L"), not a reverb return
    ('overheads', r'^(drum |kit |d )?(room|rm|rooms|amb room|vibe|trash|crush|front of kit|fok|kit mic)( (l|r|sl|sr|mic|mics|\d))?$', 0.75),
    ('overheads', r'^vp ?88\b', 0.7),
    ('overheads', r'^(cymbals?|cymb\w*|cym|crash|china|splash)( (l|r|sl|sr|\d))?$', 0.8),
    ('drum_trigger', r'\b(kick|kik|snare|snr|sn|tom|rack|floor) ?(trig\w*|tg|trg)\b|\btrg\b', 0.95),
    ('hihat', r'^(hh|hat|hats|hi hat|hihat|high hat)( (mic|top|bot|\d))?$', 0.95),
    ('kick_in', r'^(k|kick|kik|kck|bd|bass drum) ?(in|inside|1|port)?$', 0.95),
    ('snare_bottom', r'\b(snare|snr|sn|sd) ?\d? ?(bot|btm|bottom|bttm|under|b)\b', 0.95),
    ('horns', r'\b(tpt|trpt|trp|tbn|tbone|bari sax|alto sax|tenor sax|sax\w*|flugel\w*|clarinet|oboe|bassoon|tuba)\b', 0.85),
    ('hand_perc', r'\b(steel ?(pan|drums?)|agogo|guiro|cabasa|claves?|triangle|cowbell|wood ?block|udu|bodhran|tabla|'
                  r'stomp ?(box|board)?|tap (shoes|dance|board)|body perc\w*|bongos?|congas?|timbales?)\b', 0.85),
    # guitar and amp models: "Jazzmaster", "AC30", "Vox AC30" (before the vocal rules see "vox")
    ('electric_guitar', r'\b(strat|tele|telecaster|jazzmaster|jaguar|les ?paul|gretsch|rickenbacker|ac ?(15|30)|twin|'
                        r'deluxe|princeton|jcm\w*|plexi|marshall|mesa|orange amp|fender|vox ac ?\d+|kemper|helix|'
                        r'axe ?fx|quad ?cortex)\b', 0.85),
    ('acoustic_guitar', r'\b(12 ?string|twelve string|nylon|classical gtr|classical guitar)\b', 0.85),
    ('folk_strings', r'\b(sitar|oud|bouzouki|mandolin|mando|banjo|dobro|dulcimer|ukulele|uke|resonator)\b', 0.85),
    ('vocal_fx_mic', r'\b(vocoder|talk ?box)\b', 0.85),
    ('lead_vocal', r'\b(worship (leader|ldr)|wl (vox|vocal)|rapper|cantor|soloist|lead singer)\b', 0.75),
    ('vocal_generic', r'^(bgv|bgvs|bv|bvs|harm|harmony|backing vox|backing vocals?|background vocals?|bkg vox)( \d+| [a-z]+)?$', 0.9),
    ('vocal_generic', r'\b(hype ?man|hype|beat ?box\w*|mc vox|soprano)\b', 0.75),
    ('speech_mic', r'\b(pastor|preacher|podium|lectern|pulpit|announcer|announce\w*|host|mc|emcee|presenter|sermon|'
                   r'teaching|panel(ist)?|moderator|speech|spch|keynote|officiant|lav|lapel|narrator|narration|q ?a|q a mic)\b', 0.85),
    ('tracks_music', r'\b(ableton|backing tracks?|stems?|loops|multitrack|playback|pb rig|mainstage tracks|dj|turntables?|'
                     r'decks?|cdjs?)\b', 0.85),
    # "PB", "PB L", "PB 2": the band's playback rig (taxonomy example "PB 1"); walk-in music says so (media rule)
    ('tracks_music', r'^(pb|pbk|p b)( \d+| [lr]| st)?$', 0.85),
    ('media_playback', r'\b(walk ?in|walk ?out|walkin|pre ?show|preshow|break music|house music|spotify|ipod|iphone|'
                       r'laptop|computer|video|vid|media|propresenter|pro presenter|resolume|qlab|playout|announcements?|'
                       r'zoom|teams|webex)\b', 0.8),
    ('comms_radio', r'\b(clear ?com|intercom|stage (mgr|manager)|sm mic|riedel)\b', 0.85),
    ('test_signal', r'\b(pink|pink noise|sig gen|signal gen\w*|oscillator|osc|tone)\b', 0.9),
    ('measurement_ref', r'\b(ref mic|reference mic|measurement mic|meas mic|rta|smaart)\b', 0.9),
]
LIST_RULES = [(c, re.compile(rx), p) for c, rx, p in LIST_RULES]
MEDIA_WORDS = re.compile(r'\b(video|vid|stream|zoom|teams|webex|media|laptop|computer|ipad|iphone|ipod|propresenter)\b')
STEM_WORDS = re.compile(r'\b(tracks?|trax|trx|stems?|loops?|backing|multitrack|ableton)\b')
# Words that make a channel a control or comms signal whatever else its name says.
CONTROL_WORDS = re.compile(r'\b(tb|talkback|talk|click|clk|cues?|guide|smpte|ltc|timecode|trig|trigger|tg|comms?|iem)\b')

# "JORDAN", "Robin 1", "Casey (C)", "Drew (SL)": a capitalised word, maybe a number or a position
PERSON_ONLY = re.compile(r"^[A-Z][A-Za-z'’]{1,14}(?:\s+\d)?(?:\s*\((?:[A-Z]{1,3}|[A-Za-z]+)\))?$")
NOT_A_NAME = {'mic', 'mics', 'line', 'input', 'spare', 'aux', 'fx', 'misc', 'other', 'extra', 'new', 'test', 'di', 'xlr',
              'rf', 'wireless', 'stereo', 'mono', 'opt', 'option', 'tbd', 'tba', 'channel', 'sub', 'main', 'mix'}

_TPL_RULES = None


def template_rules():
    """[(category, compiled regex, only)] from templates.json meta.taxonomy.rules, in order."""
    global _TPL_RULES
    if _TPL_RULES is None:
        rules = _templates()['meta']['taxonomy']['rules']
        _TPL_RULES = [(r['category'], re.compile(r['regex']), r.get('only')) for r in rules]
    return _TPL_RULES


def template_category(n, stereo=False):
    """Layer 2: first template rule that matches the normalised name, or None.
    The template 'utility' rule (tuner, foh mix, producer) has no template of its own -> 'other'."""
    for cat, rx, only in template_rules():
        if only == 'stereo' and not stereo:
            continue
        if rx.search(n):
            if cat == 'fx_reverb' and only == 'stereo':
                return None        # list context: a stereo "Room" is a room mic pair (LIST_RULES)
            return 'other' if cat == 'utility' else cat
    return None


# Template rules that are too loose on input-list names, checked before trusting a template hit.
WEAK_TEMPLATE = {
    # "^\d+ [a-z]+$" in vocal_generic ("2 mics"); "\bsing\b"; bare "amp" without a guitar word
    'vocal_generic': re.compile(r'^\d+ [a-z]+$'),
}

_LP = None


def _listparse():
    global _LP
    if _LP is None:
        from sessionmaker import listparse as lp
        _LP = lp
    return _LP


def artist_tokens(artist):
    """Name words of the artist/act, used to spot the lead vocal ("Sam Vox" when the artist is Sam Rivers)."""
    if not artist:
        return []
    junk = {'the', 'and', 'band', 'tour', 'input', 'inputs', 'list', 'ip', 'io', 'rider', 'audio', 'plan', 'show', 'live',
            'rev', 'final', 'v', 'copy', 'stage', 'plot', 'foh', 'mon', 'monitors', 'channel', 'channels', 'sheet',
            'church', 'worship', 'house', 'festival', 'fest'}
    return [w for w in normalise(artist).split() if len(w) > 2 and w not in junk and not w.isdigit()]


PLAYBACK_SRC = re.compile(r'(?i)ableton|laptop|computer|\bmac\b|tracks|playback|mainstage|loopback|qlab|\bpc\b')


def _post(cat, p, why, n, mic):
    """Second look at a rule hit with the words the first rule did not use."""
    if cat == 'tracks_music':
        sub = refine('playback', n)
        if sub != 'tracks_music':
            return sub, p, why + ' + stem word'
    if cat == 'rack_tom' and re.search(r'\b(lo|low|floor|flr|ft|big)\b', n):
        return 'floor_tom', p, why + ' + low tom'
    if cat == 'sample_pad' and PLAYBACK_SRC.search(mic or ''):
        return 'tracks_music', 0.7, 'pad from a computer = playback'
    if cat == 'snare_top' and re.search(r'\b(bot|btm|bottom|under)\b', n):
        return 'snare_bottom', p, why + ' + bottom'
    if cat == 'kick_in' and re.search(r'\bsub\b', n):
        return 'kick_sub', p, why + ' + sub'              # "Kik Sub"
    if cat == 'kick_in' and re.search(r'\b(out|outside|front|reso)\b', n):
        return 'kick_out', p, why + ' + out'
    if cat in ('bass_di', 'bass_amp') and re.search(r'\b(piano|pno|grand)\b', n):
        return 'piano', p, why + ' + piano'               # "Upright Pno"
    if cat == 'bass_di' and re.search(r'\b(amp|cab|mic|dirty|drive|dist|fuzz)\b', n):
        return 'bass_amp', p, why + ' + amp'              # "Bass Cab"
    return cat, p, why


GROUP_OF = None
PERSON_DASH = re.compile(r"^\s*([A-Z][A-Za-z'’]{1,14})\s*[-–:]\s+(.+?)\s*$")       # "Tom - Vox", "Kim: BGV"
DASH_PERSON = re.compile(r"^\s*(.+?)\s+[-–]\s+([A-Z][A-Za-z'’]{1,14})\s*$")        # "Vox - Tom"


def _group(cat):
    global GROUP_OF
    if GROUP_OF is None:
        GROUP_OF = groups()
    return GROUP_OF.get(cat, 'other')


def _alternatives(raw):
    """Other readings of a name, each with the kind of answer it may give:
    ('any', the name without its brackets): "Vox 2 (Tom)" -> "Vox 2". The words outside the brackets name the
        channel; the brackets hold a player, a mic or a note.
    ('vocal', the thing after or before a player's name): "Tom - Vox" -> "Vox". Only a vocal reading counts, so
        "Trax 3 - Keys" stays a stem."""
    out = []
    core = re.sub(r'\s+', ' ', re.sub(r'\([^)]*\)?', ' ', raw or '')).strip()
    if core and core != (raw or '').strip():
        out.append(('any', core))
    for rx, who_g, thing_g in ((PERSON_DASH, 1, 2), (DASH_PERSON, 2, 1)):
        m = rx.match(core or raw or '')
        if m:
            who = m.group(who_g).lower()
            if not (STEM_WORDS.search(who) or CONTROL_WORDS.search(who) or MEDIA_WORDS.search(who) or
                    who in ('pb', 'spd', 'pad', 'fx', 'aux')):
                out.append(('vocal', m.group(thing_g)))
    return out


def rule_category(name, mic='', section=None, stereo=False, artist=None):
    """(category, confidence, why) for one channel name. Confidence >= 0.6: the rules are sure.

    A sure reading of the name without its brackets, or of "<player> - Vox", wins when it lands in another instrument
    group than the full name: "Vox 2 (Tom)" and "Tom - Vox" are a singer named Tom, not a rack tom."""
    cat, p, why = _rule_category(name, mic, section, stereo, artist)
    for kind, alt in _alternatives(name):
        c2, p2, w2 = _rule_category(alt, mic, section, stereo, artist)
        if c2 == 'other' or p2 < 0.6 or _group(c2) == _group(cat) or (kind == 'vocal' and _group(c2) != 'vocals'):
            continue
        cat, p, why, name = c2, p2, w2 + ' (read as "%s")' % alt, alt
        break
    return _post(cat, p, why, normalise(name), mic)


def _rule_category(name, mic='', section=None, stereo=False, artist=None):
    raw = name or ''
    n = normalise(raw)
    if not n:
        return 'other', 0.0, 'empty'
    # "Spare Vox", "Spare DI": a patched spare. Classify what it is a spare of.
    m = re.match(r'^(spare|spr|backup|bkup|back up)\s+(.+)$', n)
    if m and not is_bare_spare(m.group(2)):
        cat, p, why = rule_category(m.group(2), mic, section, stereo, artist)
        if cat == 'lead_vocal':
            cat = 'vocal_generic'      # a spare vocal is not the lead channel
        return cat, p * 0.95, 'spare of: ' + why
    toks = artist_tokens(artist)
    vocalish = re.search(r'\b(vox|vocals?|voc|vx|mic|rf|lv|sing\w*|main)\b', n) is not None
    if toks and vocalish and any(re.search(r'\b%s\b' % re.escape(t), n) for t in toks) and \
            not re.search(r'\b(tb|talkback|trx|trax|tracks?|spare|spr|guest|gst|iem|ears)\b', n):
        return 'lead_vocal', 0.85, 'artist name + vocal'
    control = CONTROL_WORDS.search(n) is not None
    media = MEDIA_WORDS.search(n) is not None
    for cat, rx, p in LIST_RULES:
        if cat == 'fx_any':
            if control or not rx.search(n):
                continue
            if media:
                return 'media_playback', 0.8, 'list rule (media return)'   # "Video Rtn", "Stream Rtn"
            return refine('fx_return', n), p, 'list rule (return)'
        if control and cat in ('media_playback', 'speech_mic', 'tracks_music'):
            continue                   # "Video TB", "Host Click": the control word decides (template rules)
        if cat == 'media_playback' and STEM_WORDS.search(n):
            continue                   # "Laptop tracks" is backing tracks, not walk-in music
        if rx.search(n):
            return cat, p, 'list rule'
    cat = template_category(n, stereo)
    if cat and not (cat in WEAK_TEMPLATE and WEAK_TEMPLATE[cat].search(n)):
        if cat == 'vocal_generic':
            lp = _listparse()
            k, _ = lp._vocal_kind(' %s ' % raw.lower(), mic, artist, 0.9)
            if k == 'lead_vocal':
                return 'lead_vocal', 0.7, 'template rule + lead hint'
        return cat, 0.9, 'template rule'
    lp = _listparse()
    coarse, p = lp.categorize(raw, mic or '', section, artist)
    if coarse == 'spare':
        return 'other', p, 'spare'
    if coarse == 'other':
        # a channel named only for a person ("JORDAN", "Robin 1", "Casey (C)") is that person's vocal mic
        # on almost every list; below 0.6 so the classifier still gets a say
        if PERSON_ONLY.match(raw.strip()) and n.split()[0] not in NOT_A_NAME:
            return 'vocal_generic', 0.5, 'person name = vocal'
        return 'other', p, 'no rule'
    fine = refine(coarse, n, mic)
    why = 'parser rule' if p >= 0.6 else ('mic or section hint' if p >= 0.45 else 'weak')
    return fine, p, why
