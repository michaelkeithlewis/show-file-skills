# dLive show versions 11-14, settings files, talkback groups, actions

Field notes from markcarlberg (pull request #2), from dLive Director V1.9x to V2.11 saves and Director's own
upgrades of older shows. They add to the `format-*.md` pages here and do not replace them; where they disagree
with a page here, that page stands and the difference is under What we don't know in `../README.md`. The tools in
`scripts/` read and write Version 14 only.

Proof in brackets: save-proven (one change in Director, save, the named bytes moved), upgrade-proven (Director
upgraded an older show and the change is what moved), seen in every file (consistent, never moved alone), or
unconfirmed.

## Container and versions

- The Avantis container, file for file: gzip, then a POSIX ustar tar with directories and regular files only and
  two zero blocks at the end. No encryption or signing; the show's name is the file name only. [save-proven]
- `Show/Version.dat` is a bare number: `11` (early, probably V1.8x), `12` (Director V1.9x), `13` (V2.0x), `14`
  (V2.11). No file holds a firmware or Director version string. [seen in every file]
- Show-wide files are the Avantis's, sized to 128 inputs and 64 legs, plus dLive-only hardware files
  (`EastPage`, `ExternalScreen/*`, `IOCustomNames/*` with names as decimal byte lists, `IPController/*`,
  `MCASettings`, `MixrackStartup`, `Multifunctions/*`, `SouthConfig/*`, surface AES, RTA and word clock files).
  [seen in every file]
- Scene slots: Version 11 and 12 store all 501 slots (an unused one is a header-only `.dat`, 108,494 or 108,495
  bytes); Version 13 stores only the slots in use. A stored scene can be partial: it holds only the blocks its
  recall scope stored. [seen in every file]
- Scene header length 0x1A7CD (V11), 0x1A7CE (V12), 0x1CDF9 (V13). Surface chains start at 0x390. [seen in
  every file]
- The surface is told apart by its banks (`Channel Left/Middle/Right Bank Switcher`, 146 bytes for 12 faders,
  98 for 8, 2 for a bank the surface lacks): S7000 12/12/12, S5000 12/8/8, S3000 and C2500 12/0/8 (not told
  apart), C3500 12/0/12, C1500 12/0/0. The MixRack model is in no file found so far. [save-proven by surface
  saves]
- Version byte meanings differ from the Avantis: `Input Mixer` version 2 means "has Ultra FX sends" on an
  Avantis but "no rack sends" on dLive 11 and 12. Decide the layout by family first. [save-proven]

## Platform counts and block lengths

Every show holds 128 inputs, 64 mono and 32 stereo slots each for groups, auxes and matrices, 16 + 16 FX sends,
16 FX returns, 6 mains, 24 DCAs, 8 mute groups, 2 monitor strips (Wedge, IEM), 16 FX racks, 64 Dyn8 units,
20 source selectors; Version 13 adds 8 AHFX racks. Name managers are `1 + strips x 10` (inputs 1,281, mono buses
641, stereo 321, DCAs 241, mains 61, monitors 21). [proven by length]

| Block | V11 | V12 | V13 | V14 |
|---|---|---|---|---|
| `Highpass Filter` | 45 v2 | 45 v2 | 5 v3 | as 13 |
| `Lowpass Filter`, `Talkback Highpass Filter` | 31 v3 | 31 v3 | 11 v4 | as 13 |
| `Parametric EQ` | 118 v3 | 118 v3 | 38 v4 | as 13 |
| `SCF Gate` | 63 v3 | 63 v3 | 23 v4 | 23 v4 |
| `Graphic EQ` | 619 v1 | 1089 v2 | 169 v3 | |
| `Gate` | 25 v2 | 19 v3 | 19 v3 | 19 v3 |
| `Compressor` | 111 v5 | 119 v6 | 88 v7 | 127 v8 |
| `Digital Attenuator` | 7 v1 | 7 v1 | 7 v1 | |
| `Input Mixer`, `Mix Mixer` | v2, no rack sends | v2, no rack sends | v3, 8 rack sends | `Mix Mixer` v4 |

- The V14 compressor (127 bytes, version 8) is the Avantis Bridge-5 one with one byte more at [32] and 36 more
  after the eleven model 10 bytes (47 from [58]). Each model's library preset matches Avantis V1.30's at these
  offsets. [save-proven]

## The mix

- `Input Mixer` row: the Avantis stride with 24 DCA bytes and, from V13, 40 bytes of rack sends:
  `S = G + 4(mono FX + mono aux + mono mtx) + 5(stereo FX + stereo aux + stereo mtx) + 15 + 24 + 8 (+ 40)`.
  [save-proven in V2.11]
- `FX Send Mixer` and `AHFX Send Mixer` records are 8 bytes longer than the Avantis's (24 DCA bytes). [proven by
  length]
- `DCA Levels and Mutes`: 129 bytes, `1 + 24 x 4 + 32`. Mute group engaged flags sit one per 4-byte record past
  the 24 DCAs, as on the Avantis. [save-proven]
- `MixConfig.dat` byte 7 is named "main stereo" in Director's log of each recall; bytes 1-11 are mono groups,
  stereo groups, mono FX sends, stereo FX sends, mono auxes, stereo auxes, main stereo, main config, stereo
  matrices, mono matrices, PAFLs (`format-mixconfig.md`). [read from Director's recall log]
- The pool is 64 legs and no file spends more than 62 (the desk keeps two back, as the Avantis). [seen in every
  file]
- FollowPanSettings: a following stereo matrix written as kind 10 (the Avantis value) makes Director V2.11 log
  `ERROR: Unexpected mix type (MixerModule.cpp:653)` about 1,900 times per load and show Internal Error; written
  as 11 it loads clean. From Version 13 the file holds eight kind 19 lines, one per AHFX rack, after the stereo
  FX sends. [load-checked in Director V2.11; kind 11 seen in every file from Version 11 to 14]
- `Send Source Select, <Mono|Stereo> <Aux|FX> NN[ Left/Right]` byte 1 is the pre send point: `00` Post Preamp,
  `03` Post Ins A Ret, `04` Post PEQ, `07` Post Delay. A stereo mix holds it on both legs. [save-proven in
  Director V2.11]

## Patch, beyond `format-patch.md`

The table offsets in markcarlberg's notes match `format-patch.md` (input records at payload 1, VSC at 0x681 and
0x801, Insert A and B returns at 0xA04 and 0xB84). Extra readings:

- Local outs 1-32 are output records 0-31; output records 33-64 are FX rack inputs (rack k at 33 + 2(k - 1) and
  the next, fed `1D 00 k-1`); 65-80 UltraFX rack inputs (V13 and V14 only). In a Version 11 or 12 file every
  record from 65 on sits 16 lower. DX 1/2 out N is record 480 + N, ME out N record 544 + N (40). I/O Port 1 out N
  is record 96 + N, with Ports 2 and 3 following at 128 records each. [upgrade-proven; Ports 2 and 3 seen]
- A Dyn8 return is `27 00 u-1`, and its send goes to output record 584 + u in V14 (568 + u in V12). [save-proven]
- The talkback source slot is output record 32 (payload 6728). [save-proven]
- Returning an insert on a MixRack socket sets that preamp to +20 dB, pad in, 48V off (`1B 00 00 00` to
  `14 00 01 00` after the version byte). [save-proven]
- A mix's `Insert, <mix>` byte 1 is the same bypass as an input's: `00` in, `01` out. [save-proven]
- Preamp blocks in the Surface scene: `Surface Analogue Input`. [save-proven]

## Talkback, PAFL, settings

- **Talkback groups:** twelve at the end of the `Channel Mapper`, starting 1,775 bytes before its end, 148 bytes
  apart: `[02]`, a NUL-terminated name, then 128 bytes of slots from +19, one slot per mix of the bus
  configuration in the order mono groups, stereo groups, mono FX sends, stereo FX sends, mono auxes, stereo
  auxes, the mains (8 bytes), mono matrices, stereo matrices; a mono mix's slot is 2 bytes, a stereo one's 4. A
  member's slot holds `[kind][number from 0]`, `00`s otherwise. Kinds: `02` mono group, `04` mono aux, `05`
  stereo aux, `08` main, `0A` mono matrix, `0B` stereo matrix [save-proven], `03` stereo group [seen]. Adding
  mixes shifts later slots; files keep stale bytes from older layouts in other slots, so a slot counts only where
  it holds its own mix's kind and number. [save-proven]
- **`Show/Talkback/Talkback.dat`:** `2`, Surface Talk Button Latching, Enable Dim PAFL on Talkback, the Trim
  (`0x8000 + 256 x dB`). The talkback mic's gain, pad and 48V are its source socket's preamp. [save-proven]
- **`PAFLSettings.dat`** (version 6, 210 fields): [0] Ext Ip Talk (same sense as the Avantis), [8] Additive,
  [9] Input AFL, [10] Output AFL, [38] Mix Follows Input, [39] Mix Follows Mix, [40] Sel Follows, [49] PFL Trim
  (`0x8000 + 256 x dB`), [57] Delay in samples at 96 kHz. Field 207 is the PAFL each surface listens to. Strips
  do not choose a PAFL. [save-proven]
- `SignalGenerator.dat` and `AutoMicMixer` (673 bytes) are the Avantis's
  (`../../avantis/references/settings-and-surface.md`) with 64 leg lines and 128 inputs. [seen in every file]
- **Dyn8:** 64 `Dynamics Unit NN` blocks, 140 bytes. Version 01 (V11-12) and 02 (V13-14) hold the same 140 bytes
  reordered. [upgrade-proven] The V14 word map is in `format-fx.md`.
- **Versioned text files:** `Preferences.dat` versions 4, 6, 7, 8, each the one before with lines appended.
  `MIDISettings.dat` 2, 3, 4 (version 3's eleven values are version 4's first eleven). Scene safes version byte
  20 (V11-13), 21 (V14). [upgrade-proven]

## Actions (`Show/Multifunctions/<name>.dat`)

One file per action: a version line (`1`; V2.11 writes `2` and then the creation time in hex milliseconds), then
one line per step of comma tokens (`aa,<hex>` a byte, `a8,<hi>,<lo>` a 16-bit number; V2 adds `ea`,
`eb,<hex>`, `e8,<hex>`). A step: function, mode (0 Toggle, 1 Set On, 2 Set Off), the function's values, then a
count and that many strips as `[kind][number from 0]`. Director lists actions by name; order is not stored.

| Function | Name | Values |
|---|---|---|
| 1 | Mutes | |
| 2 | Assign | |
| 3 | Strip Assign | (not save-proven) |
| 4 | Main Level | level, 8000 = 0 dB |
| 5 | Send Level | level, 8000 = 0 dB |
| 6 | Processing | 1 Preamp Model In, 2 LPF, 3 HPF, 4 Gate, 5 Insert A, 6 Insert B, 7 Compressor, 8 PEQ, 9 NEQ |
| 7 | ABCD Ip | 1 A, 2 B |
| 8 | Talkback Grp | |
| 9 | Talkback Add | |
| 0B | Ext Ip to PAFL | |
| 0C | Set Bypass UFX | |

Strip kinds: 01 input, 02/03 group, 04/05 aux, 06/07 FX send, 08 main, 0A/0B matrix, 0C FX return, 0D DCA,
13 UFX unit. [every function but 3 save-proven; strip kinds seen] Functions 6 and 7 match
`format-processing-surface.md`.

## FX racks

- `FX Manager 01-16` (124 bytes, v4 on V11/12, v7 on V13): engine codes use the standard SQ numbering, not the
  Avantis's (ADT 09, De-Esser 15, Stereo Tap Delay 23; the table is in `../../sq/references/FORMAT.md`). Parameter
  values are the Avantis library's. In V11-12 records word 24 holds a value of its own. [engines save-proven in
  V2.11; the rest seen]
- `AHFX Manager 01-08` (V13 on) is the Avantis `Ultra FX Manager`, with dynamics, SCF, PEQ and side chain
  blocks labelled "AHFX". The FX return PEQ is `Parametric EQ, FX Return Left/Right NN`. [seen in every file]
- The reverb and delay parameter words are the same numbers on SQ, Avantis and dLive
  (`../../sq/references/FORMAT.md`).
