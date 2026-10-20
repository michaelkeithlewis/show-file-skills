---
name: dlive-showfile
description: Read and write Allen & Heath dLive show files (.tar.gz, firmware 2.x / show Version 14) without opening dLive Director - channel names, colours, stereo pairs, routing and DCAs, the full input and output patch (ABCD sources, I/O ports, Dante, DX, surface, insert returns, virtual soundcheck), mixer config changes (bus counts), mix masters and sends (IEM mixes, FX sends, matrix sends), input processing (read in physical units, reset to defaults, or copy a previous show's processing by instrument), the FX rack, UltraFX and Dyn8 units, MixRack preamps (gain, pad, 48V), SoftKeys, multifunction macros, the surface fader layout and stored scenes, plus a validator that checks a show before it goes near Director or a console. Trigger on "dLive", "show file", "showfile", "Director", "CTi1500", "DM64", "patch the inputs", "set up the IEM sends", "mixer config", "change the aux count", "copy my processing", "softkeys", "layers/layout", "48V", "drop the stored scenes", "is this show safe to load", or any request to build or edit a dLive show for an artist. NOT for Avantis/SQ shows or live console control over MIDI/TCP.
---

# dLive show file editing

Every dLive structure these tools write was decoded from the Director V2.12 binary and checked
byte-for-byte against Director's own output. Director is compiled from the console's code, so a show that
loads in Director offline will load on the console.

## Safety rules (read first)

1. Write new files only (`<Show> V1 16.tar.gz`). Never overwrite a show or touch Director's live state
   (`~/Library/Application Support/AllenAndHeath/...`, it includes a binary SRAM image).
2. Run `scripts/dlive_lint.py <out>` after every change. Never hand over a file with ERRORs.
3. A script-written show goes to Director offline first. The engineer opens it, checks it, and saves it from
   Director. Only Director's save goes to a console.
4. Firmware: shows saved by newer firmware do not load on older consoles. Ask the rental shop which
   firmware the console runs, and open and save in the matching Director version.
5. Never put PASSIVE ribbon sockets on 48V (Coles 4038, R-121). Active ribbons need it.
   Take 48V from the input list.
6. The writers support show Version 14 (firmware 2.x) with an LR main only. They refuse anything else.
Full risk write-up and console recovery steps: `references/console-safety.md`.

## Where things live

- Tools: `scripts/` in this skill. Format notes: `references/`.
- Director treats a folder on disk as its USB drive (Utility > Shows > USB > Recall). Put finished shows there.
- Requires Python 3.9+ and nothing else.

## Tools (all `python3 scripts/<script> ...`; each writes a new file and edits every StageBox/Surface scene
that carries the section unless noted)

| Script | Does |
|---|---|
| `dlive_lint.py show` | Validator. Run after every edit. |
| `build_show.py plan.json template out` | Names, colours, stereo pairs (InputConfig plus the channel mono flag), group/DCA/main assigns from a plan (`dlive_scene.py` is the field map). |
| `dlive_patch.py dump\|apply show [patch.json out]` | Input sources A-D + active, every output socket, insert returns, FX/UFX rack inputs, virtual soundcheck. |
| `dlive_mix.py config\|reconfigure\|mixes\|apply` | Mixer config change (live scene + show files + scene safes, like Director); mix names/faders/mutes/DCAs/pans and sends from a plan. |
| `dlive_processing.py dump\|reset\|copy` | Input processing: reset to defaults, or copy from another show via a channel map (inserts, side chains, FX sends follow). |
| `dlive_proc.py dump\|table show` | Read-only: input processing in physical units (Hz, dB, ms, ratios), one line per channel with `table`. |
| `dlive_fx.py dump\|table show` | Read-only: UltraFX, FX rack and Dyn8 units with their parameters, sends and returns. |
| `dlive_ears.py show` | Read-only: every send into the auxes, FX and UltraFX, plus aux masters. Use it to see how a show builds its ear mixes. |
| `dlive_preamps.py dump\|set` | DM preamp gain, pad, 48V. |
| `dlive_softkeys.py dump\|set` | SoftKeys (both sets): unused, mute <strip>, ABCD set all, talkback, virtual soundcheck mode, multifunction (`mf:ON/OFF`). |
| `dlive_multifunctions.py dump\|remap` | Multifunction macros: list channel refs, remap channels for a new artist, remove macros. Library: `insert_action` (insert A/B in/out/toggle), `abcd_action`, `macro_file`, `add_macro`. |
| `dlive_layout.py dump\|set` | Surface fader banks (CTi1500 = left bank, 12 x 6 layers). |
| `dlive_scenes.py dump\|drop` | List stored scenes, or drop them and keep only the live state. |

Each script's docstring has the exact plan/JSON shape. Read it before writing a plan.

## New show for an artist (the recipe)

1. Start from your closest existing show, or from the A&H factory FoH show that installs with Director.
   Names/colours/stereo pairs/groups/DCAs: `build_show.py`.
2. Mixer config: `dlive_mix.py reconfigure ... sAux=7` (the 64-bus limit includes 2 for an LR main + 2 for PAFL).
3. Patch: `dlive_patch.py apply` (a common layout: FOH ch = socket; IEM copies = FOH + 64 with source B = Dante same number).
4. Sends/IEM mixes/masters: `dlive_mix.py apply plan.json`.
5. Processing: `dlive_processing.py copy new.tar.gz template.tar.gz map.json out --clear-unmapped 1-64,121-128`
   with an instrument map (new channel -> template channel). Templates carry their channel processing by
   number, so always reset or remap. Never leave it.
6. Preamps: `dlive_preamps.py set --48v-on <sockets>`.
7. SoftKeys/macros: dump them. Clear keys that point at things the new show lacks (removed FX, the old
   show's virtual soundcheck keys). Run `dlive_multifunctions.py remap` with the same instrument map.
8. Layout: `dlive_layout.py dump`. A tidy FOH style is DCAs on A, groups B, ears C, talkbacks/matrices D,
   utility/masters E, FX F.
9. Stored scenes: a template's scenes carry the old artist's config and processing, and a recall puts them back.
   Keep only the live state: `dlive_scenes.py drop`.
10. `dlive_lint.py`, then check the result against the brief (dump each section and compare), then open it in Director.

Building from an input list with no template show: `references/show-maker.md`.

## Gotchas

- Director converts only the live scene on a mixer config change. Stored scenes keep their old config and
  are fitted at recall. The tools do the same.
- Patch references to removed mixes stay (Director keeps them).
- On linked stereo pairs the odd channel holds the send pan. The even side's value is ignored.
- Stereo pairs live in two places: `Show/InputConfig/InputConfig.dat` and byte 7 of each input channel section
  (1 mono, 0 both sides of a pair). Director keeps them in step; `build_show.py` writes both.
- Bus count: MixConfig byte 8 is the main mode (0 none, 1 LR, 5 5.1, 6 LCR+) and byte 11 the stereo PAFL count.
  `MixConfig.buses_used` counts both, so a show with no main (the factory Monitors show) lints clean.
- Input channel section: byte 0 main assign, byte 2 mute, bytes 3-4 fader, byte 5 pan 0-74, byte 7 mono flag.
- Insert "in" with nothing patched is harmless. A Dyn8/FX unit can be inserted on one channel only.
- Name fields: 8 characters, NUL-terminated. Bytes after the NUL are leftovers Director keeps.
- Older stored scenes in long-lived shows use older section formats (lint warns, Director converts).
- Virtual soundcheck: `dlive_patch` sets the VSC port + socket range (`{"vsc": {"port": "IO 4", "first": 65, "last": 120}}`),
  "VSC port n" sources and "Ip n VSC rec" sends. Record runs only in VSC mode 1, playback in mode 2 (SoftKeys
  `vsc:1` / `vsc:2`). Channels without a VSC source keep their live input. Details: `references/format-patch.md`.
- ABCD "set all" only flips channels whose ABCD is enabled, so FOH channels with ABCD off are safe from the ears A/B keys.
- Ear reverbs with one FX unit per vocal mic, fed from the IEM channel's direct out: `references/ears-fx.md`.
  FX rack unit k = rack inputs 2k-1/2k = FX return strip k = FX Return Mixer rows 2k-1/2k (`FX Rtn 2k-1/2k` in plans).
- dLive thresholds sit on a nominal 0 dB scale (full scale +18). A dBFS console needs them 18 dB lower.
- How it was decoded and how to extend it: `references/re-toolkit.md`.
