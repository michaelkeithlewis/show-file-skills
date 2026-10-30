# SQ and SQ+ show file format

Format notes for Allen & Heath SQ-5, SQ-6 and SQ-7 (firmware 1.5 and 1.6) and SQ+ (firmware 2.0.3) show
folders. Worked out by markcarlberg from files saved by SQ MixPad 1.6.1, SQ+ MixPad 2.0.3 and an SQ desk on
1.6.3, mostly by changing one control, saving, and comparing.

How each fact was proven is in brackets after it:

- **save-proven**: one control was changed in MixPad or on the desk, saved, and the named bytes were the ones
  that moved.
- **seen in every file**: consistent across many saved files, but never moved alone by a save.
- **unconfirmed**: a reading that fits the files and has not been tested. Treat it as open.

The SQ is not like the Avantis and dLive: a show is a folder of fixed-layout binary images, not a tar of
labelled blocks. Offsets below are little-endian unless they say otherwise.

## Container

- A show is a `SHOW####` folder holding `SHOW.DAT` (512 bytes, the show name in ASCII to the first NUL, no
  checksum), `NVDATA.DAT` (the show's current state) and one `SCENEnnn.DAT` per stored scene, where
  `SCENE000` is scene 1. An SQ USB stick keeps show folders under `AHSQ/SHOWS` and exported scenes in
  `AHSQ/SCENES`; an SQ+ stick keeps them under `SQP-SHW`. [seen in every file]
- Library presets are `LIBnnn.DAT`, 512 bytes: slot at 0x04 (the `nnn`), kind at 0x14 (5 input channel,
  8 FX, 10 input patch), name at 0x170, zlib CRC-32 of 0x14-0x1FB at 0x1FC. Nothing else in the folder lists
  them, and no NVDATA or scene holds a library's name or slot. [seen in every file]
- Every scene and NVDATA image is 128 KiB of fixed layout, and NVDATA is laid out exactly as a scene, every
  section at the same offset. [save-proven]
- The desk and MixPad load a show folder as its NVDATA. A stored scene's content appears only once that scene
  is recalled. [save-proven, checked in MixPad]
- MixPad reloads its working show when its `CurrentShow` folder changes on disk, so writing into that folder
  replaces the open show. [seen in MixPad]

## Header and checksum

| Offset | SQ | SQ+ (firmware 2) |
| --- | --- | --- |
| 0x00-0x03 | 0x00 `A1` scene, `B5` NVDATA [seen in every file] | `A1` in both; 0x01-0x03 `00 00 00` scene, `FF FF FF` NVDATA [save-proven] |
| 0x04-0x05 | scene number from 0, u16; `FFFF` in NVDATA [seen in every file]; 0x08-0x0B varies, not placed | `0D 00 00 00` at 0x04 and `0A 00 00 00` at 0x08 in every file, no scene number [constant in every file, meaning unknown] |
| 0x0C-0x0E | firmware major, minor, patch (`01 06 03` = 1.6.3) [save-proven] | `02 00 03` = 2.0.3, 0x0F `01`; major 2 tells an SQ+ file apart [save-proven] |
| name | 0x14, 16 bytes, cut at NUL; FF in NVDATA [seen in every file] | 0x10, 16 bytes; 00 in NVDATA [save-proven] |
| end, CRC | section 1 sentinel at 0x38; zlib CRC-32 (poly `EDB88320`) of 0x14-0x1FFFB stored at 0x1FFFC [save-proven] | 0x20-0x30 zero, `FF` to 0x203, section 1 at 0x204; the same CRC over 0x204-0x1FFFB, so the name is outside the span [save-proven] |

- Bytes 0x1A-0x1B move across a run of scene stores because MixPad names each new scene "Scene NN" and those
  are the name's digits, not a save counter. [save-proven by a bus config save]

## Sections

The body is 14 sections, each opened by a sentinel `NN A5 A5 A5` (NN = 1-14) at the same offset in every image
of a product line. The body starts 4 bytes after the sentinel; offsets below are body offsets unless they say
otherwise. A strip's stored settings live in both section 2 and section 5: copying one without the other leaves
a strip half one show and half another. [save-proven]

| Section | SQ sentinel | Holds |
| --- | --- | --- |
| 1 | 0x00038 | bus config, stereo pairs, matrix widths, custom layers |
| 2 | 0x00370 | 122 strip blocks x 336 bytes; block n at 0x374 + 336n (SQ+ 0x540 + 336n) |
| 3 | 0x0A394 | 32 DCA records x 24 |
| 4 | 0x0A698 | 32 mute group records x 24 |
| 5 | 0x0A99C | 122 send records x 300, in section 2's order; record s at 0xA9A0 + 300s |
| 6 | 0x13898 | 315 head amp records x 4 |
| 7 | 0x13D88 | 412 output patch records x 4, then a 96-byte table (SQ+ 288 bytes) |
| 8 | 0x1445C | five records x 4 (PAFL Ext In source) |
| 9 | 0x14474 (SQ+ 0x14700) | direct-out point and follow, signal generator, PAFL |
| 10 | 0x14498 | soft keys, then records not placed |
| 12 | 0x14A78 | scene recall filter (from body +0x574) |
| 14 | | AMM at 0x15F30 (SQ+ 0x162F8), gang words, a large tail |

## Value laws

- **Level** (faders, sends, mix masters, trim, DCA level): u16, `dB = (raw - 0x8000) / 256`; `0x0000` is off,
  `0x8A00` is +10 dB, the maximum. The SQ MIDI protocol's 14-bit taper is `round(raw x 16383 / 35328)`, which
  reproduces the published taper table. [save-proven] The Avantis stores the same 1/256 dB step as a signed
  16-bit big-endian value (`../../avantis/references/processing.md`).
- **dB fields in processing** (gate, compressor, GEQ, trim): the same `0x8000 + 256 x dB`, but 0x0000 is
  -128 dB, not off. [save-proven]
- **Frequency word**: `Hz = 4 x 2^(raw / 4608)`. 0x29CB 20.0 Hz, 0x4197 50 Hz, 0x5396 100 Hz, 0xA162 2 kHz,
  0xDD2E 20 kHz. Used by the HPF, PEQ, key filters, generator and AMM filters; the same law as the dLive notes
  (`../../dlive/references/format-processing.md`). The desk truncates the HPF word and rounds the PEQ word
  (100 Hz is stored 0x5396, not 0x5397). [save-proven]
- **Time** (gate and compressor): `raw = 65535 x (log10(seconds) + 6) / 11`, a log scale from 1 us to 100 s;
  saved raws sit 0.6-1.9 counts above the law. [save-proven]
- **Pan and balance byte**: 0 to 74, 37 (0x25) centre, 0 hard left. [save-proven]
- **PEQ width codes**: 1-25, widest first, 1.5 octave to 1/9 octave. MixPad labels them 1.5, 1.4, 1.3, 1.2,
  1.1, 1, 0.95, 0.9, 0.85, 0.8, 3/4, 0.7, 2/3, 0.6, 0.55, 0.5, 0.45, 0.4, 1/3, 0.3, 1/4, 0.2, 1/6, 0.13, 1/9.
  Untouched code 16 is half an octave. SQ code n is Avantis code n - 1. [save-proven at the ends and the
  default]

## Strip blocks (section 2)

| Blocks | What |
| --- | --- |
| 0-47 | inputs 1-48 |
| 56-59 | SQ+ UltraFX returns 1-4 |
| 64-71 | FX returns 1-8 |
| 72-83 | groups 1-12 (Group n = block 71 + n) |
| 88-99 | auxes 1-12 (Aux n = block 87 + n) |
| 104 | LR |
| 107-110 | FX sends 1-4 |
| 111-114 | SQ+ UltraFX sends 1-4 |
| 115-120 | matrices 1-6 (Matrix n = block 114 + n, mono or stereo) |

Other blocks are unallocated. Block n is the strip the desk addresses as n on its network protocol.
[save-proven]

| Offset | Field |
| --- | --- |
| 0x00-0x0C | name, up to six characters, NUL-filled; 0x0D-0x0F `FF FF FF` [seen in every file] |
| 0x10-0x12, 0x14 | colour R, G, B (each 00 or FF: eight colours), colour-set flag 1 [save-proven by a DCA colour save] |
| 0x18-0x1B | input patch `[u16 socket from 0][kind][fill]` |
| 0x130-0x132 | delay, u16 samples at 96 kHz (2300 = 23.96 ms), then in; input up to 341 ms, mix 682 ms [save-proven on inputs] |
| 0x134 | gang (inputs) |
| 0x13C | DCA membership, u32, bit n = DCA n+1, bits 0-7 used [save-proven on inputs, groups, auxes] |
| 0x140 | mute group membership, same form; inputs and FX returns only [save-proven on inputs] |
| 0x144 | trim, level law, +-24 dB (floor 0x6800) [save-proven on inputs; seen on mixes] |
| 0x148 | aux pre-send point; on block 106 (not a mix) the Input to PAFL source |
| 0x149 | balance: aux and stereo group [save-proven] |
| 0x14A | signal generator assign, 1 assigned [save-proven on Aux 1 and LR] |
| 0x14C | bit 0 polarity, bit 1 mute, bit 2 recall safe; other bits 1 (0xF8 base) [save-proven] |

## Inputs, patch and head amps

- **Patch kinds** at +0x1A: 00 none, 01 Local, 02 SLink, 03 USB, 04 I/O Port, 0x13 signal generator.
  [save-proven for 01, 02, 04; seen in every file for 03] On an SQ+ an UltraFX return block holds 08 at +0x18
  where an FX return holds 00. [seen in every file]
- **Local sockets**: 0-31 the SQ-7's mic inputs; 0x30-0x35 ST1 L/R to ST3 L/R. [seen in every file] 0x3A is
  probably the talkback XLR. [unconfirmed]
- **Head amps, section 6**: 315 records `[u16 gain][48V][pad]`. Record = socket: Local mic N = record N - 1
  (records 0-58), SLink N = 58 + N (59-186), I/O Port N = 186 + N (187-314). Gain is on the level law,
  0 to +60 dB (0x8000-0xBC00), the preamp's own gain with or without the pad. Default `00 9C 00 00` (+28 dB,
  48V off, pad off), the factory Reset value. MixPad's gain box truncates (0xA4DD, 36.86 dB, shows "36") and
  shows gain - 20 with the pad on. [save-proven]
- **Stereo image** (Processing > Preamp on a pair), on the pair's odd block only: +0x34 width as a straight
  percent (0x64 = "Stereo"); +0x36 mode in menu order: L/R 0, R/L 1, L-Pol/R 2, R-Pol/L 3, Mono 4, L/L 5,
  R/R 6, M/S 7. +0x35 always 00. The even block keeps 0x64 and 00. Same codes on the Avantis. [save-proven for
  width and codes 0, 1, 4, 7; 2, 3, 5, 6 by menu order only]
- **Tube Stage** (DEEP preamp): +0x3C level u16 (law unknown), +0x43 mode (Pentode 0, Triode 1, Warm
  Pentode 2, Dual Pentode 3, Pentode Triode 4, High Drive 5), +0x44 FineAdj (bias, raw byte), +0x50 02 =
  loaded, +0x51 bypass (1 out, 0 in). [save-proven: bypass, modes 2 and 3; seen in every file: the loaded flag;
  modes 0, 1, 4, 5 by panel order only, unconfirmed]

## Processing

- **High pass**: +0x54 frequency word, +0x56 slope (1, 2, 3 = 12, 18, 24 dB/oct), +0x57 in. Default 100 Hz,
  slope 1, off. Range 20 Hz to 2 kHz. Only inputs carry one. [save-proven: frequency; seen in every file: slope
  and switch]
- **PEQ**: four bands at +0x7C, +0x82, +0x88, +0x8E, each `[u16 gain][u16 freq][width code][type]`; in at
  +0xAD (01 in). On inputs, FX returns and every mix. Gain -15 to +15 dB. Defaults 63, 220, 2500, 10000 Hz at
  code 16. [save-proven: gain, frequency, width ends, in switch]
- PEQ band 1 type: 00 bell, 06 low shelf, 0B high pass. [seen in every file] Bands 2-3: bell only (00).
- **Gate** (inputs only; a mix has no gate): +0x5C attack, +0x5E release, +0x60 hold (time law), +0x62
  threshold (-72 to +18 dB), +0x64 depth (0 to 60 dB), +0x79 in. Key source +0x20 block (u16), +0x22 kind
  (00 self, 0D another item); a gate keys from an input (0-47) or a mix (72 on). Key filter +0x74 frequency
  word, +0x76 type (0B high pass, 08 band pass, 0A low pass), +0x77 in. Untouched: high pass 50 Hz, out
  (`97 41 0B 00`). The band pass stores no width. [save-proven]
- **Compressor** (inputs and every mix): +0xF4 attack (30 us to 300 ms), +0xF6 release (50 ms to 2 s), +0xF8
  threshold (-46 to +18 dB), +0xFA make-up (0 to +18 dB), +0x10B ratio code, +0x110 soft knee (00 hard,
  01 soft), +0x12D model, +0x12E in. Key source +0x24/+0x26 as the gate's (may name an input, a mix or LR). Key
  filter +0x124-0x127 as the gate's. There is no parallel path. +0x10A is 00 everywhere. [save-proven]
- **Mix GEQ** on every aux, group, matrix and LR: +0xB0, 31 u16 words on the dB law (0x8000 flat); the desk
  uses the first 28, the ISO third octaves 31.5 Hz to 16 kHz (words 28-30 never leave 0x8000). In switch +0xF1
  (01 in). [save-proven: law and switch; seen in every file: word to frequency] DEEP GEQ models are not located.
- **Mix trim** +0x144 as an input's. [seen in every file] **Mix polarity** (Processing > Mix Ext In) +0x14C
  bit 0 as an input's. [save-proven on LR, groups, auxes and matrices]

Ratio codes 0-40 (18 proved by a save each, the rest by stepping MixPad's display in order):

| Codes | Ratios |
| --- | --- |
| 0-9 | 1, 1.03, 1.05, 1.07, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35 |
| 10-19 | 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2, 2.3, 2.5, 2.7 |
| 20-29 | 3 (default), 3.3, 3.5, 3.7, 4, 4.3, 4.5, 4.7, 5, 5.3 |
| 30-40 | 5.5, 5.7, 6, 7, 8, 10, 12, 16, 20, 40, infinity |

## Compressor and gate models (DEEP)

The compressor model byte +0x12D uses the Avantis numbering. +0x12E is the in switch for every model. Each
model lays its own controls out in +0xF4-0x123; loading a model switches it in. [save-proven by saves setting
each model at its control ends in MixPad]

| Code | Model | Controls (block offset) |
| --- | --- | --- |
| 00 | Manual Peak | the stock fields; loads with attack 856 us |
| 01 | Manual RMS | the stock fields |
| 02 | Opto | F8 threshold (dB law; its dial reads otherwise, -12 on the dial is -14 dB), FA gain (-18 to +18, 0x6E00 to 0x9200), 10B ratio code 0-40 (0 = 1.2:1, 30 = 4:1, 40 = 10:1, between them not pinned), 10C attack (00 Fast, 02 Slow), 10D recovery (00 Fast, 01 Med, 02 Slow), 10E Transient, 10F Burn |
| 03 | 16T | F8 threshold, FA gain, 10B ratio code on the 41-code table, 110 soft knee |
| 04 | 16VU | F8 threshold, FA gain, 10B compression code 0-40 |
| 05 | Ducker | F4 attack, F6 release, 102 hold (time law), F8 threshold (-72 to +18), 100 depth (dB law, 20 dB = `00 94`); 10B 00 |
| 06 | Peak Limiter 76 | FC input, FE output (0x8000-0x9200, 0 to +18 dB), 104 ratio (00 all buttons, 04 20:1; 01-03 read as 4, 8, 12 by button order, unconfirmed), 106 attack (knob 1 `E9 A9` to 7 `81 C4`), 108 release (1 `DD 73` to 7 `E4 94`), 10A unit (00 1, 01 2); no threshold control |
| 07 | Mighty | F6 release (`16 56` 0.05 s to `0A 8F` 5 s per 20 dB), F8 threshold (`00 5C` -40 to `00 92` +18), FA output (`00 6E` to `00 92`), 10A detector (00 average, 01 peak) |
| 08 | OptTronik | F4 gain, F6 peak reduction (bytes, 0-100 dial units), F8 compress 00 / limit 01, F9 unit A 00 / B 01, FA emphasis (16 flat, 1C 80 Hz, 1F 80 Hz and 5 kHz); no threshold control |
| 09 | Bus | F4-F5 `00 80`, F6 ratio (1.5, 2, 4, 10:1; default 02), F7 threshold `(dB + 15) x 4` for -15 to +15, F8 attack (0.1, 0.3, 1, 3, 10, 30 ms; default 05), F9 release (0.1, 0.3, 0.6, 1.2 s, Auto); make-up is not stored although MixPad has the knob |
| 0A | Compstortion (SQ+ only) | see What we don't know in `../README.md` |

- **Fill.** Bytes of 0xF4-0x123 a model does not use hold FF for the OptTronik and Bus on an SQ, and 00 on an
  SQ+. A stock compressor over these bytes is all 00 except 0xFD, which holds 0x80. [seen in every file]
- The DEEP models store each shared control as the same number on the SQ and the Avantis, with four desk
  differences: Peak Limiter 76 input and output (SQ 0 to +18; Avantis -40/-80 to +18), Opto attack (SQ
  Fast/Slow; Avantis also Medium), Ducker threshold range and depth resolution, and the Bus make-up (Avantis
  only). [save-proven on both desks]

**SQ+ gate models**: model byte at +0x78 (a standard SQ holds 00). Each model uses +0x5C-0x67, and MixPad
rewrites all twelve bytes on a load. [save-proven]

| Code | Model | +0x5C-0x67 as loaded | Controls |
| --- | --- | --- | --- |
| 00 | Gate | `A6 32 60 7B 78 78 00 62 00 94 00 00` | the stock gate's |
| 01 | Ducker | `33 68 D7 72 87 7A 00 79 00 94 00 00` | gate layout: attack, release, hold, threshold, depth [save-proven] |
| 02 | Dual Threshold Expander | `ED 50 5E 74 00 62 00 52 00 94 00 00` | 5C attack, 5E release, 60 upper threshold, 62 lower threshold, 64 depth, 66 LIN 00 / EXP 01 [save-proven for upper threshold and switch] |
| 03 | Source Expander | `00 62 00 94 02 00 00 00 00 00 00 00` | 5C threshold, 5E depth, 60 speed (00 Slow, 01 Medium, 02 Fast) [save-proven] |
| 04 | Expander | `00 62 00 94 ED 50 78 78 5E 74 10 02` | 5C threshold, 60 attack, 64 release, 66 ratio as 1:r on the 41-code table (code 16 = 1:2, 18 = 1:2.5) [save-proven at two points]; 5E, 62, 67 not placed |

## Sends, assigns and bus feeds (section 5)

Record s (s = block) is 50 entries of 6 bytes; entry k is the send from block s to block 72 + k. Entry:
`[u16 level][pan][00][flags][FF]`, flags `0xFC | b1 << 1 | b0`, b1 = assigned/on, b0 = pre-fader.
[save-proven]

| Entries | Destination |
| --- | --- |
| 0-11 | groups 1-12 (assign only; level fixed at 0x8000) |
| 16-27 | auxes 1-12 |
| 32 | LR: on an input its own fader, LR pan and LR assign; on any mix its master fader; on a group its LR assign |
| 35-38 | FX sends 1-4 |
| 39-42 | SQ+ UltraFX sends 1-4 |
| 43-48 | matrices 1-6 (from LR, groups and auxes only; the desk leaves every mix's send into a matrix on at -inf) |

- A send's pan into a stereo aux uses the pan law; into a mono aux it stays 37. [save-proven]
- Inputs, FX returns and groups send into FX sends; a return's entry into its own rack's send always has the on
  bit clear (0xFC). A group feeds auxes and FX sends; an aux feeds matrices only; no group feeds a group and no
  aux, FX send or LR feeds any mix. An untouched group-to-aux entry is 0x0000 flags 0xFF; group-to-FX 0xFE.
  [seen in every file]
- A stereo input pair keeps its values on the odd input's (even-numbered) block; the even input's block is
  stale. [save-proven]
- **Aux pre-send point** (+0x148, one per aux, MixPad's "Channel Source"): 00 Post Preamp, 02 Post PEQ
  (default), 03 Post Delay/AMM, 04 Post Compressor; MixPad offers no 01. A matrix has no point; a pre send into
  one leaves just before the source's fader. Non-aux blocks hold 03 (02 on blocks 100-103 and 106).
  [save-proven]

## Bus config and matrices (section 1)

| Body offset (image) | Field |
| --- | --- |
| +0x01 (0x3D) | number of groups [save-proven] |
| +0x02 | FX send count, 4 [seen in every file] |
| +0x05 (0x41) | number of auxes; groups + auxes = 12 [save-proven] |
| +0x0C | stereo input pairs, 3 bytes, one bit per odd/even pair, pair 1 lowest [save-proven] |
| +0x1C (0x58) | group stereo mask, u16, bit n = Group n+1 [save-proven] |
| +0x1E (0x5A) | aux stereo mask, u16; in both masks bits past the count and bits 12-15 read 1, and a block that leaves gets its bit set [save-proven] |
| +0x20 (0x5C) | matrix widths, u32, bits 11-16 = Matrices 1-6 stereo [save-proven on 1.6] |

- Six matrix channels: a mono matrix takes one, a stereo one two, Matrix 1 first, so a file has three to six
  matrices. `05 38 00 00` is three stereo; `05 00 00 00` six mono; `05 20 00 00` mono, mono, stereo, mono,
  mono. The low `05` is in every image and is not the matrices'. On 1.5 the bits past the last matrix read 1 up
  to bit 18 (`05 F8 07 00`); on 1.6 they read 0. [save-proven on 1.6; seen in every 1.5 file]
- Each mix block keeps its role; the counts say how many of each range are live. When a mix goes, the desk
  resets its block and record to a never-used block's state (but +0x12B is 0x26, 0x00 when never used), sets
  every input's and FX return's send into a group that goes to `00 80 25 00 FC FF`, every send into an aux that
  goes to `00 00 25 00 FF FF`, unpatches every output it fed, and clears its entry in the section 7 table.
  [save-proven]
- The layout lives in NVDATA. A scene's section 1 holds a copy of the layout it was stored under, and the desk
  does not apply it on recall, so scenes and NVDATA of one show can disagree. [save-proven, checked in MixPad]

## DCAs, mute groups, gangs

- **DCAs, section 3**: 32 records of 24 (8 used): `[R G B][00][colour set][3 bytes][u16 level][mute][name,
  13 bytes]` (+0, +4, +8, +10, +11). Membership is on each strip (+0x13C). A save proved a group can join a
  DCA. [save-proven]
- **Mute groups, section 4**: 32 records of 24 (8 used): +0-7 `00 00 00 00 00 FF FF FF`, +8 mute (01 engaged),
  +9 name (13 bytes NUL-filled, to a closing `FF FF`). [save-proven on MG1-2; seen on the rest]
- **Gangs** (8 on an SQ): input block +0x134 = gang n-1, FF none. Gang n's attribute word (u16) at 0x15FE4 +
  4(n-1) (section 14 body +0xB4; SQ+ 0x163AC, +0xB8). Bits 3 PEQ, 7 Fader, 8 Mute. [save-proven] Applying a
  gang rewrites the second member's section 5 entries 7-15, 21-31, 33, 39-42 and 49 to `00 00 25 00 00 00`.
  [save-proven] Only inputs have been ganged.

## Output patch (section 7)

Records 0-411: `[u16 source][type][fill]`, fill 0xFF on 1.5 and 0xFE on 1.6. [save-proven]

| Records | Socket |
| --- | --- |
| 0-15 | Local out 1-16 |
| 32, 33 | Local A, Local B (which physical sockets is unknown) |
| 40, 41 | AES L, R |
| 64-103 | ME 1-40 (default: input direct outs Ip1-32, then Ip41-48) |
| 108-235 | SLink 1-128 |
| 236-267 | USB 1-32 |
| 268-283 | not placed |
| 284-411 | I/O Port 1-128 |

Types: 00 none; 0F a block (mono or left leg; an input's block is its direct out, a mix's is its output); 10
the right leg of a stereo block; 01 a Local input (tie line, source = socket); 04 an I/O Port input (tie line);
05 a strip's insert send. [save-proven] A stereo mix is one block.

## Inserts and direct outs

- **Input insert**: +0x1C return `[u16 socket from 0][kind]` using patch kinds (01 Local save-proven, 03 USB
  seen); +0x28 send with output kinds (1A Local out save-proven, 1D USB out seen). An FX rack is return kind 18
  and send kind 2B with the rack number from 0. +0x2B and +0x2F are fill (00 when assigned in a scene). +0x31
  in (0 in, 1 out; MixPad switches it in on assign), +0x32 type (0 Digital, 1 Analogue, 2 -10 dBV). Assigning
  also writes a type 05 record on the send's output socket. [save-proven] A mix block holds the same two
  records; no save has set one.
- The insert returns between the gate and the PEQ: the direct-out source list runs Preamp, HPF, Gate, Insert
  Return, PEQ, Compressor, Delay. No position byte exists. [seen in MixPad's list]
- **Direct outs**: one desk-wide setting for every input. Section 9 body +0x00 (0x14478) point: 00 Post
  Preamp, 01 Post HPF, 02 Post Gate, 03 Post Insert Return, 04 Post PEQ, 05 Post Compressor, 06 Post Delay
  [05, 06 save-proven; the rest from MixPad's list order]. Body +0x01 (0x14479) follow flags: bit 0 Fader,
  1 Mute, 2 DCA Fader, 3 DCA Mute, 4 Mute Group [save-proven]. Common value 0x1A.

## FX racks, sends and returns

**Section 13**: records 0-7 are FX racks 1-8; on an SQ+ records 8-11 are UltraFX racks 1-4. [save-proven]

| Desk | Record |
| --- | --- |
| SQ (154 bytes) | [0] status, [1] engine (SQ numbering), [2..17] name, [18..21] fill (`00 00 00 FF` on 1.6, zeros on 1.5), [22..149] 64 parameter words, [150..153] two record words |
| SQ+ (172 bytes) | [0] status (UltraFX: 06 loaded, 02 empty), [1] 00 (UltraFX loaded: 03), [2] engine (Avantis numbering), [3..18] name, [19..21] 00, [22..165] 72 words, [166..169] record words, [170..171] level |

The SQ status byte follows the loaded preset: 2 for most, 4 dynamic EQ and de-esser, 3 multiband comps and
Echo, 1 seven older reverbs. [seen in every file] Parameter words are the same numbers as the Avantis's in the
other byte order (`08 4D 62 A1` on the SQ is `4D 08 A1 62` on the Avantis). A name ends at its NUL; bytes after
it are stale. [save-proven]

| Engine | SQ | SQ+ / Avantis |
| --- | --- | --- |
| Empty, Reverb, SMR Reverb, EMT 250, Room | 00, 02, 03, 04, 05 | 00, 02, 03, 04, 05 |
| Flanger, Chorus, ADT | 07, 08, 09 | 06, 07, 08 |
| Symphonic, Sub Harmonics, Gated Verb, Phaser | 0C, 0D, 0E, 10 | 09, 0A, 0B, 0C |
| De-Esser, Dynamic EQ, Multi Band Comp 4, 3 | 15, 1C, 1D, 1E | 0D, 11, 12, 13 |
| Bucket Brigade, Stereo Tap Delay, Echo | 22, 23, 24 | 15, 16, 17 |

- Some engines hold desk-specific fixed words: EMT 250 words 6, 7, 9 are `80ED 8086 8080` on the SQs and 0 on
  the Avantis; Stereo Tap word 14 is `0000` on the SQs where the Avantis holds `8000`; Sub Harmonics record words
  are `7C00 7C00` on the SQs. [seen across the factory libraries]
- SQ+ UltraFX engines: 1C Spaces Reverb, 1D Plate Reverb, 1E Vocal Tuner, 22 Vocal Harmoniser 4, 23 Vocal
  Harmoniser 2, 24 Vocal Shifter, 28 Vocal Gridder, 2A Amp Cab, 2B Saturator, 2E-32 Essential models (SQ+
  only). The Avantis's Spaces record has a space byte the SQ+ record lacks. [read from library preset names]
- **FX sends** (blocks 107-110): master fader = entry 32 of the own record, mute = +0x14C bit 1, DCA bits at
  +0x13C; no mute groups; width not decoded. [save-proven on FX send 1; seen on 2-4]
- **FX returns** (blocks 64-71): return n plays rack n, laid out as an input (LR entry fader, balance,
  assigns; aux and FX send entries; PEQ; DCA and mute group bits; mute). HPF, gate, compressor, delay and trim
  bytes hold the reset: a return has none. [seen in every file]
- **SQ+ UltraFX**: sends at blocks 111-114 (entries 39-42 feed them; master and mute as FX sends) and returns
  at blocks 56-59, laid out as FX returns (name +0x00, colour +0x10-0x12, colour set +0x14, mute +0x14C, PEQ).
  [save-proven on send 1 and return 1; seen on 2-4] Returns 1-4 are on LR in the SQ+ blank. [seen]

### Reverb and delay parameter words

The parameter words are the same numbers on the SQ, SQ+, Avantis and dLive, so this applies to all four.
Worked out in SQ MixPad 1.6.1: one save moving every front-panel control of an EMT 250 at once (each word
moved alone and matched the display), saves at each end of every control, and one factory preset per engine
checked against MixPad's display to the last digit. MixPad's value boxes truncate (a 3.846 s decay shows 3.84).
A value box moves with a sideways drag; a vertical drag does nothing. [save-proven unless marked]

The four reverb engines (Reverb, SMR Reverb, EMT 250, Room) share their first six words, the front panel in
MixPad's order:

| Word | Control | Law | Range |
| --- | --- | --- | --- |
| 0 | LF Cut | `4 x 2^(raw/4608)` Hz, the PEQ's frequency law | Off (its 20 Hz word, `0x29AA`) to 400 Hz |
| 1 | HF Cut | same | 2-20 kHz |
| 2 | Predelay | `0x8000 + 16 x ms` | 0-170 ms |
| 3 | Decay Time | `65535 x (log10 s + 6) / 11`, the dynamics' time law | EMT 250 0.4-4.5 s; Reverb, SMR and Room 0.1-10 s (those three ends from the display) |
| 4 | HF Decay | frequency law | 2-20 kHz |
| 5 | HF Slope | `0x8000 + 16 x value` | 1-10 |

Stereo Tap Delay (SQ engine 23): word 0 the left time and word 1 the right, plain milliseconds (5-2700 ms);
word 3 the Feedback knob, `0x8000 + 32 x` its 0-10 (full is `0x8140`).

A file written with these words loads in MixPad 1.6.1 showing exactly the values written (four reverbs and a
delay written onto the SQ factory show and recalled). [save-proven]

## Desk-wide settings

Section 9 (body offsets; SQ body starts 0x14478) [save-proven by one-change saves]:

| Body | Field |
| --- | --- |
| +0x02-0x07 | generator: +0x02 frequency word (`7A11` 440 Hz), +0x04 level (dB law), +0x06 mute, +0x07 type (0 Sine, 1 White, 2 Pink, 3 Band-pass) |
| +0x10, +0x12 | Listen Level, PFL Trim, both dB law |
| +0x16 | PAFL Delay, u16 samples at 96 kHz |
| +0x18 | flags: bit 1 Additive, 2 Sel Follow PAFL, 3 LR to PAFL, 4 Input AFL, 5 Output AFL, 6 PAFL Follow Mix, 7 Input Override Mix |
| +0x19 | Ext in to PAFL, 0 on |

- Input to PAFL Source is block 106 +0x148: 3 Post Delay/AMM, 0 Post Preamp. [save-proven]
- PAFL Ext In source: section 8 records 3 and 4 (body +0x08, +0x0C), the same value in both, read as an input
  patch `[socket][00][kind][fill]`. Record 5 reads `3A 00 01` in every image. [save-proven for the field]
- **AMM**, section 14 body (0x15F30; SQ+ 0x162F8): +0x00 and +0x08 two 64-bit slot masks; +0x10 48 slot
  priorities (dB law); +0x70, +0x72 side chain HPF and LPF (frequency word); +0x74 48 slot inputs from 0 (empty
  slot 00 on an SQ, FF on an SQ+); +0xA4 number of AMMs (1 or 2); +0xA5, +0xA6 AMM 1 and 2 Out; +0xA7 Follow
  Fader. A slot's On/Off is not in the scene. [save-proven]

## Layers, soft keys, scenes

- **Layers**, section 1 body +0x2C: eight 97-byte records, each one 0xFF then 32 slots `[kind][index][00]`;
  kind 00 empty, 01 strip (index = block), 02 DCA (index from 0). Layer names are not in these records. [seen
  in every file]
- Factory layers differ per model: SQ-7 32 faders a layer; SQ-6 four layers of 24 (25-32 empty, DCAs at 17-24
  of layer 4); SQ-5 five layers of 16 (17-32 empty, DCAs on layer 5). [save-proven]
- **Soft keys**, section 10 (1,476 bytes): sixteen 8-byte records `[value][00][type][00][00 00 00 00]`; an
  empty key is all zeros. A fresh show: six type 02 (values 0-5), one empty, one type 14, eight type 03 (values
  0-7). The section is the same in every scene and NVDATA of a show (MixPad keeps soft keys in its NV store).
  [seen in every file]
- Recall filter: section 12 body +0x574 (0x14FF0), one 8-byte record per strip block in section 2 order; byte
  0 bit 3 is Inputs > Preamp (set on blocks 0-63 when blocked). Body +0xAE8 (0x15564) toggles with it, meaning
  unknown (FF on an SQ+ base). [save-proven for the Preamp bit]
- Up to 300 scenes on an SQ. [seen]

## Models and firmware versions

- **SQ-5, SQ-6, SQ-7**: factory shows differ only in section 1 layers, the input patch of inputs past the
  model's mic count (`00 00` at +0x18/+0x1A), and the section 7 output patch (missing Local outs off; USB and
  I/O Port outs past them on ST1-3 and socket 0x3A). Switching MixPad's model rewrites nothing: it hides faders
  and sockets past the model and keeps them in the file. Scene store did nothing in MixPad set to an SQ-5.
  [save-proven in MixPad; what a real SQ-5 does on load is not checked]
- **SQ 1.5 vs 1.6**: fill bytes differ (strip record fills at +0x1B, +0x1F, +0x23, +0x27, +0x2B, +0x2F and
  section 7 fills FF on 1.5, FE on 1.6; matrix width fill bits; section 11 +0x13 bits 5-6). 1.6 adds section
  12 +0x570 and a 6,664-byte table at section 14 +0x31C. 1.5.1 and 1.5.6 spell a show identically. [seen in
  every file]
- **MixPad 1.6.1 vs desk 1.6.3**: the same show differs at 7,730 bytes, all fill: sixty offsets of every
  section 2 record (FF from MixPad, 00 from the desk), the three bytes after the colour flag (MixPad FF; the
  desk 00 on a coloured strip), and 350 bytes of sections 8 and 11-14. MixPad 1.6.1's NVDATA also fills section
  14's tail from 0x17C5C with FF where scenes and the desk hold 00. Section 5 is identical. [save-proven]
- **SQ MixPad 1.6.1 vs SQ+ MixPad 2.0.3**: header to 0x203, CRC from 0x204, name at 0x10, sections shifted
  (block n at 0x540 + 336n). Section 7 is 192 bytes longer (its table 16 x 18), section 11 is 48 bytes (SQ 28),
  13 is 2,792 (2,500), 14 is 40,204 (41,168), each count including the sentinel. Fill 00 where an SQ fills FF
  (gate +0x66-0x73, unused compressor bytes). Gate models at +0x78, Compstortion, UltraFX blocks, records and
  entries, section 9 at 0x14700, AMM and gang words 4 bytes further into section 14. Every other strip and send
  field sits where an SQ's does. [save-proven]
