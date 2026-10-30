# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/build_show.py

- stereo pairs: InputConfig.dat = "1" then 64 flags (one per odd/even pair)
- plan owns pairs up to its last channel
- repack in the template's own member order and ustar format (no PAX headers)

## scripts/dlive_ears.py

- FX/UFX return mixers hold L/R rows per strip

## scripts/dlive_fx.py

- the other dLive scripts sit in this folder
- ---------------------------------------------------------------- conversions
- eAHFXParameterFormat -> (fn, unit)
- ---------------------------------------------------------------- scene helpers
- ---------------------------------------------------------------- units
- string pool order @0x1012140e5 GetMBCSlopeName @0x100fb9e40
- ---------------------------------------------------------------- main decode
- per-channel sends (Input Mixer): FX sends (mFX then sFX lists), UFX sends in rest[47 + 5u]
- return routing (FX Return Mixer / AHFX Return Mixer are cMixer sections like Input Mixer)
- unused returns sit at main-on, fader -inf
- L and R carry the same routing

## scripts/dlive_lint.py

- eAudioSourceType values seen in Director (0x00-0x2e) seen in Director-saved banks
- Director 2.12 itself writes other recall-filter state here once a scene has been stored, so a mismatch is only a warning.
- bytes after the NUL are leftovers

## scripts/dlive_mix.py

- ---------------------------------------------------------------- mixer config
- buses per main mix mode (byte 8: 0 none, 1 LR, 5 5.1, 6 LCR+), from sMixerConfigurationSettings::GetNumberOfMainMixChannels @0x1005676f0; byte 11 = stereo PAFL count
- mono buses come in pairs: an odd mono count pushes every later stereo mix off its even bus, the console logs "this fn requires the mix number to be even" (MixerModule.cpp) and Sel on a stereo strip shows its neighbour. Director only offers even mono counts; no real show seen has an odd one.
- ---------------------------------------------------------------- scene section chain
- ---------------------------------------------------------------- cMixer (Input / FX Return / AHFX Return Mixer)
- ---------------------------------------------------------------- cMixMixer (Mix Mixer)
- mono FX, then mono aux stereo FX, then stereo aux
- 16-byte strip (mute, fader s16 @3, pan @5, mono @7 ...) + 24 DCA + 8 mute groups
- ---------------------------------------------------------------- per-mix processing sections
- Director V2.12 defaults, read from freshly created mixes
- ---------------------------------------------------------------- scene safes / recall filter
- ---------------------------------------------------------------- follow pan
- ---------------------------------------------------------------- mix edits: masters, sends, names
- FX / UFX sends have no Mix Mixer strip (names only)
- ---------------------------------------------------------------- show level

## scripts/dlive_multifunctions.py

- ---- writers (shapes copied from Director-saved macros; meanings from cMultifunctionRecall @0x1010ae6e0) fn 6 = processing in/out: [aa,6][aa,mode][aa,2][eb,0][a8,0,proc][a8,count][strip keys]. Mode (eSoftkeyMode): 1 = in, 2 = out, 0 = toggle. proc (eChannelProcessingMode, RecallProcessing jump table): 1 preamp, 3 HPF, 4 gate, 5 insert A (mixes: their one insert), 6 insert B (input channels only), 7 comp, 8 PEQ, 9 NEQ. Director-written 'INSERT ON/OFF' and 'LP ON/OFF' macros are proc 5. fn 7 = ABCD source select: [aa,7][aa,0][aa,2][eb,0][a8,0,source 1-4][a8,count][strip keys] (a Director-written 'VSC ON/OFF': source 2 / 1 on one channel).

## scripts/dlive_patch.py

- eAudioSourceType values (shared by inputs and outputs)
- socket locations as Director's CSV import names them: name -> (type, first input number, count)
- destination blocks: name -> (payload offset, count, output-number offset inside a shared block)
- Virtual soundcheck: VSC_BYTES = [port][range start][range end]. Port is an I/O port index that Director maps with cSocket::IOPortToLocation (@0x100737ba0): 0-2 = MixRack I/O Port 1-3, 3-4 = Surface I/O Port 4-5. Range: start byte = first socket - 1, end byte = last socket (SetVirtualSoundCheckRangeStart/End @0x1001c6850). A channel plays back from the port when its VSC input source is "VSC port n" with n inside the range, its VSC flag (VSC_FLAGS) is set and the VSC mode is 2 (cChannelMapperBase::VirtualInputActive @0x1004fe090); record sends ("Ip n VSC rec" at socket n) drive the port outputs in mode 1. Seen: port 0 (IO 1) 75-124 on one show, port 3 (IO 4) 1-56 on another. The mode itself is not stored in the Channel Mapper section.
- output destinations: name -> (block, first index, count). Surface sub-ranges from the CSV table.
- an older-format stored scene (Director converts it on load)
- template member order, ustar, no PAX

## scripts/dlive_proc.py

- the other dLive scripts sit in this folder
- ---------------------------------------------------------------- unit conversions (Director globals)
- PEQ width index = high byte of the u16, 25 steps; table @0x102526ef0 read by cBiquadFunctions::RefreshBand
- octaves for that Q (RBJ bandwidth relation)
- ratio index -> ratio, tables of {label, double} @0x106d677f0 (manual), 0x106d67b80 (16T), 0x106d67e10 (16VU), 0x106d680a0 (Opto); 60.0 is "Infinity"
- fixed detector times the driver uses regardless of the stored attack/release (SendAll_16T @0x100e6af4d: 0.0015 s / 0.13 s, SendAll_16VU @0x100e6b15d: 0.0005 s / 0.08 s)
- ---------------------------------------------------------------- section decoders
- qtype: 0 -> Bell, else ConstantQBell (CalculateCoeffs @0x1005917d0)
- which stored generic fields each model's SendAll_*_Settings_ToDriver actually reads
- ratio_state 0-4 (driver bounds-checks < 5); the threshold comes from a 5-entry table by state (@0x1029f4014: -6, -6, -4.5, -3, -1 dB). Label order assumed 4/8/12/20/all (1176 convention).
- attack/release go through UWORDToTime and then a model curve in ChangeExponentialAttack/UseExponentialRelease; not plain seconds (34 s on Kout)
- ---------------------------------------------------------------- show access
- semantics inferred, see references/format-processing.md
- ---------------------------------------------------------------- CLI

## scripts/dlive_safes.py

- record-relative offsets of the per-bus safes in FILE order inputs/returns: 64 bytes, one per bus (group assign) 64 triplets (aux / FX send items) 64 triplets (matrix send items) mix records: 64 triplets (group -> aux/FX sends) 64 triplets (sends to matrix) 64 bytes
- inputs, FX returns, UFX returns

## scripts/dlive_scene.py

- exact framing: names + colours
- label matched inside a longer label (e.g. "Stereo AHFX Send" vs "FX Send")
- channel section offset in block

## scripts/dlive_softkeys.py

- virtual soundcheck key, as in a Director-saved show (mode 1 record/live, 2 playback)
- multifunction key: mf:<macro on>/<macro off> (latching, Director's 01 00 header)
