# What the editor accepts

What the Yamaha offline editors do with a generated show. One fact per line, each ending with its proof: editor and version, console if hardware, date. "Version not recorded" means the session did not write the version down. A generated show is a file written by a tool, not saved by the editor. Format details are in `FORMAT.md`.

## What loads

- DM3 Editor 3.0.0 opened fresh standard-strip exports and same-format channel relocation exports with no format error. (DM3 Editor 3.0.0, 2026-07-29)
- DM3 Editor loaded a round trip of a default session and rendered the full processing. (DM3 Editor, version not recorded, 2026-08-23)
- DM7 Editor loaded an export with channel 1 renamed and coloured cyan and channel 2 renamed and coloured orange. Names and colours rendered exactly. (DM7 Editor, version not recorded, 2026-08-23)
- DM7 Editor V1.7.5 loaded a session with channel 1 renamed and showed the new name, with channels 2 and 3 unchanged and the icon and colour at their defaults. (DM7 Editor V1.7.5, 2026-08-03)
- The DM5 and DM5 Compact exports were accepted in a recorded editor run. (DM5 Editor, version not recorded, 2026-10-19)
- RIVAGE PM Editor loaded a file whose channel 1 was renamed KICK. The surface showed KICK on the factory defaults and reported "Finished loading file". It then loaded a generated file, and the surface showed IN1 to IN144. (RIVAGE PM Editor, version not recorded, 2026-08-23)
- PM3, PM5, PM7 and PM10 exports were accepted in a recorded editor run. (RIVAGE PM Editor, version not recorded, 2026-10-18)
- TF1, TF3, TF5 and TF Rack files saved by TF Editor came back byte-identical through a read and write with no edit (14 files per model). No TF Editor load of a generated export is on file. (TF Editor, version not recorded, 2026-10-18)

## What is silently dropped

- A DM7 file whose mix-bus names were not written opens with the factory names Mix 1 to Mix 8, not the engineer's bus names. (DM7 Editor, version not recorded, found by opening a real show, 2026-09-01)
- Colours translated onto a CL or QL from another desk came out wrong in CL Editor when the palette was wrong. Purple and green were swapped, white showed as blue and yellow as cyan. Only red held. Names and values were right. (CL Editor, version not recorded, 2026-09-01)
- The CL palette read back from CL Editor holds off, purple, cyan, red, green and blue. Yellow, orange, pink and white have not been seen in a CL file. (CL Editor, version not recorded, 2026-09-01)
- On a real CL1, 48V can be held back on recall by the desk's recall-safe settings, even when the file says on. The file is not the whole answer. (CL1 console, 2026-08-04)
- The CL and QL editors store a placeholder name in a fixed four-character form such as "ch10". A tool that writes the spaced display form "ch 10" changes the file. (desk-written CL5 file, date not recorded)
- A re-save of an unedited factory session in the vendor editor changes 95.6% of the file's bytes. A tool that touches 30% is closer to the original than the editor. (DM3, DM7 and RIVAGE sessions, byte compare, 2026-08-14)

## What is refused

- No Yamaha editor refusal of a generated show is recorded in the sources for this file.

## Name and character limits

- CL and QL names are 8 characters. (desk-written CL5 file read, 6 of 6 names correct, 2026-09-03)

## Empty and partial files

- The DM7 factory session has channel 1 EQ on, high-pass off, gate and compressor off, fader at minus infinity, colour blue and icon blank. (DM7 Editor V1.7.5, full DM7 selected, 2026-08-03)
- Offline DM7 Editor does not respond to the +48V and phase buttons. They probably address a head amp that is not there (inferred). 48V and phase cannot be set or captured offline. (DM7 Editor V1.7.5, 2026-08-03)
- A re-save of the same DM7 factory session twice gives two files that differ in about 95% of their bytes, so a byte compare of two saves proves nothing. (DM7 Editor V1.7.5, 2026-08-03)
- In the DM7 editor, the DYN1 and DYN2 switches work only in the expanded view. The compact panel label is a link, not a switch. (DM7 Editor V1.7.5, 2026-08-03)
- TF Editor saves a .tff file by every save path tried, including the scene manager's Extract. It produced no .tfp or .tfs file in three attempts. (TF Editor V4.5.0, TF3 model, 2026-09-29)

## Version and firmware notes

- RIVAGE channel capacity follows the DSP engine: 144 on DSP-R10 and CSD-R7, 120 on DSP-RX and 288 on DSP-RX-EX. The editor's PM7 factory file holds 144 records. (RIVAGE PM Editor, version not recorded, 2026-10-17)
- PM3, PM5 and PM10 exports are DSP-R10 systems and PM7 is CSD-R7, each from the editor's own factory file. A DSP-RX or RX-EX show exports back into one of those. (RIVAGE PM Editor, version not recorded, 2026-10-17)
- The DM7 editor's file-open sheet remembers the previous folder. A scripted load that does not set the folder reloads the old file and looks like a failed load. (DM7 Editor, version not recorded, 2026-08-23)
- The DM7 editor keeps the last saved file name in its window title. A title is not evidence that a load worked. Check the channel list. The bay windows repaint after several seconds. (DM7 Editor V1.7.5, 2026-08-03)
- The RIVAGE PM Editor file-loading flow is owned by one bay window. Clicks go to a sibling bay window unless that window is raised first. (RIVAGE PM Editor, version not recorded, 2026-08-23)
