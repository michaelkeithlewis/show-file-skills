---
name: livetrax-template
description: Build and read LiveTrax 3 (Ardour-based live multitrack recorder) session templates as Ardour XML - track names, record inputs, direct outs for virtual soundcheck, arm, mute, colour, Master feeds, and the per-device port patch - from a simple CSV track list, without clicking through LiveTrax. Trigger on "LiveTrax", "Trax Live", "record template", "multitrack template", "virtual soundcheck template", "build the record session from the input list", ".template", or ".ardour" from LiveTrax. NOT for Waves Tracks Live, Pro Tools, or Reaper.
---

# LiveTrax 3 templates

LiveTrax 3 stores sessions and templates as Ardour XML (Session version 7003). The
generator clones the Master bus and one mono track from a base template that LiveTrax
saved, then rebuilds the track list from a CSV. Format notes: `references/FORMAT.md`.
Requires Python 3.9 or later and nothing else.

## Safety rules

1. The base must be a file that LiveTrax itself saved, with a Master bus and at least one
   mono track. Never hand-write a base.
2. Write the output to a new file. Never overwrite the base.
3. Open the output in LiveTrax, check the patch on the real interface, and save it from
   LiveTrax before the show.

## Commands

```
python3 scripts/lt_dump.py BASE.template                       # devices + track list
python3 scripts/lt_dump.py SESSION.ardour --csv tracks.csv     # turn a session into a CSV
python3 scripts/lt_template.py BASE.template tracks.csv OUT.template --name "Show" \
    --device "Dante Virtual Soundcard" --device "<other interface>" [--master-out 31-32]
```

CSV columns (see `examples/tracks.csv`): `name` (unique, no `/`), `inputs` (`5` or `57-58`),
`playback` (direct-out channels, blank = none), `arm` (default 1), `color` (hex RRGGBB),
`master` (1 = feed Master), `mute`.

## New template (the recipe)

1. Run `lt_dump.py` on any session saved on the record machine. Copy the exact device
   names it prints.
2. Write the CSV from the input list. A common layout: track N records input N and its
   direct out goes to output N for virtual soundcheck. Two-mix tracks get `master=1` and no
   direct out.
3. Run `lt_template.py` with every device the template may open on (`--device` repeats).
4. Run `lt_dump.py` on the output and compare it to the CSV.
5. Copy the output to `~/Library/Preferences/LiveTrax3/templates/<Name>/<Name>.template` on the
   Mac (folder name = file name), open it in LiveTrax, check, save.

## Gotchas

- Port connections are stored per CoreAudio device name. A device that is not listed opens
  with every track unpatched. The name must match exactly.
- Colours are RGBA packed into one integer. The CSV takes plain hex RRGGBB.
- Stereo tracks get a Stereo Balance panner on the direct out. Mono tracks keep the default.
- GUI window state from the base is dropped on purpose. LiveTrax rebuilds it.
