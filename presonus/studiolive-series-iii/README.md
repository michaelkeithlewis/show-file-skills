# PreSonus StudioLive Series III

Notes on StudioLive Series III project files, worked out with the Universal Control 5.1.1 Offline Editor. The
editor stores a scene and a project file for each model, both binary files (`.scn` and `.cnfg`).

This folder is documentation only. There is no StudioLive reader or writer in this repo.

## Safety

The format is not documented by PreSonus. Never load a generated project straight into a mixer. Open it in the
offline editor, check it, save it from the editor, and load only that save. Do the first load at prep, never at
the show.

## What we know

- The offline editor stored a factory project for each model chosen from its device menu: 16, 16R, 24, 24R, 32, 32R, 32S, 32SX, 32SC, 64S, SE16, SE24 and SE32 (Universal Control 5.1.1, 2026-10-19).
- Those factory saves fall into seven groups. Inside a group the scene and project files are identical once unpacked (Universal Control 5.1.1, 2026-10-19).
- The model number is the preamp count, not the channel count. The 16, 32SC, SE16 and 24 still carry 32 channel lines, and the channels above the preamp count default to a non-analog input (Universal Control 5.1.1, 2026-10-19).
- Rack models (16R, 24R, 32R) save a project with no surface layer and no AES source (Universal Control 5.1.1, 2026-10-19).
- The 64S saves twice the channels and aux sends, no subgroups, and a main mono and master section. The 16R saves half the channels with fewer aux and effects (Universal Control 5.1.1, 2026-10-19).

## What we don't know

- Whether a scene moves between models in a group on a real mixer. This is inferred from the saves, not tested on a mixer.
- Whether a scene moves between groups. Only the channel and bus counts are known to differ, and they would need folding.
- Whether the editor loads a generated project. No load test is on record.
- A mixer load: not tested. Processing values were not compared across the saves.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-10-19, Universal Control 5.1.1, a factory project stored for each model; grouped by comparing the saves.

## Credits

Full list of contributors: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
