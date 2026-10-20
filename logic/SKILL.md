---
name: logic-projectdata
description: Read Logic Pro ProjectData (the binary inside a .logicx package) without opening Logic - channel strips, names, inputs, outputs, buses and aux routing, insert slots and AU plugins - measure each AU insert's real latency from its saved state, compute per-path latency to the main mix, and patch AUSampleDelay inserts in to line every path up. Trigger on "Logic", ".logicx", "ProjectData", "plugin latency in my Logic template", "line up the latency", "time-align the live stream mix", "what is on each channel strip", or "add a sample delay to these channels", "bounce bars 17 to 25", "which inserts are bypassed". NOT for Pro Tools, Ableton, or Logic regions and automation.
---

# Logic Pro ProjectData

A Logic project's binary document is `<Song>.logicx/Alternatives/000/ProjectData`: a
24-byte header and a flat chain of chunks. Channel strips are `OCuA` chunks, insert slots
are `UCuA` chunks, and AU inserts carry their state as an XML plist. Format notes:
`references/PROJECTDATA.md`. Python 3.8 or later, nothing else. Measuring latency
needs a Mac with the plugins installed and the Swift compiler (Xcode command line tools).

## Safety rules

1. Copy the whole `.logicx` package first. Work on the copy.
2. `add-delay` writes a new ProjectData. Put it into the copied package in place of the
   original ProjectData only after `strips` shows the expected result.
3. Open the patched copy in Logic and check every changed strip before you use it live.
4. Plugin latency changes with settings. Measure again after you change look-ahead,
   oversampling or quality modes.

## Commands (`python3 scripts/logic_pd.py ...`)

| Command | Does |
|---|---|
| `strips PD [--lat lat.txt]` | strip list: name, input, output, inserts (and latency) |
| `extract PD plists/` | AU ClassInfo plists, one per insert, for `aulat.swift` |
| `paths PD --lat lat.txt [--main-out 73] [--json paths.json]` | latency of every live-input strip to the main out, through buses and aux strips |
| `plan paths.json [--target N] [--json plan.json]` | delay per strip to reach the longest path (or N) |
| `add-delay PD OUT plan.json` | AUSampleDelay at insert 1 of each planned strip, other inserts move down one |

`scripts/aulat.swift` (macOS) reads a folder of plists and prints each plugin's latency.

## Line up a template (the recipe)

1. Copy the project. Run `strips` on its ProjectData. Find the output value your final mix
   uses (73 in the original project, shown as `Bus41`) and use it as `--main-out`.
2. `extract` the plists. On the Mac, in a Terminal in the logged-in session:
   `swiftc -O aulat.swift -o aulat && ./aulat plists > lat.txt`.
3. Check `lat.txt` for `NOTFOUND` lines (plugin not installed, or the run was over ssh).
4. `paths` with `--lat`, then `plan`. Read the plan. A strip that needs a large delay often
   means one heavy plugin on another path. Removing that plugin can be the better fix.
5. `add-delay`, then `strips` on the output. Copy the output into the package as
   `ProjectData`, open it in Logic, and check.

## Gotchas

- Strips that end on a hardware output or on a bus with no aux strip show `lat None` and
  get no plan entry.
- Logic's own plugins are listed as `native` and count as zero latency.
- A strip with all 11 insert slots used cannot take a delay.
- `add-delay` copies the chunk header from an existing AU insert in the project. A project
  with no AU inserts at all cannot be patched. Add any AU in Logic, save, and run again.
- Test without a project: `examples/make_test_projectdata.py` writes a synthetic file
  that matches `examples/lat.txt` and `examples/plan.json`.

## Bounce and read Logic without looking

To bounce a section or read insert bypass states in a running Logic, use `scripts/logic_ax.lua` through
`scripts/hs_run.sh` (see the README and `../macos-accessibility/`). Run with `dry = true` first.
