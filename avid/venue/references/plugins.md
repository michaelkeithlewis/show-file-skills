# S6L plug-in state notes

Notes from markcarlberg on the plug-in state that S6L shows store. The rack structure, the slot record, the chunk
record and the AAX SDK default chunk format are in [`S6L-FORMAT.md`](S6L-FORMAT.md) section 4; the routing word
detail is in section 10.9. This file adds what a slot holds for two plug-in families. The tools do not decode or
change either one: they list the slot as "settings stored" and copy it byte for byte.

Labels as in `S6L-FORMAT.md`: PROVEN, STRONG, UNVERIFIED.

## Waves SoundGrid rack

A `SoundGridRack` slot holds a Waves preset in XML. STRONG (read in eleven production shows saved by VENUE 8.0 and
8.1, against Waves V16).

- The rack is marked by `GenericType="WSCR"`.
- `<ActiveSetup>` holds `SETUP_A` or `SETUP_B`. The rack's settings are in `<PresetData Setup="SETUP_A">` (or B).
- Inside are eight `<slot_data>` elements, one per rack slot, each with `plugin_name`, `plugin_preset` (the
  plug-in's own preset in a CDATA block), `plugin_current_setup` (`setA` or `setB`, the live one), `plugin_bypass`
  and `plugin_disabled` (`true` or `false`).
- In the plug-in's own preset, `<Parameters Type="RealWorld">` is a whitespace-separated list, one value per
  parameter in the plug-in's own units, `*` where the plug-in stores none.

This repo does not map list positions to controls. A position map would come from the plug-in's own files, and
this repo takes no facts from vendor files.

## Avid Channel Strip (AAX default chunk)

The parameter IDs below are read from the default-format chunks of the 32 Channel Strips in Avid's four public demo
shows. Units are as stored: dB, Hz and seconds. STRONG. Every demo Channel Strip sits at 1:1 and in circuit, so the
ratio and type codes are pinned only that far.

| Section | Parameter IDs |
|---|---|
| Dynamics | `Dynamics On/Off` |
| Compressor | `Cmp In/Out`, `Cmp Ratio`, `Cmp Threshold` (dBFS), `Cmp Attack Time` (s), `Cmp Release Time` (s), `Cmp Knee`, `Cmp Gain Makeup` (dB) |
| Expander and gate | `Exp In/Out`, `Exp Ratio`, `Exp Threshold` (dBFS), `Exp Attack Time` (s), `Exp Hold Time` (s), `Exp Release Time` (s), `Exp Depth` (dB, stored positive) |
| EQ | `EQ On/Off`; per band `EQ <band> In/Out`, `Gain`, `Frequency`, `Q`, with `<band>` = `Low`, `Low-Mid`, `High-Mid`, `High`; `EQ Low Type`, `EQ High Type` |
| Filters | `Filters On/Off`; per filter n = 1, 2: `Filter n In/Out`, `Filter n Frequency`, `Filter n Type`, `Filter n Slope 12/24dB` |

UNVERIFIED (one value seen per field):

- `EQ Low Type` and `EQ High Type` 0 as a shelf.
- `Filter n Type` 0 as a high pass and 1 as a low pass.
- `Filter n Slope 12/24dB` 0 as 12 dB/oct and nonzero as 24 dB/oct.

## Open questions

- Channel Strip codes away from the demo defaults, and the other Avid default chunks.
- The slot flag bytes and the chunk header IDs (also in `S6L-FORMAT.md` section 9).
- The "15 is unused" note beside the routing save (value or slot not stated).
- The full encoding of `MicLineInputStrip` bytes 102 to 104.
