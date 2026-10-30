# RIVAGE PM field map

Field paths and encodings in RIVAGE PM shows (`.RIVAGEPM`), contributed by markcarlberg (pull request #2). The
container, the sections and the tested values are in [`FORMAT.md`](FORMAT.md) 4.7 to 4.10 and 1.4; this page does not
repeat them. The DM7 field names are in [`dm7-fields.md`](dm7-fields.md), and "as DM7" means the same field name and
encoding. Nothing on this page is used by `scripts/yamaha_tool.py`.

The files read were about 24 console and editor saves and ten RIVAGE PM Editor blanks. Every line says how it was found:

- **(save)**: a controlled save in RIVAGE PM Editor moved the value, or the editor showed it on a written file.
- **(files)**: the same across those files, but never moved by a save on its own.

Untested readings are in `../rivage-pm/README.md` under What we don't know.

## Models, engines and files

- One file family serves the PM10, PM7, PM5 and PM3: `.RIVAGEPM`, and the older `.PM10ALL` (R3.01k). Surfaces seen:
  `CS-R10`, `CS-R5`, `CS-R3`, `CSD-R7`. Engines: `DSP-R10`, `DSP-RX`, `DSP-RX-EX`, and the PM7's own `CSD-R7`. (files)
- Counts come from `Unit/ChannelInfo` (InputChannel, MixBus, MatrixBus) in `Current/Status_2`. (files)

| Engine | Inputs / mixes / matrices | Plug-in racks run | Proof |
| --- | --- | --- | --- |
| DSP-RX-EX | 288 / 72 / 36 | 32 (512 units) | files |
| DSP-RX | 120 / 48 / 24 | 24 (384) | files |
| DSP-R10 | 144 / 72 / 36 | 24 (384) | files, editor blanks only |
| CSD-R7 (PM7) | 144 / 60 / 36 | 24 (384) | files, one PM7 console save |

- Table sizes are the engine family's, not the engine's: every DSP-RX and DSP-RX-EX file holds `InputChannel[288]`,
  `Mix[72]`, `Matrix[36]`, `Stereo[4]`, `DCA[24]`, `Mute[12]`; DSP-R10, PM7 and `.PM10ALL` files hold
  `InputChannel[144]` with the same 72 and 36. Take the show's size from the engine record. (files)

## Container, against the DM7

- The header version is the software that wrote the file, not the console firmware. The `.PM10ALL` holds 0. Each inner
  entry is `#YAMAHA MBDFBackup` with model `PM10` on every desk. (files)
- `#MMS FACADE` sections have the `#MMS FIELD` layout byte for byte. (files)
- In console saves and DSP-RX or DSP-RX-EX blanks, `CurrentParam_1` equals `_2` but for the save id, a few `EN00/sinf`
  bytes and, in a few files, some `EN00/mix` bytes. In an editor-made DSP-R10 file (R10 and PM7 blanks) `_2` has the
  R10 shape (1,818,900 bytes, 144 inputs) and `_1` is a full-size factory state (2,549,492 bytes) that the editor never
  brings into step. The setup pair behaves the same. (files) The write rule in FORMAT.md 4.7 still holds: write both.
- `Snapshot/` entries come last, in name order. `Snapshot/InitialSceneData.dms` is in every file and in no list. `Setup/
  FileInfoList` and `Setup/PlayList` are the 2-track recorder's song list and play list. (files)

## Sections

| Section | Holds |
| --- | --- |
| `EN00/mix` | the mix: 566 fields, 354 of them named as in the DM7 `Mixing` section |
| `EN00/proc` | engine outputs: `HC[4]/OutputPort[256]` (HY), `MY[2]/OutputPort[16]`, `TL1G/OutputPort[128]`, `LocalIO[2]` (`MY[2]`, `DA[8]`, `AES[8]`, `2TrRec[2]`) |
| `RIO000` to `RIO011`, `RIO100` to `RIO111` | rack slots on the first and second TWINLANe networks |
| `CSIO00`, `CSIO01` | the surface's own I/O units |

All (files). Setup sections: `stup` (surface), `EN00/stup` (engine), `EN00/ovly`, `EN00/bkup`, and `RIOnnn/stup` and
`CSIOnn/stup` (unit settings) with their `bkup`.

No mirror setting exists in the launcher or in SYSTEM CONFIG (save). In blanks `EN01` equals `EN00`; in every show seen
it holds a new show's defaults and `EN01/pp` reads `Mix-DSP` (files).

## Identity, versions and schemas

- Console save: `Status_2` `EN00/pp/Specification/Unit` names the engine (`ProductName`, `FirmwareVersion`);
  `cst/Version/App.Version` is the surface firmware; `EN00/sinf/Info` has `ProductName` the surface and
  `ProductSubName` the engine. (files)
- Editor save: the engine block reads `Mix-DSP` with no firmware; `cst` holds the editor's version;
  `sinf/Info.ProductName` reads `Editor` or `CS-R5 Editor`, and `ProductSubName` reads `DSP-RX-EX` whatever was chosen.
  The source console's firmware is not kept. (files)
- Any save: the surface is `EN00/stup/ConsoleNetwork/LocalIO[0].ProductName`, and the engine shows in the
  `Unit/ChannelInfo` counts. Two blanks that differ only in engine differ only in `Status_2` `EN00/pp` and the save id.
  (save) `EN00/pp UnitStatus/Mirroring.RunningMode` is 1 on console saves, 0 on editor saves. (files)

Schema MD5 by firmware (first four hex digits), (files):

| Schema | Firmware | Adds |
| --- | --- | --- |
| `f53d` | V5.00, V5.03, V5.11, V5.14 | strip items laid out differently from V7 |
| `e715` | V6.11, V6.60, V6.71 | dynamics `TypeNo`, `Parameter[10]`, `Out.Phase`, custom faders in the mix |
| `a084` | V7.00, V7.20 | `Mix/ToMix` (mix-to-mix sends) |
| `ac76`, `7381` | PM7 CSD-R7 V5.14; `.PM10ALL` R3.01k | their own |

## Inputs and the input patch

`EN00/mix:InputChannel[k]` is as DM7 plus `Insert[2]`, `Dynamics[2]`, `Surround`, `ImmersiveSound`.
`InPatch/Bank[2].Source` is Input A and B; `InPatch.Select` on means Input B is live, an alternate input separate from
Virtual Soundcheck. (files)

| Code | Source | Proof |
| --- | --- | --- |
| kind 0x014, sub 01 or 02 | the surface's units (`CSIO00`, `CSIO01`), index card x 8 + port | files |
| kind 0x02A, sub 00, 08, 10, 18 | HY slot 1 to 4, index = port (0 to 255) | files |
| kind 0x066 | a Premium Rack output (effect return) | files |

## I/O racks, HY slots and head amps

All (files).

- `RIOnnn/proc`: `Pancake[6]` card slots of `InputPort[16]` (`Phase`, `HeadAmp` `48V` and `Gain`, `Silk` `On`,
  `Texture`, `Type`, gain compensation), `MSDecode[8]`, `OutputPort[16]/Patch`; `MY[2]`; `HC[2]/OutputPort[256]`.
  `CSIOnn/proc`: `Pancake[3]` of 8 ports.
- Mounted hardware in `EN00/stup`: `DSPUnit/HC[0..3].CardName` (the engine's HY slots 1 to 4; empty when none),
  `DSPUnit/MY[m].CardName`, `SnakeNetwork[0]/IOUnit[n].ProductName` with `HC[0].CardName`, `Pancake[0..5].CardName`
  and per-slot `WithRecall`. Blanks mount no rack and no HY card. The card list can be stale against the patch.
- A head amp belongs to the port (`.../Pancake[slot]/InputPort[port]/HeadAmp`, encoded as DM7), found from the
  channel's `InPatch`. The SILK mic card has no pad field. SILK and compensation have no per-mount default.
- `Unit.48VMaster` is 0 in every file, condenser shows included.
- Remote Dante head amps: `EN00/mix:DanteRemoteControl/IOUnit[48]/InputPort/HeadAmp`.

## Output patch, port names, TWINLANe

| Output source code | Signal | Proof |
| --- | --- | --- |
| 0x03E + mix, 0x040 + matrix, 0x042 + 0, 1, 16, 17 | mix, matrix, ST A L/R, ST B L/R | files |
| 0x03C08000 + ch | a channel direct out | files |
| 0x03C28000 + ch | a channel recording feed; 1,379 of 1,383 sit on the HY port that channel plays back from | files |
| 0x05200000 + 0, 1, 2 / 16, 17 | MONITOR A L, R, C / MONITOR B L, R | save |
| 0x05000000 + 0 / 16 | CUE A / CUE B | save |
| kind + 0x100 | a strip's insert send | save |

- Surface card outputs (`CSIOnn/proc`) are unpatched in every file; the surface's outputs are `EN00/proc` `LocalIO`.
  (files)
- Port polarity, gain, delay and names (`Label.PortName`, `SignalName`) are setup records as DM7:
  `RIO0nn/stup/Pancake[slot]/OutputPort[port]`, `CSIO0u/stup/...`, `EN00/stup/MY[m]/OutputPort[k]`. HY and AES outputs
  hold none. (files)
- TWINLANe: `EN00/stup/AssignToSnake/IOUnit[rack]/Pancake[card]/Port[port]` `Permission`, plus `On` on input cards.
  SYSTEM CONFIG's PULL then APPLY sets both. (save) A port not pulled never reaches the engine. (files)

## Tap points (save)

30 Pre Filter, 50 Pre EQ (the default insert point), 60 Pre DYN1 (an output's PRE DYN), 70 Pre DYN2 (inputs only), 80
Pre Delay (output inserts only), 100 Pre Fader (the default pre point), 110 Post Fader, 120 Post ON. One list serves
inserts, sends, direct outs and delay. The DM7's 200 and 210 never occur. Strip order: HPF and LPF, EQ, DYN1, DYN2,
delay, fader, ON, with no reorder switch. Send pre points FILTER, EQ, DYN1, DYN2, FADER; post points FADER, ON.
`Mix/ToStereo.Point` is 110 on every mix.

## EQ, filters, A/B and Theatre banks

- `PEQ/Bank[2]` on every strip, bands and shelves as DM7; `Type` PRECISE, SMOOTH, LEGACY, AGGRESSIVE. (files)
- `PEQ.Select` and `Dynamics[k].Select`: 0 bank A, 1 bank B. `HPF[2]` and `LPF[2]` are the A/B banks, not two filters,
  and follow the EQ's button. (save)
- `TheatreSelect` is Theatre mode's A to D choice (C = 2), not the A/B button. Theatre mode is console-wide (UNIT MODE:
  DEFAULT or THEATRE; the editor restarts). UNIT MODE did not appear in the diff. (save)
- Theatre banks live in the setup: `EN00/stup/InputChannel[k]` holds four banks each of `HPF`, `LPF`, `PEQ/Bank` (with
  `Label.Name`) and each dynamics slot's `Bank` and `KeyIn`, plus `TheatreMode` (`PlayerLibraryName`, `BankLink`).
  (files)

## Dynamics

- Inputs have `Dynamics[2]` (DYN1, DYN2), each with `Bank[2]` and `KeyIn[2]`; buses have one slot. Typed tables
  (`Gate`, `Ducking`, `Expander`, `PM_Comp`, `Classic_Comp`, `DeEsser`) as DM7, with `Type` text naming the loaded one.
  (files)
- From V6, `TypeNo`: 0 PM Comp, 1 Classic Comp, 2 GATE, 3 DE-ESSER, 4 EXPANDER (files); 6 FET LIMITER, 7 DIODE BRIDGE
  (save). Those two have no table: `Type` stays `Classic Comp` and the settings are `Parameter[k].Value` in the DM7
  layout (save). For other types `Parameter[10]` is a stale default copy, and the editor shows the typed table (save).
- DYN2 menu: LEGACY COMP, COMP260, GATE, DE-ESSER, EXPANDER, DUCKING, FET LIMITER, DIODE BRIDGE. (save)
- Gate `Range` -32768 is -inf; knee text HARD, SOFT-1 to SOFT-5. `KeyIn` as DM7, with codes 0x03C18000 + ch (another
  channel) and kind 0x402 sub 01 (an input port). (files)

## Inserts

- `Insert[2]` on inputs, mixes, matrices and stereo, each the DM7's 18-byte record: eight slots a strip, insert 1's four
  in series, then insert 2's. (files)
- Module codes: 0x066 Premium Rack slot, 0x068 EQ rack, 0x02A HY port (outboard return), 0x028 MY port, 0x06400000
  outboard with no ports chosen (the editor's `----`). (files) 0x028 sub 01 index n is an outboard loop over the
  surface's MY card, CS1:MY1-(n+1). (files)
- Insert send: `(kind + 0x100) << 20 | (insert x 8 + module) << 12 | strip index`. Ch 1 insert 2 slot D = 0x13C0B000,
  MX 1 = 0x13E00000, ST A = 0x14200000 and 0x14200001. (save) An outboard loop is an HY return module with the same
  strip's insert send on an HY output. (files)

## Buses, mains, DCAs, pairs, safes

- `Mix[72]` as DM7 plus `Out.Phase`, `SubIn`, `MixMinus/Owner`, `ToMix[72]` (V7, never live in a file seen),
  `ToStereo.ToStereoA` and `ToStereoB`, and `ToLCR`. `BusType` VARI (aux) or FIXED (group). (files)
- `Stereo[4]` is ST A L, R and ST B L, R; one ST setting writes `Stereo[0]` and `[1]`. `Stereo.Mono`;
  `Stereo/ToMatrix` adds `FollowBalance` and `FollowBalanceMode`. (save)
- Pairs: `GainGang` and `DelayGang` on paired inputs, `DelayGang` on paired buses; 970 of 984 paired mix halves send to
  stereo with `PanType` BALANCE. DCAs, mute groups and channel link as DM7. (files)
- Safes, one set for all scenes: `EN00/stup/<strip>[k]/RecallSafe.On`, `MuteSafe`, `SoloSafe`; `EN00/stup/Isolate`;
  scope `EN00/stup/RecallSafe`. (files)

## Custom fader banks and masters

- `Course[3]/CustomFader[5]/Bank[6]/Strip[12].ChID` and bank `Label.Name`: in `EN00/mix` from V6 (name 8 bytes), in
  the surface's `stup` before (64 bytes). (files)
- `Course[0]` is bay R, `[1]` C, `[2]` L. (save, PM10 session)
- `ChID`: kind in the top byte, strip below in twelves (`0107000A` is input 7 x 12 + 10, channel 95). Kinds 1 input,
  2 mix, 3 matrix, 4 DCA, 5 stereo leg (files); 7 cue master (CUE A 0, CUE B 2), 8 monitor master (MON A 0, MON B 3)
  (save). Master faders: `EN00/mix:MasterFader[2].ChID`.

## Monitor, cue, talkback, oscillator, Virtual Soundcheck

- `EN00/stup:Monitor[0]` and `[1]` (MONITOR A, B) as DM7, with eight DEFINEs of output codes. The monitor delay sits
  at `Cue[m]/Delay`. (files)
- `Cue[0]` and `[1]` (CUE A, B): points and `Mode` (`MIX`, `LAS`) as DM7 (files); `Out.Mode` `STEREO` or `MONO`
  (save). Per strip A, B or both: `CueButton/<strip>.Assign`, `DCA[24]` included (save).
- `Talkback[0]` and `[1]` (A, B), each the DM7's single talkback: eight groups `SendAssign/Define[8]` (bits `Mix` x72,
  `Matrix` x36, `Stereo` x4, `InputChannel`, `Monitor`, `Directout`), the group in use `SendAssign.Select` (from 0),
  two dimmers, `fromInput.Source`. (files)
- The talkback mic is the surface's TALKBACK IN: `CSIO00/stup/Talkback[0]` holds its `HeadAmp` (`Gain` 0.01 dB, `48V`)
  and `HPF` (`On`, `Frequency` Hz x10). (files)
- `Oscillator` as DM7; `SineWave[k].Frequency` in 0.1 Hz. (files)
- Virtual Soundcheck as DM7: `InputChannel/VirtualSC.Source` (playback port), record send on an output playing
  0x03C28000 + ch, no tap field (files). `VirtualSC.Safe` set is the channel's PATCH > RECORDING tick cleared;
  `EN00/stup:VirtualSC.MasterOn` (a bit; a byte on the DM7) is the switch (save).

## Racks and plug-in mounting

- One pool, `EN00/prem/PremiumRack2[32]/PlugIn[16]`, the DM7's 569-byte record (rack item 9,104 bytes, `LR[2]` 275
  bytes at +19 with `Parameter[64]`). There is no FX rack: reverbs and delays are plug-ins. `PluginName` is 17 bytes, so
  long names are cut. A plug-in sits on its first slot, spans `SlotSize`, starts anywhere and never crosses a rack
  (1,792 mounts). (files)
- Slot code: 0x066 in bits 20 to 31, rack (from 0) x 8 in bits 12 to 19, slot x 16 + half in bits 0 to 11 (half 0
  L(A), 1 R(B)); rack 32 slot 15 B = 0x066F80E1. Racks show as a to x, then A to H. (save)
- Feeds `EN00/mix/PremiumRack[32]/Slot[16]/InputPort[2]` and `KeyInInput[2]`. EQ racks `EN00/mix/GEQRack2[48]` as DM7,
  code 0x068, index rack x 16 + half. (files)
- `Status_2` `cs/PremiumRack/ResourceMeter`: `Effect.MaximumSlot` 512 or 384, `GEQ.MaximumSlot` 48, `UsedSlot` (racks
  the engine runs only). (files) A DSP-RX file can carry mounts in racks 25 to 32, left by a DSP-RX-EX session. (save)
- Dugan: `GEQRack2[0].Type` `Automixer32`, `SlotSize` 16. A channel joins through insert 2 with 0x06800000 + (n / 2)
  x 16 + n % 2 (automixer channel n), back-patched in `GEQRack2[0]/AB[0]/Patch`; settings in
  `DuganAutomixer/Channel[64]`. (files)
- Plug-in parameter words: [`premium-rack.md`](premium-rack.md).

## Scenes

All (files). FORMAT.md 4.9 has the tested part.

- `Snapshot/<id>.dms` has a 72-byte head (`#YAMAHA MBDFScene`, `Rivage` at 0x24, a version at 0x34, a save id), 59
  sections and `#END`. The version is the firmware that stored that scene; one file holds V5.00 and V5.11 scenes side
  by side.
- 30 `#MMS FIELD` sections and 29 `#MMS FILTER` sections (one per FIELD but `BAN`). The FILTER mask is zero in 225 of
  231 scenes. `BAN` holds `Info` (`Protect`, `Title`, `Comment`, `TimeStamp`), `Focus` and `Fading`.
- Scene list `EN00/slst`: `SceneList/Bank[1]/Info[1000]`, `FileName` (40 bytes) and `SceneNumber` (8 bytes), in console
  order, not numeric order. `_1` can hold more or fewer rows than `_2`.
- `Info.Protect` 1 is write protection. There are no factory scenes. Last recalled: `EN00/stup/Scene`
  (`Last.SceneNumber`; `0.00` with no scenes).

## Libraries and status

- `LibraryList_2` and `_1` (`EN00/llst`) index `Lib/<kind>/<id>.pst`: InCh, OutCh, InEQ, OutEQ, Dyna, GEQ, plug-in
  kinds, UsrSet. `EN00/stup:WordClock.Source` reads `INT96000` in blanks and `HCSLOT1` for HY slot 1. (files)
- `Status_2` is run-time state (units found on TWINLANe and Dante, meters, lock PINs). An editor save lists no units.
  (files) `vl/ChannelLink/RelativeValue` and `cs/Cue/CueButtonRotate` are status copies of mix and setup values. (save)

## What RIVAGE PM Editor does (save)

- With PM7 remembered, the DSP choice is hidden but the last DSP picked is still used, so a PM7 file can carry another
  engine's counts. A new offline session restores the previous session's state, across engines.
- A DSP-RX session offers racks a to x only. Mix-to-mix sends and the Dugan cards are greyed on a fresh show.
- A file whose HY cards or racks differ from the session raises SYSTEM CONFLICT. Loaded with the file's system settings,
  SYSTEM CONFIG shows its cards. An empty slot shows as HY SLOTn BLANK.
