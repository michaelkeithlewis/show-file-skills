# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/analyze.py

- Krumhansl-Schmuckler key profiles
- half/double candidates - worship/acoustic material is often mis-octaved
- label by relative RMS energy of each span (quiet / mid / full)

## scripts/clipgain_normalize.py

- keystrokes cannot reach the clips of an inactive or hidden track
- already clip-gained (see .premix_clipgain.json); name it with --tracks to add more
- Pro Tools clip gain tops out at +36 dB
- premix.py reads this: PTSL cannot read clip gain

## scripts/io_map.py

- "External Headphones 1-2 (Stereo) -> MON L/R" = an output path

## scripts/lyrics.py

- per-segment role: repeated lyric => chorus-like, unique => verse-like
- contiguous runs of the same role -> raw sections
- merge sub-min_dur fragments (breath-split sustained lines) into a neighbour
- keep the longer-lived neighbour's role
- re-coalesce consecutive same-role after merging
- a unique ("verse") run that appears once, late, between choruses -> Bridge
- unique lyric block after a chorus in the back half
- optional: snap each section start to the nearest musical boundary

## scripts/premix.py

- each command re-renders its stems; ~90 MB a stem, 25 GB after one album (2026-10-29)
- ---------- the session as Pro Tools sums it ----------------------------------------------------
- routing folders: {name: {bus, out, parent, fader}}, filled by session_map()
- producer tracks parked inactive or muted (a muted synth bass) do not sound: keep them out of the model
- no bus (FX GROUP): its tracks bypass the fader the engineer set this folder by hand (a folder driven hot into its own plug-ins): never change what feeds it; its fader still absorbs its parent's moves
- skip empty folders (ORCH GRP, BGV with no stems)
- raise the children by r ... ... the folder fader comes down by r
- Group loudness targets, LU relative to the kick group, gated over the parts where each group plays. First-blend defaults; edit here. Matched against the folder name (first hit wins).
- Printed effect returns on producer sessions ("v lead apollo fx", "LV verb.dup3", "bgv harm 1 verb", "Vocal Echos"). Loudness-matching them to the dry stems would put a reverb print as loud as the vocal (producer session, 2026-10-29), so they keep the producer's printed wet/dry ratio: fader = dry partner's fader + partner clip gain - own clip gain.
- "v lead apollo fx" -> "v lead.rx"
- Anchor = the kick folder, else the whole kit (producer sessions keep drums in DRUM GROUP), else the lead vocal, else the loudest folder; every folder lands on its role offset from the anchor's ROLE level. (Picking the loudest folder as "kick" put one song's BGVs 3 LU over the lead and another's bass 4 LU over it, 2026-10-29.)
- ---------- Pro Tools I/O -----------------------------------------------------------------------
- FilePerMixSource: SingleFile with several sources writes ONE multichannel file (2 channels per source)
- no inserts, straight to its folder: model is exact a printed effect keeps its producer chain's level change (an echo print through a saturator + delays read -11 dB)
- one source bounces to "ZZPC.wav" with no bus suffix
- anchors (kick or whole kit) + the lead vocal

## scripts/prep_session.py

- ---------- session creation -------------------------------------------------
- .create() returns before the session is open; the builder's own follow-up calls race ahead and throw. Not a failure -- the poll below is the real answer.
- ---------- stems: download + import ----------------------------------------
- ---------- channel analysis (FULL FILE - never sample the head) -------------
- one mono signal printed with a pan: the quiet side is an exact scaled copy of the loud side
- -> pan_to_mono.py (mono track from the loud side + the matching pan)
- one-sided, no partner -> mono of the live side
- ---------- organize: fold a loose track into a folder ----------------------
- ---------- color each stem to match its parent group -----------------------
- ---------- click grid: detect tempo, snap section markers to bars -----------
- clear our prior prep markers then place
- ---------- CLI --------------------------------------------------------------

## scripts/pt_dialog_watch.py

- "Some inputs are missing" on open (interface not connected) untitled OK-only alerts (plug-in info notices and similar)
- [window, presses]: the SAME dialog window surviving 5 presses means a modal behind it has Pro Tools wedged
- plug-in trial offers: never start or buy one
- trial prompts repeat once per track as NEW windows; only the same window surviving presses is a wedge

## scripts/ptax.py

- not macOS, or pyobjc missing: --help still works
- Escape to Pro Tools only; a global keystroke lands in whatever app is in front

## scripts/ptctl.py

- These two strings are what Pro Tools shows in its "allow connection" dialog the first time. Keep them stable so the grant sticks. Override with the PTSL_COMPANY / PTSL_APP environment variables if you want your own names.
- State setters that all share the (track_names: List[str], new_state: bool) shape.
- ---- commands ----------------------------------------------------------------
- Commands whose availability is version/edition-gated - probed by `caps`. Each: (CId name, benign request body) - body that's valid enough to reach the implemented/unimplemented check without mutating the session. Non-destructive probes: invalid args reach the implemented/not-implemented check WITHOUT mutating the session. "supported (arg err)" means the command exists; "UNSUPPORTED" means this PT build doesn't implement the command id.
- Wishlist commands that may be ADDED in a newer PTSL. Probe by name so they get picked up automatically once py-ptsl ships a proto that defines them.
- Saved PTSL command list. Ships with the Pro Tools 2025.6 list in references/.
- which wishlist commands now exist in the proto at all
- diff full command set vs saved baseline -> reveals new commands after update
- try eval first (expression), fall back to exec (statements)
- default to turning the flag ON if no state was given
- `launch` runs WITHOUT a connection (Pro Tools may be down)
- surface PTSL errors cleanly for chat

## scripts/ptprep.py

- Records which memory-location numbers this tool placed, per session, so `clear-prep` removes only those. Lives outside the skill folder.
- ---- session audio discovery -------------------------------------------------
- match a file whose name starts with the clip root
- ---- marker placement --------------------------------------------------------
- Absolute (sample) reference so markers stay put when tempo is set later - NOT Bar|Beat, which would drag them around once a tempo map exists.
- record for clean removal later, keyed by session
- ---- commands ----------------------------------------------------------------
- harmonic/primary source (for snapping)
- default to sections if no marker type chosen
- --lyrics / --structure override plain section markers with named sections
- fall through to also add bars/beats below
- provides --sections (count), --beats-per-bar

## scripts/ref_align.py

- onset-ish envelope makes the correlation robust to mix differences

## scripts/ref_compare.py

- A constrained search beats inverting the whole mix. Only move the groups that dominate a band that is actually off, cap the move, and score on band shares.
- coordinate descent, a few sweeps

## scripts/ref_offset.py

- beat-periodic grooves make onset envelopes agree at +/-1 beat too; the spectrum (chords, who plays) does not.

## scripts/route_folders.py

- verify from a fresh read, not from what route_track reported

## scripts/route_groups.py

- The folder list comes from the open session. Do NOT hard-code a bus list from CId_GetExportMixSourceList: it only enumerates buses already in use as a source, so an absent name there means "nothing feeds it yet", not "no such bus". The bus a folder owns is shown on the folder's own input selector and is usually, but not always, the folder's name.

## scripts/session_map.py

- tempo: is the audio on the session grid? strong onsets vs the 8th grid, swept over tempo and phase

## scripts/stemid.py

- 3 s an FX return can ring after its dry note dB/s; dry vocals drop ~-280, reverb/delay returns ~-100..-160
- Class -> routing folder in YOUR template. These defaults match a common layout (DRUM GROUP > KICK/SNARE/TOM/OH GRP; BAND > BASS/GUITAR/KEYS/ORCH; VOCALS > LV/BGV).
- ---------- io + cache --------------------------------------------------------
- ---------- per-signal features -----------------------------------------------
- under half a second of signal = dead stem
- 10 ms onset envelope: L/R halves of one source hit in sync, two takes do not
- decay: how fast the level can fall (2nd percentile of the slope, dB/s)
- fine spectrum: chroma for "same notes?" and the lowest resonance for kick vs tom
- ---------- AST (AudioSet) tagging ---------------------------------------------
- ---------- pairing ------------------------------------------------------------
- ---------- classification -----------------------------------------------------
- hits, not notes (boomy kicks and toms read as harmonic, so a clear drum tag also counts)
- a stereo vocal that sounds for a few seconds, alone, is an FX moment, not a part
- lines: stems singing the same notes at the same time (lead + doubles, or a harmony stack)
- a stem that mostly sings alone is the lead in those bars
- FX returns: ring on one dry stem (its VERB) or throw on a few words (VOCALS)
- ---------- driver -------------------------------------------------------------
- could be a tight double; confirm
- stems of different lengths line up at 0
- delay throws, however the tagger heard them

## scripts/stemqc.py

- A very sparse group (a few short hits) never produces a run long enough to span, so "silent" here would be a lie -- check its peak.

## scripts/stems.py

- Template folder -> stem name. A folder not listed here becomes a stem named after itself.
- these are containers; their child folders are the stems
- top-level folder, or a folder directly in BAND / VOCALS AGs / Piano get their own stem KICK GRP, TAIKO HITS, RIDESSSS ride with their parent
- any ancestor folder named LV, LVs, LV DBLS ...
- a renamed vocal comp still belongs to the vocal stems
- some producers file every guitar under EG: acoustics become AGs, the rest EGs
- nothing in this stem plays over the range: the stem list follows the song's material

## scripts/structure.py

- recurrence (long-range repetition) + path (local continuity), blended
- [start, end, type, vocal_level|None]
- fraction of peak vocal RMS to count a span as "has vocal"
- group span indices by structural type
- vocal-energy summary per type (only meaningful with a vocal stem)
- candidates that recur (>=2 spans) and carry vocal
- pass 1: assign a BASE label (no number) to every span
- pass 2: merge consecutive spans sharing a base label
- pass 3: number repeated labels and finalise

## scripts/verify_routing.py

- -60 dB is the line. A bus with nothing assigned to it reads -240 dB (true digital silence); -78 dB is plug-in noise floor bleeding through an otherwise empty bus, not audio. The main bus reads near 0 dB when it has the mix.
