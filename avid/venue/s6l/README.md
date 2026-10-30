# Avid VENUE S6L

Covers S6L shows from VENUE 5.0 and later. File extension: `.dsh`.

## Tooling

- [`scripts/s6l_tool.py`](../scripts/s6l_tool.py) reads with `info`, `strips`, `plugins`, `snapshots`, `check` and `json`.
- The same script writes with `edit`: names, faders, colours and rack slot clears. Run `info` first. The `edit:` line says if the show can change.
- Format notes: [`references/S6L-FORMAT.md`](../references/S6L-FORMAT.md). Every fact has an evidence label. Skill: [`SKILL.md`](../SKILL.md).
- Open every edited file in VENUE Standalone with **Filing** > **Load**. Save the file there. Load only that save on a console.

## What we know

- `edit` opens only on VENUE 8.2 shows from an E6L-192 engine with no snapshots.
- Each write passed Filing > Load in VENUE S6L Standalone 8.2.0.187. VENUE's save held every value, and no other node differed beyond three named nodes.
- Limits: 16-character names, faders from -inf or -144 to +12 dB, colours 0 to 8.
- Counts inside the gate: 192 inputs, 80 auxes, 16 groups, 24 matrixes, 3 mains and 48 VCAs. The mains need an L-R plus Mono show.
- A rack slot clear works on an input, group or matrix insert, or a slot that is not routed, with no sidechain key.
- Plug-in racks and AAX SDK default format settings are PROVEN reads. A Channel Strip slot matched the Avid System Guide screenshot.
- Rack and position are PROVEN for positions 1 to 7, and STRONG for positions 8 to 25.
- Parse and write give identical bytes on 23 of 23 private shows from VENUE 7.0 to 8.2. The file has no checksum.
- Engines: `Main Rack Type` 4 is E6L-144, 5 is E6L-192, and 7 is E6L-112. All three are STRONG.
- VENUE converts a 7.x show to 8.2 on load. The converted show then needs VENUE 8.2.

- A contributor's one-change saves in VENUE 8.2 Standalone (markcarlberg) read further fields: mute, safes, pan,
  polarity, delay, direct outs, VCA and mute group membership, filters, dynamics switches and key sources, the output
  patch, preamps and 48V, aux pre points, matrix levels and sources, and the bus split. The tools do not use them yet
  (`references/S6L-FORMAT.md` section 10).
- `Main Rack Type` 8 is E6LX-128, 9 E6LX-176 and 6 E6LX-256, and `Console Type` 5 to 10 is S6L-24, 24D, 32D, 16C,
  24C and 48D. PROVEN for reading by one Standalone save per engine and surface (section 10.10); the tools still
  refuse these engines.
- VENUE 8.0 and 8.1 snapshot streams convert to the 8.2 layout by fixed record rules that reproduce VENUE 8.2's
  resave byte for byte in ten of thirteen pairs (section 10.11).

## What we don't know

- A console load of a written file: not tested. Only VENUE Standalone has loaded these files.
- VENUE 7.0 and 7.2 shows: read-only. No VENUE 7.x Standalone has loaded a written file.
- E6LX engines and which `Console Type` value is which surface: UNVERIFIED.
- Other engines on 8.2, FX returns, PQ strips and L-C-R mains: refused.
- Snapshots: the record is not decoded, so a show with snapshots is read-only.
- The patch: VENUE puts its own patch back, so the tools never write it.
- Preamps, 48 V, the patch source, the output patch, mutes and VCA members: not read.
- HPF, EQ, dynamics and sends: STRONG reads, not load-tested as writes.
- Plug-in settings in other formats: shown as "settings stored" and never changed.
- Slots past rack position 25: the map is not proven.
- The input patch code: a contributor reading says `InputStrip` byte 88 is a u16 block-coded patch code; repo says
  bytes 88 and 89 are a copy and VENUE restores its own patch; needs a save that settles it (section 10.12).
- FX return strips: the contributor's 8.x shows hold none (returns are inputs fed by a rack); section 3 lists the
  array as STRONG. Unsettled.
- Bus HI and LO type bytes, bus makeup, Local input record stride, Stage 4 to 6 outputs, and what each snapshot
  recalls (section 10).

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-10-29, VENUE 8.0.3.1, 8.1.0.216 and 8.2.0.187 Standalone, contributor notes (markcarlberg): strip, bus, matrix, output patch and preamp fields from one-change saves; engine and surface codes; snapshot record framing and the 8.0 to 8.2 rules.
- 2026-10-30, VENUE 8.1.0.216 and 8.2.0.187 Standalone, contributor notes (markcarlberg): 8.1 to 8.2 snapshot rules; snapshot record 235 is built from record 46, not a constant.
