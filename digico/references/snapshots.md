# DiGiCo snapshots

Section 210 (`d2 00`) holds the snapshots: a pool of stored module states, the snapshot groups, the snapshot records and a trailer. Section 115 (`73 00`) holds the setlists. This file gives their layout and the rules for adding, updating and deleting a snapshot by bytes. A snapshot's scope and what a recall changes are in [`scope-and-recall.md`](scope-and-recall.md). [`session-structure.md`](session-structure.md) has the frame of every section; this file adds what the snapshot fields mean and how to write them.

Proven on a Quantum 112 at V2242. Each fact comes from a one-change save (one edit on the console, Save As, then a byte compare with the file before) or from a file written by bytes that loaded and worked on the console. File facts were checked on 121 shows saved by Quantum 112, 225, 326, 338 and 852 consoles and offline software, V1742 to V2242. 46 of them hold snapshots, 1476 in all. SD files are not tested.

Keys are (module, param, band) in hex, as in [`FORMAT.md`](FORMAT.md).

## Section 210

```
d2 00 d2 00
u32 state count, then that many module records       the pool; a state's index is its position
u32 0
u32 group count, then that many 338-byte group records
u32 snapshot count, then that many snapshot records   in number order
trailer, 794 or 795 bytes
```

- A pool state is a module record, as in section 211. The 10 bytes after its slot count hold the scope flags, the crossfade time and the reference count (table in `scope-and-recall.md`). In a state, +0x39 is 0 and +0x3a counts the snapshot strips that point at it. The count is exact in all 46 shows.
- The record's last 12 bytes, `ff x8 00 x4` in section 211, are two i32 and a u32 0 in a state: the pool index the state was copied from, and the snapshot that made the copy, each -1 for none. They are history only. In 94,636 of the 840,036 states in the 46 shows, the snapshot named there no longer uses the state.
- Snapshots share states. A snapshot that stores the same values as another points at the same state. A state serves one strip: no state in the 46 shows is used by two strips.
- Console files keep states that no snapshot uses, with count 0: 7847 in the 46 shows. Update Current leaves them behind ("Store and update" in `scope-and-recall.md`).

## The snapshot record

```
d3 00 | u32 strip count
  each strip: d5 00 | 01 00 | u8 0 | u32 module count | that many u32 pool indexes | 27 00 | index | type | name[32] | 5 bytes
u16 length + name
TDateTime                    when it was stored
u16 0x3e0 + 992 bytes        not the scope (scope-and-recall.md); what it holds is open
options                      below
u16 length + note text       CRLF line ends
u16 length + node bytes      4 bytes per node strip
```

- Section 211 is a record of the same layout. There the byte after `d5 00 01 00` is 1 and the modules are inline, the name is empty, and the options have number 0 and id 0.
- A snapshot and section 211 can hold different strips. I/O rack slots, FX units, talkback outputs and the Quantum 852 video link are in one and not in the other in 38 of the 46 shows. This fits racks and units added or removed after a snapshot was stored. The strips a snapshot shares with section 211 are in the same order in all 1476 snapshots. Match strips by (index, type), never by position.
- The same module can hold a different slot list in different snapshots (4 shows). Match slots by (param, band).
- The name can be empty. Insert New stored a snapshot without a name.

### Params a snapshot never keeps

A state leaves out a fixed set of params, which depends only on the module and the strip type. No state in the 46 shows holds one of them, and section 211 holds them.

| Module | Params never kept |
| --- | --- |
| `01` input | `14` (inputs, talkback input); `f0` (matrix inputs) |
| `02` aux sends | `f2` |
| `04` EQ | `81`, `f4`; also `7b` on auxes, groups, matrix outputs and solo |
| `05` dynamics | `f5` |
| `0b` bus trim | `38` |
| `0c` fader | `02`, `0b`, `0c`, `0f`, `11`, `1a`, `1e`, `20`, `df`, `e1`, `e7`, `ef`, and the safes `f0` to `fa` |
| `0f` graphic EQ | `f0` |
| `10` control group | `16`, `19`, `1d`, `df`, `ef`, `f0`; on strip type `12`: `14`, `1a`, `ef` |
| `11` input socket | `80`, `84`, `c8`, `c9`, `fe` |
| `12` output socket | `9c`, `e2` |
| `13` external | `08`, `09` |
| `15` FX unit | `f0` |
| `17` solo | `00`, `02`, `04` to `09`, `0f`, `10`, `11`, `13`, `14`, `3c` |
| `18` monitoring | `17`, `20`, `42`, `45`, `48` to `5c`, `65`, `66`, `6f`, `e9` |
| `1a` Mustard pre-amp | `f1` |
| `1c` Mustard EQ | `f4` |
| `1d` Mustard dynamics | `4b`, `f5` |
| `1f` Spice Rack | `19`, `db`, `f0` |
| `21` talkback trim | `e3`, `ea` |

Every other module keeps every param. Among those left out are the safes, hard mute `(0c, 02)`, link pans `(0c, 0f)`, the EQ and dynamics order `(04, 81)` and the bus EQ view `(04, 7b)`.

`7b` is also left out on strip type `07`, the right legs of stereo auxes and groups (2026-10-31, editor-verified). The editor's own states were read back against the table above. On the Quantum 225 at V2242, the table matched in 116 of 117 combinations of module and strip type. The one miss was `7b` on strip type `07`. With that rule added, the table matched in 117 of 117. On the SD12 at V1619 and V2242, the table matched in 88 of 88.

## Options

The options follow the 992-byte block. Offsets count from the options' first byte as if the MIDI list were empty. When it is not, add its length to every offset from +0x008.

| Offset | Type | Meaning | Proof |
| --- | --- | --- | --- |
| +0x000 | u16 | 2 | files |
| +0x002 | u16 | misc scope, the snapshot's other recall switches ("Misc scope" in `scope-and-recall.md`) | one-change saves |
| +0x004 | u32 + bytes | MIDI list: its length, then the entries (below) | one-change saves |
| +0x008 | u16 8 + 8 bytes | GPO relay states | field name only, not tested |
| +0x012 | u16 0x327 + 807 bytes | layout copy: section 212 after its first 2 bytes, as it was when the snapshot was stored. A recall uses it only with the misc switch Layout | one-change saves |
| +0x33b | u16 | length of the rest: 0x51, or 0x4d at V1742 (no recall macro) | files |
| +0x33d | i32 | number x 100: 1.5 is 150 | one-change saves |
| +0x341 | u16 | fade, in quarter frames: the longest crossfade (+0x35) of the snapshot's states | one-change saves; every snapshot of the 46 shows |
| +0x343 | u8 | snapshot group, counted from 1, 0 = none | one-change save |
| +0x344 | u8 | 1 = skipped by Fire Previous and Fire Next | one-change save |
| +0x345 | u16 | 18 in every snapshot | files |
| +0x347 | i32 | recall time, in quarter frames at the session's frame rate. On with misc bit 7 | one-change saves |
| +0x34b | i32 | duration, in 1/100 s. On with misc bit 3 | one-change save |
| +0x34f, +0x353, +0x357 | i32 | play from, play to, locate to. On with misc bits 4, 5, 6 | one-change save; unit open |
| +0x35b | u32 | note text colour, Windows RGB (black by default) | one-change save |
| +0x35f | u32 | note background (white by default) | one-change save |
| +0x363 | u8 | note font charset (1) | files |
| +0x364 | u8 | note font size (9). +0x365 u8: font style | one-change save |
| +0x366 | name[32] | note font ("Arial") | files |
| +0x386 | u16 | id (below) | files |
| +0x388 | u16 | faders and panners wait time from the Cross Fades panel, in quarter frames | one-change save |
| +0x38a | i32 | macro fired on recall: its position in the macro list, from 0. -1 = none | one-change saves |

Recall time:

- 01:00:00:00 at 25 fps is 90,000 frames and is stored as 360,000. One second more adds 100, one frame adds 4.
- Changing the session's frame rate leaves the stored number as it is. The frame rate is header byte 0x5f: 2 = 25 fps and 5 = 30 fps (one-change saves), 1 = 24 fps (read from a show).
- A timecode offset is not a field: the console adds it into the stored time.
- Recall at Time switched off keeps the stored time.

Fade:

- A fade is a crossfade time on module states (+0x35). The snapshot's fade at +0x341 is the longest of them.
- The Cross Fades panel puts a column's time on every module of that column in the snapshot's states. 20 frames on an aux's Input/Trim column put 80 on its `0b` and `1a` states, the modules of that Recall Scope column ("Recall Scope panel columns" in `scope-and-recall.md`).
- Setting the snapshot's fade time in the snapshot list put that time on the fader module `0c` of every input, and on nothing else.

MIDI list:

- Each entry is `u8 n | port letter | n - 1 message bytes`.
- Program change 5 on channel 1, port A, is `03 41 c0 04`: the file keeps the program number minus 1.
- A snapshot can send several messages of any kind. `03 41 c0 04 03 41 c1 06 04 41 90 0a 05` adds a program change on channel 2 and a note on.
- The console sets misc bit 0 with the list. All 940 snapshots with a list in the 46 shows have it.

Id and number:

- Ids written by the console run 0x10, 0x110, 0x210 and so on. The high byte counts up over the show's life: a show with one snapshot holds 0x710.
- The low byte is 0x10 in 1337 of the 1476 snapshots; 0x11, 0x12 and 0 also occur.
- Ids are unique in 45 of the 46 shows. One show with 222 snapshots repeats nine of them. What the console uses the id for is open.
- Snapshots are stored in number order in all 46 shows. Numbers can repeat: the show with 222 snapshots holds five numbers twice.
- Setlists and the trailer point at a snapshot by its position. A macro that fires a snapshot by number keeps the number (one-change save).

## Snapshot groups

A group record is 338 bytes: `u16 0x150 | name[32] | 4 x 72 bytes | 16 zero bytes`. The four 72-byte blocks hold `be 73 48 7c` markers and `ff`; what they mean is open.

A snapshot's group byte (+0x343) points into this list, counted from 1. Nothing else refers to a group by number: section 211 keeps none, and no macro action names a group. So groups can be reordered by moving the records and every snapshot's group byte with them. A file reordered this way loaded on a Quantum 112.

## Setlists (section 115)

```
73 00 | u32 count | count x (name[32] | u32 n | n x u32 snapshot index) | i32 current setlist, -1 = none
```

- An empty section is `73 00 00 00 00 00 ff ff ff ff`.
- V2232 and V2242 files have the section. The 53 files from V2025 and older have none.
- A setlist names snapshots by their position in section 210. The indexes move when a snapshot is added or deleted in front of them.
- Proven by one-change saves. A setlist in running order, written by bytes, loaded and fired its cues.

## Trailer

The trailer follows the last snapshot. It is 794 bytes starting `ec 00`, or 795 bytes starting `ed 00`:

- 794 in every V1742 and V1926 show, and in the empty sessions of the Quantum 225 and 338 offline programs at V2242 (not the Pulse ones).
- 795 in every V2232 and V2242 show. V2025 shows have either.
- Two files written from those empty sessions, saved again by DiGiCo's software, came back with 795 bytes: one 0 byte was inserted at offset 238.

| Offset | Type | Meaning |
| --- | --- | --- |
| +2 | i32 | current snapshot, -1 = none |
| +6 | i32 | the snapshot that was current before it |
| +10 | i32 | selected snapshot |
| +0x1f | u8 | 1 = Relative Groups on |

- Insert New made the new snapshot current and selected, and put the old current one at +6.
- Delete set +2, +6, +10 and the current setlist to -1.
- In a show without snapshots, +2 and +10 are -1, but +6 often is not (73 of 75 shows). Check +6 only in a show with snapshots.
- The rest of the trailer is open.

The editor's own Delete and Insert New move +2, +6 and +10 differently from the bullets above that start "Insert New made" and "Delete set". The rules are under "Insert New, as the editor does it" and "Delete a snapshot, as the editor does it".

## Writing snapshots

Nothing in this folder writes snapshots yet, and the tools refuse structural edits on a session with snapshots. Each recipe below was written by bytes and loaded on a Quantum 112.

The sections marked editor-verified were compared with the editor's own result, or loaded in the editor. Each names its consoles and builds. Where an editor-verified section and an older recipe differ, follow the editor-verified section.

### Add a snapshot

1. Copy a snapshot record.
2. Set the name, number, group byte, recall time and misc bit 7. Give it a new id: one high byte above the highest in the show, low byte 0x10.
3. Add 1 to the reference count of every state the copy points at.
4. Insert it in number order. Raise every setlist index and trailer index at or after its position by 1.

Without step 3 the file loads, but a later delete on the console can free states that other snapshots still use.

A cue list from timecode works this way: one snapshot per song with the song's start as its recall time, Recall at Time on, one group per song, and a setlist in running order. Written by bytes, it loaded and the cues fired.

### The first snapshot of a show without snapshots

- Each module of section 211 becomes one state, with the same slots in the same order, minus the params a snapshot never keeps. The first 5 of the 10 bytes stay as they are. +0x39 = 0, +0x3a = 1, both history fields -1, and the date is the time stored.
- The record is section 211's record with each strip's modules replaced by pool indexes (the byte after `d5 00 01 00` = 0). It gets a name, number 100 (+0x33d), id 0x10 (+0x386) and the time stored. Nothing else in the options changes.
- The trailer's current and selected become 0.
- The console groups the states by strip type, in this order in a Quantum 112 file: `1b 4d 1c 4e 1d 4f 1e 50 11 18 0b 08 0a 10 0f 07 05 06 01 0c 09 1f 51`. Snapshot strips find their states by index, so a reader needs no order.

Checked against a session saved before and after the console stored its first snapshot. Rebuilt this way, all 1726 states equal the console's bytes except their dates. A new show built from a console's empty session with a first snapshot written this way loaded.

### Insert New

For each module of section 211, take its snapshot form (without the params a snapshot never keeps). Point the new snapshot at the current snapshot's state for that strip and module when the slots, the first 6 of the 10 bytes and the name are equal. Otherwise add a new state with the current snapshot's scope flags. Raise the counts. The new snapshot becomes current and selected.

### Insert New, as the editor does it (2026-10-31, editor-verified)

The editor's own Insert New was compared with the same change written by bytes. Every state, every snapshot and every other section was equal, apart from the save times and, between two snapshots, the 3 bytes in the last bullet below. Quantum 225 at V2242: after one live change (an input muted), with the new snapshot stored after the last one and between two others. SD12 at V1619 and V2242: with no live change, so every state was shared. The recipe above holds, with these changes:

- The trailer's previous snapshot (+6) stays as it was. Only the current (+2) and the selected (+10) snapshot become the new one. The previous snapshot does not move with the snapshots after the new one: in the run between two snapshots it stayed 3, while the snapshot it had named moved to 4.
- The new snapshot goes after the current one. With no current snapshot, it goes last.
- The number (+0x33d) follows the neighbours. After the last snapshot, when its number is whole, the new number is the next whole number (3.00 gives 4.00). Between two numbers 1.00 apart, it is the half (1.00 and 2.00 give 1.50). Between two numbers 0.50 apart, it is 0.20 more (1.00 and 1.50 give 1.20). The editor's result for any other gap was not captured.
- The id (+0x386) is one high byte above the highest id in the show, with low byte 0x10. The editor's own results ran 0x310, 0x410 and 0x510.
- A new state goes at the end of the pool. Its history fields hold -1 and the position of the new snapshot ("Section 210" above). In every older state, a snapshot index in the second history field at or after that position goes up by 1.
- Firing a snapshot in the editor changes 3 bytes of strip trailers, in section 211 and in the fired snapshot. A snapshot stored after the fire copies them from section 211. A store by bytes leaves those bytes as they are.

Proof: the new snapshot loaded in the Quantum 225 V2242 editor and appeared in the list. Firing the first snapshot unmuted the input. Firing the new snapshot muted it again.

Not captured, so write no Insert New in these cases:

- The current snapshot's states carry scope flags or crossfade times. The flags of the new states are not known.
- The gap between the neighbours is not 1.00 or 0.50, or the last number is not whole.
- The session has setlists. The positions at or after the new snapshot go up by 1, as under "Add a snapshot", but no editor Insert New was driven on a session with setlists.

### Update a snapshot

- Write the changed values into the snapshot's states. Keep its scope flags, crossfades, strip list and options.
- A state that other snapshots share needs a copy first. Add it at the end of the pool, with the old index and this snapshot in the history fields and count 1. Lower the old state's count by 1 and point the snapshot at the copy.
- A rename also goes into the snapshot's strip trailer and its Input/Trim state ("Names on a recall" in `scope-and-recall.md`).
- A value can go into section 211 only, into one snapshot, into every snapshot, or only into the snapshots that held the old live value.
- An FX unit's state in a snapshot can hold another algorithm than the live unit. The same param is another control there, so leave such states alone.

### Delete a snapshot

1. Remove the record and lower the count of every state it used by 1.
2. Drop it from every setlist, and lower the setlist indexes after it by 1.
3. Set the trailer's +2, +6, +10 and the current setlist to -1.
4. Remove the states only it used when they are the last states of the pool.

Done this way, a delete matched the console's own delete byte for byte. There the states only the deleted snapshot used were the last in the pool. Removing a state from the middle would move every later index in every snapshot. Leaving it in place with count 0 gives a state like the 7847 that console files already hold.

### Delete a snapshot, as the editor does it (2026-10-31, editor-verified)

The editor's own delete (delete mode, mark the row, confirm, Save As) was compared with the same delete written by bytes. Every state, every snapshot and every other section was equal, apart from the save times. Quantum 225 at V2242: seven deletes in a row, among them the first row, a middle row, the last row, the current snapshot, a snapshot after the current one, and a snapshot that made a state in the middle of the pool. SD12 at V1619 and at V2242: one delete each. The steps above hold, with these changes:

- The trailer's current snapshot follows its snapshot: it becomes -1 when the deleted snapshot was the current one, goes down by 1 when it came after the deleted one, and stays when it came before. The selected snapshot becomes the row above the deleted one (-1 for the first row). The previous snapshot (+6) is not touched. Step 3 above, which sets all three to -1, is not what the editor writes.
- A state that only the deleted snapshot used leaves the pool wherever it sits. Every later pool index in every snapshot goes down by the number of removed states in front of it. Step 4 above names only the case where the removed states are the last in the pool.
- Delete does not leave a freed state behind with count 0. Update Current leaves such states.
- In the second history field of every state, a snapshot index after the deleted snapshot goes down by 1. A state that the deleted snapshot made, and that stays in the pool, gets -1 there.
- Setlists (V2232 and V2242 files): the snapshot leaves every setlist, later positions go down by 1, and the current setlist becomes -1, as in the steps above. No editor delete was driven on a session with setlists.

Not captured: the delete of the only snapshot. Use Clear all snapshots to empty the list.

### Notes, MIDI, lock and skip

Written by bytes and loaded: notes (text with CRLF line ends), lock (misc bit 13), skip (+0x344) and a MIDI program change (program number minus 1, misc bit 0).

### Settings of one snapshot (2026-10-31, editor-verified)

One file per console and build, written by bytes, had every setting below changed on one snapshot: Quantum 225 at V2242, SD12 at V1619 and SD12 at V2242. The editor loaded each file as its startup session. The Snapshots screen showed the new name, number, lock, skip, duration and recall time. The editor's re-save read back every value. The re-save equals the editor's re-save of the unchanged session with the same settings written on it by bytes, save times masked. So the editor moved no other byte.

- Name: u16 length and latin-1 text, after the strips. The longest name in 47 real shows is 29 characters.
- Note: u16 length and text, after the options, with CRLF line ends. The longest note in 47 real shows is 237 characters.
- Number: the i32 at +0x33d, number x 100. Keep the snapshots in number order: give a snapshot a number between the numbers of its neighbours.
- Skip: the u8 at +0x344. 1 = skipped.
- Lock: misc bit 13.
- Recall time: the i32 at +0x347, in quarter frames at the session's frame rate, on with misc bit 7 (Recall at Time).
- Duration: the i32 at +0x34b, in 1/100 s, on with misc bit 3.
- The proof files had each value and its switch on. The Snapshots screen shows a recall time as "fire at timecode hh:mm:ss:ff" and a duration as hh:mm:ss:ff.

A longer or shorter name or note changes the size of section 210. Rewrite the section table offsets to match: the last offset equals the file size ([`FORMAT.md`](FORMAT.md), "File structure"). Skip, lock, number, recall time and duration change bytes in place.

### Clear all snapshots (2026-10-31, editor-verified)

The editor's own Files > Session Structure > clear snapshots > Restructure was captured six times in five editors: Quantum 225 at V2242, V2025 and V1619, SD9 at V2242 (twice) and SD12 at V1619. The Quantum 225 and SD9 sessions are real shows. The two SD9 captures are a show with a snapshot group and the same show with 2 setlists written by bytes. The SD12 session is a sample with 3 snapshots stored in the editor.

Each capture saved the session twice in one boot: after a Restructure alone, then after clear snapshots and Restructure. A Restructure alone also writes other things (it can add I/O rack records and reset some live values). So the second save, compared with the first, shows what the clear writes. Two saves of one session also differ in save-time bytes (the module times, the heap words of the bank records). Those were masked.

What the clear writes:

- Section 210 loses the pool, the groups and the snapshots. It is `d2 00 d2 00`, four u32 counts of 0 (the pool, the `u32 0`, the groups, the snapshots) and the trailer.
- Trailer: current, previous and selected (+2, +6, +10) become -1. The u32 at +14 and the u32 at +33 become 0. The byte at +23 becomes 0 in the V2242 editor only. The V1619 and V2025 editors keep it. The rest of the trailer stays.
- Section 115 (V2232 and V2242 files) becomes the empty setlist section `73 00 00 00 00 00 ff ff ff ff`. Older builds have none.
- Section 201: every section's Global Scope goes back to its default ([`scope-and-recall.md`](scope-and-recall.md), "Global Scope defaults and the clear"). A Restructure alone keeps Global Scope.
- Nothing else changes. The live settings in section 211 stay as they are.

The trailer offsets count from its length word, as in "Trailer" above. Counted from after the length word they are 0, 4, 8, 12, 21 and 31.

Proof: a file made from the first save by writing only the changes above equals the editor's second save in all six captures, after the masks.

Load proof: files cleared this way by bytes, from the real Quantum 225 and SD9 shows, loaded in the Quantum 225 V2242, SD9 V2242 and Quantum 225 V1619 editors. The Snapshots screen was empty. The editor's re-save held no snapshots and no setlists. The re-save equals the written file except two things the editor does on any load of a session without snapshots. Its own cleared file gets the same two:

- The trailer gets one more 0 byte at its end. Its length word goes from 236 to 237, so 794 to 795 bytes in all, as under "Trailer" above.
- The u32 at +0x4c of the section 201 channel records of auxes and control groups becomes -1 (counted from the `cb` tag).

Not load-proven: the cleared Quantum 225 V2025 and SD12 V1619 files (their captures match, but no file written by bytes was loaded), SD12-96 files (a plain SD12 editor opens its own session for them) and Pulse files (no Pulse editor was run).

Not known:

- What the trailer bytes at +14, +23 and +33 mean. The clear sets them to 0.
- Header byte 0x5f = 3. Some real shows hold it. Which frame rate it is stays open.
- The clear on V1455, V1528, V1742, V1926, V2126 and V2232: not captured.
- The clear on any console other than the Quantum 225, SD9 and SD12 above: not captured.

### Restructure with snapshots (2026-10-31, editor-verified)

Files > Session Structure > Restructure, with clear snapshots off, keeps every snapshot and rebuilds section 210 with the console. Each change was made in the editor and saved with Save As. The same change written by bytes, with section 210 rebuilt by the rules below, equalled the editor's save in 36 results: Quantum 225 at V2242 (12), SD12 at V2242 (13) and SD12 at V1619 (11). The comparison masks the save times. On the Quantum 225, it also leaves out the two resets in rule 9. The sessions are builds from an editor default session with generic channel names, or a sample session, with 2 or 3 snapshots stored in the editor. The changes were: inputs added, removed and moved (moved on the Quantum 225 only), a stereo input added, mono and stereo auxes and groups added, mono auxes and groups removed, and several kinds in one Restructure.

1. A removed strip loses its copy in every snapshot. The pool states that no copy uses any more go, and the rest are numbered again in order. A route to the removed strip inside a pool state becomes 0.
2. On the Quantum 225 at V2242, the editor drops the snapshot copies of strip `0901` (kind 09, index 1) on every Restructure, whatever the change was. The SD12 editors at V1619 and V2242 keep them.
3. A new strip gets one new set of pool states, and its new copy in every snapshot points at them. The set holds one state per module of the live strip, without the params a snapshot never keeps for that strip type. The reference count (+0x3a) is the number of snapshots, and +0x39 is 0. Every slot that holds a route to another strip is 0, among them a stereo bus's partner key `(05, 14)`. The width slots hold the mono value, also on a stereo input: `(08, e8)` on bands 0 and 1 and `(0e, e8)` are 1.0, and `(1d, 3f)` is 0.0. The copy goes into every snapshot in strip id order.
4. The states for the new strips of one Restructure are written in this order: right legs (strip type `07`), auxes (`05`), groups (`06`), inputs (`01`), each by id. Inputs, an aux and a group in one Restructure make one rebuild at the end, so the order holds across kinds.
5. A new aux or group adds its band to the per-bus runs in the pool states of every kept strip. The editor appends the band's slots at the end of the run, with the value the live strip holds. The runs include the aux sends of module `02` on inputs, groups, right legs and the talkback input (with `f2` left out), and the group assigns of module `03`. The send level `(02, 01)` is the exception: it is -150 (off), also where the live talkback input holds 0. A run per param (the group assigns of the talkback input) takes the new band on its first param only. Quantum 225 and SD12 at V2242.
6. The runs of removed buses stay in the pool states. A bus added later that takes a freed band finds its slots there, and the editor leaves them as they are. SD12 at V2242: 1200 pool states came back identical, and the 2 new auxes got 9 states each.
7. The Quantum 225 and SD12 editors at V2242 write the trailer one byte longer after a Restructure: 794 bytes (`ec 00`) become 795 (`ed 00`, a 0 byte inserted at offset 238). A file that the V2242 editor saved before already has 795. The SD12 V1619 editor keeps 794.
8. Trailer +33 is a bit field, and the low byte of the u32 that Clear all snapshots sets to 0. The Restructure writes 4 when a stereo aux or group is added, and 1 when a stereo strip is added on a Quantum. A stereo input on a Quantum gives 1, a stereo bus on a Quantum gives 5, and a stereo bus on the SD12 gives 4. The byte stays 0 when the change only adds mono strips or removes strips, and for a stereo input on the SD12. Earlier captures held 0x10 for an LCR group and 5 for pre-mute sends, so the byte is not only a stereo flag. The values written here are proven. The meaning of the other bits is open.
9. The editor resets two things that a file written by bytes keeps. On the Quantum 225, the strip view bytes in the banks (section 243, +0x15d) go back to the SD view. After an input is removed, the editor renumbers the Mustard channels (section 201 input records, +86) on load. Recalls fired in the editor showed that neither changes what a recall brings back.

Proof, loaded: files made this way were the startup session of the SD12 at V1619 (2 files), the SD12 at V2242 (1 file) and the Quantum 225 at V2242 (2 files). Each re-save equalled the written file, save times masked. Proof, recalled: snapshots were fired one by one in the editor on files of the same kinds. Every recall fired, the Snapshots screen listed every snapshot, and the new strips showed on the surface. On the Quantum 225, the recall saves from the written file and from the editor's own result were equal in both recalls, apart from the strip view bytes.

Not covered: a real Quantum 225 show saved at V1619, with 3 snapshots, custom banks and a custom aux order, in the Quantum 225 V1619 editor. The editor put a new mono aux second, and rebuilt the banks and sections 201, 211, 212 and 246 differently from the written file. The rules above were not shown for that case.

## For tools

- Keep every reference count equal to the number of snapshot strips that point at the state.
- Append new states at the end of the pool. Snapshots point at states by position.
- Copy a shared state before you change it for one snapshot.
- Keep snapshots in number order, and move setlist and trailer indexes with them.
- Leave the params of the table above out of every pool state.
- Match strips by (index, type) and slots by (param, band), never by position.
- Don't rely on the history fields, on unique ids, or on unique numbers.
- A delete takes the states that only the deleted snapshot used out of the pool wherever they sit. Move every later pool index and every history index with them.
- On a delete and on an Insert New, keep the trailer's previous snapshot as it is. Do not move it with the snapshots.
- After a structure change on a session with snapshots, rebuild section 210 by the rules in "Restructure with snapshots".

## What we don't know

- The 992-byte block in each snapshot record, the four blocks of a group record, and most of the trailer.
- The unit of play from, play to and locate to.
- What the id is for, and what its low byte means.
- The GPO relay states: only the field's name is known.
- Which modules each Cross Fades column covers, beyond Input/Trim on an aux. A fade written by bytes is not tested.
- How a fade typed in seconds becomes frames: 2.5 s was stored as 280, which is 70 frames at the session's 30 fps.
- Whether the console needs the order of the pool states.
- SD consoles: none of this is tested on an SD file.
- Settings, Delete, Insert New and Restructure with snapshots: run on the Quantum 225 at V2242 and the SD12 at V1619 and V2242 only. The line above stands for every other SD console.
- Delete, Insert New and renumber on a session with setlists, and the delete of the only snapshot: not driven in an editor.
- Insert New after a snapshot whose states carry scope flags or crossfade times, and for number gaps other than 1.00 and 0.50.
- Whether a delete moves the first history field of a state (the pool index it was copied from) when it removes states in front of that index. The deletes written by bytes left the field as it was and matched the editor. Whether any of them held such a state is not known.
