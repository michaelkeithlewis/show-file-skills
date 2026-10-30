# Yamaha DM3

Covers DM3 and DM3 Standard. File extension: `.dm3f`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads with `show` and `check`. Every write is refused.
- `show` marks a column with `?` when no editor test checked that field on this console.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4 and 6. Skill: [`SKILL.md`](../SKILL.md).
- Contributed field map (not used by the script): [`references/dm3-fields.md`](../references/dm3-fields.md).

## What we know

- A new session saved by DM3 Editor 3.1.0 walks to its exact end and rebuilds byte for byte (BB-G2-WALK).
- The header model text is `DM3`. The session carries the editor's version, V3.10 (BB-G2-WALK).
- `Fader.On` is one unsigned byte on DM3, not a bit as on DM7 (BB-DM-SHAPE).
- Reads of a DM3 editor file matched the site's engine (README, "Verified for this release").
- DM3 and DM3 Standard differ only in `ProductSubName` (`DM3` against `DM3S`): a byte diff of the two DM3 Editor 3.1 blanks finds nothing else but save ids and one time stamp byte (markcarlberg, pull request #2, `references/dm3-fields.md`).
- The header model at 0x24 must be checked: a parser that checks only the `#YAMAHA MBDFProjectFile` magic misreads a `.dm3f` as a DM7 (same source).
- DM3 Editor 3.1 controlled saves placed the input patch codes (IN, DANTE, USB), the head amp at `Process/BuiltIn/InputPort[16]/HeadAmp`, the bus-owned send pre point, the insert point and insert codes, and the output patch codes for MIX, MATRIX, ST L, CUE L, MONI L, OSC and insert sends (`references/dm3-fields.md`).
- The comp ratio is u8 x10 with 255 = infinity (controlled save).
- A new show carries 14 protected factory scenes, an unprotected `Initial Data` scene and 262 protected factory presets (saves).

## What we don't know

- All writes: read only. The test that settles the writes is a rename test in DM3 Editor, then the rest.
- Names, colours, icons, faders and ON keys: read by the DM7 paths, unproven on DM3.
- Real DM3 shows: the docs name only a new editor session.
- A console load: not tested.
- Sends, EQ, dynamics, delay, inserts and the output patch: not read by the script.
- Where the -24 dB PAD is stored, and how it relates to `HeadAmp.Gain`.
- What `Process/Dante/InputPort[16]/HeadAmp` (-600 on the blank) means without a remote I/O device.
- Whether the CH 1 to 16 HPF offers a slope other than 12 dB/oct.
- PLAYBACK L/R as patch codes 0x07800000 and 0x07800001, and FX k L/R as 0x06400000 + (k - 1) x 16 + side: unconfirmed readings.
- `BandL.Type` and `BandH.Type` 2 as a high-pass or low-pass at the band's frequency (switched by `BandL.HPFOn` and `BandH.LPFOn`): unconfirmed.
- Which band copy plays with the 1-knob EQ on (unconfirmed reading: the bank plays, `OneKnobBackup` keeps the manual EQ).
- Bus GEQ (`Mix/GEQ`, `Stereo/GEQ`, 31 bands): gain units unconfirmed (0.01 dB likely).
- The processing order (unconfirmed reading: HPF, gate, EQ, comp).
- The gate key-in "Mix" text and code; whether the comp key-in has any other choice.
- Whether the post send point is post-fader or post-ON.
- Bus INSERT OUT codes. ST R, MONI R and CUE R as left + 1 are unconfirmed.
- What `Setup:InsertActive.On` and `Setup:MuteMaster.On` mean.
- Whether DM3 Editor 3.1 has any DCA page.
- Stereo-strip balance storage: whether each half's `Pan` holds the balance knob.
- Effect parameter maps (`Bank.Value[64]`).
- Whether a set password is stored in clear.
- What the factory scene and preset version bytes (`52 02 00 07`, `52 03 0A 09`) mean, and the table layout in editor versions other than 3.1.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-10-29, DM3 Editor 3.1, markcarlberg's blanks of both models and controlled saves mapped identity, patch, head amp, send, insert and output patch fields (`references/dm3-fields.md`).
