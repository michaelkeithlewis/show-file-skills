---
name: yamaha-showfile
description: Read Yamaha console show files without the console or the Yamaha editors - CL and QL (.CLF), DM7 and DM5 (.dm7f, .dmxf), DM3 (.dm3f) and TF (.tff) - and print every input (name, colour, icon, patch, head amp, HPF, fader, ON key, DCAs), the buses, DCAs, mute groups and stored scenes. Write only the edits a black-box editor test proved - CL and QL names, colours, icons, faders, ON keys, HPF, input patch, head amp gain and 48V, DCA assigns and mix/matrix/DCA/mute group names; DM7 firmware V2.01 names, colours, faders, ON keys, HPF, patch and head amps. Trigger on "Yamaha", "CL5", "CL3", "CL1", "QL5", "QL1", "DM7", "DM5", "DM3", "TF5", ".CLF", ".dm7f", ".dmxf", "CL Editor", "DM Editor", "rename the channels in this Yamaha show", "patch the Dante inputs on the CL", "what is in this CLF". NOT for RIVAGE PM files, user key files (.CLU, .dm7u), sends, EQ, dynamics, or live console control.
---

# Yamaha show files

Two file generations cover the current Yamaha consoles. CL and QL save a `.CLF`: a big-endian record tree with a
word-sum checksum on every block. DM7, DM5, DM3, TF and RIVAGE PM save a `#YAMAHA MBDF` file: zlib entries, and every
section carries its own schema, so values are read and written by name. Format notes and the test behind every fact:
`references/FORMAT.md`. Requires Python 3.8 or later and nothing else.

## Safety rules

1. Write a new file with the same extension. The tool refuses to overwrite its input or change the file type.
2. Run `--dry-run` first, then the real command, then `show` and `check` on the output.
3. The tool writes only what an editor test proved, and refuses the rest with one sentence. If any change in a command
   is refused, nothing is written. Never work around a refusal by hand-editing bytes.
4. Every written file goes to the free Yamaha editor first (CL Editor, QL Editor or DM Editor). Open it, check it, save
   it there. Only the editor's save goes to a console, at prep, never first at the show.
5. User key files (`.CLU`, `.dm7u`) hold passwords. Never open, print or edit them.
6. Firmware: the tool never changes the firmware version or the scene format. DM7 files from firmware 1.x, and every
   firmware other than V2.01, are read only.

## Commands

```
python3 scripts/yamaha_tool.py show  SHOW [--console cl5] [--json]
python3 scripts/yamaha_tool.py check SHOW
python3 scripts/yamaha_tool.py ports SHOW [--console ql1]
python3 scripts/yamaha_tool.py rename  IN OUT CHANNELS NAME [NAME ...]
python3 scripts/yamaha_tool.py colour  IN OUT CHANNELS COLOUR
python3 scripts/yamaha_tool.py icon    IN OUT CHANNELS ICON                   # CL and QL
python3 scripts/yamaha_tool.py fader   IN OUT CHANNELS DB                     # or: off
python3 scripts/yamaha_tool.py on      IN OUT CHANNELS on|off
python3 scripts/yamaha_tool.py hpf     IN OUT CHANNELS [--on|--off] [--freq HZ]
python3 scripts/yamaha_tool.py patch   IN OUT CHANNELS SOURCE                 # "DANTE 3", "OMNI 2", "INPUT 12", none
python3 scripts/yamaha_tool.py preamp  IN OUT CHANNELS [--gain DB] [--48v on|off]
python3 scripts/yamaha_tool.py dca     IN OUT CHANNELS DCA [--mode add|remove|only]   # CL and QL
python3 scripts/yamaha_tool.py busname IN OUT BUS NAME                        # mix3, matrix1, dca2, mute1 (CL and QL)
python3 scripts/yamaha_tool.py apply   IN OUT OPS.json
```

CHANNELS: `3`, `1-8`, `1,3,5-8`, `st1l` or `st1r` (CL and QL ST IN), or `all`. Every write takes `--dry-run`,
`--console` and `--all-scenes`. The `OPS.json` shape is at the top of `yamaha_tool.py`.

## What each console takes

| Console, file | Writes |
| --- | --- |
| CL, scene format 5, 6, 7 | rename, colour, icon, fader, on, hpf, patch, preamp (OMNI 1 to 8), dca (mono channels), busname |
| QL, scene format 6, 7 | the same, preamp on INPUT 1 to 32 (QL1: 16) |
| CL, scene format 7, `--all-scenes` | rename, colour and patch also go to every stored scene |
| DM7, firmware V2.01 | rename (8 characters), colour, fader, on, hpf, patch (none, OMNI 1 to 32, DANTE 1 to 144), preamp (OMNI) |
| DM7 1.x or other firmware, DM7 Compact, DM5, DM5 Compact, DM3, TF | read only |
| RIVAGE PM, user keys, scene-only and library files | refused |

`show` prints "Writes open for this file" for the file in hand. Trust that line over this table.

## Recipe: names and patch from an input list

1. `show SHOW --console <model>` and read the current names, patch and head amps.
2. Write an `OPS.json` with one `rename` (with `names` in channel order), `set` with `colour`, and `patch` per source.
   Head amp gain and 48V go only to channels patched to the console's own inputs (`preamp`).
3. `apply IN OUT OPS.json --dry-run`, read every line, then run it without `--dry-run`.
4. `show OUT` and compare with the list. `check OUT`.
5. If `show` says stored scenes hold their own names, colours or patch, a recall brings the old ones back. On a CL
   format 7 file, run the rename, colour and patch changes again with `--all-scenes`. Otherwise tell the engineer.
6. Hand over the file with the editor rule: open in the Yamaha editor, save there, load that save at prep.

## Gotchas

- A `.CLF` does not record CL or QL, or which model. Always pass `--console`. Without it the tool guesses from the
  comment and the patch, and says so.
- Names hold 8 characters, plain ASCII. A longer name is refused, never cut. Shorten it yourself.
- An ST IN pair: the strip shows the L slot's fader, ON key and HPF. Writing to `st1l` writes both sides, as the
  editor does. Names, colours and patch stay per side.
- A channel patched from Dante or a slot has its head amp on the stage box. `preamp` refuses it. Rio and other stage
  box head amps are not in this tool.
- A head amp change goes to the port the channel is patched to at that point of the command, after any repatch
  earlier in the same `apply`.
- Rack outputs (FX, PRFX, GEQ) show on read but are never written: the editor drops them when the rack is set up
  differently.
- A DM7 channel on another EQ type keeps its HPF elsewhere. `show` prints `-` for its HPF, and `hpf` refuses it.
- `show` marks a column with `?` when no editor test has checked that field on this console or firmware.
