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
cd dlive/scripts
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

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.
