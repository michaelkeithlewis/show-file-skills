# Yamaha DM7

Covers DM7 and DM7 Compact. File extensions: `.dm7f` and `.dmxf`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads both models with `show`, `check` and `ports`.
- On a DM7 at firmware V2.01 only, the same script writes with `rename`, `colour`, `fader`, `on`, `hpf`, `patch`, `preamp` and `apply`.
- `show` prints "Writes open for this file". Trust that line over this page.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4, 5 and 6. Skill: [`SKILL.md`](../SKILL.md).
- Open every written file in DM Editor and save it there. Load only that save on a console.

## What we know

- The header model is `DM7` on both models. `ProjectInfo` tells the models apart: `ProductSubName` is `DM7` or `DM7C` (BB-DM-MODEL).
- Writes are open only when `ProductSubName` is `DM7` and the firmware is V2.01.
- DM Editor 2.0.1 showed every written value. The re-save matched 208 items with 0 mismatches (BB-DM-LOAD, BB-DM-RANGE, BB-DM-ORDER).
- Names: DM Editor shows 8 characters, so `rename` writes at most 8.
- Faders take any 0.01 dB from -138 to +10 dB. HPF takes any 0.1 Hz from 20 to 2000 Hz (BB-DM-RANGE).
- Patch writes take none, OMNI 1 to 32 and DANTE 1 to 144. The tests wrote OMNI 9, 13 and 14, DANTE 5 and 144, and none.
- A head amp change goes to the port the channel is patched to at that moment (BB-DM-ORDER).
- The schema changes with firmware. The `Mixing` section is 308,622 bytes at V1.53, 309,618 at V1.73 and 310,514 at V2.01.
- Real DM7 shows at V1.53 and V1.73 walk to their exact end and rebuild byte for byte (BB-G2-WALK).
- DM Editor loads a file whose entries changed compressed size, and rejects a broken zlib stream (BB-G2-ZLIB).

## What we don't know

- A console load of a written file: not tested. Only the editor has loaded these files.
- DM7 firmware 1.x and every firmware other than V2.01: read only.
- DM7 Compact: read only. No write test ran on a DM7 Compact session.
- Icons, DCA assigns, and mix, matrix and DCA names: read only. Icons and names read as stored, unproven.
- Stored scenes: refused.
- A channel on another EQ type: the HPF element is not proven. `show` prints `-` and `hpf` refuses the channel.
- Sends, EQ, dynamics, delay, inserts and the output patch: not read.
- Mix, matrix and stereo faders, ON keys and bus types: not read.
- User key files (`.dm7u`), scene-only files and library files: refused by design.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
