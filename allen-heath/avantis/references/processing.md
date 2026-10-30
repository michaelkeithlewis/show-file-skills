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
