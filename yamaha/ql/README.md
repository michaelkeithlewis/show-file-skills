# Yamaha QL

Covers QL1 and QL5. File extension: `.CLF`.

## Tooling

- [`scripts/yamaha_tool.py`](../scripts/yamaha_tool.py) reads with `show`, `check` and `ports`.
- The same script writes with `rename`, `colour`, `icon`, `fader`, `on`, `hpf`, `patch`, `preamp`, `dca`, `busname` and `apply`.
- Pass `--console ql5` or `ql1` on every command. The file does not record the model.
- Format notes: [`references/FORMAT.md`](../references/FORMAT.md), sections 2, 3, 5 and 6. Skill: [`SKILL.md`](../SKILL.md).
- Open every written file in QL Editor and save it there. Load only that save on a console.

## What we know

- A `.CLF` has no model field. QL1 and QL5 saves from QL Editor differ only in the new session's default patch (BB-MODEL).
- The data holds the same largest layout as a CL file. Yamaha's published counts are QL5 64 and QL1 32 mono inputs, and QL 16 mixes.
- Writes are open on scene formats 6 and 7. The proof is a new QL1 session and a real QL show (format 6).
- QL Editor showed each written value: 99 and 131 items, 0 mismatches.
- Head amp writes cover the local inputs: INPUT 1 to 32, and INPUT 1 to 16 on a QL1.
- QL Editor loaded a written QL5 file with gain on all 32 local inputs and +48V on 8. Every value matched (BB-QL).
- Patch codes differ from CL: 65 to 72 are INPUT 1 to 8, and 193 to 216 are INPUT 9 to 32 (BB-CSV-2).
- A patch to FX 3B written into a QL show with another rack set-up came back as NONE (BB-RACK).
- A CSV import needs all nine files, or QL Editor shows one error box per missing file. A header-only file raises no box and changes nothing (FORMAT.md 3.4.1, BB-CSV-3).

## What we don't know

- A console load of a written file: not tested. Only the editor has loaded these files.
- QL files in scene format 5: read only.
- Stored scenes on QL: refused. `--all-scenes` is a CL format 7 write.
- Stored scene titles in format 6: read, marked `?`.
- Sends, EQ, dynamics, delay, inserts and the output patch: not read.
- Mix, matrix and stereo faders, ON keys and bus types: not read.
- Rio and other stage box head amps: not read.
- Mute group assigns and rack outputs as a patch source: read only.
- DCA assigns on an ST IN: refused.
- GEQ as a QL patch source: no test named the code.
- User key files (`.CLU`): refused by design.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
