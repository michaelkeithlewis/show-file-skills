# Yamaha DM5

Covers DM5 and DM5 Compact. File extensions: `.dm7f` and `.dmxf`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads with `show` and `check`. Every write is refused.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4 and 6. Skill: [`SKILL.md`](../SKILL.md).

## What we know

- DM Editor 2.0.1 saved new sessions as DM5 and DM5 Compact (BB-DM-MODEL).
- The header model on a DM5 file is `DM7`. `ProjectInfo` tells the models apart: `ProductName` is `DM5` and `ProductSubName` is `DM5` or `DM5C` (BB-DM-MODEL).
- A DM5 show has the same `#FILE` groups as a DM7 show (FORMAT.md section 4.4).

## What we don't know

- All writes: read only until the DM7 test runs on a session of this model.
- Real DM5 shows: the docs name only new editor sessions.
- A console load: not tested.
- Sends, EQ, dynamics, delay, inserts and the output patch: not read.
- Mix, matrix and stereo faders, ON keys and bus types: not read.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
