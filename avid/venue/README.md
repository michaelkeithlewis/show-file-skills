# venue: Avid VENUE show files (S6L and classic)

Read Avid VENUE show files (`.dsh`) without the console or the VENUE software, and make the few changes that VENUE
has loaded back. This folder is a Claude Code skill (`SKILL.md`) and two plain Python scripts:

- `scripts/s6l_tool.py` for **S6L** shows (VENUE 5.0 and later): read the whole show, and rename strips, set
  faders and colours, and clear plug-in rack slots inside the limits below.
- `scripts/dshow_tool.py` for **classic VENUE** shows (D-Show, Profile, SC48): read the config and the strip names,
  and rename in place.

The `.dsh` extension is not DiGiCo. Every VENUE show starts with the magic `Digidesign Storage - 1.0`.

To use it in the browser instead, go to [idontownapc.com/s6l](https://idontownapc.com/s6l): the same code, with
VENUE-style Inputs, Outputs and Plug-Ins pages.

## Models

- [S6L](s6l/): S6L shows, VENUE 5.0 and later
- [D-Show](d-show/): classic D-Show, Profile, SC48

## What is in the folder

- `SKILL.md`: the skill. Claude Code loads it when you ask about a VENUE show.
- `scripts/s6l_tool.py`: `info`, `strips`, `plugins`, `snapshots`, `check`, `json`, `edit`.
- `scripts/dshow_tool.py`: `dump`, `names`, `rename` for classic shows.
- `references/S6L-FORMAT.md`: the S6L format notes. Every fact carries an evidence label (PROVEN, STRONG or
  UNVERIFIED) and the test behind it.
- `references/plugins.md`: what a Waves SoundGrid rack slot and an Avid Channel Strip slot hold.
- `references/FORMAT.md`: the first notes, for classic shows.

## Requirements

- Python 3.8 or later. No other packages.
- VENUE Standalone (free from your Avid account, Windows only), to open and re-save every edited file.
- Your own show files. No show files ship with this folder.

## S6L quick start

```
cd avid/venue/scripts
python3 s6l_tool.py info "My Show.dsh"                       # software, engine, counts, what edit may change
python3 s6l_tool.py strips "My Show.dsh" --proc --sends      # every strip with patch, HPF, EQ, dynamics, sends
python3 s6l_tool.py plugins "My Show.dsh" --params           # rack slots, inserts, readable plug-in settings
python3 s6l_tool.py snapshots "My Show.dsh"
python3 s6l_tool.py edit "My Show.dsh" "My Show v2.dsh" \
    --names input-list.csv --rename aux1="Drum Fill" --colour in1=yellow --fader vca1=0 --clear 2.3 --dry-run
```

Drop `--dry-run` to write the file. Then copy it into a show folder, load it in VENUE Standalone with **Filing** >
**Load**, check it, and save it there. Load only VENUE's save on a console.

Strip ids are 1-based, as on the VENUE screen: `in1`, `aux1`, `grp1`, `mtx1`, `mains1` to `mains3`, `vca1`, `fx1`,
`pq1`. A rack slot is `RACK.POSITION`, for example `2.3`. `--names` takes a `.csv` with a Name column (a Ch column
sets the input number) or a text file with one name a line.

## What it reads

| Data | Label |
|---|---|
| Software version, engine, mix configuration, sample rate, who saved the show | PROVEN for the version; STRONG for the engine codes |
| Strip names, faders, colours (with the colour each number shows as on VENUE's screen) | PROVEN on VENUE 8.2 (Filing > Load); colours STRONG on 7.x |
| Stereo flag, input patch bytes, HPF, input EQ, output EQ, compressor, gate, aux send levels | STRONG |
| Plug-in racks: the type in each slot, the strip kind and strip it is inserted on, bus-fed routing | PROVEN |
| Rack and position of each slot | PROVEN for positions 1 to 7, STRONG for 8 to 25; past position 25 not mapped |
| Insert position on the strip | STRONG |
| Plug-in settings in the AAX SDK default format (Avid Channel Strip, Pro series, EQ3, Dyn3 and more) | PROVEN |
| Every other plug-in format | not decoded: shown as "settings stored" and never changed |
| Snapshot names and the plug-in copies each snapshot keeps | STRONG |
| Preamps, 48 V, the patch source, the output patch, mutes, VCA members | not read yet |

Classic VENUE and S3L-X shows get a read-only summary.

## What it writes, and how that was proven

`edit` makes only these changes:

- Names on inputs, auxes, groups, matrixes, the mains and VCAs, 16 characters at most (Windows-1252).
- Faders (-inf, or -144 to +12 dB) and colours (0 to 8) on the same six kinds.
- Clearing a plug-in from a rack slot that is inserted on an input, group or matrix, or is not routed, with no
  sidechain key: the slot, both routing copies and both sidechain words.

Each one was proven with Filing > Load in VENUE S6L Standalone 8.2.0.187 on Windows 11:

1. The written file went into a show folder under `Documents\D-Show\User Data\Shows\`.
2. **Filing** > **Load** loaded it. The Info area was blue (the show matches the system).
3. VENUE saved it at once under a new name.
4. The Inputs, Outputs, Patchbay, Overview and Plug-Ins pages showed every change, and the strips and slots next
   to them as before.
5. VENUE's save was compared node by node with VENUE's save of the unchanged show. Every value was kept, and
   nothing else differed except the load time, the load path and VENUE 8's `Current State`.

The runs used a clean show that VENUE Standalone saved itself and an 8.2 console show, both from an E6L-192 with no
snapshots, so `edit` opens only on such shows:

- VENUE 8.2 shows from an E6L-192 engine. VENUE 7.0 and 7.2 shows stay read-only: no VENUE 7.x Standalone has
  loaded a written file yet. If your console runs 8.2, load the 7.x show in VENUE 8.2 Standalone, save it, and edit
  that save (the show then needs VENUE 8.2).
- No snapshots. The snapshot record is not decoded, so any snapshot may keep its own copy of a strip or a slot.
- Inside the E6L-192 counts: 192 inputs, 80 auxes, 16 groups, 24 matrixes, 3 mains, 48 VCAs. The mains only in an
  L-R plus Mono show. Never FX returns or PQ strips.
- No slot that VENUE 8's current state keeps a copy of, no bus-fed slot, no aux insert, no keyed slot, nothing past
  rack position 25.

Everything else is refused with a sentence, and one refused change stops the run. `edit` never writes the patch,
processing, sends, snapshots or plug-in settings, and never overwrites its input. Before it writes, it checks that
the new file parses, writes back byte for byte, holds the values asked for, and differs from the input only in the
records the changes name.

A written file loaded in VENUE Standalone. It has not been tested on a console. Do the first console load at prep
or rehearsal, never at the show, and keep a known-good show on the stick.

## Classic VENUE and D-Show

`dshow_tool.py` reads the system config and every strip name of a classic VENUE show (Profile, SC48, D-Show
family), and renames strips in place without moving a byte offset.

```
python3 scripts/dshow_tool.py dump  "My Show.dsh"
python3 scripts/dshow_tool.py names "My Show.dsh"
python3 scripts/dshow_tool.py rename "My Show.dsh" "Kick In" "Kick" "My Show renamed.dsh" --dry-run
python3 scripts/dshow_tool.py rename "My Show.dsh" "Kick In" "Kick" "My Show renamed.dsh"
```

A rename must be the same length as the old name or shorter, and the file size must not change. `FORMAT.md` has
the safe-rename rule.

Correction (2026-10-26): the one show this tool was first tested on turned out to be an S6L show saved by VENUE 8.2,
not a classic show. On it, the config block and all 267 strip slots read, and a rename changed only the bytes of the
renamed name (3 copies, size unchanged). No file it wrote has been opened in VENUE. For S6L shows use
`s6l_tool.py`, whose renames VENUE has loaded.

## Status

Verified for this release:

- `python3 -m py_compile` and `--help` on both scripts.
- `s6l_tool.py` reads every field the same as the code behind idontownapc.com/s6l on 51 VENUE files (23 private
  S6L shows from VENUE 7.0, 7.2 and 8.2, and the 28 demo files in Avid's VENUE 4.5.3 installer) and on a show built
  from an input list.
- Its writes are byte-identical to that code's on a show built from an input list (21 strip changes, and 25 input
  names from a CSV), on synthetic shows (slot clears), and on an 8.2 console show (strip changes, and every used
  slot: 25 clears identical, 9 refused by both).
- Every refusal path (long names, characters VENUE does not keep, other versions and engines, snapshots, L-C-R
  mains, FX returns, keyed, bus-fed and current-state slots), and 900 damaged files read without a crash.

This tool is not affiliated with or endorsed by Avid. VENUE, S6L, D-Show and AAX are trademarks of Avid Technology.
The format was decoded from show files and public documents; no Avid program was disassembled. No warranty.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack planning app for touring and production crews.
