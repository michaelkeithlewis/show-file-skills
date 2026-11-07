# Soundcraft Si

Notes on Soundcraft Si Expression shows (`.ssh`), worked out with Si Offline Expression 2.2 (build 1) on a
Windows offline editor. A show is a text file that carries compressed parts. Impact and Performer were not
tested.

This folder is documentation only. There is no Si reader or writer in this repo.

## Safety

The format is not documented by Soundcraft. Never load a generated show straight into a console. Open it in the
offline editor, check it, save it from the editor, and load only that save. Do the first load at prep, never at
the show.

## What we know

- Four channel names set in the editor changed the saved show, and the names read back on the input setup pages (Si Offline Expression 2.2, 2026-10-12).
- High-pass filter on, EQ on, one EQ band, compressor on, threshold and ratio on channel 1 each moved the saved show after a one-change save (Si Offline Expression 2.2, 2026-10-12).
- Control sweeps from minimum to maximum matched the retail spec at both ends for EQ frequency, gain and width, and for compressor threshold and ratio (Si Offline Expression 2.2, 2026-10-12).
- The editor opened a show written outside it, re-saved it, and the re-saved file held the written names and channel 1 values (Si Offline Expression 2.2, 2026-10-12).
- The editor shows no numeric values, so a value is proven by the editor's own re-save, not by eye (Si Offline Expression 2.2, 2026-10-12).
- A new Si Expression show written by a generated file loaded in the editor, and the plot name appeared as the show name (Si Offline Expression 2.2, 2026-10-14).

## What we don't know

- The lowest high-pass frequency. The editor's knob floor reads 40 Hz and the retail spec says 22 Hz. Unresolved because the editor has no readout (2026-10-12).
- Whether the high-frequency EQ band and the second mid band width are written. They were not measured (2026-10-12).
- One extra value in the filter section moved when a dynamics knob was dragged in the alternate layout. Not identified (2026-10-12).
- Reopening by name: the reloaded surface screens were unclear, so reopen is partly proven (2026-10-12).
- Whether a console loads a generated show. Nothing here ran on a console.
- Si Impact, Si Performer and the other Si models: no editor test.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-10-12, Si Offline Expression 2.2, names and channel 1 processing saved by one-change saves; sweeps checked the ranges.

2026-10-14, Si Offline Expression 2.2, a generated Expression show loaded and showed the plot name as the show name.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.

Full list of contributors: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
