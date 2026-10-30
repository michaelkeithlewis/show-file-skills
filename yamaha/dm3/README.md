# Yamaha DM3

Covers DM3 and DM3 Standard. File extension: `.dm3f`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads with `show` and `check`. Every write is refused.
- `show` marks a column with `?` when no editor test checked that field on this console.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4 and 6. Skill: [`SKILL.md`](../SKILL.md).

## What we know

- A new session saved by DM3 Editor 3.1.0 walks to its exact end and rebuilds byte for byte (BB-G2-WALK).
- The header model text is `DM3`. The session carries the editor's version, V3.10 (BB-G2-WALK).
- `Fader.On` is one unsigned byte on DM3, not a bit as on DM7 (BB-DM-SHAPE).
- Reads of a DM3 editor file matched the site's engine (README, "Verified for this release").

## What we don't know

- All writes: read only. The test that settles the writes is a rename test in DM3 Editor, then the rest.
- Names, colours, icons, faders and ON keys: read by the DM7 paths, unproven on DM3.
- Real DM3 shows: the docs name only a new editor session.
- A console load: not tested.
- Sends, EQ, dynamics, delay, inserts and the output patch: not read.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
