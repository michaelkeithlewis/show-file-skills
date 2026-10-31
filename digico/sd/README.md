# DiGiCo SD

Covers SD5, SD5 CS, SD7, SD8, SD9, SD10, SD11 and SD12. File extension: `.ses`.

## Tooling

- From `digico/scripts`, read with [`ses.py`](../scripts/ses.py), `sessionmaker.inspect` and `sessionmaker.validate`. Build with `sessionmaker.build`. Edit with `sessionmaker.edit` and `sessionmaker.commands`. List baselines with `sessionmaker.consoles`.
- Per-model table: [`consoles.py`](../scripts/sessionmaker/consoles.py). Docs: [`sessionmaker.md`](../references/sessionmaker.md), [`baselines.md`](../references/baselines.md) and [`FORMAT.md`](../references/FORMAT.md).
- Open every result in the offline editor for that console and build. Use **Files > Save As**. Load only that save on a console.

## What we know

| Key | Model | Family | Default inputs | Max inputs | Bus budget |
| --- | --- | --- | --- | --- | --- |
| `sd5` | SD5 | SD5 | 108 | 124 | 124 |
| `sd5cs` | SD5 CS | SD5 | 108 | 124 | 58 |
| `sd7` | SD7 | SD7 | 72 | 253 | 124 |
| `sd8` | SD8 | SD8 | 60 | 120 | 50 |
| `sd9` | SD9 | SD9 | 48 | 96 | 50 |
| `sd10` | SD10 | SD8 | 96 | 96 | 66 |
| `sd11` | SD11 / SD11i | SD9 | 32 | 32 | 26 |
| `sd12` | SD12 | SDC | 48 | 72 | 38 |

- The SD8 editors V1455, V1619 and V2242 booted 120-input sessions and re-saved all 120 names. DiGiCo lists 60. A real 65-input SD8 show loads in full.
- SD models have no Mustard and no Spice Rack in the table. The SD7 Theatre and Broadcast extensions use the SD7 file. SD12-96 and SD11i are not the same file as a plain SD12 or SD11: see "Extensions" below. The `consoles.py` note "SD12-96 uses the same file" is wrong.
- SD inputs share one engine pool with the aux, group and matrix buses. The pool runs to 191 on SD9, SD11 and SD12, and to 255 on SD5, SD7, SD8 and SD10.
- Default inputs are fallbacks. The newest baseline's own count wins. Bus budget is mono equivalents (FORMAT.md).
- SD FX: reverbs use DSP 64 to 94, others use 0 to 30, and each session has 16 + 16. Preamp gain is +10 to +60 dB on the SD9 and SD11 Local I/O, D-Rack and D2-Rack. Other sockets take -20 to +60 dB.

### Session Structure limits (measured)

The table above shows what `consoles.py` allows today. This table shows what the console's Session Structure dialog allows, read in the real offline editors on 2026-10-24 at every build V1455 to V2242. No limit changes with the firmware. A stereo input takes 2 paths, and an FX return counts as an input. See [`engine-findings.md`](../references/engine-findings.md).

| Key | Input paths | Bus slots | Rule |
| --- | --- | --- | --- |
| `sd5` | 253 at most (195 at the default) | 124 at 48 kHz | pool |
| `sd5cs` | 132 | 58 | fixed |
| `sd7` | 253 at most (203 at the default) | 124 at 48 kHz | pool |
| `sd8` | 120 | 50 | fixed |
| `sd9` | 96 | 50 | fixed |
| `sd10` | 144 | 66 | fixed |
| `sd11` | 48 | 26 | fixed |
| SD11 with SD11i | 80 | 26 | fixed |
| `sd12` | 72 | 38 | fixed |
| SD12 with SD12-96 | 96 | 50 | fixed |

- SD5 and SD7 pool: paths + matrix outputs + bus slots must be 255 or fewer. Paths never pass 253, because a session has at least the 2 bus slots of the stereo Master.
- SD5 and SD7 at 96 kHz: the bus limit follows the rate key: 60, 92 or 124. On every other SD console 96 kHz changes no limit.
- The `consoles.py` caps for SD5 CS (124), SD10 (96) and SD11 (32) sit below these limits, and the cap for SD5 (124) ignores the pool.
- An SD file over the path limit still loads. The first Restructure deletes the last mono inputs ([`engine-findings.md`](../references/engine-findings.md)).
- The SD11i default session has 40 inputs and 12 matrix inputs. A plain SD11 default has 32 and 8.

### Extensions

- Header `0x25` bit `0x10` means SD12-96 in an SD12 file and SD11i in an SD11 file. Every SD5, SD5 CS, SD7, SD8, SD9 and SD10 default sets the bit, so it means nothing on those files.
- A plain SD12 editor refuses an SD12-96 file. It opens its empty default with no dialog. The test file had 48 inputs, inside the plain limits, so the bit alone caused it (SD12 V2242: the title was gone from the re-save and the bit was clear).
- The SD12-96 editor opens a plain SD12 file with the 96 / 50 limits, and saves it with the bit set. That save no longer opens on a plain SD12.
- A file with the bit clear may be meant for either console. Use the plain limits for it.
- Clear the bit, or refuse, when you write for a console without the extension. A 96 kHz SD12-96 file has no plain SD12 target.
- The extension belongs to the editor. Offline editors enable it in System > Enable Console Extensions.

### Sibling files

- SD8 and SD10 share family code `SD8` but not their bus layout. SD8 buses carry module 07, and the SD10 bus EQ (module 04) has 25 more slots, bands 4 to 7.
- An SD10 editor that loads an SD8 file converts it with no dialog. On one real show it dropped module 07 from 56 bus units, added EQ bands 4 to 7, changed FX unit slot `15/00`, and moved 6 output-socket sources. Proven in the SD10 editors on backdated copies, and in the SD10 V2242 editor on the V2242 source.
- Over 81 SD files, each SD8 and SD10 file matched its own console's bus layout and none matched the sibling's, so the layout tells the two apart.
- SD9 and SD11 lay out buses the same way, and so do SD5 and SD5 CS. The file does not say which console it is for.

### I/O

- SD7 V2242: the editor clears 48V on load on the Local I/O Mic/Lin inputs (socket 0:Mic/Lin 1 and 3 proven), main and alt inputs. Gain stays. Switch 48V on at the console.
- MADI links: a device on a link past the console's links keeps its sockets, but the editor zeroes its device id, which means not connected. Links kept: SD12 0-1, SD8 and SD10 0-1, SD9 and SD11 0-2, SD5 0-2, SD7 0-3.

### Inserts

- Insert A has a fixed point. Insert B is pre-fader, or post-fader with module `0c` param `e1` = 1.0.
- SD9 and SD11 take one insert per channel. The SD9 V2242 editor drops insert A on load (route, on, and the destination's source) when a file gives a channel both inserts. Insert B switched on next to a routed or switched-on insert A does the same. The manual gives the same rule for SD11.
- Post-fader insert B: at most 32 channels (manual), mono only. The SD12 V2242 editor drops a stereo post-fader insert on load. The `0c` tap is proven on V2242 only, and no real session holds one.
- Tap bytes at the destination: `07` for insert A, `05` for insert B pre-fader, `0c` for insert B post-fader, then `<side> <idx> 01`.
- Insert B pre-fader taps `04` instead of `05` on a channel with `(04, 81, 0)` = 1.0, the dynamics-before-EQ switch. The SD12 V2242 and V1619 editors rewrite a tap that does not match the switch on load. Update the tap when the switch changes.

### Contributed notes

Each is from a one-change save or a Session Structure reading. The format side is in [`session-structure.md`](../references/session-structure.md).

- Engine mode (header 0x87): the SD5 offers all four (1, 4, 5, 8). SD12, SD9 and SD5 CS offer 1 and 4 only. On the SD5 the 96 kHz modes leave processing alone and cut spare buses, and 96 kHz with 128 buses gives up I/O port 4.
- SD12: matrix 12 x 8 and 12 control groups are fixed. The SD12 editor refuses a file with 16 control groups. An SD8 refused a session until header 0x93 and 0x96 both said 16.
- SD12 USB holds 48 channels at 48 kHz and 24 at 96 kHz.
- SD12 offers no insert point (`e1`), and its editor shows the dynamics key only on the lower section.
- Macro keys per bank: SD12 five, SD9 eight.
- Snapshot number in SD12 files: 47 bytes from the end of its metadata at V1742, 51 at V2242.

### Fader banks

Bank placement is section 212 ([`FORMAT.md`](../references/FORMAT.md), "Fader bank placement"). The bay map below was read off the V2242 editors' Fader Banks screens on each console's default session. The record is the section 212 record of the bay. Layers x buttons is the grid the screen shows.

| Family | Models | Bays: record, layers x buttons | Bank moves |
| --- | --- | --- | --- |
| `SD5` | SD5, SD5 CS | Left: 2, 3 x 5. Centre: 4, 3 x 4. Right: 3, 3 x 5 | proven at V2242 |
| `SD7` | SD7 | Left: 2, 3 x 6. Master 1: 1, 1 x 4. Master 2: 0, 1 x 4. Right: 3, 3 x 6 | unproven |
| `SD8` | SD8, SD10 | Left: 3, 3 x 4. Centre: 4, 3 x 4. Right: 2, 3 x 4 | unproven |
| `SD9` | SD9, SD11 | Left: 3, 3 x 4. Right: 2, 3 x 4 | unproven |
| `SDC` | SD12, SD12-96 | Left: 3, 3 x 4. Right: 2, 3 x 4 | proven at V2242 and V1619 |

- A bank move is proven when a file with banks moved by bytes loaded in the editor, the Fader Banks screen showed every moved bank, and the re-save kept section 212 byte for byte and added no bank ([`engine-findings.md`](../references/engine-findings.md), "Fader banks"). The runs used the SD12 (V2242 and V1619) and SD5 (V2242) editors.
- The SD5 CS and SD12-96 editors were not part of the runs. The SD5 CS default holds the same section 212 as the SD5's.
- More than two bays: the SD5, SD8 and SD10 have three. The SD7 has four, with two Master columns of one layer between Left and Right.
- Record numbers differ by family. The Left bay is record 3 on the SD8, SD9 and SD12, and record 2 on the SD5 and SD7.
- Colours: every SD default holds colour set B ([`FORMAT.md`](../references/FORMAT.md), "Fader bank placement").
- The scripts in this folder read bays for the `SDC` family only and move no bank.

## What we don't know

- Whether a real console processes input paths past the dialog limit: no console test has been run.
- SD7 Theatre and Broadcast extensions: not tested.
- Snapshot scope and recall ([`scope-and-recall.md`](../references/scope-and-recall.md)): proven on Quantum only, not tested on an SD file.
- The bit test on a plain SD11 with an SD11i file: only SD12 was tested.
- Every SD model and build: same writers and `validate.py`, marked untested. The docs name no generated load on a real SD console.
- `ses.py` parse floor: `digico/README.md` says V1455, FORMAT.md says V1619. SD5 CS, SD7, SD10 and SD11 are not in the tested list.
- Snapshots ([`snapshots.md`](../references/snapshots.md)): proven on Quantum only, not tested on an SD file.
- The docs do not list the 18 console and build pairs where FX units booted and re-saved.
- Names over 8 characters: not written. Structural edits on a session with snapshots: refused.
- SD7 pool: a contributor reading of the dialog gives one pool of 249 with buses to 122. The table above reads 255 for paths + matrix outputs + bus slots. Needs a reading that settles it.
- Thresholds above 0 dBFS: a contributor reading says SD production sessions hold compressor thresholds up to +14.3. The repo says thresholds stop at 0 ([`filters-and-thresholds.md`](../references/filters-and-thresholds.md)). Needs a save that settles it.
- Bank moves on the SD7, SD8, SD9, SD10 and SD11: not run in their editors. The SD5 CS and SD12-96 editors: not run either.
- SD11: the default session fills record 2 only, which the SD9 map calls the Right bay. The SD11 bay map is unverified.
- A console swap inside one family (SD12 V1619 to SD12 V2242, SD5 to SD5 CS, SD12 to SD12-96): the swap keeps every bank, record, layer and button as the source has them. This was byte-checked on default sessions of each family. No such file was booted in an editor.
- Bank colours in the SD editors: seven colours are seen on SD banks ([`FORMAT.md`](../references/FORMAT.md)). The SD5 and SD12 editors drew the set A colours and an orange and a green as grey buttons. The full palette is not known.
- The clear snapshots + Restructure on the SD9 at any build but V2242, on the SD12 at any build but V1619, and on the SD5, SD7, SD8, SD10 and SD11: not captured. The cleared SD12 V1619 file was not loaded. SD12-96 files: not load-proven, because a plain SD12 editor opens its own session for them.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
- 2026-10-30, SD12 V2242, contributed one-change saves on the header, sections, ports, macros, banks and snapshots ported to `references/session-structure.md`.
- 2026-10-31, SD12 V2242 and V1619, SD5 V2242: bank moves loaded in the editors, the Fader Banks screen showed every moved bank, and the re-save kept section 212 byte for byte. The bay map of each family above was read off the V2242 editors' Fader Banks screens. Ported to `references/FORMAT.md` and `references/engine-findings.md`.
- 2026-10-31, SD5 and SD12 V2242 as console swap targets: banks carried from the Quantum 326/338 loaded, showed on the Fader Banks screen and re-saved with section 212 byte for byte. An SD12 with 34 banks, 10 of them on no button, kept all 34. Ported to `references/engine-findings.md`.
- 2026-10-31, SD5 and SD12 default sessions (V1619 and V2242), read from the files: a 99-byte record of section 212 is 84 bytes of positions and 15 bytes after them, seven shown-button bytes (all 1) and eight zero bytes. `references/session-structure.md` counts three flag bytes there, and the layout.py docstring takes the first byte after the seven as the active layer. Both notes stand until a save settles them.
- 2026-10-31, SD5, SD8, SD10 and SD7 default sessions (V1619 and V2242), read from the files: output banks sit on layer 1 of the Centre bay (SD5, SD8, SD10) and of both Master columns (SD7). The note in `references/script-notes.md` (layout.py section) that every default puts output banks on layer 2 holds for the Left and Right bays. That note stands.
- 2026-10-31, SD9 V2242 and SD12 V1619: the editor's own Session Structure > clear snapshots > Restructure was captured on a real SD9 show with a snapshot group, on the same show with 2 setlists written by bytes, and on an SD12 sample with 3 snapshots stored in the editor. A file made by writing only the changes of the clear equals the editor's save, with save-time bytes masked, Global Scope included. A cleared SD9 file loaded in the SD9 V2242 editor: the Snapshots screen was empty and the re-save held no snapshots and no setlists. The SD12 V1619 file was not loaded. Ported to `references/snapshots.md`, `references/scope-and-recall.md` and `references/session-structure.md`.
- 2026-10-31, a real SD9 show saved at V1619 (one snapshot group) and the SD12 V1619 sample above: section 210 read with the layout in `references/snapshots.md` and matched the Snapshots screens of the SD9 V2242 and SD12 V1619 editors (names, numbers, group, current snapshot and, on the SD9 show, the recall time and note). Two setlists written by bytes into an SD9 V2242 file showed in order. The lines above, `references/snapshots.md` and `references/scope-and-recall.md` say SD files are not tested. That no longer holds for the snapshot list, the trailer, section 115 and Global Scope. Those notes stand.
- 2026-10-31, SD9 V2242 and SD12 V1619: section 0 is the session name. The editor shows it as Session on the master screen, as the session title in Session Structure and the Session Notes dialog, and as the Description in the Load and Save Session lists. A 64-character name written into section 0 alone showed in full in the SD12 V1619 editor and the re-save kept it. Ported to `references/FORMAT.md`. The `layout.py` and `inspect.py` docstrings and `set_notes` still call it notes.
