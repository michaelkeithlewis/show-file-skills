# protools: Pro Tools control and session prep for Claude Code

A Claude Code skill that drives a running Pro Tools session through Avid's Pro
Tools Scripting SDK (PTSL), and covers the whole studio chain: a folder of stems
becomes a templated, organized, routed and marked-up session, gets a first premix,
and goes back out as a properly named, versioned bounce delivered to the client on
Samply (with the [`samply/`](../../samply/) skill) or to mastering.

You ask in plain words ("mute the drums", "drop a marker at the chorus", "prep
this song from these stems", "route the stems to their groups") and Claude runs
the scripts in this folder on your Mac.

## What it does

- **Control:** transport, mute/solo/record-enable and the other track states,
  track selection and creation, markers, timeline selection, session info, save,
  import, and offline bounces (`scripts/ptctl.py`).
- **Session prep:** create a session from your template, import stems, turn
  dual-mono stems into true mono tracks, fold stems into the template's routing
  folders, route each track to its folder bus, color by group
  (`scripts/prep_session.py`, `scripts/route_folders.py`).
- **Markers:** tempo and key detection, click-grid fitting with a candidate table
  for octave and triplet errors, and verse/chorus/bridge markers from lyric
  repetition (Whisper), musical repetition, or an arrangement map for
  instrumentals (`scripts/ptprep.py`, `scripts/stemqc.py`).
- **Stem QC:** dead or clipped stems, per-group activity in bars, and
  identification of unnamed stems by listening (`scripts/stemid.py`).
- **Premix:** clip-gain staging to -18 dBFS, one headroom trim, a role-based balance
  checked against a reference, top-down folder faders, and a check for anything that
  sticks out (`scripts/clipgain_normalize.py`, `scripts/premix.py`).
- **Reference and headphones:** a song's reference loaded into ADPTR Metric AB synced
  to the timeline, with its offset against the stems measured first
  (`scripts/metricab_ref.py`, `scripts/ref_align.py`, `scripts/hp_metricab.py`).
- **Files, bounces and delivery:** a song-folder layout, one bounce name used
  everywhere (`<Song>_<Initials>_V<n>_PtMst.wav`), versioning, a FINALS folder for
  mastering, and upload to Samply as a new track or a new version
  (`references/session-prep.md`, "Bounce, name, version, deliver").
- **Stems and instrumentals:** solo-in-place prints of every stem and a no-vocal
  version through the full master chain, named and zipped for delivery, with a click
  scan for edits the full mix hides (`scripts/stems.py`, `scripts/snapscan.py`,
  `references/stems.md`).
- **Live captures:** stems onto a streaming or broadcast template's own tracks from a
  map, and section markers for a service or a show with no click
  (`scripts/place_onto.py`, `scripts/envelopes.py`, `scripts/tx_regions.py`).
- **GUI gaps:** The existing routing scripts use `scripts/ptax.py` and the macOS
  Accessibility API, by control name, with no mouse or screen coordinates. Newer
  SDK output-ID reuse is documented in the field notes below.

The playbooks and format notes are in `references/`.

## Requirements

- macOS with Pro Tools 2025.6 or later (PTSL is built in). Verified on Pro Tools
  2025.6.1 / PTSL 2025.
- Python 3.9 or later.
- For `ptax.py`, `route_folders.py` and `demo_guard.py`: Accessibility permission
  for the app that runs Python.
- Your own session template. This skill builds from a template because PTSL cannot
  add plug-ins.

## Install

1. Copy this folder to `~/.claude/skills/protools` (Claude Code loads every folder in
   `~/.claude/skills/` that has a `SKILL.md`). For delivery, also copy
   [`samply/`](../../samply/) to `~/.claude/skills/samply` and follow its README.
2. Create the venv and install the packages:
   ```
   cd ~/.claude/skills/protools
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
   `faster-whisper` (lyric markers) and `onnxruntime` (stem identification) are
   optional. Remove them from `requirements.txt` if you do not need them.
3. Grant Accessibility: System Settings > Privacy & Security > Accessibility, add
   the terminal app that runs Claude Code (Terminal, iTerm, or your IDE). Check it:
   `.venv/bin/python scripts/ptax.py trusted` must print `True`.
4. Start Pro Tools, then run `.venv/bin/python scripts/ptctl.py status`. The first
   time, Pro Tools asks you to allow the connection ("ShowFileSkills / ClaudeCode").
   Accept it. To show other names, set `PTSL_COMPANY` and `PTSL_APP`.

## Quick start

```
PY=.venv/bin/python
$PY scripts/ptctl.py launch                 # open Pro Tools if needed, wait for PTSL
$PY scripts/ptctl.py status
$PY scripts/ptctl.py tracks
$PY scripts/ptctl.py mute "BASS" on
$PY scripts/ptctl.py marker "Chorus 1" --time "0:45"

$PY scripts/stemqc.py levels "<stems dir>"
$PY scripts/prep_session.py channels "<stems dir>"
$PY scripts/prep_session.py grid kick.wav snare.wav hats.wav
$PY scripts/route_folders.py --dry
```

In Claude Code, just ask: "prep this song from the stems in <folder> using my
template <group>/<name>", "premix it against the reference", "bounce V2 and put it
on Samply as a new version".

## Status: what is proven and what is not

Proven on real sessions:
- Every `ptctl.py` verb, on Pro Tools 2025.6.1.
- The prep pipeline end to end (create from template, raw import, spot-by-id
  foldering with EDL verification, color, markers) on a 2026 build, including a
  64-stem drop with no input from the engineer.
- `route_folders.py`: 51 of 51 tracks routed on a test session.
- `set_tempo.py`, `clipgain_normalize.py`, `pan_to_mono.py`, `premix.py` (all verbs),
  `merge_pairs.py`, `resample_session.py`, the Metric AB reference flow and the
  template-update helpers, on real sessions on a 2026 build.
- `stemid.py`: 45 of 51 folders and 25 of 25 L/R pairs on a 76-file test drop.
- Offline bounces with `export_mix`.

Known limits (PTSL has no command for these):
- Meter, pan, faders, plug-in insert or bypass, track order, move into
  folder, combine two monos to stereo. Tempo, pan and faders have no PTSL command
  either, but `set_tempo.py`, `pan_to_mono.py` and `premix.py apply` set them through
  Accessibility. Spotting clips by id combines two monos into one stereo track.
- The original output-ID lookup needed the Private API (an Avid-issued key), so
  the existing scripts use Accessibility. Newer 2026.4.1 tests reused an assigned
  route through `GetTrackMainOutputAssignments`; see the field notes below.
  Accessibility controls only exist for tracks Pro Tools has drawn on screen.
- `import_audio` in py-ptsl is broken; the scripts call the raw command.
- Tempo detection is an estimate. Read the candidate table and confirm by ear.

Verified for this release (on a machine without Pro Tools):
- `python3 -m py_compile` on every script.
- `--help` on every CLI.
- Offline smoke tests on synthetic audio: `prep_session.py channels` and `grid`,
  `stemqc.py levels` and `arrangement`, `analyze.py`, `interleave.py`,
  `envelopes.py`, `ref_compare.py`.
- `place_onto.py`, `ref_align.py`, `tx_regions.py`, `hp_metricab.py` and
  `metricab_ref.py` were generalized for publication (hard-coded maps and paths became
  arguments) and have not been re-run in that form.
- The PTSL and Accessibility scripts were not re-run against Pro Tools after the
  clean-up for publication (paths and names changed, logic did not).

## Additional macOS field notes

[Franklin Rice's session-prep field notes](references/macos-session-prep-field-notes.md)
record version-scoped 2026.4.1 output-ID reuse, a successful prepared-template
session-data import request, Accessibility pitfalls, optional MonoMate handoff
measurements and checkpoint findings. These supplement the existing scripts;
they do not change their behavior or imply that every reported SDK limitation
is resolved on every version.

## No warranty

These scripts are examples to adapt. They come with no warranty. Save your
session before a prep, and work on a copy when in doubt. This project is not
affiliated with or endorsed by Avid. Pro Tools is a trademark of Avid Technology.

More Accessibility rules (save panels, hung jobs, Logic) are in `../../apple/macos-accessibility/README.md`.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

## Built on tour

Built by Michael Lewis, touring engineer and co-founder of
[Truck Packer](https://truckpacker.com), the truck-pack planning app for touring
and production crews.
