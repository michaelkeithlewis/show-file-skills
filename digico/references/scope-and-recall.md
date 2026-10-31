# DiGiCo snapshot scope and recall

On a recall, a live value takes the snapshot's value only when three things all allow it: Global Scope recalls that module in the section, no safe on the strip keeps it, and the snapshot's own scope has it. A snapshot's scope is not a table in the snapshot record. It is a flag on the stored module states that the snapshot points at, so snapshots that share a state share its scope.

Proven on a Quantum 112 at V2242 and V2242.4. Each fact comes from a one-change save (one edit on the console, Save As, then a byte compare with the file before) or from recalls fired on the console and saved. Console-saved shows from the Quantum 225, 326, 338 and 852 (V1742 to V2242) use the same flags. SD files are not tested.

Keys are (module, param, band) in hex, as in [`FORMAT.md`](FORMAT.md).

## Where a snapshot keeps its states

- Section 210 (`d2 00`) is the snapshot pool. It holds every stored module state once, as a module record like the ones in section 211.
- A snapshot lists its strips the way section 211 does, but each strip holds one u32 pool index per module instead of the modules. The strip ends with the same trailer `27 00 | index | type | name`.
- Snapshots that store the same state share one pool record.

A module record has 10 bytes between its slot count and its first slot. They hold the scope:

| Record offset | Type | Meaning |
| --- | --- | --- |
| +0x34 | u8 | scope flags: 0x04 out of the recall scope, 0x02 out of the group and auto update scope |
| +0x35 | i32 | this module's crossfade time, in quarter frames |
| +0x39 | u8 | 1 in section 211, 0 in pool states |
| +0x3a | i32 | reference count: how many snapshot strips point at this state. 0 in section 211 |

The offsets count from the record's `da 00`. The reference count is exact in every console-saved show.

## The snapshot's recall scope

- Module flag: 0x04 at +0x34 takes the whole module out of the recall scope, in every snapshot that uses this state.
- Parameter flag: 0x04 in a slot's flags byte takes one parameter out. Only these slots use it: the fader module `0c` (`21` level, `22` mute), the control group fader `10` (`21`, `22`), matrix sends `06` (`24` level, `25` on) and input aux sends `02`.
- Section 211 never holds scope flags. In the pool states of every console-saved show, +0x34 is 0 or 0x04. 0x02 appears only in the samples below.

What the console writes:

- A whole strip out (an input, an aux): 0x04 on every module of the strip, except the automation module `0a`, which it leaves, and the fader `0c`, which never gets the module flag. The fader's level and mute get the parameter flag instead.
- One column out, here EQ: every module type of that column, so EQ `04` and Mustard EQ `1c`.
- An aux out: also every input's sends to that aux. In each input's module `02`, every slot whose band is that aux gets the parameter flag, except param `f2`. Groups' send modules stay in.
- Stereo buses: the L and the R half are always scoped alike (1992 pairs in console-saved shows, no exception).

To change the scope of one snapshot only, give it its own copy of the state first: a new pool record, the snapshot's index pointed at it, and both reference counts set. Then set the flag. A flag set on a shared state changes every snapshot that uses it. A file with per-snapshot scope written this way loaded on a Quantum 112 and showed in its Recall Scope panel.

## Recall Scope panel columns

The same map of modules to columns on every strip type, rebuilt from one save with a different column out on each strip of every section:

| Column | Modules |
| --- | --- |
| Input/Trim | `01` (inputs) or `0b` (buses), and Mustard pre-amp `1a` |
| Delay | `09` |
| Filters | `07` and Mustard filters `1b` (buses: `1b`) |
| EQ | `04` and Mustard EQ `1c` |
| Dynamics | `05` and Mustard `1d`, `1e` |
| Inserts | `08` |
| Sends | `02` (inputs, groups); `06` params `24`, `25` (matrix inputs); on an aux: the inputs' sends to it |
| Fader | `0c` or `10`, param `21` |
| Mute | `0c` or `10`, param `22` |
| Panner | `0d` (inputs) |
| To Groups | `03` (inputs, groups) |
| Outputs | `0e` (inputs, auxes, groups, matrix outputs), `12` (output ports) |
| External | `13` (inputs, groups) |

Graphic EQ `0f`, Spice Rack `1f` and I/O ports have one module, the whole strip. Columns per section: inputs 13; auxes 10 (Input/Trim to Inserts, Sends, Fader, Mute, Outputs); groups 12 (to Mute, To Groups, Outputs, External); matrix outputs 9 (to Inserts, Fader, Mute, Outputs); matrix inputs 2 (Input/Trim, Sends); control groups 2 (Fader, Mute).

## Group and auto update scope

Each snapshot also has a Group & Auto Update Scope, the panel next to Recall Scope. It uses the same places with the other bit:

- Module flag 0x02 at +0x34: the whole module is out. Proven with an EQ: the console set it on `04` and `1c`.
- Parameter flag 0x02 in the slot: one parameter is out. Proven with a fader level.

No console-saved show uses it.

## Global Scope

Global Scope is per section and holds for every snapshot. It lives in section 201, in each section's group record (`ca 00 6c 00`, in front of that section's `cb` channel records). Offsets count from the `ca`:

| Group record offset | Type | Meaning |
| --- | --- | --- |
| +0x25 | u32 | recall: bit n set = module type n is recalled in this section |
| +0x29 | u32 | auto update: bit n set = module type n takes Update Group and auto update |
| +0x2d | 32 bytes | per-parameter recall, bit n = param n, for the per-parameter columns (fader level `21`, mute `22`, matrix send level `24` and on `25`) |
| +0x4d | 32 bytes | per-parameter auto update, the same bits |

- One panel column can be several module bits. Recall off for the inputs' EQ column cleared the bits of module `04` and module `1c`: `0x7c4873be` became `0x6c4873ae`.
- The fader column splits into level and mute through the per-parameter sets. Auto Update off for the inputs' fader level cleared bit `0x21` of +0x4d and nothing in +0x29.
- A default session sets every module the section has (inputs `0x7c4873be`; matrix inputs `0x42`, modules `01` and `06`). Shows narrow it.
- FX units (strip type `0e`) and Spice Rack slots (`18`) have group records of their own, with the bit of module `15` and of module `1f`. Many shows recall neither.

## Global Scope defaults and the clear (2026-10-31, editor-verified)

Files > Session Structure > clear snapshots > Restructure puts every section's Global Scope back to its default. A Restructure alone keeps Global Scope as the show has it. The offsets are the ones in the Global Scope table above.

- The recall word (+0x25) and the auto update word (+0x29) both take the default word of the section's type.
- The two 32-byte per-parameter sets (+0x2d and +0x4d) become all `ff`: every parameter on.
- The default depends only on the section type. Every group record of the 128 editor-saved default sessions (V1455 to V2242, every console) holds the default word of its type in both words, with both per-parameter sets all `ff`.
- A default word is the module types the section has, by the bit rule above. FX is bit 21 (module `15`), Spice Rack bit 31 (module `1f`), Graphic EQ bit 15 (module `0f`), Nodal Processing bits 4 and 5 (modules `04` and `05`), Control Groups bit 16 (module `10`) and output ports bit 18 (module `12`). Input ports hold none.

| Section (type) | Default word |
| --- | --- |
| Input Channels (`01`) | `7c4873be` |
| Aux Outputs (`05`), Matrix Outputs (`10`) | `7c405bb0` |
| Group Outputs (`06`), Busses (`07`) | `7c485bbc` |
| Control Groups (`0a`) | `00010000` |
| FX (`0e`) | `00200000` |
| Matrix Inputs (`0f`) | `00000042` |
| Graphic EQ (`11`) | `00008000` |
| Nodal Processing (`14`) | `00000030` |
| Spice Rack (`18`) | `80000000` |
| Output ports (`4d` to `5f`) | `00040000` |
| Input ports (`1b` to `2f`) | `00000000` |
| Monitoring (`08`), Talkback Outputs (`09`), Solo (`0b`), Talkback Input (`0c`), Video Link (`13`) | `00000000` |

- The default sessions hold input ports `1b` to `20` and output ports `4d` to `52`. The site engine takes the wider ranges in the table alike. The rest were not seen.
- Multis (`12`) is in no default session. Its default is not known.
- Proven by six captures of the clear ([`snapshots.md`](snapshots.md), "Clear all snapshots"). The words above, written into the save after a Restructure alone, give the editor's save after the clear.
- Two of the captures are SD files (SD9 V2242 and SD12 V1619). So the Global Scope layout and these defaults hold on SD files. The recall flags on pool states are still untested there.

## Misc scope

The snapshot's other recall switches are one u16 in the snapshot record. Right after the 992-byte block (below) come `u16 2`, then this u16.

| Bit | Switch | Proof |
| --- | --- | --- |
| 0 | MIDI | one-change save |
| 1 | GPOs | panel order |
| 2 | Layout ("Banks" in the manual) | one-change save |
| 3 | Duration | one-change save |
| 4, 5, 6 | Play From, Play To, Locate To | one-change saves |
| 7 | Recall at Time | one-change saves |
| 8 | CG Members | panel order |
| 9 | Gangs | panel order |
| 10, 11 | Stop, Play | panel order |
| 12 | Waves | panel order |
| 13 | Lock | one-change save |
| 14 | Fourier | panel order |

"Panel order" means the bit was read from the order of the switches on the panel, not saved on its own.

## The 992-byte block is not the scope

Before its options, each snapshot record holds `u16 0x3e0` and 992 bytes. This block is not the recall scope. It did not change by a byte in any of these one-change saves: a whole input out, one column out, one input's sends out, an aux out, one column out on each strip of every section, and both Global Scope changes. What it holds is open.

## Channel safes

Safes are plain 0 / 1 parameters on the strip. Snapshots never keep them: no pool state in any console-saved show holds one.

| Key | Safe | Keeps on a recall |
| --- | --- | --- |
| `(0c, f0, 0)` | full safe | the whole strip. Switching it on switches every safe of the strip on, Mustard's too |
| `(0c, f1, 0)` | trim | input `01`, bus trim `0b`, delay `09` |
| `(0c, f2, 0)` | aux | aux sends `02` |
| `(0c, f3, 0)` | bus | group sends `03` |
| `(0c, f4, 0)` | EQ | EQ `04`, not the filters (see below) |
| `(0c, f5, 0)` | dynamics | `05` |
| `(0c, f6, 0)` | fader / mute | `(0c, 21)` and `(0c, 22)` |
| `(0c, f7, 0)` | pan | `0d` |
| `(0c, f8, 0)` | inserts | `08` |
| `(0c, f9, 0)` | outputs | `0e`, `12` |
| `(0c, fa, 0)` | external | `13` |
| `(1a, f1, 0)`, `(1c, f4, 0)`, `(1d, f5, 0)` | Mustard tubes, EQ, dynamics | `1a`; `1c` and `1b`; `1d` and `1e` |
| `(10, f0, 0)` | control group safe | |
| `(15, f0, 0)`, `(1f, f0, 0)` | FX unit, Spice Rack slot | the unit |

About 640 input strips in console-saved shows have safes on. Switching one safe off clears full safe.

## What a recall changes

A live value takes the snapshot's value when all three allow it:

1. Global Scope recalls its module type in that section (+0x25), and for the per-parameter columns its bit in +0x2d is set.
2. No safe on the strip keeps it.
3. The snapshot's scope has it: module flag 0x04 clear on the state, parameter flag 0x04 clear on the slot.

A replay of this rule matched five recalls fired and saved on a Quantum 112, value for value and name for name.

- The EQ safe does not keep the filters. An EQ-safed channel kept its EQ but took the snapshot's HPF. With only the EQ out of the snapshot's scope, the EQ stayed and the HPF came from the snapshot. The filters are a column of their own.
- Control group membership (the fader's `(0c, 04, 0)` bits and the control groups' module `0a`) comes back only with the misc switch CG Members.
- FX units and Spice Rack slots need their own Global Scope bit (module `15`, module `1f`), no unit safe, and the snapshot's scope.

## Names on a recall

When a strip's Input/Trim column is recalled (inputs `01`, buses `0b`), the live strip and every module name take the name in the snapshot's strip trailer. Output ports come back with their module `12`, input ports with `11`. Control group names come back only with CG Members.

So a channel renamed in section 211 alone gets its old name back at the next recall that reaches its Input/Trim. The console's Update Current writes a renamed strip's name into the snapshot's strip trailer and into its Input/Trim state. The strip's other states keep the old name. Proven by recalls fired and saved on a Quantum 112, and by a one-change save of a rename followed by Update Current.

## What a recall leaves

- KLANG mode, azimuth, elevation and width on a send (`02`, params `0b`, `0e` to `10`). Level and unmute do come back.
- The fader's control group bits `(0c, 04, 0)`: they go with CG Members.
- An output socket's own source `(12, 00, 0)`: output routes come from the buses.
- The Mustard compressor's stereo link `(1d, 3f, 0)` comes back on buses, but on a stereo input it is always on after a recall, whatever is stored.
- A Spice Rack slot that the recall changes loses its preset (its preset index becomes -1).

With the misc switch Layout on, a recall puts back which bank each layer shows on each fader bay. It does not put the bank buttons back: after a bank was moved to another button, a recall left the buttons as they were.

## Store and update

- Insert New shares every state of the current snapshot where the live value equals it, and adds new states only for changed modules. So a new snapshot takes the current snapshot's scope: a channel that is out of scope in the current snapshot stays out in the new one.
- Update Current changes the values that differ, in the snapshot's own states. A shared state that changes gets a new copy for this snapshot. The old one stays in the pool with a lower count, possibly 0. The snapshot keeps its scope.
- Update Group writes the current snapshot's changes into the other snapshots of its snapshot group, but only what Global Scope's auto update reaches (+0x29, +0x4d), and that includes the current snapshot: an EQ change with auto update off for EQ went into neither. With Relative Groups on, dB changes are relative: each snapshot moves by the same amount from its own value, and minus infinity counts as -150 dB. A snapshot's own group and auto update scope (flags 0x02) keeps parameters out.

## For tools

Nothing in this folder writes scope yet. A tool that edits a show with snapshots has to keep these rules:

- An edit to section 211 lasts until the next recall that reaches it under the rule above. To keep it, write it into the snapshots' states too. [`engine-findings.md`](engine-findings.md) says the same for insert routes.
- A rename lasts only if each snapshot's strip trailer and Input/Trim state get the new name too. `ses.rename()` writes section 211 and section 201, not section 210.
- Keep section 211 free of scope: +0x34 = 0, +0x39 = 1, +0x3a = 0.
- To change one snapshot's scope, copy a shared state first and set both reference counts.
- Scope both halves of a stereo bus alike.
- Take a fader out with the parameter flags on `(0c, 21)` and `(0c, 22)`, never with the module flag.

## What we don't know

- The 992-byte block in each snapshot record.
- Misc scope bits 1, 8 to 12 and 14: read from the panel order, not saved one by one.
- What the console does with +0x39 in a pool state. It is 0 there in every show.
- SD consoles: none of this is tested on an SD file.
