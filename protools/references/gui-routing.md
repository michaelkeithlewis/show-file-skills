# GUI routing fallback (computer-use clicks)

Use this only when `route_folders.py` fails, for example when you cannot grant
Accessibility to the process that runs Python, but you do have a computer-use tool
that can click and type in Pro Tools. `route_groups.py` (you make the clicks) is the
last resort after this.

Not covered: pans, plug-in bypass, faders. Those are also PTSL gaps, and this file
has no tested procedure for them. Do not improvise one from it.

## Terms

- **Routing folder:** a folder track that owns a bus, usually with the same name.
- **Folder bus:** that bus. A track inside `OH GRP` outputs to the bus `OH GRP`.
  The folder's own input selector (its first I/O button) shows the bus it owns.
  It is not always the folder's name (`DRUM GROUP` may own `DRUMS`).
- **Output selector:** the second I/O button on a track, which sets its main output.

## Step 1: build the plan with the SDK

Route only **audio tracks**, grouped by their **direct** parent folder. Leave folder
tracks alone: nested folders (`KICK GRP` inside `DRUM GROUP`) already have the
right outputs, and routing them again breaks the template.

```bash
.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, "scripts")
from collections import defaultdict
from ptctl import engine
from ptsl import PTSL_pb2 as pt
with engine() as e:
    tracks = e.track_list()
    folders = {t.name for t in tracks if t.type == pt.TType_RoutingFolder}
    plan = defaultdict(list)
    for t in tracks:
        if t.type == pt.TType_Audio and t.parent_folder_name in folders:
            plan[t.parent_folder_name].append(t.name)
    for f, names in plan.items():
        print(f"{f}: {len(names)} tracks: {names}")
EOF
```

Take a screenshot of the Edit window's I/O column. Skip any folder whose tracks
already show their bus.

## Step 2: route each folder

Work in the **Edit window**; its I/O column shows each track's output selector.

1. **Jump to the folder.** Press **Command+Option+F** (Track > Scroll to Track).
   The dialog searches by **track name**. Type the first child's name and press
   Return. That track moves to the top of the Edit window. This also selects only
   that track, so select in the next step, not before.
2. **Select with the SDK, not by clicking names.** A Shift-click range can include a
   nested folder, and the modifier click would then route that folder too.
   ```python
   e.select_tracks_by_name(names)   # inside `with engine() as e:`
   ```
3. **Option+Shift+click the output selector** on the first selected track. Zoom
   the screenshot first to get the exact point.
4. **Use the menu's `search...` item, not the bus submenu.** The bus submenu is
   long and scrolls under the pointer; a click there can land on the wrong bus.
   Click `search...` (just above the selector), type the bus name, check that one
   result is highlighted, then press **Return** once. Return applies the bus to
   every selected track.
5. **Zoom on the I/O column.** Every selected track must now show the bus name
   (abbreviated, for example `TOM`, `OHG`, `GUIT`). This is the check.

**Option+Shift applies to the selected tracks. Option alone applies to every track
in the session.** Never click with Option alone. Output changes are not on the undo
list; fix a wrong route by routing again.

After the last folder, save with the SDK (`e.save_session()`).

## Step 3: optional bounce check

```bash
.venv/bin/python scripts/verify_routing.py --list      # the buses it will check
.venv/bin/python scripts/verify_routing.py --master-bus <your main bus>
```

It bounces each folder's bus plus the main bus over a short window and reports
peak level. Above -60 dB carries audio. About -240 dB means nothing feeds the bus;
about -78 dB is plug-in noise with no audio. Folders with no tracks are reported as
"silent (empty folder)" and do not fail. The default window is 200,000 samples from
sample 3,700,000; point `--at-sample` at a busy section. The bounce files are
deleted afterwards. A full-song check takes minutes, so use it only when a route is
in doubt.

## Report

1. The folders that now route correctly.
2. The folders that still read silent, and what you tried.
3. Any dialog Pro Tools opened and how you answered it.
