# Avantis show files

Notes on Allen & Heath Avantis and Avantis Solo show files (`.tar.gz`, firmware 1.x and 2.x), and on
converting shows between Avantis and dLive. Everything here was worked out on real consoles: an Avantis
Solo on firmware 2.01 and a dLive S3000 on firmware 2.12, with Avantis Director and dLive Director to open
and check each result.

This folder is documentation only for now. The format notes come from Konverter Konrad, a browser tool
that converts Avantis and dLive shows in both directions (CLAP! Audio Toolbox, toolbox.clap-live.de).
A Python port of the reader, the writer and the converter will follow in this folder.

## What is documented

| File | Content |
|---|---|
| `references/FORMAT.md` | Archive, show versions (Bridge-4, Bridge-5), scene files, section chain, name and colour blocks |
| `references/mixer.md` | Mixer config, bus budget, mixer sections (input, FX return, mix), send rows, FollowPan |
| `references/processing.md` | Processing sections on Bridge-4 (filter coefficients) and Bridge-5 (parameters), models |
| `references/patch-and-io.md` | Channel mapper, socket families, preamps, trim, strip types, surface banks |
| `references/translate-dlive.md` | What maps between Avantis and dLive, what gets lost, FX type IDs |
| `references/console-safety.md` | Console limits by firmware and dPack, file names, crash causes, test workflow |

## How Avantis differs from dLive in one table

| | Avantis / Solo | dLive |
|---|---|---|
| Show version (`Show/Version.dat`) | `Bridge-4` (FW 1.x), `Bridge-5` (FW 2.x) | `13` (FW 1.x), `14` (FW 2.x) |
| Input channels | 64, 96 with FW 2.0 + dPack | 128 |
| Buses | 42, 56 with FW 2.0 + dPack (incl. LR and PAFL) | 64 (incl. main and PAFL) |
| Mono and stereo bus ways | 38, 52 with dPack | 60 |
| Buses per type | 16 at most | 32 at most |
| FX engines | 12 | 16 |
| Ultra FX / AHFX | 8, only with the RackUltra FX card (needs FW 2.0 + dPack) | 8 AHFX built in |
| DCAs | 16 | 24 |
| Filter storage | Bridge-4: biquad coefficients. Bridge-5: parameters like dLive | parameters |
| Show file name on the console | 14 characters before `.tar.gz`, no underscores | see `allen-heath/dlive/` |

## Safety

The format is not documented by Allen & Heath. Never load a generated file straight into a console. Open it
in Avantis Director, check it, save it from Director, and load only that save. Do the first load at prep,
never at the show, and keep a known-good show on a USB stick. `references/console-safety.md` has the
details.

## What we know

- Bridge-4 and Bridge-5 shows written by Konverter Konrad opened in Avantis Director and loaded on an Avantis Solo at firmware 2.01. Bridge-4 on firmware 1.x is not console-tested here.
- Avantis Director does not open a show name longer than 14 characters before `.tar.gz` (`references/console-safety.md`).
- A FollowPanSettings block that does not match the bus config crashes Avantis Director on load (`references/mixer.md`).
- dLive to Avantis and Avantis to dLive translations loaded on an Avantis Solo (FW 2.01) and a dLive S3000 (FW 2.12) (`references/translate-dlive.md`).

## What we don't know

- Compressor model 10: these notes call it CompStortion, and the dLive notes call it the Distressor (`../dlive/references/format-processing.md`). The byte layout is not compared yet.
- The Bridge-5 UFX send and return row format.
- The Gated Echo FX type id on Avantis (0x17 is unconfirmed).
- The flag at bytes 617-618 of the compressor block (`references/processing.md`).
- Avantis firmware other than 2.01, and shows from an Avantis (not Solo) surface.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.
