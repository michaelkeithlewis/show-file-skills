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

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*
