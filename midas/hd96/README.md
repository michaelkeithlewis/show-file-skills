# Midas HD96

Notes on the Midas HD96 show file (`.show`), worked out with HD96 Edit 2.4.2 on a macOS offline editor
(console software 2.4.1). A show is a compressed text file. The Midas M32 is a different line and is covered
in [`behringer/x32`](../../behringer/x32/README.md).

This folder is documentation only. There is no HD96 reader or writer in this repo.

## Safety

The format is not documented by Midas. Never load a generated show straight into a console. Open it in HD96 Edit,
check it, save it from the editor, and load only that save. Do the first load at prep, never at the show.

## What we know

- Saving the show alone did not store channel names or processing. They reached the file only after the editor's Master scene was stored and the show saved (HD96 Edit 2.4.2, 2026-10-12).
- Four channel names, then a high-pass filter, one EQ band, and a compressor threshold and ratio on channel 1, each moved the saved show when changed by one step at a time (HD96 Edit 2.4.2, 2026-10-12).
- After quitting and relaunching the editor, a reopened show held the same names and channel 1 values (HD96 Edit 2.4.2, 2026-10-12).
- Colour, fader level, gate on, compressor on, high-pass on and off, EQ on and off, and band shapes each changed the saved show when set (HD96 Edit 2.4.2, 2026-10-20).
- The editor does not store channel mute offline. Four mute controls were tried and the saved show did not change (HD96 Edit 2.4.2, 2026-10-14).
- Adding a channel to a mute group does change the saved show, so membership can be saved while the muted state cannot (HD96 Edit 2.4.2, 2026-10-14).
- A new HD96 show written by a generated file loaded in the editor through its File, Export route and read back with the names in place. The editor needs its Automation setting on and a go to scene 1 first (HD96 Edit 2.4.2, 2026-10-14 and 2026-10-15).

## What we don't know

- Whether a console loads a generated show. Nothing here ran on a console.
- The units of the EQ width control. The editor shows a width value, and octaves is a guess (2026-10-12).
- The exact steps of the editor's knobs. A requested 250 Hz and -4.0 dB could not be set by mouse, so 252 Hz and -4.1 dB were used (2026-10-12).
- Mute state. Offline it cannot be captured, so it is not written (2026-10-14).
- HD96 consoles other than the 24-input model named in the saved show.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-10-12, HD96 Edit 2.4.2, one-change saves of names, high-pass, EQ and compressor; names and values survived a relaunch.

2026-10-14, HD96 Edit 2.4.2, mute cannot be saved offline; mute group membership can.

2026-10-20, HD96 Edit 2.4.2, colour, fader, gate, compressor on and off, high-pass and EQ on and off, and band shapes saved.

## Credits

Full list of contributors: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
