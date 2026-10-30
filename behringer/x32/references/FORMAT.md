# X32 / M32 scene format

Notes on the Behringer X32 and Midas M32 scene file (`.scn`). Contributed by markcarlberg. Most of this page is
desk research and reading of real files, not save-proven. Each line says where it comes from:

| Label | Meaning |
|---|---|
| save-proven | An X32-Edit or desk save moved it: one control changed, the named bytes changed. |
| real files | Consistent across many real scenes, never moved in isolation. |
| protocol doc | The unofficial X32/M32 OSC Remote Protocol document (4.02 and 4.09-02). |
| manual | Behringer's X32 quick start guide or X32 RACK manual. |
| unconfirmed | A reading that fits what was seen. Treat it as a guess until a save settles it. |

`.shw` (show), `.snp` (snippet) and preset files are separate formats and are not covered.

## Container

- Plain text, one node per line: a path, then positional tokens split on whitespace. (real files)
- Line 1 is the header: `#4.0# "name" "notes" %000000000 1`. The first token is the scene format number, then
  the scene name, notes and two more fields. Real exports and X32-Edit pad this line with spaces to 127
  characters. (real files)
- A later line that starts with `#` is a comment. (protocol doc, unconfirmed in files)
- A quoted run is one token. `""` is a real, common value that means unnamed. (real files)
- The desk parses on whitespace. Exports pad fields to fixed columns that depend on the line, the field and the
  length of the value. A rebuilt line with other padding loads the same but no longer compares byte for byte.
  (real files)
- `-oo` (minus infinity) appears only on fader and send levels. (real files)
- No line names the model. Every scene holds the full X32 node set and loads on any X32 or M32. M32 firmware
  uses the X32 numbering. (real files)
- Every scene node in real files matches the scene list in the protocol doc, except the `/-stat/*` surface
  lines and `grp` on matrices and mains, which the doc does not list. (real files)

## Number spellings and value grids

The desk stores grid points, not free numbers. A value off the grid, or spelled another way, is snapped on load
at best. The grids come from the protocol doc and were checked against real scenes. (protocol doc, real files)

| Quantity | Grid / law | Spelling |
|---|---|---|
| EQ and key filter frequency | 201 log points, 20 Hz to 20 kHz: `lo * (hi/lo)^(i/steps)`, 200 steps | below 1 kHz one decimal (`124.7`); from 1 kHz `NkFF`, hundredths of a kHz truncated (`1k97` = 1.97 kHz, `10k02`) |
| Low cut frequency | 101 log points, 20 to 400 Hz | whole hertz (`20`, `83`) |
| Q | 72 log points, 10 down to 0.3 | one decimal, `10` at the top |
| EQ gain | 0.25 dB steps, ±15 dB | `+0.00` style; at or above 10 dB truncated to one decimal (`-13.75` prints `-13.7`) |
| Fader | -oo, then up to +10 dB, printed to 0.1 dB | `-oo`, `0.0`, `+0.3`, `-13.6` (sign on positives, bare zero) |
| Send and M/C level | 161 points: off, 3 dB steps to -60, 1 dB to -30, 0.5 dB to -10, 0.25 dB to +10 | as fader |
| Pan | -100 to +100, steps of 2 | `+0`, `-24` |
| Digital trim | ±18 dB, 0.25 dB steps | one decimal, half away from zero (`+10.8` = 10.75) |
| Head amp gain | -12 to +60 dB | `+10.0`; step size unconfirmed (see README) |
| Threshold | 0.5 dB steps | `-80.0`, zero unsigned |
| Makeup | 0 to 24 dB, 0.5 dB steps | `9.50`, `11.5` |
| Ratio | 1.1 1.3 1.5 2 2.5 3 4 5 7 10 20 100 | literal on 4.0 (`3.0`) |
| Hold | 101 log points, 0.02 ms to 2 s | a fixed list (`0.02` ... `1002` `2000`), not printf output |
| Release | 101 log points, 5 ms to 4 s | rounded integer |
| Attack | 0 to 120 ms | integer |
| Knee | 0 to 5 | integer |
| Mix (wet) | 0 to 100, steps of 5 | integer |
| Gate range | 3 to 60 dB, whole | one decimal |
| Delay | 0.3 to 500 ms | one decimal |
| Oscillator f1/f2 | 121-point log scale, 20 Hz to 20 kHz | frequency shorthand |

The desk prints its own steps rounded half away from zero (0.25 is `+0.3`). It never prints negative zero.
(real files)

## Strips and paths

32 channels (`/ch/01` to `/ch/32`), 8 aux inputs (`/auxin`), 8 FX returns (`/fxrtn`, FX 1-4 left and right),
16 mix buses (`/bus`), 6 matrices (`/mtx`), main LR (`/main/st`) and M/C (`/main/m`), 8 DCAs (`/dca`), 6 mute
groups.

Node layouts, token index from 0 after the path. Positions were read off a firmware 4.0 export. Positions that
held a non-default value there are save-proven; the rest are from real files.

| Node | Tokens |
|---|---|
| `/ch/NN/config` | name, icon, colour, source. Bus and DCA config carry three (no source). Aux in config carries a source: `/auxin/01/config "" 55 GN 33` |
| `/ch/NN/preamp` | digital trim, invert, low cut on, slope (literal dB/oct, for example `24`), low cut freq. Example `+0.0 OFF OFF 24  20` |
| `/auxin/NN/preamp` | trim, invert (no low cut) |
| `/mtx/NN/preamp` | invert only |
| `/ch/NN/delay` | on, time ms |
| `/ch/NN/gate` | on, mode, threshold, range, attack, hold, release, key source. Example `OFF GATE -80.0 60.0 10 50.2  258 0` |
| `/ch/NN/gate/filter`, `/ch/NN/dyn/filter` | on, type, freq |
| `/ch/NN/dyn` | on, mode (COMP/EXP), detector (PEAK/RMS), envelope (LIN/LOG), threshold, ratio, knee, makeup, attack, hold, release, position (PRE/POST), key source, mix, auto |
| `/mtx/NN/dyn`, `/main/*/dyn` | as above with no key source, so mix is at 12 and auto at 13 |
| `/ch/NN/insert` | on, position (PRE/POST), selection (OFF, FX1L to FX8R, AUX1 to AUX6) |
| `/ch/NN/eq/B` | type, freq, gain, Q. Example `PEQ 1k97 +0.00 2.0` |
| `/ch/NN/mix` | on, fader, LR assign, pan, M/C assign, M/C level |
| `/ch/NN/mix/BB` | on, level, pan, tap, pan follow. Even sends hold on and level only |
| `/bus/NN/mix` | as a channel's mix |
| `/mtx/NN/mix`, `/main/m/mix` | on, fader |
| `/main/st/mix` | on, fader, pan |
| `/bus/NN/mix/MM`, `/main/*/mix/MM` | sends to matrices, same tokens as a channel send |
| `/ch/NN/grp` | `%dcaBits %muteBits` (also on auxin, fxrtn, bus, mtx, main) |
| `/ch/NN/automix` | group (OFF/X/Y), weight (`-12.0`) |
| `/dca/N` | on, fader; `/dca/N/config` name, icon, colour |

From real files:

- Aux inputs have a source and trim but no low cut, dynamics, insert or delay. FX returns have no source and no
  preamp. The X32 has no aux input dynamics.
- Pan, tap and pan follow are stored on the odd send of each bus pair only, linked or not. An even send node is
  two tokens. Firmware before 4.0 writes no pan follow.
- LR assign (mix token 2) is a send to the stereo main at unity. Tokens 4 and 5 are the M/C switch and level.
  Both are after the fader.
- Bus, matrix and main config lines are 3 tokens. LR and M/C names can be empty.

## Enumerations

- Colour codes: `OFF RD GN YE BL MG CY WH`, plus inverted forms with an `I` suffix (seen as `MGi`). Colour is
  token 2 of `config`. (real files)
- Icons: 1 to 74, 1 = none. (real files)
- Names: twelve characters, plain ASCII, no double quote. (real files)
- Strip source (channel and aux in config): 0 off, 1-32 routed inputs, 33-38 aux inputs 1-6, 39-40 USB L/R,
  41-48 FX returns 1L-4R, 49-64 mix buses. (real files bear out 33-38 and 39-40; the rest protocol doc)
- Key source (gate and dyn): the same list, 0 off. (real files)
- Key filter type: `LC6 LC12 HC6 HC12`, or a bare Q (`1.0 2.0 3.0 5.0 10.0`) that means a band pass around the
  frequency. (real files)
- Gate mode: `GATE`, `EXP2`/`EXP3`/`EXP4` (1:2, 1:3, 1:4 expander), `DUCK` (ducker). (real files)
- EQ band type, channel: `LCUT LSHV PEQ VEQ HSHV HCUT` (VEQ is the vintage bell whose bandwidth narrows with
  gain). Bus, matrix and main EQ has six bands. Matrices and mains add crossover types on bands 1 and 6:
  `BU6 BU12 BU18 BU24`, `BS12 BS24`, `LR12 LR24` (band 1 a high pass, band 6 a low pass). The desk ignores band
  2 while band 1 is a crossover, and band 5 while band 6 is one. (real files; the protocol doc lists
  crossovers for matrices and mains only)
- Send tap: `IN/LC`, `<-EQ`, `EQ->`, `PRE`, `POST`, `GRP`, in signal order. The arrow says which side of the EQ.
  (real files)
- Insert position: PRE is ahead of the EQ, POST after it. (manual, for buses, mains and matrices; unconfirmed
  for channels)
- Membership bitfields: `%` then bits, the rightmost character is group 1. Mute groups read the same way.
  (save-proven)

## Subgroups (GRP)

An X32 bus has no mode. Each input strip picks one tap per bus pair. `GRP` assigns the strip to the pair after
its fader and pan. A pair that takes GRP assigns from some strips and level sends from others behaves as a mix
bus. (real files)

Unconfirmed: that the stored send level and pan of a GRP send do nothing. GRP sends are nearly always stored at
`-oo`, which fits, but it was not measured on a desk.

## Input routing and head amps

- `/headamp/NNN gain phantom` (for example `+10.0 OFF`): 000-031 local, 032-079 AES50 A, 080-127 AES50 B. Card
  and user inputs have no head amp in the scene. Gain and 48V live here, not in `/ch/NN/preamp`. (real files)
- Head amps are addressed by physical input, not by channel. Source 1-32 on a channel is a routed input.
  `/config/routing/IN` maps routed inputs to sockets in blocks of eight. On a default local patch, source N is
  headamp N-1. (real files)
- `/config/routing/IN` has five tokens: four 8-wide blocks for sources 1-32 (`AN1-8`, `A1-8`, `B17-24`,
  `CARD1-8`, `UIN1-8` ...) and an aux block. `AUX1-4` leaves all six aux inputs on the rear jacks (the name is
  kept from older firmware). A family range in that slot (`AN1-4`, `A1-6`) takes aux inputs 1-2, 1-4 or 1-6 from
  that family. A scene with no `IN` line reads as local inputs on 1-32 and aux inputs on their jacks. (real
  files)
- `/config/routing/PLAY` holds the playback blocks (the alt source of every routed input), and
  `/config/routing REC|PLAY` is the switch (virtual soundcheck). Head amps still follow the `IN` patch in PLAY.
  (real files)
- `/config/userrout/in` (firmware 4.x): 32 values, 0 off, 1-32 local, 33-80 AES50 A 1-48, 81-128 AES50 B 1-48,
  129-160 card 1-32, 161-166 aux inputs 1-6, 167-168 talkback inputs. (real files, checked against head amps
  with 48V on)
- Blocks start one past a multiple of eight (inputs) or four (XLR outs). A block starts at 41 at most. (real
  files)

## Outputs

- Each output slot takes a source code and a tap: `/outputs/main/NN` (1-16), `/outputs/aux/NN` (1-6),
  `/outputs/p16/NN` (1-16), `/outputs/aes/NN` (1-2), `/outputs/rec/NN`. From firmware 3.0 a third token is
  polarity. `/outputs/main/NN/delay` is on and time (0.3-500 ms). `/outputs/p16/NN/iQ` holds the Turbosound iQ
  settings. (real files)
- Slot source codes: 0 off, 1-2 main L/R, 3 M/C, 4-19 buses 1-16, 20-25 matrices 1-6, 26-57 channels 1-32,
  58-65 aux in 1-8, 66-73 FX returns 1-8, 74-75 monitor L/R, 76 talkback. (real files)
- Output tap tokens: `IN/LC`, `<-EQ`, `EQ->`, `PRE`, `POST`, and a `+M` form of each tap ahead of the fader
  (follows the strip mute). (real files)
- Physical connectors take their signal in blocks: local XLRs four at a time (`/config/routing/OUT`: `OUT1-4`,
  or four inputs such as `AN1-4`, `A5-8`); AES50 A, B and card eight at a time (`/config/routing/AES50A`,
  `AES50B`, `CARD`), from `OUT1-8`, `P161-8`, `AN1-8`, `A1-8`, `B1-8`, `CARD1-8`, `UIN9-16` (user-in slots) or
  `UOUT1-8` (user-out slots). Numbered forms `AUX1-4`, `AUXIN1-4` also occur. (real files)
- `AUX/CR` (aux outs 1-6 then the monitor pair) and `AUX/TB` (aux ins 1-6 then talkback) as X32-Edit 4.00's
  eight-wide block names. (unconfirmed)
- AES50 and card blocks reach a strip only through output slots 1-16, either directly or through the user-out
  page. (real files)
- `/config/userrout/out` (4.x): 48 values, 0 off, 1-160 inputs (as user-in), 161-166 aux in, 167-168 talkback,
  169-184 outputs 1-16, 185-200 P16, 201-206 aux outs, 207-208 monitor. (real files)

## Desk-wide nodes

| Node | Content | Source |
|---|---|---|
| `/config/chlink`, `auxlink`, `fxlink`, `buslink`, `mtxlink` | one ON/OFF per pair (16 values for 32 channels) | real files |
| `/config/linkcfg` | what a link couples: head amp + delay, EQ, dynamics, fader + mute | real files |
| `/config/mono` | mode (`LR+M` mono bus, `LCR` centre), link (M/C level follows LR fader) | real files |
| `/config/mute` | six ON/OFF mute group masters | real files |
| `/config/amixenable` | X and Y switches (firmware 3.0+). Automix acts on channels 1-8 only; the node is written for all 32 | real files |
| `/config/tape` | USB player gain L/R, autoplay | real files |
| `/config/userctrl/A` to `C`, `/btn`, `/enc` | colour, 8 buttons, 4 encoders; tokens name strips by number (`P1604`, `S2014`, `F60`) | real files |
| `/config/dp48`, `/assign`, `/grpname`, `/link` | DP48 personal mixer setup (4.x; `link` from 4.04) | real files |
| `/-stat/selidx`, `chfaderbank`, `grpfaderbank`, `sendsonfader`, `bussendbank`, `eqband`, `userbank`, `dcaspill` | surface state, 8 lines, in desk saves from 4.04 | real files |

**Solo and monitor**, `/config/solo`, 17 tokens from 0: 0 monitor level, 1 source
(`OFF LR LR+C LRPFL LRAFL AUX56 AUX78`), 2 source trim (±18), 3 channel tap, 4 bus tap, 5 DCA tap, 6 exclusive,
7 solo follows select, 8 select follows solo, 9 dim amount (0-40 dB), 10 dim on, 11 mono, 12 delay on, 13 delay
time (0.3-500 ms), 14 master control, 15 mute, 16 Use DIM for PFL. Factory line:
`0.0 LRAFL 0.0 PFL PFL PFL OFF OFF OFF -20 OFF OFF OFF 0.3 OFF OFF OFF`. The follow switches, monitor level, mute
and PFL dim are save-proven by X32-Edit saves. Token 12 is placed by order only (unconfirmed).

**Talkback**: `/config/talk ON|OFF INT|EXT`. `/config/talk/A` and `/B` hold level, dim, latch, then an 18-bit
destination map printed high bit first: the rightmost bit is bus 1, bits 1-16 buses, bit 17 LR, bit 18
(leftmost) M/C. The dim amount is `/config/solo` token 9. Save-proven by X32-Edit saves. The protocol doc orders
the three as level, latch, dim; the saves show level, dim, latch.

**Oscillator**: `/config/osc` holds level (-90 to +10 dB), f1, f2, select (`F1`/`F2`), type
(`SINE PINK WHITE`), destination 0-25 (mix buses 1-16, L, R, L+R, M/C, matrices 1-6). Whether it is switched on
is not in the scene. Factory line `-40.0 100.2 1k00 F1 PINK 0`. (real files)

## Effects

- 8 slots: `/fx/N TYPE`, `/fx/N/source L R` (for example `MIX13 MIX13`), and `/fx/N/par` with 64 positional
  values, filled with zeros past the type's own count. (real files)
- FX 1-4 take any type, as a send effect or an insert. FX 5-8 take insert types only (no reverb or delay). A
  dual type is two mono units, and a strip inserts one half (`FX5L`, `FX5R`). FX returns 1-8 are FX 1-4 L/R.
  (real files)
- Reverb codes: `HALL AMBI RPLT ROOM CHAM PLAT VREV VRM GATE RVRS`. Delays: `DLY 3TAP 4TAP`. Combined:
  `D/RV CR/R FL/R D/CR D/FL MODD`. Others: `CRS` (chorus), `DES`/`DES2`, `EXC`/`EXC2`, `ENH`/`ENH2`, `LIM`,
  `CMB`/`CMB2`, `GEQ`/`GEQ2`, `TEQ`/`TEQ2`, `PIT`/`PIT2`, `P1A`/`P1A2`, `PQ5`/`PQ5S`, `ULC`/`ULC2`,
  `LEC`/`LEC2`, `FAC`/`FAC1M`/`FAC2`, `WAVD`, `SON`, `EDI`, `IMG`, `AMP`, `DRV`. (real files)
- Parameter order for the FX 1-4 types follows the parser published with the protocol doc, with words such as
  factor `1/4 3/8 1/2 2/3 1 4/3 3/2 2 3` and mode `ST X M` for DLY. DLY offset is -100 to +100. (protocol doc,
  real files; offset unit unconfirmed)
- Insert processor `/fx/N/par` orders, from real files: `ULC` (1176 style) on, input, output, attack, release,
  ratio. `LEC` (LA-2A style) on, gain, peak, mode COMP/LIM, out gain. `FAC`/`FAC1M`/`FAC2` (Fairchild style) on,
  input, threshold, time, bias, output, balance. `P1A`/`P1A2` and `PQ5`/`PQ5S` hold 11 values, order
  unconfirmed.
- No strip has a GEQ. A graphic EQ is an FX type inserted on a bus. (real files)

## Scenes, shows and libraries

A `.scn` holds one scene. Cues, scenes, snippets and presets live in the show (`/-show/showfile/*`), libraries
under `/-libs`, preferences under `/-prefs` (clock, card, remote, RTA, lamp, about 55 controls). A `.scn` holds
none of them. Metering preferences are not in a scene. The desk has 100 scene slots. (protocol doc,
unconfirmed in files)

A forum report says that updating a desk to 4.x wipes its stored scenes, snippets and libraries. (unconfirmed)

## Firmware and the header

The header is a scene format number, not the firmware. Identify a scene by its line set. (real files)

| Firmware | Header | Lines added |
|---|---|---|
| 1.x | not seen | no file seen |
| 2.x (2.08-2.12) | `#2.1#` | baseline, 169 keys; `/outputs/main/NN` is source and tap |
| 3.0 | `#2.6#` | `/config/amixenable`; output polarity token. 171 keys |
| later 3.x | `#2.7#` | `/config/routing/PLAY`, `/config/routing`. 173 keys |
| 4.00-4.03 | `#4.0#` | `/config/userrout/in` (32), `/out` (48), `/config/dp48`, `/assign`, `/grpname`. 178 keys. Routing tokens `UIN`/`UOUT` |
| 4.04-4.05 | `#4.0#` | `/config/dp48/link`; desk saves add the 8 `/-stat` lines |
| 4.06-4.13 | `#4.0#` | `/main/st/grp`, `/main/m/grp`, `/mtx/NN/grp` (matrices and mains in DCAs and mute groups) |

A `#2.1#` scene can hold the 3.0 lines, and is then a 3.x save. (real files)

## What X32-Edit writes

- The X32-Edit 4.x "Initialize Settings > Mixer" scene (save-proven): header padded to 127; buses 1-12
  "MixBus n" cyan, 13-16 "Fx n" magenta at 0 dB feeding FX 1-4; FX 1-4 a vintage room, hall, delay and chorus
  (VRM, HALL, DLY, CRS), FX 5-7 dual graphic, FX 8 true graphic; aux in 1-6 on sources 33-38, 7-8 the USB player
  (39, 40) named, yellow, panned hard; FX returns at 0 dB, odd left, even right, sends post-fader; input sends to
  buses 1-8 `EQ->`, 9-16 `POST`; channel dyn PEAK, bus dyn RMS; local outs 1-14 buses 1-14, 15-16 main L/R; P16
  1-16 channels 1-16 pre-EQ; mains white with six matrix sends.
- The X32-Edit 4.3.0 blank holds the 4.06+ `grp` lines and `dp48/link` but no `/-stat` lines. A scene with that
  shape is likely an editor save. (unconfirmed)
- X32-Edit keeps no library folder. It saves a scene wherever it is pointed. (real files)
