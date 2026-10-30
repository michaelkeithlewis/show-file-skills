# DM7 and DM5 field map

Field paths and encodings in DM7 family shows (DM7, DM7 Compact, DM5, DM5 Compact), contributed by markcarlberg
(pull request #2). The container is the one in [`FORMAT.md`](FORMAT.md) section 4. Nothing on this page is used by
`scripts/yamaha_tool.py`; the tool uses only the facts in FORMAT.md.

Every line says how it was found:

- **(save)**: one control changed in DM Editor 2.0, saved, and the bytes that changed were the ones named. This is the
  save-and-read test of FORMAT.md 1.
- **(load)**: a written file loaded in DM Editor 2.0 and showed the value.
- **(files)**: the same in every DM7 show and editor save at hand, but never moved by a save on its own. Treat it as a
  reading of the files, not a proven fact.

A reading that no file and no save has tested is not here. It is in `../dm7/README.md` under What we don't know.

## Container details

- Extensions: the DM7 console and DM7 Editor 1.x write `.dm7f`; DM Editor 2.0 writes `.dmxf`, the same container with a
  newer schema. The header model says which family a file is, not the extension. (files)
- Bytes 0x38 to 0x47 of the project header and of every inner MBDF file are a version-4 UUID, new on every save. Of
  399 seen, all carry the version-4 version and variant bits. A file that keeps the template's save ids loads and
  re-saves in DM Editor 2.0. (save)
- `ProjectInfo/Info` holds `ProductName`, `ProductSubName`, `OwnerName`, `Category`, `UnitMode`, `Split`, `Comment`,
  `TimeStamp`. (files)
- `#FILE` entry bytes 24 to 27 always hold the name length + 8, and byte 43 always holds 8. Their meaning is not known.
  (files)
- `.old` twins: every mix, setup, preset-list and scene-list entry has one. In every controlled DM Editor 2.0 save,
  each `.bup.old` holds the same data as its `.bup` from byte 72 on, under its own save id. For an entry the save did not
  change, the `.old` is the previous save's `.bup`. Scene and library preset entries have no twin. (save)
- A stream recompressed with another DEFLATE (fixed Huffman codes included) loads in DM Editor 2.0 when the entry's
  compressed length is updated and later entries move. (load) This agrees with BB-G2-ZLIB.
- Library preset files (`.dm7p`) use a scoped section header: bytes 24 to 27 give a scope length (24), and `MMSXLIT`
  follows the scope. The scope names the preset kind (`CH` or `MX`), the source strip and the block (`CH` strip, `HA`
  head amp). (files)
- A later DM7 firmware adds an 8-byte `Surround` table to every input channel (item 1,785 bytes, not 1,777), so `Mix`
  starts at 214,200 instead of 213,240. Every value reads the same by name. (files)

## What DM Editor 2.0 rewrites on save

- It always saves `.dmxf`. On a `.dm7f` upgrade it changes 23 values in `FX/FX[n]` (`MixBalance` and parameter words)
  with no user change. (save)
- Every MBDF file it rewrites gets a new save id, even with unchanged data. (save)
- `CnsSetup` view and selection fields move on every save. `Setup/Scene/Current.EditFlag` goes to 1 on the first edit.
  (save)
- Offline, two DM7 Control fields (jog wheel target, key bank) went back to their old values on the next save. (save)
- Broadcast Package controls (Fader CUE Release, Backstop PFL, Mix Minus) stay greyed offline, even with the licence
  flagged active in the file. Their fields can only come from a console save. (save)

## Models

- A DM7 Compact blank and a DM5 blank differ only in `CnsSetup/Course[c]/Overview/MeterBridge.DisplayMode` ("In"
  against "DM5:Input"). DM5 and DM5 Compact blanks do not differ in setup. (save)
- Every model's file holds the DM7's full tables (120 inputs, 48 mixes). A smaller model's blank carries the extra
  strips, patched and named `ch61`, `MX25` and so on. Take "in use" from the show, not from the table counts. (files)

## Layout of a show

Shorthand: `IC` = `Mixing/InputChannel[ch]` (120, ch 1 is item 0), `MX` = `Mixing/Mix[m]` (48), `MT` =
`Mixing/Matrix[t]` (12), `ST` = `Mixing/Stereo[s]` (4: ST A L, ST A R, ST B L, ST B R), `SET` and `CNS` = the setup
file's `Setup` and `CnsSetup` sections.

- Entries: `Current/CurrentBackupFile.bup` (about 400 KB: `Mixing`, `Process` with the OMNI head amps and output
  patches, `FX`, `PremiumRack`, `Scene`, `Preset`); `Setup/SetupBackupFile.bup` (about 750 KB: `Setup`, `CnsSetup`);
  `PresetList/PresetListBackupFile.bup`; `SceneList/SceneListBackupFile.bup`; `Scn/UserA/<GUID>.dm7s`;
  `Lib/InCh` and `Lib/OutCh` `<GUID>.dm7p`. (files)
- Top-level `Mixing` tables on the 1,777-byte input layout: InputChannel 120 x 1,777 at 0, Mix 48 x 647 at 213,240,
  Matrix 12 x 518 at 244,296, Stereo 4 x 743 at 250,512, DCA 24 x 88 at 253,484, Mute 12 x 64 at 255,596, then
  GEQRack2 32 x 439, Tempo, Dynamics (EXT IN keys), EffectRack, PremiumRack (4, or 6 in `.dmxf`), Console,
  DuganAutomixer, ChannelLink, DanteRemoteControl, PremiumRackDisplay, Cue, Monitor, ToPhones, CustomFaderBank,
  DM7ControlCustomFader, AIMixing. (files)
- Input channel children in order: Signal, Label, InPatch, VirtualSC, Input, Insert, DirectOut, HPF[4], LPF[4], PEQ,
  Proc, Dynamics[2], Delay, ToMix[48], ToMatrix[12], ToStereo, DCA, MuteGroup, Fader, (Surround), Automixer,
  ChannelLink. (files)
- Inputs have four banks of filters, EQ and dynamics (A and B, plus C and D for the Theater Package, picked by
  `PEQ.ActorSelect`); output strips have two. `PEQ.Select` picks the bank. (files)

## Encodings

- Levels (fader, send, DCA, PEQ gain, head amp gain): signed 16-bit, 0.01 dB, -32768 = -inf. Head amp floor -600
  (-6 dB). `On` is the bit after the level; mute is "not on". (save)
- Pan: signed 8-bit, L63 = -63 to R63 = +63. (save)
- HPF, LPF and PEQ frequencies: u32 in 0.1 Hz. Slopes: u8 dB/oct. Q: u16 in 0.001. Delay times: µs (1.00 ms = 1000).
  (save)
- Digital gain `Input.Gain`: signed 16-bit, 0.01 dB, -96 to +24 dB. (files)
- Icons: text 12 (`Blank`, `Kick`, `Snare` and so on). (files)

## Patch codes

A patch word is 32 bits: a kind in the top 12 bits, a sub-code in the next 8, an index in the bottom 12. Indices are
0 based (ch 16 is 0x0F). The output patch lives on the port, not the strip:
`Process/<device>/OutputPort[k]/Patch.Source`, devices Omni (16), AES (4), PY (64), USB (32), Dante (144), Recorder (2).
(save)

Input sources (`IC/InPatch/Bank[0..1].Source`, insert returns, talkback, key EXT IN, Virtual Soundcheck Playback In):

| Code | Source | Proof |
| --- | --- | --- |
| kind 0x014, sub 01, + index | OMNI IN (IN 5 = 0x01401004, IN 32 = 0x0140101F) | save |
| kind 0x01A + index | Dante input, up to 144 | save |
| kind 0x016, sub 01, + index | AES/EBU IN (0x01601000 and 0x01601001 seen as insert returns) | files |
| kind 0x01C + index | USB IN (0x01C00010 and 0x01C00011 seen as insert returns) | files |
| kind 0x06C + slot x 16 + side | FX rack output L or R (each reverb takes two slots: 0/1, 32/33) | files |

Signals on output ports and other source fields:

| Code | Signal | Proof |
| --- | --- | --- |
| 0x03C08000 + ch | input direct out (ch 9 = 0x03C08008) | save |
| 0x03C18000 + ch | input pre-DYN1 key feed (key-in OTHER PRE EQ; ch 5 = 0x03C18004) | save |
| 0x03C28000 + ch | input recording out ("R.Out n" on the patch page) | files |
| 0x03E00000 + n | mix n + 1 (MX45 = 0x03E0002C) | save |
| 0x04000000 + n | matrix n + 1 | files |
| 0x04200000 + 0, 1, 16, 17 | ST A L, ST A R, ST B L, ST B R | files |
| 0x05200000 + 0/1, 16/17 | MONITOR A L/R, MONITOR B L/R | B save, A files |
| kind + 0x100, slot in bits 12 to 15, + strip | insert send of slot A to D: 0x13C input, 0x140 matrix | input save, matrix files |

Insert slot codes (`Insert/Module[0..3]/Patch.Source`):

| Code | Slot | Proof |
| --- | --- | --- |
| 0x066, 8 x group in bits 12 to 19, slot x 16 + half | Premium Rack bank a to d (a `.dmxf` holds six), slot 1 to 16, L(A) 0 or R(B) 1: Premium a13 L(A) = 0x066000C0, b1 A = 0x06608000 | save |
| 0x068, (rack - 1) x 16 + half | EQ rack 1 to 32, A or B: EQ5 A = 0x06800040 | save |
| an input port code | outboard loop return; the send is the output port playing the strip's insert send | OMNI save, AES and USB files |
| 0x06400000 | outboard slot with no ports chosen | files |

## Inputs, pairs, head amps

- Pairs: `IC/Signal.Relation` 0x80 left half, 0x01 right half, 0 mono. Making a pair sets both halves' `GainGang` 1,
  `DelayGang` 1, `Relation` 128 and 1, and `ToStereo.PanType` from PAN to BALANCE. (save)
- L/R path: `IC/Signal.StereoInputType` `STEREO`, `MONO`, `L/L`, `R/R`, the same word on both halves. (save)
- Input A/B: `IC/InPatch/Bank[0]` is Input A, `Bank[1]` Input B; `InPatch.Select` 0 = A, 1 = B. Each bank has its own
  analog gain, +48V and gain compensation on the socket it patches. Digital gain and channel polarity are the
  channel's. (save)
- OMNI head amp: `Process/Omni/InputPort[port]/HeadAmp`: the `48V` bit before `Gain`, then `CompensationOn` and
  `CompensationGain`. Values -600 to 4000 seen. (save)
- Port processing ahead of the channel: each OMNI IN port has its own polarity (`Process/Omni/InputPort[k].Phase`,
  combined with `IC/Input.Phase`), HPF (`SET/Omni/InputPort[k]/HPF` `On`, `Frequency` in Hz x10) and M/S decode per
  odd/even pair (`Process/Omni/MSDecode[p].On`, `.SideGain`; p = 9 is IN 19/20). (save)
- Dante input patch: `SET/DanteNetwork/InputPort[n]/Patch/Source`: 0x44 in the top byte, unit in bits 12 to 23, port in
  bits 0 to 11. Dante 20 = 0x44002013, subscribed to an I/O rack's port 20. The device list is
  `SET/DanteRemoteControl/IOUnit[24]` (`ModelName`, `DeviceLabel`, `UniqueID`, `InPortNum`, `OutPortNum`). A Yamaha
  I/O rack's head amp is `Mixing/DanteRemoteControl/IOUnit[unit]/InputPort[port]/HeadAmp`, -600 to 6300 seen. (files)
- Delay: `Delay.On`, `.Time` in µs (0 to 1000 ms), `Delay/Insert.Point`. Display scale `CNS/Delay.Scale`: 0 meter,
  3 msec. (save)
- Direct out: `DirectOut.On`, `.Point`, `.Level` (signed 16-bit, 0.01 dB), `.FollowOn`, `.FollowFader`, `.FollowDCA`.
  The patch lives on the output port (0x03C08000 + ch), not on the channel. (save)
- Virtual Soundcheck: Playback In per channel is `IC/VirtualSC.Source` (an input port code). The recording out is an
  output port playing 0x03C28000 + ch. (files)
- +48V master: `SET/Unit[0].48VMaster`, 1 on, 0 off. (save)
- Factory input state, read from untouched strips: named `chN`, Blue, icon Blank, unpatched, polarity off, digital gain
  0; insert off at Pre DYN1; direct out off, 0 dB, Pre Filter; HPF off 80 Hz 12 dB/oct; LPF off 16 kHz 12 dB/oct; PEQ on,
  PRECISE, 125 Hz, 355 Hz, 3.55 kHz, 6.3 kHz flat, Q 1.4, shelves on at Q 4.0; DYN1 Gate off; DYN2 Comp 260 off; delay
  off at Pre Fader; every send on at -inf, Post ON, Follow on; To Stereo ST/M, CSR 50, pan centre; fader -inf, on.
  Buses: `MXn`, `MTn`, `ST A`, Orange, insert Pre Proc, PEQ 80 Hz to 10 kHz in octaves at Q 4.0, shelves off, Comp 260
  off, fader 0 dB. DCA `DCAn`, Yellow, 0 dB. Mute group `Mute n`. (files)

## Filters and EQ

- `HPF[b]`, `LPF[b]`: `On`, `Frequency` (u32, 0.1 Hz), `Slope` (u8 dB/oct). HPF 20 Hz to 2 kHz at 6, 12, 18 or 24;
  LPF 20 Hz to 20 kHz at 6 or 12. (save)
- `PEQ/Bank[b]`: `On`, `Type` text (`PRECISE`, `AGGRESSIVE` seen in saves), `Band[0..3]` on inputs and `Band[0..7]` on
  buses, each `Bypass`, `Frequency`, `Gain`, `Q`. (save) `Attenuator.Gain`: signed 16-bit, 0.01 dB. (files)
- `LowShelving.On` turns band 1 into a low shelf and `HighShelving.On` the last band into a high shelf. Each has its own
  `Q` x1000 (4.0 = 4000, the default). (save)
- `Proc.EQDynOrder`: 0 EQ then DYN2, 1 DYN2 then EQ. (save)

## Dynamics

Inputs have two slots, `IC/Dynamics[0]` (DYN1) and `[1]` (DYN2); a bus has one. Each slot: `Select`, `ActorSelect`,
`Bank[b]` with `Type` text, `On`, `MixBalance` (u8, 0 to 100 %), `Parameter[0..9].Value` (signed 32-bit), and
`KeyIn[b]`. Any slot can hold any of the eight types, and DM Editor 2.0's DYN1 menu offers all eight. (save)

| Screen | File `Type` | Words | Proof |
| --- | --- | --- | --- |
| Gate | `GATE` | 0 threshold 0.01 dB, 1 attack ms, 2 range 0.01 dB (-32768 = -inf), 3 hold µs, 4 decay µs | save |
| Ducking | `DUCKING` | the Gate's layout | save |
| Expander | `EXPANDER` | 0 threshold, 1 attack ms, 2 release µs, 3 ratio x10, 4 knee, 5 out gain 0.01 dB | save |
| Legacy Comp | `PM Comp` | the Expander's layout (-8 dB, 30 ms, 256 ms, 2.5:1 as 25, Soft-2 as 2) | save |
| Comp 260 | `Classic Comp` | 0 threshold 0.01 dB, 1 attack µs (3.148 ms = 3148), 2 release 0.1 ms (290.6 ms = 2906), 3 ratio x100 (8:1 = 800), 4 knee index (Soft-2 = 2), 5 out gain 0.01 dB | save |
| De-Esser | `DE-ESSER` | 0 threshold 0.01 dB, 1 frequency 0.1 Hz (6.3 kHz = 63000), 2 Q x1000 (3.2 = 3200), 3 type (0 Bell, 1 High Shelf) | save |
| FET Limiter | `FET LIMITER` | 0 input and 1 output in half-dB steps (-34 dB = -68); 2 ratio index (0 4:1, 1 8:1, 2 12:1, 3 20:1, 4 All); 3 attack index 0 to 78, µs = 800 - 10 x index; 4 release index 0 to 105, ms = 1100 - 10 x index; 5 In-Out Link | save, both ends of each law |
| Diode Bridge Comp | `DiodeBridgeComp` | 0 threshold in half-dB steps (-0.5 dB = -1); 1 ratio index (1 2:1, 2 3:1, 3 4:1, 4 6:1, 5 12:1); 2 recovery index (0 100 ms, 1 400 ms, 2 800 ms, 3 1.5 s, 4 auto1, 5 auto2); 3 gain in half-dB steps | save |

- A type switch in the editor carries some of the previous type's words over (Ducking took the Gate's values). Words the
  new type does not use are set to 0. A new Diode Bridge defaults to ratio 4, recovery 4, gain 0. The Diode Bridge has
  no attack, no release and no key filter. (save)
- The stock Gate: -26 dB, 0, -56 dB, 2.54 ms hold, 323 ms decay. (files)
- Older console shows have FET Limiter and Diode Bridge Comp only in DYN2. (files)
- Key-in `KeyIn[b]`: `SourceSelect` text `SELF POST EQ` (the strip), `MIX OUT` (`Source` = the mix code), `OTHER PRE EQ`
  (screen: Other Pre DYN1; `Source` 0x03C18000 + ch), `EXTERNAL INPUT 1` to `4` (each an input port at
  `Mixing/Dynamics/KeyIn/ExternalIn[k].Source`). `FilterType` `NONE` or `HPF`; `FilterFrequency` 0.1 Hz (125000
  default); `FilterQ` x1000 (700 default). (save)

## Tap points

One code list serves every point selector: sends, matrix sends, mix to stereo, inserts, direct outs, delay and cue. The
codes are not in signal order. (save)

| Code | Point |
| --- | --- |
| 30 | Pre Filter |
| 60 | Pre DYN1 |
| 80 | Pre Delay (outputs only) |
| 100 | Pre Fader |
| 110 | Post Fader |
| 120 | Post ON |
| 130 | Post Pan (cue) |
| 200 | Pre Proc (before EQ and DYN2) |
| 210 | Mid Proc (between EQ and DYN2) |

| Selector | Options seen in DM Editor 2.0 (default) |
| --- | --- |
| Input send pre point | Pre Filter, Pre DYN1, Pre Proc, Mid Proc, Pre Fader (100) |
| Send post point | Post Fader, Post ON (120) |
| Output send to matrix | Pre Filter, Pre Proc, Mid Proc, Pre Delay, Pre Fader, Post Fader, Post ON |
| Input insert `Insert.Point` | Pre Filter, Pre DYN1 (60), Pre Fader, Post ON |
| Output insert point | Pre Filter, Pre Proc (200), Pre Delay, Post Fader, Post ON |
| Direct out `DirectOut.Point` | Pre Filter (30), Pre DYN1, Pre Proc, Mid Proc, Pre Fader, Post Fader, Post ON |
| Input delay `Delay/Insert.Point` | Pre Filter, Pre DYN1, Pre Fader (100), Post Fader |

## Inserts and racks

- One insert per strip with four slots A to D chained at one point: `Insert.On`, `Insert.Point`,
  `Insert/Module[0..3]/Patch.Source`. A slot holds a Premium Rack processor, an FX rack effect, an EQ rack half or an
  outboard loop. (save)
- Input insert delay compensation (44 samples): `SET/DelayCompensation`. (save)
- Premium Rack: [`premium-rack.md`](premium-rack.md).
- FX rack (section `FX`): `FX/FX[16]`: `Bypass`, `MixBalance`, `Param.PluginName`, `.LibraryName`, `.SlotSize` (1 or
  2), `Param/Bank.Value` x64 signed 32-bit, `.TempoAssign`. Fed from `Mixing/EffectRack/Slot[16]/InputPort[2]/
  Patch.Source`; returns patch into input channels with kind 0x06C. Tempo: `Mixing/Tempo[5].Bpm`. FX delay times are
  in 0.1 ms. FX filter frequencies are indices on a 1/12-octave scale, 20 x 2^(n/12) Hz, HPF 0 = Thru, LPF 117 = Thru.
  (files)
- EQ racks: `Mixing/GEQRack2[32]`: `Type` `8BandPEQ` (default), `31BandGEQ`, `Flex15GEQ`; `SlotSize`, `ItemNum`,
  `AB[2]` `On` and `Patch.Source`; `GEQ.Limit` text; `GEQ/Band[31].Gain` signed 16-bit 0.01 dB; PEQ rack bands, shelves,
  HPF and LPF, `NotchFilter[4]`; `GEQLink`, `GEQLRLink`, `PEQLRLink`. The patch is save-proven; the rest is (files).
- A rack input is patched back to the strip: an EQ rack's `GEQRack2[r]/AB[h]/Patch.Source` holds the strip's insert send
  (0x13C00011 for ch 18). (save)

## Sends, To Stereo and buses

- Sends `IC/ToMix[0..47]`, `IC/ToMatrix[0..11]` (also on mixes and stereo legs to matrices): `On`, `Level`, `Pan`,
  `Pre` (0 uses `PostPoint`, 1 uses `PrePoint`), `PrePoint`, `PostPoint`, `FollowOn`, `FollowFader`, `FollowDCA`,
  `FollowPan`, `FollowPanMode`. A stereo destination writes both legs' sends. A channel pan change is written into every
  `ToMix[m].Pan` that follows it. (save)
- To Stereo: `PanMode` `ST/M` or `LCR`, `CSR` 0 to 100 (50), `PanType` `PAN` or `BALANCE` (switching to BALANCE set
  both legs' pans from -63/+63 to 0), `Pan` -63 to +63, `ToStereoA`, `ToStereoB`, `ToLCR`. A mix's `ToStereo.Point`
  uses the tap list, Post Fader (110) by default. Desk-wide pan law: `SET/PanNominalMode`. (save)
- `MX.BusType` `VARI` or `FIXED`. Switching a mix to FIXED makes the editor set every input's send to it to on, level 0
  (0 dB), and clear `Signal.PanLink`: a FIXED send is a switch at 0 dB. (save)
- A mix pair sets `DelayGang` 1 and `ToStereo.PanType` BALANCE (no `GainGang`); a matrix pair sets `DelayGang` 1. (save)
- `MX/Signal.PanLink`: input send pans follow the channel's. (save)
- A stereo mix in PAN mode can swap left and right (`ToStereo.Pan` 63 and -63). A matrix has only `Out.Balance`, one
  value on both halves, and cannot swap. (save)
- Mixes have 8-band PEQ, one dynamics slot with two banks, `SubIn` and `MixMinus/Owner.InputChannel` bits.
  `ST/ToMatrix` adds `PanType` and `FollowBalance`. ST B mono is `ST.Mono` on `Stereo[2]`. (files)

## DCAs, mute groups, channel link

- `DCA.Assign` 24 bits and `MuteGroup.Assign` 12 bits, on inputs and output strips. (save; the DCA bits agree with
  BB-DM-SAVE)
- `Mixing/DCA[0..23]`: `Label`, `Fader`, `DCAMuteTarget` (0 Post Only, 1 Pre & Post). (save)
- `Mixing/Mute[0..11]/Label.Name`. Masters in setup: `SET/MuteMaster[g].On`, `.DimmerLevel` (0.01 dB, -32768 = full
  mute, the default); any other value makes the group a dim of that depth. (save)
- Channel link: `IC/ChannelLink.GroupId` (0 none, A = 1); `Mixing/ChannelLink/Input[g]` is group g's record, with
  per-parameter bits (`.Fader`, `.Delay`, `.EQ` and more), `/HeadAmp.Gain`, `/ToMix[48].On`, `/ToMatrix[12].On`;
  `Output[g]` for output groups. Linking copies the first channel's linked parameters onto the others. (save)

## Monitor, cue, talkback, oscillator (setup file)

All (save) unless marked.

- Monitor A/B `SET/Monitor[m]`: `Source.Select` (0 based), `Source.Mode`, `/Define[8].Source` (signal codes) and
  `.Name`, `Level.FaderLevel` (dB x100), `Dimmer.On` and `.Level`, `Out.Mode` and `.LastLCRMode` (`LCR`, `ST Dmix`),
  `Out.CenterOn`, `OutPatch` (MAIN, ALT1, ALT2), insert, CUE/COMM interrupt.
- Monitor delay sits under the cue records: Monitor A at `SET/Cue[0]/Delay`, Monitor B at `SET/Cue[1]/Delay` (`.On`,
  `.Time` µs).
- Cue A/B `SET/Cue[c]`: `Mode` 0 MIX CUE, 1 LAST CUE (switching A switched B too); `Input.Point` (30 PFL Pre Filter,
  100 PFL Pre Fader, 130 Post Pan), `DCA.Point` (120 Pre Pan, 130 Post Pan), `Output.Point` (100 PFL, 120 AFL);
  `Input.Trim` (dB x100); `.FollowPan`. Per-strip cue destination: `CNS/Cue/CueButton/<strip>[n].Assign`.
- Talkback `SET/Talkback`: `SendAssign.Select` (0 based group), `/Define[g]` bit lists `Mix` x48, `Matrix` x12,
  `Stereo` x4 (0 and 1 ST A L/R, 2 and 3 ST B L/R), `Monitor` x2, `Directout` x2; `Dimmer.Level`,
  `DimmerForTalkback.Level` (`.dmxf` only) in dB x100; input `fromInput.Source`. The talkback HPF is the input port's
  HPF, and the talkback mic's gain and +48V are that port's head amp.
- Oscillator `SET/Oscillator`: `Mode` `SINE 1CH`, `SINE 2CH`, `PINK NOISE`, `BURST NOISE`; `Level` x2 (dB x100);
  `SineWave[k].Frequency` (Hz x10); HPF and LPF; `SendAssign` bit lists as talkback, plus `InputChannel` x120.

## Output ports

- OMNI and AES OUT: `SET/Omni/OutputPort[k]` and `SET/AES/OutputPort[k]` `.Gain` (dB x100) and `.Phase`.
  `SET/Console/Omni.OutputLoadImpedance` `10k` or `600`. (save)
- Output delay is a pool of 20 shared across OMNI, AES and Dante: `SET/OutputProcessing[p]` `.Assign` (OMNI OUT
  0x01400000 + (n-1), AES OUT 0x01600000 + (n-1), Dante OUT 0x01A00000 + (n-1)), `/Delay.On`, `.Time` µs. A Dante OUT
  has no port gain or polarity of its own: its `.Gain` and `.Phase` sit in its pool slot. (save)

## Dugan automixer

- `IC/Automixer.Assign`: the automixer channel, 1 based; 0 none. (save)
- `Mixing/DuganAutomixer/Channel[64]`: `Group` 0 a to 4 e, `Weight` in half-dB steps, `ChMode` 0 manual, 1 auto
  (default), 2 mute, `ChModePreset`, `Override`, `Bypass`. (save)
- Group masters `SET/DuganAutomixer/Master[g]`: `Override`, `Mute`, `Bypass` (`.dmxf` only). (files)

## Scenes and libraries

All (files).

- A scene `Scn/UserA/<GUID>.dm7s` holds the current mix file's header with kind `Scene` and its own save id, then
  sections `Scene`, `Mixing`, `Process`, `FX`, `PremiumRack` in the current mix's schema, then `#END`.
- Scene list: `SceneList/Bank[2]/Info[500]`, `FileName` (the GUID) and `SceneNumber` text (`5.00`, sub-scenes such as
  `14.50`). An empty row is no scene. DM Editor 2.0 blanks hold no scene.
- Scene section: `Info` (`Title` text 64, 16 characters on screen; `Comment` 128; `Protect`; `TimeStamp`), `Focus`,
  `Fading` and `IndividualFading`, `GPI`, `Playback`, `SceneLink`, `MIDI`, and `DCA[24]/AssignedBitmap`
  (`InputChannel` u32 x4, `Mix` x2, `Matrix`, `Stereo`, lowest bit first), which matches the strips' `DCA.Assign`.
- Current scene: `SET/Scene/Current.EditFlag`, `SET/Scene/Bank[b]/Last.SceneNumber`,
  `CNS/Scene/Bank[b].SelectedScene`, `SET/DM7Control/Scene/Bank[b].RemoteSelectedScene`; Global Paste groups
  `CNS/Scene/GlobalPasteGroup[g].Select`. Recall safe is desk-wide in setup (`SET/RecallSafe[2]`, per strip
  `SET/InputChannel[n]/RecallSafe[2]`), one set for all scenes.
- The preset list has a fixed table per kind (`User/CHInput`, `User/CHOutput`, factory lists, one per Premium
  plug-in), each 100 rows of one 40-byte `FileName`.

## Surface, setup and PY slot

- Custom fader banks: `Mixing/CustomFaderBank/Course[bay]/CustomFader[n]/Bank[b]` `ChID` x12 and `LabelName`; main
  faders `.../Master/MasterFader.ChID`. Channel ids: category << 24, index << 16: 0x0C input, 0x10 mix, 0x14 matrix,
  0x18 stereo leg, 0x1C DCA. ST A = 0x18000001, ST B = 0x18020001, input 41 = 0x0C280000. (files)
- User keys are text records `FUNCTION,PARAM1,PARAM2,` (for example `SENDS ON FADER,MIX 5`) in `CNS/UserDefined`;
  DM7 Control keys in `SET/DM7ControlUserDefined`. (files)
- DM7 Control: `SET/DM7Control/Course.ControllerMode` 0 Side Car, 1 Remote; `JogWheel.Target` `TOUCH AND TURN` or
  `SCENE LIST`; `Panner.Target` `AFC IMAGE` or `5.1 SURROUND`; `Panner/Encoder.Target` `WIDTH` or `LFE`;
  `Scene.DecIncBehavior` `WITHOUT_RECALL` or `WITH_RECALL`. (save)
- PY slot: `SET/PY.CardName` (empty for none, `PY64-MD`, `PY64-D` and others). Each card family's settings table sits
  in Setup whatever is fitted. PY64-MD: `Redundancy/Input.On`, `InputPort[p].RateFs` (1, 2), `OutputPort[p].Frame` (0
  same as input, 96000, 48000), `.Channel` (0, 64, 56). PY64-D's own Dante settings are greyed offline. (save)
- Licences `CNS/TemporaryLicense/DEK-DM7-TH`, `DEK-DM7-BR`, `DEK-DUGAN` `.Active`; unit mode `CNS/Unit.Split` and
  `SplitPoint`; word clock `SET/WordClock.Source` (`DANTE96000`); Dante `SET/DanteNetwork/Config` (`DeviceID`,
  `BitDepth`, `ReceiveLatency` in 0.01 ms, `NetworkFs`). (files)

## Firmware differences

What later schemas add, oldest console schema first, then later console firmware, then `.dmxf`. (files)

| Where | Added in | What |
| --- | --- | --- |
| `IC/Surround` (8 bytes per input), `Mixing/SurroundCue`, `SET/MixingMode`, `SET/Surround*` | later console firmware, `.dmxf` | 5.1 surround |
| `SET/ImmersiveSound`, `CNS/ImmersiveSound`, Scene `ImmersiveSound` | later console firmware, `.dmxf` | AFC Image |
| `SET/PY/InOut`, `SET/PY/Dante`, `SET/MonitorMix/MixBus` | later console firmware, `.dmxf` | PY SRC, PY64-D clock, MonitorMix permissions |
| PremiumRack and its Setup tables, 4 to 6 groups | `.dmxf` | Premium DSP |
| `AIMixing/AutoComp`, `CustomFaderBank/Course/PlusOneFader`, `SET/Talkback/DimmerForTalkback`, `SET/DuganAutomixer/Master.Bypass`, `CNS/TemporaryLicense/DEK-DUGAN` | `.dmxf` | Assist, surface, talkback dimmer, Dugan licence |
| `SET/DanteRemoteControl/IOUnit` item 1,153 to 3,209 bytes | `.dmxf` | Rio output processing |
| `CNS/Cue/FaderCueRelease`, `BackstopPFL`; DM7 Control keys in `CNS/UserDefined` | oldest only | moved to `SET/CueCommon` and `SET/DM7ControlUserDefined` later |
