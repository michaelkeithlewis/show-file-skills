# Avantis talkback, PAFL, AMM, gangs, layers, soft keys

From markcarlberg's Avantis Director V1.30 and V2.01 saves (pull request #2). Proof in brackets: save-proven
(one change, save, the named bytes moved), seen in every file (consistent, never moved alone), or unconfirmed.
The dLive files of the same name are in `../../dlive/references/format-versions.md`.

## Talkback

- **`Show/Talkback/Talkback.dat`:** `1`, then 56 `true`/`false` assign lines, one per mix leg in chain order
  (groups, mono FX sends, mono auxes, stereo FX sends, stereo auxes, mains, matrices; stereo left then right).
  The mains always take four legs whatever the mode, so an LR show leaves two empty before the first matrix.
  Then line 58 `true` (unmoved), line 59 Enable Dim PAFL on Talkback, line 60 the source Trim
  (`0x8000 + 256 x dB`). The source's gain, pad and 48V are its socket's head amp. The talkback source is the
  `Channel Mapper` slot at payload offset 3616. No on/off, latch or level is in any file. [assigns for mains and
  matrices save-proven; groups and auxes seen; dim and trim save-proven]
- **`Talkback Highpass Filter`** (scene block, 31 / 11 bytes): an input LPF's layout: frequency (default
  `5C96`, 141.4 Hz), width 0D, type 04, switch (01 out). [save-proven]

## Signal generator

`SignalGenerator.dat`: `1`, a field line `[0] 1, [1] type, [2..3] frequency word (high first), [4..5] level
word, [6] mute`, then 56 assign lines by leg. Type 1 White, 2 Pink, 3 Band Pass. Level s16 1/256 dB with the
generator's 0 dB at `E1 F6`; `80 01` off. Frequency `7A 11` is 440 Hz. [save-proven]

## PAFL

`PAFLSettings.dat` (version 1, 46 fields): [0] Ext Ip Talk To PAFL (true is off), [2] Additive, [3] Input AFL,
[4] Output AFL (true AFL), [5] Delay (samples at 96 kHz), [6] PFL Trim, [9] Mains To PAFL L from Left (by value:
[10] L from Right, [11] R from Left, [12] R from Right), [42] Mix Follows Input, [43] Mix Follows Mix, [44] Sel
Follows. The last three are mirrored in `BankSwitcher.dat` [2], [3], [1]. Strips do not choose a PAFL; wedge,
IEM and RTA are fixed to PAFL 1. [each switch save-proven]

## Auto mic mixer

`AutoMicMixer` (545 bytes): [1 + n] input n+1 in an AMM; [106..233] each AMM's inputs, 32 words apiece (AMM 1 at
[106], AMM 2 at [170]), `FFFF` empty; [234] mode 01 NOM, 00 D-Classic; [235..236] side chain HPF, [237..238]
LPF (frequency law); [241..242] On Hold in hundredths of a second; [544] Follow Fader. [save-proven]

## Metering

`MeteringRepeater.dat` `1,attack,release,peak hold`: peak hold in 20 ms steps. [save-proven]

## Gangs

`Channel Ganging`: version byte, 16 records. Version 1 (Bridge-4) 30-byte records, version 2 (V2.01) 32-byte:
`[on][16 member bytes, inputs from 0][13 or 15 flags]`. Flag 4 is PEQ; flags 9 and 10 are Fader and Mute as a
pair (on by default). [save-proven on V2.01; version 1 flags seen]

## Layers

Surface scene `Channel Left Bank Switcher` and `Channel Right Bank Switcher`, 146 bytes: `01`, `0C` (12 faders
a layer), then six layers A-F of twelve `[kind][number from 0]`. Kinds: 00 empty, 01 input (a stereo input by
its odd half), 02/03 mono/stereo group, 04/05 aux, 06/07 FX send, 08 main by leg, 09/0A matrix, 0B FX return,
0C DCA. Layers have no names. [seen in every file]

## Soft keys

Surface scene `Surface Soft Controls` (version 02, length per show) and `Soft Rotaries Control Manager`
(49 bytes v02 on V1.30, 61 bytes v03 on V2.01). Keys name a target as kind and number. The Surface scene chain
also uses the u32 length and the trailing `49`. [seen in every file]
