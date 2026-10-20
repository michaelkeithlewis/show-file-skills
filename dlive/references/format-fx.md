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

## Dyn8

- Multiband compressor: 4 bands (in, threshold, ratio, gain, attack, release), 3 crossovers, slope (6, 18 or
  24 dB/oct), detector (Peak, RMS, Auto Punch, Auto Opto, Slow Auto, Fast Auto), soft knee.
- Dynamic EQ: 4 bands (in, frequency, width, cut or boost ratio, threshold, above or below, release mode). The
  cut/boost index runs 0-108, and 54 is 1:1 (no action). The ratio comes from `OCTIVE_DYN_EQ_RATIO_LOOKUP`
  @0x1017b2770. Bands 1 and 4 use the shelf width table.
- Thresholds use `GetFromOffsetHalved` @0x100503330 (0.5 steps of 1/32).

## Raw or unconfirmed

- Dyn8 `bands_wide`, `self_keyed` and side-chain bytes (reported under `?raw_tail`).
- Any parameter without a confirmed conversion code (reported as `?raw`).
- UltraFX "step" parameters (for example `HF CutType` 1.812) read as fractions, so their scale is not confirmed.
  On the plates, a nonzero `HF CutGain` points to a shelf, not a cut.
