# dLive show files

Read and write Allen & Heath dLive show files (`.tar.gz`, firmware 2.x, show Version 14) without dLive Director
open. This folder is a Claude Code skill (`SKILL.md`) and a set of plain Python scripts you can run yourself.

To use it in the browser instead, go to [idontownapc.com/dlive](https://idontownapc.com/dlive): the same code, with a console view.

## What it does

- Names, colours, stereo pairs, group, DCA and main assigns from a plan.
- The full patch: input sources A-D, every output socket, insert returns, FX rack inputs, virtual soundcheck.
- Mixer config changes (bus counts) the way Director does them, including scene safes.
- Mix masters and sends: IEM mixes, wedges, FX sends, matrix sends.
- Input processing: read it in Hz, dB and ms, reset it to Director's defaults, or copy it from another show by
  instrument.
- FX rack, UltraFX and Dyn8 units: read their programs, parameters, sends and returns.
- MixRack preamps (gain, pad, 48V), SoftKeys, multifunction macros, the surface fader layout.
- Stored scenes: list them, or drop them and keep only the live state.
- A validator (`dlive_lint.py`) to run before a show goes near Director or a console.

## Requirements

- Python 3.9 or later (a current patch release; tested on 3.12). Standard library only.
- dLive Director in the version that matches the console firmware, to open and re-save every result.
- Your own show files. This folder ships none.

## Quick start

```
cd allen-heath/dlive/scripts
python3 dlive_lint.py "My Show.tar.gz"                       # check a show
python3 dlive_proc.py table "My Show.tar.gz" --ch 1-24       # processing, one line per channel
python3 dlive_patch.py dump "My Show.tar.gz"                 # the patch
python3 build_show.py ../examples/build_plan.json "Template.tar.gz" "New V1.tar.gz"
python3 dlive_mix.py reconfigure "New V1.tar.gz" "New V2.tar.gz" sAux=10
python3 dlive_patch.py apply "New V2.tar.gz" ../examples/patch.json "New V3.tar.gz"
python3 dlive_mix.py apply "New V3.tar.gz" ../examples/mix_plan.json "New V4.tar.gz"
python3 dlive_scenes.py drop "New V4.tar.gz" "New V5.tar.gz"
python3 dlive_lint.py "New V5.tar.gz"
```

Then open the result in Director offline, check it, and save it from Director. Load only Director's save on a
console. `references/console-safety.md` has the full risk write-up and the console recovery steps.

The examples in `examples/` are synthetic (a made-up band). Each script's docstring has its exact JSON shape.

## Layout

- `scripts/`: the tools. `dlive_mix.py`, `dlive_patch.py` and `dlive_scene.py` are also the libraries the others
  import. `fx_tables.json` holds Director's FX parameter tables; `input_defaults.json` and `section_lengths.json`
  hold format constants.
- `references/`: format notes for every section the tools touch, how the format was decoded, a safety write-up,
  and how to build a show from an input list (`show-maker.md`).
- `examples/`: synthetic plans.

## Status

Proven:
- Every structure the writers produce was checked byte for byte against Director V2.12's own output (mixer config
  change, IEM sends, patch, scene safes, SoftKeys, layout, no-op round trips).
- Script-written shows have loaded in Director and been edited there.
- `dlive_lint.py` passes Director-saved shows with 0 errors and caught 18 of 18 deliberately corrupted files.

Verified for this release:
- Every `.py` file compiles (`python3 -m py_compile`).
- The chain in "Quick start" ran on a copy of the A&H factory FoH show (Director 2.12) with the example plans:
  build, reconfigure, patch, mixes, preamps, drop scenes, then `dlive_lint.py` with 0 errors. `dlive_proc.py`,
  `dlive_fx.py`, `dlive_ears.py`, `dlive_patch.py dump` and `dlive_scenes.py dump` read the result.

Not covered:
- Show formats before Version 14 (firmware 1.x). The tools refuse them.
- Writing main modes other than LR (the bus count reads them).
- Some SoftKey types, some compressor-model fields (Amp76, Distressor), PEQ types 5-9. See `references/`.
- Older-format stored scenes: the patch tool skips them and says so. Drop them (`dlive_scenes.py`) or let
  Director convert them.

Not affiliated with Allen & Heath. dLive is a trademark of Allen & Heath. The file format was decoded by hand
and is not documented by the manufacturer. Check every show before it goes near a console. No warranty. Part of
the dLive field map credits github.com/jaylenjinx/dlive-show-editor.

## What we don't know

markcarlberg's notes on show Versions 11-14, settings files, talkback groups and actions are in
`references/format-versions.md`, and the Dyn8 word laws in `references/format-fx.md`. Where his readings disagree
with a save-proven fact here, the repo fact stands until a save settles it:

- Preamp gain: a contributor reading says the MixRack preamp block holds a u16 gain / 256 in a 5-byte block; `references/format-processing.md` says one whole-dB byte (`01 | gain | pad | 48V`, default 27 dB). `references/format-processing-surface.md` reads the same bytes as s16 dB x 256. A save with a fractional gain would settle it.
- Compressor model 10: a contributor reading calls it CompStortion; `references/format-processing.md` calls it the Distressor, with byte 58 as the ratio switch. The Avantis notes list the same naming question (`../avantis/README.md`).
- Mix Mixer group rows: a contributor reading says the last byte after the group-to-group bytes is the group's Grp To Grp send point (`03` Post Delay, `02` Post Comp); `references/format-mixconfig.md` says it is the main assign, default 3. Needs a save that settles it.
- Version 11 gate (25 bytes) and the V11 and V13 compressor fields past byte 18.
- `Channel Mapper`: the gap between the VSC banks and the Insert A table; output records 32-96 and those past DX 1/2; source types `07`-`0B` as input sources.
- Whether the output patch ends at record 639: Dyn8 inputs at 584 + u would run past it for high unit numbers.
- Preamp labels `StageBox TSnake Analogue Input, Number 01-64` (read as DX 1/2 1-32, DX 3/4 33-64) and `StageBox Port B TSnake Analogue Input, Slot 1-3` are unconfirmed; an I/O Port with a DX Link card is read as keeping its stage box's preamps in `StageBox Port B Analogue Input, Slot n, Number NN`, unconfirmed.
- `PAFLSettings.dat` [87..90] Mains To PAFL, placed by value only.
- An FX send's kind in talkback groups; the stereo aux, main and matrix insert send codes beyond what files show; mute groups' 4-byte record contents beyond the engaged flag.
- Dyn8 dynamic EQ cut/boost step to ratio values.
- Whether the MixRack model is in any file (`SouthConfig*` is the candidate).

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-10-30, Director 2.12 and console saves, 42 real shows: 39 file names fit 16 characters, 13 sit at exactly 16, and some are cut mid-word at 16. The 3 over 16 are 2 tars from a Mac user and 1 console tar, and none of the 42 stores the name inside, so `dlive_lint.py` warns and does not fail.

2026-10-30, Director V1.9x to V2.11: version 11-14 field notes contributed by markcarlberg (pull request #2), in `references/format-versions.md`.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.

The scene safes map is by [Stefan "Hedde" Hettenbach](https://www.instagram.com/stefan_hettenbach/) (Clap! Live Solutions, Mannheim). Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).

Cross-desk format notes in this folder are by [markcarlberg](https://github.com/markcarlberg). Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
