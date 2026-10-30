# Avid VENUE D-Show

Covers classic D-Show, Profile and SC48 shows. File extension: `.dsh`.

## Tooling

- [`scripts/dshow_tool.py`](../scripts/dshow_tool.py) has `dump` (config and strip names), `names` (one line per strip) and `rename`.
- [`scripts/s6l_tool.py`](../scripts/s6l_tool.py) gives a read-only summary of a classic show.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md) and section 1 of [`references/S6L-FORMAT.md`](../references/S6L-FORMAT.md). Skill: [`SKILL.md`](../SKILL.md).
- Open every renamed file in the VENUE standalone software. Save the file there before the file goes near a console.

## What we know

- Classic shows use the same container as S6L shows, with the magic `Digidesign Storage - 1.0`.
- Avid's VENUE 2.9 and 4.5 demo shows parse and write back byte for byte (round trip).
- D-Show or Profile with FOH Rack, VENUE 2.9: `Main Rack Type` 0, `Console Type` 2 (PROVEN, 9 demo shows).
- SC48, VENUE 2.9: `Main Rack Type` 2, `Console Type` 3 (PROVEN, 2 demo shows).
- `Partial Support SW Version` is 2.0 on classic shows (PROVEN, demo files).
- A rename must be the same length as the old name or shorter. The file size must not change.
- `rename` works by name, so two strips with the same name are both renamed.

## What we don't know

- `dshow_tool.py` on a real classic show: the one show the tool was first tested on turned out to be an S6L show saved by VENUE 8.2.
- A renamed file opened in VENUE: not tested on any show.
- The `--pad nul` rename: unproven. Use the default `--pad space`.
- Whether a console loads a renamed file: not tested.
- Numeric parameters, routing and the patch: not read. Use the VENUE software for those changes.
- The token table in FORMAT.md: wrong in part. S6L-FORMAT.md section 1 has the correct container grammar.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
