# Avantis patch, sockets and surface

Compare `allen-heath/dlive/references/format-patch.md`.

## Hardware

| Model | Faders | Local mic/line in | Line out | AES3 | SLink | I/O ports |
|---|---|---|---|---|---|---|
| Avantis | 24 (12 + 12) | 12 | 12 | 1 stereo in, 1 stereo out | 1 (128 x 128) | 2 (128 x 128 each) |
| Avantis Solo | 12 | 6 | 6 | 1 stereo in, 1 stereo out | 1 (128 x 128) | 2 (128 x 128 each) |

SLink talks dSnake (AR/AB boxes), gigaACE (DX via DX Hub, GX4816) and ME. Shows move freely between
Avantis and Solo: a Solo saves 12 + 12 strips and leaves the right bank empty.

## Channel mapper (input sources)

Avantis entries are 3 bytes: `[type][index u16]`.

| Type | Source | Index |
|---|---|---|
| `00` | Local | 0-11 analogue, 12-13 AES |
| `01` | I/O Port 1 | 0-127 |
| `02` | I/O Port 2 | 0-127 (from the socket family order, not yet confirmed with a test show) |
| `03` | SLink | 0-127 |
| `25` | USB | |
| `26` | Signal generator | |
| `11` | Not patched | |

To confirm type `02`: an Avantis show with input 1 from I/O Port 1 ch 1 and input 2 from I/O Port 2 ch 1.

## Preamps

One 5-byte section per socket: `[01][gain s16/256 dB][pad][48V]`. Default gain 27 dB. AES and USB have no
gain, only trim.

| Section | Avantis | dLive |
|---|---|---|
| `StageBox Analogue Input, Number NN` | Local 1-12 | MixRack 1-64 |
| `StageBox GX Analogue Input, Number NN` | SLink 1-128 | none |
| `StageBox Port B Analogue Input, Slot S, Number NN` | I/O Port S (remote box preamps on a card) | |

## Strip types (surface layout and strip assign)

| Strip | Avantis | dLive |
|---|---|---|
| Input | 1 | 1 |
| Mono group | 2 | 2 |
| Stereo group | 3 | 3 |
| Mono aux | 4 | 4 |
| Stereo aux | 5 | 5 |
| Mono FX send | 6 | 6 |
| Stereo FX send | 7 | 7 |
| Main | 8 | 8 |
| Mono matrix | 9 | 10 |
| Stereo matrix | 10 | 11 |
| FX return | 11 | 12 |
| DCA | 12 | 13 |
| UFX / AHFX send | | 19 |
| UFX / AHFX return | | 20 |

From mono matrix on, dLive is one higher. The same shift shows in FollowPanSettings (stereo matrix 10 on
Avantis, 11 on dLive) and in compressor side chain sources.

## Surface banks

Avantis 12 + 12, Solo 12 (saved as 12 + 12). For comparison, dLive surfaces (left + middle + right):
S3000 12 + 0 + 8, S5000 12 + 8 + 8, S7000 12 + 12 + 12, C1500 12, C2500 12 + 0 + 8, C3500 12 + 0 + 12,
CTi1500 12.

## More patch detail (markcarlberg, pull request #2)

From Avantis Director V1.30 and V2.01 saves. Proof in brackets: save-proven, seen in every file (never moved
alone), or unconfirmed.

### Channel Mapper records

Records of `[type][u16 index]` after one version byte. Bridge-4: 1,830 records (5,491 bytes). Bridge-5: 1,590
records: 16 Ultra FX rack inputs (type `2A`) inserted at record 1238 and 256 empty records past USB removed, so
everything from 1238 moves up 16. [save-proven]

| Records (Bridge-4) | What | Proof |
|---|---|---|
| 0-95 | input sources | save-proven |
| 96-191 | Virtual SoundCheck: input n's playback, `22 n` = port channel n + 1 | save-proven |
| 192-319 | Virtual SoundCheck: port channel's record send, `24 i` = input i + 1 | save-proven |
| 352 + n, 448 + n | Insert 1 and Insert 2 returns for input n | seen |
| 859-886, 887-942, 943-970, 971-976, 977-1032, 1033-1060 | mix insert returns: stereo groups, mono auxes, stereo auxes, mains (a record a leg), mono matrices, stereo matrices; mono groups probably 803-858 | save-proven for the first of each kind |
| 1061 + (N - 1) | Local out N, 1-16 | save-proven |
| 1076 + N | SLink out N | save-proven |
| 1205 (payload offset 3616) | talkback source, spelt as an input source | seen |
| 1206-1237 | FX rack inputs, two per rack, fed `1A 00 k-1` (FX send k) | save-proven |
| 1241 + N | I/O Port 1 out N | save-proven |
| 1369 + N | I/O Port 2 out N | save-proven |
| 1497 + N | ME out N, 1-40 (default unpatched) | save-proven |
| 1538 + (u - 1) | Dyn8 unit u's input | seen |
| 1570 | USB out 1 | save-proven |

No AES tab exists in Director V1.30. Local 13-16 are records 1073-1076 and play what they are set to. Unpatched
is `11 00 00`. [save-proven]

**Input source types:** 00 Local (socket from 0), 01 I/O Port 1, 02 I/O Port 2, 03 SLink, 04 an input's direct
out, 09 mono group, 0A stereo group, 0B mono aux, 0C stereo aux, 0D main, 0E mono matrix, 0F stereo matrix,
11 none, 19 Rack FX, 25 USB, 26 signal generator. AES is not a source type of its own. [save-proven; USB n as
index n + 1 seen]

**Output source types:** the bus types above (a stereo source is index 2(n - 1) + leg, left 0, the same type
both legs; mains by leg, 0D 0/1 LR, 0D 2 M), 04 direct out, 05/06 Insert 1/2 send (index the input from 0),
10 PAFL (left 0, right 1; the second PAFL 2 and 3), 13-18 mix insert sends (stereo group, mono aux, stereo aux,
main, mono matrix, stereo matrix: each the bus type plus 9), 19 FX rack output, index 2(rack - 1) +
(output - 1), 1B the monitor (wedge) bus, 23 Dyn8 unit output (index u - 1). `1A` and `1E` also appear.
[save-proven; 1B right leg seen]

### Inserts, Dyn8, Virtual SoundCheck

- An input insert's return is its return record; its send is any output record playing type 05/06 with the
  input's index. Loops in files return on the socket number their send leaves on. [seen]
- On an FX rack the return plays `19 00 2(k-1)` and both rack input records play the insert send. On a Dyn8
  unit the return plays `23 00 u-1` and the unit's input record plays the send. [save-proven for mixes; seen
  for inputs]
- **Mix inserts:** one `Insert, <mix>` block a leg (`02 00 00`) and one return record a mix; Main LR has a
  record a leg. A stereo mix's record holds its left socket; the pair starts on an odd socket. A stereo mix on
  Dyn8 takes units u and u + 1, u odd, and so does a stereo input (each side its own unit, the same settings in
  both). Only one insert a mix; FX sends have none. The mix insert's byte 1 is the same bypass as an input's,
  00 in and 01 out (a dLive save switched one Out: `02 00 00` to `02 01 00`). [save-proven]
- Returning an insert on a Local socket makes Director set that head amp to `01 14 00 01 00` (+20 dB, pad in,
  48V off). [save-proven]
- **Dyn8:** 32 `Dynamics Unit 01-32` blocks, 140 bytes each, in every scene (A&H publishes 16, or 24 with
  dPack). [seen in every file] dLive Dyn8 words are in `../../dlive/references/format-fx.md`.
- **Virtual SoundCheck:** `Show/VirtualSoundCheck/VirtualSoundCheck.dat`: `1`, then the mode: 0 Inactive,
  1 Record Send, 2 Virtual SoundCheck. The two `Channel Mapper` banks are each other's inverse: one input per
  port channel. The port (I/O Port 1 or 2) is not in the file. Stored scenes hold the same records. There is
  no alt input on an Avantis. [0, 2 and the banks save-proven; 1 seen]

### Head amps

- The stored gain is the preamp's own; with the pad in, Director's box shows the stored gain less 20 (typed 30
  with the pad stored `32 EB`, 50.92 dB). Range +5 to +60. Default `01 1B 00 00 00` (+27 dB). [save-proven]
- The second I/O Port slot's label has no comma before "Number":
  `StageBox Port B Analogue Input, Slot 2 Number NN`. [seen in every file]

### Outputs

- **`Global Direct Outputs`** (6 bytes, factory `02 07 00 01 00 00`): +1 tap point 00 Post Preamp, 01 Post LPF,
  02 Post Gate, 03 Post Ins A Ret, 04 Post PEQ, 05 Post Comp, 06 Post Ins B Ret, 07 Post Delay; +2 Follow Fader;
  +3 Follow Mute; +4 probably Follow Total Main Gain. One point for the whole desk. [seen in every file]
