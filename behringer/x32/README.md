# X32 / M32 scenes

Notes on Behringer X32 and Midas M32 scene files (`.scn`, firmware 2.x to 4.13). An X32 scene is a text file of
OSC-style paths with positional tokens. This folder is documentation only: there is no reader or writer yet.

The notes were contributed by markcarlberg. Most of them are desk research (the unofficial X32/M32 OSC Remote
Protocol document, Behringer's quick start guide and X32 RACK manual) checked against real scene files. Only a
few facts were moved by a single save. `references/FORMAT.md` labels each line with its source.

## What is documented

| File | Content |
|---|---|
| `references/FORMAT.md` | Container, value grids and spellings, strip paths, enumerations, routing and head amps, outputs, desk-wide nodes, effects, firmware line sets, what X32-Edit writes |

## Safety

The format is not documented by Behringer. Never load a generated scene straight into a desk. Open it in
X32-Edit, check it, save it from X32-Edit, and load only that save. Do the first load at prep, never at the show.

## What we know

- Membership bitfields (`%` then bits, as in `/ch/NN/grp`) read with the rightmost character as group 1, for
  DCAs and mute groups. Proven by a save.
- `/config/solo`: the solo follows select and select follows solo switches, monitor level, mute and PFL dim
  sit at the token positions in `references/FORMAT.md`. Proven by X32-Edit saves.
- `/config/talk/A` and `/B` order their first three tokens level, dim, latch, not the level, latch, dim of the
  protocol doc. Proven by X32-Edit saves.
- Node token positions that held a non-default value in a firmware 4.0 export are proven by that save.
- The contents of the X32-Edit 4.x "Initialize Settings > Mixer" scene (`references/FORMAT.md`, "What X32-Edit
  writes"). Proven by the editor save.

## From the protocol doc and the manual

These come from published documents and are consistent with real scenes, but no single save moved them.

- The value grids and spellings for frequency, Q, gain, fader, send, pan, trim and dynamics times.
- The scene node list. Real files match it except the `/-stat/*` lines and `grp` on matrices and mains.
- The X32 quick start guide says an insert on a bus, main or matrix swaps between pre-EQ and post-EQ.
- FX 1-4 parameter order follows the parser published with the protocol doc.

## What we don't know

- Head amp gain step: 0.5 dB or 0.1 dB. A +22.5 dB value in a file rules out 1 dB.
- Older exports may store the ratio as an index into the ratio list. Not seen yet.
- `/config/solo` token 12 (delay on) is placed by order, not by a save.
- Whether GRP ignores the stored send level and pan, and whether it follows the strip pan into a linked pair.
  Not measured on a desk.
- The unit of the DLY offset (read as ms).
- Whether a 2.x or 3.x desk loads a `#4.0#` scene or `AUX/CR` and `AUX/TB` blocks, and whether 4.00-4.05 ignore
  the 4.06 `grp` lines.
- Where the gate and compressor sit relative to a channel insert at PRE and POST.
- `AUXn` inserts as Aux Out n / Aux In n loops: from the manual, no file uses one.
- Parameter order of ENH/ENH2, P1A/P1A2 and PQ5/PQ5S.
- Whether a forum report that a 4.x update wipes stored scenes, snippets and libraries is true.
- No 1.x scene and no `.shw` or `.snp` file has been examined.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.

Cross-desk format notes in this folder are by [markcarlberg](https://github.com/markcarlberg). Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
