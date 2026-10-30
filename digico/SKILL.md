---
name: digico-session
description: Read, build and edit DiGiCo SD and Quantum sessions (.ses) by bytes, on a baseline saved by the DiGiCo offline editor - build a new session from an input list or a plain description (channel count, order, stereo, names, per-instrument starting processing, buses, SD FX units, IEM and wedge mixes, sends, input patch and preamps), edit any session (processing, names, moves, stereo, patch, sends, FX, buses) from edit ops or plain-English commands, check a session (what console and software it loads on, structure, problems). Built for agents creating session files from the command line. Trigger on "DiGiCo", ".ses", "Quantum", "SD12", "SD9", "Q225", "Q338", "session file", "build a DiGiCo session from this input list", "check this session", "Mustard", "Spice Rack", or any request to make or change a DiGiCo show file.
---

# DiGiCo sessions

DiGiCo sessions are always patched in place on a **baseline**: a session the DiGiCo offline editor saved for the
console and software build you will load it on. The tools never write a session from nothing. The console rebuilds
its caches on load.

## Safety rules

1. Write new files only. Never overwrite the baseline or the engineer's session.
2. Open every generated session in the DiGiCo offline editor for that console and build, check it, then
   **Files > Save As** a new file. Only the editor's save goes to a console.
3. First load on a real console happens at prep or rehearsal, never at the show.
4. Read the report next to the output (`<out>.md`). Every approximation and warning is listed.
5. A session saved by a newer build does not load on an older console. Build on the console's own build.

## Set up once

- Baselines: `references/baselines.md`. Default sessions go in `scripts/baselines/<key>_v<build>.ses`
  (or the folder `SM_BASELINES` names).
- Python 3.9+, standard library only. Run everything from `scripts/`.

## Tools

| Command (from `scripts/`) | Does |
|---|---|
| `python3 ses.py <file.ses>` | Summary: console, build, inputs, stereo, auxes, groups. `ses.py` is also the reader/writer library: slots by (module, param, band), renames every name copy in place, strip views. |
| `python3 -m sessionmaker.inspect <file.ses>` | Checker: what it loads on, channels, patch, mixes, FX, structure problems. `--json` for the full model. |
| `python3 -m sessionmaker.consoles` | Consoles and builds the baselines folder supports. |
| `python3 -m sessionmaker.listparse <list> --table` | Read an input list (CSV, XLSX, XLS, DOCX, PDF, HTML, text). |
| `python3 -m sessionmaker.intake <list or "description">` | Channel plan with instrument categories. |
| `python3 -m sessionmaker.build <req.json> <out.ses>` | New session from a request. Writes `<out>.md` (report) and `<out>.json` (read-back, checks). |
| `python3 -m sessionmaker.edit <in.ses> '<ops json>' <out.ses>` | Apply edit ops. Refused ops say why and leave the file as it was. |
| `python3 -m sessionmaker.commands <in.ses> "<text>"` | Turn plain English into edit ops (prints them; apply with `edit`). |
| `python3 -m sessionmaker.validate <file.ses>` | Structural invariants. Run after every write. |

The request format is in the `build.py` docstring, the op format in `edit.py`. Overview: `references/sessionmaker.md`.

## New session from an input list (the recipe)

1. `intake` the list. Check every category and stereo pair against the list; fix names to 8 characters.
2. Write the request: console key, build, channels, `processing: templates` (or `none`), and the option blocks you
   need (`mixes`, `fx`, `sends`, `buses`, `patch`). See `examples/build_request.json`.
3. `build`. Read the report and the warnings. `validate` and `inspect` the result.
4. Changes: `commands` to draft ops, read them, then `edit`. Validate again.
5. Open in the editor, check, Save As.

## Levels and filters (read before writing values by hand)

- Thresholds are dBFS and stop at 0.
- The strip shows the -3 dB cutoff. Stored HPF = shown / 1.25, stored LPF = shown / 0.8. EQ is stored as shown.
- Times are stored in seconds.
Details: `references/filters-and-thresholds.md`.

## Format notes

`references/FORMAT.md` (container, section table, module records, slot keys, stereo, Mustard, Spice Rack, FX units,
sends, buses, patch, surface banks), `references/CHANNEL_MODEL.md` (the input channel signal flow and what is
mapped), `references/engine-findings.md` (editor-proven limits, load rules and the guards these scripts still lack),
`references/scope-and-recall.md` (snapshot scope, Global Scope, safes, and what a recall changes and leaves).
Key by (module, param, band), never by offset: the channel stride changes with the session structure.
