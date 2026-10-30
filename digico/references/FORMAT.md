# DiGiCo Quantum 2 .SES format: decoded so far

Console: **Quantum 2**, offline editor **v22.0.2242**. Baseline for the early fixed offsets: an editor-saved default
Q225 session (589028 bytes). The fixed offsets are historical: use the (module, param, band) keys in "File structure" below.

## Container
- Uncompressed, unencrypted. Entropy ~3.36 bits/byte.
- Header @0x00: `"DiGiCo     "` (11B) + 4-byte model field @0x0b (`"SD5 "`, `"Q2  "`) + `".SES vO   \r"`.
- Save noise: ~1914 OLE-date float64 timestamps (high word `0x40e68f62`); masked structurally in tooling.

## Serialization model (KEY)
Channel parameters are a stream of **8-byte tagged slots**:
`[float32 value][1-byte field-ID][05 00 00]` -> next value is +8 bytes on.
EQ, dynamics, and filters all follow this. Field-ID byte identifies the parameter type.

## Per-channel block
- **Channel stride = 0x12f6 (4854 B)**, constant. `chN field = ch1_offset + (N-1)*0x12f6`.
- All parameter values are float32 little-endian.

### Channel-1 offsets (add stride for other channels)
| Param | Offset | Encoding |
|---|---|---|
| LPF in | 0x14081 | 0/1 |
| LPF freq | 0x14089 | Hz (coarse HF resolution) |
| HPF in | 0x14091 | 0/1 |
| HPF freq | 0x14099 | Hz |
| EQ in | 0x141c5 | 0/1 |
| fader | 0x14559 | dB |
| mute | 0x14561 | 0/1 (1=muted) |

### EQ: 4 bands, band record stride 0x60, laid out band4->band1 ascending
`band N freq = 0x14305 - (N-1)*0x60`. Offsets **relative to band freq**:
| Field | rel | Encoding |
|---|---|---|
| shape | -0x08 | 1.0=bell, 3.0=lowshelf, 4.0=highshelf (2.0=?) |
| freq | +0x00 | Hz |
| Q | +0x08 | float |
| gain | +0x10 | dB |
| Precision/Classic | +0x20 | 0=Precision, 1=Classic |
| dynamic-EQ enable | +0x28 | 0/1 |

Per-band shape options are restricted: bands 1-2 bell↔lowshelf, bands 3-4 bell↔highshelf.
Dynamic-EQ sub-params (threshold/ratio/etc.) when enabled: NOT yet mapped.

### Dyn1 compressor: tagged slots @ 0x143af + k*8  (FULLY MAPPED)
| Field | Offset | Encoding |
|---|---|---|
| **in** | 0x143af | 0/1 (0x143b7 is a constant 1.0, NOT the in bit) |
| threshold | 0x143bf | dB (mirrored at +0x40, +0x80) |
| **knee** | 0x143c7 | enum: hard=0.0, med=1.0, soft=2.0 |
| attack | 0x143cf | **seconds** |
| release | 0x143d7 | **seconds** |
| ratio | 0x143df | :1 |
| makeup | 0x143e7 | dB |
| **mode** | 0x143a7 | comp=0, multi=1, deesser=2 (gate/ducker vals TBD) |
| **autogain** | 0x143ef | 0/1 |

### Dyn2 (gate/ducker/comp): record @ 0x14497 (mode), +8 each
| Field | Offset | Encoding |
|---|---|---|
| **mode** | 0x14497 | gate=0, duck=1, comp=2 (other vals TBD) |
| in | 0x1449f | 0/1 |
| threshold | 0x144a7 | dB |
| attack | 0x144af | seconds |
| release | 0x144b7 | seconds |
| hold | 0x144bf | seconds |
| range/depth | 0x144c7 | dB (stored positive) |

Both Dyn slots share a unified processor: the mode selector is the slot immediately
before the In bit. Switching mode also rewrites that mode's default param values.
**Sidechain link** (a channel's key from another channel): (05, 16, 0) = the source as a route, (05, 37, 0) = key
on. Console sample and details: `CHANNEL_MODEL.md`, Dyn2.

## Multiband / pan / aux / Mustard Comp (2026-07-09)
- **Dyn1 multiband**: 3 band records @0x143bf/0x143ff/0x1443f = [on@-8][thresh][?+8][atk+0x10 s][rel+0x18 s][ratio+0x20].
  UI band->record: b1 (lo)->rec1, b2 (mid)->rec3, b3 (hi)->rec2, i.e. band bytes 0 / 2 / 1 (console-confirmed).
  Crossovers: lo @0x1447f (def 130Hz), hi @0x14477 (def 1000Hz).
- **SD EQ per-band on** @ band freq+0x18 (gain+8), 1.0=on.
- **Pan** @0x14b55: -1.0=hard left, 0=center (marker-0d sends section).
- **Aux1**: level @0x1468b (dB, -150=off), on @0x14693. Further auxes likely follow in same section.
- **Mustard Comp** (marker 1d, same field-IDs as SD dyn): model @0x1503d (Classic=0, VCA=3, FET=4,
  Optical=5, LevAmp=8), on @0x15045, mix @0x1504d (1.0=100%), threshold @0x15065, flagA @0x1506d,
  attack @0x15075 (s), release @0x1507d (s), ratio @0x15085, output @0x1508d (dB), flagB @0x15095,
  optical atk/rec opts @0x1509d/0x150a5, sc HP @0x150b5, sc LP @0x150bd,
  FET: in @0x150d5, ratio enum @0x150dd (4:1=1, 8:1=2), out @0x150ed.
- **Field-ID bytes are global across processors** (0e=thresh, 11=attack, 12=release, 10=ratio, 09=gain);
  the marker byte after the ID identifies the section (05=SD dyn, 1d=M-comp, 0d=sends/pan).

## Names
- Length-prefixed: `[len:u8][chars][nullpad]`, appears ~20x per channel.
- Every copy is a **fixed 32-byte field: up to 31 characters** (Latin-1). A longer name moves nothing and
  does not grow the file (see "File structure" below). The console does not clear the rest of the field, so
  old characters can follow a new, shorter name: read by the length byte. Console-saved sessions hold long
  names on every Quantum model (1267 input names over 8 characters in 189 sessions from the Q112, Q225, Q326,
  Q338 and Q852, V1926 to V2242), and names of 9 to 13 characters written in place by bytes loaded on a
  Quantum 112 (V2242). The +361 B once seen after renaming 12 channels is exactly one bank record (0x169), so
  that save most likely also gained a bank.
- The tools here cut channel names to 8 characters by choice (short console names); `ses.rename()` writes
  up to 31 with `max_len=31`.
- Bus names: separate region (~0x4cd00), ~15 copies.

## Console-confirmed
HPF, fader, mute, and a name+HPF+fader combo all loaded & displayed correctly on a real
Quantum 2 -> external in-place patches are accepted (console rebuilds caches on load).
The file also serializes volatile heap pointers/caches; we patch a real baseline and let
the desk rebuild them: never author those from scratch.

## Tooling
The early offset tools only fit one 48-channel layout and are not included. `scripts/ses.py` replaced them.

## Not yet mapped
Dyn1 knee + which toggle is in; Dyn2 (gate); Mustard EQ/Dyn1/Dyn2; digitube; inserts;
input patch/routing; bus sends/assignments; freq/gain quantization grid.

## Mustard Gate + flag disambiguation + pan/aux (2026-07-16)
- **Mustard Gate/Ducker** record @0x15157 (8-byte slots): mode @0x15157 (gate=0, duck=1),
  in @0x1515f, threshold @0x15167, attack @0x1516f (s), release @0x15177 (s), hold @0x1517f (s),
  range @0x15187 (positive dB).
- **M-Comp flags resolved**: knee @0x1506d (hard=1, soft=0); sensing @0x15095 (RMS=0, Peak=1);
  optical attack option @0x1509d (fast=0, medium=1).
- **Pan** @0x14b55: -1.0 hard L, 0 center, +1.0 hard R (fully confirmed).
- **Aux sends** inline: aux N level @0x1468b+(N-1)*0x60, on-bit at +8. aux1/aux2 verified.
  HIGHER auxes are NOT inline (aux12 landed at 0x1838d, a separate sends matrix) - needs aux-ramp capture.

## File structure (2026-10-11, from the V2242 editor binary + editor-saved baselines)
- Editor binary `Quantum2.exe` is 32-bit Delphi 10.3; its record RTTI names the slot type `tControllerSnapshot`.
- **Header** 0x100 B, then a **section table**: int32 offsets[40] at 0x100, section ids u8[40] at 0x1a0. The editor
  rejects a file unless offsets ascend and the last one equals the file size. Ids seen: 201 channel records,
  211 live channel/bus modules, 219 snapshot copies of channel blocks, 243 surface.
- **Module record**: `da 00 | 3a 00 (header len from type) | type u16 | 00 00 | name ShortString[31] (32 B) | TDateTime |
  count u16 | ... | count x slot | ff x8 00 x4`.
- **Slot** = `[param u8][module u8][band u8][flags u8][float32]`. Every offset in this file points at the float; the
  4 bytes BEFORE it name the field (the "field-ID after the value" reading above is off by one slot).
- **Input channel** = 18 records (01 input, 09 delay, 07 filters, 08 inserts, 04 EQ, 05 dyn, 0c fader/mute, 02 sends,
  0d pan, 03 groups, 0e, 13, 0a, 1a-1e Mustard) + trailer `27 00 | id (0x0100|idx) | name`. Channel record in
  section 201: `cb 00 79 00 | id | number | name`. All 20 copies of a name are fixed 32-byte fields.
- **Stride depends on session structure** (4854 B with 6+6 auxes, 4750 B with 4+7), so key by (module, param, band),
  never by offset. Keys for every field mapped above: `scripts/keys_from_offsets.json`. The control names come from the
  installer's iPad control file for the Q2 (164 controls with min/max).
- EQ: UI band n = band byte 4-n (byte 3 = LF). Dyn2 = module 05 band 3. Aux sends: module 02, one band per aux
  (mono auxes first). Delay on = (09, 0x07).
- **Filters**: the strip shows the -3 dB cutoff, the file stores the design frequency. Shown HPF = stored x 1.25,
  shown LPF = stored x 0.8. EQ frequency, gain and Q are stored as shown.
- Verified by loading generated sessions in the V2242 editor (running under Wine).
- **EngineChannel** (section 201 record +84, V1619+): DSP path. SD models keep inputs and buses in one pool: groups
  (06) at the bottom, then the inputs, then the Talkback Input (0c) at last input + 1, with aux (05) and matrix (10)
  outputs at the top (SD9/SD11/SD12 to 191, SD5/SD7/SD8/SD10 to 255). Quantum inputs have their own pool from 0; TB In
  sits at 254 on Q2/Q3/Q5/Q7 and at last input + 1 on Q1/Q8. The editors move TB In to last input + 1 on load where
  it sat there before (boot re-saves, 2026-10-12). `scripts/sessionmaker/layout.py` `engine_room()` and `validate.py` enforce it.

## Tools (2026-10-11)
- `scripts/ses.py`: structural reader/writer. Parses any session back to V1619 (Q2, Q3, Q5, SD8, SD9, SD12 tested),
  finds live channels, gets/sets slots by key, renames all name copies in place.
- `scripts/sesproc.py`: processing keys and the SD comp and Mustard writers.

## Stereo, Mustard, Spice Rack, SD FX, dynamic EQ and levels (2026-10-11, editor-verified)
- **Stereo inputs**: in the section 201 channel record, the byte at +41 is the width (01 mono, 02 stereo). The record's
  `number` is the surface channel. After a Channel Order restructure it differs from the internal index
  (`id & 0xff` + 1). `ses.py` maps them: `Session.display`, `Session.width`, `Session.ch(n)`.
- **Mustard comp** (module 0x1d, band 0): on 0x02, model 0x0b (classic 0, vca 3, fet 4, optical 5, levamp 8),
  mix 0x47, threshold 0x0e, knee 0x0f (hard 1), attack 0x11 (s), release 0x12 (s), ratio 0x10, output 0x09.
  FET only: input 0x41 (default -20), ratio button 0x4a (4:1 = 1, 8:1 = 2, 12:1 = 3, 20:1 = 4), output 0x4d.
  Quantum 225 limit: 24 instances, and a stereo channel uses 2. On load, the editor turns off the excess in channel
  order. The Optical ratio is a step, (0x4c, 0): real sessions hold 2, 3, 4, 5 with the ratio (0x10) at 2:1, 3:1, 4:1,
  6:1 (`CHANNEL_MODEL.md`, Mustard keys).
- **Spice Rack / Chilli 6**: type 0x1f records with 67 slots in section 211, in Spice Rack slot order (6 slots on a
  Q225). Bands 0-3 are multiband bands 1-4, band 4 is P1, band 5 is P2. Params: 03 bypass, 0e threshold,
  11 attack (s), 12 release (s), 0a range (dB, negative cuts), 07 gain, 05 frequency (crossovers on bands 1-3),
  06 Q. The insert routing (insert A > INTERNAL > Spice Rack > slot) is made in the editor and lives in the baseline.
- **SD FX unit**: type 0x15 record named after its preset (for example "Live room"). Predelay (0x0f, 0) in s,
  lo filter (0x14, 1) Hz, hi filter (0x14, 0) Hz, hi damping (0x37, 0) Hz, decay (0x12, 0) in s, mix (0x01, 0).
  Units, aux feeds and return channels can now be written from nothing (see "FX units, sends, buses and patch"
  below); a baseline can also carry its own editor-made units.
- **Dynamic EQ** on a channel EQ band (module 04, same band byte as the EQ): enable 0x7d, threshold 0x0e,
  ratio 0x10, attack 0x11, release 0x12, below/under 0x0b.
- **Levels**: DiGiCo thresholds are dBFS and stop at 0.
- **Surface banks** (section 243): u16 | u32 bank count | banks of 0x169 B: u16 size | u16 index |
  name ShortString[15] | ... | 12 strips of (index u8, type u8) at +0x23 (01 input = internal index - 1, 05 aux,
  06 group, 0a CG, 10 matrix) | ... | 12 view bytes at the end of the bank (0 SD view, 2 Mustard view).
  The SD/M strip buttons only switch this view. Mustard is active once any Mustard module is on, and the strip
  then shows "active" over M. `ses.py`: `Session.banks()`, `Session.set_strip_view()`.

## FX units, sends, buses and patch (2026-10-13, editor-verified)
Writers: `scripts/sessionmaker/fx.py`, `sends.py`, `buses.py`, `patch.py`; the session maker drives them through
`scripts/sessionmaker/options.py`. Each module's docstring holds its full field map. The longer research write-ups
behind them are not published.
- **Routes** are 4 raw bytes in a float slot: `00 <side> <index> <type>` (00 00 00 00 = none). Types: 01 input,
  05 aux, 06 group, 07 right side of a stereo bus, 0e FX unit, 10 matrix, 18 Spice Rack, 1b INTERNAL inputs,
  1c + k input sockets of I/O port k, 4d INTERNAL outputs, 4e + k output sockets of port k.
- **FX unit**: section 201 record in the "FX" group (type 0e; +41 width 2, +42 i32 preset index, +84 EngineChannel),
  section 211 object 0x0e00 | k holding the section 219 library record renamed, live byte +57 = 1, (f0,0) after
  (05,0), (ff,0) = 1.0 (the editor clears it to 0 on load). Inputs (00,0) L / (00,1) R name the source (aux 05,
  its right side 07, an input 01). The feeding aux has (0e,fe,0) = `00 <side> k 0e` and, mono into both sides,
  (0e,e8,0) = 0.0. A return is an input whose (01,00,0) = `00 00 k 0e`. DSP: reverbs 128-158 (Quantum) / 64-94 (SD),
  others 0-26 then 64, 66 (Quantum; Q112 stops at 26) / 0-30 (SD), 16 + 16 per session (16 + 14 on Q112).
- **Aux sends** (input module 02, band = aux internal index): 01 level dB (-150 off), 02 on, 03 pan (stereo aux),
  04 pre/post (0 post, 1 pre, 2 pre-mute, 3 mid-EQ/dyn, 4 pre-EQ/dyn, 5 pre-processing). Group assign: module 03
  param 09, band = group internal index. Header 0x5c = master group band.
- **Bus masters** (05 aux, 06 group, 07 right side; L and R linked by the 201 record's BussID at +54, R named
  "<name> R"): module 0c 21 fader, 22 mute, 0f link pans (0 off, 1 on, 2 reversed; the editor rewrites send pans
  from it); module 0e fe output route = one of its sockets. Output socket (module 12) (00,0) = its source bus. The
  editor does not mirror L to R, so both sides are written.
- **Bus layout**: header u16 0x36/0x38 mono/stereo auxes, 0x46/0x48/0x4a groups. Section 201 aux, group and 07
  records in surface order; per-aux and per-group slots in module 02/03/21 of every input and bus, banded by internal
  index. Budget per console (mono equivalents, stereo 2): Q112 26, Q225 38, Q338 66, Q5 130, Q7 130, Q852 194,
  SD5 124, SD5CS 58, SD7 124, SD8 50, SD9 50, SD10 66, SD11 26, SD12 38. The editor keeps budget + 4 and drops
  (default session) from budget + 5.
- **Input patch**: input module 01 (00,0) main, (00,1) alt (none on a stereo channel), (0e,0) alt in use. A stereo
  channel names its left socket; the right side is the next socket. Socket objects (module 11): 86 gain dB
  (-20..+60; +10..+60 on D-Rack, D2-Rack and the SD9/SD11 Local I/O), 83 48V, 89 pad. Gain and 48V belong to the
  socket.
- **I/O devices**: section 246 = `f6 00 | u16 10500 | 50 x 210-byte records`; record k owns input sockets 1c + k and
  output sockets 4e + k; +0 device type (02 SD Rack, 04 D-Rack, 07 D2-Rack, 0b MQ-Rack, 19 Std MADI, 21 MADI 64...).

