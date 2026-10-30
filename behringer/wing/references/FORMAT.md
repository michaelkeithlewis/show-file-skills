# WING snapshot format

Notes on the Behringer WING snapshot (`.snap`) for the full size, Compact and Rack. Contributed by markcarlberg.
Most of this page is desk research and reading of real files, not save-proven. Each line says where it comes
from:

| Label | Meaning |
|---|---|
| save-proven | A WING Edit or desk save moved it: one control changed, the named keys changed. |
| real files | Consistent across many real snapshots, never moved in isolation. |
| protocol doc | The unofficial WING Remote Protocols document V3.0.5-1 (OSC tables, effects appendix, JSON tree). |
| libwing | libwing 1.0.5's `propmap.jsonl`, a node map generated from a WING Compact on 3.0.5. |
| manual | Behringer's WING user manual (2025-10-20, FW 3.1) or WING Effects Guide (FW 2.1). |
| unconfirmed | A reading that fits what was seen. Treat it as a guess until a save settles it. |

## Container

- `.snap` is one JSON document. Paths below join keys with dots (`ae_data.ch.1.fdr`); WING keys never contain a
  dot. Numeric keys are strings (`"1"`); sort them as numbers. (real files)
- Top level: `type` (`snapshot.N`), header keys, then `ae_data` (audio engine), `ce_data` (control surface),
  `ae_globals`, `ce_globals`. Some versions add `active_show`, `active_scene`, `scopes`, `wedit_layer`. (real
  files)
- Desk header: `creator_fw` (`3.1-0-g9f314617:release` = 3.1), `creator_sn`, `creator_model` (`ngc-full` on
  1.x/2.0, `wing` on 3.0.x full size, `wing-fullsize`/`wing-compact` on 3.1), `creator_version` (hardware code:
  `SX45-XU2` full size, `T55-XU3` Compact), `creator_name`, `created`. (real files)
- WING Edit 3.x saves use `creator`/`creator_vers` and no `creator_fw`. Their `creator_model` is the editor
  setting, not proof of the desk. INIT CONSOLE snapshots from WING-Edit carry `creator_model` `WING-EDIT`,
  `creator_fw` `VERSION_FULL`, `creator_sn` `NO_SERIAL`, and the editor version in `creator_version`. (real
  files)
- One format serves all three models. One snapshot holds the layer banks of every model and opens on any model.
  (real files)
- Real snapshots nest seven levels deep. (real files)
- Number spelling: an integer when whole, else a 32-bit float to ten significant digits and at most nine
  decimals (`0.100000001`, `-0.199999809`). Booleans are JSON `true`/`false`. Another float printer changes
  every line. (real files)

## `ae_data` layout

`cfg`, `io`, `ch` (1-40), `aux` (1-8), `bus` (1-16), `main` (1-4), `mtx` (1-8), `dca` (1-16), `mgrp` (1-8),
`fx` (1-16), `cards` (`wlive`, `wmadi`), `play`, `rec`. (real files)

| Strip | Keys (3.3 INIT) |
|---|---|
| `ch.N` | `in`, `flt`, `clink`, `col`, `name`, `icon`, `led`, `mute`, `fdr`, `pan`, `wid`, `solosafe`, `mon`, `proc`, `ptap`, `peq`, `gate`, `gatesc`, `eq`, `dyn`, `dynxo`, `dynsc`, `preins`, `main`, `send`, `tapwid`, `postins`, `tags` |
| `aux.N` | as a channel without `flt`, `peq`, `gate`/`gatesc`, `proc`, `ptap`, `dynxo`, `tapwid`, `postins` |
| `bus.N` | `in`, `col`, `name`, `icon`, `led`, `busmono`, `mute`, `fdr`, `pan`, `wid`, `mon`, `eq`, `dyn`, `dynxo`, `dynsc`, `preins`, `main`, `send`, `postins`, `dly`, `tags` |
| `main.N` | as a bus without `main` (sends to matrices only) |
| `mtx.N` | as a main plus `dir`, without `send` |
| `dca.N` | `name`, `col`, `icon`, `led`, `mute`, `fdr`, `mon` |
| `mgrp.N` | `name` (`MGRP.1`), `mute` (engaged) |

Mains are stereo unless `busmono` is set. There is no fixed LR: main 1 reads like the other three. (real files)

## Value laws

| Quantity | Law | Source |
|---|---|---|
| Fader, send, main send level | dB as a float; `-144` is the bottom stop and means off. No fixed grid: files hold whole dB, tenths stored as floats and binary fractions down to 1/512 dB side by side. The protocol doc's "-oo..10 in 1024 steps" is the fader travel, not a storage grid | real files |
| Pan | -100 to +100 | real files |
| Width `wid` | percent; can exceed 100; negative swaps L/R; 0 folds to mono | real files |
| Frequency, Q | Hz and Q as floats | real files |
| Input balance `in.set.bal` | dB between legs, -9 to +9; law against pan not stated | protocol doc |
| Trim `in.set.trim` | dB | real files |
| Delay | value in the unit `dlymode`/`mode` names: `M`, `FT`, `MS`, `SMP` (default 0.1 in mode M). The speed of sound and sample rate behind M, FT and SMP are unconfirmed | real files |
| Colour `col` | index 1-18, WING-Edit's swatches: 1 slate blue (default), 2 blue, 3 violet, 4 teal, 5 green, 6 lime, 7 yellow, 8 brown, 9 red, 10 salmon, 11 magenta, 12 purple, 13 amber, 14 light blue, 15 orange, 16 mint, 17 grey, 18 light grey. Picker grid by row: 13 12 6 / 7 11 5 / 14 9 16 / 2 15 4 / 1 10 17 / 3 8 18 | save-proven: one save with each swatch on its own channel, read back |
| Icon | 0 blank, otherwise 1-614 in seven blocks | real files |
| Tags | comma string: `#D13` DCA 13, `#M2` mute group 2, plus free text (`BAND,KICK`) | real files |
| Strip names in references | `CH.11`, `AUX.3`, `BUS.11`, `MAIN.2`, `MTX.4`; also `SELF`, `OFF` | real files |
| Automix weight `postins.w` | dB (`3.7` for +3.7) | save-proven |

## Sources, sockets and patching

- `ae_data.io.in.<GRP>.<n>` is a socket. Strips name a socket rather than own it, and any number of strips can
  hear one. Groups and counts as the snapshot declares them: `LCL` 24, `AUX` 8 (Aux In sockets), `A`/`B`/`C` 48
  each (AES50 A-C), `SC` 32 (StageConnect), `USB` 48, `CRD` 64 (card), `MOD` 64 (module), `PLAY` 4, `AES` 2,
  plus internal `USR` 56 (user signals) and `OSC` 2. (real files)
- Socket keys: `mode` (`M`, or `ST` pairing an odd and even socket into one stereo input), `g` gain, `vph` 48V,
  `mute`, `pol`, `col`, `name`, `icon`, `tags`. Preamp groups (Local, AES50 A-C) add `rmt` (remote) and `rcvc`.
  An unnamed socket is `""`. (real files)
- Strip patch `in.conn`: `grp`, `in`, `altgrp`, `altin`. `in.set.altsrc` selects the alt, `in.set.srcauto` is
  the auto source switch, `io.altsw` is the global alt switch and `io.autoaltovr` its override. (real files)
- A strip can hear a bus: `{grp: BUS, in: 2b-1}`, buses counted left then right (bus 13 is BUS 25). (real files;
  whether that plays in stereo is unconfirmed)
- The stereo width of an input comes from the socket mode, not a strip pairing. (real files)
- Polarity: socket `pol` and strip `in.set.inv` each invert, and both together cancel. (real files)
- Source link `clink` (channel, aux): when on, the strip shows its source's name, colour and icon over its own.
  Linked with nothing patched, or to an unnamed source, it shows no name, colour 1, icon 0. A linked strip fed
  from a bus shows the bus name. (save-proven in WING-Edit 3.3.3; main and matrix feeds not checked)
- User signals `io.in.USR.<n>.user`: USR 1-24 hold `grp`, `in`, `tap` (PRE/POST) and `lr` (`L+R`). The higher
  ones hold only `grp` and `in` and take a socket (a split). The 3.3 INIT lists USR 25-56 in that shape. A user
  signal is the only way an input strip reaches an output. On an input channel PRE means its `ptap` point. (real
  files)
- On 1.12 the source of a user signal is kept apart at `io.user.<n>`. (real files)

## Outputs

- `io.out.<GRP>.<n>` = `{grp, in}`. Output groups: `LCL` 8, `AUX` 8 (aux outs), `A`/`B`/`C` 48, `SC` 32, `USB`
  48, `CRD` 64, `MOD` 64, `REC` 4, `AES` 2. (real files)
- Sources: `BUS`, `MAIN`, `MTX` counted left then right (MTX 5 is matrix 3 left, MAIN 6 is main 3 right); `MON`
  1-2 the monitor pair; `USR n`; a physical group (a split); `SEND n`, the send of an effects slot; `OFF`. (real
  files)
- `io.out.SC.N.in`: the number under a StageConnect output that plays nothing. (real files)

## Channel processing

- Filters `flt`: `lc`, `lcf`, `lcs`, `hc`, `hcf`, `hcs`. Slopes are strings (`"24"`, `"12"`) from firmware 3.0.5.
  Older files have none (12 implied). (real files)
- Tool filter (same object): `tf` on, `mdl` `TILT`/`MAX` (Maxer)/`AP1`/`AP2` (all-pass), `tilt`. MAX adds `low`,
  `proc`. AP adds `f`. (real files)
- Pre-EQ `peq` (channels only): `on`, three bells `1g 1f 1q` to `3g 3f 3q`, in series ahead of the main EQ.
  (real files)
- EQ `eq` (STD model): `on`, `mdl`, `mix` (%), low band `lg lf lq leq`, bells `1g 1f 1q` up to 4 (inputs) or 6
  (bus, main, matrix), high band `hg hf hq heq`. Mix strips add `tilt`. (real files)
- `leq`/`heq` tokens: `PEQ`, `SHV`, `CUT` (original cut, no slope named), `BW6`, `BW12`, `BS12`, `LR12`, `BW18`,
  `BW24`, `BS24`, `LR24`, `BW48`, `LR48`. A missing key is a shelf. A cut is a pass filter, never a shelf. (real
  files)
- EQ models other than `STD` (`SOUL`, `E88`, `E84`, `F110`, `PULSAR`, `MACH4`) use keys of their own (the E84
  `lf` is a switch position). SOUL mid bands `lmf lmg lmq lmf3 hmf hmg hmq hmf3`. PULSAR `eq1`,
  `1lb 1latt 1lf 1hw 1hb 1hf 1hatt 1hattf`, `eq5`, `5lb 5lf 5md 5mf 5hb 5hf`. (real files)
- Process order `proc`: four letters, G gate, E EQ, D dynamics, I insert 1, each once. Default `GEDI`. Files hold
  GEDI (most), EDGI, GEID, EGDI, GIED, IGED, EGID. (real files)
- Pre-send tap `ptap` (channels): `IN` (after preamp, ahead of cuts), `FILT` (after cuts), `3`/`4`/`5` (after the
  first, second, third slot of `proc`), `PFL` (after the fourth, before the fader), `AFL` (after the fader,
  ahead of INS 2), `POST` (after INS 2). Default `5`. WING Edit 3.1 labels the last six TAP 3, TAP 4, TAP 5, PRE
  FDR, POST FDR, POST PROC. (manual, protocol doc)
- Inserts: `preins` {`on`, `ins` `NONE`|`FX1`-`FX16`}, `postins` {`on`, `mode` `FX`|`AUTO_X`|`AUTO_Y`, `ins`,
  `w`}. Channel INS 1 sits where `proc` puts the I (always pre-fader). INS 2 is always post-fader. Aux inputs have
  INS 1 only. Bus, main and matrix: INS 1 pre-fader, INS 2 post-fader. An unused insert is often left on with
  `NONE`. (manual 6.1, real files)
- Automix: `cfg.amix.x`/`.y` masters, and per strip `postins.mode` AUTO_X/Y and `w`. (save-proven)

## Dynamics slots

- A channel has a gate slot (`gate`, key `gatesc`) and a dynamics slot (`dyn`, key `dynsc`), plus `dynxo`. Aux
  inputs have `dyn`/`dynsc` only. Buses, mains and matrices have `dyn`, `dynsc`, `dynxo`. Since 3.1 any gate or
  compressor model can sit in either channel slot, so the model, not the slot, sets the key set. (real files)
- Every slot: `on`, `mdl`, and from 3.1 `mix` and `gain`, then the keys of the model. (real files)
- Stock `GATE`: `thr`, `range`, `att`, `hld`, `rel`, `acc` (ACCENT, undocumented), `ratio` as a string (`"1:3"`;
  a value other than GATE makes it a downward expander). Factory `thr` -40 in a channel gate slot, -36 in an aux
  slot. (real files)
- Stock `COMP`: `thr`, `ratio`, `knee`, `det` (`RMS`/`PEAK`), `att`, `hld`, `rel`, `env` (`LOG`/`LIN`), `auto`
  (AUTO ENV: programme-dependent times, not auto makeup). Threshold in dBFS. (real files)
- Key `gatesc`/`dynsc`: `type` (`OFF BP LP6 LP12 HP6 HP12`), `f`, `q` (kept when OFF), `src` (`SELF`, `CH.n`
  ...), `tap` (`IN` on channels, `BUS` on mix strips). Only OFF and BP seen in files; the cut types come from the
  editor's list.
- Crossover `dynxo`: `depth`, `type`, `f`, and from 3.1 `q` (INIT 0.4). (real files)

Model tokens and their keys (real files at defaults unless marked):

| Token | Unit modelled | Own keys |
|---|---|---|
| `DUCK` | ducker | gate keys without ratio |
| `PSE` | source expander | `thr`, `depth`, `fast`, `peak` |
| `CMB` (aux; channel gate slot from 3.1) | PSE + LA combo, one switch | `thr depth fast peak ingain cpeak cmode`; before 3.1 an aux slot with no `mdl` |
| `WARM`, `DS902`, `WAVE`, `RIDE` | preamp saturation, de-esser, transient shaper, auto rider | own keys (WARM `drv hrm col trim`, `wmix` from 3.1) |
| `9000G`, `D241G`, `E88`, `EXP` | SSL 9000 gate, Drawmer DL241 gate, Neve 88 gate, WING expander | `thr range hld rel fast mode`; `thr slow`; `thr range rel hyst fast m40`; COMP's keys |
| `76LA` | 1176 | `in`, `out`, attack/release knob 1-7 running backwards (7 fastest), `ratio` 4, 8, 12, 20, `ALL` |
| `LA`, `L100` | LA-2A, TLA-100 | LA `ingain`, `peak` 0-100, `mode` COMP/LIM; L100 `ingain`, `gr`, `att`/`rel` FAST/MED/SLOW |
| `2250` | API 2500 | `thr` on the unit's dBu scale (+2 to +10 in files, not dBFS), `ratio`, `att`, `rel`, `gain`, `mix`, knee HARD/MED/SOFT, `type` OLD (feedback)/NEW; no THRUST control |
| `B160`, `B560`, `SBUS` | dbx 160, dbx 560, SSL bus | B160 `thr`, `comp`, `gain`, no time controls, no knee switch; B560 EASY switch; SBUS stepped ratio/attack/release, `thr`, makeup |
| `NSTR` | Distressor | `in`, `out`, attack/release 0-10, ratio incl. `NUKE` |
| `RED3`, `9000C`, `D241C`, `BLISS`, `E88C` | Red 3, SSL 9000, DL241, Eternal Bliss, Neve 88 | `thr ratio att rel auto`; `thr ratio rel fast peak`; `thr ratio att rel lim lrel auto`; `thr ratio att rel afast alog glon glim`; `thr ratio knee rel`, attack a word |
| `ECL33` | Neve 33609 | `con cthr crec cfast`, `lon lthr lrec lfast`; `crec` recovery words `100`, `400`, `800`, `A1`, `A2` (the word for 1.5 s not seen) |
| `F670`, `LMT`, `ONEC` | Fairchild 670, LMT, One Knob | `in thr time bias` (knob positions); `tspd trans tgain ton comp cgain con`; `gr dag` |
| `DEQ`, `DEQ2` | dynamic EQ, dual dynamic EQ | see "Dynamic EQ models" |

Control ranges found by loading values past the ends into WING Edit 3.3.3, which clamps to the end on load
(save-proven):

| Model | Range |
|---|---|
| `76LA` | `in`, `out` -48 to 0 dB (an `in` of -58 shows -48.0) |
| `L100` | `ingain` (GAIN) 0 to 10, `gr` (GAIN REDUCTION) 0 to 10 (40 shows 10.0) |
| `SBUS` | attack 0.1 / 0.3 / 1 / 3 / 10 / 30 ms; release 0.1 / 0.2 / 0.4 / 0.8 / 1.6 s and `AUTO`; ratio 1.5 / 2 / 3 / 4 / 5 / 10:1; threshold -40 to 0 dB; makeup -6 to +12 dB |
| `B160` | `thr` 0.01 to 5 V (0.223607 reads "0.22"); `comp` 1:1.1 to 1:50; `gain` -6 to +12 dB |

The WING-Edit 3.3.3 model list holds RED3, 9000C, 9000G, F670, D241C, D241G, BLISS, LMT, DEQ, DEQ2, E88, E88C,
ECL33, ONEC, EXP, each read off its defaults with `on`, `mdl`, `mix`, `gain` (save-proven). It also holds
`3CMP`, not seen in files. Before 3.3 the Drawmer is `D241` in either slot, and its keys tell which (D241C
`thr, ratio, att, rel, lim, lrel, auto`; D241G `thr, slow`). (real files)

## Dynamic EQ models

Save-proven from WING-Edit's page and saves (2026-10-29): `DEQ` (DYNAMIC EQ, one band) and `DEQ2` (DUAL DYNAMIC
EQ, keys prefixed `1-`, `2-`) sit in either dynamics slot. Keys: `thr` dBFS, `ratio` (1.2-10), `att` and `rel`
ms, `g` the band gain in dB, `f`, `q`, `filt`, `mode`. `mode`: `high` Above, `low` Below. `filt`: `BP` is the
default. The other `filt` spellings (`LP6`, `LP12`, `HP6`, `HP12`, `FLAT`) are unconfirmed by a save.

## Sends, buses, matrices

- Channel and aux sends `send.<n>` (buses 1-16) and `send.MX<n>` (matrices 1-8): `on`, `lvl`, `pon`, `mode`
  (`PRE`/`POST`/`GRP`), `plink`, `pan`. PRE is the channel's `ptap` point. (real files)
- `pon` is IGNORE CHANNEL MUTE (TAP ONLY) in WING-Edit's send options. Nearly all true values sit on PRE sends.
  (real files)
- Bus and main sends to matrices: `on`, `lvl`, `pre`. Main assigns `main.<n>`: `on`, `lvl`, `pre`. A bus never
  sends to itself. (real files)
- Group mode: a send into a GRP bus is an on/off assign after the strip's fader and pan; level and pan do
  nothing. (real files)
- `busmode` (PRE/POST/GRP) on buses and matrices and per-send `ind` exist in `snapshot.9` (WING Edit 3.x, desk
  3.0.4) only. `snapshot.10` and `.11` have neither, and the `mode` of each send is its tap. In files with
  `busmode`, a send with `ind` off always carries its bus's mode. Where neither key exists, the sends are the
  only statement of a bus's mode. (real files; `ind` as an independent-send switch unconfirmed)
- The pre-3.0.5 per-send width `send.<n>.wid` has no 3.x home. (real files)
- Mix strip `in.set`: `inv`, `trim`, `bal`. Mix delay `dly`: `on`, `mode`, `dly` (3.0+); before 3.0 `dly.m`, in
  metres, no mode. (real files)
- Matrix direct input `dir` (3.x): `on`, `lvl`, `inv`, `in` (`OFF` or `CH.3`). Before 3.0, several per matrix:
  `dir.1`, `dir.2` ... each with `in`, `lvl`, `on`, `tap` (PRE/POST), `inv`. (real files)

## Monitor, solo, talkback, oscillator

- `cfg.mon.1`/`.2`: `lvl`, `inv`, `pan`, `wid` (0 mono, 100 stereo), `eq` (6 bands plus `lsg lsf hsg hsf`), `lim`,
  `dly` {`on`, `m`}, `dim`, `pfldim` (dB), `eqbdtrim`, `srclvl`, `srcmix`, `src` (`MAIN.1`), `dirin`, `tags`.
  (real files)
- `cfg.solo`: `mode` (`LIVE`/`SIP`), `mon`, `mute`, `chtap`, `bustap`, `maintap`, `mtxtap`, `srcsolo`.
  `ce_data.cfg.soloexcl`, `solofsel`, `selfsolo` are exclusive, solo follows select, select follows solo. (real
  files)
- Per strip `mon` `A`/`B`/`A+B` picks the solo bus. DCAs have it too. (real files)
- `cfg.talk`: `assign` (host channel: `OFF`, `CH40`, `AUX8`), `lvl`, and `A`/`B` each with `mode`
  (`AUTO PUSH LATCH`), `mondim`, `busdim`, `indiv`, and destination switches `B1`-`B16`, `MX1`-`MX8`, `M1`-`M4`.
  The input of the host channel is the talkback mic (manual 5.5). `lvl` is -144 in every file; the level is the
  TALK LEVEL knob. On 1.x/2.0 `mondim` is a switch; 3.x holds 0-40 dB. (real files, manual)
- Oscillators are sockets `io.in.OSC.1`/`.2`, each with `osc` {`mode` SINE/PINK/WHITE, `lvl` -40 to +6 dB, `f`
  20-20000}. A strip or output patches them; they have no destination. On 1.12 they were `cfg.osc.N.mode/f/lvl`.
  (real files)
- `cfg.mainlink` (M/C style link), `cfg.dcamgrp`, `cfg.rta`, `cfg.mtr` (meter taps per page and surface,
  `mainmtr`, `mainpos`). (real files)

## Effects and FX loops

- 16 slots, `ae_data.fx.<n>` = `{"mdl": CODE, "fxmix": 0-100, ...}`. An empty slot is
  `{"mdl": "NONE", "fxmix": 100}`. (real files) That a slot holding only `mdl` and `fxmix` loads the model's
  defaults is unconfirmed.
- Premium models (every reverb and delay, plus `CHORUS`, `FLANGER`, `DIMCRS`, `PITCH`, `D-PITCH`) run only in
  slots 1-8. Standard and channel models run in 1-16. (manual, Effects Guide; consistent with real files)
- Reverbs include `HALL ROOM CHAMBER PLATE CONCERT AMBI BPLATE V-PLATE V-ROOM V-REV GATED REVERSE VSS3 SHIMMER
  SPRING`. Delays `ST-DL TAP-DL TAPE-DL OILCAN BBD-DL DEL/REV`. Processors include `DE-S2`, `EXCITER`, `ENHANCE`,
  `DEQ3`, `C5-CMB`, `LIMITER`, `GEQ`, `PIA`, `PCORR`, `DOUBLE`, `P-BASS`/`SUB`/`SUB-M`, `V-IMG`, `TAPE`, `BODY`,
  `SPKMAN`, `PULSAR`, `*VINTAGE*`, `*MASTER*`, `*BUS*`, `*EVEN*`, `*SOUL*`, channel EQs and amps. (real files)
- File spellings beat the protocol doc where they differ: `DE-S2` `gdr` `m`/`f` and `mode` `st`/`ms`; Enhancer
  `stlvl`/`mlvl` (doc `stlv`/`lmvl`). libwing beats the doc on several reverb ranges and keys (HALL shape 0-250,
  size 2-100; GATED/REVERSE `hsf`, not `hfs`; BPLATE `mspd`, not `msdp`). (real files, libwing)
- `*VINTAGE*` (FET comp + Pulsar EQ + LA leveler) keys: `d_in`, `d_out` -48 to 0, `d_att`, `d_rel` 1-7,
  `d_ratio` 4/8/12/20/ALL, `d_on`; the Pulsar keys; `l_ingain`, `l_peak` 0-100, `l_mode` COMP/LIM, `l_on`. (real
  files)
- `PULSAR` (Pultec P1a + M5) FX keys: `mix`, `eq1` + `1lb 1latt 1lf 1hw 1hb 1hf 1hatt 1hattf`, `eq5` +
  `5lb 5lf 5md 5mf 5hb 5hf`. (real files)
- No tempo node exists. Tap tempo sets the `time` of a delay. (real files)
- Outboard loop: a slot with `mdl` `EXT` and `egrp`, `ein` (return socket), `emode` (`M`/`ST`), `lat`, `trim`.
  (real files) Unconfirmed: that ST returns on `ein` and `ein+1`, and that the send is whichever output plays
  `SEND 2k-1` (and `2k` for stereo) for slot k. This fits every EXT slot in files.
- Common file convention for send effects: the effect inserted (`preins`) on a bus, the bus off the mains, the
  return a channel or aux whose `in.conn` is that bus. (real files)

## Layers, custom controls, safes

- `ce_data.layer.<bank>`: `sel`, `spidx`, then layers `"1"`... each with `ofs`, `name`, and positions
  `"n": {type, i, dst}`. Banks: `L`, `C`, `R` (full size), `CMPCT` (Compact), `RCK` (Rack), `EXT` (extender),
  `VRT` (virtual surface), `WEDIT` (WING-Edit's view, 3.3). WING Edit 3.1 wrote its view as top-level
  `wedit_layer` (`count` where 3.3 has `spidx`). A layer can run past the faders of its bank; up to 40 positions
  seen. (real files)
- Position numbering: `CH` 1-40 channels, `CH` 41-48 aux inputs; `BUS` 1-16 buses, 17-20 mains, 21-28 matrices;
  `DCA` 1-16; `OFF` (or 0) empty. (real files)
- Factory layouts, in every file that names its layers (real files):

| Bank | Layers |
|---|---|
| L | CH1-12, CH13-24, CH25-36, CH37-AUX, BUSES, USER 1, USER 2 |
| C | DCA, MAIN, AUX, BUSES, USER 1, USER 2 |
| R | MAIN, DCA, CH1-40, AUX, BUSES, USER 1, USER 2 |
| CMPCT | CH1-12, CH13-24, CH25-36, CH37-AUX, BUSES, MAIN/MTX, DCA, USER 1, USER 2 |
| RCK | CHANNELS (CH1-40), AUX, BUSES, MAIN/MTX, DCA |

- A full size desk saves the CMPCT bank as the desk's own runs or empty. A CMPCT bank somebody arranged points
  to a Compact. (real files)
- `ce_data.user`: 16 custom pages (4 encoders, 8 buttons each), USER and DAW pages, GPIO pages, Compact U/D/MM
  pages. 3.3 adds `ledstate` per control (page 1 and USER in the INIT). (real files)
- `ce_data.safes` (3.x): strings with one character per item, space = not safe, `+` = safe, per group (`ch`,
  `aux`, `bus`, `main`, `mtx`, `dca`, `mute`, `fx`, `source.<grp>` ...) and per area. 1.12 used `safes.ch.N`
  booleans and `safes.area.L/C/R`. Per-input `solosafe` is separate. (real files)

## Library files

- `.show` (`showfile.1`): `type`, `creator_fw`, `creator_sn`, `creator_model`, `creator_name`, `created`,
  `scenes.count`, `scenes.N.name/skip/link/type/file`; a list that points at `.snap` files. (real files)
- `.layer` (`faderlayer.1`): `type`, `creator`, `vers`, `model`, `name`, `layer.name`, `layer.ofs`,
  `layer.N.type/i/dst`. (real files)
- `active_scene`, `active_show` (2.0+) and `scopes.*` (show-control scopes) sit in the snapshot itself. (real
  files)

## The blank snapshot

WING-Edit 3.3.3 INIT CONSOLE (everything selected), full size and Compact: `snapshot.11`, two-space indented
JSON, CRLF line ends. Save-proven: the files were held byte for byte.

- `ae_globals`: `clkrate` 48000, `clksrc` `INT`, `startmute`, `usbacfg` `48/48`, `sccfg` `AUTO`, `harmt`,
  `custsync`. Desk saves record their clock here. WING Edit 3.x saves hold no `ae_globals`.
- Channels 1-8 on `LCL` 1-8 (Compact: 1-24 on LCL 1-24); aux 1 on USB 1, aux 2 on the player; the rest
  unpatched. Delay 0.1 in mode M, off.
- Input sends: buses 1-8 and matrices pre-fader, 9-10 follow their group, 11-16 post-fader; 9-16 pan-linked.
  Main 1 on, 2-4 off, all 0 dB post-fader.
- Buses 1-8 colour 10 (salmon) at -144 off the main; 9-16 at 0 dB on main 1 (9-10 colour 6 lime, 11-16 colour
  12 purple).
- Outputs: Local 1-6 buses 1, 3 ... 11; Local 7-8 main 1 L/R; aux outs 7-8 monitor 1 L/R; the rest off.
- Every `clink` on, every socket unnamed. The aux dynamics slot holds a `GATE` (WING-Edit 3.1's INIT held the
  combo). DCA faders at -144, `mon` A.
- Recall-safe strings use their own counts (8 Local sources of 24, 24 user signals of 56; the custom row 22 on
  full size, 31 on Compact).

## Firmware differences

| Firmware | `type` | What changes |
|---|---|---|
| 1.10 | not seen | no file seen |
| 1.12.x | `snapshot.6` | user signal sources at `io.user.N`; clock and USB config inside `ae_data.cfg` (`clkrate`, `clksrc`, `startmute`, `muteovr`); oscillator at `cfg.osc`; RTA keys `ae_data.cfg.rta.rta*`; meter and surface prefs in `ce_data.cfg`; safes as booleans |
| 1.13.x | `snapshot.8` | `ae_globals` split out of `ae_data`; per-strip `main` assign blocks; input source groups renamed; safes per source and output group |
| 2.0 | `snapshot.8` | `active_show`, `active_scene`; W-LIVE auto play/rec; MIDI scene and show-control switches; safes areas renamed |
| 3.0.0-3.0.4 | `snapshot.9` | sends gain MX1-8 (16 to 24 send keys); bus, matrix and main delay as `dly.dly` + mode; talkback A/B; `CMPCT`, `RCK`, `EXT`, `VRT` banks; matrix `busmode` and single `dir` |
| 3.0.5-3.0.6 | `snapshot.10` | `flt.lcs`/`flt.hcs`; `busmode` and send `ind` gone |
| 3.1, 3.1.1 | `snapshot.11` | aux `dyn` with a model (`mdl`, `mix`, `gain`; combo spelled `CMB`) and `dynsc`; `dynxo.q`; every gate-slot model gains `mix`/`gain` (WARM's own mix becomes `wmix`); W-MADI card; `creator_model` `wing-fullsize` |
| 3.3 (WING-Edit 3.3.3) | `snapshot.11` | `ce_data.layer.WEDIT`, `autosel_WEDIT`, `safes.area.WEDIT`/`WINGEDIT`, `ledstate`; `cfg.rta.rtasrc/rtatap/rtadecay/rtadet` gone; Drawmer split into `D241C`/`D241G` (`D241` in either slot through 3.1) |

(real files) Pre-3.0 strip delay in metres, pre-3.0 matrix `dir.N`, pre-3.0.5 `send.wid`, and the 1.12 clock,
oscillator, RTA, surface, safes and MIDI keys have no direct 3.x home or move to new keys (`ae_globals`,
`io.in.OSC`, `ae_data.cfg.mtr`, `ce_globals`). Which 3.3.3 differences belong to the firmware and which to the
editor is open.

## What WING Edit writes

- WING Edit 3.0/3.1 save `snapshot.9`, two types behind a 3.1 desk, as one line of JSON, without the cut slopes
  or the aux key input. They carry `wedit_layer` and a read-only `cfg.talk.lvl`. (real files)
- WING-Edit 3.3.3 writes `snapshot.11` with all 3.1 keys, pretty-printed (about 913 KB against 365 KB for a
  one-line file). It writes `cfg.mon.N.lvl`, `cfg.talk.lvl`, `rec.path`. (real files)
- On library load WING Edit clamps emulation controls to their ends. (save-proven)
- WING-Edit 3.3.3 loads a legacy `D241` token written into a 3.3 file as the stock compressor. A 3.3 file needs
  the `D241C`/`D241G` tokens. (save-proven)
- A desk save keeps its own key order and float spelling. A snapshot whose values are swapped in place, text
  otherwise untouched, round-trips byte for byte. (real files)
