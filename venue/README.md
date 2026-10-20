# venue: Avid VENUE / D-Show show files

A Claude Code skill and a Python script for classic Avid VENUE show files (`.dsh`,
Profile / SC48 / D-Show family). It reads the system config and every channel strip
name, and it renames strips in place without the console or the VENUE software.

The `.dsh` extension is not DiGiCo. The file magic is `Digidesign Storage - 1.0`.

## What is in the folder

- `SKILL.md`: the skill. Claude Code loads it when you ask about a VENUE show.
- `scripts/dshow_tool.py`: `dump`, `names`, `rename`.
- `references/FORMAT.md`: the format notes (token types, config block, strip objects,
  packed name tables, the safe-rename rule).

## Requirements

- Python 3.8 or later. No other packages.
- The VENUE standalone software, to open and re-save every edited file before it goes to a console.
- Your own show file. No show files ship with this folder.

## Quick start

```
python3 scripts/dshow_tool.py dump  "My Show.dsh"
python3 scripts/dshow_tool.py names "My Show.dsh"
python3 scripts/dshow_tool.py rename "My Show.dsh" "Kick In" "Kick" "My Show renamed.dsh" --dry-run
python3 scripts/dshow_tool.py rename "My Show.dsh" "Kick In" "Kick" "My Show renamed.dsh"
```

To install as a skill, copy this folder to `~/.claude/skills/venue-showfile/`.

## Status

- Proven on one real show file: the config block and all 267 strip slots read correctly,
  and a rename changes only the bytes of the renamed name (3 copies, size unchanged).
- Not proven: that a renamed file opens in the VENUE software. Treat every output as
  untested until you open it there.
- Not supported: longer names, gain, EQ, dynamics, routing, patch, S6L shows.
- Verified for this release: `python3 -m py_compile`, `--help`, `dump`, `names`, a
  shorter rename, a refused longer rename, and a dry run, all on a private show file
  that is not included.

This tool is not affiliated with or endorsed by Avid. VENUE and D-Show are trademarks
of Avid Technology. No warranty.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack planning app for touring and production crews.
