# yamaha: Yamaha CL, QL and DM7 show files

A Claude Code skill and a Python script for Yamaha console show files. It reads CL and QL (`.CLF`) and DM7, DM5,
DM3 and TF (`.dm7f`, `.dmxf`, `.dm3f`, `.tff`) without the console or the Yamaha editors. It writes only the edits
that a black-box editor test proved: names, colours, faders, channel on, HPF, input patch, head amp gain and 48V,
DCA assigns and bus names.

To use it in the browser instead, go to [idontownapc.com/yamaha](https://idontownapc.com/yamaha). The page runs on
this code, with a console view.

## Models

- [CL](cl/): CL1, CL3, CL5
- [QL](ql/): QL1, QL5
- [DM7](dm7/): DM7, DM7 Compact
- [DM5](dm5/): DM5, DM5 Compact
- [DM3](dm3/): DM3, DM3 Standard
- [TF](tf/): TF1, TF3, TF5, TF-RACK
- [RIVAGE PM](rivage-pm/): PM3, PM5, PM7, PM10

## What it does

- Reads a show and prints it the way the console shows it: every input with name, colour, icon, patch, head amp,
  HPF, fader, ON key and DCAs, then the mixes, matrices, DCAs, mute groups and stored scenes. `--json` prints the
  whole model.
- Checks the container, every checksum or schema, and every entry: the record tree and every checksum (CL, QL), or
  every record, schema and zlib entry (DM7, DM5, DM3, TF).
- CL (scene format 5, 6 or 7) and QL (format 6 or 7): rename, colour, icon, fader, ON key, HPF, patch (Dante, OMNI or
  INPUT, playback, slots), head amp gain and 48V on the console's own inputs, DCA assigns, and mix, matrix, DCA and
  mute group names. On a CL format 7 file, `--all-scenes` also sends names, colours and patch to every stored scene.
- DM7 files from firmware V2.01: rename (8 characters), colour, fader, ON key, HPF, patch (OMNI 1 to 32, DANTE 1 to
  144) and head amp gain and 48V on the OMNI inputs.
- Refuses everything else with one sentence: user key files, scene-only and library files, RIVAGE PM files, and every
  write that no editor test covered (section 6 of `references/FORMAT.md` lists them).

Every write keeps the file type, the firmware version or scene format, and every byte it does not change. If any
change in a command is refused, nothing is written.

## What is in the folder

- `SKILL.md`: the skill. Claude Code loads it when you ask about a Yamaha show.
- `scripts/yamaha_tool.py`: `show`, `check`, `ports`, and one command per write (`rename`, `colour`, `icon`, `fader`,
  `on`, `hpf`, `patch`, `preamp`, `dca`, `busname`), plus `apply` for a JSON list of changes.
- `references/FORMAT.md`: both file generations, where each value lives, and the test that proved each fact.

## Requirements

- Python 3.8 or later. No other packages.
- The free Yamaha editor for your console (CL Editor, QL Editor or DM Editor), to open and re-save every written file.
- Your own show file. No show files ship with this folder.

## Quick start

```
cd yamaha/scripts
python3 yamaha_tool.py show "My Show.CLF" --console cl5
python3 yamaha_tool.py check "My Show.CLF"
python3 yamaha_tool.py rename "My Show.CLF" "V2.CLF" 1-3 "Kick In" "Kick Out" "Snare" --console cl5 --dry-run
python3 yamaha_tool.py rename "My Show.CLF" "V2.CLF" 1-3 "Kick In" "Kick Out" "Snare" --console cl5
python3 yamaha_tool.py patch "V2.CLF" "V3.CLF" 65 "OMNI 1" --console cl5
python3 yamaha_tool.py preamp "V3.CLF" "V4.CLF" 65 --gain 30 --48v on --console cl5
python3 yamaha_tool.py apply "My Show.dmxf" "My Show V2.dmxf" changes.json
```

A `.CLF` does not record which CL or QL model made it, so pass `--console` (`cl5`, `cl3`, `cl1`, `ql5`, `ql1`). Then
open the result in the Yamaha editor, check it, and save it from the editor. Load only the editor's save on a console.

To install as a skill, copy this folder to `~/.claude/skills/yamaha-showfile/`.

## Status

Proven, and how:

- Every fact the script uses was proven black box, and `references/FORMAT.md` names the test for each one. A value
  was set in the free Yamaha editor (by a click or Yamaha's documented CSV import) and the saved file was read, or a
  value was written into a file and the editor showed it after a load. The editors ran under Wine on Linux: CL Editor
  5.8.1, QL Editor 5.8.1 and DM Editor 2.0.1.
- Every write this script makes loaded in the editor with the values matching. CL: a new CL5 session (format 7) and
  two real shows (formats 5 and 6); the editor's re-save and CSV export matched 147 items with 0 mismatches each. QL:
  a new QL1 session and a real format 6 show, 99 and 131 items, 0 mismatches. CL stored scenes: a recall showed the
  written names, colours and patch. DM7 V2.01: the bay, the channel bar and the Channel List showed every value, and
  the re-save matched 208 items with 0 mismatches.
- Those editor tests ran on the engine behind idontownapc.com/yamaha. This script is a port of that engine. For the
  same changes it writes byte-identical files, and it reads every value the same.

Verified for this release:

- `python3 -m py_compile`, `--help`, and the Python 3.8 grammar.
- Reads compared with the site's engine on 8 test files built from a sample input list (CL5, QL1, a CL5 session
  with stored scenes, DM7), on 8 files saved by the Yamaha editors and converter (CL5, QL, DM7, DM3, TF5, RIVAGE PM), and on 25
  real show files that are not included: every value the same (over 70,000 values in 49 reads), and the same 16 files
  refused by both (user keys, scene-only files, RIVAGE PM).
- Writes compared with the site's engine: byte-identical files for the same changes on the test files and on 9 writes
  to real CL and QL shows of formats 5 and 6. Both engines refused the same writes to QL format 5 and DM7 firmware 1.x
  files.
- Every command on the test files: `show`, `check`, `ports`, each write command, `apply` and `--dry-run`. 32 refusal
  cases each gave one sentence and wrote nothing (overwriting the input, another file type, long or non-ASCII names,
  rack outputs, inputs the model does not have, head amps on Dante channels, out-of-range values, ST IN DCA assigns,
  stored-scene writes of other values, DM7 DCA, bus name, icon and stored-scene writes, TF, DM3, DM7 Compact and
  RIVAGE PM files, a file that is not a Yamaha show). `check` caught a flipped name byte (checksum) and a damaged DM7
  file.

Not proven:

- That a console loads a file written here. Only the editors have loaded these files. Load the editor's save, at prep.
- Sends, EQ, dynamics, delay, inserts, the output patch, and mix and matrix faders: not read.
- DM7 firmware 1.x, other firmware than V2.01, DM7 Compact, DM5, DM5 Compact, DM3 and TF: read only. RIVAGE PM: not
  read.

## Safety

Yamaha does not document these formats. Never load a written file straight into a console. Open it in the Yamaha
editor, check it, save it from the editor, and load only that save. Do the first load at prep or rehearsal, never at
the show, and keep a known-good show on a USB stick.

Every fact here was proven by a black-box test named in `references/FORMAT.md`: show files the editors saved, and
what the editors showed when they loaded a written file. No table, text or file from a Yamaha program, descriptor,
template, preset, font or screenshot is copied here, and no Yamaha file ships with this folder.

This tool is not affiliated with or endorsed by Yamaha. Yamaha and the console names are trademarks of Yamaha
Corporation. No warranty.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack planning app for touring and production crews.
