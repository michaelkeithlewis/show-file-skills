# dLive scene safes and recall filters, field by field (Director V2.12)

Extends `format-mixconfig.md` and `scripts/dlive_safes.py`, which cover the record sizes and the per-bus
columns. This page names every byte of an input record and the head of a mix record.

Source: the Director V2.12 binary. `cSceneSafeManager::Set*SceneSafe` and `Set*Safe` (each setter writes one
field; the store offsets are in the disassembly), `cInputChannel::RecallFilterChanged` (which component
gets which byte) and `sInputSceneSafeRecallFilterBase::AreAnyFiltersSet`. Struct sizes:
`sInputSceneSafeRecallFilterBase` 510 bytes (0x1fe), `sInputSceneSafeRecallFilter` 521 bytes (0x209), the
11 channel fields at the end.

Checked against 15 real shows. Scenes without filters are all zero in every show.

## Where the data sits

- `Show/SceneSafes/StageBoxSceneSafes.dat`: `01 01 15` + 13-byte mixer config, data from byte 16,
  122077 bytes.
- In a scene: mixer config at 330..342, filter from byte 343, the same 122077 bytes, then `01` + u32 chain
  length (header 122425 bytes in total).
- 1 = safe / filtered out (not recalled), 0 = recalled.
- Layout: 128 inputs x 521 (66688 bytes), then 64 mixes x 518, then FX 32, 16 FX sends x 37, 32 FX returns
  x 510, AHFX, DCA, other, UFX. Where the mixes start is open (see "What we don't know").

## Input record (521 bytes, offsets in hex)

| Offset | Field |
|---|---|
| 0x000 | Fader |
| 0x001 | Mute |
| 0x002 | Pan / width (image controls, LCR, divergence) |
| 0x003 | Group assign, 64 x 1 byte, index = bus number |
| 0x043 | Aux send level / pre, 64 |
| 0x083 | Aux send on, 64 |
| 0x0C3 | Aux send pan, 64 |
| 0x103 | Matrix send level, 64 |
| 0x143 | Matrix send on, 64 |
| 0x183 | Matrix send pan, 64 |
| 0x1C3 | AHFX send level, 8 |
| 0x1CB | AHFX send on, 8 |
| 0x1D3 | AHFX send pan, 8 |
| 0x1DB | Main on / main mono on |
| 0x1DC | Wedge / IEM on |
| 0x1DD..0x1FC | DCA and mute groups, 32 (likely 24 DCA + 8 mute groups) |
| 0x1FD | Name / colour |
| 0x1FE | Trim (Digital Attenuator) |
| 0x1FF | Stereo (stereo image, stereo inputs only) |
| 0x200 | Preamp model |
| 0x201 | HPF and LPF (both filters) |
| 0x202 | Insert 1 and 2 |
| 0x203 | PEQ |
| 0x204 | Gate (incl. side chain) |
| 0x205 | Compressor (incl. side chain) |
| 0x206 | Delay |
| 0x207 | Direct out |
| 0x208 | Source A/B/C/D (absent on 5 of 128 inputs) |

Open question: `dlive_safes.py` reads the aux sends as 64 triplets from offset 67 (0x043) and the matrix
sends as 64 triplets from 259 (0x103), i.e. 3 bytes per bus. The setters in our reading write level, on
and pan as three separate 64-byte arrays, i.e. 1 byte per bus in each. Both cover the same 192 bytes,
but which byte belongs to which bus differs. A scene with exactly one aux send filtered on one input
settles it.

## Mix record (518 bytes)

| Offset | Field |
|---|---|
| 0 | Delay |
| 1 | Name / colour |
| 2 | Send source |
| 3 | Group to group |
| 4 | External trim |
| 5 | Insert |
| 6 | PEQ |
| 7 | Compressor |
| 8 | GEQ |
| 9 | Fader |
| 10 | Mute |
| 11 | Pan / width |
| 12.. | Sends (aux, matrix, AHFX arrays) and DCA / mute groups, not mapped yet |

The record alignment was checked against stereo pairs. The Director setters address these fields one
record off; the data does not.

## More setter regions (absolute offsets into the 122077 bytes, not verified against data)

FX sends from 0x1862B (37 per send: level, mute, routing, name / colour, send source), FX returns from
0x1887B (510 per return: level, mute, image, routing, name), AHFX sends 0x1C84B, AHFX returns 0x1C973,
DCA 0x1D963 (level, mute, name), preamp safe per input 0x1D9F7 (64), T-Snake preamp 0x1DA37 (64),
Port B+ 0x1DA77. These did not line up cleanly with a real show's data; they may be off by one record like
the mix setters. Confirm with calibration scenes (one filter per scene) before using them.

## Seen in real shows

- "Everything safe" scenes (used to recall strip assign only): every field 1, also for buses that do not
  exist. "Stereo" only on stereo inputs, "Source" on 123 of 128.
- Global safes on one touring show: name / colour, main, wedge / IEM, AHFX sends, DCA 1-8 and aux sends to
  some mixes safe on all 128 inputs, plus a handful of inputs and mixes fully safe. Stereo pairs always
  match.
- Every dLive show carries `StageBoxRoleSceneSafes0-4` and `SurfaceRoleSceneSafes0-4`.
- Not mapped yet: mix sends, FX, FX returns, DCA channels, other, UFX, surface safes (576 bytes).

## What we don't know

- Where the mix records start. `scripts/dlive_safes.py` starts them right after the inputs (data byte 66688).
  This page found the stereo pairs line up (left and right mix records equal) 7 bytes later, at 66695, in real
  shows with mix safes set, and the 7 bytes between read 1 in "everything safe" scenes. A scene with exactly one
  mix safe set settles it. Until then `dlive_safes.py` keeps 66688.
- The aux and matrix send bytes: 64 triplets (`dlive_safes.py`) or three 64-byte arrays (the setters). See
  "Input record".
- The setter regions above: not checked against show data.
