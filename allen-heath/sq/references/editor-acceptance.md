# What the editor accepts

What SQ MixPad does with a generated show folder. One fact per line, each ending with its proof: editor and version, console if hardware, date. "Version not recorded" means the session did not write the version down. A generated show is a file written by a tool, not saved by MixPad. Format details are in `FORMAT.md`.

## What loads

- A generated SQ show loaded in SQ MixPad. (SQ MixPad, version not recorded, 2026-10-15)
- A no-edit round trip of a show saved on a physical SQ comes back byte-identical and keeps the show's own scene label. (desk-written show, byte compare, 2026-08-14)
- A generated show passed a check in SQ MixPad on the tree certified for release. (SQ MixPad, version not recorded, 2026-08-31)

## What is silently dropped

- A generated show replaced the scene label an engineer had set with a default name. The label must come from the file that was loaded. (desk-written scene compared after round trip, 2026-08-13)

## What is refused

- No SQ MixPad refusal of a generated show is recorded in the sources for this file.

## Name and character limits

- No name limit has been measured from a generated show in these sources.

## Empty and partial files

- A reorder of an imported show moves each channel's record with it. A reorder of a from-scratch show does nothing, because the template has no strip to move. (physical SQ show capture, no editor load, date not recorded)

## Version and firmware notes
- No generated SQ show has been loaded on a physical SQ. Only MixPad has loaded one. (no console load recorded in the 2026-10-18 acceptance record)
