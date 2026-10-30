# Yamaha RIVAGE PM

Covers PM3, PM5, PM7 and PM10. File extension: `.RIVAGEPM`.

## Tooling

- No command works on these files. [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) refuses a RIVAGE PM file with one sentence.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4 and 6.

## What we know

- RIVAGE PM files use the generation 2 container, `#YAMAHA MBDF`.
- A new session saved by RIVAGE PM Editor 7.2.0 walks to its exact end and rebuilds byte for byte (BB-G2-WALK).
- The header model text is `Rivage`. The session carries the editor's version, V7.20 (BB-G2-WALK).
- RIVAGE PM's compressed fields are a body with no schema of their own ([`references/script-notes.md`](../references/script-notes.md)).

## What we don't know

- Every value in the file: refused until a reader for its sections exists.
- Channels, patch, processing and scenes: nothing on this model line is decoded.
- Real RIVAGE PM shows: the docs name only a new editor session.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
