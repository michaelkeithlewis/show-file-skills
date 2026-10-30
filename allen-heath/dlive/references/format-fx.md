# dLive FX side: UltraFX, FX rack, Dyn8, FX sends and returns

Decoded from dLive Director V2.12 with the symbol table and objdump. Ground truth: two Director-saved touring
shows with UltraFX, FX rack and Dyn8 units in use.

Tool: `scripts/dlive_fx.py dump <show.tar.gz> [--scene 65535] [--all]` prints JSON. `table` prints a short human
table. Parameter names, ranges, conversion codes, per-program parameter lists and the Dyn8 point map are Director's
own static tables, kept in `scripts/fx_tables.json` with their addresses.

## Section layouts (live scene, big-endian)

- **AHFX Manager NN** (UltraFX, 246 B): `6 | 3 | prog u16 | subtype u8 | name[19] | wet u16 | dry u16 |
  72 x param u16 | width u16 | 72 x MIDI CC u8`. Writer: `cAHFXNetObject::FillGetStatus` @0x100e5ada0.
- **FX Manager NN** (standard FX rack, 124 B): `7 | prog u16 | name[19] | wet u16 | dry u16 | 48 x param u16 |
  width u16`. Writer: `cIFXNetObject::FillGetStatus` @0x100279300.
- **Dynamics Unit NN** (Dyn8, 140 B): `2 | type u8 | 60 x param-point u16 | 8 x bands-wide u8 | 8 x self-keyed u8 |
  sc u8 u8`. Writer: `nDynamicsDataNet::PackFullMessage` @0x1000d81c0.
- **Sends**: `[on, pre, level s16be (dB x 256), (pan)]`, the same layout `dlive_mix.edit_send` writes.
- Gains use GainToUWORD: dB = (u ^ 0x8000 as s16) / 256, and 0 = -inf.

## Rack units, inputs and returns

- FX rack unit k = rack inputs 2k-1/2k = FX return strip k = FX Return Mixer rows 2k-1/2k. In a `dlive_mix.py`
  plan it is `FX Rtn 2k-1/2k`.
- A unit fed from a channel direct out (rack input = `Ip n DO`) needs no aux or FX bus. See `ears-fx.md`.
- A Dyn8 or FX unit used as an insert can sit on one channel only. The binding is in the patch, not in the unit.

## FX send masters

Decoded with Director 2.12 differentials on 2026-10-26: one change at a time, stored from Director, then compared.
The masters live outside the Mix Mixer, so a `Mono FX Send Channel` has a name but no Mix Mixer strip.

- **FX Send Mixer** (593 B): `01 | 16 x record (37 B)`. **AHFX Send Mixer** (297 B): `01 | 8 x record (37 B)`. The
  differentials covered FX sends only. The UltraFX record is read as the same layout, not tested.
- Record: `fader s16 (dB x 256, 0x8001 = -inf) | mute u8 (1 = muted) | 34 bytes not decoded`. The 34 bytes are probably
  DCA and mute group assigns, by size.
- Numbering: record k is FX send k+1 in Mixer Config order, mono FX sends first, then stereo, one record each. The
  patch's "FX Send k" is the same number. With 2 mono and 2 stereo FX sends, "FX Send 3" is St FX 1. Proven in
  Director 2.12: a show set to mFX 2 / sFX 2 read units 1-4 as the two mono and then the two stereo sends, with the
  written levels.
- Records past the FX send count keep their old values. Director's config change does not touch them.
- The factory FoH show (Director 2.11 and 2.12) has FX sends 1-8 at 0 dB and muted (`0000 01`). Its FX returns are
  muted at -inf too. A show built from it has silent FX until you unmute each master it feeds. Leave the unused
  masters as they are.
- Writer: in a `dlive_mix.py apply` plan, `"mixes": {"FX 2": {"mute": false, "fader": 0}}` writes the master in every
  scene the plan edits. Older stored scenes hold a shorter section, and the writer skips them. The bytes match the site engine's writer on the factory show. `Main`, aux and group entries
  still go to the Mix Mixer. A `UFX n` entry writes no master.

## Dyn8

- Multiband compressor: 4 bands (in, threshold, ratio, gain, attack, release), 3 crossovers, slope (6, 18 or
  24 dB/oct), detector (Peak, RMS, Auto Punch, Auto Opto, Slow Auto, Fast Auto), soft knee.
- Dynamic EQ: 4 bands (in, frequency, width, cut or boost ratio, threshold, above or below, release mode). The
  cut/boost index runs 0-108, and 54 is 1:1 (no action). The ratio comes from `OCTIVE_DYN_EQ_RATIO_LOOKUP`
  @0x1017b2770. Bands 1 and 4 use the shelf width table.
- Thresholds use `GetFromOffsetHalved` @0x100503330 (0.5 steps of 1/32).
- A stereo input takes two units side by side, the odd one on the left. Every stereo Dyn8 insert in the reference
  shows does this (7/8, 9/10, 15/16, 23/24, 29/30, 37/38).
- Mode is the band In points, not the type byte. Points 5-8 are the compressor band In and points 55-58 the dynamic
  EQ band In, with `0x8010` = In and `0x8000` = Out. Multiband has the compressor bands in and the EQ bands out. Dynamic
  EQ is the other way round. Both halves can be in, and a fresh unit has both in.
- The type byte is the Dyn8 Options switch "Enable Multi BD 3" (@0x1008ba790). It reads 0 on all 2,432 units in 42 real
  shows, whichever bands are in.
- A fresh unit holds Director's defaults (`cDynamicsProgramDefines::GetDefaultValueForParamPoint` @0x100502e50), and the
  tail of bands wide 0, self keyed 1, side chain 0 0.
- Insert routing, from the Channel Mapper: `Ip Ins A/B return` [ch] returns from `Dyn k out` (type 0x27, k-1), and
  `Dyn unit input` [k] holds the send (0x08 Ins A or 0x09 Ins B, ch-1).
- The Dyn8 screens in Director have not been checked against these modes yet. The mode rule comes from the code and the
  real shows.

## Raw or unconfirmed

- Dyn8 `bands_wide`, `self_keyed` and side-chain bytes (reported under `?raw_tail`).
- Any parameter without a confirmed conversion code (reported as `?raw`).
- UltraFX "step" parameters (for example `HF CutType` 1.812) read as fractions, so their scale is not confirmed.
  On the plates, a nonzero `HF CutGain` points to a shelf, not a cut.

## Dyn8 word laws (markcarlberg, pull request #2)

Saved in dLive Director, one control per band per save. Version 02 layout: `[02][type]`, then 16-bit big-endian
words from byte 2, then byte 121 bypass (`10`) and bytes 122-129 side chain Wide per band (multiband LF-HF, then
dynamic EQ LF-HF). [save-proven]

| Words | Control | Law |
|---|---|---|
| w00 | master trim | `0x8000 + 10 x dB`, -12 to +12 |
| w01-04 | multiband threshold | `0x8000 + 32 x dB`, -46 to +18 |
| w05-08 | multiband in | `0x8000 + 16n` |
| w09-12 | multiband gain | `0x8000 + 10 x dB`, -6 to +18 |
| w13-16 | multiband ratio | word - 0x8000: 0 1:1, 120 1.17, 222 1.45, 341 1.9, 416 2.4, 478 2.8, 512 3.4, 536 3.6, 573 4.0, 636 4.8, 689 6, 726 7, 796 10, 832 20:1 |
| w17-19 | crossovers | `4 x 2^(raw/4608)` Hz, 20 Hz to 18 kHz |
| w20 | slope | `0x8000 + 16n`: 0 6 dB/oct, 2 24 |
| w21 | detector | 0 Peak, 1 RMS, 2 Auto Punch, then Auto Opto, Slow Auto, Fast Auto in Director's stepping order |
| w22 | knee | 0 hard, 1 soft |
| w23-26 | attack | `65535 x (log10 s + 6) / 11`, 0.3 to 300 ms |
| w27-30 | release | same law, 50 ms to 2 s |
| w31-34 | dynamic EQ width | 0 shelf; 72 1.5 oct, 106 1.27, 160 1.05, 256 0.86, 328 0.7, 388 0.45, 512 1/9 |
| w35-38 | dynamic EQ frequency | `4 x 2^(raw/4608)` Hz |
| w39-42 | dynamic EQ cut/boost | 54 is 1:1, below 54 a cut (the step to ratio list is not reproduced here) |
| w43-46 | dynamic EQ threshold | `0x8000 + 32 x dB` |
| w47-50 | below | 1 = below |
| w51-54 | release mode | 0 Std, 1 Fast |
| w55-58 | dynamic EQ in | |

- Under the Auto detector modes Director hides the bands' attack and release.
- Director keeps each crossover at least 2.42 times the one below; a file with two closer crossovers loads and
  keeps them.
