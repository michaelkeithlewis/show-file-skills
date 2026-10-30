# Yamaha DM7

Covers DM7 and DM7 Compact. File extensions: `.dm7f` and `.dmxf`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads both models with `show`, `check` and `ports`.
- On a DM7 at firmware V2.01 only, the same script writes with `rename`, `colour`, `fader`, `on`, `hpf`, `patch`, `preamp` and `apply`.
- `show` prints "Writes open for this file". Trust that line over this page.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4, 5 and 6. Skill: [`SKILL.md`](../SKILL.md).
- Open every written file in DM Editor and save it there. Load only that save on a console.
- Contributed field maps (not used by the script): [`references/dm7-fields.md`](../references/dm7-fields.md) and [`references/premium-rack.md`](../references/premium-rack.md).

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
- DM Editor 2.0 controlled saves (markcarlberg, pull request #2) placed the patch codes for OMNI, Dante, direct outs, mixes and Premium and EQ rack insert slots; the eight dynamics types and their parameter words; the tap point codes; send, pair, FIXED bus, DCA, mute group and channel link fields; monitor, cue, talkback and oscillator fields; and the output delay pool (`references/dm7-fields.md`).
- The FET Limiter time laws were proven at both ends: attack µs = 800 - 10 x index, release ms = 1100 - 10 x index (controlled saves, `references/dm7-fields.md`).
- Each `.bup.old` holds the same data as its `.bup` from byte 72 on after a DM Editor 2.0 save, under its own save id (controlled saves).
- A file that keeps the template's save ids loads and re-saves in DM Editor 2.0 (load test).
- U76 and Opt-2A parameter words were pinned by controlled saves; MBC4 by four controlled saves and a load (`references/premium-rack.md`).

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
- Version bytes of a `.dmxf`: a contributor reading (pull request #2) says `56 02 00 00`; this repo says `56 02 01 00` = V2.01 (FORMAT.md 4.1, BB-G2-WALK). Needs a save that settles it, for example the same session saved from DM Editor 2.0.0 and 2.0.1. The same reading gives `56 01 36 00` for one `.dm7f`, not compared with the V1.53 and V1.73 shows here.
- `#FILE` entry bytes 24 to 27 (name length + 8) and byte 43 (always 8): meaning not known.
- Whether a console, not DM Editor, accepts recompressed entries with unchanged save ids.
- Output kind 0x050, seen in pairs on ports 0 and 1. The mix and stereo insert send kinds 0x13E and 0x142 are unconfirmed (no save).
- The Dante patch "unit + 1" rule has no controlled save behind it.
- AES/EBU and USB inputs as a channel's own patch: seen only as insert returns. Kind 0x064 as an empty outboard slot: screen check only.
- FET Limiter word 6 (-545 to -455 seen; set to -540 when In-Out Link went on). Legacy Comp ratio words past 200; Comp 260 knee indices other than Soft-2; Diode Bridge ratio index 0.
- Key filter LPF and BPF spellings; the `SourceSelect` text for DYN2's Other Pre Proc.
- Delay scale codes 1 and 2 (unconfirmed reading: feet and samples); phones points (code 50 seen); meter points.
- Theater banks C and D and what `ActorSelect` does.
- The Mix Minus `BusType` spelling and every Broadcast Package field (greyed offline).
- Virtual Soundcheck: what `VirtualSC.Safe` and `SET/VirtualSC.MasterOn` do (unconfirmed reading: the channel's exemption and the master switch), and one show whose Playback In ports in the file did not match the editor page.
- Per-strip `CueButton.Assign` codes; whether CUE A and B mode are one setting or interlocked.
- A DM7C-labelled show that names channels past 72.
- Scene `Focus.DataFormat` targets, fade time unit, scene GPI codes, and what the two `SceneList` banks and the two `RecallSafe` copies are (unconfirmed reading: split sides).
- Where library presets other than input and output channel presets sit.
- FX rack parameter units for types not seen in shows; the reverb time index table. `FX.SlotSize` 0 on the second unit of a 2-unit type is unconfirmed.
- Six Premium Rack groups in a `.dmxf` matching 64 units plus the 32 a DM5 PY-DSP adds: unconfirmed.
- Rio D3 output gain, polarity and delay (`.dmxf` only, `SET/DanteRemoteControl/IOUnit/OutputPort[256]`): not seen on hardware.
- Portico 5033 word order: an earlier reading of DM7 files put word 0 as ALL BYPASS and each band switch before its band; the RIVAGE PM Editor reading in `references/premium-rack.md` puts word 0 as TRIM and each switch after its band. Both agree on the switch and gain words. Needs a controlled save.
- Rupert EQ810 words 6 and 7 (one reading: word 7 at 4 is the 185 Hz high pass, word 6 at 1 the 16 kHz low pass).
- DynamicEQ4 RATIO above 50 (a boost): assumed symmetric with the cut law, unconfirmed. DynamicEQ6 shelf Q law, and the A/R preset slots of bands 2 and 3.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-10-29, DM Editor 2.0, markcarlberg's controlled saves mapped patch codes, dynamics words, tap points and bus fields (`references/dm7-fields.md`).
- 2026-10-30, DM Editor 2.0 and RIVAGE PM Editor 7.2, DynamicEQ4 Q law corrected against a DM Editor reading (0.91 at 61); MBC4 words proven on both desks.
