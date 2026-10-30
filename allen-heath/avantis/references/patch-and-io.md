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
