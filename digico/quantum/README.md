# DiGiCo Quantum

Covers Q112, Q225, Q225 Pulse, Q326/338, Q338 Pulse, Q5, Q7 and Q852. File extension: `.ses`.

## Tooling

- From `digico/scripts`, read with [`ses.py`](../scripts/ses.py), `sessionmaker.inspect` and `sessionmaker.validate`. Build with `sessionmaker.build`. Edit with `sessionmaker.edit` and `sessionmaker.commands`. List baselines with `sessionmaker.consoles`.
- Per-model table: [`consoles.py`](../scripts/sessionmaker/consoles.py). Docs: [`sessionmaker.md`](../references/sessionmaker.md), [`baselines.md`](../references/baselines.md) and [`FORMAT.md`](../references/FORMAT.md).
- Open every result in the offline editor for that console and build. Use **Files > Save As**. Load only that save on a console.

## What we know

| Key | Model | Family | Default inputs | Max inputs | Mustard cap | Spice Rack slots | Bus budget |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `q112` | Quantum 112 | Q1 | 48 | 80 | 20 | 6 | 26 |
| `q225` | Quantum 225 | Q2 | 48 | 72 | 24 | 6 | 38 |
| `q225p` | Quantum 225 Pulse | Q2 | 48 | 96 | 36 | 6 | not listed |
| `q338` | Quantum 326/338 | Q3 | 48 | 128 | 36 | 8 | 66 |
| `q338p` | Quantum 338 Pulse | Q3 | 48 | 156 | 48 | 8 | not listed |
| `q5` | Quantum 5 | Q5 | 108 | 124 | 24 | 12 | 130 |
| `q7` | Quantum 7 | SDQ | 72 | 253 | 24 | 16 | 130 |
| `q852` | Quantum 852 | Q8 | 72 | 253 | 24 | 32 | 194 |

- Verified: the Q225 Mustard cap of 24 and the Q225 V2242 build. On a Q225, a stereo channel uses 2 Mustard instances, and on load the editor turns off the excess in channel order.
- Quantum 112 inputs, proven on a real console (V2242): a session with 80 inputs, written by bytes, loaded. The same session with 82 inputs was refused on load with "console not supported".
- Default inputs are fallbacks. The newest baseline's own count wins. Bus budget is mono equivalents (FORMAT.md).
- Generated Q225 V2242 sessions loaded in the V2242 offline editor and re-saved unchanged. In-place patches (names, HPF, fader, mute) loaded on a real Quantum 2.
- Pulse models need the Pulse extension on the console, V1742 or newer. Q326 and Q338 share one key.
- TB In sits at 254 on Q2, Q3, Q5 and Q7, and at last input + 1 on Q1 and Q8.
- Snapshot scope, Global Scope, the channel safes and what a recall changes: [`scope-and-recall.md`](../references/scope-and-recall.md). Proven on a Quantum 112 at V2242 and V2242.4 with one-change saves and recalls saved on the console. Shows from the other Quantum models use the same flags.

### Session Structure limits (measured)

The table above shows what `consoles.py` allows today. This table shows what the console's Session Structure dialog allows, read in the real offline editors on 2026-10-24. The limits are the same at every build each editor exists for. A stereo input takes 2 paths, and an FX return counts as an input. See [`engine-findings.md`](../references/engine-findings.md).

| Key | Input paths | Bus slots | Rule | Builds read |
| --- | --- | --- | --- | --- |
| `q112` | 80 | 26 | fixed | V2126, V2232, V2242 |
| `q225` | 72 | 38 | fixed | V1455 to V2242 |
| `q225p` | 96 | 50 | fixed | V1742 to V2242 |
| `q338` | 128 | 66 | fixed | V1455 to V2242 |
| `q338p` | 156 | 74 | fixed | V1742 to V2242 |
| `q5` | 256 | 130 | pool | V1455 to V2242 |
| `q7` | 256 | 130 | fixed | V1455 to V2242 |
| `q852` | 384 | 194 | fixed | V1926 to V2242 |

- Quantum 5 pool: paths + bus slots must be 290 or fewer. Matrix outputs do not count. At the default 36 bus slots this gives 254 paths.
- The `consoles.py` caps for Q5 (124), Q7 (253) and Q852 (253) sit below these limits, and the Q112 cap (80) equals its limit. They count channels, so stereo inputs can still pass the path limit: 253 channels with 4 stereo is 257 paths on a Q7.
- The Quantum 5 load check allows 256 inputs and 134 bus paths and does not know the pool. A file can load and then lose inputs at the first Restructure.

### Other findings

- Snapshots: the pool, the snapshot record and its options, snapshot groups, setlists, and how to add, update and delete a snapshot by bytes: [`snapshots.md`](../references/snapshots.md). Proven on a Quantum 112 at V2242 with one-change saves and with files written by bytes that loaded. Shows from the Quantum 225, 326, 338 and 852 (V1742 to V2242) have the same layout.
- Snapshot times and the Snapshots panel's settings (2026-11-01, one-change saves on a Quantum 112 at V2242): every snapshot time is in quarter frames of the session's frame rate, the duration too (5 s is 600 at 30 fps). Frame rate codes 3, 4 and 6 are 29.97, 29.97 drop and 30 drop, counted as 30 frames a second. The trailer of section 210 holds the panel's settings: [`snapshots.md`](../references/snapshots.md), "Snapshot times" and "Trailer".
- Snapshot settings, Delete, Insert New and Restructure with snapshots (2026-10-31, editor-verified), Quantum 225 at V2242. Settings of one snapshot loaded and re-saved with every value kept. A delete and an Insert New (after a live change, after the last snapshot and between two) written by bytes equalled the editor's own result, save times masked. Between two snapshots, 3 bytes that the editor's fire wrote were the only other difference. A Restructure with snapshots kept (12 editor results) did too, apart from two resets the editor makes. Details: [`snapshots.md`](../references/snapshots.md) and [`engine-findings.md`](../references/engine-findings.md). No other Quantum model or build was run.
- Pulse: header `0x25` bit `0x10` set means Pulse on a Q225 or Q338 file. Every Pulse default session has the bit set, and every plain default has it clear.
- Quantum 7 V2242: the editor clears 48V on load on the Local I/O Mic/Lin inputs (socket 0:Mic/Lin 1 and 3 proven), main and alt inputs. Gain stays. Switch 48V on at the console.
- MADI links: a device on a link past the console's links keeps its sockets, but the editor zeroes its device id, which means not connected. Quantum 225 keeps links 0 to 2 (link 4 was zeroed at V1619 and V2242). Quantum 338, 5, 7 and 852 kept links 0, 2 and 4.
- Spice Rack slots hold a Chilli 6 or a Naga 6. A stereo link of a Chilli 6 and a Naga 6 loads with the link dropped, proven on Q225. Two Chilli 6 slots link. A link of two Naga 6 slots is unverified. A mono channel can use a Naga 6 slot.
- A stereo channel takes the slot pair 1+2, 3+4 or 5+6. A pair written as 2+3 keeps the link, but the editor marks slot 4, not slot 3, so write the pair the editor would take.
- Insert points: inserts A and B and the Mustard strip each hold one of the five points, and they never share one. Slot `e1` of module 08: 0 post-fader, 2 pre-fader, 3 mid-EQ/dyn, 4 pre-EQ/dyn, 5 pre-processing. Defaults: A 4, B 2, Mustard 3. Proven on Q225 V2242.
- Names hold up to 31 characters ([`FORMAT.md`](../references/FORMAT.md), Names). Console-saved sessions from every Quantum model hold longer names, and names of 9 to 13 characters, written in place, loaded on a real Quantum 112 (V2242). The tools write 8 by choice.
- Confirmed 2026-10-31 in the Quantum 225 V2242 and Quantum 112 V2242 editors, for names of 13 and 31 characters. Channels 2, 3 and 4 were renamed to 13, 31 and 31 characters in all 20 copies (the name of channel 4 held spaces, a hyphen, a slash, round brackets, a hash and digits). Both editors loaded the files. The boot re-save held every written name in all 20 copies and left every other name unchanged. A strip shows only what its name box fits: 11 to 13 characters in the Quantum 225 editor, 16 to 17 in the Session Report. The file keeps the whole name.
- Read from real console-saved sessions, not an editor load: the longest names are 12 characters on the Quantum 225 and Quantum 5, and 16 on the Quantum 326/338.

### Mustard (contributed notes)

Keys are (module, param) in hex, as in [`FORMAT.md`](../references/FORMAT.md). The full Mustard key list is in [`CHANNEL_MODEL.md`](../references/CHANNEL_MODEL.md).

- Levelling Amp (comp model 8): (1d, 52) peak reduction and (1d, 51) gain, proven by one-change saves on a Quantum 112 at V2242.4. Its attack and release are fixed: no session read holds them.
- Gate (1e, 4c), the MSE release: 0 slow, 1 medium, 2 fast. Proven by one-change saves on a Quantum 5 at V2025.
- A comp or gate type change resets that module's controls to the type's defaults. Write the type first, then the controls. Proven by one-change saves; the editor does the same on load.
- The engine mode at header 0x87 offers 1 (48 kHz) and 4 (96 kHz) only on Quantum ([`session-structure.md`](../references/session-structure.md)).
- Nodal nodes, Spice Rack objects and the Quantum strip kinds: [`session-structure.md`](../references/session-structure.md).
- Confirmed 2026-10-31 in the Quantum 225 V2242 and Quantum 112 V2242 editors, with files written by bytes, loaded and re-saved: Levelling Amp gain (1d, 51) and peak reduction (1d, 52) take 0 to 100. Four Levelling Amps on channels 1 to 4 held gain and peak reduction of 60 and 45, 0 and 100, 100 and 0, and the type's defaults. The strips showed peak reduction 45, 100, 0 and 20 and gain 60, 0, 100 and 25, so 0 and 100 are the ends of the knobs and the defaults are 25 and 20. The Quantum 112 keys are the Quantum 225's.
- Same runs, channels 5 to 9: a gate, a ducker and three MSEs (release fast, slow and medium), each with a threshold and a range. The keys are the mode (1e, 0b) with 0 gate, 1 ducker and 2 MSE, the threshold (1e, 0e), the range or depth (1e, 0a) and the MSE release button (1e, 4c). The gate row on the M view read gate, duck, mse, mse, mse with the thresholds written. The depth and the release button are not drawn on the strip, and the re-save kept them. The type or mode went in first and the controls after it, which is the order the type-change line in this list asks for.
- The re-save equalled the written file on every Mustard slot: each written value exact, and no other slot of modules 1d and 1e changed.
- The Quantum 5 V2025 editor has no Levelling Amp (its Mustard comp slots stop at 4d) and resets a Levelling Amp written into a V2242 file. A V2025 baseline with a gate, a ducker and an MSE written loaded and re-saved unchanged. The Levelling Amp is proven on the Quantum 225 and Quantum 112 only.

### Fader banks

Bank placement is section 212 ([`FORMAT.md`](../references/FORMAT.md), "Fader bank placement"). The bay map below was read off the V2242 editors' Fader Banks screens on each console's default session. The record is the section 212 record of the bay. Layers x buttons is the grid the screen shows.

| Family | Models | Bays: record, layers x buttons | Bank moves |
| --- | --- | --- | --- |
| `Q1` | Quantum 112 | Main: 2, 3 x 4 | unproven |
| `Q2` | Quantum 225, 225 Pulse | Left: 3, 3 x 4. Right: 2, 3 x 4 | proven at V2242 and V1619 |
| `Q3` | Quantum 326/338, 338 Pulse | Left: 2, 3 x 4. Centre: 4, 3 x 4. Right: 3, 3 x 4 | proven at V2242 |
| `Q5` | Quantum 5 | Left: 2, 3 x 5. Centre: 4, 3 x 4. Right: 3, 3 x 5 | unproven |
| `SDQ` | Quantum 7 | Left: 2, 6 x 6. Master 1: 1, 1 x 4. Master 2: 0, 1 x 4. Right: 3, 6 x 6 | unproven |
| `Q8` | Quantum 852 | not mapped | not mapped |

- A bank move is proven when a file with banks moved by bytes loaded in the editor, the Fader Banks screen showed every moved bank, and the re-save kept section 212 byte for byte and added no bank ([`engine-findings.md`](../references/engine-findings.md), "Fader banks"). The runs used the Quantum 225 (V2242 and V1619) and Quantum 326/338 (V2242) editors.
- The Pulse editors were not part of the runs. A Pulse default session holds the same section 212 as the plain console's.
- More than two bays: the Quantum 326/338 and Quantum 5 have three. The Quantum 7 has four, with two Master columns of one layer between Left and Right.
- Quantum 852: the default session fills records 1 to 4. Which record is which bay was not read.
- Colours on a real Quantum 112 (V2242, 2026-10-15): bank colours written by bytes loaded and showed on the console's bank buttons, which do not show true RGB. Pale colours wash out to white, dark ones go black, and mixed ones shift: salmon `#fa8072` showed warm white, `#0c2238` and `#000000` black, brown `#8b4513` orange-green, pink `#ffc0cb` cold white. These showed close to as written: the set A defaults, `#ff0000`, `#ffff00`, `#ff8000`, `#00c859`, `#00ffff`, `#ff00ff`, `#000080`, `#3cb371` and `#32cd32`. Two files of test colours, each bank named after its colour, read off the surface.
- Colours: the Quantum 112, 225, 326/338 and 852 defaults hold colour set A. The Quantum 5 and Quantum 7 defaults hold set B ([`FORMAT.md`](../references/FORMAT.md), "Fader bank placement"). How the Quantum 5 and Quantum 7 editors draw them was not checked.
- The scripts in this folder read bays for the `Q2` family only and move no bank.

### Sample rate keys (2026-11-01, editor capture)

Quantum 225 at V2242. The bytes are in [`session-structure.md`](../references/session-structure.md), "Sample rate keys".

- The 48kHz and 96kHz keys change header 0x77, header 0x87 and the mode byte (+4) of two records of section 246: the MQ-Rack record and the Standard MADI record. Nothing else changes, with or without snapshots. The session with snapshots held 2 snapshots and 2 FX units.
- Hops captured: up, down, up, down without snapshots, and up, down, up with snapshots.
- Files written with the same changes loaded in the Quantum 225 V2242 editor. The editor showed the new rate on the master screen and re-saved each file with that rate.
- Quantum 225 at V1619: a real show with Copy Audio presets showed the prompt "Changing Sample Rate will clear all Copied Audio. Continue?" after the 96kHz key and Restructure. After Yes, section 229 was unchanged.

### I/O patch (2026-11-01, editor load)

Quantum 225 at V2242 and V1619. The rules are in [`io-patch.md`](../references/io-patch.md).

- Editor load of an added SD Rack (V2242 and V1619), an added MQ-Rack (V2242) and a removed rack (V2242): the editor kept every rack record, socket group and route. The V1619 re-save differed only in section 219 stamps and section 243 heap words.
- The same files held channels 1 to 8 on the new rack, gain, 48V and pad on its sockets, and aux outputs on its outputs. The editor kept them.
- Quantum 225 V2242 with 3 snapshots: after a live patch change, firing a snapshot brought back the snapshot's input source and aux output. Gain, 48V and pad stayed.

### Bus processing (2026-11-01, editor load)

Quantum 225 at V2242 (sample session) and V1619 (editor default). The keys and rules are in [`bus-processing.md`](../references/bus-processing.md).

- Aux, group, Master and matrix output strips: EQ, compressor, gate, delay and trim. The editor kept 63 of 63 pairs of change kind and bus kind at both builds. The 63 pairs cover 658 slots, with no stray slot.
- A Quantum bus holds 8 EQ bands. Bands 5 to 8 take gain, frequency and Q only. A shelf on bands 2 and 3 stays.
- Insert in: 23 switches on groups and matrix outputs of a real V1619 show with 3 snapshots. The editor kept each one after it moved to the other state.
- Live edits on a session with 3 snapshots were kept at V2242, and section 210 stayed as it was.

## What we don't know

- Whether a real console processes input paths past the dialog limit: no console test has been run.
- Quantum 852 before V1926 and Quantum 112 before V2126: no editor exists. Pulse before V1742: the extension did not exist.
- The extension option on Q5, Q7, Q852 and Q112: the Enable Console Extensions panels were not opened.
- Mustard caps: Q225 Pulse, Q338 and Q338 Pulse come from DiGiCo's V1742 release notes, and the Q112's 20 from the V2242.4 release notes (no Q112 session numbers a Mustard channel above 19). The 24 on Q5, Q7 and Q852 is unverified.
- Every other model and build: same writers and `validate.py`, marked untested until someone loads one.
- `ses.py` parse floor: `digico/README.md` says V1455, FORMAT.md says V1619. Both list Q2, Q3, Q5, SD8, SD9 and SD12.
- Structural edits on a session with snapshots: refused.
- Snapshot settings, Delete, Insert New and Restructure with snapshots on the Quantum 225 at any build but V2242, and on every other Quantum: not run in an editor. A real Quantum 225 show saved at V1619, with custom banks and a custom aux order, did not match a rebuilt Restructure outside section 210.
- Mustard Optical attack and recovery, (1d, 48) and (1d, 49): a contributor reading says 0 slow, 1 medium, 2 fast. `CHANNEL_MODEL.md` says 0 fast, 1 medium, 2 slow. Needs a save that settles it: set one known option on the console and compare.
- FET ratio button (1d, 4a) value 0: a contributor reading of the screen order says it is ALL. Unconfirmed; no save holds it.
- Levelling Amp (1d, 50) as Limit or Compress: unconfirmed by a one-change save.
- DiGiCo's release notes say V1143 added Spice Rack, Mustard and nodal processing (Quantum 7), V20 the Mustard MSE, V22 the Levelling Amp and set lists, and V2242.4 lifts the Quantum 225 Pulse to 120 inputs. The dialog limit read here is 96 at V1742 to V2242. V2242.4 has not been read in the dialog.
- Bank moves on the Quantum 112, Quantum 5 and Quantum 7, and on both Pulse models: not run in their editors.
- Quantum 852 fader bank map: not read.
- A console swap inside one family, for example Quantum 225 to Quantum 225 Pulse: the swap keeps every bank, record, layer and button as the source has them. This was byte-checked on default sessions of each family. No such file was booted in an editor.
- Bank colours in the Quantum editors: the Quantum 225 editor drew the set B matrix and talkback colours as the input colour. No other Quantum editor was checked for set B colours.
- The clear snapshots + Restructure on the Quantum 225 at V1455, V1528, V1742, V1926, V2126 and V2232, and on the Quantum 112, 326/338, 5, 7 and 852 at any build: not captured. The cleared Quantum 225 V2025 file was not loaded. Pulse files: not load-proven.
- Names over 8 characters on the Quantum 225 Pulse, on every build of the Quantum 112 and Quantum 225 below V2242 (the real V1619 shows hold names of up to 12 characters), and on the Quantum 326/338, Quantum 5, Quantum 7 and Quantum 852: no editor was booted with long names there, so the site engine keeps them at 8. What a console strip shows for a name longer than the editor's name box is not known.
- Levelling Amp mode (1d, 50) and side-chain emphasis (1d, 53): not written in the 2026-10-31 editor runs, so still unconfirmed.
- A real Quantum 326/338 V2025 show with 1,889 preset library entries and 7 notes did not load in the Quantum 326/338 V2242 editor used for the 2026-10-31 runs, the unchanged show included. The cause is not known. A library entry with a note is proven on a written entry only ([`FORMAT.md`](../references/FORMAT.md), "Preset library").
- Rate keys are not proven on the Quantum 225 at V1619 (no plain session was captured), on the Quantum 225 Pulse, and on every other Quantum model and build. A device record in a state that no capture covers is not proven either: its +4 byte has a history, so the site engine refuses the record.
- Racks: adding a rack on the Quantum 326/338 is not proven, so the site engine closes it. The older proof predates the change that clears the routes of the new sockets, and a file from the current writer was never booted. Adding a D2-Rack is not proven either. The Quantum 225 has three MADI links, so the site engine refuses a second added rack.
- Output patch of a group, matrix or Master output on a rack socket: not proven. Only aux outputs are proven.
- Any I/O patch change on a session with snapshots: not proven, because a recall undoes the routes. The recall experiment ran on the Quantum 225 V2242 only.
- Bus processing: insert in on an aux, and insert in on any V2242 file, are not proven. No other Quantum model or build was run.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-10-30, Quantum 5 V2025 and Quantum 112 V2242.4, contributed one-change saves on Mustard (Levelling Amp, MSE release, type resets) and nodal nodes ported here and to `references/session-structure.md`.
- 2026-10-31, Quantum 225 V2242 and V1619, Quantum 326/338 V2242: bank moves loaded in the editors, the Fader Banks screen showed every moved bank, and the re-save kept section 212 byte for byte. The bay map of each family above was read off the V2242 editors' Fader Banks screens. Ported to `references/FORMAT.md` and `references/engine-findings.md`.
- 2026-10-31, Quantum 225 and Quantum 326/338 V2242 as console swap targets: banks carried from an SD12 (V1619) to the Quantum 225, and from the Quantum 225 to the Quantum 326/338, loaded, showed on the Fader Banks screen and re-saved with section 212 byte for byte. Ported to `references/engine-findings.md`.
- 2026-10-31, Quantum 326/338, Quantum 5 and Quantum 7 default sessions (V1619 and V2242), read from the files: output banks sit on layer 1 of the Centre bay (Quantum 326/338, Quantum 5) and of both Master columns (Quantum 7). The note in `references/script-notes.md` (layout.py section) that every default puts output banks on layer 2 holds for the Left and Right bays. That note stands.
- 2026-10-31, Quantum 225 V2242, V2025 and V1619, real shows with snapshots: the editor's own Session Structure > clear snapshots > Restructure was captured on each. A file made by writing only the changes of the clear equals the editor's save, with save-time bytes masked. Files cleared by bytes loaded in the V2242 and V1619 editors: the Snapshots screen was empty and the re-save held no snapshots. Ported to `references/snapshots.md`, `references/scope-and-recall.md` and `references/session-structure.md`.
- 2026-10-31, a real Quantum 225 show saved at V1619, read in the V2242 editor: section 210 read with the layout in `references/snapshots.md` and matched the Snapshots screen (numbers, names, current snapshot). `references/snapshots.md` covers V1742 to V2242.
- 2026-10-31, Quantum 225 Pulse and Quantum 338 Pulse V2242 default sessions, read from the files: the snapshot trailer is 794 bytes, as in the plain consoles. `references/snapshots.md` says the empty Pulse sessions at V2242 are not 794. That note stands.
- 2026-10-31, Quantum 225 V2242: section 0 is the session name. The editor shows it as Session on the master screen, as the session title in Session Structure and the Session Notes dialog, and as the Description in the Load and Save Session lists. A 64-character name written into section 0 alone showed in full and the re-save kept it. Ported to `references/FORMAT.md`. The `layout.py` and `inspect.py` docstrings and `set_notes` still call it notes.
- 2026-10-31, Quantum 225 V2242 and Quantum 112 V2242: names of 13 and 31 characters, a Levelling Amp with gain and peak reduction from 0 to 100, and a Mustard gate, ducker and three MSEs were written by bytes, loaded and re-saved with every written value kept. The Quantum 5 V2025 editor kept a gate, a ducker and an MSE and has no Levelling Amp. Ported to `references/FORMAT.md`, `references/CHANNEL_MODEL.md` and `references/engine-findings.md`.
- 2026-10-31, Quantum 225 V2242: FX units were added behind preset library entries of several strips and with a note, on a written default and on a real V1619 show with 22 user channel presets and 21 user FX presets. The editor kept every unit, and the library held the same number of entries after the re-save (43 and 143). Ported to `references/FORMAT.md` ("Preset library") and `references/engine-findings.md`.
- 2026-10-31, Quantum 225 V2242: settings of one snapshot, seven deletes in a row and Insert New (after a live change, after the last snapshot and between two) were written by bytes and compared with the editor's own result. Every state, snapshot and section was equal, save times masked, except 3 bytes that the editor's fire wrote in the between-two case. The editor's states also leave out `7b` on strip type `07`. Ported to `references/snapshots.md` and `references/engine-findings.md`.
- 2026-10-31, Quantum 225 V2242: Restructure with clear snapshots off, 12 editor results (inputs added, removed and moved, a stereo input, mono and stereo auxes and groups). Section 210 rebuilt by bytes equalled the editor's save, apart from two resets the editor makes: the strip view bytes and the Mustard channel numbers. New auxes and groups started from the default strip, not from a copy of the last bus. Ported to `references/snapshots.md`, `references/engine-findings.md` and `references/session-structure.md`.
- 2026-10-31, Quantum 225 V1619, a real show with 3 snapshots, custom banks and a custom aux order: the editor's Restructure did not equal the rebuilt file outside section 210. A new mono aux sat second, and the banks and sections 201, 211, 212 and 246 were rebuilt differently. The pair stays closed. Ported to `references/engine-findings.md`.
- 2026-11-01, Quantum 225 V2242 and V1619: the 48kHz and 96kHz keys (V2242, captured), rack add and remove, the input and aux output patch, and bus processing were written by bytes, loaded and re-saved in the editors. A real V1619 show with Copy Audio presets showed the Copy Audio prompt. A recall fired after a live patch change brought back the snapshot's input source and aux output (V2242). Ported to `references/session-structure.md`, `references/io-patch.md`, `references/bus-processing.md` and `references/engine-findings.md`.
- 2026-11-04, Quantum 112 V2242, and the Quantum 326/338 editor V2242 for one file: recalls fired and saved (six save-backs of files written by bytes, and one one-change save after FX > NEW). A recall makes the FX rack the snapshot's, an output socket's source follows the strip that feeds it, and the fader's gang comes back only with the misc switch Gangs. Ported to `references/scope-and-recall.md`, `references/io-patch.md` and `references/snapshots.md`.
- 2026-11-01 to 11-03, Quantum 326/338 editor V2242, one-change saves on a real show: where Restructure puts one more mono group, stereo group or mono aux, and a show's first stereo aux. Quantum 326/338 and Quantum 852 editors V2242: real shows with no bus of the width asked for, the bus written by bytes from another width or the master, loaded. Ported to `references/session-structure.md`.
- 2026-11-02 to 11-04, Quantum 112 V2242: the Minimum session (no aux) with one mono aux added and saved. A file written by bytes equals the save. A session from Minimum with three auxes written that way loaded in the editor, and the sends metered. Ported to `references/session-structure.md`.
