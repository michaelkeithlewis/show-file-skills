# SQ show files

Notes on Allen & Heath SQ-5, SQ-6, SQ-7 (firmware 1.5 and 1.6) and SQ+ (firmware 2.0.3) show folders. The
format was worked out by markcarlberg from files saved by SQ MixPad 1.6.1, SQ+ MixPad 2.0.3 and an SQ desk on
firmware 1.6.3, mostly by changing one control, saving, and comparing.

This folder is documentation only. There is no SQ reader or writer yet.

## What is documented

| File | Content |
|---|---|
| `references/FORMAT.md` | Show folder, header and CRC, the 14 sections, value laws, strip blocks, patch and head amps, processing and DEEP models, sends, bus config, output patch, FX racks, desk-wide settings, version differences |

## How the SQ differs from Avantis and dLive

| | SQ / SQ+ | Avantis, dLive |
|---|---|---|
| Container | `SHOW####` folder of fixed 128 KiB images (`NVDATA.DAT`, `SCENEnnn.DAT`) | `.tar.gz` of labelled blocks |
| Checksum | zlib CRC-32 at 0x1FFFC | none |
| Byte order | little-endian | big-endian |
| Level word | u16, `0x8000 + 256 x dB`, 0 = off | s16, 1/256 dB, `0x8001` = off |
| FX parameter words | same numbers, other byte order | |

## Safety

The format is not documented by Allen & Heath. Never load a generated show straight into a desk. Open it in
MixPad, check it, save it from MixPad, and load only that save. Do the first load at prep, never at the show,
and keep a known-good show on a USB stick.

## What we know

Each line says how it was proven. Details and offsets are in `references/FORMAT.md`.

- A show folder loads as its `NVDATA.DAT`; a stored scene's content appears only when that scene is recalled (MixPad check).
- Every image ends in a zlib CRC-32 over a fixed span (SQ 0x14-0x1FFFB, SQ+ 0x204-0x1FFFB), stored at 0x1FFFC (save-proven).
- Firmware is at 0x0C-0x0E; major 2 tells an SQ+ file apart (save-proven).
- A strip's settings sit in both section 2 (strip block) and section 5 (send record); both must be copied together (save-proven).
- Level, frequency, time and pan laws (save-proven by one-change saves in MixPad).
- Head amp records, the 41 compressor ratio codes, DEEP compressor model layouts and SQ+ gate models (save-proven by saves at each control's ends).
- A scene's bus layout copy is not applied on recall; the layout lives in NVDATA (MixPad check).
- Reverb and Stereo Tap Delay parameter words: a file written with them loaded in MixPad 1.6.1 showing the values written. The same words apply on Avantis and dLive.
- Switching MixPad between SQ-5, SQ-6 and SQ-7 rewrites nothing in the file (MixPad check; a real SQ-5 load is not checked).

## What we don't know

- PEQ band 4 type codes. Files hold 00, 07 (with gain, at 2.9-20 kHz) and 0A (gainless), read as bell, high shelf and low pass. MixPad 1.6.1 has no band 4 type control, so no save can set it. Unconfirmed.
- The PEQ width code to Q law on the SQ (a frequency sweep on a desk would settle it).
- The 16VU compression code: the 41-code table or its own scale. One reading of dLive Director V2.11's display put nine marks five codes apart at 1, 1.5, 2, 3, 4, 6, 10, 20, infinity. Unconfirmed.
- Peak Limiter 76 at raw 0x8000: MixPad shows "24" on reload, not infinity, although its own save wrote those bytes.
- Peak Limiter 76 ratio codes 01-03 (4, 8, 12:1 by button order only).
- Compstortion (SQ+, code 0A): F4 and F6 read as attack and release (`0x0032`), F8 and FA as input and output on the field law (`33 7A` -5.8 dB, `66 88` +8.4 dB), which is which not pinned; ratio buttons, detector, distortion and HP bytes not placed. All unconfirmed.
- Tube Stage level and bias laws; modes 0, 1, 4, 5 are by panel order only.
- Expander bytes +0x5E, +0x62, +0x67 and the Dual Threshold Expander's +0x67.
- Local sockets 32-47 (one source lists 0-47 as mic inputs); whether socket 0x3A is the talkback XLR.
- Which physical sockets Local A and B (output records 32, 33) are; output records 268-283; the 96-byte (SQ+ 288-byte) table after section 7's records, which holds type 05 entries naming strip blocks and type 15 on sources 24-27 and is cleared when a block stops being a mix.
- Output types 06 (probably an insert send's right leg) and 11 (seen on a few records); the code for an FX send patched to a socket.
- LR and matrix balance; the Mix Ext In source and preamp (candidates +0x18-0x1B and +0x2C-0x30 on mix blocks); a stereo width on mixes.
- Talkback assigns, source, HPF and latch (+0x14B on mix blocks is the candidate for the assigns).
- The insert's FX unit (+0x2C-0x30 may name it; 09, 0B, 0D seen); inserts on mixes and their processing position.
- Gang attribute bits other than 3, 7 and 8 (0-2 may be Trim, Filter, Gate by MixPad's order); whether a mix can be ganged.
- Input to PAFL Source codes 1 (Post PEQ) and 2 (Post Compressor), by menu order only.
- With two AMMs, whether slots 1-24 are AMM 1's.
- Soft key type codes, the rest of section 10 (SoftRotaries and footswitch are candidates), whether a scene recall changes soft keys.
- Layer names: six 612-byte records in section 14 hold "Tab"-style names in one show. Unconfirmed.
- Header 0x08-0x0B on an SQ and the SQ+ header words at 0x04 and 0x08.
- Stereo Tap Delay input filters (words 5-6 look like frequency-law words), feedback filter (7-8), width (4), Link, tap source and BPM/ms switches; the Echo, Bucket Brigade and Gated Verb engines; the reverbs' Expert pages and the Global time.
- Section 11 (likely network or MIDI settings), the rest of section 12, and section 14's tail tables.
- DEEP GEQ models.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-10-30, SQ MixPad 1.6.1, SQ+ MixPad 2.0.3, SQ desk 1.6.3: format notes contributed by markcarlberg (pull request #2).

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.

Cross-desk format notes in this folder are by [markcarlberg](https://github.com/markcarlberg). Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
