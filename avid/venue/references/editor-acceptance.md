# What the editor accepts

What VENUE Standalone does with a generated S6L show. One fact per line, each ending with its proof: editor and version, console if hardware, date. "Version not recorded" means the session did not write the version down. A generated show is a file written by a tool, not saved by VENUE. Format details are in `S6L-FORMAT.md`.

## What loads

- A generated S6L show was accepted in a recorded editor run. (VENUE Standalone, version not recorded, 2026-10-18)
- A generated show passed a check on VENUE Standalone on the tree certified for release. (VENUE Standalone, version not recorded, 2026-08-31)
- A no-edit round trip of a desk-written S6L show comes back byte-identical. A sweep of 86 desk-written shows found a stereo link in exactly two of them. (desk-written shows, byte compare, 2026-08-14)
- Module on/off for HPF, EQ, gate and compressor was written and read back, in both states, against single-toggle captures from a real desk. (desk-written S6L captures, no editor load, date not recorded)

## What is silently dropped

- On an S6L, 48V belongs to the input socket, not the channel. Switching 48V on a channel moves nothing in any channel strip, so a tool cannot write channel phantom into a strip. (desk-written pair with and without 48V, byte compare, date not recorded)
- A writer that sets an aux strip label from a field that holds no label writes an empty string over the desk's own label and the label is lost. One aux name was lost per mix created. (desk-written show with 64 busses and monitors, size compare, 2026-09-01)
- Linking two channels renumbers the input of every strip after the pair. A link cannot be added to one strip in place. Reading a link works. (desk-written link and unlink transitions, 197 moving blobs counted, date not recorded)
- A show saved with sockets outside the range that was measured (Local Analog, the second half of a 192-channel rig) reads those sockets as unknown and leaves them as they are. (desk-written shows, date not recorded)

## What is refused

- No VENUE refusal of a generated S6L show is recorded in the sources for this file.

## Name and character limits

- No name limit has been measured from a generated show in these sources.

## Empty and partial files

- No S6L strip has an uncoloured state. Across 87 desk-written shows and 15,714 input strips, every strip carries one of eight named colours. A writer that fills a strip with a category colour changes the desk's own colour. (87 desk-written shows, count, date not recorded)

## Version and firmware notes

- Sources record no VENUE firmware version for a generated-show load. The editor runs named in the sources are not tied to a version. (no version recorded, 2026-10-18)
- Classic VENUE and D-Show shows have no behaviour recorded in these sources.
