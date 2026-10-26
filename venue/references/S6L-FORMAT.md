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
