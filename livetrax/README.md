# livetrax: LiveTrax 3 record templates

A Claude Code skill and two Python scripts for LiveTrax 3, the live multitrack recorder
built on Ardour. You write the track list as a CSV. The script builds a LiveTrax template
with track names, record inputs, direct outs for virtual soundcheck, arm, mute, colours,
Master feeds and the hardware patch for every audio device you name.

## What is in the folder

- `SKILL.md`: the skill. Claude Code loads it when you ask for a LiveTrax template.
- `scripts/lt_template.py`: base template + CSV to a new template.
- `scripts/lt_dump.py`: print a session's devices and track list, or write it back out as a CSV.
- `references/FORMAT.md`: the session XML notes (routes, ports, per-device connections, direct outs).
- `examples/tracks.csv`: a made-up 18-track band.

## Requirements

- Python 3.9 or later. No other packages.
- LiveTrax 3 and one template or session that LiveTrax saved (the base). No base ships
  with this folder. Make one in LiveTrax with at least one mono track and save it as a template.

## Quick start

```
python3 scripts/lt_dump.py "My Base.template"
python3 scripts/lt_template.py "My Base.template" examples/tracks.csv "Demo.template" \
    --name "Demo" --device "Dante Virtual Soundcard" --master-out 31-32
python3 scripts/lt_dump.py "Demo.template"
```

Copy `Demo.template` to `~/Library/Preferences/LiveTrax3/templates/Demo/Demo.template` and
open it in LiveTrax.

To install as a skill, copy this folder to `~/.claude/skills/livetrax-template/`.

## Status

- Proven: the XML structure matches what LiveTrax 3.0-5 writes, and the output round-trips
  through `lt_dump.py`.
- Not yet proven: that a generated template opens in LiveTrax with the patch in place.
  Open it, check it, and save it from LiveTrax before you rely on it.
- Known limit: a CoreAudio device name that is not listed opens unpatched.
- Not covered: plugins, buses other than Master, markers, LiveTrax 1 templates.
- Verified for this release: `python3 -m py_compile` and `--help` on both scripts, and a
  round trip with `examples/tracks.csv` (CSV to template with a private base, then
  `lt_dump.py --csv` back to an identical CSV).

This tool is not affiliated with or endorsed by the makers of LiveTrax or Ardour. No warranty.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack planning app for touring and production crews.
