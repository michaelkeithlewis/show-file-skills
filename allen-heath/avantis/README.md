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
| `references/settings-and-surface.md` | Talkback, signal generator, PAFL, AMM, metering, gangs, layers, soft keys (markcarlberg) |

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
- Version.dat: markcarlberg's notes list `Bridge-3` for desk firmware V1.20-V1.25 and tie `Bridge-4` to Director V1.30 and `Bridge-5` to V2.01; `references/FORMAT.md` says Bridge-4 is firmware 1.x and Bridge-5 firmware 2.x and has no Bridge-3. A Bridge-3 show loaded in Director would settle it.
- Frequency law: a contributor reading says `4 x 2^(raw / 4608)` exactly (save-proven on the SQ); `references/processing.md` uses the fitted `3.990373 x 2^(code / 4606.26)`. Both agree within display precision; a 20 kHz word on Avantis would tell them apart.
- PEQ width: a contributor reading says the width is a code byte (0-24) plus a fraction byte the desk ignores; `references/processing.md` reads a u16 Q code with a fitted Q table. Needs a save that settles it.
- Bridge-4 shelves: a contributor reading puts the first-order corner at `c x tan(pi f / fs)` with c = pi (LF) or 0.318 (HF); `references/processing.md` has the fitted factor 3.04. Needs a save that settles it.
- Bridge-4 chain length: a contributor reading says the u32 just before the first block is the chain's length on every family; `references/FORMAT.md` says Bridge-4 has no such field. Needs a check on a Bridge-4 save.
- Show name length: a contributor reading says Director lists a show by the first 16 characters of the file name and a longer name fails to recall with "Show not found"; `references/console-safety.md` says 14 characters. Needs a save that settles it.
- FX racks: a contributor reading lists `FX Manager 01-16` with an 18-byte name at [4..21]; `references/FORMAT.md` says 12 racks and a 20-byte name. Needs a save that settles it.
- FX type IDs: a contributor reading gives dLive the standard SQ numbering (Reverb 02, SMR Reverb 03, Room 05, Gated Verb 0E, Bucket Brigade 22, Echo 24) and Avantis Bucket Brigade 0x15; `references/translate-dlive.md` has SMR Room 3 on dLive, 14 as Gated Echo, and no BBD on Avantis. Needs a save that settles it.
- GEQ bytes 617-618: a contributor reading names [617] the GEQ out switch and [618] the slot (0 GEQ, 4 NEQ12); slot codes 1, 2 and 3 also occur on shaped or switched-out GEQs and are not named.
- Bridge-4 GEQ band Q away from flat (Q 4.33 flat, narrowing as gain rises); Bridge-3 GEQ preset recall on V2.01.
- MixConfig [11] as the PAFL count (save-proven on dLive only), and which two buses the desk keeps back from the 56 (54 is not recall-tested).
- Main section +7 (LCR switch candidate) and +9..10 (C level candidate); which `Mix Mixer` main record is which in a four-mono-main LCR+ show.
- `Channel Mapper` records 320-352 (`01 01 01` on 320-351; 352 varies), 605 and 686, mono group insert returns (probably 803-858), the AES outputs' sockets, and which rear sockets Local 13-16 are.
- Which physical I/O Port each `Port B` head-amp slot is; the Virtual SoundCheck port.
- Peak Limiter 76 attack and release and Mighty release laws; the OptTronik emphasis filter; the low pass key filter's shelf state.
- Dual Expander fields; a Ducker threshold moved off its preset.
- Mix insert In switch; Main 03/04 insert records; a stereo mix on an FX rack.
- Dyn8 unit contents on Avantis; DEEP preamp model blocks; Source Select Controllers; `Output Socket Polarity`.
- Ultra FX send masters and return fader and mute.
- The second PAFL's fields in `PAFLSettings.dat` ([21..41] look like a copy); fields [1], [7], [8], [45].
- AMM per-input priority and chair, byte [539] (moves with Chair Sensitivity and Duck Level); the signal generator Sine code (0 by elimination); meter attack and release laws; `MeteringSourcesGlobal.dat`; RTA.
- Whether `Talkback.dat` gives FX sends legs: a change of FX send count moved no talkback line.
- Layer kinds 0D and 0E; soft key contents.
- Input source types for FX returns and FX sends as key sources (no code seen).

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-10-30, Avantis Director V1.30 and V2.01: field map additions contributed by markcarlberg (pull request #2), merged into `references/` under "markcarlberg, pull request #2" headings.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.

The Avantis notes are by [Stefan "Hedde" Hettenbach](https://www.instagram.com/stefan_hettenbach/) (Clap! Live Solutions, Mannheim), from his Avantis and dLive converter. Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
