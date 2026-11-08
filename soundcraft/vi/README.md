# Soundcraft Vi

Notes on Soundcraft Vi1000 shows, worked out with Soundcraft Virtual Vi 6.4.8 running as a Vi1000 on a Windows
offline editor. A show is a folder of several files, and the editor keeps backups of its main files.

This folder is documentation only. There is no Vi reader or writer in this repo.

## Safety

The format is not documented by Soundcraft. Never load a generated show straight into a console. Open it in
Virtual Vi, check it, save it from the editor, and load only that save. Do the first load at prep, never at the
show.

## What we know

- A show appears in Virtual Vi's list only when the whole factory folder is present. A route that shipped only some of the files did not load (Virtual Vi 6.4.8, 2026-10-13).
- Four channel names set in the editor changed the saved show. A name of a different length moves everything after it, so names cannot be edited in place (Virtual Vi 6.4.8, 2026-10-12).
- Channel 1 low cut, one EQ band and compressor threshold and ratio each changed the saved show after a one-change save (Virtual Vi 6.4.8, 2026-10-12).
- After a full machine reboot and relaunch, a reloaded show held the same values on the input, EQ and dynamics screens (Virtual Vi 6.4.8, 2026-10-12).
- A show folder written by a generated file loaded in Virtual Vi and was saved by it. The editor's saved files were identical to the written ones (Virtual Vi 6.4.8, 2026-10-14).
- A Vi1000 show folder with the whole factory set is listed and loads, with its names confirmed (Virtual Vi 6.4.8, 2026-10-14).

## What we don't know

- The low cut could only be set to 82 Hz, not 80 Hz, because the editor's encoder stepped from 78 to 82 (2026-10-12).
- One global filter file changes when a channel is renamed. A written show leaves it out, and the editor still loads and saves it. Its content is not understood (2026-10-12).
- Vi1, Vi2, Vi4, Vi6 and Vi7000: no editor test. Only the Vi1000 is covered.
- Whether a console loads a generated show. Nothing here ran on a console.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-10-12, Virtual Vi 6.4.8, names and channel 1 processing saved by one-change saves; values survived a reboot.

2026-10-13, Virtual Vi 6.4.8, a partial show folder was not listed; the whole folder is needed.

2026-10-14, Virtual Vi 6.4.8, a written show loaded and re-saved identically.

## Credits

Full list of contributors: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
