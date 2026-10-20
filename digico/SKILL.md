---
name: digico-session
description: Read, build and edit DiGiCo SD and Quantum sessions (.ses) by bytes, on a baseline saved by the DiGiCo offline editor - build a new session from an input list or a plain description (channel count, order, stereo, names, per-instrument starting processing, buses, SD FX units, IEM and wedge mixes, sends, input patch and preamps), edit any session (processing, names, moves, stereo, patch, sends, FX, buses) from edit ops or plain-English commands, check a session (what console and software it loads on, structure, problems), and translate an Allen & Heath dLive show to a DiGiCo session (names, trim, polarity, delay, HPF/LPF, 4-band EQ, gate, compressor, stereo pans, Mustard comps, SD reverbs, Chilli 6, dynamic EQ) with a report of every approximation. Trigger on "DiGiCo", ".ses", "Quantum", "SD12", "SD9", "Q225", "Q338", "session file", "build a DiGiCo session from this input list", "translate my dLive show to DiGiCo", "check this session", "Mustard", "Spice Rack", or any request to make or change a DiGiCo show file. Needs the dlive-showfile skill next to it for dLive translation.
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
  (or the folder `SM_BASELINES` names). For dLive translation, make a layout baseline in Session Structure.
- Python 3.9+, standard library only. Run everything from `scripts/`.
- dLive translation reads the show with `../dlive/scripts/` (the dlive-showfile skill in this repo). Set
  `DLIVE_SCRIPTS` if it lives somewhere else.

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
| `python3 dlive2digico.py <show.tar.gz> <baseline.ses> <out.ses> [--channels 1-64] [--config fx.json]` | dLive show to DiGiCo session. |

The request format is in the `build.py` docstring, the op format in `edit.py`. Overview: `references/sessionmaker.md`.

## New session from an input list (the recipe)

1. `intake` the list. Check every category and stereo pair against the list; fix names to 8 characters.
2. Write the request: console key, build, channels, `processing: templates` (or `none`), and the option blocks you
   need (`mixes`, `fx`, `sends`, `buses`, `patch`). See `examples/build_request.json`.
3. `build`. Read the report and the warnings. `validate` and `inspect` the result.
4. Changes: `commands` to draft ops, read them, then `edit`. Validate again.
5. Open in the editor, check, Save As.

## dLive to DiGiCo

```
python3 dlive2digico.py <show.tar.gz> <baseline.ses> <out.ses> [--channels 1-64] [--config fx.json]
```

Written: name, digital trim, polarity, delay, HPF, LPF, 4-band PEQ, gate/ducker (Dyn2), compressor (Dyn1),
stereo-pair pans. Modelled dLive comps go to the Mustard comp up to the console's instance limit
(`--mustard-limit`, 24 on a Quantum 225, a stereo channel uses 2), ranked by channel name (vocals first),
and those strips open on the Mustard view. The rest get an approximation on the SD compressor.

With `--config` (see `examples/fx_config.json`) it also writes:
- the SD reverbs that replace the dLive UltraFX reverbs, with return faders and channel sends to the auxes,
- Chilli 6 settings in the Spice Rack slots from a vocal channel's dLive Dyn8 (`show:N` = the translated
  show's own Dyn8 unit N, `tpl:N` = unit N of the `template_show` in the config),
- a dynamic band on a free EQ band for each dynamic cut of a non-vocal Dyn8.

Not written: preamp gain, 48V, the input patch, IEM sends, groups, control groups, insert FX. The baseline's
layout is kept; make it match the show first.

## Levels and filters (read before writing values by hand)

- dLive thresholds sit on a nominal 0 dB scale (full scale +18). DiGiCo thresholds are dBFS. Subtract 18 dB.
- The strip shows the -3 dB cutoff. Stored HPF = shown / 1.25, stored LPF = shown / 0.8. EQ is stored as shown.
- Times are stored in seconds.
Details: `references/filters-and-thresholds.md`.

## Format notes

`references/FORMAT.md` (container, section table, module records, slot keys, stereo, Mustard, Spice Rack, FX units,
sends, buses, patch, surface banks), `references/CHANNEL_MODEL.md` (the input channel signal flow and what is
mapped). Key by (module, param, band), never by offset: the channel stride changes with the session structure.
