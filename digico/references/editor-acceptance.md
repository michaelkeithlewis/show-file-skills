# What the editor accepts

What the DiGiCo offline editors do with a generated session. One fact per line, each ending with its proof: editor and version, console if hardware, date. "Version not recorded" means the session did not write the version down. A generated session is a file written by a tool, not saved by the editor. Format details are in `FORMAT.md`.

## What loads

- The Quantum 225 offline editor loaded a Quantum 225 session built from a factory session that the Quantum 225 editor itself saved. (Quantum 225 offline editor 21.0.2126, 2026-10-18)
- The Quantum 112 offline editor loaded a generated Quantum 112 session. (Quantum 112 offline editor, version not recorded, 2026-10-18)
- Sessions saved by the SD7, SD8, SD9, SD10 and SD11 offline editors (11, 4, 10, 10 and 79 files) re-export byte-identical when nothing is edited. (each model's own offline editor, versions not recorded, 2026-10-18)
- An SD12 factory session, saved on a real desk, re-exports byte-identical. (SD12 desk save, 2026-08-14)
- A real Quantum 112 show re-exports byte-identical. (Quantum 112 show file, byte compare, 2026-08-14)
- Single-toggle SD7 and SD9 captures each decode with exactly the one module the desk switched, and the matching default captures decode with none. (desk-written SD7 and SD9 captures, date not recorded)

## What is silently dropped

- A name written to a DiGiCo stereo pair is one name for one strip. Collapsing two differently named strips into a pair drops the second name from the file. (generated session read back, no editor load, 2026-09-01)

## What is refused

- The Quantum 225 offline editor greyed out, and would not open, a session that was a Quantum 112 session under a Quantum 225 name. The Quantum 112 editor opens the same file. It is inferred, not tested, that other models behave the same way. (Quantum 225 offline editor 21.0.2126, 2026-10-18)
- That refusal ended once the session came from the Quantum 225 editor's own factory session. A matching export is not an accepted export until the target editor says so. (Quantum 225 offline editor 21.0.2126, 2026-10-18)

## Name and character limits

- An SD8 session stores channel names in the form "number, colon, name". A display that hides the number must compare stored names with stored names, or an untouched session looks renamed on every channel. (desk-written SD8 session, 2026-08-14)

## Empty and partial files

- No behaviour of an empty or partial session in a DiGiCo editor is recorded in the sources for this file.

## Version and firmware notes

- Quantum 338, 7 and 852 sessions are built from the SD7 and SD10 factory sessions. No load in their own editors is recorded, so their status is unknown. (no editor load recorded, as of 2026-10-18)
- Real DiGiCo sessions seen in testing reach 53 MB and 82 MB. (desk-written sessions, size check, 2026-08-14)
