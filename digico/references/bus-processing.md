# DiGiCo bus processing: aux, group and matrix output strips

A bus master carries the same module records as an input channel for what its strip shows. A bus master is an aux, a group, the Master group or a matrix output. So a write to bus processing is a handful of slots. This page gives the keys, what the editor does with a value, the proofs and what stays closed. The site engine below is the web engine at [I Don't Own a PC](https://idontownapc.com).

Each fact says how it was proven. The facts date from 2026-11-01.

- "Editor load": the offline editor opened a file written by bytes. Its strips showed the values where the screen was reached. Its re-save kept every byte written.
- "Exploration file": a file with values written by hand and booted in the editor, to see what the editor keeps.
- "Not proven": no editor run covers it.

Keys are (module, param, band) in hex, as in [`FORMAT.md`](FORMAT.md). A key written `04/02/0` is module 04, param 02, band 0.

## Bus objects

- Section 211 holds a bus as an object: aux `05xx`, group `06xx` and matrix output `10xx`. A stereo bus also has a right side object `07xx`. [`session-structure.md`](session-structure.md), "Strip kinds and their modules", lists the modules of each kind.
- The EQ (`04`), dynamics (`05`), delay (`09`) and insert (`08`) modules use the keys of an input channel. The trim is module `0b`, not `01`.
- A stereo bus keeps the same values in both sides. In 20 stereo buses of console-saved shows, none of these modules differed between the two sides. Write both sides.
- The Master group is a group bus. The Master takes the same writes.

## Keys

| What | Keys | Notes |
| --- | --- | --- |
| EQ in | `04/02/0` | 1.0 in, 0.0 out |
| EQ band | `04/04` shape, `04/05` frequency, `04/06` Q, `04/07` gain, at the band byte | Write no band on flag (`04/03`). See "What the editor does with a value" |
| Comp in, mode | `05/02/0`, `05/3a/0` | Mode 0 single band, 1 multiband, 2 de-esser |
| Comp settings | threshold `05/0e` on bands 0, 1 and 2, ratio `05/10`, attack `05/11` (s), release `05/12` (s), knee `05/0f`, makeup `05/09` | Knee 0 hard, 1 medium, 2 soft. The editor mirrors the threshold into the three bands, so write all three. The other keys are band 0, as on an input |
| Gate in, mode | `05/02/3`, `05/0b/3` | Mode 0 gate, 1 ducker, 2 comp |
| Gate settings | threshold `05/0e/3`, range `05/0a/3`, attack `05/11/3`, hold `05/13/3`, release `05/12/3` (s) | Same keys as an input |
| Delay | on `09/07/0`, time `09/08/0` (s) | 0 ms is off. `09/17` is a separate fine trim in samples. Leave it alone |
| Trim | `0b/01/0` (dB) | Module `0b`, not `01` |
| Insert in | `08/02/0` insert A, `08/02/1` insert B | Switch it only for an insert that already goes somewhere. Its send (`08/fe`) or its return (`08/00`) is not zero. Write no route |

- The comp keys are those of the single band compressor. A multiband compressor, a de-esser, a ducker and a second compressor on Dyn2 use other keys. Their in switch is the same slot. Their settings were not written.
- Nothing else is touched: no band on flag, no template and no stored snapshot copy.

### EQ bands

- UI band n sits at band byte 4 - n for bands 1 to 4 (bytes 3, 2, 1, 0). UI band n sits at band byte 12 - n for bands 5 to 8 (bytes 7, 6, 5, 4).
- A bus holds bytes 7 to 4 only when the file has a frequency slot at band byte 7. A Quantum bus does. An SD12 bus does not, so the SD12 bus has 4 bands. [`session-structure.md`](session-structure.md), "Strip kinds and their modules", lists the bus EQ size of the other SD consoles. Read the size from the file, not from the console.
- [`CHANNEL_MODEL.md`](CHANNEL_MODEL.md), "Other channel types", calls bytes 7 to 4 the pre-insert bands. Bytes 7 to 4 have no bell or shelf switch.
- Shape: 1 bell, 3 low shelf, 4 high shelf. A shelf takes Q 0.85. The editor forces that value on load, so write it with the shape.
- Where a shelf can sit on the Quantum: a low shelf on band 1 or 2, and a high shelf on band 3 or 4.
- Where a shelf can sit on the SD (proven on the SD12): a low shelf on band 1 only, and a high shelf on band 4 only.
- Bands 5 to 8 are bells.

Ranges the writes accept, in display units. The input panel sets these ranges.

- EQ: frequency 20 Hz to 20 kHz, gain -18 to +18 dB, Q 0.1 to 20.
- Comp: threshold -60 to 0 dB, ratio 1 to 50, attack 0.02 to 100 ms, release 1 ms to 10 s, makeup 0 to 40 dB.
- Gate: threshold -60 to 0 dB, range 0 to 90 dB, attack 0.05 to 100 ms, hold 2 ms to 2 s, release 5 ms to 10 s.
- Delay 0 to 1300 ms. Trim -20 to +60 dB.

## What the editor does with a value

Exploration files on the Quantum 225 V2242 and the SD12 V2242:

- Trim: -40 and -25 dB come back as -20. +25, +40 and +60 stay. The editor holds the trim from -20 to +60 dB.
- Delay: 1.5 s and 2 s come back as 1.3 s. The editor holds the delay from 0 to 1300 ms, as on an input.
- Band on flag: a 0 on band byte 3 comes back as 1. The editor runs every band while the EQ is in. Never write a band off. Set the gain to 0 dB to flatten a band.
- Shelf: on the Quantum 225 a shelf on bands 2 and 3 stays. On the SD12 a shelf there comes back as a bell, as on an input.
- Bands 5 to 8 (bytes 7 to 4): the editor rewrites a shelf shape there. The shapes become 2 and 0, the gain becomes 0, and the frequencies move. These bands take gain, frequency and Q only.
- Not clamped on load: EQ gain 25 dB, frequency 5 Hz, Q 0.05 and 30, comp threshold -70 dB, ratio 60, makeup 50 dB, gate threshold -70 dB, range 100 dB and hold 5 s. The ranges above are not a limit that the editor enforces. Keep to the ranges.

## Snapshots

- Each snapshot keeps its own stored states of every bus. The pool states in section 210 hold modules `04`, `05`, `08`, `09` and `0b` of each aux, group and right side.
- A bus edit changes the live settings only. The edit follows the rule for input processing.
- A session with 3 snapshots ran on each of the Quantum 225 V2242, the SD12 V2242 and the SD12 V1619. The editor loaded the edited file and kept the live values. Section 210 stayed as it was. The re-save differed from the original's re-save in save-time stamps only.
- No recall was fired after a bus edit. By the scope rules in [`scope-and-recall.md`](scope-and-recall.md), a recall brings back the stored states for the columns it covers, as for an input. Warn the user to update the snapshots on the console after loading the file.

## Proof

Each run follows one method:

1. Apply the whole set of writes to a session. The set has 50 writes: every change kind on a mono and a stereo aux, a mono group, a stereo group, the Master and a matrix output. Each bus gets a different value. Each in switch goes both ways. The site engine lifts every refusal for the run.
2. Boot the file in the editor of its console and build.
3. Compare the re-save with the file. Three checks must hold:
   - every slot written holds the bytes written, for each change kind and bus kind;
   - no slot that was not written differs from the re-save of the original file, booted the same way;
   - the file made differs from the original in the written slots only.
4. Read the values on the editor's aux strips (Channel Surface, layer 2) where the screen is reached.

Bytes outside section 211 that differ between two re-saves are save-time stamps (4-byte runs) and a few heap pointers. The stamps and pointers differ between two boots of the same file.

| Console and build | File | Result |
| --- | --- | --- |
| Quantum 225 V2242 | sample session | 63 of 63 pairs of change kind and bus kind. 658 slots. 0 stray slots |
| Quantum 225 V1619 | editor default | 63 of 63. 658 slots. 0 stray |
| SD12 V2242 | editor default | 60 of 60, with no bands 5 to 8. 490 slots. 0 stray |
| SD12 V1619 | sample session | 60 of 60. 490 slots. 0 stray |
| Insert in, Quantum 225 V1619 | a real show with 3 snapshots | 23 insert in switches (18 on groups, 5 on matrix outputs). Each moved to the other state and was kept. 0 stray |
| Snapshots, Quantum 225 V2242, SD12 V2242 and SD12 V1619 | sessions with 3 snapshots | The full set. Live edits kept. Section 210 unchanged. 0 stray |

The editor's aux strips showed the written values on the Quantum 225 V2242, the SD12 V2242 and the SD12 V1619:

- aux 1: trim 3.0, delay 5.00 ms on, comp threshold -25.0 with gain 1.0, gate threshold -50.0;
- aux 2: trim -20.0;
- aux 7: trim 4.5, delay 20.0 ms on, comp threshold -27.0 with gain 2.0, gate threshold -48.0;
- aux 8: trim 60.0, delay 27.5 ms off.

The Quantum 225 V1619 file and the snapshot and show files are proven by the re-save alone. The layer key did not reach the aux layer in those boots.

## Rules the site engine follows

1. Write a change only for a console and build where an editor loaded such a file. Refuse every other pair with one sentence that names the proven ones.
2. Write both sides of a stereo bus.
3. Never write a band on flag. Refuse a band off with a sentence that says to set the gain to 0 dB.
4. Refuse a shelf on a band where the console cannot hold it. Refuse a shelf on bands 5 to 8.
5. Refuse a value outside the ranges above.
6. Write the comp settings only when Dyn1 is a single band compressor. Write the gate settings only when Dyn2 is a gate.
7. Switch an insert on only when the insert has a send or a return.
8. Change the live settings only. Warn that each snapshot keeps its stored values.

## Not proven, so closed

The site engine refuses each item with one sentence that names the proven consoles.

- Every console and build outside the table: the Quantum 326/338, 5, 7, 852, 112 and the Pulse models, the SD5 to SD11, SD12-96, and the other builds of the Quantum 225 and SD12. No run.
- Insert in on an aux: no real show has a routed aux insert.
- Insert in on any V2242 file: no file holds a routed bus insert, and the routes are not written.
- Bands 5 to 8 on an SD console: the SD12 has none, and no other SD editor was run.

## What we don't know

- What a recall does to bus processing after an edit. No run fired one.
- What a console does with a value that the editor does not clamp.
- Whether the shelf rule of the SD12 holds on the other SD consoles.
- Insert in on the SD12. The only insert in proof is a Quantum 225 show.
