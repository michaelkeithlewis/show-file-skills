# DM3 field map

Field paths and encodings in DM3 and DM3 Standard shows (`.dm3f`, scenes `.dm3s`, presets `.dm3p`), contributed by
markcarlberg (pull request #2). The container is the one in [`FORMAT.md`](FORMAT.md) section 4, and the DM7 field
names are in [`dm7-fields.md`](dm7-fields.md). "As DM7" means the same field name and encoding. Nothing on this page is
used by `scripts/yamaha_tool.py`.

The evidence is DM3 Editor 3.1 saves: a new show for each model, controlled saves that each moved one control, and the
factory scenes and presets that ride inside every new show. Every line says how it was found: **(save)** a controlled
save moved it, **(files)** the same in every file at hand but never moved by a save on its own. Untested readings are in
`../dm3/README.md` under What we don't know.

## Identity

| Field | DM3 | DM3 Standard | DM7 family |
| --- | --- | --- | --- |
| Header model at 0x24, also in each inner MBDF file | `DM3` | `DM3` | `DM7` |
| `Project/Info.ProductName` | `DM3` | `DM3` | `DM7` or `DM5` |
| `Project/Info.ProductSubName` | `DM3` | `DM3S` | `DM7`, `DM7C`, `DM5`, `DM5C` |

- The two models differ in `ProductSubName` alone. A byte diff of the two blanks finds only the header save id
  (0x38 to 0x47), header byte 0x2B7 (`00` against `53`, the `S`), header byte 0x37A (`TimeStamp.Second`), and the save
  ids of the current file, the scene list and their `.old` twins. The other 278 entries are identical unpacked. (save)
- The Standard's file still holds every Dante table (`Process/Dante` 16 in and 16 out, `Setup/Dante`) at defaults.
  (save)
- A parser that checks only the `#YAMAHA MBDFProjectFile` magic misreads a `.dm3f` as a DM7: it finds no input patch and
  takes a DM3 mix as the stereo bus. Check the model at 0x24 first. (save)

## Container differences from the DM7

| Item | DM3 | DM7 | Proof |
| --- | --- | --- | --- |
| Version bytes 0x34 to 0x37 | `56 03 0A 00` (V3.10, as FORMAT.md 4.1) | see FORMAT.md 4.1 | save |
| Factory scene and preset version bytes | `52 02 00 07`, `52 03 0A 09` | none | save; meaning not known |
| First `#FILE` entry | 0x37C | 0x470 in one DM7 show | save |
| Entry folder separator | colon: `Library:A`, `Scene:A` | slash: `Lib/InCh`, `Scn/UserA` | save |
| Section version text | none | `01.00.00 A` | save |
| Section function names | `Processing`, `SceneInfo`, `PresetInfo`, `ConsoleSetup` | shorter | save |
| Bit fields | none; every switch is a byte | switches packed as bits | save |
| Separate setup file, preset list | no, no (Setup is a section; each preset is its own entry) | yes, yes | save |

An editor save gives the current file and the scene list new save ids and rewrites the header time stamp. Factory scenes
and presets keep their ids. (save)

## Entries and sections

A blank show has 282 entries. (save)

| Entry | Count | Unpacked bytes | Sections (data bytes) |
| --- | --- | --- | --- |
| `Current/CurrentBackupFile.bup` (+ `.old`) | 1 | 84,500 | Mixing (14,890), Process (264), FX (584), Setup (25,041), Security (186), Scene (342), Preset (478), CnsSetup (2,179) |
| `SceneList/CurrentListBackupFile.bup` (+ `.old`) | 1 | 8,408 | SceneList (8,000) |
| `Scene:A/<GUID>.dm3s`, `Scene:B/...` | 14 + 1 | 45,120 each | Scene, Mixing, Process, FX |
| `Library:A/<GUID>.dm3p` | 262 | 7,472 to 9,424 | Preset, then one strip: Mixing, Process, FX |

- `Mixing` tables: `InputChannel[16]` 473 bytes at 0, `StInChannel[2]` 452 at 7,568, `FxRtnChannel[4]` 452 at 8,472,
  `Mix[6]` 419 at 10,280, `Matrix[2]` 335 at 12,794, `FxBus[2]` 167 at 13,464, `Stereo[2]` 406 at 13,798,
  `ChannelLink[1]` 280 at 14,610. (save)
- `InputChannel` children: `Label` at 0, `Patch` 100, `Signal` 104, `Input` 105, `Insert` 108, `PEQ` 114, `Gate` 223,
  `Comp` 286, `Delay` 339, `AutoMixer` 345, `ToMix[6]` 349, `ToMatrix[2]` 379, `ToFX[2]` 389, `ToStereo` 397,
  `MuteGroup[6]` 399, `Fader` 405, `ChannelLink` 408, `Library` 409. (save)
- Several table names carry `TF` (`RecallSafe/TF`, `Focus/TF`, `Library/TF`). (save)

| Strip | Table | Notes |
| --- | --- | --- |
| CH 1 to 16 | `Mixing/InputChannel[16]` | |
| Stereo input | `Mixing/StInChannel[2]` | two items, L and R |
| FX returns (2) | `Mixing/FxRtnChannel[4]` | FX1 RTN L/R, FX2 RTN L/R |
| Mixes, matrices | `Mixing/Mix[6]`, `Mixing/Matrix[2]` | `Mix.BusType` VARI or FIXED |
| FX buses (2) | `Mixing/FxBus[2]` | name, colour, fader, on, last preset; the DM7 has none |
| Stereo bus | `Mixing/Stereo[2]` | two items, L and R |
| DCAs | none | only `CnsSetup/Common/DCAGroupRollOut.TargetCH`, which the DM7 has too |

`Label` `Name`, `Color`, `Icon` as DM7. `Label.Category` (text 16: Vocal, Drums, Keys, Output, FX, Others, `----`) is
DM3 only. (files)

## Input patch

One `Patch.Source` (u32) per strip, with no Input A/B and no `InPatch`. The word layout is the DM7's; the codes are the
DM3's own. (save)

| Source | Code | DM7 code |
| --- | --- | --- |
| IN n | 0x01400000 + n - 1 (sub-code 00) | OMNI 0x01401000 + port (sub-code 01) |
| DANTE n | 0x01800000 + n - 1 | 0x01A00000 + port |
| USB n | 0x01600000 + n - 1 | not a channel patch |

## Head amps, digital gain, polarity

- `Process/BuiltIn/InputPort[16]/HeadAmp`: `Gain` signed 16-bit 0.01 dB, `48V` byte. An untouched port reads 0, against
  -600 on the DM7. (save)
- `<strip>/Input.Gain` (digital gain) and `Input.Phase` (a byte) as DM7. The ports have no polarity of their own. (save)
- `Setup/PhantomMaster.On` is the +48V master (the DM7's `Unit.48VMaster`), 1 on the blank. (save)

## HPF and EQ

- One bank, `PEQ/Bank`, with no A/B. `PEQ.On` is a byte. Frequency, gain and Q units as DM7. (files)
- `PEQ/Bank.Type` is `BOLD` on every strip. (files)
- `PEQ/Bank/HPF` `On`, `Frequency` (800 = 80 Hz), `Slope` 12, on CH 1 to 16 only. Other strips have no `HPF` block, and
  CH 1 to 16 have no `BandL.HPFOn`. (save for which strips carry it; values files)
- `BandL`, `Band[2]`, `BandH`: four bands, defaults 125 Hz, 1 kHz, 4 kHz, 10 kHz, Q 0.7. (files)
- `BandL.Type`, `BandH.Type`: 0 bell, 1 shelf. (save) The middle bands' `Type` is always 0. (files)
- There is no LPF block and no per-band bypass. (files)
- 1-knob EQ: `PEQ/Bank/OneKnob` `On`, `Mode` (`Intensity`, `Vocal`, `Loudness`), `Depth` %. `PEQ/OneKnobBackup` holds a
  second full copy of the bands. (files)

## Dynamics

Fixed slots with named fields replace the DM7's `Dynamics[2]/Parameter[10]`.

| Slot | Path and fields | Proof |
| --- | --- | --- |
| Gate (inputs only) | `Gate.On` byte; `Gate/Bank.Type` `GATE` or `DUCKING` | save |
| GATE, DUCKING | `Gate/Bank/Gate`, `Gate/Bank/Ducking`: Threshold, Attack, Range (stored negative), Hold, Decay, as DM7 | save |
| Gate key-in | `Gate/KeyIn.SourceSelect` text 16: Self Pre EQ, `SELF POST EQ` (blank), Other Ch. Other Ch is written `OTHER POST EQ` with `Source` 0x03C18000 + channel from 0 | save |
| Comp | `Comp.On` byte; `Comp/Bank.Type` always `COMP`; `Comp/Bank/Compressor` fields as the DM7's Legacy Comp | files |
| Comp ratio | u8 x10 (25 = 2.5:1); 255 = infinity | save |
| Comp knee | text `HARD`, `SOFT-1` to `SOFT-5` (HARD, SOFT-2, SOFT-5 seen) | files |
| Comp key-in | `SourceSelect` only, always `SELF POST EQ`, no `Source` | files |
| 1-knob comp | `Comp/Bank/OneKnob` `On`, `Depth` | files |

Attack is whole milliseconds. (files) No processing order is stored (no `EQDynOrder`). (files)

## Faders, pan, delay, pairs

- `Fader.Level`, `ToStereo.Pan`, `Delay.Time`, `Signal.Relation` (0x80 left, 0x01 right) as DM7. Switches are bytes.
  (save for level and relation; files for the rest)
- `ToStereo.Assign` is the DM7's `ToStereoA` (one stereo bus). `Output.Balance` is the DM7's `Out.Balance`.
  `Signal.PanLink` is on mixes and matrices. `Delay.LRLink` is on stereo strips. (files)
- The stereo input, FX returns and stereo bus are always two items, never paired by `Relation`. (files)

## Buses, sends and send points

- `ToMix[6]`, `ToMatrix[2]`: `Level`, `On`, `Pan`, `Pre`, as DM7. `ToFX[2]` has `Level`, `On` and `Pre` with no pan,
  feeding the two FX buses. (save)
- The pre point belongs to the bus, not the send: `Mix/SendPoint.Pre`, `Matrix/SendPoint.Pre`, Pre Fader 100 (blank) or
  Pre EQ 50. The editor sets it per mix pair in Bus Setup. FX buses have no `SendPoint`. (save)
- Turning a mix FIXED makes the editor set every send into it to level 0 and off. A FIXED send acts as a switch. (save)

## Mute groups, channel link, automixer

All (files).

- `InputChannel/MuteGroup[6]` is one byte per group. `Setup/MuteMaster[6]` holds `Name` (`MUTE 1` to `MUTE 6`) and
  `On`. `Setup/MuteSafe/InputChannel.On` is the mute safe per input.
- Channel link: `InputChannel/ChannelLink.GroupId`, with link-parameter bytes in `Mixing/ChannelLink/Input`.
- Automixer: `AutoMixer` `On`, `Group`, `Weight` on all 16 inputs; `Setup/Automixer/Master[2].Bypass`.

## Inserts

One slot per strip, `Insert.On` a byte.

| Field | Values | Proof |
| --- | --- | --- |
| `Insert.Point` | Pre EQ 50 (blank), Pre Fader 100, Post ON 120 | save |
| Post ON | offered on inputs and mixes only | files |
| INSERT IN | `Insert/Module/Patch.Source`, an input code (USB 2 = 0x01600001) | save |
| INSERT OUT | an output port playing `Ins CH n`, 0x13C00000 + n - 1 | save |

## Output patch

The patch sits on `Process/<device>/OutputPort[k]/Patch.Source` for `Omni` (8), `Dante` (16) and `USBToHost` (18). The
recorder's patch is in `Setup/Recorder/Record/OutputPort[2]`. The codes are the DM7's family shifted by two.

| Source | Code | Proof |
| --- | --- | --- |
| MIX n | 0x04200000 + n - 1 | save |
| MATRIX n | 0x04400000 + n - 1 | save |
| ST L | 0x04600000 | save |
| CUE L | 0x05000000 | save |
| MONI L | 0x05200000 | save |
| OSC | 0x05400000 | save |
| Ins CH n | 0x13C00000 + n - 1 | save |

- No channel direct out is offered, and there is no direct-out table. (save)
- Blank defaults: OMNI 1 to 6 play MIX 1 to 6, OMNI 7 and 8 ST L and R, Dante 9 and 10 MATRIX 1 and 2, Dante 11 and 12
  MONI L and R, and the recorder takes ST. (save)

## FX, monitor, cue, oscillator

All (files).

- `FX/FX[2]`: `Bypass`, `MixBalance`, `Param` (`PluginName`, `LibraryName`, `Bank.Value` signed 32-bit x64), as the
  DM7 rack. Blank: RevHDHall, MonoDelay. Each effect is fed by its FX bus.
- One cue, `Setup/Cue` (`Mode`, input and output `Point`, `Trim`). It is not a bus table.
- `Setup/Monitor`: source bytes (Mix, Matrix, Stereo, Playback, UsbIn), `Level`, `Delay`, `Mono`.
- `Setup/Oscillator` as DM7, as bytes, plus an FxBus assign.
- There is no talkback table.

## Scenes and presets

- Each scene is its own entry, a whole MBDF scene. Scene entries have no `.old` twin; the list does. (save)
- `SceneList/Bank[2]/Info[100].FileName`: each row names the scene's entry, and an empty row means no scene. Row i of
  bank A is A00 + i. (files)
- `Scene/Info` holds `Title`, `Comment`, `Protect` and `TimeStamp`. `Scene/Focus` has `DataFormat` `TF`. `Scene/Fading`
  has a per-kind `On`, FX buses included. The last recalled scene is in `Setup/Scene.LastScene` and
  `CnsSetup/Scene.SelectedScene`. (files)
- Every new show carries 14 factory scenes in bank A, all `Protect` 1, plus an unprotected `Initial Data` in bank B.
  (save)
- 262 factory presets (`Library:A`), all `Protect` 1, plus one Dante preset (`Library:DNT`). Each strip's
  `Library/LastRecallPreset.Title` reads `- - - - - - - -` when none was recalled. (save)

## Security

`Security/UserAccount/DM3/Account[2]` (Administrator, Guest) has a 24-byte `Password` and `PanelAccess`.
`Setup/CommSession/MobileMix.Password` (text 24) is the MonitorMix app password. Both are empty in the blanks. A
converter must leave both untouched. (save, layout only)
