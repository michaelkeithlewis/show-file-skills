# Yamaha RIVAGE PM

Covers PM3, PM5, PM7 and PM10. File extension: `.RIVAGEPM`.

## Tooling

- No command works on these files. [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) refuses a RIVAGE PM file with one sentence.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 4 and 6.
- RIVAGE PM sections: FORMAT.md 4.7 to 4.10. The RIVAGE PM tests: FORMAT.md 1.4.
- The facts below come from black-box tests on real PM5 shows at V7.20. No reader or writer for this model line is in the script yet.
- Contributed field maps (not used by the script): [`references/rivage-fields.md`](../references/rivage-fields.md) and [`references/premium-rack.md`](../references/premium-rack.md).

## What we know

- RIVAGE PM files use the generation 2 container, `#YAMAHA MBDF`.
- A new session saved by RIVAGE PM Editor 7.2.0 walks to its exact end and rebuilds byte for byte (BB-G2-WALK).
- The header model text is `Rivage`. The session carries the editor's version, V7.20 (BB-G2-WALK).
- RIVAGE PM's compressed fields are a body with no schema of their own ([`references/script-notes.md`](../references/script-notes.md)).
- Two real PM5 shows saved on a console at V7.20 (CS-R5 surface, DSP-RX-EX engine) walk and rebuild byte for byte: the outer file, and every inner file in every `#FILE` entry (BB-RV-WALK).
- The compressed `#MMS FIELD` and `#MMS FILTER` bodies are zlib streams. Each one inflates to a complete `MMSXLIT` section with its own schema, which differs from the line above. Every schema MD5 matches and every size adds up, 4,926 sections per show (BB-RV-WALK). See FORMAT.md 4.7.
- The layout rule of FORMAT.md 4.3 gives the exact stored element size of every collection in both shows, about 119,600 collections each (BB-RV-WALK).
- The live state is in `Current/CurrentParam_1` and `CurrentParam_2`. Engine `EN00` holds the show. In both shows, engine `EN01` holds factory defaults (BB-RV-WALK).
- `CurrentParam_1` and `_2` can differ in a console save: one show had them identical, the other had the Stereo A and B fader levels different and nothing else (BB-RV-COPIES). A write must go to both.
- PM Editor 7.2.0 loads a file with a channel ON and a channel name written into `EN00` of both copies and recompressed with zlib level 1, and its re-save keeps the write (BB-RV-LOAD).
- Stored scenes keep their own values. A write to the current state does not change a stored scene. A write into a stored scene holds through a recall in PM Editor (BB-RV-SCENE).
- Scene number, scene title, focus and fade flags, channel names and ON keys, and channel EQ and plug-in library recalls written into a show all loaded in PM Editor, and its re-save kept every write (BB-RV-BUILD).
- User Defined Key labels live in the setup section (BB-RV-UDK). A write of them is not load-tested.
- Genius.lab macros are a single-byte XOR over JSON (BB-RV-MACRO). See FORMAT.md 4.10.
- Levels are signed 16-bit in 0.01 dB, -32768 = -inf, as on DM7 (BB-RV-LOAD).
- PM Editor's selective scene load leaves the scenes that are not in the load in place (BB-RV-SELLOAD).
- RIVAGE PM Editor 7.2 controlled saves (markcarlberg, pull request #2) placed: the tap point codes (30 to 120, no 200 or 210); `HPF[2]` and `LPF[2]` as the A/B banks that follow `PEQ.Select`; `TheatreSelect` as Theatre mode's A to D choice; dynamics `TypeNo` 6 FET LIMITER and 7 DIODE BRIDGE with their settings in `Parameter[k]`; the insert send code; Premium Rack slot codes; MONITOR and CUE output codes; cue `Out.Mode`; `CueButton` assigns; custom fader `Course[0]` = bay R; cue and monitor master `ChID` kinds; `VirtualSC.Safe` and `MasterOn`; TWINLANe `Permission` and `On` set by PULL then APPLY (`references/rivage-fields.md`).
- Two editor blanks that differ only in engine differ only in `Status_2` `EN00/pp` and the save id (controlled save).
- A DSP-RX file can carry Premium Rack mounts in racks 25 to 32, left by a DSP-RX-EX session (save).
- With PM7 remembered, RIVAGE PM Editor still uses the last DSP picked, so a PM7 file can carry another engine's counts; a new offline session restores the previous session's state (editor test).
- REV-X REV TIME, INI. DLY and filter words; SP2016, Y7, SPX Reverb and SPX Stereo Delay words; MBC4, DynamicEQ4 and DynamicEQ6 words were pinned by controlled saves (`references/premium-rack.md`).

## What we don't know

- Every value in the file: refused until a reader for its sections exists.
- Channels, patch, processing and scenes: nothing on this model line is decoded.
- Real RIVAGE PM shows: the docs name only a new editor session.
- Which of `CurrentParam_1` and `_2` a console load uses when they differ.
- What `EN01` holds on a system that runs two engines.
- Whether a scene's FILTER sections are the focus mask, the fade mask or both. Both flags changed in the same test.
- The `RIO` and `CSIO` `proc` sections in the current state: not read. They may hold stage box head amps.
- Scene sections `BAP`, `CAP` to `CXP`, `HAP` and `HBP`: not mapped.
- Sends, dynamics, output patch, and mix and matrix bus settings: not mapped.
- A written file loaded on a console: not tested. Only PM Editor has loaded these files.
- Firmware other than V7.20, and PM3, PM7 and PM10 files.
- Scene sections `BAP`, `CAP` to `CXP`, `HAP`, `HBP`: a contributor reading (pull request #2) maps `BAP` to engine I/O, `CAP` to `CLP` to `RIO000` to `RIO011`, `CMP` to `CXP` to `RIO100` to `RIO111`, and `HAP` and `HBP` to the surface units, by schema. Not tested by a recall.
- Genius.lab macro keys: a contributor reading names an `Automation` root and step keys `Category`, `FunctionCategory`, `FunctionElements`, `Parameters`, `Value`; FORMAT.md 4.10 names `Macro` items with `Trigger`, `Condition` and `Action` atoms carrying `Logic`, `Comparison`, `Assignment`. The two readings are not compared on one file.
- `CurrentParam_1` in an editor-made DSP-R10 file: a contributor reading says it is a full-size factory state the editor never brings into step, and suggests reading `_2`. Which copy a console uses is still open, so a write still goes to both.
- The I/O rack input patch code `402 nn` with index 32 + card slot x 16 + port: an unconfirmed reading (1,356 of 1,381 rack inputs land on mic-card slots; indexes below 32 never seen). The second TWINLANe network's sub-code.
- I/O rack UnitIDs 0x201 and 0x202 for M1 and M2 in `Status_2`: unconfirmed.
- Output port `Delay.Time` units (unconfirmed reading: µs). Which strip point the `03C 28` recording feed leaves from.
- Where the +48V master lives: `Unit.48VMaster` is 0 in every file, condenser shows included.
- Ducking's `TypeNo`; which `Type` texts LEGACY COMP and COMP260 are; whether DYN1 offers FET or Diode; the order of a Diode Bridge's recovery and gain words.
- Where Theatre banks C and D keep their contents, and where UNIT MODE is stored.
- What a mirrored engine looks like (no editor save can make one).
- Where Dugan channels 3 to 32 are back-patched; monitor sources `058 00` and `050 00`; oscillator sine mode words (no file holds one).
- Whether DSP-R10 and PM7 schemas run 24 or 32 racks; whether the editor recomputes the resource meter on load.
- The PM7 counts: one console save says 144 / 60 / 36, one PM7 editor blank says 144 / 72 / 36 (that blank was made with a remembered DSP-R10 choice).
- The `.PM10ALL` engine (144 inputs suggests DSP-R10); local I/O counts per surface model.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-10-29, V7.20, a channel ON and name written into the current state of a real PM5 show loaded in PM Editor 7.2.0; the re-save kept the write.
- 2026-10-29, V7.20, a write into a stored scene held through a recall in PM Editor.
- 2026-10-29, V7.20, scene renumber and rename, focus and fade off, names, channel EQ and plug-in library recalls and channel ON in one file loaded in PM Editor; the re-save kept every write and left every scene file byte for byte.
- 2026-10-30, V7.20, two real PM5 shows walk and rebuild byte for byte; every compressed section is a full MMSXLIT section with a matching schema MD5.
- 2026-10-30, V7.20, `CurrentParam_1` and `_2` differ in one console save (Stereo fader levels).
- 2026-10-29, V7.20, markcarlberg's controlled saves in RIVAGE PM Editor 7.2 mapped tap points, A/B and Theatre banks, dynamics type numbers, insert and rack codes (`references/rivage-fields.md`).
- 2026-10-30, V7.20, markcarlberg's controlled saves pinned DynamicEQ6, SP2016, Y7, SPX and MBC4 words (`references/premium-rack.md`).
