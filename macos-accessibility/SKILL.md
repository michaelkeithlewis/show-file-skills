---
name: macos-accessibility
description: Drive Mac audio apps (Logic Pro, Pro Tools, any AppKit app) through the macOS Accessibility tree with no screenshots or mouse coordinates - press menus and buttons by name, set fields by AXValue, get past save panels without hanging, run Hammerspoon jobs without blocking, and bounce from Logic blind. Trigger on "accessibility", "AX", "Hammerspoon", "click it without the mouse", "bounce from Logic remotely", "the save panel is stuck", "export hangs at 0%", or any request to automate a Mac app's UI. For Pro Tools session control use the protools skill first (PTSL); this covers what PTSL cannot do.
---

# macOS Accessibility automation

Read `README.md` in this folder before you automate a Mac app. The rules that matter most:

1. Read the AX tree, never the screen. Dump the window, then find controls by role plus title, description or
   `AXIdentifier`.
2. Act with `AXPress` and `AXValue`, and read every value back before you confirm.
3. Never press Cmd+Shift+G in a save panel, and never press Escape to clear a stuck sheet.
4. Never wait on `hs -c`. Queue jobs with `../logic/scripts/hs_run.sh` and poll the result file.
5. Activate Logic before you look for its windows. A background Logic shows none.

Logic bounce: write a job like `../logic/examples/bounce_job.lua` and run
`../logic/scripts/hs_run.sh <job.lua> 60`. Start with `dry = true`: it sets the range, reads the settings and
cancels.
