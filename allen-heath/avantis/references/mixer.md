# Avantis mixer config, buses and mixer sections

Compare `allen-heath/dlive/references/format-mixconfig.md`. Byte layouts match dLive where not noted otherwise.

## MixConfig

`Show/MixConfig/MixConfig.dat`, 13 bytes, same layout as dLive:
`[1, MG, SG, mFX, sFX, mAux, sAux, 1, mode, sMtx, mMtx, PAFL, 23]`. Avantis shows use mode 1 (LR) and one
stereo PAFL. Copy the same 13 bytes to scene header bytes 330 to 342.

## Bus budget

| | Buses total | Mono and stereo ways | Notes |
|---|---|---|---|
| Avantis, any firmware | 42 | 38 | 42 = 38 + LR 2 + PAFL 2 |
| Avantis FW 2.0 + dPack | 56 | 52 | same split, 4 for LR and PAFL |
| dLive | 64 | 60 | for comparison |

- A stereo bus costs 2 ways, a mono bus 1.
- Every mono count (groups, FX sends, auxes, matrices) must be even, as on dLive.
- At most 16 buses of one type on Avantis (dLive: 32).
- The factory config of a new Avantis show already uses all 42 buses. To add a bus, remove another first.
- Bus order is the dLive order: mono groups, stereo groups, mono FX, mono aux, stereo FX, stereo aux, main,
  PAFL, mono matrix, stereo matrix.

## Changing the bus config

Each bus owns a family of sections in the live scene: `Mix Delay`, `Digital Attenuator`,
`Compressor side chain source`, `Insert`, `Parametric EQ`, `Graphic EQ`, `Compressor`, and for groups, FX,
auxes and main also `Send Source Select`. Stereo buses carry `Left` and `Right` sections.

What works on Avantis (checked in Director and on the console):

1. Drop the sections of buses above the new count.
2. To add buses, copy the sections of the highest existing bus of that type, renumber them, and set the last
   byte of `Compressor side chain source` to the new bus index (number minus 1).
3. Write MixConfig, the scene header copy, FollowPanSettings and the mixer sections (below) for the new
   config. All of them must agree.

Observed, not understood: `Send Source Select, Stereo Aux NN` for stereo aux 6 and up holds `01 07 00` in
Director's own saves.

## FollowPanSettings

`Show/FollowPanSettings/FollowPanSettings.dat`, text: `1`, then one `type,index,0,0` line per stereo mix in
this order: stereo aux (type 5), stereo FX (type 7), stereo matrix (type 10 on Avantis, 11 on dLive).
dLive also lists the UFX returns (type 19).

If this file does not match the bus config, Avantis Director crashes on load. It was the first crash we hit
when converting a dLive show.

## Mixer section header

`Input Mixer`, `FX Return Mixer` and `Mix Mixer` each carry their own bus config in payload bytes 1 to 8:
`mg, sg, mf, sf, ma, sa, mm, sm`. Note: mono matrix before stereo matrix, the reverse of MixConfig.

This header decides the row layout. It can differ from MixConfig and from the bus sections in the same
scene. Seen on a real Avantis show: rows were 179 bytes where MixConfig predicted 184. Read the rows with
the header config; take bus names and counts from the show.

## Input Mixer and FX Return Mixer rows

12-byte header, then one row per channel (`(len - 12) / channels`):

`[group assigns: mg + sg bytes][mFX sends][mAux sends][sFX sends][sAux sends][mMtx sends][sMtx sends][main 6][mark 5][flags 28][tail]`

- Mono send: 4 bytes `[assigned][pre][level s16]`. Stereo send: 5 bytes, plus pan. Level is s16/256 dB,
  `0x8001` = off. Pan `0x25` = centre. A fresh send reads `01 00 80 01` (mono) or `01 00 80 01 25` (stereo).
- Main: `[LR assign][main mono][mute][level s16][pan]`.
- Mark: `00 01 4a 80 01`.
- Flags: DCA membership from flag byte 4.
- Tail: 8 Ultra FX sends of 5 bytes on consoles with Ultra FX.

## Mix Mixer rows

11-byte header (byte 0 = section version, bytes 1 to 8 = config as above), then rows in the order mono
groups, stereo groups, mono aux, stereo aux, LR, mono matrix, stereo matrix.

- Group rows: sends to mFX, mAux, sFX, sAux, mMtx, sMtx (5 bytes each).
- Aux and LR rows: sends to mMtx, sMtx.
- Matrix rows: no sends.
- Then 1 byte, main 6, mark 5, tail (Bridge-4: 29 bytes; dLive: 37 bytes).
- dLive from section version 4 adds group to group flags (mg + sg + 1 bytes) before main in group rows.
  Avantis has no group to group routing.
- dLive and Bridge-5 append 40 bytes per group at the end of the section (8 UFX sends x 5 bytes).

Trust a fixed layout only if every row has `4a 80 01` at main + 8. If not, search for the marks instead.
That rule fixed garbage bus masters when reading Bridge-5 shows.

## More mixer detail (markcarlberg, pull request #2)

From Avantis Director V1.30 and V2.01 saves. Proof in brackets: save-proven, seen in every file (never moved
alone), or unconfirmed. Differences from the text above are listed under What we don't know in `../README.md`.

### MixConfig bytes

- [7]: 01 a stereo LR, 00 an LR of two mono strips (seen in the V2.01 LCR+ factory shows). [seen in every file]
- [8] main mode: 00 None, 01 LR, 02 LR+M sum, 03 LR+M, 04 LCR, 06 LCR+. [save-proven]
- [11]: 1 in nearly every file, 2 where a layout spends 52 legs instead of 54. It is the PAFL count on dLive;
  on Avantis that reading is unconfirmed.
- Director recalls an odd mono count as the pair below it and flags the console. Stereo counts may be odd.
  [seen in every file]
- The pool is 54 legs (56 buses with dPack less two the desk keeps back): mono 1, stereo 2, FX sends included,
  LR 2 and any mode past LR 4. No file spends more than 40 without dPack. A file spending 56 was refused whole
  on recall ("Director - Internal Error"). 54 itself is not recall-tested. [seen in every file]
- FX sends: twelve at most, a stereo one counting as one of the twelve and two legs of the pool (Director's
  "FX Remaining" and "Mixes Remaining"). [save-proven]

### Live-scene order

The mix section opens the chain: one run of blocks per strip in the order mono groups, stereo groups, mono FX
sends, mono auxes, stereo FX sends, stereo auxes, mains, mono matrices, stereo matrices. Per leg on Bridge-4:
`Mix Delay`, `Digital Attenuator`, `Parametric EQ`, `Graphic EQ`, `Compressor`, `Compressor side chain source`,
`Insert`, then a `Send Source Select` per leg on everything but a matrix. An FX send has only its
`Send Source Select`. On Bridge-5 the section is grouped by block kind (every PEQ, then every GEQ, then every
compressor, then each leg's delay, trim, side chain source and insert, then every `Send Source Select`, then the
Ultra FX racks' sixteen). An option card block sits after the section. [save-proven]

- Mains: `Main 01` Left/Right in LR; `Main 03` and `Main 04` (mono) are added in every mode past LR, default
  names M (C in LCR and LCR+) and Msum. Main records in `Mix Mixer` follow the labels, so an LR+M show's M is
  the second record. [save-proven]
- LR+M and LR+M sum cannot be told apart by labels; only MixConfig [8] says. Only LR+M has a per-input M
  assign. [save-proven]
- Changing the layout re-lays the `Input Mixer`, `FX Return Mixer`, `Ultra FX Return Mixer` and `Mix Mixer`,
  adds or removes the mixes' own blocks, and rewrites the MixConfig copies in the header and scene safes. It
  does not touch the `FX Send Mixer`, the name managers, the FX racks, stored scenes, `Talkback.dat` or
  `SignalGenerator.dat`. Stale per-leg lines are kept by place. [save-proven]

### Input Mixer row length

`S = G + 4 x (mono FX + mono aux + mono matrix) + 5 x (stereo FX + stereo aux + stereo matrix) + 15 + 16 + 8`,
G the number of groups, plus 40 on Bridge-5 (eight Ultra FX sends). The formula gives every block length seen.
[save-proven] Record n is at payload +12 + S(n - 1).

The 15-byte main section: +0 LR assign, +1 M assign (LR+M), +2 mute, +3..4 fader, +5 pan [save-proven]; +6
always 0, +7 0 on exactly the inputs `InputConfig.dat` pairs (02 on every input of the LCR+ factory show),
+8 always 0x4A, +9..10 always `80 01`, +11..14 zero [seen; meanings of +7 and +9..10 unconfirmed]. Then 16
DCA bytes (1 = member) and 8 mute-group bytes [save-proven]. Bridge-5 adds eight Ultra FX sends,
`[on][pre][s16 level][pan]` each, reset `01 00 80 01 25` [save-proven].

### FollowPanSettings

`kind,index,follow,0` per stereo mix, index from 0, follow 1 on. Kind 18 is an Ultra FX rack, added by V2.01.
A send into a flagged mix holds the input's pan byte; one into an unflagged mix holds its own.
[seen in every file]

### Mix Mixer, FX Send Mixer, DCAs, FX returns

- `Mix Mixer` main record count by mode: 0 None, 1 LR, 2 in every mode past LR. A group feeds auxes, FX sends
  and matrices; an aux and a main feed only matrices; no group feeds a group. [save-proven by layout]
- `FX Send Mixer`: `[01]` then 16 records of 29 bytes (465 bytes always): +0..1 fader, +2 mute, +3..4 zero,
  +5..20 DCA 1-16, +21..28 mute groups 1-8. Record k is FX send k in the desk's order, mono first.
  [fader save-proven on record 1; DCAs by name; the rest seen in every file]
- `DCA Levels and Mutes` (97 bytes): version, 16 x `[mute][00][s16 level]`, then eight 4-byte mute-group
  records. Group n's engaged flag is [61 + 4n]. [save-proven]
- `FX Return Mixer`: the `Input Mixer` header and 32 records at the input stride: return n is records 2n-1 and
  2n, both legs holding the same mix except a send pan on the first leg. The return PEQ is
  `Parametric EQ, FX Channel NN`, an input PEQ block. [seen in every file]
