# Session prep: stems to a mix-ready Pro Tools session

The playbook for turning a folder of stems into a templated, organized,
marked-up session, and for getting the mix back out: file layout, premix, bounce
naming and versioning, and delivery. The scripts are in `scripts/`. Run every one
with the venv python (`PY=.venv/bin/python`, see README.md). Pro Tools must be
running with a session open where noted.

The whole chain, in order:

1. File layout: put the drop where the session will live (below).
2. Pre-flight: Pro Tools up, iCloud handled, dialog watcher running.
3. The pipeline: read the drop, create from template, import, channel formats,
   folders, routing, clip gain, color, tempo and markers, headphones and reference.
4. Premix (only when asked): a first balance.
5. Bounce, name, version, deliver (to Samply with `../../samply/`, or a FINALS
   folder for mastering).

## File layout

Pick one layout and keep it, so a script (and the next person) can find every song:

```
<projects root>/<Artist>/<Project>/<Song>/          e.g. STUDIO PROJECTS/<Artist>/2026 EP/<Song>/
    <Song>.ptx                                       the session (Pro Tools names it)
    Audio Files/  Bounced Files/  Session File Backups/
    <Song> Reference.wav                             the client's demo or rough mix
    Stems/                                           the drop as it arrived (keep the sender's subfolders)
```

- Stems arrive as a zip or folder in Downloads, or as a cloud-drive share. Copy them
  into the song's `Stems/` and check the copy (file count and sizes, or
  `rclone check --size-only` for a share) before you build.
- Name the artist folder the way the artist bills themselves on their own material.
- Name a capture or one-off session folder by what it is and when it was recorded
  (`<MM.DD.YY> - Full Set`), not by the year you mixed it.
- If the drop has no song title (a share named `MULTITRACKS`), build under
  `UNTITLED <MM.DD.YY>` and let the engineer rename it. Do not guess a title.
- Keep docs (advances, input lists, contracts, stage plots) in a separate tree from
  audio, so a session folder only holds session data.
- `Bounced Files/` is where every bounce lands (`export_mix` writes there). Never
  rename or delete a delivered bounce; a new mix is a new version (see "Bounce, name,
  version, deliver").
- If the projects root is iCloud-synced, build in a `.nosync` folder (below) and
  move the finished song folder in afterwards. A shell `mv` into iCloud can drop
  empty scaffold folders (`Bounced Files`, `Clip Groups`, `Video Files`); `mkdir`
  them back or let Pro Tools recreate them.

## Pre-flight

1. Run `$PY scripts/ptctl.py launch`. It launches Pro Tools if needed and waits for
   the scripting server on 127.0.0.1:31416. It returns `already-running`,
   `launched` or `timeout`.
2. Run `$PY scripts/ptctl.py status`. If it hangs right after a launch, Pro Tools is
   showing the "Allow ClaudeCode to connect" dialog. Accept it.
3. Do not test whether Pro Tools is alive with `pgrep`. A crashed Pro Tools leaves a
   `crashpad_handler` process whose arguments contain "Pro Tools". `launch` checks
   the socket, which is the real answer.

### iCloud-synced Documents

If `~/Documents` syncs to iCloud, Pro Tools can freeze or slow down:

- **Create-from-template hangs** while Pro Tools writes the new session through the
  iCloud File Provider. Create into a folder whose name ends in `.nosync` (Apple's
  exclusion suffix), for example `<your projects>/_LOCAL.nosync/<Song>`. Move it
  into the synced folder afterwards if you want it there.
- **Slow opens.** Pro Tools scans every preset under
  `~/Documents/Pro Tools/Plug-In Settings` while it opens a session. If those files
  are iCloud placeholders, each read waits on the network. Make sure the folder is
  downloaded: `find "<dir>" -name '*.icloud' | wc -l` must print 0.
- **Evicted stems.** Import works by reference. If iCloud evicts the stems, the
  session goes offline. Keep stems in a `.nosync` folder, or materialize them first
  with `$PY scripts/prep_session.py download "<stems dir>"`.

### A create looks like a hang for 10 to 20 minutes

While Pro Tools builds a big template session it instantiates every plug-in. During
that window PTSL answers `PT_NoOpenedSession`, the `.ptx` on disk is a 0-byte stub,
and no window is open. All three are normal. The real signal is CPU:
`ps -A -o %cpu,comm | grep "MacOS/Pro Tools"` reads 90 to 300 percent while it
works, and near 0 for minutes when it is wedged.

### Never kill a hung PTSL client

Killing a client in the middle of a command can leave Pro Tools' alert suppressor
in place. Every later connection then fails with
`PT_UnknownError (Another alert suppressor is already present.)`, and only a
restart of Pro Tools clears it. Run long calls in their own terminal or in the
background with output to a log, and read the log.

`scripts/demo_guard.py` answers the routine dialogs (plug-in demo offers, Missing
plug-ins, Session Notes) while a session opens. Run it in a second terminal.

For any unattended run, also start `scripts/pt_dialog_watch.py` in its own terminal. It
logs every dialog's title, text and buttons, and saves a screenshot to `~/pt-dialog-shots/`
once Screen Recording is granted (without it, the logged text is the record). It answers
`Session Notes` ("Some inputs are missing") with **No** and untitled OK-only alerts (plug-in
info notices, `"Follow Main Pan" will be disabled`, which appears when a main output is set
to `no output`) with **OK**. Stop it with `touch /tmp/pt_dialog_watch.stop` before anyone
works in Pro Tools again: it clicks dialogs for them.

## The pipeline

### 0. Read the drop before you build it

```
$PY scripts/stemqc.py levels "<stems dir>"                 # peak / RMS / % active per stem
$PY scripts/prep_session.py channels "<stems dir>"         # mono / dual-mono / stereo / L-only / R-only, then pairs
```

- Count the files and compare with what the sender says they sent. Drops often
  arrive as a tree (`BASS/`, `DRUMS/KIT/`, ...). Every script here walks the tree.
  Use the sender's subfolders as the folder map when they exist.
- `levels` finds dead stems, stems pinned at full scale, and stems that barely play.
- `channels` reads the WHOLE file. Never decide from the first seconds: a stem can
  be identical L/R in the intro and stereo in the body.
- A re-export of the same song can change a stem's channel format. Re-run
  `channels` on every drop.

### 0b. Unnamed or misnamed stems: listen instead of guessing

For files called `Audio 1_03`, `Track 07` or `Inst 1`:
```
nice -n 15 $PY scripts/stemid.py "<stems dir>" --json stemid.json   # --debug for features and tags
```
It reads no names except a channel suffix (`.L/.R`, `_L/_R`, ` L/ R`). For every
source it proposes a folder and a track name, plus `ok` or `check`:

- Pairs L/R halves, by suffix or by audio. Identical halves are reported as
  dual-mono. An audio-only pair (`stereo?`) can be a tight double (two takes in
  sync): confirm it.
- Splits drums into kick, snare, tom, overheads, cymbals, kit mics and percussion
  by spectrum.
- Groups vocal stems that sing the same notes (chroma) into lines. The line that
  covers most of the song is the lead (LV); other lines are harmonies (BGV). A
  slow-decay stem is a reverb or delay return and goes with the stem it rings on.
- The first run downloads the AudioSet AST model (about 350 MB) to `~/.cache/stemid`.

Show the table to the engineer and confirm every `check` row before you fold. On
one 76-file test drop, scored against the engineer's own map, it placed 45 of 51
sources in the right folder and found 25 of 25 L/R pairs. Known misses: bowed or
tremolo electric guitar can read as strings (treat any ORCH call as suspect), and
a doubled lead the producer kept on the lead playlist can read as BGV.

Edit the `FOLDER` table at the top of `stemid.py` to match your template's folders.

### 1. Create the session from your template

Build from a template, never from scratch: PTSL cannot instantiate plug-ins, so
the template is how inserts, sends, buses and VCAs get into the session.

```python
import sys; sys.path.insert(0, "scripts")
import prep_session as ps
ps.create_from_template("<template group>", "<template name>", "<Song>", "<parent dir>.nosync")
```

Group is the subfolder under `Pro Tools/Session Templates/`; name is the `.ptxt`
file name without the extension. `create_from_template` waits for the session to
open (it polls every 10 s for up to 30 minutes and prints progress), then returns
`{session, path, tracks, waited_secs}`.

A session template that is a plain `.ptx` (not a registered `.ptxt`) cannot go
through `create_from_template`. Copy the `.ptx` into a new session folder, create
`Audio Files/` beside it, and open the copy.

### 2. Import

```python
files = ps.stem_files("<stems dir>")      # recursive; print len(files) and check it
ps.import_stems(files)                    # raw CId_Import, one new track per file
```

The wrapped `import_audio` in py-ptsl is broken (see `PTSL_REFERENCE.md`).

**Match the sample rate first.** `AOperations_AddAudio` links a file without converting
it, and Pro Tools does not warn. A 44.1k stem in a 48k session plays 8.8% fast and
1.5 semitones sharp. `import_stems` refuses a mismatched file. Run
`prep_session.py rates "<stems dir>"`, then `prep_session.py resample "<stems dir>"` if a
rate differs. It writes 32-bit float AIFC copies at the session rate (afconvert, best SRC)
to `<stems dir> 48k/` and keeps the originals. Import that list. For a session that is
already built on the wrong rate, run `resample_session.py "<stems dir>" --dry` with the
session open, then run it without `--dry`. It swaps each affected track's clips in place
(Slip mode, Clear, spot at sample 0) and keeps plug-ins and routing.

### 3. Decide each stem's channel format

| `channels` says | Do |
|---|---|
| dual-mono (identical L/R) | One mono track. `dualmono_to_mono` spots the louder side's clip. No rebounce, half the DSP. |
| panned-mono (the quiet side is an exact scaled copy of the loud side) | One mono track from the loud side, panned to match. Build it as stereo, route it (4b), then run `pan_to_mono.py` (see "Panned-mono stems" below). |
| stereo | Keep stereo. |
| mono | Mono. |
| L-only + R-only (a stereo file pair, one side dead in each), or an L/R-named pair of mono files | ONE stereo track, always. `channels` lists the pairs at the end. `merge_lr_pair(e, name, folder, l_clip, r_clip)` spots the L file's left clip onto ch1 and the R file's right clip onto ch2. The clips can come from different files. No rebounce and no new file. For a session that is already built, run `scripts/merge_pairs.py "<stems dir>"` with it open. |
| L-only or R-only with no partner | One mono track from the live side. |

Some exporters print each half of a hard-panned part as a full stereo file with one
side silent. Take the side from the audio, not the name: one real drop named its right
half `... PAN L_2`. The side tag can also sit mid-name (`CINEMA TOM PAN L 2.0_1`). If
the pair's base name is already taken by another stem, add ` LR`.

Confirm the borderline ones with the engineer (correlation 1.0 with a level offset
is effectively mono).

### 4. Organize into the template's folders

PTSL has no "move track into folder" command. Create a new track inside the folder
and place the audio on it:

- **Preferred:** `CId_CreateNewTracks` with `insertion_point_track_name=<folder>`,
  then `CId_SpotClipsByID` at sample 0 with the imported clip ids (`.L` and `.R`
  together for stereo, one clip for mono). Then delete the loose source track.
  This placed 64 of 64 stems with no empties on one test drop.
- `fold_into_folder` (copy/paste) is the older method. It has silently left
  foldered tracks empty. Avoid it, or verify every track.
- To keep the template's own tracks (their inserts, sends and VCAs are the point),
  put the audio ONTO them with `move_onto(e, src, dest)`, or for a whole map
  `scripts/place_onto.py map.json --dry` (a list of `[stem track, template track]`
  pairs). Both paste at the session start time. A session that starts at
  `01:00:00:00` would otherwise get every clip an hour early.

Read the template's structure first:
`$PY scripts/ptctl.py exec "import json;print(json.dumps([(t.name,t.parent_folder_name) for t in e.track_list()]))"`.
(`ptctl.py tracks` does not show the parent folder.)

Default name map (confirm anything this does not place, or use the `stemid.py` proposal):

| Name contains | Folder |
|---|---|
| kick, snare, tom, OH, HH | the matching drum sub-folder |
| room, poke | the top drum folder |
| bass | BASS |
| gtr, elec, ACG | GUITAR |
| rhodes, keys, piano, organ | KEYS |
| strings | ORCH |
| vox, lead | LV |
| bgv | BGV |

If the template has no folder for a group, make one with
`CId_CreateNewTracks {track_type:"TType_RoutingFolder", track_format:"TFormat_Stereo", insertion_point_position:"TIPoint_Last"}`.
Its own output still needs assigning (step 4b).

**Verify every foldered track has audio** with the session text export:
`CId_ExportSessionInfoAsText {include_track_edls:True, output_type:"ESI_String"}`.
Each clip is a row under its `TRACK NAME:`. Those rows carry a ` (Stereo)` /
` (Mono)` suffix: strip it before you match names, or every track reads empty.
Cross-check `# OF AUDIO CLIPS` in the header (stereo stems add two clips each).
Do not trust "the selection looks right": `select_all_clips_on_track` on an empty
track leaves the previous selection in place.

### 4b. Route every foldered track to its folder bus (mandatory)

Tracks made by `CId_CreateNewTracks` output to the session's main bus, NOT to their
folder's bus, even inside a routing folder. Until they are routed, the template's
group processing gets nothing.

```
$PY scripts/route_folders.py --dry     # "<track>: <current> -> <bus>" for each track
$PY scripts/route_folders.py           # routes, then re-reads every output
```

It must end with `ROUTED`. It reads each folder's bus off the folder's own input
selector, so a folder called `DRUM GROUP` that owns a bus called `DRUMS` works. Aux
tracks and tracks already on their bus are skipped, so a re-run is safe. About one
minute for 50 tracks. This needs the Accessibility grant (README.md). The
template's own folders and aux returns keep their outputs; that is correct.

Fallbacks, in order: `references/gui-routing.md` (computer-use clicks), then
`route_groups.py` (selects each folder's tracks; you make one Option+Shift+click per
folder). `verify_routing.py` offline-bounces each folder bus and reads its peak,
when you want proof by audio rather than by selector labels.

Do not report a prep as done while any foldered track still outputs to the main bus.

### 5. Gain-stage with clip gain (never a rebounce)

`$PY scripts/clipgain_normalize.py --dry`, then the same command without `--dry`. Every
stem's gated average lands at -18 dBFS (details under "Panned-mono stems and clip-gain
staging" below). Run it on fresh clips only, and never while someone works in the session.

### 5b. Color by group

`ps.color_by_group(e)` sets each foldered audio track to its parent folder's palette
color. Do not run it on a template whose tracks carry their own colors inside a
folder: it repaints them. In that case color only the tracks you created, matching a
sibling (look up its hex in `CId_GetColorPalette`, set that index).

### 6. Tempo and section markers

Most produced songs are cut to a click, so the grid is constant.

```
$PY scripts/prep_session.py grid kick.wav snare.wav hats.wav shaker.wav
```

- Feed a DENSE percussive source and check `onsets`. A sparse source returns a
  confident wrong answer: kick and snare alone (11 onsets) once returned 165 for a
  song at 110 (the 1.5x triplet relative). Another song at 85 read 170 (the eighth
  note).
- Read the `candidates` table, not just `detected_bpm`. It scores the detected
  tempo, its relatives, and tempos from the modal inter-onset interval (the felt
  pulse) by on-grid share and RMS distance. The true tempo usually wins clearly
  (on one drop: 90 percent of onsets within 35 ms at 110, 44 percent at 82.5).
- Check the bar count against the song length before placing markers.

Sections, best to fallback:

1. **Lyrics** (needs a vocal stem): `$PY scripts/ptprep.py markers <harmonic src> --lyrics --dry-run`.
   Whisper transcribes the vocal; a repeated lyric block is a chorus, a unique
   block late in the song is a bridge, and boundaries snap to the musical
   segmentation. Needs `faster-whisper`.
2. **Structure** (no transcription): `--structure`. Musical repetition plus vocal
   energy.
3. **Instrumental drops:** `$PY scripts/stemqc.py arrangement "<stems dir>" --bpm <n>`.
   Both methods above degrade badly with no vocal (structure once returned one
   section for a whole instrumental cue). This prints which group plays in which
   bars and segments the summed mix. Name markers by what enters ("Piano in",
   "Full band in"), not Verse/Chorus.

Place markers on bar lines with `ps.place_grid_markers(e, sections, bpm)` (bar 1 =
0:00, Absolute reference). Always dry-run first. `ptprep.py clear-prep` removes
only the markers these tools placed.

PTSL cannot write tempo, but the Tempo ruler's Tempo Change dialog can:
`$PY scripts/set_tempo.py <BPM>`. It presses `Add Tempo Change`, refuses unless the
dialog opens at `1| 1| 000` (insertion point at the session start), types the BPM (an
AXValue write is ignored), presses OK, and reads back the Edit window's tempo. Check
the timebases first: every audio track must be sample-based (`t.timebase == 1`), so
audio and Absolute markers do not move. The meter stays at the template's.

### 6b. Headphones and the reference (per song, if your template uses them)

- **Headphones off the master bus.** If you monitor through a separate output (for
  example the computer's headphone jack), put a pre-fader send on the master bus to
  that output and set the bus's main output to `no output`, with the print coming off
  a bus above it. `$PY scripts/hp_metricab.py --track "MASTER BUS" --hp "<output name>"`
  sets and checks it. `$PY scripts/strips.py "MASTER BUS" "Click 1"` shows a strip's
  inserts, sends and output.
- **Reference into Metric AB.** If the template carries ADPTR Metric AB on the master
  bus, put the client's demo or reference in slot 1, synced to the timeline. PTSL cannot
  load a file into a plug-in and Metric AB's file slots are not exposed to Accessibility,
  so go through a preset:
  1. Save any Metric AB preset once as a seed (Settings menu > Save Settings As). Keep
     your standing references in its other slots; they are kept.
  2. `$PY scripts/ref_align.py "<song folder>"` cross-correlates the reference with the
     summed stems (stems sit at Pro Tools 0) and prints the offset. Fix an offset in the
     file, not in Metric AB: pad a negative offset with that much silence at the front
     (same rate and format), save it as `<Song> Reference ALIGNED.wav`, and leave the
     client's original untouched. Before padding, check that the offset holds in several
     40 s windows: a steady value is a trimmed print, a drifting one is a different edit.
  3. `$PY scripts/metricab_ref.py seed.tfx "<song folder>/<Song> Reference.wav"
     "~/Documents/Pro Tools/Plug-In Settings/ADPTR MetricAB/<Song> - REF.tfx"`.
  4. `$PY scripts/hp_metricab.py "<Song> - REF"` opens the insert and picks the preset
     from the Librarian menu. Save the session. Delete the `.tfx` afterwards if you do
     not want it in the Librarian.

### 7. Save and report

`e.save_session()`, then report: stems imported, foldered and routed, channel
decisions, BPM and section bars, and the manual steps below. Do not report a prep as
done while any foldered track still outputs to the main bus.

## Updating your template (and pushing the change into built sessions)

Use this when you change template tracks in one song (vocal FX returns, the master's
routing) and want the template and the other unmixed songs to match. Pro Tools does the
copy through Import Session Data, so no restart is needed. Pro Tools holds one session at
a time, so every step closes the open session. Save that session first. Do not edit the
`.ptxt` as binary: the block schema drifts between versions, and new plug-ins need
session-wide table entries.

1. Back up the template `.ptxt`.
2. Start `pt_dialog_watch.py`. It answers the `Session Notes` report each import raises.
   Then create a session from the template into a `.nosync` scratch folder.
3. Run `scripts/push_session_data.sh "<source song .ptx>" "<scratch session .ptx>"`. It runs two imports:
   - `FX_TRACKS` (default: the vocal FX returns) replace their same-named tracks with all track data.
   - `MASTER_TRACKS` (default: `MASTER BUS`) take only main outputs and sends. The target keeps its
     own master chain and its reference plug-in state.
4. Run `ptax.py menu File "Save As Template..."`. Keep **Install template in system** and the
   category. The name field ignores Accessibility writes: focus it, then type with
   `ptkeys.py key 0 cmd` (select all) and `ptkeys.py text "<template name>"`. Press OK, then **Replace**.
5. For each unmixed song, run `push_session_data.sh "<source .ptx>" "<song .ptx>"...`. One call
   takes several targets. Then run `merge_pairs.py "<stems dir>"` and `route_folders.py --dry` while each
   song is open.
6. Stop the watcher (`touch /tmp/pt_dialog_watch.stop`).

The helpers use Accessibility only and never type into the frontmost app:
`ax_open_panel.py` (moves through the Open panel by selecting rows and pressing Open; keystrokes
posted to the app do not reach that panel), `isd.py` (Import Session Data destinations), `trackdata.py`
(the Track Data to Import checkboxes), `strips.py` (a strip's inserts, sends and output),
`opensess.py` (open a session and wait for it), `ptkeys.py` (keys posted to the Pro Tools pid only).

## Manual steps PTSL cannot do

- Set the meter. (Tempo: `set_tempo.py`.)
- Pan. (Hard-panned pairs do not need it: they become one stereo track in step 3.)
- Bypass plug-ins. Reorder tracks (for example move utility tracks to the top).
  (Faders: `premix.py apply` types them through Accessibility.)
- Set the main output of a track that is not in a folder: use
  `ptax.py route <bus or output> <track>...` (Accessibility).
- VCA membership for tracks you created.

## Long live captures (one file per input, a whole show)

- Put the audio ONTO the template's tracks and keep every template track
  (`place_onto.py`). The engineer migrates plug-in settings themselves. Stems the
  template has no slot for get a new track in the right folder.
- Read `e.session_start_time()` first. A broadcast or streaming template often starts
  at `01:00:00:00`, and pasting at zero puts every clip an hour early.
- Do not run `color_by_group` on a template whose tracks carry their own colors. Color
  only the tracks you create, matching a sibling.
- Mono L/R pairs for a stereo template track: `interleave.py L.wav R.wav out.wav`
  into the session's `Audio Files`, import, place on the stereo track.
- Keep console channel numbering in track names stable week to week, even when a
  channel is empty.
- **The click is the timing authority.** Lyric timestamps land tens of
  milliseconds off the beat and can put a song boundary in the wrong place.
  Peak-pick the click stem, split it into click-active regions (a gap over about
  2.5 s ends a region; a song can span two regions when the click pauses). A song
  marker goes on its region's first click. Section markers come from lead-vocal
  onsets, snapped to the nearest click. Songs with no click sit in the gaps; place
  those from the lyrics. Use the lyrics and the setlist only for titles and order.
- Give each song (its marker and its sections) one marker color, cycling through
  high-contrast colors with no adjacent repeats.
- A common convention: crowd mics in a basic folder routed straight to the main
  bus (`ptax.py route <bus> <tracks>...`); utility tracks (board feed, click,
  talkback) at the top, muted and uncolored (`color_index: -1`); drum triggers in a
  basic folder at the bottom, muted.
- Still manual afterwards: VCA membership for new tracks, and inserts on them.

### Captures with no click (a service, a talk, a festival set)

Build a per-second envelope of every stem with `envelopes.py`, then read the show
off it: band stems active = a song; spoken mics active with the band quiet = talk;
only crowd mics active = a quiet section. Transcribe only those regions with
`tx_regions.py <stems dir> regions.json` (it mixes each region to 16 kHz mono and runs
Whisper) to name songs and speakers. Place the markers Absolute and color them by kind,
for example songs green (10), spoken amber (7), message or talk blue (12), structural
grey (15).

## Reference-mix pass

`$PY scripts/ref_compare.py "<stems dir>" reference.wav` reports the global trim,
band-by-band tonal balance against the reference, and which group owns each band.

Do not hand anyone a least-squares inversion of the mix. Groups overlap spectrally
and the reference is compressed and limited, so a fit confidently returns nonsense
("cymbals -79 dB"), and regularizing it just returns "every group +0.0 dB". Band
shares and band ownership are stable. The constrained search at the end is a
starting point and says when it hits its +/-12 dB clamp.

## Housekeeping

- Deleting an audio file does not remove its clips from the session's clip list,
  and PTSL has no "clear unused clips" command. Decide the file layout before you
  import, or rebuild from the template.
- To hand a session to someone else when the audio was imported by reference,
  send the `.ptx`. They open it, point Pro Tools at their copy of the stems, and
  Find All relinks by name. For a self-contained copy, use File > Save Copy In with
  audio files.

## Output routing through PTSL: original probes and newer findings

| Route | Result |
|---|---|
| `CId_SetTrackMainOutputAssignments` | Works, but needs a `signalpath_id`. |
| `CId_GetTrackControlInfo` (id source used in the original probes) | "Private API has not been enabled". `CId_EnableAPI` needs an Avid-issued encrypted key. |
| A bus name as the id | "Signal path with ID ... was not found". |
| Enumerating ids | 0 to 63 all rejected. Ids are 128-bit GUIDs. |
| A track's own `.id` / `.id_compressed` | A different id space; rejected. |
| `CId_CreateSignalPath` for a bus | "Creating signal paths of type 'SPType_Bus' is not yet implemented". |
| `CId_Import` with `IType_Session` (Import Session Data) | Original request failed with `PT_InvalidParameter`; a later explicit prepared-template request completed on 2026.4.1 (see below). |

`CId_GetExportMixSourceList` lists only buses something already feeds, so a bus
missing from it may still exist. Never hard-code a bus list. With a Private API key,
the unlock would be: `EnableAPI(key)`, `GetTrackControlInfo` on a correctly routed
track to read its `signalpath_id`, then `SetTrackMainOutputAssignments` on the new
track. Accessibility remains a working fallback.

Later Pro Tools 2026.4.1 / SDK 2026.4 tests retrieved an already-assigned output's
`signalpath_ids` using `CId_GetTrackMainOutputAssignments`, then used the setter
for grouped output assignment without an EnableAPI call. Session-data import
also completed with an explicit prepared-template request, including
`audio_handle_size: 1000`, Import As New Track and Do Not Import playlists.
Neither result establishes a universal fix for older request/version failures.
See [macOS session-prep field notes](macos-session-prep-field-notes.md) for the
payload, checks, MonoMate handoff findings and sanitized full-run timing.

## Panned-mono stems and clip-gain staging

- **Panned-mono:** a mono part printed into a stereo file with a pan. The quiet side is an exact
  scaled copy of the loud side, and `channel_kind` returns `panned-mono`. Build it as stereo and
  route it. Then run `pan_to_mono.py --dry`, and run it again without `--dry`. The script creates a
  mono track from the loud side in the same folder slot and copies the bus, color, solo and mute. It
  types the pan into the Output window's `Front Pan Numerical` field. Pro Tools pans mono with an exact
  sin/cos -3 dB law (0 = -3.01/-3.01 dB, 61 = -10.41/-0.41 dB), so
  pan = `100*(4*atan(loud/quiet)/pi - 1)` reproduces the printed ratio. Half the DSP per track.
- **Clip-gain staging:** `clipgain_normalize.py --dry`, then the same command without `--dry`. It sets
  each track's clip gain so the gated average level sits at -18 dBFS. Peaks stop at -1 dBFS, and clip
  gain stops at +36 dB. PTSL has no clip gain command, so the script sends Ctrl+Shift+Up/Down (one Clip
  Gain Nudge each) to the Pro Tools process after `SelectAllClipsOnTrack`. Run it only on fresh clips,
  and never while someone is working in the session.

## Premix: a first balance

1. `clipgain_normalize.py`: clip gain puts every stem's gated average at -18 dBFS.
2. `premix.py trim --out trim.json`, then `premix.py apply trim.json`: one fader value for every stem,
   so the loudest bus peaks at -6 dBFS before plug-ins.
3. `premix.py verify --ref <reference>`: offline-bounces every bus in one pass
   (`EM_DF_FilePerMixSource`) and reports peaks, loudness and tonal bands against the reference.
4. `premix.py plan --ref <reference> --out plan.json`, then `apply`, then `verify`. Each stem is
   loudness-matched inside its folder. Each folder goes to a role offset from the kick (`ROLE_TARGETS`
   in `premix.py`: snare 0, bass -1, toms -3, guitars, keys and orchestra -4, lead vocal 0, BGV -6,
   cymbals, percussion and FX -9). The reference nudges each folder by at most +/-3 dB. A free
   spectral fit is degenerate, because group spectra overlap: on one song it matched every band
   within 2 dB and put the toms 12 LU over the kick.
5. `premix.py check --faders plan.json --bpm N`: flags any folder that comes within 2 LU of the whole
   mix in a 4-bar window (kick, bass and the lead vocal are exempt). A flag is fine when that folder
   is the only thing playing, as in a keys-only intro.
6. Save. Copy the plan to `<session>/.premix_faders.json`, and report folder loudness against the
   kick, bus peaks, and bands against the reference.

Every premix script refuses to run if someone used the Mac in the last 2 minutes, and stops if anyone
touches it mid-run. Back up the `.ptx` first. Clip gains are logged in `<session>/.premix_clipgain.json`,
because PTSL cannot read clip gain back; a rerun skips tracks that are already gained.

Faders are typed into each track's Output window (`Volume Numerical`). Posted keystrokes reset the
Mac's HID idle timer, so `ptgui.py` records its own last keystroke to tell its input from a person's.

## Premix: top-down faders

After `plan`, run `premix.py topdown --faders plan.json --out td.json`, then `premix.py apply td.json`.
Use `--live` instead of `--faders` if the session changed. What a folder's children share moves onto the folder fader,
deepest first and then up to the parent, so stem faders sit near unity with good resolution. Folder faders sit after
the folder's plug-ins, so a folder's children are lifted only until its bus input reaches -6 dBFS peak or -18 LUFS.
A folder fader the engineer set by hand is left alone (a folder driven hot into its own plug-ins
sounds different if you move what feeds it). The sum of faders on every path stays the same, so the
mix does not move. `apply` types the folder faders too.

## Revisions: finding a pop

Bounce every bus in one pass. The bus with the HF burst names the folder, and a one-sample step in that bus over
smooth raw stems means a plug-in or automation did it. Check every fix with a bounce from the song start, because
time-based and triggered plug-ins carry state from where playback begins. `declick.py` repairs a few milliseconds of a
bounced file by AR interpolation.

`ptgui.nudge_clip_gain_range(e, track, t0, t1, steps)` puts clip gain on part of a track (see
`PTSL_REFERENCE.md`, "Field notes").

## Bounce, name, version, deliver

### Naming

Use one name for a bounce everywhere: the `export_mix` `base_name`, the file in
`Bounced Files/`, and the name on Samply or in a delivery folder. A convention that works:

```
<Song>_<Initials>_V<n>_PtMst.wav        e.g. Song Title_AB_V2_PtMst.wav
```

- `<Song>` in Title Case. Not the project's track-number name (`06 - SONG`), and not
  `SONG V2`.
- `<Initials>`: the mixer's initials, so a client folder with several mixers stays clear.
- `V<n>`: V1 for a song's first mix, then V2, V3. Use V2.1 for a small fix on V2. To find
  the next number, list `Bounced Files/`. Never overwrite a delivered version.
- The bus: `PtMst` (post master bus, what the artist approves) or `PrMst` (pre master
  bus, the print for mastering). Live records follow the same rule.

### Bounce

- Default: the `PtMst` bus, 24-bit / 48 kHz stereo interleaved WAV, offline, over the
  song's selection memory location (`ptctl.py locate <n>`, then `export_mix`). Recipe in
  `PTSL_REFERENCE.md`.
- Ask for format, source bus and offline or realtime only when there is no standing
  convention. Bouncing writes to disk: confirm first.
- Some sessions print one 4-channel 32-bit float file with the post-master mix on
  channels 1-2 and the pre-master mix on 3-4. Check by level: channels 1-2 match the
  separate PtMst, channels 3-4 are several dB quieter. Split 3-4 out for the PrMst.

### Deliver to the client (Samply)

Use the `samply/` skill in this repo (`../../samply/`):

- Upload the `_PtMst` bounce into the artist's project (or its mix folder), under the
  same name. Never send the `_PrMst` to a client.
- A new mix of a song that is already on Samply is a new **version** of that song's
  stack, not a new track: upload with `--version-of <stack id>`. Uploading with the
  same name alone makes a duplicate track.
- Verify in the web app that the upload shows a duration. A 200 from the API is not
  proof that it processed.
- A client reference or demo can sit in the song's stack as its oldest version, so the
  client can A/B (do that in the web app; the API cannot reorder versions).

### Deliver to mastering (a FINALS folder)

In `Bounced Files/`, make `<Song or Project> FINALS/` holding the latest `_PrMst`
(32-bit float) and `_PtMst` of every song, plus a short note to the mastering engineer
that explains Pr (pre master bus, for mastering) and Pt (post master bus, approved by the
artist) and states the bit depth of each. Zip it Finder-style:
`ditto -c -k --sequesterRsrc --keepParent "<dir> FINALS" "<dir> FINALS.zip"`.
