# What the editor accepts

What WING-Edit does with a generated snapshot. One fact per line, each ending with its proof: editor and version, console if hardware, date. "Version not recorded" means the session did not write the version down. A generated snapshot is a file written by a tool, not saved by the editor. Format details are in `FORMAT.md`.

## What loads

- WING-Edit accepted generated WING snapshots in a recorded acceptance run. (WING-Edit, version not recorded, 2026-10-15)
- A freshly generated 8-channel snapshot loaded. Gate and compressor lit on exactly channels 1 to 8, and 48V showed on exactly channels 4 to 6. (WING-Edit, version not recorded, 2026-08-23)
- A no-edit round trip of a desk-written snapshot differs from the original in formatting and whitespace only. All 34,704 values compared equal. (desk-written snapshot, value compare, 2026-08-14)
- A physical WING has not loaded a generated snapshot. The editor accepts the files, and the console is untested. (no console load recorded in the 2026-10-18 acceptance record)

## What is silently dropped

- When one stereo Source sits on an adjacent odd and even pair, WING-Edit shows that Source's single name on both strips. Both typed names stay in the file, so the editor shows one name where the file holds two. (WING-Edit, version not recorded, 2026-10-18)
- A snapshot that uses a premium EQ or dynamics model holds those settings in a different schema from the standard modules. A writer that does not know the model must leave that part untouched and must not show it as a standard module. (desk-written snapshots, file read, date not recorded)
- A round trip of a factory-default snapshot is a valid file that shows nothing authored. A reader that only imports named channels returns an empty list for it, and that is not a fault in the file. (WING-Edit, version not recorded, 2026-08-23)

## What is refused

- No WING-Edit refusal of a generated snapshot is recorded in the sources for this file.

## Name and character limits

- No name limit has been measured from a generated snapshot in these sources.

## Empty and partial files

- A factory-default snapshot loads cleanly and has no named channels. (WING-Edit, version not recorded, 2026-08-23)

## Version and firmware notes

