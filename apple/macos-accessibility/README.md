# macOS Accessibility automation for audio apps

How to drive Logic Pro, Pro Tools and other Mac apps from an agent or a script with no screenshots, no mouse
coordinates and as few keystrokes as possible. Every rule here was learned by an automation that hung, clicked the
wrong thing, or ran blind overnight.

The working code is in this repo:
- Logic: `../logic/scripts/logic_ax.lua` (Hammerspoon), with `hs_run.sh` to run jobs. It reads insert bypass states
  and bounces a bar range to a named file.
- Pro Tools: `../../avid/protools/scripts/ptax.py` (routes tracks by control name) and `demo_guard.py` (dismisses plug-in
  demo prompts).

## Set up

1. Grant Accessibility to the process that sends the actions: **System Settings > Privacy & Security >
   Accessibility**. Add Hammerspoon, your terminal, or the Python that runs the script.
2. For Hammerspoon jobs from a shell, install the CLI once from the Hammerspoon console: `hs.ipc.cliInstall()`.
3. You do not need Screen Recording. Read the AX tree instead (see "Read, do not look").

## Read, do not look

- Read the Accessibility tree, not the screen. `screencapture` fails over SSH and when the display sleeps, and a
  Hammerspoon snapshot without Screen Recording shows only the menu bar. Logic's AX tree is rich: windows, the
  bounce dialog, insert slots, plug-in windows and the save panel all have roles, titles and identifiers.
- Find controls by role plus title, description or `AXIdentifier`. Never by position: positions move with window
  size and screen.
- Dump a window first (`L.dump(L.win("Tracks"), 6)` in `logic_ax.lua`) and write the predicate from what you see.

## Act through AX, not keystrokes

- Press menu items by path through the AX menu bar (`L.menu({"File", "Bounce", "Project or Section…"})`). It
  fails loudly when an item is missing or disabled. A keystroke fails silently.
- Press buttons with `AXPress`. Set text fields with `AXValue`, then read the value back before you confirm.
- Some apps mix web views and real AppKit. A web view's buttons can be clicked through its DOM, but its confirm
  sheets are AppKit and only respond to Accessibility. Cancelling a job can need both: a DOM click to raise the
  sheet, an AX click to confirm it.

## The save panel

- **Never press Cmd+Shift+G** in a save panel. Its "Go to" box autocompletes against iCloud Drive and can sit on
  "Loading" forever. The sheet is modal, so the app looks stuck at 0 percent while it waits for you.
- Do not navigate at all. The panel reopens in the last folder used. Set the name and confirm:
  - With AX: set `AXValue` on the field with identifier `saveAsNameTextField`, check the `where popup` value
    shows the folder you expect, then press `OKButton`.
  - With System Events, when the name field already has focus: Cmd+A, type the name, Return (key code 36).
- Do not press Escape to clear a stuck sheet. In a save panel Escape is Cancel and kills the whole export.
- "Already exists, replace?" is a nested sheet: `sheet 1 of sheet 1 of window N`. Search nested sheets for the
  Replace button, or the job stalls with the prompt open.
- The panel is hosted by `com.apple.appkit.xpc.openAndSavePanelService`, so `entire contents` under the app process
  can come back empty. The app process still exposes the nested sheet's fields.

## Running jobs without hanging

- `hs -c` can hang forever on some return values, and its timeout flag does not stop it. Queue the job on a
  Hammerspoon timer, write the result to a file, and poll the file. `hs_runner.lua` and `hs_run.sh` do this.
- Wrap every remote call in `timeout`.
- Add a watchdog to anything that runs while you sleep: poll progress, and on a stall save an AX dump of the front
  window, cancel, relaunch and retry.

## Logic Pro specifics

- Logic shows zero windows in the AX tree while it is in the background, and its menus read as disabled. Activate it
  first (`open -a "Logic Pro X" <project>`). If only a plug-in window is open, use **Window > Open Main Window**.
  **Bounce > Project or Section** stays disabled until the main window is up.
- The bounce dialog's Start and End fields are groups of slider segments (bars, beats, divisions, ticks).
  `AXIncrement` and `AXDecrement` move 10 units. Setting `AXValue` moves only one unit toward the value. The value is
  ticks x 2^32, with bar 1 at 38400 ticks and 3840 ticks per bar in 4/4. `L.setpos2()` steps there and checks each
  move. Changing the dialog's range does not move your cycle locators.
- Insert bypass is readable on the inspector channel strip: an insert is a group with a `bypass` and an `open`
  button. Toggle bypass with the plug-in window's power button (`AXDescription == "bypass"`).
- Some plug-ins switch their own options off after a while (an unlicensed copy, for example). Set the option just
  before each bounce and check the result was processed.
- Verify without listening: re-bounce a range you already have and compare level and correlation with
  `../logic/scripts/locate_clip.py` before you trust a plug-in state.

## Pro Tools specifics

- PTSL (the scripting SDK) cannot set a track's output. `ptax.py` sets it through the output selector by control
  name. Accessibility controls only exist for tracks Pro Tools has drawn, so scroll or show the track first.
- Plug-in demo prompts block automation. `demo_guard.py` dismisses them.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.
