# Yamaha CL

Covers CL1, CL3 and CL5. File extension: `.CLF`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads with `show`, `check` and `ports`.
- The same script writes with `rename`, `colour`, `icon`, `fader`, `on`, `hpf`, `patch`, `preamp`, `dca`, `busname` and `apply`.
- Pass `--console cl5`, `cl3` or `cl1` on every command. The file does not record the model.
- On a scene format 7 file, `--all-scenes` also sends names, colours and patch to every stored scene.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 2, 3, 5 and 6. Skill: [`SKILL.md`](../SKILL.md).
- Open every written file in CL Editor and save it there. Load only that save on a console.

## What we know

- A `.CLF` has no model field. One session saved as CL5, CL3 and CL1 gave three byte-identical files (BB-MODEL).
- The data always holds the largest layout: 96 input slots, 24 mixes, 8 matrices, ST L, ST R, MONO, 16 DCAs and 8 mute groups.
- The model sets only how many channels the console shows. Yamaha's published mono input counts are CL5 72, CL3 64 and CL1 48.
- Writes are open on scene formats 5, 6 and 7. The proof is a new CL5 session (format 7) and two real CL shows (formats 5 and 6).
- CL Editor showed each written value. The re-save and CSV export matched 147 items with 0 mismatches each.
- CL Editor 5.8.1 re-saves format 5 and 6 files as format 7, with each value at the same offset (BB-RESAVE).
- CL Editor refuses a file with a wrong checksum: "Checksum error. (-2)" (BB-SUM).
- Head amp writes cover OMNI 1 to 8 only. CL Editor showed every gain from -6 to +50 dB, +60 dB and +66 dB.
- Stored scenes on format 7 take names, colours and patch. A recall showed the written values (BB-SCENE).
- A CSV import needs all nine files, or CL Editor shows one error box per missing file. A header-only file raises no box and changes nothing (FORMAT.md 3.4.1, BB-CSV-3).
- CL Editor 5.8.1 controlled saves placed the input insert, direct out, delay, ATT, gate, comp, EQ and send cells, the mix, matrix, ST and MONO processing and fader cells, and the shared hold and release time ladder (`references/FORMAT.md` 3.8). Read from saves only; no written file has been loaded with them.

## What we don't know

- A console load of a written file: not tested. Only the editor has loaded these files.
- Sends, EQ, dynamics, delay, inserts, the output patch, and mix, matrix and stereo faders, ON keys and bus types: not read.
- Rio and other stage box head amps: not read. `preamp` refuses a channel patched from Dante or a slot.
- Mute group assigns and rack outputs as a patch source: read only.
- DCA assigns on an ST IN: refused.
- Stored scenes on formats 5 and 6, other values in stored scenes, and bus names in stored scenes: refused.
- Stored scene titles in format 6: read, marked `?`.
- The bytes that formats 6 and 7 add: not understood.
- User key files (`.CLU`): refused by design. The files hold the console's user accounts.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-09-19, CL Editor 5.8.1, controlled saves placed input processing, sends and the mix, matrix, ST, MONO and DCA master cells (`references/FORMAT.md` 3.8).
- 2026-09-01, CL Editor (version not recorded), colours translated from another desk showed wrong when the palette was wrong: purple and green swapped, white as blue, yellow as cyan, only red held. The palette read back holds off, purple, cyan, red, green and blue (`references/editor-acceptance.md`).
- 2026-08-04, CL1 console, 48V can be held back on recall by the desk's recall-safe settings even when the file says on.
