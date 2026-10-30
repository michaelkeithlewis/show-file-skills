# Premium Rack plug-in words

How the DM7 family and RIVAGE PM store Premium Rack plug-ins and their parameter words, contributed by markcarlberg
(pull request #2). Nothing on this page is used by `scripts/yamaha_tool.py`. FORMAT.md 4.9 has the tested library
recall.

Every line says how it was found:

- **(save)**: one control changed in the editor, saved, and the stored word compared with the display.
- **(display)**: the editor's display read against the stored words of existing files, in RIVAGE PM Editor V7 (PM5,
  DSP-RX, offline). No control was moved on its own.
- **(files)**: the same in every file at hand, never moved by a save on its own.

Untested readings are under What we don't know in `../dm7/README.md` and `../rivage-pm/README.md`.

## Where the racks live

| Desk | Path | Proof |
| --- | --- | --- |
| DM7, DM5 | mix file section `PremiumRack`: `PremiumRack2[g]/PlugIn[16]`; 4 groups in a `.dm7f`, 6 in a `.dmxf` (every Premium table grew from 4 to 6) | files |
| RIVAGE PM | `EN00/prem:PremiumRack2[32]/PlugIn[16]` | files |
| both | input patch `Mixing/PremiumRack[g]/Slot[16]/InputPort[2]/Patch.Source`, key-in `/KeyInInput[2]/Patch.Source` (RIVAGE PM: `EN00/mix:PremiumRack/...`) | files |

| Field | Encoding | Proof |
| --- | --- | --- |
| `PluginName` | text 17: the library name plus ` St` or ` Dual` (`U76 St`, `Opt-2A Dual`) | save, for a mount |
| `LR[h].LibraryName` | per half, the library name (`Opt-2A`) | save, for a mount |
| `SlotSize` | DSP units used; 0 on a unit a plug-in spans | save, for a mount |
| `ItemNum` | 1 stereo, 2 dual | save, for a mount |
| `LR[h].Bypass`, `LR[h].TempoAssign` | per half | save, for a mount |
| `LR[h]/Parameter[64].Value` | signed 32-bit words, layouts below | save or display, per plug-in |

- A plug-in that spans several DSP units is mounted on its first slot: Opt-2A Dual on a13 is `PlugIn[12]`, `SlotSize`
  4, `ItemNum` 2. (save, DM Editor 2.0)
- A Dual is two mono halves with word sets in `LR[0]` and `LR[1]`, each with its own `Bypass`. A stereo unit uses
  `LR[0]`. (files)
- A Premium slot's `Mixing/PremiumRack[g]/Slot[s]/InputPort[h]/Patch.Source` holds the strip's insert send (0x13C0000F
  for ch 16, slot A). (save, DM Editor 2.0)
- Display page `Mixing/PremiumRackDisplay`. Parameter safe `SET/PremiumRack[g]/PlugIn[16]/LR[2]/RecallSafe`. (files)

## U76 (save)

St and Dual, one word set per half. Pinned by controlled saves with one half's knobs fully up and the other's down.

| Word | Control | Law | Points (word, display) |
| --- | --- | --- | --- |
| 0 | INPUT | dB = (w - 560) / 10 | 381 -17.9, 429 -13.1, 210 -35.0 |
| 1 | OUTPUT | dB = (w - 400) / 10 | 180 -22.0, 270 -13.0 |
| 2 | ATTACK | 0 to 250 over the 1 to 7 dial, 250 the fastest; display about 5.50 - 0.0216 w ms | 0 5.50, 93 3.51, 122 2.87, 250 0.10 |
| 3 | RELEASE | 0 to 250 over the 1 to 7 dial, 250 the fastest | 250 56.4 ms, 133 564.4 ms |
| 4 | RATIO | index 0 to 4: 4, 8, 12, 20, ALL | 1 8, 2 12, 4 ALL |
| 5 | METER | index OFF, +4, +8, GR | 3 GR |

## Opt-2A (save)

St and Dual. Pinned the same way as the U76.

| Word | Control | Law | Points |
| --- | --- | --- | --- |
| 0 | PEAK REDUCTION | 0 to 476 over the 0 to 100 knob | 0 -48.0 dB, 220 21.4, 270 26.7, 350 35.3, 476 48.0 |
| 1 | RATIO | continuous, 0 to 200, ratio = 2 x 5^(w/200) | 0 2.00, 35 2.65, 75 3.66, 100 4.50, 200 10.00 |
| 2 | GAIN | 0 to 368 over the 0 to 100 knob | 0 -56.0 dB, 60 0.0, 80 3.7, 120 9.4, 368 36.7 |
| 3 | METER | 1 is GR | |

## Portico 5033 (display)

Dual, one set per half. Every frequency is a step of 1/48 octave from its band's base: f = base x 2^(w/48). Q steps the
same way from 0.707: Q = 0.707 x 2^(w/48). Gains are in 0.1 dB. LF and HF are shelves. Computed frequencies fall within
about 2 % of the display.

| Words | Band | Base and points |
| --- | --- | --- |
| 0, 1 | TRIM, (0) | |
| 2, 3, 4 | LF freq, gain, on | base about 30 Hz: 52 63 Hz, 68 80 Hz |
| 5, 6, 7, 8 | LMF Q, freq, gain, on | base 50 Hz: 87 175 Hz, 108 236 Hz; Q 72 2.00 |
| 9, 10, 11, 12 | MF Q, freq, gain, on | base about 337 Hz: 40 600 Hz, 64 850 Hz |
| 13, 14, 15 | HMF Q, freq, gain (no switch of its own) | base about 1.78 kHz: 36 3.00 kHz, 84 6.00 kHz; Q 114 3.61 |
| 16, 17, 18 | HF freq, gain, on | base about 2.5 kHz: 88 9.00 kHz, 109 12.0 kHz |

## Portico 5043 (display)

| Word | Control | Law | Points |
| --- | --- | --- | --- |
| 0, 1 | IN, FB | switches | |
| 2 | THRESHOLD | 0.1 dB | -210 -21.0, -350 -35.0 |
| 3 | ATTACK | ms | 40, 20, 45 |
| 4 | RELEASE | about 100 ms + 7.8 ms a step | 7 155, 10 178, 12 194 |
| 5 | RATIO | steps, not linear | 51 2.50, 60 2.80, 69 4.0 |
| 6 | GAIN | 0.1 dB | 40 4.0 |

## Portico 5045 (display)

| Word | Control | Law |
| --- | --- | --- |
| 0 | PROCESS ENGAGE | switch |
| 1 | RMS/PEAK | switch; 1 (lit) is PEAK |
| 2 | TIME CONSTANT | A to F as 0 to 5 |
| 3 | THRESHOLD | 0.1 dB, -42 to -12 |
| 4 | DEPTH | 0.1 dB, 0 to 20 (shown negative) |

## Buss Comp 369 (display)

| Word | Control | Law |
| --- | --- | --- |
| 0 | INPUT ADJUST | 0.1 dB |
| 1 | LINK | switch |
| 2 | METER | switch |
| 3 | COMPRESS | in |
| 4 | RATIO | steps: 1.5, 2, 3, 4, 6 |
| 5 | GAIN | 0.1 dB |
| 6 | RECOVERY | steps: 100, 400, 800, 1500 ms, a1, a2 |
| 7 | THRESHOLD | dBFS = -40 + w/2 |
| 8 | LIMIT | in |
| 9 | ATTACK | 0 fast, 1 slow |
| 10 | LIMIT RECOVERY | steps: 50, 100, 200, 800 ms, a1, a2 |
| 11 | LIMIT THRESHOLD | 22 reads -5.0 dBFS (one point) |

## Rupert EQ773 (display)

St and Dual.

| Word | Control | Law |
| --- | --- | --- |
| 0 | LC FREQ | steps: off, 50, 80, 160, 300 Hz |
| 1 | LF GAIN | 0.1 dB |
| 2 | LF FREQ | steps: off, 35, 60, 110, 220 Hz |
| 3 | MF GAIN | 0.1 dB |
| 4 | MF FREQ | steps: off, 0.36, 0.7, 1.6, 3.2, 4.8, 7.2 kHz |
| 5 | HF GAIN | 0.1 dB, a fixed-frequency shelf |
| 6 | DRIVE | 0.1 |
| 7 | EQL | the EQ in |

## Rupert EQ810 (display, partly read)

- Words 2 and 4: LF and HF frequency steps (LF 33, 56, 95, 160, 270 Hz; HF 3.3, 4.7, 6.8, 10, 15 kHz).
- Words 5 and 8: LF and HF gains as 160 + 0.1 dB steps (133 is -2.7 dB).

## REV-X (RIVAGE PM)

Values typed into each box or stepped with the arrow keys, read off the display, and two controlled saves to pin the
stored index. The factory default (Hall) is `[0, 26, 200, 6, 12, 10, 28, 50, 32, 0, 49, 100]`.

| Word | Control | Law | Proof |
| --- | --- | --- | --- |
| 0 | TYPE | index, 0 Hall | display |
| 1 | REV TIME | index 0 to 69 into units of 27.94/300 s: 3 + i units for i up to 47, then +5 units a step to 57, +10 a step to 67, 68 is 250 units, 69 is 300 (0.279 s at 0, 1.58 s at 14, 2.70 s at 26, 4.66 s at 47, 9.31 s at 57, 18.6 s at 67, 27.9 s at 69) | save |
| 2 | INI. DLY | 0.1 ms | save |
| 3, 4 | HI. RATIO, LO. RATIO | x10 | display |
| 5, 6, 7 | DIFFUSION, ROOM SIZE, DECAY | as shown | display |
| 8 | LO. FREQ | 20 x 2^(i/6) Hz, shown as the 1/6-octave nominal value | save |
| 9 | HPF | 0 Thru, else 20 x 2^(i/6) Hz | save |
| 10 | LPF | 20 x 2^(i/6) Hz | save |
| 11 | MIX BAL | % | display |

## SP2016, Y7, SPX Reverb, SPX Stereo Delay (save)

Two to five controlled saves each in RIVAGE PM Editor 7.2. One 32-bit value per control.

- SP2016: 5 mix, 6 PREDELAY ms, 7 DECAY (w + 20)/100 s (280 = 3.00 s, 513 = 5.33 s), 8 POSITION %, 9 DIFFUSION %, 10
  LOW GAIN w - 8 dB, 11 LOW FREQ 50 x (w + 1) Hz, 12 HIGH GAIN w - 8 dB, 13 HIGH FREQ 1000 + 500 x w Hz. Factory 8, 4,
  8, 6 = 0 dB at 250 Hz, 0 dB at 4.0 kHz.
- Y7: 12 Reverb Time (w + 4)/10 s (1.2 to 5.1 s at five points); 13 Pre Delay 2 ms a step to 40 ms at index 20, 4 ms a
  step to 100 ms at 35, then 8 ms a step (60 at 25, 76 at 29, 220 at 50, 356 at 67, 572 at 94; 67 was predicted before
  its save); 14 Size; 15 RT Damping; 16 Rolloff; 22 Dry/Wet; 23 Lock.
- SPX Reverb: the REV-X layout, with REV TIME (i + 3)/10 s (3.4 s at 31, 4.0 s at 37) and INI. DELAY in 0.1 ms. HPF
  1/12 octave a step, 0 = Thru, 1000 x 2^((w - 68)/12) Hz (31.5 Hz at 8, 63 at 20, 85 at 25). LPF 1/12 octave a step,
  101 = Thru, 1000 x 2^((w - 52)/12) Hz (3.55 kHz at 74, 8 kHz at 88, 11.8 kHz at 95). The display shows the nominal
  1/12-octave values.
- SPX Stereo Delay: 0 and 1 DELAY L and R in 0.1 ms, 2 and 3 FB. GAIN L and R %, 4 HI. RATIO tenths, 5 HPF (0 Thru), 6
  LPF (92 = 10 kHz), 7 SYNC, 8 and 9 NOTE L and R, 10 BPM, 11 MIX BAL.

## MBC4 (save)

Four controlled saves in RIVAGE PM Editor 7.2 (every control moved on its own, all at their lowest, all at their
highest, four ratios past 8:1), each against the untouched half, and a load check of a written unit. The same plug-in
runs on the DM7. Plain signed 32-bit values, one per control.

- Words 0 to 2, the crossovers, each on its own 1/48-octave grid: LOW 20 x 2^(w/48) Hz (0 to 224, 20 to 500 Hz), MID
  1000 x 2^((w - 176)/48) Hz (0 to 336, 80 Hz to 10 kHz), HIGH 1000 x 2^(w/48) Hz (0 to 188, 1 to 15 kHz). Factory 96,
  176, 144 = 80 Hz, 1 kHz, 8 kHz.
- Seven words a band from word 3, low band first: GAIN in 0.1 dB (-180 to 120), THRESH in 0.1 dB (-800 to 0), RATIO 0.1
  a step to 8:1 at 70 then 0.2 a step to 20:1 at 130, ATTACK 0.1 ms a step to 10 ms at 100 then 1 ms a step to 120 ms at
  210, RELEASE w + 5 ms (5 ms to 1 s), the band switched out (1 = out), and a word that stayed 1.
- 31 MAIN in 0.1 dB (-180 to 120), 32 KNEE 0 (HARD) to 4 (SOFT), 33 FLAVOUR 0 VCA or 1 OPTO, 34 stayed 1.

## DynamicEQ4 (save)

RIVAGE PM Editor readouts and two saves; DM Editor read one Q point. A half's words band by band: bands A and D
`[on, shape, F, Q, thr, ratio, mode, ballistics, cue, key]`, bands B and C the same without `shape`; 38 words.

| Control | Law |
| --- | --- |
| F | 1000 x 2^((w - 272) / 48) Hz |
| Q | 5 x 2^(-(w - 24) / 15); DM Editor reads 0.91 at 61 |
| THRESH | (w - 800) / 10 dB |
| RATIO | 50 is 1:1; below 50 (a cut), 1 - 1/ratio = 0.0275 x (50 - w) |
| shape (A, D) | 0 bell, 1 shelf |
| MODE | 1 Above, 0 Below |
| FAST/SLOW/AUTO | 0, 1, 2 |
| KEY IN CUE | 1 on |
| KEY IN EXT | 1 |

## DynamicEQ6 (save)

Nineteen controlled saves in RIVAGE PM Editor 7.2, each read against the display. Six bands, each a low shelf, bell or
high shelf, with static gain, dynamic range, threshold, Above/Below, Auto threshold or Manual attack and release, a
Ratio/Knee preset (Soft, Medium, Hard), an attack/release preset (Fast, Slow, Auto) and a key-in filter. The unit is
`DynamicEQ6 Dual` (5 DSP slots, two halves) or `DynamicEQ6 St`. A stereo channel's right leg plays the second half.

- Packing: each of a half's 64 `Parameter/Value` words holds three 10-bit fields (bits 0 to 9, 10 to 19, 20 to 29);
  slot = 3 x word index + field. Signed fields are two's complement in 10 bits. Fields do not move when values change.
- Bands 4 to 6 repeat bands 1 to 3, 69 slots on.

| | band 1 | band 2 | band 3 | Law |
| --- | --- | --- | --- | --- |
| release | 0 | 25 | 50 | ms |
| attack | 1 | 26 | 45 | ms = 2^(v/75) |
| threshold | 2 | 21 | 46 | dB = -30 + v/10 (signed) |
| key-in freq | 3 | 28 | 53 | as freq |
| freq | 4 | 29 | 48 | Hz = 1000 x 2^((v - 288)/48) |
| range | 5 | 24 | 49 | dB = v/10 (signed) |
| gain | 6 | 31 | 56 | dB = v/10 (signed) |
| Q | 7 | 32 | 51 | Q = 2 x 2^((36 - v)/12) |
| key-in Q | 8 | 27 | 52 | as Q |
| on | 10 | 35 | 54 | 1 on |
| shape | 11 | 30 | 55 | 0 low shelf, 1 bell, 2 high shelf |
| below | 12 | 37 | 62 | 1 Below |
| manual | 16 | 41 | 60 | 1 Manual attack and release |
| A/R preset | 17 | not found | not found | 0 Fast, 1 Slow, 2 Auto |
| ratio/knee | 18 | 43 | 68 | 0 Soft, 1 Medium, 2 Hard |
| auto | 20 | 39 | 64 | 1 Auto |
| dynamics flag | 23 | 42 | 67 | 1 once the range leaves 0 |

Shelf Q sits in slots 165 to 173 (72 = the shelf default, 2.8). Its law is not settled.
