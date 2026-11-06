# DiGiCo session structure: header, sections, objects, strip kinds

Contributed notes on the SD and Quantum session file (`.ses`). They come from production sessions (SD12, SD9, SD5, Quantum 225, Quantum 338), the factory session of every offline editor, and one-change saves (mostly SD12 V2242 and Quantum 5 V2025). They add to [`FORMAT.md`](FORMAT.md) and do not repeat it. Where a fact here meets a fact in `FORMAT.md` or the model READMEs, the one-change save in those files wins, and the disagreement is in the open list at the end.

Each fact says how it was proven:

- "One-change save": one control changed in an editor or on a console, and only the named bytes moved.
- "Editor load": an editor opened or refused a written file.
- "Editor capture": the editor's own Files > Session Structure with one key pressed, then Restructure and Save As. The file is compared with the same editor's plain Restructure of the same file, so a difference belongs to the key.
- "Every session read": the value fits one reading across every session read, but was never moved on its own.
- "Session Structure dialog": read off the editor's Session Structure page.
- "Unconfirmed": a reading that fits, not tested.

Modules are written in hex, as in `FORMAT.md` (module `0c` is the fader, `11` an input socket, `12` an output socket). All integers are little-endian.

## Container

- No encryption, no compression, no checksum: no zlib, gzip or zip stream, and no CRC-32, Adler-32 or byte sum in the header or the tail (every session read). Names and float32 values are in clear.
- A saved change moves only the module times, the records touched, the header counts and the section 201 labels on a restructure, section 210 on a snapshot change, and sections 243 and 212 on a bank change. Section order, record order and untouched sections stay (one-change saves).
- With the framings below, every session read reassembles byte for byte.

## Header

The header is 456 bytes (0x1c8). The section offsets (0x100) and the section ids (0x1a0) are in `FORMAT.md`.

| Offset | Field | How proven |
| --- | --- | --- |
| 0x00 | `DiGiCo`, 5 spaces, model code (4), `.SES v`, format letter, 3 spaces | one-change saves |
| 0x15 | format letter: H, I, J, K, M, O (see Versions) | every session read, one per build |
| 0x19 | `0d` | every session read |
| 0x20 u16 | header length 456; the first section starts here | every session read, editor load |
| 0x22 u16 | software build: 1528, 1619, 1742, 1926, 2025, 2242 seen | one-change saves (re-save at a new build) |
| 0x77 f32 | sample rate, 48000 or 96000 | one-change save |
| 0x7f f32 | oscillator frequency (1000.0 seen) | every session read |
| 0x83 f32 | oscillator level dB (-18, -16, -31 seen) | every session read |
| 0x87 u8 | engine mode (below) | one-change saves |
| 0x95 u8 | multis | every session read |

- The header holds no snapshot count (one-change saves).
- Engine mode at 0x87: 1 = 48 kHz with 128 buses, 4 = 96 kHz with 64, 8 = 96 kHz with 96, 5 = 96 kHz with 128. The SD5 offers all four. SD12, SD9, SD5 CS and Quantum offer 1 and 4 only. Proven in the Session Structure dialog with a save for each mode.
- The 48kHz and 96kHz keys write 0x77 and 0x87 together and also change section 246. See "Sample rate keys" below.
- Early notes read 0x96 as the control group count, because every production session has as many control groups as matrix inputs. An SD7 restructure to 32 matrix inputs moved 0x96 alone, and on eight factory sessions 0x94 is the control groups. This agrees with [`engine-findings.md`](engine-findings.md).
- The u16 at 0x24 reads 0x0008 or 0x1008. Its high byte is header 0x25, whose bit 0x10 is the extension bit in [`engine-findings.md`](engine-findings.md).

## Versions

| Letter | Build | Format facts (each from a session at that build) |
| --- | --- | --- |
| H | V1528 | no `ee` section on SD12; label records 0x58 bytes; no macro release list |
| I | V1619 | input module `13` holds 24 slots |
| J | V1742 | no `ee` section on SD12 |
| K | V1926 | module `13` holds 23 slots; macros gain a release list |
| M | V2025 | no format change isolated |
| O | V2242 | section `73` appears; label records 0x79 bytes (the same record plus 33 zero bytes) |

- The letters are shared by SD and Quantum. L and N were not seen.
- A Quantum 338 session re-saved from V1619 at V1926 kept every object, snapshot and library entry. Only module `13` lost one slot, and sections 248 and 227 changed.

## Sections

Order seen: `00 db f6 fc c9 d2 (73) d3 f3 d4 e4 d9 e8 ea ec ed dd cf f8 f9 fa eb e2 d0 e3 e5 e1 (ee)`. Most sections open with the tag, a zero and a u32 count. `FORMAT.md` names sections by their decimal id (201 = `c9`, 211 = `d3`, 219 = `db`, 243 = `f3`, 212 = `d4`, 246 = `f6`).

| Tag | What | How proven |
| --- | --- | --- |
| `00` | session name: u16 length + text, the editor's Session field | one-change save |
| `c9` (201) | patch-bay page names and the label groups (below) | one-change saves |
| `d2` (210) | snapshots (below, and [`scope-and-recall.md`](scope-and-recall.md)) | one-change saves |
| `d3` (211) | the current mix: every strip, port, FX unit and graphic EQ | one-change saves |
| `d4` (212) | surface sections: banks on the layer buttons (below) | one-change saves |
| `f8` (248) | macros (below) | one-change saves |
| `e5` (229) | Copy Audio presets. A session with none holds 12 bytes here ("Sample rate keys") | editor capture |
| `f6` (246) | the I/O device table: a 4-byte header, then 50 records of 210 bytes ("Ports, sockets and patch", "Sample rate keys") | editor captures, editor loads |
| `f7` (247) | Session Notes text, one u16-length string | one-change save |

- Section 0 holds two u16-length strings. The first is empty in every show read, so the section starts `00 00`. The second is the session name. One-change save: the "session title" box of Session Structure changed only the second string.
- [`FORMAT.md`](FORMAT.md), "Session name", says the editor's place for the Session Notes text is not known. The place is section 247. One-change save: one line typed into Files > Session Notes added the section, between `cf` and `f8`. The captures saved with empty notes have none.

Most of the file size is the library and the snapshots. The current mix is 0.4 to 1.3 MB.

## Objects in section 211

- Object list: `d3 00`, u32 count, objects. Objects run in kind order.
- Object: `d5 00 01 00`, a flag byte, a u32 module count, the modules, a 41-byte trailer. The flag byte is set in section 211 and clear on a snapshot object.
- Trailer: `[u16 39][u8 slot][u8 kind][u8 name length][name, 31 bytes][i32][u8 width]`. Width 1 mono, 2 stereo. The i32 is -1 on all but 35 of 11,982 objects; whether it is the strip colour is open. The trailer slot has gaps, and right legs share one slot range.
- Module tail: 12 bytes, three u32 (a base reference, -1 for a full module, and two words).
- Save time: f64 OLE date; every module of a file carries the same moment, restamped on save.
- Float noise: -8 dB is stored as -7.9999967.

Proven by parsing every byte of the current mix of every session read and reassembling it byte for byte.

## Strip kinds and their modules

Seen in every session read.

| Kind | What | Modules |
| --- | --- | --- |
| 01 | input channels | 01, 09, 07, 08, 04, 05, 0c, 02, 0d, 03, 0e, 13, 0a (+ 1a to 1e on Quantum) |
| 05 | aux buses | 0b, 09, 07, 08, 04, 05, 0c, 0e, 0a |
| 06 | group buses, Master among them | 0b, 09, 07, 08, 04, 05, 0c, 02, 03, 0e, 13, 0a |
| 07 | right legs of stereo auxes and groups | as the bus |
| 08 | monitoring | 18 |
| 09 | aux sets | 21, 0e |
| 0a | control groups | 10, 0a |
| 0b | solo buses | 17, 08, 0c, 0e |
| 0c | talkback input | 01, 09, 07, 08, 04, 05, 0c, 02, 03, 06 |
| 0e | FX units | 15 |
| 0f | matrix inputs | 01, 06 |
| 10 | matrix outputs | 0b, 09, 07, 08, 04, 05, 0c, 0e, 0a |
| 11 | graphic EQ units | 0f |
| 12 | multis | 10 |
| 14 | nodal nodes (Quantum) | 04, 05 |
| 18 | Spice Rack slots (Quantum) | 1f |
| 1b | oscillator, white and pink noise, talk mic | 11 |
| 1c | local inputs | 11 |
| 1d to 2a | input sockets of ports 1 to 14 | 11 |
| 4d | headphones | 12 |
| 4e | local outputs | 12 |
| 4f to 5c | output sockets of ports 1 to 14 | 12 |

- An output group's kind is its input group's kind plus 0x32 (one-change saves).
- Quantum adds the Mustard modules to every input, drops module `07` from the outputs, and adds Spice Rack and nodal objects. Bus and matrix EQ has 8 bands on SD5, SD5 CS, SD7, SD10 and every Quantum, and 4 on SD8, SD9, SD11 and SD12. Inputs have 4 (every session read). The SD10 against SD8 bus EQ is in [`../sd/README.md`](../sd/README.md).

## Numbering and labels (section 201)

Object order is not bus order: the SD12 blank's Aux 1 to 6 sit in slots 16 to 21. The desk number is the label record:

```
cb 00 LL 00 [slot] [kind] [number u16] [name length] [name] ...
```

- `LL` is 0x58 before V2242 and 0x79 from it.
- In 121 real Quantum shows, `LL` is 0x58 at V1742 to V2025 (Quantum 225), 0x78 on the Quantum 852 at V1926, and 0x79 at V2232 and V2242. With 0x79 a record is 125 bytes, and its last byte (+124) is group aux send enabled: 1 on every group but the master, and 0 on the master, the auxes and the right legs (68 shows). A new group takes 1, as `buses.py` writes it.
- Layout: a prefix (a u32 not decoded, the CRLF patch-bay page names, folder names, the card groups' table, a u32 group count), then per kind a 112-byte header `ca 00 6c 00 [kind] [name length] [name]` (`d1` in place of `ca` for the Quantum Nodal Processing group), a u32 count, and the label records. At V2242 a record is 125 bytes: slot +4, kind +5, number +6, name length +8, name +9, and the slot again at +84 on ports, matrix inputs, control groups, graphic EQs, multis and nodes.
- Console sends and receives are port groups with user names. Talkback output names are label records of kind 09.
- Reordering buses in Session Structure renumbers the label records and the default names only.

Proven by one-change saves.

## Restructure rules

Proven by restructures in the editors, saved and compared:

- An added strip copies the last of its kind into the lowest free slot. A removal takes the last input or the highest-numbered bus. Nothing else is renumbered. The header counts and the labels follow.
- Each label run carries a u32 count. A count off by one fails the load with "Invalid Group object: 202 read instead of 203" (editor load).
- A kind's numbers run 1 to its count. A gap hangs or fails the load (editor load).
- A stereo aux or group has a right leg (kind 07, "Aux 1 R") with its own object and label, linked to its bus both ways by module `05` param `14` (`00 00 slot kind`). An orphaned leg is an access violation on load. The solo bus points at Master the same way.
- An added strip's module headers carry its own name.
- Making an input stereo sets: width 2 in the trailer and the label (byte 41), (08, e8) on both bands and (0e, e8) to 2, (05, 14) on, and the label's processing number (byte 84) to the next free one.
- The LR main is a stereo group named "Master" (any case).
- Global Scope (2026-10-31): a Restructure alone keeps every section's Global Scope. With clear snapshots switched on, the Restructure also empties sections 210 and 115 and puts every section's Global Scope back to its type default ([`snapshots.md`](snapshots.md), "Clear all snapshots"; [`scope-and-recall.md`](scope-and-recall.md), "Global Scope defaults and the clear"). The session was saved after a Restructure alone and after clear snapshots plus a Restructure, in five editors, and the two saves were compared.
- Snapshots (2026-10-31): a Restructure with clear snapshots off keeps every snapshot and rebuilds section 210. Removed strips lose their copies, a new strip gets one shared set of pool states, and a new aux or group adds its band to the runs of every kept state. The rules and proofs are in [`snapshots.md`](snapshots.md), "Restructure with snapshots". Quantum 225 at V2242, SD12 at V1619 and V2242.
- New auxes and groups (2026-10-31): the editor does not copy the last bus of the kind. The editor writes the default strip of the console, and the default value in the new band of every strip that has aux sends or group assigns. Copying the last bus and writing the default strip give the same bytes on a session whose buses still hold the defaults. They differ when the buses were edited. Matched on the SD12 at V1619 and V2242 and the Quantum 225 at V2242: [`engine-findings.md`](engine-findings.md), "New buses start from the default strip".
- A bus of a width the session has none of (2026-11-02). In every session read, a mono bus, a stereo bus's left side, its right leg and the master hold one layout per kind: the same modules, params, aux send and group assign runs, and the same section 201 record. Only these differ: (08, e8) on both bands and (0e, e8), which are 2 on a stereo left side and 1 on a mono bus and on every right leg; the Mustard compressor's stereo link (1d, 3f); the link to the other side (05, 14); and in the section 201 record the width (+41), the BussID (+54) and group aux send enabled (+124). So a new bus can be made from one of the other width of its kind, or from the master. `buses.py` does this when the default session has no strip of that kind and width (`_fallback_obj`, `_convert`).
  - Proof, saved: nine new buses made from the other width or from the master came out as DiGiCo's own save of the same change, save dates and memory pointers aside. Six on sessions without snapshots: a mono aux from a stereo one, a mono group from a stereo one and from the master, a stereo aux from a mono one, a stereo group from a mono one and from the master. Three with snapshots: a mono aux from a stereo one, a stereo group from a mono one and from the master. Quantum 112 at V2242.
  - Proof, loaded: written this way on real shows with no bus of that width, these loaded: a stereo aux on a show with mono auxes only and a mono and a stereo group on a show whose only group is the master (Quantum 326/338 editor at V2242), and a mono aux on a show with stereo auxes only (Quantum 852 editor). The two Quantum 326/338 re-saves kept the new buses as written.
- Where a new bus goes on a session whose buses are not mono first (2026-11-01). One-change saves in the Quantum 326/338 editor at V2242, on a real show: Session Structure with one more mono group, one more stereo group or one more mono aux, then Restructure. Each new bus went to the end of its kind, after the master, and its run went last in every strip. A new right leg went last among the right legs. Nothing was renumbered. `buses._plan` puts a new mono bus after the last mono one when the buses are not mono first. The real Quantum 225 show under "Not covered" in [`snapshots.md`](snapshots.md) had its new mono aux put second by the V1619 editor, so the place may depend on the build or on the show.
- A session's first stereo aux (2026-11-02, the same editor and show): the aux went to the end of the auxes, and its right leg went first among the right legs, before the groups' right legs.
- A session's first aux (2026-11-02). A session with no aux has no aux send module (`02`) on any strip, so there is no run to add a band to. `buses.restructure` refuses such a session. The editor's first aux, a mono one, writes:
  - the aux: the default session's first mono aux strip, as index 0 and named "Aux 1", in section 211 right after the inputs;
  - on every strip whose kind sends to auxes in the default session (inputs, groups and their right legs, the talkback input): a module `02` right after the fader module `0c`. It is a copy of that strip's fader module record with the type `02`, holding one run of the default session's aux send params for band 0: the level at -150 (on the talkback input 0), `(02, 0c)` at -150, `(02, 10)` at 60, every other param 0;
  - on the talkback outputs, one more slot `(21, ea, 0)` = 0;
  - header 0x36, the mono aux count, one up;
  - a section 201 record right after the aux group record, whose count goes from 0 to 1. It is the default session's first mono aux record with slot 0, number 1, the name, and the EngineChannel right after the groups and their right legs. The solo buses move up by one.
  - Proof, saved: the Quantum 112's Minimum session (no aux, the master its only group) with one mono aux added and saved, Quantum 112 at V2242. A file written by these rules equals that save, save dates and memory pointers aside.
  - Proof, loaded: a session from Minimum with two mono auxes and a stereo one, the first written this way and the other two as above, loaded in the Quantum 112 editor at V2242. Input 1's sends to all three auxes metered.
  - Not tested on a session with snapshots: no sample has snapshots and no aux.

## Sample rate keys

Files > Session Structure has a 48kHz key and a 96kHz key. The key takes effect on Restructure.

Editor captures, 2026-11-01. In each capture only a rate key was pressed, then Restructure and Save As. The file was compared with the same editor's plain Restructure of the same file. The test sessions have generic channel names.

| Console, build | Snapshots | Hops captured | What changed |
| --- | --- | --- | --- |
| Quantum 225 V2242 | none | up, down, up, down | Header 0x77 and 0x87, and 2 bytes of section 246. Nothing else |
| Quantum 225 V2242 | 2, with 2 FX units | up, down, up | The same. Section 210 and the FX units stay as they were |
| SD12 V2242 | none | up, down | Header, 3 records of section 246, and 48 socket objects (sections 201 and 211). Down brings the sockets back |
| SD12 V2242 | 3 | up | The same, and section 210 loses the 48 sockets from the pool and the copies |
| SD12 V1619 | none | up | As the SD12 V2242 |

Up is 48 to 96 kHz. Down is 96 to 48 kHz.

Byte rules:

1. Header 0x77 is the float32 SampleFrequency: 48000.0 or 96000.0. Only the float's third byte (0x79) differs: 0x3b at 48 kHz and 0xbb at 96 kHz.
2. Header 0x87 is the BussingMode byte: 1 at 48 kHz and 4 at 96 kHz. Seen on the Quantum 225 V2242 and on the SD12 at V2242 and V1619.
3. Section 246 is the I/O device table. The editor re-reads what each device can do at the new rate.
4. Quantum 225 V2242: byte +4 of two records changes. Record 1 has device type 0x0b (MQ-Rack). Record 2 has device type 0x19 (Std MADI). Both sit on MADI links.
   - Up: 0x40 to 0x20 on record 1, and 0x40 to 0xa0 on record 2.
   - Down: 0x20 to 0x00 on record 1, and 0xa0 to 0x80 on record 2.
   - Up again: 0x00 to 0x20, and 0x80 to 0xa0. Down again: the same as the first down.
   - Bit 0x40 goes. Bit 0x20 comes at 96 kHz and goes at 48 kHz. Record 2 also gets bit 0x80 and keeps it.
5. The +4 byte is a bit field with a history. The rate alone does not set it. Console-saved shows hold 0, 1, 3, 0x10, 0x40, 0x80, 0xa0 and 0xa1 there at both rates.
6. SD12 at 96 kHz, V2242 and V1619:
   - Record 2 (device type 0x21, MADI 64, on the second MADI port) goes from id 2, link class 2, link index 1 to 0, 0, 0. The port is unlinked.
   - Record 3 (the USB device, type 0x27) loses the card codes of slots 3 to 5 and 11 to 13.
   - The USB device loses its sockets 25 to 48, input and output. Section 211 loses 24 objects of type 0x1f and 24 of type 0x51. Section 201 goes from 48 to 24 records in each of the two socket groups.
   - Record 1 (the D2 rack) byte +4 goes from 0x00 to 0x20.
7. SD12 at 48 kHz: the 48 sockets come back identical, and record 3 is restored. Record 2 stays unlinked. Record 1 byte +4 goes from 0x20 to 0x00.
8. SD12 with snapshots: section 210 loses the pool states and the snapshot copies of the 48 sockets. The pool went from 1218 to 1170 states on the session with 3 snapshots.
9. The SD5 and SD7 bus limit follows the rate key, and the SD7 has four keys ([`../sd/README.md`](../sd/README.md)). The bytes of those keys were not captured.

Copy Audio:

- Section 229 holds the Copy Audio presets. A session with none holds 12 bytes there.
- When presets exist and the rate changes between 48 kHz and 96 kHz, Restructure asks "Changing Sample Rate will clear all Copied Audio. Continue?" (Yes, No). Restructure asks no other question, except for DEFAULT ALL.
- After Yes, the saved section 229 equals the original byte for byte. The presets stay in the file.
- Editor capture on a real Quantum 225 V1619 show whose section 229 held 5958 bytes.

FX units do not change the bytes of the keys and do not ask anything. The Quantum 225 base had two.

Rules the site engine follows. The site engine is the web engine at [I Don't Own a PC](https://idontownapc.com):

- Write header 0x77, header 0x87 and the section 246 records in one change. Change nothing else.
- Run only for a console, build, direction and snapshot state that an editor capture covers and a written file has proven. Today that is the Quantum 225 V2242, both directions, with and without snapshots.
- Keep the exact old and new record for each console, build and direction. Refuse a session that has a section 246 record outside that table.
- Refuse a session with Copy Audio presets (a section 229 longer than 12 bytes).
- Accept 48000 or 96000 exactly, on a session now at one of them. Refuse everything else.
- Refuse the SD12 until the socket removal is written and loaded. Refuse the SD5 and SD7.
- A refusal leaves the whole Restructure as it was, counts included.

Written files, Quantum 225 V2242:

- A file made by the rules above equalled the editor's save for every captured hop. The header and section 246 matched byte for byte. Save times were masked.
- The editor opened each written file, showed the new rate on the master screen and re-saved the file with that rate.
- One file combined 96 kHz, 2 added inputs and 1 added aux on the session with 2 snapshots and 2 FX units. The re-save equalled the file.
- Where a re-save differed, the same editor made the same change when it re-saved the control file with no rate key. The changes were a few objects of section 211, the Mustard path number and one byte of section 210.

Not proven:

- The SD12 rate change. The editor's change is captured only. Nothing writes it, and no file with it was loaded.
- The SD12 down hop at V1619, and with snapshots at V2242: not captured.
- The keys on the Quantum 225 at V1619, the Quantum 225 Pulse and every other console and build: not captured there.
- A device record in a state that no capture covers. The +4 byte has a history.
- What the Yes in the Copy Audio prompt does while a console runs. The file keeps section 229.

## Ports, sockets and patch

- Local I/O is port 0. The sockets of port N are kind 1c + N (module `11`) and 4e + N (module `12`), named "N:Mic n" (one-change saves). Port N is its place in the list: "7:Mic" is port 7, not an Optocore ID.
- Section 246 device records: the record layout is in `FORMAT.md`. Seen at record +64: two bytes (flag, order), the device type, the connection. From +72 a card slot every 6 bytes, the card type at +2. An unused record is 32 bytes of `ff`, then zeros.
- More device types than `FORMAT.md` lists, each from a session that holds the device: `19` MADI, `21` MADI 64, `0f` Dante, `33` Dante 64, `27` USB, `1c` Waves, `08` and `09` OrangeBox 1 and 2, `1a` Con, `1d` Con Send, `1e` Con Receive.
- Connections: `00` none, `01` to `07` MADI and DMI ports, `2a` to `2c` Optocore 1.11 to 1.13. `8a` to `8c` are the same with the top bit set; that the bit means a locked loop is unconfirmed.
- Card types: `16` mic, `15` line in, `01` DAC, `19` and `21` MADI, `0f` and `33` Dante, `1a` and `1b` Con, `1c` Waves, `27` USB. `07` and `03` as AES is unconfirmed.
- A grown port (SD12 USB from 24 to 48) adds sockets as numbered copies of the last one ("3:USB 25") in the mix and the label group, plus the section 246 entries per eight channels (offsets 74 and 122). Every session read. SD12 USB holds 48 at 48 kHz and 24 at 96 kHz.
- Input module `01`: (ff, 0) means the name follows the source. Main, alt and alt-in-use are in `FORMAT.md`. A stereo input's right side is the next socket of the same group, whether the left one is odd or even (one-change saves).
- Output socket module `12`: (e2, 0) port to port and (ff, 0) on (every session read). A source with a tap byte is an insert send: `05` insert B, `07` to `09` insert A, `00` the strip's own output (one-change saves).
- Direct out, module `0e`: `fe` port or FX unit, `3d` on, `3e` pre (1.0) or post (0), `e8` width (one-change saves). `3c` as the level is unconfirmed. Direct outs and inserts are stored on both sides, the strip and the port. Factory sessions can come patched.

## Head amps (module 11, on the socket)

- (11, 86): analogue gain in 0.5 dB steps (one-change saves; -18 to +48.5 seen). (11, 83) 48V only on analogue sockets. (11, 89) the -20 dB pad of an SD-Rack; Local mic inputs have none (one-change saves).
- (11, fe): a back-reference to an output port (every session read).
- DiGiCo's published figure: analogue modules ship at 0 dBFS = +22 dBu, with jumpers for +24, +20, +18 and +15. Not save-proven.

## Channel processing

| Key | Meaning | How proven |
| --- | --- | --- |
| (01, 01) | digital trim dB (-20 to +25.3 seen) | every session read |
| (01, 02) | polarity by leg: 1 L, 2 R, 3 both | every session read |
| (01, 0f) | stereo width: 0 stereo, -1 mono, above 0 wide (-35 % = -0.349) | one-change save |
| (01, 12), (01, 13) | DiGiTube drive (1.0 default), on | one-change save on a Quantum 5 |
| (01, 14) | Gain Tracking | one-change save |
| (09, 08) | delay time in seconds (12.5 ms = 0.0125) | one-change save |
| (0b, 01) | bus input trim dB | every session read |
| (0b, 12), (0b, 13) | bus DiGiTube drive, on | every session read |

- An early survey read (01, 12) and (01, 13) as the delay. A Quantum 5 save showed them as DiGiTube; the delay is module `09`.
- Filters (module `07`): band 1 HPF, band 0 LPF, `03` on, `05` frequency. Defaults are stored 16 Hz and 25 kHz, which the strip shows as 20 Hz and 20 kHz ([`filters-and-thresholds.md`](filters-and-thresholds.md)). No slope is stored (one-change saves).
- EQ (module `04`): band 0 is the top band. (04, 7c) classic mode (one-change save). Inputs offer shelves only on the outer bands. 8-band bus EQs in sessions run two high-pass and two low-pass bands ahead of four parametric bands; type 0 low-pass and 2 high-pass is unconfirmed.
- Dynamics (module `05`): buses, matrices and solos carry the same module. (05, 3b) auto gain (one-change save). Key filters (05, 05, 3) HPF and (05, 05, 2) LPF have no switch and sit flat at 20 Hz and 20 kHz (every session read). The SD12 editor shows the key only on the lower section.
- Inserts (module `08`): `e8` width. `e1` is 4 on every insert A and 2 on every insert B in the sessions read; the SD12 offers no insert point.

## Graphic EQs, Spice Rack, nodal

- Graphic EQ units (kind 11, module `0f`): `07` the 32 band gains, low first, 15 Hz to 20 kHz; `02` in; `00` a reference back to the bus (`07 00 01 05` for aux slot 1); `05` gang. A unit sits on a bus through the bus's insert (08, 00) and (08, fe). A stereo bus takes two ganged units, one on the bus's insert A and one on its right leg's, each pointing back at its own leg, `05` = 1.0 on both (one-change saves).
- Spice Rack (kind 18, module `1f`): `3f` stereo (every session read).
- Nodal nodes (Quantum), one-change saves: one kind 14 object per node with its own EQ (`04`) and dynamics (`05`), named like "Ch 5 > Aux 4"; a label in the `d1` group; and an entry in the table that ends section 211: two zero bytes, u16 length (4 per node), then per node the send module (02), its band (the aux slot), the source slot and kind. "Ch 5 > Aux 4" is `02 03 04 01`. An idle node is all zero.

## Buses, matrices, control groups, multis

- A stereo bus's right leg holds its own copy of the bus's processing (every session read).
- Matrix inputs (kind 0f) feed the matrices. (01, 00) is the source: an input, a bus or right leg, a solo, a port. Module `06` on the matrix input, one band per matrix output: `24` level, `25` on. A stereo source takes two matrix inputs (every session read).
- Matrix outputs are mono: no session holds a stereo one and Session Structure offers none. A stereo matrix is two outputs side by side.
- Control groups (kind 0a, module `10`: `21` master level, `22` master mute). Membership is (0c, 04): band 0 bit n = control group n + 1, band 1 the next 32 (one-change saves).
- There is no mute group table. A control group's "all mute" is its master mute, and a strip's "CG mute" stores nothing (one-change saves).
- Multis (kind 12, module `10`) have a label in a "Multis" group after Talkback Outputs (absent from blanks) and are counted at header 0x95. Each member's (0c, e7) = `[multi slot, 12, place, 0]` (every session read).
- (0c, 0b) solo assign: 0 Solo 1, 1 Solo 2, 2 both (one-change save). (0d, 23) pan as a float: 0.2149 shows as 21.

## Solos, talkback, FX units

- Two solo buses (kind 0b), renameable. Module `17` (one-change saves): `04` AFL (0 PFL), `05` single (0 multi), `02` width, `07` and `08` delay on and seconds shared by both solos, `3c` trim, `00` a bus the solo plays. Level is (0c, 21); direct out is module `0e`. Mono or stereo moves the trailer width, (17, 02), (08, e8) and (0e, e8) together. Solo 1's legs are the monitor outputs on the output patch.
- Talkback input (kind 0c, one per session, "TB In"): trim, filters, EQ, dynamics, fader, sends (modules `02`, `03`, `06`), its source a socket. In the sessions read its sends are off with levels set, and talk keys are macros that switch them.
- Adding an FX unit in the editor puts a label in the run after the "FX" category record (`ca 00 6c 00 0e`): count up one, slot +4, number +6, `0x40 + 2 x slot` at +84. No header count changes (one-change save).

## Snapshots (section 210)

The scope flags, the safes and what a recall changes are in [`scope-and-recall.md`](scope-and-recall.md). The frame, from one-change saves:

```
d2 00 d2 00
u32 pool count, pool modules (framed as in section 211)
u32 0
u32 scope-set count, each u16 length + bytes ("All" seen)
u32 snapshot count, each:
    d3 00, u32 object count, every mix object in order:
        d5 00 01 00 (flag byte clear), u32 module count,
        that many u32 pool indices, 41-byte trailer
    metadata: u16 length + name, f64 time, u16 992 + 992 bytes,
        20 bytes, a copy of section 212 from its +2, a short run (82 to 111 bytes)
tail: u16 L, L bytes, 556 bytes
```

- Each snapshot is whole. No pool module points at a base state.
- A pool module serves one strip. Two strips sharing one, or a snapshot object with its flag byte set, faults the editor with an access violation (editor load).
- A snapshot stores each module less a fixed set of params per strip kind and module type, the safes among them.
- Snapshot number: a u32 34 bytes before the font record (`ff ff ff 00 01 09 00`, "Arial"), in hundredths (1750 = 17.50). In SD12 files it sat 47 bytes from the end of its metadata at V1742 and 51 at V2242. In a Quantum 338 session it sat 71 bytes from the end at V1619 and 75 at V1926.
- The snapshot options, the snapshot groups, the setlists (section `73`, 115), the tail and how to write a snapshot are in [`snapshots.md`](snapshots.md).

## Banks and surface sections (sections 243 and 212)

The bank record is in `FORMAT.md`. Added from one-change saves:

- Section 243 opens `f3 00`, u16 bank count, u16 0. A bank's fader count is (length - 85) / 23, 12 on an SD12.
- Bank +0x1a: the Layout page place, u32 x and u32 y (`ffffffff` = not on the page). Early notes read these 8 bytes as fixed flags.
- Fader kinds also include 12 multi. A bank's name does not bind its content.
- After the strips, 50 bytes hold the category (u8 length, "Input Channels").
- Section 212: two bytes, then one 99-byte record per surface section: seven layers of six bank buttons (u16 bank index, `ffff` none), then three flag bytes. The editor renumbers it when it inserts a bank. The page shows three layers of four buttons (SD12, Quantum 338) or five (SD5). On the SD12 blank, record 3 is the left banks and record 2 the right. A removed strip's fader becomes `00 00`.
- Section 212 in full (the bay of each record per console, the bytes after the positions, what the editors do on load, bank colours): [`FORMAT.md`](FORMAT.md), "Fader bank placement".

## Macros (section 248)

Proven by one-change saves:

```
f8 00, u16 count, 00 00, macros, 02 00 00 00
macro:   u16 id, u8 name length + name (to +34), +34 trigger kind, +35 key,
         +36 to +38 colour, u32 action count at +40, actions from +44;
         from V1926 a second list: u32 count + 14-byte items
action:  u16 length 20, u16 type, param, module, band, from +7, kind +8,
         to +9 (desk numbers), flags, f32 value +14
item:    u16 length 14, param, module, band, slot +5, kind +6,
         f32 value +7, condition +11
```

- Type is a strip kind (01, 05, 06, 0a, 10, 0e, 09) or a command (C9 save session, 2EE tap tempo, 708 update snapshot, FF transport).
- Common settings as (param, module): (22, 0c) mute, (1f, 0c) talk, (21, 0c) fader, (02, 08) insert in, (0e, 01) main or alt, (fe, 0e) output routing, (ea, 21) talk to aux. Values: 1.0 on, 0.0 off, -1.0 toggle.
- Trigger kind: 00 none, 01 and 02 GPI on and off, 03 and 04 macro key on and off, 05 F key, 07 snapshot previous and next, 08 audio master, 09 OSC, 14 and 3c advanced, 51 snapshot recall, 80 to 8f MIDI program change.
- Keys per bank: SD12 five, SD9 eight, Quantum 338 ten. Meter values are 255 + 2 x dB.

## Editor load rules

Proven by editor loads:

- Each offline editor lists only its own header code. A session with that code loads when its header counts fit the console. Otherwise the editor says "<file> cannot be used on this console". An SD8 refused a session until 0x93 and 0x96 both said 16. An SD12 refuses 16 control groups.
- The editor rejects: another model's code; counts past the console; a label run count off by one; a gap in a kind's numbers; a reference to a missing strip; a snapshot object with its flag set; a pool module shared by two strips.
- On save the editor restamps every module time, writes its own section 219, renumbers section 212 on a bank insert and the section 201 labels on a restructure (never module records), and resets the Mustard controls on a type change.

## What we don't know

Readings that disagree with a one-change save in this repo. The repo's fact stands until a save settles each one.

- Section 246 device records: a contributor reading says a 148-byte head comes first, record N-1 is port N, type `04` is the SD MiniRack class and `0b` the Quantum 112 rack. `FORMAT.md` says `f6 00 | u16 10500` and then the records, record k owns sockets 1c + k (so record 0 is Local I/O), `04` is the D-Rack and `0b` the MQ-Rack. Needs a save that settles it: add one known rack to a port and compare. The rack runs of 2026-11-01 wrote racks with the `FORMAT.md` layout (record k is port k, and k owns the socket groups `1c + k` and `4e + k`), and the editors kept every record and socket group ([`io-patch.md`](io-patch.md)). Those runs did not use device type `04`. Settled by one-change saves on a Quantum 112 at V2242 (2026-10-26), for the `FORMAT.md` layout: a D-Rack added at the console on port 4 wrote record 4 of section 246, counted after the 4-byte head (`f6 00`, u16 10500), with `04` at record +0 and its cards from +8 (four Mic inputs `16`, one Line output `01`), and the port's sockets appeared as strip types `20` and `52` (`1c + 4`, `4e + 4`). Changing that rack's type to MQ-Rack at the console wrote `0b` into the same byte and rewrote its cards in place. Record 0 is the Local I/O (type `00`). So `04` is the D-Rack and `0b` the MQ-Rack there, and no 148-byte head comes first.
- Thresholds above 0 dBFS: a contributor reading says production sessions hold compressor thresholds up to +14.3. The repo says DiGiCo thresholds stop at 0 ([`filters-and-thresholds.md`](filters-and-thresholds.md)), and the SD12 editor's knob stops at 0.0. Needs a save that settles it: load such a session in its own editor and read the knob.
- Multiband bands: a contributor reading puts the mid and the high band on dynamics bands 1 and 2. `FORMAT.md` says the UI low, mid and high bands are band bytes 0, 2 and 1 (console-confirmed). Needs a save that moves only the high band.
- Model markers: a contributor reading says the header code plus counts within the limits are enough to load, with no hidden marker. The repo found that header 0x25 bit 0x10 alone made a plain SD12 refuse an SD12-96 file inside the plain counts, and that SD8 and SD10 files differ by their bus layout ([`../sd/README.md`](../sd/README.md)). The repo's findings stand.
- SD7 pool: a contributor reading of the Session Structure dialog gives one pool of 249. The repo reads paths + matrix outputs + bus slots at 255 or fewer ([`../sd/README.md`](../sd/README.md)). Needs a reading that settles it.
- Bank faders: a contributor reading puts a type byte in each fader entry (04 input, 02 bus, 00 empty). `FORMAT.md` puts the strip view (0 SD, 2 Mustard) in 12 bytes at the end of the bank. These may be different bytes. Needs a save that changes one fader.
- Snapshot groups: a contributor reading takes the records after the pool's `u32 0` as scope sets ("All" seen). [`snapshots.md`](snapshots.md) has them as the snapshot groups: adding a group in the snapshot list added one 338-byte record there, and the snapshot's group byte points into the list (one-change save). In 121 Quantum shows, 586 snapshots hold a group byte, and none points past the list.
- Module tail in section 210: a contributor reading takes the first word as a base reference, -1 for a full module. In a pool state it is the index of the state it was copied from, and the state is whole either way: 450,354 of the 840,036 states in 46 Quantum shows hold one, each pointing at a state of the same module type, and none holds fewer params than a state without one ([`snapshots.md`](snapshots.md)).

Not decoded yet:

- Header 0x24 apart from bit 0x10 of 0x25, 0x58 to 0x5f, 0x65 (-18.0 on every file), 0x7b (25.0 on every file).
- Sections `fc`, `e4`, `d9`, `e8` to `ed`, `dd`, `cf`, `e2`, `d0`, `e3`, `e5`, `f9` (32 entries "Set 1" to "Set 32"), `fa` (48 entries of 19 bytes: name, index, A/B/C), `eb` (a CRLF list of 120 short labels), `e1` (UI items "ExplicitTop", perhaps layout) and `ee` (32 "Rack n" entries with the UTF-16 text "com/remote/HighlightSnapshot", perhaps remote). The u32 at the head of section 201.
- Strip colour: the trailer i32 is a candidate.
- Aux send (02, 10), 0 or 60. Module `01` params 0a, 0b, 11, 1b, 1e. Module `0c` params 0c, 0f, 05, df, 1e. (0d, 07). Module `13`. Socket params 80, 81, 84, 8b, c8, c9, ff. (0b, 0e) as bus polarity.
- Dynamics (05, 03) on bands 0 to 2: 1 on every band in every session read, perhaps a band's in.
- Aux sets (kind 09, module `21`) and monitoring (kind 08, module `18`).
- FX unit per-type params beyond `FORMAT.md`. Spice Rack insertion on a strip.
- A stereo input as a matrix source.
- The leading `07` of the graphic EQ back-reference; (0f, 05) values 0, 1, 3 and (0f, 3c).
- Which 8-band bus EQ band takes which type.
- Optocore loop settings; Copy Audio limits.
- Macros: Astral, OSC OFF, the send level scale, other Quantum key banks.
