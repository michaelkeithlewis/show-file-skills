# Avid VENUE | S6L show file (.dsh) format notes

These notes cover S6L shows (VENUE 5.0 and later). Avid does not publish this format. It was decoded from the
files alone: private S6L shows, Avid's public demo files, and the public AAX SDK documentation. No Avid program
file was disassembled. `scripts/s6l_tool.py` reads everything below and makes only the writes in section 7.

All offsets are 0-based. "u32" is a 4-byte unsigned integer and "i32" a signed one. Numbers in the show tree are
little-endian unless a line says big-endian (BE).

## Evidence labels and tests

Every fact carries one label:

- **PROVEN**: a test gave the result, or a public format source states it. The line names the test.
- **STRONG**: the data fits and nothing contradicts it, but no controlled test was made.
- **UNVERIFIED**: a guess. The line says what would settle it.

The tests the labels name:

| Test | What it is |
|---|---|
| Round trip | Parse a file and write it back. The bytes must be identical. |
| Survey | A script over 23 private S6L shows, counts only: 21 saved on consoles by VENUE 7.0.0 to 7.2.1, one saved by VENUE 7.2 Standalone, one saved on a console by VENUE 8.2.0. All are 96 kHz. |
| Demo files | The 26 demo shows and 2 scope sets in Avid's public VENUE 4.5.3 Standalone installer (saved by VENUE 2.9 and 4.5: D-Show and Profile, SC48, S3L-X). Container and console-family checks only. None are in this repo. |
| Filing > Load | VENUE S6L Standalone 8.2.0.187 on Windows 11. A file written by this code goes into a show folder, loads with **Filing** > **Load**, and is saved at once under a new name. The pages are checked for each change. VENUE's save is then compared node by node with VENUE's save of the unchanged show, made the same way. |
| Engine load | VENUE 8.2 Standalone's show engine alone, with no screen, run under Wine on Linux, loaded a written file as its console state and saved it back. This came first and is weaker than Filing > Load: it also loads a damaged file without complaint. |

The two shows used for Filing > Load: a clean show that VENUE 8.2 Standalone saved itself (an E6L-192 with
nothing on it), and an 8.2 console show from an E6L-192 with no snapshots. Neither is in this repo.

## 1. The container: "Digidesign Storage - 1.0"

```
file   := 0x0A "Digidesign Storage - 1.0" 0x00  value value
value  := type:u8 payload
```

| Type | Payload | Label |
|---|---|---|
| `0x01` | u8, used as a boolean | PROVEN (round trip) |
| `0x02` | i8 | UNVERIFIED: never seen, size assumed |
| `0x03` | u8 | PROVEN (round trip) |
| `0x04` | 16-bit | PROVEN size (round trip on VENUE 2.9 demo shows only) |
| `0x05` | u16 | UNVERIFIED: never seen |
| `0x06` | i32 | PROVEN (round trip) |
| `0x07` | u32 | PROVEN (round trip) |
| `0x08` | i64 | UNVERIFIED: never seen |
| `0x09` | u64, also a Windows FILETIME | PROVEN (round trip) |
| `0x0A` | C string, NUL-terminated, Windows-1252 | PROVEN (round trip) |
| `0x0B` | dictionary: u32 count, then count x (`0x0A` key string, value) | PROVEN (round trip) |
| `0x0C` | array: u8 element type, u32 count, then count x value; each element repeats its type byte | PROVEN (round trip) |
| `0x0D` | blob: u32 length, then that many raw bytes | PROVEN (round trip) |

- Parse and write give identical bytes on 23 of 23 private shows (VENUE 7.0 to 8.2) and 28 of 28 demo files
  (VENUE 2.9 and 4.5). PROVEN (round trip).
- A file has two top-level values, both dictionaries: the header (47 keys in VENUE 7, 48 in VENUE 8) and the body
  (41 to 53 keys). PROVEN (survey).
- Dictionary keys are sorted by the value's type byte, then by the key bytes in ASCII order: booleans first, then
  numbers, strings, dictionaries, arrays and blobs. PROVEN on 5606 of 5606 dictionaries (survey). Whether VENUE
  needs this order on load is UNVERIFIED. A writer keeps it.
- No checksum. PROVEN (Filing > Load: every loaded file had blob bytes changed and no checksum updated, the Info area
  was blue, and VENUE kept every written value).
- No compression at the top level. Snapshots are compressed one by one (section 5).
- Blobs carry explicit lengths, so a blob can grow or shrink and the container stays valid. Most show data sits in
  blobs with positional layouts that change between software versions: `InputStrip` is 225 bytes in VENUE 7 and
  233 bytes in VENUE 8. PROVEN (survey).
- Classic VENUE shows (D-Show, Profile, SC48) and S3L-X shows use the same container. PROVEN (round trip on the
  demo files). `FORMAT.md` in this folder predates this file; where the two disagree, this file wins.

## 2. The header (top-level value 0)

| Key | Type | Meaning | Label |
|---|---|---|---|
| `File Type` | string | "Digidesign D-Show File" for a show; a scope set says so here | PROVEN (survey, demo files) |
| `File Created by` | string | the software that saved the file, for example "VENUE 8.2.0.187" | PROVEN (survey) |
| `Version` | i32 version word | the header schema | STRONG |
| `Full Support SW Version` | i32 version word | the software level the show needs | STRONG |
| `Partial Support SW Version` | i32 version word | 5.0 on every S6L show, 2.0 on classic shows | PROVEN (survey, demo files) |
| `Last Known As` | string | the show's path on the machine that saved it, no extension | PROVEN (survey; Filing > Load rewrites it) |
| `Last Load Time` | u64 | Windows FILETIME (100 ns steps since 1601-01-01 UTC) | STRONG |
| `User Comment` | string | the show comment | STRONG |
| `Main Rack Type` | i32 | the engine (table below) | see the table |
| `Channel Count` | i32 | input channels of the engine | PROVEN against the engine table on every sample |
| `DSP Card count` | i32 | HDX cards for plug-ins | STRONG |
| `Bus count`, `Group count`, `Matrix count`, `VCA count`, `VCA count v2`, `FX Returns count`, `Graphic EQ count` | i32 | mix configuration | STRONG |
| `LCR not LRM` | number | 0 is L-R plus Mono; any other value is taken as L-C-R | STRONG: 0 in every sample, and VENUE shows those mains as L-R plus Mono (Filing > Load) |
| `Sample Rate` | i32 | 96000 in every sample | PROVEN (survey) |
| hardware flags (`MTS Screen Present`, `RTX Present`, ...) | boolean | many are left over from older consoles | STRONG for some, UNVERIFIED for most |
| `Bus Config Mode`, `Stage Config`, `Input Source 1` and others | number | | UNVERIFIED |

A **version word** is an i32 whose bytes, low to high, are `01`, `x`, minor, major. `01 00 02 08` is 8.2. Major and
minor are PROVEN against `File Created by` on every sample. Byte `x` is 0 in every sample, including shows saved by
7.0.1 and 7.2.1, so it is not the patch level (meaning UNVERIFIED). In an 8.2 show `Version` reads 8.0 and
`Full Support SW Version` reads 8.2. Read the software level from `Full Support SW Version`.

**Console family.** Read `File Created by`, `Main Rack Type` and the body's `Devices Configuration/Console Type`:

| Family | Software | `Main Rack Type` | `Console Type` | Label |
|---|---|---|---|---|
| D-Show or Profile with FOH Rack | VENUE 2.9 | 0 | 2 | PROVEN (9 demo shows) |
| SC48 | VENUE 2.9 | 2 | 3 | PROVEN (2 demo shows) |
| S3L-X | VENUE 4.5 | 3 | 4 | PROVEN (15 demo shows) |
| S6L | VENUE 5.0 or later | 4, 5, 7 seen | 5, 6, 7, 9 seen | PROVEN (survey) |

A major version of 5 or more with an S6L engine means S6L. Which `Console Type` value is which S6L surface (16C,
24C, 24D, 32D, 48D) is UNVERIFIED; one VENUE Standalone save per simulated surface would settle it.

**Engine.**

| `Main Rack Type` | Engine | Label |
|---|---|---|
| 4 | E6L-144 | STRONG: 15 samples, all with 144 inputs and 16 matrixes, as Avid's engine table gives for E6L-144 |
| 5 | E6L-192 | STRONG: 5 samples, all with 192 inputs and 24 matrixes; the Standalone's own saves (it simulates an E6L-192: 192 inputs, 80 auxes, 16 groups, 24 matrixes, 48 VCAs) also hold 5 |
| 7 | E6L-112 | STRONG: 3 samples, 112 inputs and 16 matrixes |
| 1, 6, 8 and up | E6LX-128, E6LX-176, E6LX-256 and others | UNVERIFIED: no sample. A Standalone save per simulated engine would settle it |

## 3. Strips

`All Strips` in the body holds one array per strip kind. Each element is a dictionary of blobs:

| Array | Kind | Blobs | Label |
|---|---|---|---|
| `MicLine Strips` | inputs | `AudioStrip`, `BusAssigns`, `InputStrip`, `MicLineInputStrip`, `Strip` | PROVEN (survey) |
| `FX Return Strips` | FX returns | as seen in the samples | STRONG |
| `Aux Strips`, `Group Strips` | auxes, groups | `AudioMasterStrip`, `AudioStrip`, `BusAssigns`, `Strip` | PROVEN (survey) |
| `Matrix Strips v2.5` | matrixes | `AudioMasterStrip`, `AudioStrip`, `MatrixMasterStrip v2.5`, `Strip` | PROVEN (survey) |
| `LCR Strips` | mains | `AudioMasterStrip`, `AudioStrip`, `LCRMasterStrip`, `Strip` | PROVEN (survey) |
| `PQ Strips v2.5` | PQ strips | | STRONG |
| `VCA Strips` | VCAs | `Strip` only | PROVEN (survey) |

The array lengths are not the engine size: one sample has 133 input strips on a 144-input engine. A stereo strip
uses one element. PROVEN (survey).

**Mains.** In an L-R plus Mono show, `LCR Strips` element 0 is Left, 1 is Right and 2 is Mono, and VENUE shows them
in the order Left, Mono, Right. PROVEN (Filing > Load). The element order of an L-C-R show is UNVERIFIED: no L-C-R
show was loaded.

### 3.1 `Strip` record (every kind)

| Offset | Size | Meaning | Label |
|---|---|---|---|
| 0 | u8 | 1 = stereo strip | STRONG (stereo-sounding names only). Never written by the tools |
| 1 | C string | the name, Windows-1252 | PROVEN (Filing > Load: every name showed on the Inputs, Outputs and Patchbay pages) |
| n | 5 bytes | flags; two of them change often between saves (mute or solo are candidates) | UNVERIFIED |
| n+5 | i32 | fader in 0.1 dB, -1440 = minus infinity | PROVEN (Filing > Load: every value showed under its fader, -INF for -1440) |
| n+9 | u8 | 1 on most strips | UNVERIFIED |
| n+10 | u8 | colour number, 0 to 8 (table below) | PROVEN on VENUE 8.2 (Filing > Load); STRONG on 7.x |
| n+11 | about 20 bytes | constant on most strips | UNVERIFIED |

`n` is the offset just after the name's NUL byte, so the record grows and shrinks with the name.

- A name holds 16 characters. PROVEN (engine load): VENUE cut names of 17 and 24 characters to 16.
- ASCII and `ö` (`0xF6`) load as written. PROVEN (Filing > Load). Bytes `0x80` to `0x9F` were never loaded, and no
  sample holds one, so the tools refuse them; typographic quotes, dashes and the ellipsis are folded to ASCII first.
  The other Latin-1 letters (`0xA0` to `0xFF`): STRONG.
- The fader tops out at +12.0 dB. PROVEN (engine load): VENUE rewrote +20.0 dB to +12.0 dB and -200 dB to -inf.
- VENUE rewrote colour numbers 9 and 200 to 8. PROVEN (engine load).
- The record layout is the same on mono and stereo strips, and names, faders and colours written to stereo inputs,
  auxes, groups and matrixes were kept. PROVEN (engine load).

**Colours.** The colour each number shows as on VENUE 8.2's Overview page, measured from its screen:

| Number | Colour | RGB |
|---|---|---|
| 0 | grey (no colour) | 51, 51, 51 |
| 1 | green | 21, 171, 21 |
| 2 | blue | 21, 21, 171 |
| 3 | yellow | 171, 151, 21 |
| 4 | orange | 153, 84, 35 |
| 5 | cyan | 21, 171, 171 |
| 6 | purple | 105, 21, 136 |
| 7 | red | 171, 21, 21 |
| 8 | white | 171, 171, 171 |

PROVEN (Filing > Load) for every number on inputs, auxes, groups, matrixes and VCAs, and for 0, 1, 2 and 7 on the
mains. FX returns, PQ strips, the other mains numbers and VENUE 7.x shows: STRONG (the same palette by inference).
Inputs of one instrument family share one number in the samples.

### 3.2 `InputStrip` record (inputs)

- Bytes 24 to 79: four EQ bands of 14 bytes, stored high band first. A band is u8 on, u8 band type, i32 gain in
  0.1 dB, i32 frequency in Hz, i32 Q x 100. The defaults are 10000, 5000, 1000 and 200 Hz at 0 dB and Q 1.00.
  STRONG (the defaults repeat on every unused input, and the used values are sane EQ values). The meaning of the
  band type values 0 and 1 is UNVERIFIED.
- Byte 88: input port (0-based). Byte 89: a source device code (0, 1, 2, 3 and 5 seen). STRONG as a read: on a
  console sample the ports run 0, 1, 2 in strip order and a stereo input takes two ports. These two bytes are a
  copy, not the patch itself. PROVEN (engine load): VENUE put its own patch back after they were changed. Where the
  patch lives, and which device each code means, is UNVERIFIED.
- Bytes 96 to 140 hold 4-byte values that track the `BusAssigns` levels. Meaning UNVERIFIED.

### 3.3 `MicLineInputStrip` record (inputs; 101, 105 or 133 bytes)

Decoded from value ranges over 3040 input strips in the survey. The six compressor values and the six gate values
on an unused input equal the values of Avid's built-in default compressor and default gate presets.

| Offset | Size | Meaning | Range in the survey | Label |
|---|---|---|---|---|
| 0 | u8 | 0 or 1 (polarity is a candidate) | 0 to 1 | UNVERIFIED |
| 1 | i32 | high-pass filter, Hz | 20 to 500 | STRONG |
| 5 | u8 | 1 on almost every input | 0 to 1 | UNVERIFIED |
| 6 | u8 | 1 on 589 of 3040 inputs (compressor in is a candidate) | 0 to 1 | UNVERIFIED |
| 7 | i32 | compressor threshold, 0.1 dB | -40.0 to +20.0 dB | STRONG |
| 11 | i32 | compressor ratio x 100 | 1.25:1 to 100:1 | STRONG |
| 15 | i32 | compressor attack, microseconds | 100 us to 200 ms | STRONG |
| 19 | i32 | compressor release, ms | 10 to 858 | STRONG |
| 23 | i32 | compressor knee, 0 (hard) to 100 (soft) | 0 to 100 | STRONG |
| 27 | i32 | compressor gain, 0.1 dB | -20.6 to +8.5 dB | STRONG |
| 48 | i32 | gate threshold, 0.1 dB | -60.0 to +12.8 dB | STRONG |
| 52 | i32 | gate ratio x 100 (10000 is a gate, lower is an expander) | 1.25:1 to 100:1 | STRONG |
| 56 | i32 | gate attack, microseconds | 20 us and up | STRONG |
| 60 | i32 | gate release, ms | 27 to 1969 | STRONG |
| 64 | i32 | gate hold, ms | 10 to 990 | STRONG |
| 68 | i32 | gate range, 0.1 dB | -80.0 to -0.1 dB | STRONG |
| 89 | i32 | 20000 on most inputs (low-pass filter is a candidate) | up to 20000 | UNVERIFIED |
| 102 to 104 | 3 bytes | rewritten by VENUE when a bus-fed plug-in that returns to this input was cleared | | PROVEN that VENUE rewrites them (engine load); meaning UNVERIFIED |

### 3.4 `AudioMasterStrip` record (auxes, groups, matrixes, mains; 297 or 309 bytes)

The 14-byte EQ band of section 3.2 sits at offsets 14, 28, 42, 56, 111, 125 and 139: the seven output EQ bands.
The six-value compressor block of section 3.3 sits at offset 71. STRONG (all 1301 output strips in the survey hold
sane values there). Which band is which, and bytes 95 to 110, are UNVERIFIED.

### 3.5 `BusAssigns` record (sends)

- u32 count, then count entries of 6 bytes. The count equals the number of aux strips plus group strips. PROVEN
  (survey, 23 of 23).
- Entry bytes 4 and 5: i16 send level in 0.1 dB, -1440 = off. STRONG for the aux entries (two saves of one monitor
  show differ only in these bytes).
- The entries after the auxes belong to the groups. VENUE writes their level bytes as 0 in one save and as -inf in
  the next. PROVEN (engine load). So they are assigns, not send levels, and the tools do not read them as sends.
- Entry bytes 0 to 3 (on, pre or post, pan): UNVERIFIED.

### 3.6 Not decoded yet

| Data | Where it probably lives | Label |
|---|---|---|
| Mic preamp gain, pad, 48 V | the per-port arrays `Input Gains`, `Input Gains Stage64` and siblings | UNVERIFIED |
| The input patch source | not found (bytes 88 and 89 of `InputStrip` are a copy) | UNVERIFIED |
| The output patch | `Output Routing` (an array of 1912 i32) | located, not decoded |
| Matrix levels | `MatrixMasterStrip v2.5` | located, not decoded |
| VCA and mute group membership | not found | UNVERIFIED |
| Recall safe, events, graphic EQs, surface layouts | `RecallSafe v02`/`v03`, `Events List 2`/`3`, `31-Band EQs`, `User Strip Layout` | located, not decoded |

VENUE writes some data twice for older software (`Effects Main Routing 2` and `3`, `RecallSafe v02` and `v03`,
`Events List`, `2` and `3`). A writer must keep the copies in step. Which copy each software version reads is
UNVERIFIED.

## 4. Plug-ins

S6L runs 64-bit AAX DSP plug-ins only (Avid S6L System Guide, p391). The show stores each plug-in's state as the
plug-in's own chunks. VENUE stores them and hands them back to the plug-in. VENUE Standalone has no plug-in code, so
it can place and route a plug-in but can not show or change its settings.

| Location in the body | Content | Label |
|---|---|---|
| `Plug-In PatchBay/Effect Type List` | one blob per plug-in type (each mono, stereo or mono-to-stereo variant is its own type) | PROVEN (survey) |
| `Plug-In PatchBay/Rack Assignments` | exactly 400 blobs, one per rack slot; an empty blob is an empty slot | PROVEN (survey, 23 of 23) |
| `Effects Main Routing 2` (and `3` in VENUE 8) | 400 i32 routing words, one per slot | PROVEN (survey) |
| `Effects SideChain Routing` (and `2` in VENUE 8) | 400 i32 sidechain key words, one per slot | PROVEN (survey) |
| `Console Options/Rack Column Names` | the five rack names, NUL-separated | STRONG |
| each snapshot, and VENUE 8 `Current State` | copies of slot chunks | PROVEN (section 5) |

### 4.1 `Effect Type List` entry

| Part | Layout | Label |
|---|---|---|
| name | C string | PROVEN (survey) |
| family | C string, the product name | PROVEN (survey) |
| type IDs | 12 bytes: manufacturer, product and plug-in ID. Each is a u32 stored little-endian, so the four characters read backwards in a hex dump (`DIVA` is "AVID") | PROVEN (survey) |
| channels | u32 inputs, u32 outputs | STRONG |
| stems | u32 input stem, u32 output stem: 0 mono, 1 stereo, 2 LCR, 3 LCRS, 4 quad, 5 is 5.0, 6 is 5.1 | STRONG |
| field 5 | u32, often `0x80000000` | UNVERIFIED |
| category | u32 bits. The bits set in the survey: `0x1` EQ, `0x2` Dynamics, `0x4` Pitch Shift, `0x8` Reverb, `0x10` Delay, `0x20` Modulation, `0x40` Harmonic, `0x80` Noise Reduction, `0x200` Sound Field, `0x2000` Effect. The tools print any other set bit as hex | PROVEN against the category enum of the public AAX SDK |
| flags | 5 bytes | UNVERIFIED |

Every used slot has an entry: 1120 of 1120. PROVEN (survey).

### 4.2 `Rack Assignments` slot record

```
offset 0    12 bytes   type IDs (as in the type list)
offset 12   u8         flag A, 1 on 1091 of 1120 used slots
offset 13   u8         flag B, 0 or 1
offset 14   u32        length L of the rest
offset 18   L bytes    zero or more plug-in chunks, back to back
```

For all 1120 used slots in the survey, 18 + L is the blob length and the chunks fill L exactly. PROVEN (survey).
Flags A and B are probably active and bypass: UNVERIFIED (one Standalone save with a slot bypassed would settle
it). A slot with no chunks (L = 0) is a plug-in placed with no stored state; VENUE Standalone writes such slots.
PROVEN (survey: 8 slots, all in the Standalone-saved show).

A chunk record:

```
i32      size: the whole record, this 56-byte header included
i32      version: -1 for the AAX default chunk
u32 x 3  manufacturer, product and plug-in ID (little-endian type IDs)
u32      chunk ID (little-endian type ID, for example 'elck')
32 bytes the chunk name, NUL-padded, for example "Complete Controls State"
...      the data: size - 56 bytes
```

The size counts the header: PROVEN by the exact walk of every slot. The IDs inside a chunk can name another variant
than the slot (a stereo slot with a chunk made by the mono variant): 59 slots in the survey, all written by VENUE.
STRONG that VENUE accepts that.

### 4.3 The AAX SDK default chunk format

468 of the 1120 used slots start with a chunk in the default format of the public AAX SDK (chunk ID `elck`, or
`Infl` once). 446 slots hold only that format. PROVEN (survey).

```
4 bytes   01 01 01 01       version mark
entries:  a type character, '_', the parameter ID, NUL, zero pad to a multiple of 4, then the value:
   'd'  double, 8 bytes BE
   'f'  float, 4 bytes BE
   'l'  int32, 4 bytes BE (ints and switches)
   's'  int16, 2 bytes BE, then 2 pad bytes
   'r'  a NUL-terminated string, padded to 4
```

The parameter IDs are the plug-in's own names for its controls, and the values are in real units (Hz, dB,
seconds). PROVEN: a strict decoder walks every default-format chunk in the survey to its last byte, and a Channel
Strip slot in a private show decodes to the exact values that Avid's System Guide screenshot on p399 shows.

The tools read this format only. A setting change needs a console test per plug-in family and is not in
`s6l_tool.py`.

### 4.4 Every other chunk format

The other first chunks in the survey are a legacy format (chunk ID `All `, 363 slots) and vendor formats. They are the plug-in maker's own data. The tools and the site never decode or change them: they are
listed as "settings stored" and copied byte for byte.

### 4.5 The routing word (`Effects Main Routing 2`)

```
0x0000000F               slot not routed
bits 31..26  type: 1 input, 3 aux, 4 group, 5 matrix; plus 0x10 for a bus-fed slot
bits 25..18  strip index, 0-based, within that kind
bits 17..16  sub field: 0 for an insert, 2 for a bus-fed slot
bits 15..0   insert: the insert position, 0-based (0 to 4 seen; STRONG)
             bus-fed: the return strip, high byte its type, low byte its index
```

- Types 1, 3, 4, 5 and bus-fed slots: PROVEN (survey: 874 of 881 routed slots point at a named strip of that kind).
- Types 6 and 7 (7 index 0 hits the first mains strip), and a bus-fed word with no return strip: UNVERIFIED.
- Avid gives 4 inserts per channel on an E6L engine and 8 on an E6LX. The survey uses positions 1 to 5. One input
  word holds 15 in its position field; the tools treat any position past 5 as not decoded.
- In VENUE 8, `Effects Main Routing 3` holds the same 400 words. PROVEN (the 8.2 sample and the Standalone's own
  saves).

### 4.6 The sidechain key word

`Effects SideChain Routing` (and `2` in VENUE 8) holds `0x10000000` for "no key" on every empty slot (8080 of 8080
in the survey, and all 400 in the Standalone's own saves). PROVEN (survey). Other values are a key source, not decoded (UNVERIFIED).

### 4.7 Rack and slot numbers

S6L has five racks of 80 slots. The slot index is not rack-major. Slots 0 to 124 are racks 1 to 5 in blocks of 25:
rack = slot / 25 + 1, position = slot mod 25 + 1. PROVEN (Filing > Load: all 34 used slots of an 8.2 console show
showed at that rack and position on the Plug-Ins page, positions 1 to 7 of all five racks); positions 8 to 25:
STRONG. Slots 125 to 399 are used in eight samples, and their map is UNVERIFIED (positions 26 to 80 in rack order is
the leading guess; a plug-in placed at rack 2 position 30 in the Standalone would settle it).

### 4.8 Clearing a slot

A clear writes four things: the slot blob becomes empty, both routing words of the slot become `0x0000000F`, and
both sidechain key words become `0x10000000`. PROVEN (Filing > Load: four slots cleared in an 8.2 console show, an
input insert, a group insert, a matrix insert and a slot that was not routed, showed empty on the Plug-Ins page,
and every other slot kept its plug-in and strip). VENUE keeps the reset sidechain words. PROVEN (engine load: a
cleared slot that had a key, on a 7.2 show that VENUE 8.2 converted on load). The four Filing > Load slots had no key.

Not cleared by the tools:

- A bus-fed slot. PROVEN (engine load): VENUE rewrote bytes 102 to 104 of the input that takes the plug-in's return.
- An aux insert or a slot with a sidechain key on VENUE 8.2: only 7.2 engine loads cleared them.
- A slot that a snapshot or VENUE 8 `Current State` keeps a copy of (section 5).
- Slots past position 25 (the map is not proven).

### 4.9 Plug-in findings that the tools do not use yet

- VENUE drops the routing of a plug-in variant whose channel count does not match the strip (a stereo variant on
  a mono input). PROVEN (engine load).
- VENUE Standalone loaded and kept a slot with no stored state, and an edited default-format chunk, byte for byte.
  PROVEN (engine load). That proves the file loads, not that a plug-in on a console accepts the chunk. Placing,
  copying and editing plug-ins wait for a console test.
- The AAX SDK's VENUE guide limits a plug-in's chunks to 64 KB. VENUE 7.x wrote a 96,036-byte record, so the limit
  is not enforced in the file. PROVEN (survey).
- More routing-word detail is in section 10.9, and plug-in state notes are in [`plugins.md`](plugins.md).

## 5. Snapshots

- `Snapshot List Compressed` is an array of blobs, one zlib stream (header `78 01`) per snapshot. PROVEN (survey:
  241 of 241 inflate).
- An inflated snapshot starts with u8 0, a u32 length, and the snapshot name as a C string. The length is the name
  length + 25 in 237 of 242 records (the 241 snapshots and one VENUE 8 `Current State`, which starts the same way).
  PROVEN (survey).
- A snapshot holds a plug-in record for each slot in its plug-in scope:

  ```
  u32      slot number, 1-based
  4 bytes  UNVERIFIED
  'L'      one byte, 0x4C
  u32      length
  chunks   the same chunk records as the rack slot
  ```

  PROVEN (survey): 1522 records decode, each with the plug-in and chunk IDs of its rack slot. 1054 are identical to
  the rack copy and 468 hold their own settings. One sample stores each record twice (reason UNVERIFIED).
- VENUE 8 adds `Current State`: a blob in the same record format, not compressed. STRONG. In the 8.2 sample every
  slot it holds is bus-fed (7 slots, 21 records), and each copy equals the rack copy.
- The rest of the snapshot record (scope bit fields, strip data) is UNVERIFIED. Until it is decoded, every snapshot
  may hold its own copy of any strip or slot, and a change to the strip or the rack lasts only until the next recall.
  So the tools change nothing in a show that has snapshots.
- Related keys: `Last Recalled Snapshot` (i32, -1 = none), `Snapshot Selection Set 3`, `Playlist`.

## 6. What VENUE does on load and save

All PROVEN by Filing > Load or engine load on VENUE 8.2 Standalone:

1. VENUE takes names, faders and colours from the `Strip` record, not from `Current State`, and rewrites
   `Current State` to match. A writer needs only the `Strip` record.
2. After Filing > Load and a save, only `Last Load Time`, `Last Known As` (the path VENUE loaded the show from) and
   `Current State` differ from VENUE's save of the unchanged show. `File Created by` stays.
3. VENUE converts a 7.x show to 8.2 on load. A converted show then needs VENUE 8.2.
4. A show for another engine is fitted to the simulated E6L-192: strips past its counts are dropped. VENUE shows a
   note for a show made for another configuration, then reconfigures and restarts when it loads.
5. VENUE lists only shows inside a show folder. The Info area colour: blue is the same configuration, orange loads
   with differences, red can not load in full (System Guide p313).
6. The engine reads around damage: a `Strip` record cut to 3 bytes still loaded. "It loaded" proves nothing alone;
   the value compare does.

## 7. The writes in `s6l_tool.py` and how each was proven

The tool opens these writes only on VENUE 8.2 shows from an E6L-192 with no snapshots, inside the E6L-192 counts
(192 inputs, 80 auxes, 16 groups, 24 matrixes, 3 mains, 48 VCAs), and on the mains only in an L-R plus Mono show.

| Write | Bytes changed | Strip kinds or slot kinds | Proof |
|---|---|---|---|
| Rename | the name in the `Strip` record (the record length changes) | inputs, auxes, groups, matrixes, mains, VCAs | Filing > Load on the clean show (5 inputs, the 3 mains, and the first and last aux, group, matrix and VCA) and on the console show (inputs, a stereo input, an aux, a stereo group and matrix): every name on the Inputs, Outputs and Patchbay pages; VENUE's save held them |
| Fader | i32 at n+5 of the `Strip` record | the same six kinds | Filing > Load: 14 strips of all six kinds on the clean show, plus inputs and stereo strips on the console show; every value under its fader |
| Colour | u8 at n+10 of the `Strip` record | the same six kinds | Filing > Load: every number but the show's own on strips 1 to 8 and the last strip of each kind; a script read each colour chip of the Overview |
| Clear a slot | the slot blob, both routing words, both sidechain words | input, group and matrix inserts, and slots not routed, with no sidechain key | Filing > Load: four slots on the console show (section 4.8) |

Each Filing > Load run also passed the strict compare: VENUE's save of the written file held every value, and no
other node differed from VENUE's save of the unchanged show beyond the three in section 6. A second Filing > Load of
the same file in a new VENUE session gave the same result.

Not written, with the reason:

- 7.0 and 7.2 shows: no VENUE 7.x Standalone has loaded a written file natively. 7.2 writes passed through VENUE
  8.2's conversion only.
- Other engines on 8.2: no 8.2 load used one.
- FX returns and PQ strips: no loaded show had them.
- The mains of an L-C-R show: none was loaded.
- The input patch: VENUE put its own patch back (section 3.2).
- Mutes, HPF, EQ, dynamics, sends: not load-tested yet.
- Snapshots and VENUE 8 `Current State`: the snapshot record is not decoded.
- Plug-in placement, copies and settings: the Standalone runs no plug-ins, so these wait for a console test.

## 8. Where shows go

- VENUE USB stick: `D-Show/Consoles/VENUE/Shows/<show folder>/<show>.dsh`. PROVEN (a VENUE stick).
- On a console: `D:\D-Show\User Data\Shows\<show folder>\<show>`. PROVEN (`Last Known As` in 21 console samples).
- VENUE Standalone: `Documents\D-Show\User Data\Shows\<show folder>\`. PROVEN (Filing > Load).
- A scope set (`.scs`) uses the same container, with its own `File Type`. PROVEN (2 demo files).

## 9. Open questions

| Question | What settles it |
|---|---|
| Does VENUE need the sorted key order on load? | Load a file with two keys swapped |
| Which `Console Type` value is which surface? | One Standalone save per simulated surface |
| `Main Rack Type` of the E6LX engines | One Standalone save per simulated engine |
| The slot flag bytes, field 5 of a type entry, routing types 6 and 7, sidechain values | Single-change saves in the Standalone, diffed node by node |
| The slot map past rack position 25 | A plug-in placed at rack 2 position 30 |
| The rest of the snapshot record and the 4 unknown bytes of a plug-in record | Single-change snapshot saves |
| Preamps, the patch source, the output patch, matrix levels, VCA and mute group membership | Single-change saves |
| Do mutes, HPF, EQ, dynamics and sends load as written? | A Filing > Load run per field |
| Does a VENUE 7.2 Standalone load the same writes natively? | The same runs in VENUE 7.2 Standalone |
| Does a console keep the chunk of a plug-in it lacks when it re-saves? | Load and re-save such a show on a console |

## 10. Contributor findings on VENUE 8.0, 8.1 and 8.2 (markcarlberg)

These findings come from a second set of shows and a second test method. The tools do not use them yet. The labels
keep the meaning of the section at the top, and the tests are:

| Test | What it is |
|---|---|
| One-change save | Change one control in VENUE S6L Standalone 8.2.0.187, save, and compare the bytes with the save before the change. |
| Patched load | Patch a few blob bytes in a file, load it in VENUE Standalone, and read the value on VENUE's screen. |
| Production set | Eleven production shows: ten saved by VENUE 8.0.3.1 and one by 8.1.0.216, all from an S6L-24D on an E6L-144. Consistency only. None are in this repo. |

Where a finding disagrees with sections 1 to 9, the earlier section stands and the difference is listed in
section 10.12.

### 10.1 Blob sizes by version

| Blob | 8.0 | 8.1 | 8.2 |
|---|---|---|---|
| `Strip` | 41 + name | | 41 + name |
| `AudioStrip` (strip in no VCA) | 86 | 102 | 102, plus 4 per VCA |
| `InputStrip` | 225 | 233 | 233 |
| `MicLineInputStrip` | 105 | 113 | 133 |
| `AudioMasterStrip` | 297 | 301 | 309 |
| `BusMasterStrip` | 1 | 6 | 6 |
| `MatrixMasterStrip v2.5` | 1376 | 1632 | 1632 |

A newer blob is the older blob with bytes added at the end, so an offset holds on 8.0, 8.1 and 8.2 up to each
blob's length. PROVEN (one-change saves on 8.0 and 8.2 shows). An aux strip and a group strip differ only in their
default colour. PROVEN (one-change save). A cleared default show stores every input strip of the engine; a
production show stores only the strips in use. STRONG (production set).

### 10.2 `Strip` record fields

Offsets use `n` from section 3.1 (the byte after the name's NUL).

| Offset | Meaning | Label |
|---|---|---|
| n | strip selected on the surface (not a mix setting) | PROVEN (one-change save) |
| n+1 | mute | PROVEN (one-change save) |
| n+3 | Channel Safe S (solo safe, inputs only) | PROVEN (one-change save) |
| n+4 | Channel Safe A (automation safe) | PROVEN (one-change save) |
| n+14 | Channel Safe B (bank safe) | PROVEN (one-change save) |
| n+21 | the bank safe's fader, -1 = none | PROVEN (one-change save) |

There is no mute safe. The colour numbers of section 3.1 carry these names in VENUE's Set Channel Color menu:
0 No Color, 1 Green, 2 Blue, 3 Yellow, 4 Amber, 5 Aqua, 6 Violet, 7 Red, 8 White. The stock colour per kind:
inputs Green, auxes Violet, groups Amber, mains Red, matrixes White, VCAs Blue. PROVEN (one-change saves).

### 10.3 `AudioStrip` (inputs; buses share the early fields)

| Offset | Meaning | Label |
|---|---|---|
| 0 | pan, i32 -100 to +100 (also a mono aux's or group's pan) | PROVEN (one-change save) |
| 4 | stereo BAL/WIDTH width in percent, default 100 | STRONG |
| 8, 9, 10 | L-R assign, C/Mono assign, polarity | PROVEN (one-change save) |
| 11, 12 | delay in; delay as u16 samples at 48 kHz (0 to 250 ms) | PROVEN (one-change save) |
| 16, 21 | direct out in; direct out level, i32 in 0.1 dB, up to +12 dB | PROVEN (one-change save) |
| 25 | mute groups 1 to 8, one bit each | PROVEN (one-change save) |
| 26 | VCAs 1 to 8, one bit each, on 8.0 | STRONG on 8.0. VENUE 8.2 ignores it on load and writes 0 there |
| 45 | u32 count, then that many VCA numbers, 0-based | PROVEN (one-change save; VENUE 8.2 loads membership from this list) |
| after the list | u32 2, mute groups 1 to 64 as 64 bits, then the delay as u16 samples at 96 kHz | PROVEN (one-change save) |

- With no VCA the 96 kHz delay is at byte 61. Each VCA adds 4 bytes and moves what follows. One delay edit changes
  both delay fields. PROVEN (one-change save).
- Direct out pickoff, 33 bytes after the VCA list: 0 Top Of Channel, 8 True Gain, 1 Insert Return, 2 Pre-Fader
  Post-Mute, 6 Post-Fader. VENUE also writes 1 and 2 at bytes 17 and 41. PROVEN on the 8.1 and 8.2 layout.
- Byte 27: 5 on one strip, 1 elsewhere. Meaning UNVERIFIED.

### 10.4 `InputStrip` and `MicLineInputStrip` fields

`InputStrip`:

| Offset | Meaning | Label |
|---|---|---|
| 0 | INPUT DIRECT (bypasses EQ, dynamics, inserts) | PROVEN (one-change save) |
| 1 | changes with a group assign | PROVEN that it moves; meaning UNVERIFIED |
| 21, 22 | EQ in (out by default); EQ mode, 0 digital, 1 ANALOG | PROVEN (one-change save) |
| 84 | u16 strip id, counting up from 0x02a0 | STRONG |
| 92 to 215 | 10-byte records (on, pre, i16 level in 0.1 dB) for the L and R legs of sends to stereo auxes | STRONG |
| 216, 217, 221 | HEAT in; DRIVE i32 (default 0); TONE i32 (default 3) | PROVEN (one-change save) |
| 229, 231 | 8.2 copies of bytes 88 and 90 | PROVEN (one-change save) |

The records at 92 are a cache. VENUE rebuilds them from `BusAssigns` on load and save and plays the sends from
`BusAssigns`. PROVEN (one-change save). This fits section 3.2, which saw bytes 96 to 140 track `BusAssigns`.

EQ band type (section 3.2 left it UNVERIFIED): on the HI and LO bands, 1 is shelf (the default) and 0 is peak. HM
and LM have no shape switch. PROVEN (one-change save: the shape switch to peak moved 1 to 0; the name "shelf" is
VENUE's screen in that save). Avid's guide calls bell the HI and LO default, which the bytes do not match. Range
+/-18 dB, 20 Hz to 20 kHz, Q 0.10 to 10.00. In ANALOG mode HI and LO become fixed shelves with type 0 and Q field
20, LO snaps to an analog step (311 Hz became 200 Hz), and a mid's Q field holds its B/W as 1/Q. PROVEN (one-change
save).

`MicLineInputStrip` (fills in the UNVERIFIED rows of section 3.3):

| Offset | Meaning | Label |
|---|---|---|
| 0 | HPF in (polarity is `AudioStrip` byte 10) | PROVEN (one-change save) |
| 5 | order: 1 dynamics before EQ (default), 0 EQ PRE DYN | PROVEN (one-change save) |
| 6, 47 | Comp/Lim in, Exp/Gate in | PROVEN (one-change save) |
| 31, 32 / 72, 73 | key HPF in, i32 Hz (default 10), for Comp/Lim / Exp/Gate | PROVEN (one-change save) |
| 36, 37 / 77, 78 | key LPF in, Hz (default 20000) | PROVEN (one-change save) |
| 41 / 82 | Sidechain switch | PROVEN (one-change save) |
| 43 / 84 | key source, 4 bytes | PROVEN (one-change save) |
| 88, 89 | LPF in, u32 Hz (default 20000) | PROVEN (one-change save) |
| 102 to 104 | the plug-in rack that feeds the input: `30 0A 20` is "Pl 3-4", 0x10 more for each later pair; the input's patch is then None. This is how an S6L marks an FX return | STRONG |
| 105, 109 | 8.2 copies of the two key sources | PROVEN (one-change save) |

Ranges from VENUE's clamps: Comp/Lim threshold -40 to +20 dB, Exp/Gate threshold -60 to +20 dB, ratio 1.25:1 to
100:1 (100:1 is the gate; lower is an expander; VENUE resaves 1:1 as 1.25:1), Comp attack 100 us to 100 ms, gate
attack 20 us to 100 ms, release and hold 10 ms to 4 s, makeup -40 to +20 dB, gate range 0 to -80 dB. Thresholds are
dBFS on screen; 0 dBVU = +4 dBu = -20 dBFS (Avid's guide). There is no de-esser on the strip. PROVEN (one-change
saves and Avid's guide).

Key source: `[pickoff] [u16 code] [byte]`, the code as a matrix source names it (section 10.7). `03 21 70 00` is the
mono main at Pre-Fader, `03 11 40 00` is Group 2, and none is `00 00 00 10`. PROVEN (one-change save). A raw rack
input carries 0x10 in the last byte and a port code, not placed.

Cleared-show defaults on 8.2: gain +10 dB; HPF 80 Hz out; LPF 20 kHz out; EQ out; gate threshold 0 dB, range
-20 dB, attack 1 ms, hold 100 ms, release 250 ms, ratio 100:1; comp threshold 0, ratio 2:1, attack 10 ms, release
100 ms, knee 0; HEAT drive 0, tone 3; fader -inf; pan centre; L-R on. PROVEN (a cleared-show save).

Numbering: a stereo strip takes two engine channels, and VENUE numbers channels by strip, not fader place.
`Input Strip Layout` holds a strip number per fader place, -1 empty. PROVEN (one-change save).

### 10.5 Output patch (`Output Routing`)

One i32 per physical output. Places hold across 8.0 and 8.2 and across rigs: Stage 1 from 0, Stage 2 from 48, the
console's own outputs from 96 (Analog 1 to 8 at 104 to 111, AES 1 to 8 from 120, USB L and R at 200 and 201),
Local 16 from 112, Stage 3 from 286. PROVEN (one-change saves).

| Source | Code |
|---|---|
| nothing | 0x01008000 |
| input strip n's direct out (n from 1) | 0x01008802 + 8(n-1) |
| aux k (from 1) | 0x01009801 + 8(k-1), unbroken (aux 34 is 0x01009909) |
| matrix 1 to 8 / 9 to 16 | 0x0100A801 + 8(k-1) / 0x0100B001 + 8(k-9) |
| L, R, Mono | 0x0100B801, 0x0100B809, 0x0100B811 |
| Monitor A L / R | 0x01008005 / 0x01000005 |
| Monitor B L / R | 0x02008005 / 0x02000005 |

A stereo strip's right half drops 0x8000 (aux 1 L 0x01009801, R 0x01001801). VENUE ignores a right-half code on a
mono strip. A default show holds L and R on Stage 1 outputs 1 and 2. PROVEN (one-change saves). `Output Routing`
grows from 1912 slots in 8.0 to 2616 in 8.2 with places fixed. PROVEN. Not placed: places 96 to 103, AES 3 to 8,
Stage 4 to 6, and Stage 16 output numbering.

### 10.6 Head amps and the rig

Gains are u32 in 0.1 dB everywhere, default 100 (+10.0 dB). Analog +10 to +60 dB, or -10 to +40 dB with the 20 dB
pad; digital inputs -20 to +18 dB; stereo right offset -20 to +20 dB. No separate trim on an analog input. PROVEN
(Avid's guide and VENUE's clamps).

- `Input Gains`: 160 gain slots of 4 bytes from byte 0, Stage 1 inputs 1 to 48 (slots 0 to 47), then Stage 2 inputs
  1 to 48 (48 to 95). From byte 640, 2 bytes per input in the same order: pad, then 48V. PROVEN (one-change saves).
- `Input Gains` from byte 1178: Local inputs, 6-byte records (u32 gain, pad, 48V). Local 1 is proven; the 6-byte
  stride comes from one record and is UNVERIFIED.
- `Input Gains Stage64`: 6-byte records (u32 gain, pad, 48V), 64 per block. Records 0 to 15 are Stage 1 inputs 49
  to 64, 64 to 79 Stage 2 inputs 49 to 64, 128 to 191 Stage 3 inputs 1 to 64. Default record `64 00 00 00 00 00`.
  PROVEN (one-change saves).
- The rig sits in the header (`Stage Config`, `Stage Config v2`, `Expansion Cards`) and in the body's card blocks
  (`Soundwaves Stage Cards` and siblings). The Standalone default (3 Stage 64 + Local 16) holds `Stage Config`
  `00 00 02 00...`, `Stage Config v2` `00...02` and no expansion card. A 2 Stage 64 + 4 Stage 16 + Local 16 rig
  holds `04 00 02 00...`, `80 00...02` and a card at byte 9 of `Expansion Cards`. A header with no card blocks
  loads inputs in italics as "Stage 5 Analog -01" with no 48V. PROVEN (patched load).
- The port gain tables hold gains on ports no strip patches. STRONG.
- `S6L Mic Pre Gains Upon Entering VSC Mode`: 512 i32 gains kept for Virtual Soundcheck. STRONG.

### 10.7 Buses, groups and matrixes

- `BusAssigns` entry: byte 0 pan (i16 -100 to 100, nonzero only into stereo auxes), byte 2 on, byte 3 pre, bytes 4
  and 5 level as in section 3.5. An aux with no send is `00000000 60fa`; a group not assigned is all zero. An off
  send into a stereo aux keeps its pan. PROVEN (one-change save).
- On an all-mono default the `BusAssigns` count is the mix-bus total. With stereo auxes it is the aux strip count, so
  changing an aux's width changes every `BusAssigns` length. STRONG.
- Aux pre points: `Console Options/Aux Busses Options` byte 24, 4 bytes per aux: 0 Pre-EQ, 1 Pre-Mute, 2 Pre-Fader.
  Copy in `Aux Busses Options 2` byte 300. Pre-EQ Post-Mute was not saved. PROVEN (one-change save).
- `AudioMasterStrip`: byte 11 bus EQ in; HPF in at 158 and Hz at 159; LPF in at 163 and Hz at 164; band order HI
  14, HM1 28, LM1 42, LO1 56, HM2 111, LM2 125, LO2 139. Bus Comp/Lim from byte 70, laid out as the input's from 6.
  Byte 2 is the aux's talkback ROUTE. PROVEN (one-change saves). The bus HI and LO1 type byte, and makeup at 91, are
  UNVERIFIED.
- Mix Bus Configuration (Options > System > Edit: Total Mix Busses, Group Busses in steps of 8) belongs to the show.
  A change touches the header's `Group count` and `Bus count`, `Aux Strips` and `Group Strips`, every input's
  `BusAssigns`, `RecallSafe v03` (10-byte records from byte 4: number, kind, 8 bytes; auxes kind 3, groups kind 4),
  `User Strip Layout`, `Other settings` byte 0 (12 less the groups in eights: 0x0c none, 0x0b 8, 0x0a 16, 0x09 24)
  and `Current State`. PROVEN (one-change saves).
- `MatrixMasterStrip v2.5` has room for 64 slots. Levels: 13-byte records from byte 198 (on, i32 level in 0.1 dB,
  i32 pan, a copy of the source). Sources: 4 bytes per slot from byte 1120 (pickoff, u16 code, a byte); 8.2 keeps a
  copy at 1376. A 9-byte table at byte 4 stops at slot 12. PROVEN (one-change saves).

Matrix source codes, strips from 0, PROVEN (one-change saves):

| Source | Code | Last byte |
|---|---|---|
| input / aux | 0x1001 / 0x3001 + 16 x strip | 00 |
| group / matrix | 0x4001 / 0x5001 + 16 x strip | 00 |
| L / R / Mono | 0x7001 / 0x7011 / 0x7021 | 00 |
| Monitor A L / R, Monitor B L | 0005 / 0004 / 0009 | 20 |
| rack input | port code (Stage 1 Analog 02 is 1010, Local Analog 03 is 30A0) | 10 |
| None | 0000 | 10 |

Pickoffs: an input's 00 Top Of Channel, 08 True Gain, 07 Pre-EQ, 01 Insert Return, 02 Pre-Fader Post-Mute, 06
Post-Fader; an aux's, group's or main's 03 Pre-Fader Pre-Mute, 04 Post-Fader, 05 Bottom Of. A stereo aux's right
leg is one less than its left: PROVEN for auxes, UNVERIFIED for groups.

### 10.8 VCAs, mute groups, layouts, monitor

- 48 VCAs and 48 mute groups on every engine. Mute group names: `Console Options/Mute Group Options`, 16 bytes each,
  groups 1 to 32 from byte 146, 33 to 48 from 726. PROVEN (one-change save).
- Flex Channels: `Console Options/Interaction Options`, Flex 1's strip (from 0) at 17 and kind at 18, Flex 2's at
  155 and 156, modes at 157 and 161 (5 latched, 4 and 0 unlatched). Kinds: 1 input, 3 aux, 7 main, 8 VCA. PROVEN.
- `User Strip Layout`: 48 layouts, each a u32 count (48), 48 two-byte slots (strip from 0, then kind: 0 empty, 1
  input, 3 aux, 4 group, 5 matrix, 7 main, 8 VCA), then the name as a C string. PROVEN (one-change save). Whether 48
  is the S6L-48D's fader count or a fixed capacity is UNVERIFIED.
- Talkback: `TalkbackOsc Options` byte 0 Level and byte 4 Dim Level, i32 in 0.1 dB. PROVEN.
- Monitor A (`Console Options/Monitor Options`): 0 Level Trim (i32 0.1 dB), 4 Type (0 PFL, 1 Stereo AFL), 8 Auto
  Cancel, 11 delay (u16 samples at 48 kHz), 17 delay in, 19 delay (samples at 96 kHz), 29 Mix to Monitors source
  number and 30 its kind (3 aux, 5 matrix, 7 mains). Monitor B (`Monitor B Options`): 0 Level Trim, 13 delay in, 14
  delay (96 kHz), 32 source number, 33 kind. PROVEN (one-change saves). Type 2 as Solo In Place is UNVERIFIED.

### 10.9 Plug-in routing word, in more detail

A Standalone save that routed four empty rack slots from the input menus splits the top bits of section 4.5:

- Bits 31 to 30: 0 insert, 1 fed by a bus out (section 4.5's +0x10), 2 fed by a direct out.
- Bits 29 to 26: 1 input, 3 aux, 7 main (L, R, C/Mono). Type 7 is the mains (section 4.5 had it UNVERIFIED).
- On an insert, the low bits: insert number from 0, plus 4 for post-fader (pre 1 to 4 stored 0 to 3, post 1 to 4
  stored 4 to 7).
- Saved words: `0x04000002` Ch 1 Pre-Fader Insert 3; `0x04040005` Ch 2 Post-Fader Insert 2; `0x0C7C0000` Aux 32
  Pre-Fader Insert 1; `0x1C080000` the mono main Pre-Fader Insert 1.

PROVEN (one-change save). The tools still treat positions past 5 as not decoded and do not write inserts.

Plug-in state notes (Waves SoundGrid racks, Avid Channel Strip names) are in [`plugins.md`](plugins.md).

### 10.10 Engines and surfaces

Each engine's default show from VENUE 8.2 Standalone. PROVEN (one save per simulated engine); this settles the
UNVERIFIED and STRONG rows of section 2 for reading:

| Engine | `Main Rack Type` | Inputs | Mix buses (default split) | Matrixes |
|---|---|---|---|---|
| E6L-112 | 7 | 112 | 48 (32 aux + 16 group) | 16 |
| E6L-144 | 4 | 144 | 64 (48 + 16) | 16 |
| E6LX-128 | 8 | 128 | 64 (48 + 16) | 24 |
| E6L-192 | 5 | 192 | 96 (80 + 16) | 24 |
| E6LX-176 | 9 | 176 | 96 (80 + 16) | 32 |
| E6LX-256 | 6 | 256 | 96 (80 + 16) | 64 (two mixer pages) |

Avid's datasheet gives the E6LX-256 192 + LCR buses; VENUE 8.2's default show for it has 96.

Surfaces, `Devices Configuration/Console Type`: 5 S6L-24, 6 S6L-24D, 7 S6L-32D, 8 S6L-16C, 9 S6L-24C, 10 S6L-48D.
PROVEN (one save per simulated surface). The 16C also clears `MTS Screen Present`, and VENUE adds a Local 16 for
it. An engine change restarts VENUE Standalone; a surface change does not. Options > System > Clear Console resets
the show and the engine to the E6L-192 default.

### 10.11 Snapshot stream

- A snapshot stream and `Current State` are a chain of records, `[u8 id][u32 LE absolute offset of the next
  record][payload]`, from offset 0 to exactly the stream's end. IDs ascend with gaps, a few out of order. 8.0 holds
  175 records, 8.2 holds 186. PROVEN (a walker reaches the end of every stream). This fits section 5: the first
  record is id 0 with the name.
- Each snapshot is a full state stream like `Current State`. One fader move changes the stream length by 4 bytes,
  so a fixed byte map cannot convert it. PROVEN (one-change save).
- Two snapshots that differ only in scope differ in 20 bytes: offset 40 (the number), 43870 to 43987, 345584 and
  396124 to 396131. PROVEN (one-change save). What each snapshot recalls field by field is not decoded.
- In `Current State`, names are in clear from about byte 1397 in input order (STRONG), and the VCA list is a u32
  naming the list's end, the strip count, then per strip a u32 count and VCA numbers, in two identical copies.
  PROVEN (one-change save).
- VENUE converts snapshots when it opens an 8.0 file. An 8.0 stream inside a file whose `Full Support SW Version`
  says 8.2 loads and recalls, but values may be wrong. PROVEN (patched load).

8.0 to 8.2 conversion rules. A converter on these rules reproduces VENUE 8.2's own resave byte for byte in ten of
thirteen 8.0/8.2 snapshot pairs and differs only at record 12's byte 5 in the other three. PROVEN (thirteen pairs:
nine 8.0 shows re-saved by VENUE 8.2):

- Records 79 and 208: a counted list `[u32 count][count x 4 bytes]`; 8.0 holds 234 entries and 8.2 938. Set the count
  to 938 and append 704 entries of `00 80 00 01`.
- Records 11 and 140: 163 two-byte entries, one per strip. The second byte 0 becomes 100, except entries 17 to 20.
- Appended in 8.2: 225, 227, 230 and 232 are constants. 226 is `10 01 00 00 02 00 00 00`, then 8.0's record 15 (each
  input's left and right patch codes), zero-padded to 1096 bytes. 228 and 229 are each 8.0's record 22; 231 is 8.0's
  record 221.
- Appended 233 is 8.0's record 21 entry by entry (32 bytes per input) with byte 1 set to `A7`, byte 25 to `2B` and
  eight `FF` after each entry. 234 is record 23 the same way, with byte 6 set to `01`, byte 25 to `27` and twelve
  `FF`. Records 21 and 23 look like per-input dynamics blocks; the field names are UNVERIFIED.
- Appended 235 is record 46 (48 entries of 32 bytes) the same way, bytes 6, 7 and 25 set to `FF` and eight `FF` after
  each entry. PROVEN (14 of 14 pairs, including an 8.1 show with a different record 46).
- Records 81 and 210 (163 six-byte entries): byte 5 is 0 in 8.2. Record 141 equals record 12.
- Every other 8.0 record is unchanged but for the next-offsets.

Record 12 byte 5 is 0 in 8.2's own current state for every show, and set in three re-saved snapshots that carry
runs matching other shows' 8.0 current states. That they are stale memory from re-saving shows back to back is
UNVERIFIED.

8.1 to 8.2, one show: an 8.1 stream is 8.2's first 183 records in the same order. Records 11, 140, 12 and 141 change
by the rules above, and 233, 234 and 235 are appended from 21, 23 and 46. That reproduces VENUE 8.2's resave but for
record 12's byte. PROVEN (one 8.1 show). VENUE 8.2's resave of one 144-channel, 16-matrix, LR+M show holds 162
strips where the same engine's default holds 163 (reason not found); that 162-strip snapshot, written into a
163-strip show, loads and recalls inputs, matrixes and mains as VENUE's own conversion does. PROVEN (patched load).

### 10.12 Where these findings and sections 1 to 9 differ

- Patch code. A contributor reading says `InputStrip` byte 88 is a u16 block-coded input patch code (Stage 1
  inputs 49 to 64 at 0x0080 + (n-49), 1 to 48 at 0x0100 + (n-1); Stage 2 at 0x0180 and 0x0200; Stage 3 at 0x0280;
  Local 16 at 0x0308; None 0x0000), with the right leg of a stereo input at byte 90. Section 3.2 says bytes 88 and
  89 are only a copy, and VENUE put its own patch back after they were changed (engine load). It needs a Filing >
  Load of a show with only byte 88 changed, read on the Patchbay page, to settle it. Whether VENUE restores the
  patch from snapshot record 15 or `Current State` is UNVERIFIED.
- FX returns. The contributor's 8.x shows hold no FX return strips: effects return on input channels fed by a rack
  (10.4, bytes 102 to 104). Section 3 lists a `FX Return Strips` array as STRONG. A show with an FX return strip, or
  an 8.2 save after adding one, would settle whether that array is used on S6L.
