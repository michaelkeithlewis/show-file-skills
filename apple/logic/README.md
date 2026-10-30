# logic: Logic Pro ProjectData strips, plugin latency and alignment

A Claude Code skill and tools for the binary `ProjectData` file inside a Logic Pro
project. They list channel strips, routing and insert plugins without opening Logic,
measure the real latency of every AU insert from its saved state, add up the latency of
every path to the main mix, and patch Apple's AUSampleDelay into the short paths so
everything lines up. The use case is a live stream or broadcast mix run through Logic,
where uneven plugin latency smears the drums and vocals.

## What is in the folder

- `SKILL.md`: the skill. Claude Code loads it when you ask about a Logic project.
- `scripts/logic_pd.py`: `strips`, `extract`, `paths`, `plan`, `add-delay`.
- `scripts/aulat.swift`: macOS AU host that reports each plugin instance's latency.
- `references/PROJECTDATA.md`: the format notes (header, chunk chain, strip and insert
  layouts, AU state, AUSampleDelay state, how to measure latency).
- `examples/make_test_projectdata.py`, `examples/lat.txt`, `examples/plan.json`: a synthetic
  three-strip project and its matching latency file and plan, for a test run without Logic.

## Requirements

- Python 3.8 or later. No other packages.
- For latency measurement: a Mac with the plugins installed and `swiftc` (Xcode command line tools).
- Logic Pro, to open and check the patched project. No projects ship with this folder.

## Quick start

```
cp -R "My Template.logicx" "My Template aligned.logicx"
PD="My Template aligned.logicx/Alternatives/000/ProjectData"
python3 scripts/logic_pd.py strips "$PD"
python3 scripts/logic_pd.py extract "$PD" plists
swiftc -O scripts/aulat.swift -o aulat && ./aulat plists > lat.txt     # on the Mac, in Terminal
python3 scripts/logic_pd.py paths "$PD" --lat lat.txt --json paths.json
python3 scripts/logic_pd.py plan paths.json --json plan.json
python3 scripts/logic_pd.py add-delay "$PD" ProjectData.new plan.json
python3 scripts/logic_pd.py strips ProjectData.new
mv ProjectData.new "$PD"
```

Then open the copy in Logic and check each changed strip.

To install as a skill, copy this folder to `~/.claude/skills/logic-projectdata/`.

## Status

- Proven on one real Logic 12.4 template: strips, names, routing and inserts read
  correctly, every AU's latency was measured from its saved state, and the delay plan was
  computed from the routing graph.
- Less proven: `add-delay` was used on that one project. Check every patched project in
  Logic (and in its autosave, see the notes) before you trust it.
- Not covered: regions, automation, sends, native-plugin latency, sample rates other than
  48 kHz in `aulat.swift`.
- Verified for this release: `python3 -m py_compile` and `--help`, and the full chain on the
  synthetic project (`strips`, `extract`, `paths`, `plan`, `add-delay`, then `strips` and
  `extract` on the output to confirm the AUSampleDelay insert and its 492-sample setting).
  `aulat.swift` was not rebuilt for this release.

This tool is not affiliated with or endorsed by Apple. Logic Pro is a trademark of Apple Inc.
No warranty.

## Remote control through Accessibility (bounce without looking)

`scripts/logic_ax.lua` drives Logic through the macOS Accessibility tree from Hammerspoon: dump any window, press
menu items by path, read insert bypass states, and bounce a bar range to a named file
(`L.bounce{name=, s={bar,beat}, e={bar,beat}, dry=}`). `scripts/hs_run.sh <job.lua>` runs a job without waiting
on the `hs` CLI, which can hang; set `HS_HOST=user@mac` to run it on another Mac over SSH. Example job:
`examples/bounce_job.lua`. `scripts/locate_clip.py <source.wav> <clip.wav>` finds where a bounce sits in a longer
file and the gain between them, so you can check a plug-in state without listening. Needs Hammerspoon with
Accessibility permission; `locate_clip.py` needs ffmpeg and numpy. The rules behind it are in
`../macos-accessibility/README.md`.

Status: the bounce, insert-state and plug-in window code ran on a real project in Logic Pro on macOS in October
2026. The generic version in this repo has passed a Lua syntax check but has not been re-run in Logic.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack planning app for touring and production crews.
