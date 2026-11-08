# What the editor accepts

What dLive Director does with a generated show archive. One fact per line, each ending with its proof: editor and version, console if hardware, date. "Version not recorded" means the session did not write the version down. A generated archive is a file written by a tool, not saved by Director. Format details are in `format-versions.md` and the other `format-*.md` notes.

## What loads

- Director recalled a re-saved archive and System Status named the show. The exported archive tree was identical to the desk archive: 0 of 184 files differed. (dLive Director V2.12, 2026-08-23)
- A generated archive carrying 48V on a channel loaded on a console surface, and the state came back on re-import. (dLive C3500 surface, Director version not recorded, 2026-07-19)
- A raw desk archive and our re-save of it show the same bare-numbered strips in Director. The two renders were compared as a control. (dLive Director V2.12, 2026-08-23)

## What is silently dropped

- Director shows its previous session when it is launched on a new file. A load that appears to fail or to lose names can be a stale session. Check the show name in System Status before trusting a render. (dLive Director V2.12, 2026-08-23)
- A blank input name slot stores the channel's own number as text. Across 218 archives, 81,111 name slots hold a bare number and 79,560 of them equal their own channel number. (218 desk-written archives, count, 2026-08-24)
- 150 archives, including the all-blank factory default show, hold the number 121 as the name of input 122. A bare number is not always its own channel's number. (218 desk-written archives, count, 2026-08-25)
- A name made only of digits cannot be told apart from the desk's own numbering, so a typed "58" reads back as blank. A name with any other character, such as "na", is a real name and is kept. (218 desk-written archives, count, ruling 2026-08-25; reversible if a typed number is ever shown to be a name)
- A stereo input is stored two ways. One is a gang table inside the scene. The other is an input stereo setting held at archive level, outside every scene. A reader that checks only the gang table dropped four of five stereo pairs of one real show. (desk-written archives, Director V2.12 era, 2026-09-01)
- The factory default show ships its last five input pairs as stereo. Those pairs are scaffolding, not the engineer's choice. (29 controlled archives, count, 2026-09-01)
- A stereo strip shows one name on the first input and a blank on its partner. Treat that as one strip. (desk-written archives, 2026-09-01)
- The factory default show holds socket records for inputs 1 to 64 only. A show of 128 inputs generated with 48V on came back with 64 on and 64 with no phantom data at all. (production export and import of a generated show, 2026-08-24)

## What is refused

- Five of seven real touring archives checked carried a show version older than 14, so a tool that handles only version 14 meets older files often. (desk-written archives, 2026-08-14)
- No Director refusal of a generated archive is recorded in the sources for this file.

## Name and character limits

- No new name limit has been measured from a generated archive in these sources. Show file name limits are in the README session notes.

## Empty and partial files

- Director shows library scenes 18 to 27 of a C1500/DM32 capture with an empty payload. This is harmless: the current scene holds the real edits. (dLive Director, C1500/DM32 capture, 2026-07-14)
- A factory default show has every input name slot blank, with the number scaffolding described above. (controlled default archive, 2026-08-24)
- Per-song scene lists could not be captured in Director offline. The base show exports and the scene list is held. (dLive Director offline, date not recorded)
- Re-saving in Director changes scene archives beyond the edit that was made, so a byte compare of two Director saves shows churn that is not a change. (controlled archives, date not recorded)

## Version and firmware notes

- Controlled archives cover show versions 13 and 14. The wider working set covers versions 6, 11, 12, 13 and 14. (29 controlled and 224 working archives, count, 2026-07-14)
- A C1500/DM32 surface capture was read back for names, colour, high-pass filter, gate and compressor, and each matched the file byte for byte. (dLive C1500/DM32 surface, 2026-07-14)
