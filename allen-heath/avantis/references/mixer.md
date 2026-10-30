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
