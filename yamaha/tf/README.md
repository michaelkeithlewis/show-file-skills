# Yamaha TF

Covers TF1, TF3, TF5 and TF-RACK. File extension: `.tff`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads with `show` and `check`. Every write is refused.
- `show` marks a column with `?` when no editor test checked that field on this console.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4 and 6. Skill: [`SKILL.md`](../SKILL.md).

## What we know

- A new session saved by TF Editor 4.50 walks to its exact end and rebuilds byte for byte (BB-G2-WALK).
- The header model text is `TF`. The session carries the editor's version, V4.50 (BB-G2-WALK).
- That session has `ProductName` `TF` and `ProductSubName` `TF5` (BB-G2-WALK).
- `Fader.On` is one unsigned byte on TF, not a bit as on DM7 (BB-DM-SHAPE).
- Reads of a TF5 editor file matched the site's engine (README, "Verified for this release").

## What we don't know

- All writes: read only. The test that settles the writes is a rename test in TF Editor, then the rest.
- Names, colours, icons, faders and ON keys: read by the DM7 paths, unproven on TF.
- TF1, TF3 and TF-RACK files: the docs name a TF5 session only.
- Real TF shows: the docs name only a new editor session.
- A console load: not tested.
- Sends, EQ, dynamics, delay, inserts and the output patch: not read.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
