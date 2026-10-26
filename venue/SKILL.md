---
name: venue-showfile
description: Read Avid VENUE show files (.dsh, magic "Digidesign Storage - 1.0") without the console or VENUE Standalone - S6L shows in full (software version, engine, every strip's name, colour, fader, input patch bytes, HPF, EQ, dynamics and aux sends, the plug-in racks with inserts and readable AAX default-format settings, snapshot names) and classic D-Show / Profile / SC48 shows (config and strip names) - and make only the changes VENUE has loaded back - on VENUE 8.2 E6L-192 S6L shows with no snapshots, rename strips (16 characters), set faders and colours, and clear plug-in rack slots. Trigger on "S6L", "VENUE", "D-Show", "Profile", "SC48", ".dsh", "Digidesign", "what is in this show", "rename the channels in this VENUE show", "colour the inputs", "what plug-ins are in this show", "plug-in settings in the show", or "clear that rack slot". A .dsh file is NOT a DiGiCo session. NOT for patch, processing, send, snapshot or plug-in setting edits, which VENUE has not loaded back yet.
---

# Avid VENUE show files

A VENUE show file (`.dsh`) is a typed key/value tree after the magic `Digidesign Storage - 1.0`. S6L shows (VENUE
5.0 and later) use `scripts/s6l_tool.py`. Classic shows (D-Show, Profile, SC48) use `scripts/dshow_tool.py`. Format
notes: `references/S6L-FORMAT.md` (S6L, with an evidence label on every fact) and `references/FORMAT.md` (classic).
Python 3.8 or later, standard library only. The web version is https://idontownapc.com/s6l.

## Safety rules

1. Write a new file. Both tools refuse to overwrite their input.
2. Run `s6l_tool.py info` first. Its `edit:` line says whether this show can be changed and why not.
3. `s6l_tool.py edit` changes only names, faders, colours and plug-in slot clears, and only on VENUE 8.2 shows from
   an E6L-192 with no snapshots. Never work around a refusal by hand-editing bytes.
4. Never edit the patch, processing, sends, snapshots or plug-in settings. Use VENUE for those.
5. Open every edited file in VENUE Standalone with **Filing** > **Load**, check it, and save it there. Only that save
   goes to a console. Do the first console load at prep, never at the show.
6. Tell the user what the tool refused and why. Do not promise that a file loads on a console: it was tested in
   VENUE Standalone only.

## S6L commands

```
python3 scripts/s6l_tool.py info SHOW.dsh
python3 scripts/s6l_tool.py strips SHOW.dsh [--kind input|aux|group|matrix|mains|vca|fx_return|pq] [--proc] [--sends]
python3 scripts/s6l_tool.py plugins SHOW.dsh [--params]
python3 scripts/s6l_tool.py snapshots SHOW.dsh
python3 scripts/s6l_tool.py check SHOW.dsh
python3 scripts/s6l_tool.py json SHOW.dsh
python3 scripts/s6l_tool.py edit SHOW.dsh OUT.dsh [--rename ID=NAME] [--names FILE] [--colour ID=COLOUR]
                                 [--fader ID=DB] [--clear RACK.POSITION] [--dry-run]
```

Strip ids are 1-based: `in1`, `aux1`, `grp1`, `mtx1`, `mains1` (Left), `mains2` (Right), `mains3` (Mono), `vca1`.
Colours: 0 grey, 1 green, 2 blue, 3 yellow, 4 orange, 5 cyan, 6 purple, 7 red, 8 white. Faders: dB or `-inf`. A
rack slot is `RACK.POSITION` as the `plugins` command prints it.

## S6L edit recipe

1. Run `info`. If `edit:` says closed, stop and give the user the sentence. For a VENUE 7.x show, the user can load
   it in VENUE 8.2 Standalone, save it, and give you that save, if their console runs 8.2.
2. Run `strips` or `plugins` and pick the ids.
3. For names from an input list, save the list as a `.csv` with a Name column (and a Ch column) and pass `--names`.
4. Run `edit ... --dry-run`. Read every line. One refused change stops the whole run.
5. Run it again without `--dry-run`.
6. Run `strips` or `plugins` on the output to check it, then tell the user to load it in VENUE Standalone.

## Classic commands

```
python3 scripts/dshow_tool.py dump  SHOW.dsh       # config + unique strip names
python3 scripts/dshow_tool.py names SHOW.dsh       # slot, strip id, flag, name per strip
python3 scripts/dshow_tool.py rename SHOW.dsh "Old" "New" OUT.dsh [--dry-run] [--pad space|nul]
```

A classic rename must be the same length or shorter. It renames by name, so two strips with the same name are both
renamed. `--pad space` (default) keeps the packed name tables intact. No file it wrote has been opened in VENUE yet.

## Gotchas

- Names hold 16 characters. VENUE cuts longer names, so the tool refuses them. Typographic quotes and dashes are
  folded to ASCII; the Euro sign and other bytes from 0x80 to 0x9F are refused.
- A show with snapshots is read-only: any snapshot may keep its own copy of a strip or a slot.
- The input patch bytes are a copy. VENUE puts its own patch back, so the tool never writes them.
- Plug-in settings are shown only for the AAX SDK default format. Every other format is "settings stored": never
  decode, change or guess at it.
- On a VENUE stick a show lives at `D-Show/Consoles/VENUE/Shows/<show folder>/<show>.dsh`. VENUE lists only shows
  inside a show folder.
