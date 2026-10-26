---
name: protools
description: Control and prep a running Pro Tools session on this Mac through the Pro Tools Scripting SDK (PTSL) - transport, track state (mute, solo, record-enable, safes, input monitor, inactive, hidden, freeze), track selection and creation, markers and memory locations, timeline selection, session info, save, import, and bounces - plus a stems-to-session prep pipeline (create from your template, import, fix channel formats, fold into routing folders, route each track to its folder bus through the Accessibility API, color by group, detect tempo and key, place verse/chorus/bridge markers on the click grid), stem QC (dead stems, levels, arrangement map, identify unnamed stems by listening), a first premix (clip-gain staging, headroom trim, role-based balance, top-down folder faders), and the way out: file layout, bounce naming and versioning, and delivery to Samply or a mastering FINALS folder. Trigger on "Pro Tools", "PTSL", "mute the drums", "solo the lead vocal", "play from the chorus", "drop a marker", "list my tracks", "bounce a mix", "prep this song", "set up a session from these stems", "route the stems to their groups", "find the tempo/key", "auto-mark the sections", "what are these stems", "premix this", "bounce V2", "deliver the mix". NOT for console show files.
---

# Pro Tools control and session prep (PTSL)

Pro Tools runs a local gRPC scripting server (PTSL) on `127.0.0.1:31416`. This skill
drives it with `py-ptsl` from short scripts. Everything runs on the Mac that runs
Pro Tools.

Verified on Pro Tools 2025.6.1 (PTSL 2025). The prep pipeline and the Accessibility
routing were also run on a 2026 build.

## Setup (once)

From this skill folder: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
Use `.venv/bin/python` for every script (below, `PY=.venv/bin/python`). The system
python does not have `py-ptsl`. Routing and dialog handling also need Accessibility
permission for the terminal app (README.md).

## Before doing anything

1. **Launch Pro Tools yourself:** `$PY scripts/ptctl.py launch`. It opens Pro Tools if
   needed and waits for the scripting server. It returns `already-running`,
   `launched` or `timeout`. Do not ask the engineer to open Pro Tools.
2. **Trust `launch` and `status`, not `pgrep`.** A crashed Pro Tools leaves a
   `crashpad_handler` process that matches "Pro Tools". `launch` checks the socket.
3. **Run `$PY scripts/ptctl.py status`** to see which session is open before you
   change anything. If it hangs after a fresh launch, the engineer must accept the
   "Allow ClaudeCode" connection dialog in Pro Tools.

## Fast path: `scripts/ptctl.py` verbs (all output is JSON)

| Command | Does |
|---|---|
| `status` | session name/path, sample rate, bit depth, TC rate, transport, track count |
| `tracks [--filter NAME]` | tracks with index, type, format and active flags |
| `play` / `stop` / `transport` | start, stop (state-aware) or read the transport |
| `mute "BASS" "KEYS" on\|off` | mute or unmute tracks |
| `solo "Lead Vox" on` | same shape for `recenable`, `recordsafe`, `solosafe`, `inputmonitor`, `inactive`, `hidden`, `online`, `frozen` |
| `select "Lead Vox" "BGV"` | select tracks by name |
| `memlocs` / `locate 2` | list memory locations / recall #2 |
| `marker "Chorus" [--time T] [--number N]` | create a marker |
| `selection` / `setsel "0:00" "0:30"` | read / set the timeline selection |
| `save` | save the session |
| `caps [--save-baseline]` | probe version-gated commands; diff the command list against the saved baseline |
| `exec "<python>"` | run code with the engine bound as `e` (escape hatch) |

Track names match exactly as Pro Tools shows them; run `tracks` and quote the
name. The last argument of a flag verb may be `on`/`off` (default `on`).
`tracks` does not show the parent folder. To see nesting:
`$PY scripts/ptctl.py exec "import json;print(json.dumps([(t.name,t.parent_folder_name) for t in e.track_list()]))"`.

## Full API

The `Engine` has about 110 methods. One-liner:
`$PY scripts/ptctl.py exec "e.create_new_tracks(number_of_tracks=2, track_name='Synth')"`.
For multi-step work, write a short script:
```python
import sys; sys.path.insert(0, "scripts")
from ptctl import engine
with engine() as e:
    e.set_track_solo_state(["Lead Vox"], True)
    e.set_timeline_selection(in_time="0:00", out_time="0:30")
```
Read `references/PTSL_REFERENCE.md` before you use methods beyond the verbs. It has
the method catalog, the `Track` object, enum meanings, the bounce recipe, the raw
import command (the py-ptsl `import_audio` wrapper is broken), clip spotting by id,
and the list of things PTSL cannot do.

## Session prep (stems to a mix-ready session)

Full playbook: `references/session-prep.md`. Read it before a prep. In short:

1. Read the drop: `stemqc.py levels`, `prep_session.py channels` (whole file), and
   `stemid.py` for unnamed stems. Count the files.
2. Create from the engineer's template with `prep_session.create_from_template`
   (into a `.nosync` folder if Documents syncs to iCloud). It can take 10 to 20
   minutes and look hung; watch Pro Tools' CPU, not PTSL.
3. Import (`import_stems`), fix channel formats (dual-mono to mono, stereo kept, hard-panned L/R pairs to one stereo track).
4. Fold into the template's folders with `CId_SpotClipsByID`; verify every track with
   the EDL text export.
5. **Route:** `$PY scripts/route_folders.py --dry`, then `route_folders.py`. It must
   print `ROUTED`. Script-created tracks output to the main bus, not their folder.
   Fallbacks: `references/gui-routing.md`, then `route_groups.py`;
   `verify_routing.py` proves routing by bouncing each bus.
6. Color by group, detect tempo (`prep_session.py grid` with a dense percussive
   source; read the candidate table), place section markers (`ptprep.py markers
   --lyrics`, `--structure`, or `stemqc.py arrangement` for instrumentals). Dry-run
   first. Then set the tempo with `$PY scripts/set_tempo.py <BPM>`: it types the BPM
   into the Tempo ruler's Tempo Change dialog at bar 1 through Accessibility and reads
   it back. Absolute markers and sample-based audio do not move.
   Then `clipgain_normalize.py` (every stem's average at -18 dBFS by clip gain).
   Optional per song: `hp_metricab.py` (headphone send off the master bus, Metric AB
   reference preset from `metricab_ref.py`, aligned with `ref_align.py`).
7. Save and report, including what the engineer must do by hand (meter, plug-in
   bypass, track order, VCA membership).

Run `pt_dialog_watch.py` (or `demo_guard.py`) in its own terminal for any unattended
run, and stop it before anyone works in Pro Tools.

## Premix (only when asked)

`clipgain_normalize.py`, then `premix.py trim`, `verify --ref`, `plan --ref`, `topdown`,
`apply` and `check`. Steps and numbers: `references/session-prep.md`, "Premix". Every
script that types into Pro Tools refuses to run if the Mac had input in the last 2
minutes and stops if someone touches it mid-run.

## Bounce, name, version, deliver

Full convention: `references/session-prep.md`, "Bounce, name, version, deliver".

- One name everywhere (bounce `base_name`, `Bounced Files/`, Samply):
  `<Song>_<Initials>_V<n>_PtMst.wav`. Title Case song, V1 for a first mix, V2 and up for
  new mixes, `PtMst` (post master bus) or `PrMst` (pre master bus). List
  `Bounced Files/` for the next number. Never overwrite a delivered version.
- Default bounce: `PtMst`, 24-bit / 48 kHz stereo WAV, offline, over the song's
  selection memory location. Recipe in `references/PTSL_REFERENCE.md`.
- Deliver the `_PtMst` to the client on Samply with the `samply` skill in this repo
  (`../samply/`): a new mix of an existing song goes in as a new version of its stack.
- Mastering gets a `<Project> FINALS` folder with the latest `_PrMst` and `_PtMst` of
  every song, zipped.

Other tools: `ptprep.py` (marker CLI on an open session; `clear-prep` removes only
its own markers), `analyze.py` (tempo/key/sections of one file), `interleave.py`
(two monos to one stereo WAV), `envelopes.py` (per-second activity of long
captures), `ref_compare.py` (stem sum against a reference mix), `ptax.py` (GUI
through Accessibility: `outputs`, `route <bus> <track>...`, `windows`, `click`,
`menu`), `demo_guard.py` and `pt_dialog_watch.py` (log and answer routine dialogs),
`place_onto.py` (stems onto a template's own tracks from a JSON map), `tx_regions.py`
(Whisper on chosen regions of a long capture), `declick.py` (repair a pop in a bounced
file), `merge_pairs.py`, `pan_to_mono.py` and `resample_session.py` (fix a session
that is already built).

## Safety

- **Free to do and undo:** mute, solo, select, transport, markers.
- **Confirm first:** anything that writes to disk or is hard to undo:
  `save_session`, `save_session_as`, `export_mix`, `export_clips_as_files`,
  `close_session`, `create_session*`, clearing memory locations, bulk clip edits,
  `CId_DeleteTracks` (it deletes every track with that name).
- **Bounces:** follow the naming convention above. Ask for format, source bus and
  offline/realtime only when there is no standing convention. `export_mix` bounces
  the timeline selection.
- **Never type into Pro Tools while someone works in it.** `clipgain_normalize.py`,
  `pan_to_mono.py`, `premix.py apply` and the template helpers send keystrokes, and a
  keystroke lands on whatever is selected.
- **Do not start playback** unless asked. It makes sound.
- **Never kill a hung PTSL client.** It can leave Pro Tools refusing every new
  connection until it restarts. Run long calls with output to a log and read the log.
- The connection is loopback only. The company/app names shown in the Pro Tools
  dialog come from `PTSL_COMPANY` / `PTSL_APP` (defaults `ShowFileSkills` /
  `ClaudeCode`); keep them stable so the grant persists.
