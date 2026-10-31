# Avantis processing sections

Compare `allen-heath/dlive/references/format-processing.md`.

## Bridge-5 (firmware 2.x)

Parameter based. The input and bus processing sections (preamp model, gate, HPF, LPF, PEQ, GEQ, delay,
stereo image, direct out, trim) have the same length and layout as on dLive and copy across byte for byte.
DEEP models (preamp, compressor, gate) carry over because the sections match.

Exception: the compressor is 90 bytes on Bridge-5 and 127 on dLive (map below).

## Bridge-4 (firmware 1.x): filter coefficients

Bridge-4 stores each filter as biquad coefficients plus the parameter record the console shows. A writer
has to compute the coefficients itself.

- Sample rate 96 kHz.
- One biquad = 20 bytes: `b0, b1, b2, -a1, -a2` as big-endian signed 32-bit fixed point with 28 fraction
  bits (value x 2^28, clamped to -8 .. 8).
- Frequency code to Hz (fitted against console output): `f = 3.990373 x 2^(code / 4606.26)`.
  The `allen-heath/dlive/` docs use `4 x 2^(u / 4608)`; both agree within the display precision.
- Q code to Q (fitted, piecewise log-linear between these points, steps under 300 codes snap down):

```
code  0     1077  1477  1985  2430  3299  3328  3615  3919  4126  4507  4651  4882  5143  5377  5884  5976  6144
Q     .2776 .3874 .4279 .4772 .5373 .6479 .7220 .7880 .8684 .9657 1.0872 1.3057 1.4505 1.7425 2.1785 2.6146 3.3502 3.6310
```

  Above 6144: `Q = 3.631 x 2^((code - 6144) / 1200)`.
- Bell: RBJ peaking EQ with the bandwidth term corrected by `tan(w/2) / (w/2)`.
- Shelves: first-order shelves with the corner moved by a factor of 3.04 (LF: f x 3.04, HF: f / 3.04).
  Fitted, matches the console to 1 or 2 LSB.

### Section layouts, Bridge-4 vs dLive / Bridge-5

| Section | Bridge-4 | dLive / Bridge-5 |
|---|---|---|
| Parametric EQ | 118 bytes: `[3]`, 4 bands x (20-byte biquad + 9-byte band record), `[0]` | `[4]`, 4 x 9-byte band record, `[0]` |
| Highpass Filter | 45 bytes: `[2]`, 2 biquads, `u16 freq code`, slope, enable | `[3]`, `u16 freq code`, slope, enable |
| Lowpass Filter | 31 bytes: `[3]`, 1 biquad, 10-byte record | `[4]`, 10-byte record |
| SCF Gate | 63 bytes, record at 21..30 and 50..63 | `[4]` + the same 22 bytes |
| Graphic EQ | 1089 bytes (619 on older shows) | 169 bytes |
| Compressor | 119 bytes | 127 bytes (Bridge-5: 90) |
| Digital Attenuator (trim) | 7 bytes | 5 bytes |

PEQ band record (9 bytes, same on all): gain s16/256 dB, u16 freq code, u16 Q code, type
(0 bell, 1 LF shelf, 2 HF shelf, 3 lowpass, 4 highpass), 2 more bytes.

HPF slopes on Bridge-4: 0 = 12 dB (one 2nd-order section plus a near-flat second section),
1 = 18 dB (1st order + 2nd order Q 1), 2 = 24 dB (Butterworth, Q 0.5412 and 1.3066). The dLive slopes
3 (18 dB Bessel) and 5 (6 dB) do not exist on Avantis; map them to 12 dB.

Graphic EQ, Bridge-4: 28 bands x 22 bytes from byte 1 (2-byte gain, then a biquad; gain is u16 with
0x8000 = 0 dB, /256 dB), bytes 617-618 a flag (dLive bytes 57-58; meaning unknown, 4 on groups),
bytes 619-726 twelve 9-byte PEQ records (dLive 59-166) with their biquads from byte 727 (20 bytes each),
bytes 1087-1088 = dLive bytes 167-168. Band frequency and Q come from inverting the template's own
coefficients; only the gain changes.

### Compressor byte map

| dLive (127) | Bridge-4 (119) | Bridge-5 (90) |
|---|---|---|
| 0..39 | 1..39 (byte 0 not copied) | 0..39 |
| 41..42 | 40..41 | (inside the next row) |
| 41..66 | | 40..65 |
| 105..113 (side chain filter) | 77..85 | |
| 114..126 (side chain filter) | 106..118 | |
| 107..108, 116..117 (CompStortion only) | | 70..71, 79..80 |

Bus compressor dLive bytes 44-49 and Bridge-4 bytes 42-77 have no counterpart. CompStortion's own
controls (dLive 57-69) do not fit Bridge-4.

## Models (byte 1, same IDs on Avantis and dLive)

- Compressor: 0 Manual Peak, 1 Manual RMS, 2 Opto, 3 16T, 4 16VU, 5 Ducker, 6 Peak Limiter 76, 7 Mighty,
  8 OptTronik, 9 Bus Compressor, 10 CompStortion. "Ducker Slow" is not a model, only different times.
  CompStortion needs Avantis FW 2.0; on a Bridge-4 target set Manual RMS.
- Gate: 0 Gate, 1 Ducker, 2 Dual Expander, 3 Source Expander.
- Preamp model: 0 none, 1 Dual Stage, 2 Tube Stage.

## Trim

`Digital Attenuator Input Channel NN`: bytes 1-2 trim s16/256 dB, byte 3 polarity. 5 bytes on dLive and
Bridge-5, 7 bytes on Bridge-4 (same positions assumed, unconfirmed).

## More processing detail (markcarlberg, pull request #2)

From Avantis Director V1.30 and V2.01 saves. Proof in brackets: save-proven, seen in every file (never moved
alone), or unconfirmed. Offsets count from the byte after the label's NUL; byte 0 is the version. Differences
from the text above are listed under What we don't know in `../README.md`.

### Input strip blocks

| Block (input) | Bytes B4 / B5 | Layout | Proof |
|---|---|---|---|
| `Digital Attenuator Input Channel NN` | 7 / 5 | [1..2] trim s16/256 (-24 to +24), [3] polarity 1 inverted; B4 [5] 00 or 7F, unknown | save-proven |
| `Delay, Input Channel NN` | 4 | [1..2] samples at 96 kHz, [3] 1 bypassed; default `01 00 00 00` | save-proven |
| `Highpass Filter Input Channel NN` | 45 / 5 | B5 `[03][u16 freq][slope][switch]`; slope 0, 1, 2 = 12, 18, 24 dB/oct, 3 seen twice; switch 1 = out | frequency and slopes 0-2 save-proven; switch seen |
| `Lowpass Filter Input Channel NN` | 31 / 11 | a PEQ band's shape, then the switch, 1 out; default 20 kHz is `DD 2E` | save-proven |
| `Gate side chain source, Input Channel NN` | 3 | `[01][kind][n - 1]` | save-proven |
| `Compressor side chain source, <strip>` | 3 | `[01][kind][n - 1]` | save-proven |
| `Stereo Image Input Channel NN` | 4 | [0] 01, [1] 00, [2] width (straight percent), [3] mode 0-7 | save-proven |
| `Insert 1/2, Input Channel NN` | 3 | `[02][bypass][00]`: 00 in, 01 out (dLive Director V2.11 shows "Insert Bypassed" on 01; its own assigns save 00), the same as `../../dlive/references/format-processing.md` | save-proven |
| `Direct Output, Input Channel NN` | 3 | `[01][s16 level]`: a direct-out trim, not a tap point | seen in every file |

- **Stereo pairs:** `Show/InputConfig/InputConfig.dat`, `1`, then one line per pair 1/2 to 95/96, `0` mono,
  `1` stereo. Pairing also sets main section +7 to 0 on both halves (`mixer.md`). After pairing, every block of
  both halves matches except the direct output and the two side chain sources, which name the strip itself.
  The file always holds 96 inputs; V2.01 outlines 65-96 red past a 64-input desk. [save-proven]
- **Stereo image modes:** 0 L/R, 1 R/L, 2 L-Pol/R, 3 R-Pol/L, 4 Mono, 5 L/L, 6 R/R, 7 M/S. Both halves hold the
  same. No mix has a `Stereo Image` block. [0 and 7 save-proven; 1 seen; others by menu order only]
- **Processing order:** `Show/ProcessingOrdering/InputProcessingOrdering.dat`, `1` then `true`/`false` for
  inputs 1-96. `true` (default) is PEQ before compressor, `false` compressor before PEQ. The "Global" control
  rewrites inputs 1-64. The gate always runs before both. [save-proven]

### PEQ fields

- Bridge-4 band layout: `[5 x s32 biquad][s16 gain/256][u16 freq][width][fraction][type][00 00]` at
  1 + 29(k - 1), then [117] bypass (1 = out; a bypassed EQ stores flat coefficients). [save-proven]
- Files hold LF shelf and high pass only on band 1, HF shelf and low pass only on band 4. [seen in every file]
- Width codes 0-24, 0 the widest (1.5 oct), 13 the default (0.6 oct), 24 the narrowest (labelled 1/9 oct).
  Avantis code n is SQ code n + 1. [save-proven]
- Default: four bells at 63, 200, 2500, 10000 Hz (`47 97`, `65 97`, `A7 2E`, `CB 2E`), gain 0, width `0D 00`.
  [save-proven]

### Bridge-4 filters, more

- HPF slope 3 looks like a third-order Bessel. Coefficients describe the filter even when it is switched out.
  [slopes 0-2 save-proven; slope 3 unconfirmed]
- Key filter band pass: both biquads are the same second-order band pass at Q 2.9, with no width control.
  Switched out, each key filter biquad is a flat 0 dB bell at Q 0.7287706. [fitted from saved biquads at one
  frequency]

### Gate (19 bytes, both formats)

| Bytes | Field |
|---|---|
| [1] | model: 0 Gate, 1 Ducker (and Ducker Slow), 2 Dual Expander, 3 Source Expander |
| [2..3] | threshold s16/256 (-72 to +12) |
| [4..5] | Source Expander threshold (also the Dual Expander's first threshold, unconfirmed) |
| [8..9] | depth s16/256 (0 to 60) |
| [10..11] | hold, time law |
| [13..14] | release, time law |
| [15..16] | attack, time law |
| [17] | Source Expander speed: 00 Slow, 01 Medium, 02 Fast (library loads 02) |
| [18] | in switch |

Threshold, depth and times save-proven, the Ducker's times and depth save-proven, Source Expander fields and
speed seen in every file. Changing the model loads that model's `[Gate]` library preset into [1..17]. Gate
default `03 00 DC 00 DC 00 CC 00 14 00 7A 8E 00 70 B4 2F 28 02 00`. Time law:
`raw = 65535 x (log10(seconds) + 6) / 11`, as on the SQ.

### Compressor per-model fields (Bridge-4 offsets)

[1] model, [2] in switch.

| Model | Fields | Proof |
|---|---|---|
| Manual RMS / Peak | [8..9] threshold (-46 to +18), [10..11] attack, [12..13] release (time law), [15] ratio code (the SQ's 41 codes, `../../sq/references/FORMAT.md`), [16..17] make-up, [18] soft knee. Manual Peak differs only in the model byte and attack default | save-proven; Peak seen |
| Parallel path (every model) | [7] 1 on, [5..6] dry level s16/256 (`80 01` none); the desk adds dry at that level to the compressed signal | save-proven |
| 16T, 16VU | [8..9] threshold, [16..17] gain, [15] ratio code 00-28, 16T [18] knee | save-proven at the ends |
| Ducker | [8..9] threshold, [10..11] attack, [12..13] release, [23] depth (0-60), [25..26] hold | save-proven at the ends |
| Opto | threshold, ratio code and gain at 16T's bytes (1.2:1 at code 0, 10:1 at 40); [19] attack (02 slow, 01 medium, 00 fast), [20] recovery (00 fast to 02 slow), [21] burn, [22] transient | save-proven at the ends |
| Peak Limiter 76 | [27] ratio (01 4:1, 04 20:1; 02 8:1 and 03 12:1 by order only), [28..29] attack, [30..31] release (knobs 1-7, not the time law), [32] unit, [33..34] input, [35..36] output s16/256; [8..9] always -6 dB | save-proven at the ends |
| Mighty | [16..17] output, [37] detector (00 average, 01 peak), [38..39] threshold, [40..41] release (not the time law); dial and stored dB disagree at the low ends | save-proven at the ends |
| OptTronik | [32] compress/limit, [43] emphasis (`16` flat, `1C` 80 Hz, `1F` 80 Hz + 5 kHz), [44] unit A/B, [46] gain, [48] peak reduction (0-100); its emphasis filter lives in the key filter bytes [57..115] | save-proven; emphasis filter not decoded |
| Bus | [16..17] make-up (-5 to +15), [50] threshold as (dB + 15) x 4, [52] attack step 0-5, [54] release step 0-4 (4 auto), [56] ratio step 0-3 | save-proven bytes; steps held as steps |

- **Model switch:** Director loads the model's factory preset into the model byte, [8..23], [25..41], [43],
  [44], [46], [48], [50], [52], [54], [56], and leaves [2], [5..7] and everything else. A linked pair's right
  half takes only the moved controls. [save-proven]
- **Bridge-5:** [1..56] unchanged, the two key-filter biquads gone, and eleven bytes added at [57]
  (`00 00 32 00 32 00 00 00 00 00 00` by default), the model 10 controls. Version byte `06` becomes `08`.
  [save-proven]

### Key source and key filter

Source block `[01][kind][n - 1]`: 01 input, 02 mono group, 04 mono aux, 05 stereo aux, 08 main by label number
(LR `08 00`, Main 3 `08 02`) [save-proven]; 03 stereo group, 09 mono matrix, 0A stereo matrix [seen].
Self-keyed is the block naming its own strip. Gates can key from mixes.

| Gate (`SCF Gate`) / compressor | Field |
|---|---|
| [1..20] / [57..76] | high pass biquad |
| [23..24] / [79..80] | high pass frequency (default `4197`, 50 Hz) |
| [27] / [83] | type: 04 high pass, 06 LF shelf (at exactly -9 dB) |
| [30..49] / [86..105] | low pass biquad |
| [52..53] / [108..109] | low pass frequency (default `DD2E`, 20 kHz) |
| [59] / [115] | 1 out, 0 in |
| [60] / [116] | mode: 00 high and low pass, 01 band pass |
| [61..62] / [117..118] | band pass frequency (default `6597`, 200 Hz) |

All save-proven on Bridge-4. High and low pass in: 12 dB/oct each, under one switch.

### Mix graphic EQ and NEQ12

`Graphic EQ, <strip>` a leg, 28 bands at the ISO third-octave centres 31.5 Hz to 16 kHz, gain u16
`0x8000 + 256 x dB`:

| | Bridge-4, 1,089 bytes (v2) | Bridge-5, 169 bytes |
|---|---|---|
| band k gain | [1 + 22k] | [1 + 2k] |
| band k biquad | [3 + 22k] | none |
| GEQ out (1) | [617] | [57] |
| slot: 0 Constant-Q, 1 Proportional-Q, 2 Dig-GEQ, 3 Hybrid, 4 NEQ12 | [618] | [58] |
| NEQ12, 12 bands x 9 | [619] | [59] |
| NEQ12 biquads, 18 x 20 | [727] | none |
| NEQ12 high and low pass slope codes | [1087], [1088] | [167], [168] |

Centres and gain law proven by the biquads; switch seen in every file, not moved alone. Slot codes 0-3 are the graphic's type, in the order of dLive Director's "NEQ Type" list, with the same 28 band gains on the same law (proven: four stored shows, one group set to each type in turn, each read back as its code). A Bridge-3
GEQ is 619 bytes (v1) with the Bridge-4 gain, biquad, switch and slot offsets and no NEQ12.

- **NEQ12** (a mix's second parametric EQ, in its graphic slot): band k's nine bytes are a PEQ band's fields
  without its biquad: s16 gain in 1/256 dB, u16 frequency, u16 width (high byte the PEQ's width code), type
  (0 bell, 1 LF shelf, 2 HF shelf, 3 low pass, 4 high pass), `00 00`. Band 1 is the only high pass seen, band
  12 the only low pass. The block's last two bytes are the high and low pass slope codes. Bridge-4 holds
  eighteen biquads at [727]: four for band 1, one each for bands 2-11, four for band 12. Counting the biquads a
  code fills and measuring their roll-off: high pass code 0 = 12 dB/oct, 4 = 48; low pass 0 = 12, 1 = 24,
  2 = 48. [proven from the saved biquads, four real shows] Factory band 1 is a 35 Hz high pass at code 4; the
  other defaults are bells at 63, 120, 200, 280, 600, 1600, 2500, 5000, 7000, 10000, 13000 Hz, width code 13.
  [seen in every file]
- **Mix trim and polarity:** `Digital Attenuator, <strip>` per leg, an input's layout; `Mix Delay, <strip>` an
  input delay's. [delay save-proven; trim and polarity seen]

### Bridge-5 (V2.01) block changes

- Every block that held biquads keeps the same fields in the same order without them, version byte one up:
  HPF 45 to 5, LPF and talkback HPF 31 to 11, PEQ 118 to 38, `SCF Gate` 63 to 23, GEQ 1,089 to 169,
  compressor 119 to 90 (version two up), `Digital Attenuator` 7 to 5. [proven on 1,862 blocks]
- Added: `Ultra FX Manager 01-08`, `Ultra FX Send Mixer`, `Ultra FX Return Mixer` (16 returns laid out as
  inputs), Ultra FX send and return name managers, `Send Source Select, UFX 01-08 Left/Right`,
  `FX Global Key Scale`, per-rack dynamics, SCF, PEQ and side chain blocks. `Input Mixer` and
  `FX Return Mixer` move to version 2, 40 bytes a record longer. `Channel Ganging` 481 to 513 (30-byte to
  32-byte records). `FX Manager` 171 to 173 (`00 64` level added). [save-proven]
- On recalling a Bridge-4 show, Director V2.01 cleared stale bytes after name NULs, rewrote
  `VirtualSoundCheck.dat` `1\n1\n` to `1\n0\n`, and unpatched a few inputs (cause unknown). [save-proven]
