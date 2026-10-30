# dLive mixer config + mix routing (Director V2.12, show Version 14)

Tool: `scripts/dlive_mix.py` (+ `dlive_safes.py`).
Ground truth: Director's own mixer config change on a real show (stereo FX 4->3, stereo aux 3->7). The
conversion matches Director's output byte for byte everywhere except sections edited by hand in between and
Director's Digital Attenuator 5->7 byte format upgrade.

## Files a config change touches

- `Show/MixConfig/MixConfig.dat`: `[1, MG, SG, mFX, sFX, mAux, sAux, m7, mode, sMtx, mMtx, PAFL, 23]`.
  Byte 8 is the main mix mode: 0 none, 1 LR, 5 5.1, 6 LCR+. Byte 11 is the stereo PAFL count. Buses per main
  mode come from `sMixerConfigurationSettings::GetNumberOfMainMixChannels` @0x1005676f0: none 0, LR 2, 5.1 6,
  LCR+ 4. `MixConfig.buses_used` counts the main and PAFL buses from these bytes, so a show with no main
  (the A&H factory Monitors show) passes the 64-bus check.
- `Show/FollowPanSettings/FollowPanSettings.dat`: text, `1` then `type,index,a,b` per stereo mix in the
  order stereo aux (5), stereo FX (7), UFX 0-7 (19), stereo matrix (11).
- `Show/SceneSafes/StageBox*.dat` (6 files, 122093 bytes): remapped (below).
- Live scene `StageBoxScene65535` only. Director leaves stored scenes in their old config; every
  section carries its own counts and Director fits filters at recall
  (`cTLDStageBoxSceneManager::SetRecallFilters` calls `FitFilterToMixerConfig`).

## Scene file

`[header: 01 01 name, notes ..., 0x15 + 13-byte mixer config + 122077-byte recall filter][01][u32be chain
length][sections][1 trailing byte]`. Section = u16be len (label + NUL + payload), label, NUL, payload.
The u32 = bytes of the section chain (it is not a checksum).

## Bus order (sMixerConfigurationSettings::GetBusNumberForMix @0x100568990)

Mono groups, stereo groups (2 buses), mono FX, mono aux, stereo FX, stereo aux, main (2 for LR), PAFL
(2 per stereo PAFL), mono matrix, stereo matrix. 64 buses total.

## cMixer: Input Mixer / FX Return Mixer / AHFX Return Mixer

Header 12: `[ver, MG, SG, mFX, sFX, mAux, sAux, mMtx, sMtx, x, x, x]`. Per channel (128 / 32 / 16):
group assigns (MG + SG bytes), sends in order mono FX, mono aux, stereo FX, stereo aux, mono matrix,
stereo matrix (mono 4 bytes `[on, pre, level s16]`, stereo 5 bytes `+ pan 0-74, 37 centre`), 47-byte
channel section, 8 x 5-byte UFX sends (ver >= 3). Config change: carry by (type, number); new sends
`01 00 8001 (25)`.

## cMixMixer: Mix Mixer (GetStatus @0x1002cf6f0, version 4)

Header 11: `[4, MG, SG, mFX, sFX, mAux, sAux, mMtx, sMtx, mains, mainStereo]`.
Mixes in order MG, SG, mAux, sAux, Main, mMtx, sMtx. Per mix:
- groups: mono sends (mFX then mAux), stereo sends (sFX then sAux), 5 bytes each
- groups, aux, main: matrix sends (mMtx then sMtx), 5 bytes each
- groups: group-to-group (MG + SG bytes), main assign (1 byte, default 3)
- every mix: 16-byte strip `[main on, main mono on, mute, fader s16, pan, ?, mono flag, 4a, 8001, 0000,
  25, b, b]` + 24 DCA + 8 mute groups
- after all mixes: 8 x 5-byte UFX sends per group
Field names from cMixMixer::GetMainOn (+0xa8e), GetMainMonoOn (+0xa8f), GetMainMute (attr +0),
GetDCAGroupAssign (attr +1). Parses byte-exact on 7 configs (FOH and monitor shows from
several tours, including a MultiSurface show). A 2024 firmware 1.x show is Mix Mixer v2 (firmware 1.x): not supported.

## Per-mix processing sections

`Parametric EQ, <mix ch>`, `Graphic EQ, ...`, `Compressor, ...` (each a block over every mix channel),
then per mix channel `Mix Delay`, `Digital Attenuator`, `Compressor side chain source`, `Insert`, then
`Send Source Select, <mix>` over MG, SG, mFX, mAux, sFX, sAux, Main, UFX 1-8. Mix channel labels:
`Mono Group Channel 01 ` (mono = trailing space), `Stereo Aux Channel 04 Left`, `Main Channel 01 Left`.
Defaults are read from Director's fresh stereo aux; side chain default = `01 <strip type> <index>`
(self). FX sends have no processing.

## Scene safes (FitFilterToMixerConfig @0x1005a60e0, writer operator<< @0x100598410)

File = `01 01 15` + 13-byte config + body, in this order: 128 inputs x 521, 64 mixes x 518, FX 32,
16 FX sends x 37, 32 FX returns x 510, DCA, other, UFX, 8 UFX sends x 37, 8 UFX returns x 510, 1 byte.
Input/return record: 3 own bytes, 64 group-assign bytes (by bus), 64 aux/FX-send triplets, 64 matrix
triplets, tail. Mix record: 3 bytes, 64 aux triplets, 64 matrix triplets, 64 bytes, tail.
Fit: per-bus columns move to the mix's new bus; mix records move whole; new mixes start clear;
PAFL is never carried; FX send records copy by mono / stereo index. Reproduces Director exactly
on all 6 safes files of the V1 -> V1 01 pair.

## Not covered

Writing a main mode other than LR (the bus count reads them; the writers refuse them), show formats before Version 14, surface strip layouts pointing at removed
mixes (Director shows them blank), parameter-level decode of mix PEQ/GEQ/compressor values.
