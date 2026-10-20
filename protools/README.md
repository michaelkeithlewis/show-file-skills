# protools: Pro Tools control and session prep for Claude Code

A Claude Code skill that drives a running Pro Tools session through Avid's Pro
Tools Scripting SDK (PTSL), and turns a folder of stems into a templated,
organized, routed and marked-up session.

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
- **GUI gaps:** PTSL cannot set a track's output. `scripts/ptax.py` does it through
  the macOS Accessibility API, by control name, with no mouse or screen coordinates.

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

1. Copy this folder to `~/.claude/skills/protools`.
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
template <group>/<name>".

## Status: what is proven and what is not

Proven on real sessions:
- Every `ptctl.py` verb, on Pro Tools 2025.6.1.
- The prep pipeline end to end (create from template, raw import, spot-by-id
  foldering with EDL verification, color, markers) on a 2026 build, including a
  64-stem drop with no input from the engineer.
- `route_folders.py`: 51 of 51 tracks routed on a test session.
- `stemid.py`: 45 of 51 folders and 25 of 25 L/R pairs on a 76-file test drop.
- Offline bounces with `export_mix`.

Known limits (PTSL has no command for these):
- Tempo and meter, pan, faders, plug-in insert or bypass, track order, move into
  folder, combine two monos to stereo.
- Setting outputs needs the Private API (an Avid-issued key), so this skill uses
  Accessibility instead. Accessibility controls only exist for tracks Pro Tools has
  drawn on screen.
- `import_audio` in py-ptsl is broken; the scripts call the raw command.
- Tempo detection is an estimate. Read the candidate table and confirm by ear.

Verified for this release (on a machine without Pro Tools):
- `python3 -m py_compile` on every script.
- `--help` on every CLI.
- Offline smoke tests on synthetic audio: `prep_session.py channels` and `grid`,
  `stemqc.py levels` and `arrangement`, `analyze.py`, `interleave.py`,
  `envelopes.py`, `ref_compare.py`.
- The PTSL and Accessibility scripts were not re-run against Pro Tools after the
  clean-up for publication (paths and names changed, logic did not).

## No warranty

These scripts are examples to adapt. They come with no warranty. Save your
session before a prep, and work on a copy when in doubt. This project is not
affiliated with or endorsed by Avid. Pro Tools is a trademark of Avid Technology.

More Accessibility rules (save panels, hung jobs, Logic) are in `../macos-accessibility/README.md`.

## Built on tour

Built by Michael Lewis, touring engineer and co-founder of
[Truck Packer](https://truckpacker.com), the truck-pack planning app for touring
and production crews.
