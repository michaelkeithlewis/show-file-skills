# Preamps, input processing, SoftKeys, macros, surface layout (Director V2.12, show Version 14)

All sections live in the per-scene `.dat` files: StageBox scenes (MixRack state, one per stored scene plus
`StageBoxScene65535` = live) and Surface scenes. Section = u16be len, label, NUL, payload.

## MixRack preamps: `StageBox Analogue Input, Number N` (DM local sockets 1-64)
`[01][gain s16be dB*256][pad 0/1][48V 0/1]`, default `01 1b00 00 00` (27 dB). From cAnalogueInput::GetStatus
@0x1004f86a0 and ResetStatus (gain +0x98, pad +0xa0, phantom +0xa8; MIDISetPhantomPower writes +0xa8).
Byte 3 = pad confirmed in real shows: playback/line inputs carry byte 3 only, talkback switches and
condensers carry byte 4. DX/surface sockets: `StageBox TSnake Analogue Input`, `Surface Analogue Input`.

## Input processing (per input channel, 128 of each)
Families: Preamp Model, Highpass Filter, Lowpass Filter, Gate, Gate side chain source, SCF Gate,
Parametric EQ, Compressor, Compressor side chain source, Delay, Insert 1, Insert 2, Digital Attenuator
(trim), Direct Output (tap point), Stereo Image. Labels: `Parametric EQ, Input Channel 03`,
`Highpass Filter Input Channel 03` (no comma on Preamp Model / HPF / LPF / Digital Attenuator / Stereo Image).
- Defaults: `scripts/input_defaults.json`, taken from untouched channels of Director-saved shows. Linked
  stereo channels have a stereo variant for PEQ, Compressor, Gate, SCF Gate, LPF (Director rewrites a pair's
  processing when it links it). Two default lineages exist in the wild (`0a80` vs `0d00` in each PEQ band):
  a show keeps whatever default its template was born with; both load.
- Input channel section (47 bytes per channel in the Input Mixer, after the sends): byte 0 main assign,
  byte 2 mute (cMixer::GetStatus writes sInputAttributes +0, the field GetInputMute reads), bytes 3-4 fader,
  byte 5 pan 0-74 (37 centre), byte 7 mono flag.
- Stereo pairs: `Show/InputConfig/InputConfig.dat` holds the links. Byte 7 of each input channel section is a
  mono flag: 1 for a mono channel, 0 for both sides of a linked pair. Every Director-saved show keeps the two
  in step, so `build_show.py` writes both.
- Side chain source: `[01][strip type][index]`, default self (`01 01 <ch-1>`); stereo R keys from L.
- Insert: `[02][bypass][level mode]`. Byte 1 is the bypass flag: 1 = OUT, 0 = IN. "In" with nothing patched is harmless (passes audio): One touring show ran dozens.
  Insert routing lives in the patch section (`Ip Ins A/B return`; FX/UFX/Dyn8 unit inputs fed by type
  0x08/0x09 = input insert send A/B). A Dyn8/FX unit can sit on one channel only.
- Dyn8 units: `Dynamics Unit N` (140 bytes) hold parameters only; the channel binding is the patch.
- Compressor has an older shorter format (88 bytes) in older shows; Director upgrades it.
- Digital Attenuator length follows the saving version, not the age: Director 2.11 and the A&H factory
  shows write 7 bytes (`01 | trim s16 | phase | mute | 2 extra`); Director 2.12 and 2.12 consoles write
  5 bytes. Both load in 2.12.

## DCA levels and mutes: `DCA Levels and Mutes` (129 bytes, live scene)
`01` + 32 records of 4 bytes. Records 1-24 are the DCAs: `[flag A][flag B][level s16 dB*256]`, `0x8001` = -inf. Flag A is
the mute: on one Director capture flag A was 1 on DCA 11 only, and Director drew only DCA 11 muted. Levels matched Director's
faders on one show. Both factory shows have flag A = 1 on DCAs 1-10 or 1-11 at 0 dB (FoH: 1-11), so their DCA strips
read muted, and a show built from them starts with those DCAs muted. Flag B and records 25-32 are not known. No script here writes
this table: unmute DCAs in Director.

## SoftKeys: `Surface Soft Controls` (surface scenes)
cSurfaceSoftControlManager::GetStatus @0x1004d8f00: `[02][u16 26][u16 26]` + 52 settings (two identical
sets of 26) + a tail kept as is. Setting = `[function][01][LED colour 0-7][version][payload]`.
Function ids (cXxxSoftSetting constructors): 00 unused, 02 library, 04 mute (channel: `01 <strip> <idx>`),
05 PAFL, 0c tap tempo (8 bytes), 0d scene recall (`01 u16`), 0e custom MIDI, 0f PAFL clear, 10 scene go,
11 scene control, 12 Sel/Mix/PAFL combo (cPAFLComboSoftSetting, payload `<strip> <idx> <combo type> <flag> 00 00 ff ff`,
e.g. `05 <st aux-1> 02 01` for one key per IEM mix; UI modes Sel Mix PAFL / Mix PAFL / Sel PAFL, type 02
not mapped yet), 17 spills, 18 AMM, 1e (4 bytes, unknown), 1f talkback
(`02 <group-1> <latch>`), 24 ABCD set all (`01 <1-4>`), 25 ABCD set channel, 2b virtual soundcheck
(`01 <mode>`), 2d talkback additive, 33 multifunction (`01 <mode> <name on>\0 <name off>\0`).
Older shows contain key types whose sizes are not decoded yet; the parser stops there and lint warns.

## Multifunction macros: `Show/Multifunctions/<name>.dat`
Text. Line 1 `2`, line 2 a hex id, then one action per line as comma tokens: `aa,X` byte, `a8,hi,lo` 16-bit,
`e8,X` / `eb,X` marker with value, `ea` bare marker, `ad,<bytes>,0` string. A strip key is
`aa,<strip>,aa,<index>`; the last `a8` in a line counts the strip keys that end it; function 5 (send) has its
source key right after the `e8`. Seen: fn 5 send on/level to destinations, fn 6 (group/main keys), fn 7
ABCD source select, fn 13 (0x0d) show a screen (`ad Routing/Routing`). Macros reference channels by number,
so moving to a new artist means remapping (dlive_multifunctions.py remap). SoftKeys refer to macros by name.

## MCA (Mix Control Association): `Show/MCASettings/MCASettings.dat`
Text: line 1 `1`, line 2 = 24 comma-separated `true|false` (DCA 1-24: the DCA acts as an MCA) then one more
number (`0` with no MCAs, `1` once DCAs are MCAs; probably the global MCA allow). An MCA fader moves its
members' sends to the selected mix instead of their faders (cMCASettingsArchiverRestorer,
cMCAActivationManager, SoftKeys MCAGlobalAllow / MCAForceOnMix).

## Surface layout: `Channel Left/Middle/Right Bank Switcher`
`[01][strips per layer]` + 6 layers x strips x `[strip type][index]`. CTi1500/C1500 = left bank only,
12 strips x 6 layers (72). Strip types (CustomController::cConfigManagerTLD::ToChannelStripType):
ip 01, grp 02, stgrp 03, aux 04, staux 05, fx 06, stfx 07, main 08, mtx 0a, stmtx 0b, fxret 0c, dca 0d,
mon 0e, 0f (seen), stahfx 13, ahfxret 14, empty 00. Index = number within its type - 1 (stereo mixes count
as one). A tidy FOH layout: layer A DCAs 1-12, B groups, E utility + masters, F FX returns;
inputs reached by DCA spill, not input layers.

## Decoded later
- `Global Direct Outputs` `[02][source][..]`: source = eInputChannelSourcePoint 0 Post Preamp, 1 Post LPF,
  2 Post Gate, 3 Post Ins A Ret, 4 Post PEQ, 5 Post Comp, 6 Post Ins B Ret, 7 Post Delay. Common: 7.
- Multifunction fn 6 = processing in/out (`cMultifunctionRecall::RecallProcessing` @0x1010ae6e0):
  `aa,6,aa,<mode>,aa,2,eb,0,a8,0,<proc>,a8,<count>,<strips>`. mode (eSoftkeyMode) 1 = in, 2 = out (bypass),
  0 = toggle. proc 1 preamp, 3 HPF, 4 gate, 5 insert A (a mix's only insert), 6 insert B (inputs only),
  7 comp, 8 PEQ, 9 NEQ. Director-written 'INSERT ON/OFF' and 'LP ON/OFF' macros are proc 5; `insert_action()` reproduces
  them byte for byte. Insert B (proc 6) follows the same table but no Director-written sample exists yet.
- fn 7 = ABCD source select: `aa,7,aa,0,aa,2,eb,0,a8,0,<1-4>,a8,<count>,<strips>` (a 'VSC ON/OFF' macro).
- Macro file line 2 is Director's id = epoch milliseconds in hex. Limits: 100 actions, 50000 bytes per action.
- SoftKey multifunction `33 01 <colour> 01 00 <macro on>\0<macro off>\0`: Director-saved keys seen put the OFF macro
  first ('INSERT OFF'/'INSERT ON', 'LP OFF'/'LP ON'). Virtual soundcheck key `2b 01 <colour> 01 <mode>`.
