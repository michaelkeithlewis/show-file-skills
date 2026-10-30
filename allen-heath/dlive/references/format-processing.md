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
- **Distressor ratio**: byte 58 is the ratio switch, the button Director lights: 0-7 = 2:1, 3:1, 4:1, 6:1, 10:1, 20:1,
  Smash, Brit (Director's switch list, and a fresh Distressor lights 2:1). The generic ratio index (bytes 14-15) is not
  used by this model: it reads 20 on 227 of 228 Distressor sections in the live scenes of real shows, while byte 58 runs 0-7. `dlive_proc.py`
  prints the label from byte 58. Smash and Brit have no plain ratio.
- **Model switch**: when a compressor becomes another model, Director writes that model's defaults. See "Compressor model
  defaults" below.
- **Digital Attenuator**: `01 | trim gain | phase | mute`. Director 2.11 adds two trailing zero bytes (reported raw).
- **Delay**: `01 | samples | bypass`. Samples are at 96 kHz. The FPGA maximum 0x7fff is 341.3 ms.
- **Insert 1 / Insert 2**: `02 | bypass | level mode`. Byte 1 is the BYPASS flag: 1 = insert OUT, 0 = IN (the default). Verified 2026-10-23 in Director 2.12: cInsertNetObject::GetStatus writes the field cInsertNetObject::InsertBypass sets.
- **Preamp**: the MixRack socket section `StageBox Analogue Input, Number NN` is `01 | gain (whole dB) | pad | 48V`.
  The Channel Mapper's active source picks the socket. The default gain is 27 dB.
- **Stereo pairs**: `Show/InputConfig/InputConfig.dat`, plus the mono flag in byte 7 of each input channel section
  (see `format-processing-surface.md`).

## Level reference

dLive levels sit on a nominal 0 dB scale with full scale at +18 dB (dLive thresholds run up to +18). Consoles
that work in dBFS need every dLive threshold 18 dB lower.

## Compressor model defaults

Director runs `cCompressorSystemFunctions::Set_<Model>_ResetValues` when a compressor changes model. The same values are in
`ApplyDefaultsToData` @0x100e6e1d0. Each line below is bytes 3-68 of the 127-byte section for model 0-10, in the model
order above. Outside the fields an engineer turns, about 95,000 sections in real shows hold these values. No untouched
Mighty or Distressor block exists in those shows, so those two come from Director's code only.

```
0  00008001000000443f7a8e00140000000000000000007a8e00ba2d849f0000000000000000006d5c0000000000000000000000000000000000320032000000000000
1  00008001000000553f7a8e00140000000000000000007a8e00ba2d849f0000000000000000006d5c0000000000000000000000000000000000320032000000000000
2  00008001000000553f84a200190000000200000100007a8e00ba2d849f0000000000000000006d5c0000000000000000000000000000000000320032000000000000
3  0000800100000049eb770400140000000000000000007a8e00ba2d849f0000000000000000006d5c0000000000000000000000000000000000320032000000000000
4  000080010000003ed0721c00140000000000000000007a8e00ba2d849f0000000000000000006d5c0000000000000000000000000000000000320032000000000000
5  0000800100f900683272d700000000000000000014007a8700ba2d849f0000000000000000006d5c0000000000000000000000000000000000320032000000000000
6  0000800100fa00443f7a8e00140000000000000000007a8e01b58d92a30001fa0006000000006d5c0000000000000000000000000000000000320032000000000000
7  00008001000000315a84a200140000000000000000007a8e00ba2d849f000000000000000000702a0000000000000000000000000000000000320032000000000000
8  0000800100f200553f84a2001e0000000000000000007a8e00ba2d849f0000000000000000006d5c001600000a001e00000000000000000000320032000000000000
9  0000800100fa00443f7a8e00140000000000000000007a8e00ba2d849f0000000000000000006d5c0000000000000000560005000000020000320032000000000000
10 0000800100fa00443f7a8e00140000000000000000007a8e00ba2d849f0000000000000000006d5c0000000000000000000000000000000000320032000000000000
```

To switch a section to a new model:

1. Write the model byte (byte 1).
2. Write the new model's own block from the line above. Own blocks: Opto 19-22, Ducker 23-26, Amp76 27-37, Mighty 38-42,
   LevelAmp 33 and 43-49, Bus 50-57, Distressor 58-68. The manual models, 16T and 16VU have none.
3. Keep a generic field (threshold, attack, release, ratio, knee, makeup) when the old model read it the same way.
   Write the new model's default when it did not. A ducker does not share threshold or time laws with the others, and
   the ratio index only carries over between models that use the same ratio table.
4. Clamp makeup to the new model's range.
5. Leave fields the new model does not read, In/Out, the parallel path and the side chain as they are.

## Raw or unconfirmed

- Preamp Model section (18 bytes): only the model byte is named.
- PEQ types 5-9.
- Amp76 attack and release go through a model curve; plain `UWORDToTime` gives 34 s on one real channel. The
  ratio-state labels 4/8/12/20/all are assumed from 1176 convention. The Amp76 threshold comes from a per-state
  table (-6, -6, -4.5, -3, -1 dB), not from the stored threshold field.
- Distressor attack, release and distortion; 16T and Opto states; LevelAmp and Bus fields.
- The polarity of the `peq_before_comp` flag (every channel reads `true`).
- An unpatched insert reads 0 (in) as well, so check the insert return patch before treating 0 as a live insert.
- I/O-port and DX preamp socket mapping (shown as `?`). An I/O port that reads the 27 dB default on every socket
  is probably a network card without remote preamps.

## Values to read off Director to close the gaps

1. An Amp76 channel: the ratio button, plus the attack and release knob positions next to the raw values.
2. A Distressor channel: attack and release next to the raw values.
3. A non-default PEQ type 5-9.
