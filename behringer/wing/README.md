# WING snapshots

Notes on Behringer WING snapshot files (`.snap`, firmware 1.12 to 3.3) for the full size, Compact and Rack. A
WING snapshot is one JSON document with named keys, and one format serves all three models. This folder is
documentation only: there is no reader or writer yet.

The notes were contributed by markcarlberg. Most of them are desk research (the unofficial WING Remote
Protocols document V3.0.5-1, libwing's generated node map, Behringer's WING user manual and Effects Guide)
checked against real snapshots. A smaller set was moved by WING Edit saves. `references/FORMAT.md` labels each
line with its source.

## What is documented

| File | Content |
|---|---|
| `references/FORMAT.md` | Container, `ae_data` layout, value laws, sockets and patching, outputs, channel processing, dynamics models and ranges, sends, monitor and talkback, effects, layers and safes, library files, the blank snapshot, firmware differences, what WING Edit writes |

## Safety

The format is not documented by Behringer. Never load a generated snapshot straight into a desk. Open it in WING
Edit, check it, save it from WING Edit, and load only that save. Do the first load at prep, never at the show.

## What we know

- `col` is an index 1-18 into WING-Edit's swatches, in the order listed in `references/FORMAT.md`. Proven by one
  save with each swatch on its own channel, read back.
- Source link `clink`: a linked strip shows its source's name, colour and icon; with nothing patched or an
  unnamed source it shows no name, colour 1, icon 0; fed from a bus it shows the bus name. Proven by WING-Edit
  3.3.3 saves.
- Automix: `cfg.amix.x`/`.y` masters, per strip `postins.mode` AUTO_X/AUTO_Y and `postins.w` in dB. Proven by
  saves.
- Emulation control ranges for `76LA`, `L100`, `SBUS` and `B160`. Proven by loading values past the ends into
  WING Edit 3.3.3, which clamps them on load, and reading the save back.
- The WING-Edit 3.3.3 dynamics model list and each model's default keys (`references/FORMAT.md`). Proven by
  saves at defaults.
- `DEQ` and `DEQ2` keys (`thr`, `ratio`, `att`, `rel`, `g`, `f`, `q`, `filt`, `mode`), `mode` `high`/`low`, and
  `filt` default `BP`. Proven by WING-Edit's page and saves.
- WING-Edit 3.3.3 loads a legacy `D241` token in a 3.3 file as the stock compressor. Proven by a load and save.
- The WING-Edit 3.3.3 INIT CONSOLE snapshot, full size and Compact (`references/FORMAT.md`, "The blank
  snapshot"). Proven by the editor saves, held byte for byte.

## From the manual and the protocol doc

These come from published documents and are consistent with real snapshots, but no single save moved them.

- Insert positions: channel INS 1 where `proc` puts the I, always pre-fader; INS 2 always post-fader (manual
  6.1).
- Premium FX models (reverbs, delays, chorus, flanger, dimension chorus, pitch) run in FX slots 1-8 only
  (Effects Guide).
- The `ptap` tap points (manual and protocol doc).
- The host channel's input is the talkback mic (manual 5.5).

## What we don't know

- The speed of sound and sample rate behind delay units M, FT and SMP (343 m/s and 48 kHz are assumptions).
- The input balance law against pan.
- Whether `ind` is the independent-send switch. Read from its pattern only.
- Whether a channel sourced from `BUS 2b-1` plays the bus in stereo, and whether a linked strip on a main or
  matrix feed shows the feed's name.
- `SEND 2k-1`/`2k` as the send of FX slot k, and `ein+1` as the right side of a stereo EXT return.
- Whether a slot holding only `mdl` and `fxmix` loads the model's defaults.
- The `filt` spellings of `DEQ`/`DEQ2` other than `BP`.
- The fixed internal threshold of level-driven models (76LA, LA, L100, NSTR, F670, LMT, ONEC); the volts and dBu
  scales of B160 and 2250; LA `ingain` and `peak` scales; 1176 and Distressor knob laws; word-valued times.
- Channel CMB is not decoded control by control. `gate.acc` behaviour is undocumented. `3CMP` is unseen.
- Exact file spellings of `EXCITER`, `GEQ`, `PIA` and `LIMITER` keys (one or no example each).
- 3.x spellings for the 1.12 clock source (AES50-A sync), recall safes, meter, RTA and surface keys.
- The meaning of the pre-2.x direct input `tap`.
- Which 3.3.3 differences are firmware and which are editor. No 3.3 desk save, no WING Rack file, no firmware
  3.0.0-3.0.3, no Compact before 3.1, and no 1.10 file has been examined.
- How WING Edit version numbers map to firmware.
- The expander and virtual surface banks (`EXT`, `VRT`).

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-10-29, WING-Edit 3.3.3, contributor reading: `DEQ` and `DEQ2` keys and `mode` decoded from the editor page and saves.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.

Cross-desk format notes in this folder are by [markcarlberg](https://github.com/markcarlberg). Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
