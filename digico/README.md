# DiGiCo sessions

Read, build and edit DiGiCo SD and Quantum session files (`.ses`) by bytes, and translate an Allen & Heath dLive
show to a DiGiCo session. This folder is a Claude Code skill (`SKILL.md`) and a Python library you can run yourself.

## What it does

- **Build** a new session from an input list (CSV, XLSX, XLS, DOCX, PDF, HTML or pasted text) or a plain
  description: channel count, order, stereo pairs, 8-character names, per-instrument starting processing, buses,
  SD FX units with their feeds and returns, IEM and wedge mixes, sends, input patch and preamps.
- **Edit** any session: processing, names, moves, stereo, patch, sends, FX and buses, from edit ops or plain-English
  commands ("hpf vox 120, gate the toms"). An op that cannot be made is refused with a sentence.
- **Check** a session: what console and software it loads on, channels, patch, mixes, FX, structural problems.
- **Translate** a dLive show: names, trim, polarity, delay, HPF/LPF, 4-band EQ, gate, compressor, stereo pans,
  Mustard comps, SD reverbs, Chilli 6 and dynamic EQ, with a report of every approximation.

## Requirements

- Python 3.9 or later. Standard library only.
- The DiGiCo offline editor for each console and software build you target (free from DiGiCo, Windows).
- Baselines you save from that editor: `references/baselines.md`. This folder ships none.
- For dLive translation: the `dlive/` folder of this repo next to this one (it reads the show with
  `../dlive/scripts/dlive_proc.py` and `dlive_fx.py`).

## Quick start

```
cd digico/scripts
mkdir -p baselines        # save q225_v2242.ses here from the Quantum 225 editor (references/baselines.md)
python3 -m sessionmaker.consoles
python3 -m sessionmaker.intake ../examples/input_list.csv
python3 -m sessionmaker.build ../examples/build_request.json out.ses
python3 -m sessionmaker.inspect out.ses
python3 -m sessionmaker.commands out.ses "hpf vox 120, gate the toms"
python3 dlive2digico.py "My Show.tar.gz" my_baseline.ses translated.ses --channels 1-48
```

Open every result in the offline editor, check it, and **Files > Save As**. Load only the editor's save on a
console, and do the first load at prep or rehearsal.

## Layout

- `scripts/ses.py`: structural reader/writer (sections, module records, slots by (module, param, band), names).
- `scripts/dlive2digico.py`: the dLive translator.
- `scripts/sessionmaker/`: the build/edit library. `data/templates.json` holds the per-instrument starting points.
- `scripts/keys_from_offsets.json`: slot keys for the early mapped fields.
- `references/`: `FORMAT.md` and `CHANNEL_MODEL.md` (the format), `baselines.md`, `filters-and-thresholds.md`,
  `sessionmaker.md`.
- `examples/`: a synthetic input list, a build request and a translator config (made-up band).

## Status

Proven:
- In-place patches (names, HPF, fader, mute) loaded and displayed correctly on a real Quantum 2.
- Generated Quantum 225 V2242 sessions (relayouts, FX, sends, buses, patch, dLive translations) loaded in the
  V2242 offline editor and re-saved unchanged. FX units were also booted and re-saved on 18 console/build pairs.
- `ses.py` parses sessions back to V1455 (Q2, Q3, Q5, SD8, SD9, SD12 tested).

Verified for this release:
- Every `.py` file compiles (`python3 -m py_compile`). Every CLI prints its usage with `--help`.
- On a Quantum 225 V2242 editor default: `build` with the example request (17 channels, 3 stereo, 3 IEM + 1 wedge
  mix, 2 FX) passed all checks; `validate`, `inspect`, `fx`, `ses.py`, `commands` and `edit` ran on the result.
  `listparse` and `intake` read the example list. `dlive2digico.py` translated a dLive show built from the A&H
  factory FoH show into that default.
- None of these release outputs were loaded on a console.

Not covered:
- Names longer than 8 characters.
- Structural edits on a session with snapshots (refused).
- Consoles and builds other than the Quantum 225 V2242 are built with the same writers from their own editor
  defaults but have not been loaded in their editors by this release.
- The dLive translator does not write preamp gain, 48V, the input patch, IEM sends, groups, control groups or
  insert FX.
- The original tool's optional external classifier for unclear channel names is not included. The rules handle
  every list; see `references/sessionmaker.md` to plug in your own.

Not affiliated with DiGiCo or Allen & Heath. DiGiCo, Quantum, Mustard and Spice Rack are trademarks of DiGiCo.
dLive is a trademark of Allen & Heath. The format was decoded by hand and is not documented by the manufacturer.
Check every session before it goes near a console. No warranty.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.
