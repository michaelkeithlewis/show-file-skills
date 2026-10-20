---
name: venue-showfile
description: Read Avid VENUE / D-Show show files (.dsh, magic "Digidesign Storage - 1.0") without the console or the VENUE standalone software - system config (channel, bus, group, matrix, VCA counts, cards, sample rate) and every channel strip name - and rename strips safely in place (same length or shorter, file size unchanged). Trigger on "VENUE", "D-Show", "Profile", "SC48", ".dsh", "Digidesign", "rename the channels in this VENUE show", or "what is in this .dsh file". A .dsh file is NOT a DiGiCo session. NOT for S6L shows, gain/EQ/routing edits, or longer names.
---

# Avid VENUE / D-Show show files

A classic VENUE show file (`.dsh`) is a typed token stream after the magic
`Digidesign Storage - 1.0`. The tool in `scripts/` reads the config block and the strip
names, and renames strips without moving any byte offset. Format notes:
`references/FORMAT.md`. Requires Python 3.8 or later and nothing else.

## Safety rules

1. Write a new file. The tool refuses to overwrite its input.
2. A rename is allowed only when the new name is the same length as the old name or
   shorter. The tool refuses anything else, and it refuses to write if the file size changes.
3. Do not hand-edit gain, EQ, dynamics, routing, the patch, or longer names. Those live in
   binary arrays. Use the VENUE software.
4. Open every edited file in the VENUE standalone software, check it, and save it from
   there. Only that save goes to a console. Do the first load at prep, never at the show.

## Commands

```
python3 scripts/dshow_tool.py dump  SHOW.dsh       # config + unique strip names
python3 scripts/dshow_tool.py names SHOW.dsh       # slot, strip id, flag, name per strip
python3 scripts/dshow_tool.py rename SHOW.dsh "Old" "New" OUT.dsh [--dry-run] [--pad space|nul]
```

## Rename recipe

1. Run `names` and copy the exact old name (case and spaces matter).
2. Run `rename ... --dry-run`. Check the count of places (3 is normal: the strip object and
   two packed name tables) and the byte count.
3. Run it again without `--dry-run`.
4. Run `names` on the output and check the new name.
5. For several renames, chain them: the output of one is the input of the next.

## Gotchas

- `--pad space` (default) keeps the packed name tables intact. The strip name gets trailing
  spaces. `--pad nul` is the older method and can shift the packed tables (see FORMAT.md).
- Two strips with the same name are both renamed. The tool renames by name, not by strip id.
- Names are Latin-1. Characters outside Latin-1 are refused.
