# dLive input processing: section layouts and units

Decoded from dLive Director V2.12 with the symbol table and objdump. Ground truth: a FOH template with real
processing, a show that carried that processing by channel number, and the same show reset to defaults.

Tool: `scripts/dlive_proc.py dump <show.tar.gz> [--scene 65535] [--ch 1-64] [--raw]` prints JSON per channel.
`table` prints one line per channel.

Section labels zero-pad the channel number (`Input Channel 01`). A `%d` regex misses channels 1-99.

## Units (all values big-endian)

| Quantity | Encoding | Evidence |
| --- | --- | --- |
| Gain | s16 / 256 dB; 0x8001 = -inf | `UWORDToGain` @0x1001039a0; `GainToString` multiplies by 0.00390625 |
| Frequency | 4 * 2^(u/4608) Hz | `UWORDToFreq` @0x1001103e0 |
| Time | 10^((u-1)*11/65536) us; 0 = 0 | `UWORDToTime` @0x100110440 |
| PEQ width | high byte 0-24 indexes a Q table (Q 0.92 to 12.02, 1.5 to 0.12 oct); default 0x0d00 = Q 2.388 (0.6 oct) | table @0x102526ef0 |

Time defaults land on round values: ducker 3 ms / 100 ms, comp release 500 ms. 16VU stores 0.4998 / 79.98 ms
against a fixed 0.5 / 80.

## Section layouts

- **Highpass Filter**: `03 | freq | type | bypass`. Type map @0x1029aeaa0: 0 = 12 dB, 1 = 18 dB, 2 = 24 dB
  Butterworth, 3 = 18 dB Bessel, 5 = 6 dB. `MIDISetHPFBypassed` writes the bypass field.
- **Parametric EQ**: `04 | 4 x [gain s16, freq, width, type, qtype, band bypass] | bypass`. Band types
  (`cEQTypeSwitchDriver` @0x1008be3c0 / 0x1008be4a0): 0 bell, 1 LF shelf, 2 HF shelf, 3 LPF, 4 HPF. A non-zero
  qtype means constant-Q bell.
- **Lowpass Filter**: the PEQ layout with one band.
- **Gate** (19 bytes): type, threshold, upper/lower threshold, depth, hold, release type, release, attack, timing,
  enable. Field owners come from the `cGate::Set*` methods. Types: 0 gate, 1 ducker, 2 dual-threshold expander,
  3 source expander.
- **SCF Gate**: `04 | HPF band | LPF band | bypass | bandpass on | bp freq`.
- **Compressor** (127 bytes): model, enable, parallel wet/dry, threshold, attack, release, ratio index, makeup,
  knee, then per-model blocks. The side-chain filter body starts at byte 105 with no version byte. Model enum
  @0x100e70820: 0 manual peak, 1 manual RMS, 2 opto, 3 16T, 4 16VU, 5 ducker, 6 Amp76, 7 Mighty, 8 LevelAmp,
  9 Bus, 10 Distressor. Ratio tables: manual @0x106d677f0 (index 20 = 3:1), 16T @0x106d67b80, 16VU @0x106d67e10,
  Opto @0x106d680a0. The tool reports only the generic fields that each model's `SendAll_*` driver reads. Unused
  fields go under `stored_unused`.
- **Digital Attenuator**: `01 | trim gain | phase | mute`. Director 2.11 adds two trailing zero bytes (reported raw).
- **Delay**: `01 | samples | bypass`. Samples are at 96 kHz. The FPGA maximum 0x7fff is 341.3 ms.
- **Insert 1 / Insert 2**: `02 | bypass | level mode`.
- **Preamp**: the MixRack socket section `StageBox Analogue Input, Number NN` is `01 | gain (whole dB) | pad | 48V`.
  The Channel Mapper's active source picks the socket. The default gain is 27 dB.
- **Stereo pairs**: `Show/InputConfig/InputConfig.dat`, plus the mono flag in byte 7 of each input channel section
  (see `format-processing-surface.md`).

## Level reference

dLive levels sit on a nominal 0 dB scale with full scale at +18 dB (dLive thresholds run up to +18). Consoles
that work in dBFS need every dLive threshold 18 dB lower.

## Raw or unconfirmed

- Preamp Model section (18 bytes): only the model byte is named.
- PEQ types 5-9.
- Amp76 attack and release go through a model curve; plain `UWORDToTime` gives 34 s on one real channel. The
  ratio-state labels 4/8/12/20/all are assumed from 1176 convention. The Amp76 threshold comes from a per-state
  table (-6, -6, -4.5, -3, -1 dB), not from the stored threshold field.
- Distressor attack, release, ratio state and distortion; 16T and Opto states; LevelAmp and Bus fields.
- The polarity of the `peq_before_comp` flag (every channel reads `true`).
- The insert bypass sense: unpatched inserts read 0, so 0 does not prove an insert is in use.
- I/O-port and DX preamp socket mapping (shown as `?`). An I/O port that reads the 27 dB default on every socket
  is probably a network card without remote preamps.

## Values to read off Director to close the gaps

1. An Amp76 channel: the ratio button, plus the attack and release knob positions next to the raw values.
2. A Distressor channel: ratio, attack and release next to the raw values.
3. A non-default PEQ type 5-9.
