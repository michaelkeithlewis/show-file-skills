# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/ses.py

- V2242 only; kept for older callers, use CHREC_RE channel record header length: V1455 / V1619-V2126 / Q112+Q852 V1926-V2126 / V2232+
- section 201 group header (type, name, count @+0x70)
- section 201 group / channel record types (id >> 8)
- first Mustard module a writer usually needs
- ---- structure -------------------------------------------------------
- input channels: records followed (after the ff*8 00*4 tail) by a 27 00 <0x01xx> trailer
- section 211 holds the live channels; section 219 holds snapshot copies of them
- display number -> internal index display number -> 1 mono / 2 stereo internal index -> offset of its section 201 record record type -> [{'off', 'id', 'number', 'name', 'width'}] in surface order
- fallback: scan every channel record in the file
- bus maps: surface number -> band byte used by the input's send (module 02) / group (module 03) slots
- ---- surface banks --------------------------------------------------------- Section 243: u16 | u32 bank count | banks. A bank is u16 size (0x169) | u16 index | name ShortString[15] | ... | 12 strips of (index u8, type u8) at +0x23 | ... | 12 view bytes at the end of the bank. Strip type 01 = input channel (index = internal index - 1), 05 aux, 06 group, 0a CG, 10 matrix. View byte: 0 = strip shows SD processing, 2 = strip shows Mustard processing (the SD/M buttons).
- ---- slot access -----------------------------------------------------
- ---- names -------------------------------------------------------------
- every channel record for this id, any build (section 201 and any snapshot copies)

## scripts/sesproc.py

- DiGiCo keys (module, param, band). EQ UI band n lives at band byte 4 - n.
- The strip shows each filter's -3 dB cutoff; the file stores the 24 dB/oct design frequency. Measured in the V2242 editor: shown HPF = stored x 1.25, shown LPF = stored x 0.8.
- the editor mirrors the comp threshold into all three records
- Mustard compressor (module 0x1d). Keys from the decoder captures (FORMAT.md, mustard.ses).

## scripts/sessionmaker/build.py

- ses.py and sesproc.py sit next to this package
- a naming choice: the format holds 31 (FORMAT.md "Names"); the report keeps the long name
- Abbreviations, matched on whole words, case-insensitive. LONG words go first; SHORT ones only when squeezing out the spaces was not enough.
- Engine channels: a stereo channel takes 2, and the inputs must fit the room the default session leaves them (layout.engine_room: below the aux/matrix buses on SD models, below TB In on Quantum). A new bus layout moves that room on SD models, so it is read from the restructured default then.
- 1-2. layout: names, widths, order, count, notes
- 3. processing (internal index = surface number: relayout keeps 1..N in order)
- 4. structure, write, read back
- check names and details are shown to engineers as-is (web page Checks tab, report): plain words, 1-based

## scripts/sessionmaker/buses.py

- modules whose slots run once per aux (band = aux internal index) modules whose slots run once per group fixed slots inside per-bus modules aux sends run aux by aux; group assigns (TB In) run param by param
- slots that hold a raw channel id (00 00 idx type): (object type or None for any, module, param)
- Session Structure 'busses' budget per console (mono equivalents, 48 kHz): used + the dialog's spare counter in the V2242 editor (decode notes, not published). The editor loads up to budget + 4 and drops the layout (default session) from budget + 5. The older editors tested load to the same point (Q225 V1455/V1619 and SD12 V1619: 42 kept, 43 dropped; Q338 V2025 drops 74), so the budget is applied at every build. 96 kHz budgets are not measured.
- build the budgets were read at
- ---------------------------------------------------------------------------- section 201
- ---------------------------------------------------------------------------- describe
- ---------------------------------------------------------------------------- planning
- custom order: keep it, new mono after the last kept mono, new stereo at the end
- ---------------------------------------------------------------------------- per-bus slot runs
- one bus or one param: both orders read the same
- (mono, stereo left, right side); 1d only on Quantum
- ---------------------------------------------------------------------------- banks
- +0x12b: which of the slot's locked encoder rows (+0x6b) are locked; the SD / M view is +0x15d
- origin: old key for kept banks, ('new', old key of the run) for added ones
- a bank that starts over is a second copy
- keep the old heap words (save noise anyway)
- strips of other banks that show a removed bus become empty
- locked rows (4 per strip: param, module, band, 0) that show a send to a removed bus point at the first buses that are left, the way the editor re-points them (rows 1-2 of an input strip show Aux 1 and Aux 2 sends)
- keys and overview slots: kept banks move by (banks added before them - banks removed before them), an added bank takes the slot after the bank before it
- a fader-section table is paged in layers of 6; each table uses the first few positions of every page (Q338 master section: 4, i.e. 0-3, 6-9, 12; Q5 inputs: 5). Extra banks continue the pattern.
- ---------------------------------------------------------------------------- engine channels
- SD: solo 2 sits at min(8, 126 - total aux + group width); 138 of 138 SD files, and the V2242 SD5/SD7 editors moved it to 2/3/4 for widths 124/123/122 (decode notes, not published)
- ---------------------------------------------------------------------------- the operation
- the master stereo group cannot be removed (the editor's minimum is 1)
- back to front keeps offsets valid
- kept buses whose default name follows a new surface number
- ---- 243 banks, 212 placement (and its copy in the 211 tail)
- ---------------------------------------------------------------------------- fallbacks (pristine defaults)

## scripts/sessionmaker/busside.py

- ses.py and sesproc.py sit next to this package
- file family -> [(bay label, section 212 table)] where the real editor's Fader Banks screen confirmed the map
- ---------------------------------------------------------------------------------------------------- small helpers
- ---------------------------------------------------------------------------------------------------- objects
- ---------------------------------------------------------------------------------------------------- group graph
- ---------------------------------------------------------------------------------------------------- readers
- active sends per aux position, for the role rule
- ---------------------------------------------------------------------------------------------------- the surface
- ---------------------------------------------------------------------------------------------------- checks
- ---------------------------------------------------------------------------------------------------- writers

## scripts/sessionmaker/commands.py

- wall clock for the whole classifier step of a command
- "more" / "less" without a number "more X in Y" when X is not in Y yet
- ------------------------------------------------------------------------------------------------ vocabulary Command words a typo may hit. Channel-name words are never corrected (Index.name_words).
- Text rewrites on the lower-case clause (never on names, which are cut out first).
- A clause starts here when a comma or "and" is followed by one of these.
- ------------------------------------------------------------------------------------------------ groups of channels
- (key, label, regex on a cleaned target part, categories or a callable on a Ch)
- template category to use when a group word names a template ("use the snare template on 7")
- Who a monitor mix belongs to: words in a phrase -> words an aux name may carry.
- ------------------------------------------------------------------------------------------------ FX words
- kind follows the channels it is for
- Plain sound wishes -> one EQ move (a starting point, said as such in the summary). (regex, band freq, gain, type, q)
- the classifier's options when the grammar read nothing in a clause
- ------------------------------------------------------------------------------------------------ model index
- ------------------------------------------------------------------------------------------------ targets
- the whole phrase may be one channel name with "and" or "/" in it
- ------------------------------------------------------------------------------------------------ numbers
- ------------------------------------------------------------------------------------------------ results
- callable(Target) -> (ops, ask) when ops depend on the resolved channels
- ------------------------------------------------------------------------------------------------ on / off words
- ================================================================================================ recognizers
- several: "9 Keys L and 10 Keys R", "9 to Keys L, 10 to Keys R"
- "rename the drums mix to Jamie", "rename the Hall aux to Plate"
- ------------------------------------------------------------------------------------------------ mixes / buses
- "more click in the drums mix" is a send
- "16 aux and 8 stereo": the bare one is mono when the other kind is named, else ask
- ------------------------------------------------------------------------------------------------ FX units
- "add some verb to the lead" with a reverb in the session = a send, not a new unit
- the classifier may know the channels
- ------------------------------------------------------------------------------------------------ channels
- "make channel 9 mono" / "make ch 12 stereo" name an existing channel: that is a stereo change, not an add
- "add a sub kick after 2", "add a guest vocal"
- ------------------------------------------------------------------------------------------------ patch / preamp
- ------------------------------------------------------------------------------------------------ sends / groups
- ---- explicit aux: "send the vocals to aux 3 at -10", "vox pre on aux 4", "kick to aux 7 -5"
- ---- "more X in Y's mix", "the drummer wants more click", "more verb on the lead"
- "the drummer wants more click (in his ears)"
- "more X in Y's mix" / "X up in the drums mix"
- "more verb on the lead", "kill the verb on the click", "lead needs more verb"
- "put the lead in the slap", "send the snare to the plate", "vox into the hall"
- the unit these channels already use, else the one made for them (vocal plate for vocals)
- ------------------------------------------------------------------------------------------------ templates
- ------------------------------------------------------------------------------------------------ processing
- a bare negative number is the threshold ("comp the bass at -20")
- "swap the SD comps for Mustard": the channels with an SD comp on
- "cut 3 at 400": a small bare number next to the cut word is the gain
- ------------------------------------------------------------------------------------------------ faders / mutes
- the classifier intent -> recognizers to retry the clause with (forced: a keyword the grammar needs is put in front)
- ================================================================================================ text prep
- ================================================================================================ parse
- a rename carries a new name the typo fixer must not touch ("rename 3 to SnareT" is not a typo for snare)
- ---- the classifier: intents of unread clauses, channels of unresolved targets (one batch)
- ---- targets borrowed from the neighbouring clause, then ops
- ------------------------------------------------------------------------------------------------ renumbering
- model numbers in surface order (None = a channel added here)
- ------------------------------------------------------------------------------------------------ plain sentences
- ------------------------------------------------------------------------------------------------ CLI

## scripts/sessionmaker/consoles.py

- ses.py and sesproc.py sit next to this package
- key, name, family, default inputs (fallback), max inputs, Mustard, Spice Rack slots, note for the UI
- 80: console-proven, see _MAX_VERIFIED
- 120: editor-proven, see _MAX_VERIFIED
- max_inputs proven in the console's own editor. SD8: DiGiCo lists 60, but the SD8 editors V1455, V1619 and V2242 booted 120-input sessions built on their own defaults and re-saved all 120 names, the decode notes (not published), and a real 65-input SD8 show loads in full. The default session has 60. Q112: a session with 80 inputs, written by bytes, loaded on a Quantum 112 (V2242); the same with 82 was refused on load ("console not supported"). Real Q112 shows run 58 and 71 inputs.
- editor-verified (README: the editor turns Mustard off past 24 instances) other Quantums: unverified, see module docstring DiGiCo's V1742 release notes (Pulse table): Q338 36, Q338 Pulse 48, Q225 Pulse 36 Mustard channels. V2242.4 release notes: Q112 20 (Q112 Pulse 24). No Q112 session numbers a Mustard channel above 19 (cb +86).
- Builds whose generated output has been loaded in the real editor (Quantum 225 V2242: the relayout candidates s01-s13 and v2-v7 all loaded in the offline editor).
- path -> ((size, mtime), ok) key -> {build: why}, versions left out of the table (for logs and the selftest)

## scripts/sessionmaker/edit.py

- ses.py and sesproc.py sit next to this package
- ---------------------------------------------------------------------------------------------------- the session
- sends.objects() caches by file length; a move keeps the length
- ---------------------------------------------------------------------------------------------------- categories
- ---------------------------------------------------------------------------------------------------- the state
- set by ops that change the layout (validate runs after them) set by ops that change patch or bus routing
- -- bytes ----------------------------------------------------------------------------------------------------
- -- channels ---------------------------------------------------------------------------------------------------
- -- the console's default channel (for new channels and "is this value still the default?") -----------------
- ---------------------------------------------------------------------------------------------------- selectors
- ---------------------------------------------------------------------------------------------------- reading values
- ---------------------------------------------------------------------------------------------------- the model
- ---------------------------------------------------------------------------------------------------- 'set'
- every band is busy: retune the nearest bell within an octave (the sentence says what it held)
- the editor mirrors the comp threshold into all three records
- ---------------------------------------------------------------------------------------------------- Mustard
- allocation: channels already holding an instance keep it; the rest by priority within the cap
- already on: only the given values change
- the Mustard comp replaces the SD comp
- ---------------------------------------------------------------------------------------------------- names
- ---------------------------------------------------------------------------------------------------- sends
- ---------------------------------------------------------------------------------------------------- patch
- ---------------------------------------------------------------------------------------------------- templates
- ---------------------------------------------------------------------------------------------------- structure
- FX units fed from these channels' direct outs: L/R legs follow the width
- the R copy: right socket, no FX direct-out feed of its own
- ---------------------------------------------------------------------------------------------------- FX
- every output that names the unit: route cleared, mono mode back inputs patched to its return
- ---------------------------------------------------------------------------------------------------- buses, mixes
- take back unused buses from the end of each class (restructure removes from the end), mono auxes first, then mono groups, then stereo groups (never the Master), as the builder's automatic layout does
- monitor_mixes without its own rename (done above, fast)
- ---------------------------------------------------------------------------------------------------- the pipeline
- ---------------------------------------------------------------------------------------------------- CLI

## scripts/sessionmaker/fx.py

- section 201 record type, object id high byte and patch source type of an FX unit module record type of an FX unit
- record header byte: 01 on live records, 00 on library copies FX ids are 0x0e00 | k; the editors kept 32 units (largest real session: 15 units) units with DSP per pool (reverbs / other effects): the editors give a 17th reverb no DSP
- The categories of the factory presets. FPGA reverbs and the other effects use separate DSP pools (EngineChannel).
- EngineChannel of the first unit in each pool, by file family: reverbs at 128 (Quantum) or 64 (SD), the other effects at 0, 2 per unit, in rack order (real sessions V1455-V2025, the V2242 editor's own v4 edit and the editor proofs in the decode notes (not published). engine_slots() has the full order.
- Quantum families whose other-effects pool stops at 26: the Quantum 112 V2242 editor gives a 15th and 16th non-reverb unit EngineChannel -1 (no DSP) whether they are written at 64/66 or at 28/30 (verifier probes, q112_v2242_cap and results_probe.jsonl q112_v2242_capsd).
- Friendly names for kind and preset words -> factory preset name.
- Named parameters -> (param, band) on the type 0x15 record. Every name was matched to its control on the V2242 editor's FX rack display. predelay, lo/hi_filter, hi_damping, decay, time, feedback and mix were also written, booted and re-saved unchanged on 18 console/firmware pairs (decode notes, not published).
- Keys whose meaning depends on the preset (same key, different control on the rack display).
- ---------------------------------------------------------------------------------------------------- helpers
- entry kinds this reader does not know (big V2025 libraries): stop here
- ---------------------------------------------------------------------------------------------------- reading channel record header lengths; 0x78 = Quantum 112 / 852 at V1926-V2126
- section 201 ---------------------------------------------------------
- section 211 ---------------------------------------------------------
- ---------------------------------------------------------------------------------------------------- writing
- mono > stereo: the aux feeds both sides
- object trailer: last byte = width
- V1455 records have no EngineChannel, so count the units too
- 201: a mono aux record turned into an FX record, appended to the FX group

## scripts/sessionmaker/inspect.py

- ses.py and sesproc.py sit next to this package
- characters a channel strip is known to show (FORMAT.md, ses.rename default)
- real sessions: 425-4,000 live objects
- file-family code at 0x0b -> console keys that write it (consoles.py) and the plain label
- Models that share a family code are told apart by header fields that are fixed per model (tConsoleRec nMatrixOutputs 0x93, nControlGroups 0x94, nMatrixInputs 0x96, nGraphicEQs 0x97; the same values in every default V1455-V2242 and in every real session whose file name names the model). This matters, because the bigger model's file does not load on the smaller one: the SD8 editor silently starts its own empty session instead of an SD10 file, and the SD11 editor does the same with an SD9 file. The other way works: the SD10 editor keeps an SD8 file and the SD9 editor an SD11 file (editor proofs 2026-10-13, the decode notes (not published). SD5 and SD5CS files are identical, and the SD5 editor keeps an SD5CS file, so both stay candidates.
- Public software releases per console the decode notes (not published), firmware_matrix.json). Some trains shipped for one model only (V1229 Q338, V1246 Q5, V1454 Q225, V1861/V1879/V1889 Q852), so the oldest release that opens a file depends on the console.
- console software builds seen in real files that DiGiCo never published as an offline editor (two real Q5 sessions were saved by V1623 on the console itself)
- header revision letter at 0x15 per build, from every editor-saved file (V18 Q852 builds unseen)
- FX algorithm from the unit's own parameter keys (the factory presets' key sets, the same in every default V1455-V2242; the decode notes (not published). Checked in this order: every delay has (56,0), the pitch shifter (02,1), the Audio Enhancer (63,0), every reverb (0f,0) predelay; the choruses carry (12,0) too but no (0f,0).
- A name that ends in a side: "Keys L", "OH_R", "Pad-left" (a separator before it), or "KeysL" / "Gtr2R" (a capital L or R straight after a lower-case letter or a digit). A lower-case l or r straight after a letter is part of the word ("Hall", "Choir", "Guitar", "Wurl"), never a side.
- "Trx L/R", "Keys LR": a stereo name
- ------------------------------------------------------------------------------------------------ small readers
- ------------------------------------------------------------------------------------------------ structure
- ------------------------------------------------------------------------------------------------ a lean ses.Session
- ------------------------------------------------------------------------------------------------ the readout
- Pulse (V1742+, Quantum 225 and 338 only) sets bit 0x10 of the header's ExtensionsUsed byte (0x25); a Pulse session only opens on a console or editor with the Pulse extension enabled, a standard one opens on both.
- gzip: a dLive show (.tar.gz), read by dlive/check.py
- ---- buses from section 201 (surface order) ----
- patch, gain, 48V: (01,0e,0) = 1.0 when the channel runs on its alt input, and then gain, 48V and pad come from the alt socket (the main socket's values are not in use)
- processing (sessionmaker.process readback; keys from data/templates.json)
- ---- FX units, Spice Rack ---- An FX input (00, band) is fed by an aux (05), the right side of a stereo bus (07, the partner of band 0's source), an input channel's direct out (01) or a group (06). Real sessions carry a non-zero first byte on direct-out and group feeds (05, 07, 08, 09), so only the index and type bytes are read here.
- 07: the right leg of the bus already named by band 0
- patch and monitor mixes at a glance: inputs on a socket, 48V on, and auxes that carry a pre-fader mix (two or more inputs sent pre-fader, and not an FX feed)
- ---- structure check (sessionmaker.validate), guarded ----
- ---- console, version, compatibility ----
- ------------------------------------------------------------------------------------------------ CLI
- SIGALRM outside inspect's own handler

## scripts/sessionmaker/intake.py

- seconds, wall clock, whole classifier step averaged probability needed to take the classifier's channel category same for a questionnaire answer (a wrong one is visible and cheap)
- optional classifier hook ("the classifier" in the names below)
- The original tool asked an external closed-set classifier about the channels the rules were not sure of. That service is not part of this repo. Without it everything runs on the rules (taxonomy.rule_category) and the description regexes, which is the documented fallback. To plug in your own classifier, set CLASSIFIER to a callable (state, questions, timeout) -> ({qid: {'choice', 'p', 'orders', 'probs'}}, info), where questions = {qid: (instructions, {option: description})} and p is the probability of 'choice' (0..1). 'orders' = 2 tells the callers the answer is stable when the option order is reversed.
- Letters NFKD does not split into a base letter + accent.
- Console names for inputs pulled out of a sentence ("I'll need a bass DI and a vocal mic").
- "Sam - lead vocal ..." -> who = Sam
- "add a talkback for the MD, an audience pair", "plus a vocal mic for the bassist", "extra AG DI"
- Rows that are not inputs: a time or date ("9:30 AM CT", "1:30 - 3:00 PM", "Thu 9/17"), which is what a run sheet or schedule PDF turns into, and a header line that came through as a row ("Ch,Name,Mic" in a CSV with no data under it).
- a reader's internal note, not a sentence
- mostly times, dates or a lone header line: a schedule, a run sheet or an empty template, not an input list
- benchmark: neighbours from the real session
- set by the user in the UI: keep it
- the classifier says none of the templates: a flat channel, marked as a guess
- (qid, question, {option: description}). 'not_said' means "use the style default".
- style -> default answer for every question (used when neither the text nor the classifier settles it)
- "and a floor", "plus 2 floors", ", floor tom"
- "a rack and 2 floor toms", "rack, 2 floor toms"
- speech mics and no instrument: "Theatre show: 12 wireless lavs"
- "kick in and out, snare top and bottom": a kit
- stated outright, even with "and an acoustic" next to it
- "3 guitars", unless an acoustic count may be part of it
- horns / strings and named instruments
- "5 saxes, 4 trumpets": one channel each (house_order), not one per instrument type
- "walk-in music and video playback": the Media channel
- "a fiddle player who sings harmony": one harmony singer per mention that gives no number; "the guitar players sing harmonies" (plural subject, "sing") counts two
- Speech mics a description lists one by one. (kind, regex after an optional count, console name). Earlier kinds win where matches overlap, so "a moderator with a handheld" is one mic and "6 panelists on lavs" is six.
- Words that may stand between a count and the mic kind: "12 wireless lav mics", "2 radio handhelds".
- Who fills the seats of an N-piece band after drums, bass and any named instruments, in order.
- the text named them: "podium, 2 handhelds, 4 panelist lavs"
- a panel: podium + three handhelds
- Questions whose answer adds inputs. When a description names three or more of them it is an inventory: the ones it does not name are absent (not the style default, not a guess from the classifier).
- most channels one stated count may add ("8 singers", "5 saxes")
- an inventory leaves it out (an assumption)
- a mention, refined by the classifier ("choir" -> large)
- keep the answers consistent with each other
- a fiddle or mandolin is not a string section
- counts the options cap ("Six or more singers", "Three electric guitars") stay exact when the text gave them
- An item that describes the band rather than naming an input: a count of a plural ("2 guitars", "three vocals"), or a player or the whole kit ("drums", "a drummer", "band", "singers").
- two sentences in one item "Vocal and guitar" describes, a list splits it
- a pasted list: one channel per line (a comma list is split into lines first)
- options the show asks for (IEM / wedge mixes, reverbs and delays, a monitor desk), from the description text and the FX return rows of a list (options.suggest; never raises into the plan)
- nothing printable left (only emoji): the instrument's house name, else Ch N

## scripts/sessionmaker/layout.py

- OverviewPosition x of a bank that is not on the overview grid overview grid: x = 1 + 170 * col, y = 2 + 250 * row (module, param, band): (mono value, stereo value). (1d,3f,0) exists only on Quantum (Mustard).
- the id low byte is idx - 1, so 256 inputs at most
- ---------------------------------------------------------------------------- container
- bytes between id table and the first section
- ---------------------------------------------------------------------------- section 201
- ---------------------------------------------------------------------------- engine channels cb +84 EngineChannel numbers the DSP paths. Measured on all 91 editor-saved files (39 real sessions, editor-made baselines, every default session and the editors' boot re-saves in: SD models   one pool for the inputs and the mix buses. Groups (06) sit at the bottom, then the inputs, then the Talkback Input (0c) at last input + 1. Aux (05) and Matrix (10) outputs sit at the top (SD9/SD11/ SD12 end at 191, SD5/SD7/SD8/SD10 at 255); 07 (right side of a stereo aux or group) sits inside those ranges. No input ever shares an engine channel with 05/06/07/10 or 0c. Quantum     the inputs have a pool of their own from 0 (the buses reuse 0..). TB In sits at 254 on Q2/Q3/Q5/Q7 and at last input + 1 on Q1/Q8. No engine number above 255 was seen. After a relayout the editor moves TB In to last input + 1 wherever it sat there before, and leaves 254 alone (boot re-saves: sd5 126->80, sd12 66->80, q112 48->59, q852 72->62; q225..q7 kept 254). relayout() does the same.
- aux, group, right side of stereo aux/group, matrix output
- engine numbers 0..255 on a Quantum input pool Channel record header lengths. 0x78 is the Quantum 112 and 852 at V1926-V2126; before 2026-10-13 groups201 left it out, so engine_room() found no engine channels there and relayout() left TB In at the default's 72 (Q852) or 48 (Q112), which the editors then rewrote to last input + 1 on load (decode notes, not published).
- ---------------------------------------------------------------------------- section 211
- ---------------------------------------------------------------------------- banks (243) and placement (212)
- strip j: internal index - 1 at +0x23+2j, strip type at +0x24+2j (01 = input channel)
- positions 0-5 (layer 1) hold the input banks and 6-11 (layer 2) the output banks in every default
- ---------------------------------------------------------------------------- session notes (section 0)
- ---------------------------------------------------------------------------- the operation
- 211: one object per channel, cloned from its source (or the default mono object), sorted by id
- 201: cb records in surface order, EngineChannel = first + running sum of widths. The inputs must fit below the first bus (SD) or the fixed TB In (Quantum); TB In that sat right after the inputs moves with them.
- 243: input banks rebuilt in surface order, later banks renumbered
- 212 and its copy in the 211 tail

## scripts/sessionmaker/listparse.py

- console names cut to 8 by choice; the format holds 31 (references/FORMAT.md "Names")
- (field, regex on the normalised header cell). First match wins, order matters.
- Stereo said outside the name: a Stereo column ("Y"), the notes ("stereo pair"), or a pair of mics in the mic cell ("KM184 x2", "pair of 414s"). The mic hint only counts for sources that are a pair by nature (STEREO_NATURE).
- ---- categories: closed set, used for processing templates and for the classifier check ------------
- word start that treats '.' and '/' as boundaries word end that lets a digit follow ("snr1", "tom2")
- (category, regex on the lower-case name, confidence). First match wins.
- lead or backing, decided below
- section header words -> category for rows the name alone cannot place
- mic model -> category, only when the name is no help
- ---- 8-character naming ----------------------------------------------------------------------- multi-word first; applied only when the plain name does not fit
- words that are never a person's name (for the "G.Nord" initial rule)
- readers -> list of sheets, each a list of rows (list of str)
- Excel turned "9/10" into a date
- ---- .xls (Excel 97-2003, BIFF8 inside an OLE2 compound file) ----------------------------------- Only what an input list needs: sheet names and cell text/numbers. Record ids from [MS-XLS]; compound-file layout from [MS-CFB]. xlrd is used instead when it imports.
- sector ids at or above this end a chain (ENDOFCHAIN, FREESECT, FATSECT ...)
- the text follows in a STRING record
- ---- .docx ---------------------------------------------------------------------------------------
- ---- .html (and .xls files that are really an HTML table) --------------------------------------
- letter-spaced PDF headings: "s ta n d"
- a channel column only counts when it sits left of the name (a "Ch." right of it numbers outputs)
- score: mapped fields + data rows that look like inputs
- section rows: one cell of text, no channel number
- an unnamed row (numbered or not) is an unused line on that list, not a channel
- the same channel cell on two rows: a "3-4" (or "3") merged down over an L/R pair
- "opt" rows: patched just in case, not a channel
- a neighbouring column's text landed in the cell ("X 10")
- In a numbered list, an unnumbered line that starts like this is a note to the engineer, not an input.
- parentheticals are notes or the mic, never fields
- an unclosed "(" runs to the end of the line
- " - " or ", " separate fields only when the right side is gear
- token scan: name runs until the first gear token
- a generic word ("DI", "Line", "RF") that ends the text is part of the name: "Bass DI"
- "DI line: Drum pad for kicks" -> the description is the name
- "BASS", "GUITAR", "Drums:" over numbered lines
- "Drums: kick, snare, hat" -> section + items
- PDF text without a leading channel number: a heading or wrapped text
- an unnumbered line: a bullet item, a pasted name, or prose
- "DRUMS", "STAGE LEFT"; a bare "JORDAN" or "KICK" is an input
- split only when a header row repeats on one line ("CH INPUT MIC ... CH INPUT MIC ...")
- "3-4 OH" + "OH": the second row is the R half
- "Trax 1 - Perc/FX" == "Trax 2 - Perc/FX"
- long names that drift ("Walk-in / walk-out music L: Dante 65" / "Walk-in music R: Dante 66") while the list's own short-name column agrees ("WalkIn L" / "WalkIn R")
- SL/SR only pairs for sources that are a stereo pair by nature
- the RF vocal that is not a spare is usually the artist
- "T. BGV", "Trax 3 - Keys", "PB 4 - Pad R"
- "SPD Master L - Trax L": drop the remaining side tokens too
- "Trax 3 - Keys L" / "PB 4 - Pad R" / "SPD Master L - Trax L"
- "Kick 2 / Big Floor", "Walk-in / walk-out music": keep one alternative, the last one that fits cleanly
- person prefix: "Riley Nord" -> "R.Nord"
- glue numbers to the word before ("Snr 1 Top" -> "Snr1 Top")
- "BigFloor", "M.VoxPno", "G.AmpDyn"
- squeeze vowels out of the longest word (never the "G." prefix) until it fits
- the L row's "WalkIn L" names the stereo channel "WalkIn"
- a continuation block may start up to this many channel numbers after the last one taken
- the newest year's tab ("2026 IO" over "2024 FLY IO")
- every window of the best header row
- headerless tables (a Word table continued on the next page) read with the best block's columns
- the extension names a binary format but the bytes are text: an HTML export, or a CSV saved as .xls/.pdf

## scripts/sessionmaker/options.py

- ---------------------------------------------------------------------------------------------------- FX UI choice -> factory preset, unit (and aux) name, return channel name (8 chars), send role, label.
- Return-channel category per FX kind (data/templates.json fx_returns group).
- per request; the editors take 16 reverbs + 16 others (14 on a Quantum 112)
- Post-fader FX sends by unit role and channel category (dB). From the 39 real sessions: channels that send to an aux-fed unit of that role in at least about a quarter of the cases, at the median level, rounded (sends sit near 0 dB and the aux master and return fader set the amount). keys/piano/strings/choir in the hall and the delay's lead-vocal-only rule are engineering choices where the data is thin.
- hall takes what the others left
- ---------------------------------------------------------------------------------------------------- gain and 48V Starting analog gain (dB) on a mic socket by category: medians over the patched mic sockets of the 39 real sessions, categories with 20 or more channels (media_playback and measurement_ref: 19), rounded to the 0.5 dB step. lead_vocal and vocal_fx_mic take the vocal_generic value (real lists name most lead vocals "Vox 1"), floor_tom the rack_tom value (13 channels), and every tracks category the tracks_music value. Categories not listed keep the editor default.
- 48V on where at least 40 % of the real channels of that category have it (19 or more channels); the other categories in GAIN_BASE get 48V off. 48V does no harm to a balanced dynamic mic; off on a condenser is silence.
- Mic models named in an input list, read before the category: condensers and active DIs on, dynamics off.
- ---------------------------------------------------------------------------------------------------- mixes Seats a monitor mix is named after, in the order they get a mix when there are fewer mixes than seats, with the categories that are "their own" (6 dB up in their mix). per_channel: one seat per player number in the names.
- ---------------------------------------------------------------------------------------------------- normalise Letters NFKD does not split into a base letter + accent (the table of intake.console_name).
- ---------------------------------------------------------------------------------------------------- prepare
- the factory preset groups come from a V2242 Quantum default (see references/baselines.md)
- ---- FX returns: plan rows first, then new channels
- a channel number given as a return is reserved before any 'auto' return picks a row, and only one unit may return on a channel (a second one would overwrite the first unit's return patch)
- ---- aux numbers (surface order: mono auxes first)
- ---- FX sends (post-fader) by role
- ---- patch: per-channel gain and 48V
- ---------------------------------------------------------------------------------------------------- apply
- one note per input (a stereo input has two sockets)
- ---------------------------------------------------------------------------------------------------- checks
- ---------------------------------------------------------------------------------------------------- report
- consecutive channels on one device, in patch order (a patch that starts past mic 1 wraps back to the first device's lower mics)
- ---------------------------------------------------------------------------------------------------- read a show
- FX words of a description -> FX_CHOICES key, checked in this order on the text with outboard clauses left out
- A clause that names the player's own gear or a playback rig: its "effects", "reverb" or "delay" is not a console FX.
- "the singer wears in-ears", "drummer and bassist on IEMs", "everyone else is on wedges"
- "IEMs for everyone": one mix per instrument player plus a lead singer; backing vocals are taken to be sung by the players (a count in the text wins)
- "the singer wears in-ears, everyone else is on wedges": the players named get that kind, the rest the other
- ---- FX. Clauses about outboard gear ("his own effects pedalboard", "vocal effects from a TC Helicon", "sound effects playback from QLab") ask for no console FX, so they are left out first. "No reverb" drops the reverbs only, "no delays" the delays only, "no FX" everything. "Slap delay" is one unit.
- "2 delays" counts a slap that was named too
- ---------------------------------------------------------------------------------------------------- console facts
- ses.py sits next to this package

## scripts/sessionmaker/patch.py

- ses.py and sesproc.py sit next to this package
- package import (sessionmaker.patch) or a plain script next to sends.py
- record k <-> input socket type 0x1c + k, output socket type 0x4e + k
- IPAD_Q2.DOSC: analog gain -20..60; every real gain is a 0.5 step
- Device type byte (record +0) -> the editor's own name for it (V2242 switch; 0x1a is "Console" or "MADI Console").
- Stage boxes with mic preamps (gain / 48V / pad do something on their "Mic" sockets).
- D-Rack, D2-Rack, SD9/SD11 local slots that hold a raw route: source, output/insert send, copy, key input
- ---------------------------------------------------------------------------- devices (section 246)
- ---------------------------------------------------------------------------- input sockets
- editor-named sockets say what they are ("1:Mic 5", "2:Line in 3", "0:AES in 1"); a renamed socket on a preamp device ("kick in") is taken as a mic input
- ---------------------------------------------------------------------------- channel patch
- the editor clears (00, 1) on a stereo channel when it loads the file (Q225 V2242 boot re-save, the decode notes (not published), and no stereo channel in the real sessions has one (567 of 567)
- e.g. Local I/O "0:Mic 8" + "0:AES in 1": the right side is the next socket whatever it is
- segments of (sockets, first, end): the first device from `start`, the others whole, then the first device's sockets below `start` (a later channel never lands on a socket an earlier one took)
- ---------------------------------------------------------------------------- devices: add A device is declared in four places, all keyed by its port k (input socket type 0x1c + k, output 0x4e + k): section 246 record k (210 bytes, fixed size); section 201: an input socket group and an output socket group ('ca 00 6c 00 | type | name' + u32 count + one cb record per socket: id = type << 8 | idx, number idx + 1, name "k:Mic n", EngineChannel (+84) = idx); the u32 right after the two patch-bay page blocks counts the groups (on Quantum including the 'd1 00 6c 00' "Nodal Processing" group) and grows with them; section 211: one socket object per socket (module 0x11 inputs, 0x12 outputs), sorted by id with the rest, 'd3 00 | u32 object count'; the two patch-bay page blocks at the head of section 201 (u32 text length | "label\r\n" x n | n x u32 page id (first socket idx, type, 0, 0)): one page per 8 sockets, label "Mic 1-8". add_device() builds all four from a template device taken from any editor-written file (template_from()), using the target file's own cb record and socket objects as the byte layout, so the build may differ. MADI-port links each editor keeps a device on (proven by boot re-saves, the decode notes (not published). A device on a link past these is kept with its sockets but marked not connected (id 0). Models not listed: unknown, not limited here.
- device -> (default console key, port) in baselines/<key>_v<build>.ses
- 201: page labels, groups, group count
- an existing device's input socket group
- never carry the template's routes: its output sockets may be fed by its own master
- Oldest build whose editor names the device type (Quantum2.exe device-name switch: V1455, V1619 and V2025 have no case for 0x0f Local Dante, V2126 and V2242 do; the other template devices are named from V1455 on).
- the Q225 defaults before V2126 carry a D2-Rack where later ones have the MQ-Rack

## scripts/sessionmaker/process.py

- ses.py and sesproc.py sit next to this package
- Mustard goes to the channels that gain most from it first; a lower number wins, then surface order.
- the Optical ratio stops at 3:1
- SD consoles: no Mustard and no fallback, the SD template stands
- The SD/M strip buttons only switch the view, saved per bank. Mustard channels open on the M view.
- ---------------------------------------------------------------- read back (display units)

## scripts/sessionmaker/sends.py

- ses.py and sesproc.py sit next to this package
- header: tConsoleRec (0x24) + 56 = MasterGroupID (band of the master group) section 201 record: cb 00 hl 00 + tChannelRec.BussID @50
- AuxSendPrePostButton caption in the editor: "Post-Fader|Pre-Fader|Pre-Mute|Mid-EQ/Dynamics|Pre-EQ/Dynamics| Pre-Processing" = values 0..5 of (02, 04).
- longest bus name in the 39 real sessions is 20; "<name> R" must fit 31
- ---------------------------------------------------------------------------- object index
- ---------------------------------------------------------------------------- buses
- all module records in the file, in file order
- keep the parsed 201 view in step
- ---------------------------------------------------------------------------- sends
- check everything before the first write
- + 0.0: no -0.0 (the editor saves +0)
- a linked aux: the editor rewrites every send pan from the channel pan on load, so write that value
- check everything before the first write
- ---------------------------------------------------------------------------- group routing
- ---------------------------------------------------------------------------- output patch
- routed to an FX unit or another destination: leave it
- resolve every socket before the first write
- the bus's own route names one of its sockets; when it feeds an FX unit (type 0e) that feed stays
- a main output (insert sends carry a tap byte)
- ---------------------------------------------------------------------------- read back
- ---------------------------------------------------------------------------- monitor-mix example Starting IEM send levels (dB) by template category (sessionmaker.taxonomy): the medians of 7,400 active sends in the 192 stereo IEM-style mixes of 28 real sessions that have them (decode notes, not published), whole dB. 69 % of those sends are pre-fader, 30 % post-fader (dedicated monitor desks with the input faders at 0 dB).
- sent only to the mixes that ask for them (mix['click']) a player's own sources come up this much
- follow the channel's main pan (a linked aux derives it)

## scripts/sessionmaker/taxonomy.py

- Option texts for the classifier. Each says what the source is and lists the short names engineers use, because the classifier sees 8-character console names. Order matters only for display; intake asks in both orders and averages.
- coarse (parser, 28 ids) <-> fine (templates, 50 ids)
- Default fine id for each coarse id when nothing in the name refines it (see refine()).
- no room-mic template; overheads is the closest processing
- For scoring against the hand-labelled ground truth (which uses the 28 coarse ids).
- tuner feeds and the like: no template
- A row is not a channel when its name is only one of these ("Spare", "-", "N/A", "Ch 17").
- "Kit spares", "Generic spares": a line of spare gear on the list, not an input.
- Layer 1: input-list context. (category, regex on the normalised name, confidence)
- an effect return: "Acu 1 Return", "Plate Rtn" (refined to reverb/delay/modulation below); a video or stream return is media, handled by MEDIA_WORDS in _rule_category
- a mic'd room on a stage input list ("Room", "Drum Room", "Room L"), not a reverb return
- guitar and amp models: "Jazzmaster", "AC30", "Vox AC30" (before the vocal rules see "vox")
- "PB", "PB L", "PB 2": the band's playback rig (taxonomy example "PB 1"); walk-in music says so (media rule)
- Words that make a channel a control or comms signal whatever else its name says.
- "JORDAN", "Robin 1", "Casey (C)", "Drew (SL)": a capitalised word, maybe a number or a position
- list context: a stereo "Room" is a room mic pair (LIST_RULES)
- Template rules that are too loose on input-list names, checked before trusting a template hit.
- "^\d+ [a-z]+$" in vocal_generic ("2 mics"); "\bsing\b"; bare "amp" without a guitar word
- "Tom - Vox", "Kim: BGV" "Vox - Tom"
- "Spare Vox", "Spare DI": a patched spare. Classify what it is a spare of.
- a spare vocal is not the lead channel
- "Video TB", "Host Click": the control word decides (template rules)
- "Laptop tracks" is backing tracks, not walk-in music
- a channel named only for a person ("JORDAN", "Robin 1", "Casey (C)") is that person's vocal mic on almost every list; below 0.6 so the classifier still gets a say

## scripts/sessionmaker/validate.py

- Header counts (tConsoleRec) against the section 201 records they count: (header offset, struct format, record type, width or None for any, label). Equal in all 716 editor-saved files (116+ defaults, 39 real sessions, 557 boot re-saves;. The editors trust the header: the Quantum 225 V2242 editor crashed (access violation in Quantum2.exe) on a file whose header said 7 mono auxes over 6 aux records, and threw away a file whose header said 255 (decode notes, not published).
- EngineChannel: after a Restructure it is first + running sum of widths (surface order); a later per-channel flip takes the next free engine channels instead (seen in a real SD8 session). The hard invariant is that the ranges [eng, eng + width) never overlap.
- stereo must carry the stereo value; real mono channels hold the mono value or 0.0
