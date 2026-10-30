# Logic Pro ProjectData format notes

Decoded by hand from projects saved by Logic Pro 11 and 12. Apple does not publish this
format. These notes cover channel strips, insert slots, routing and AU plugin state. They
do not cover regions, automation or the arrange window.

## Where it lives

A `.logicx` project is a package (a folder). The binary document is:

```
<Song>.logicx/Alternatives/000/ProjectData
```

Each alternative (`001`, `002`, ...) has its own ProjectData. Autosaves sit next to it as
`.songData` files (see "Checking that Logic accepted a patch").

## File layout

```
0x00  24-byte header. u64 LE at +16 = length of everything after the header.
0x18  chunk, chunk, chunk, ... to the end of the file (a flat chain, no nesting)
```

If you change the size of any chunk, update the header length.

## Chunk

| Offset | Size | Field |
|---|---|---|
| +0 | 4 | tag, ASCII, stored reversed (`OCuA` on disk = `AuCO`) |
| +14 | 4 | strip index, u32 LE |
| +18 | 4 | slot, u32 LE (`0xffffffff` = the strip object itself) |
| +28 | 8 | payload size, u64 LE |
| +36 | n | payload |

The next chunk starts at `+36 + payload size`. All other header bytes were copied as found.

## Channel strip: `OCuA`, slot `0xffffffff`

Offsets are from the start of the payload.

| Offset | Field |
|---|---|
| +0x3d | strip name, NUL-terminated, up to 15 bytes (`Audio 1`, `Aux 3`, ...) |
| +0x4c | 4-byte signature. `ab f7 d3 cf` = strip with a live input. `ab f5 d7 cf` = strip whose input is a bus (aux). Only these two were seen on audio and aux strips. |
| +0x50 | 1-byte kind (not decoded further) |
| +0x5c | output, u16 LE |
| +0x5e | input, u16 LE |
| +0x84 + 4*slot | insert occupancy flag, u32 LE, 1 = slot used (slot = 5..15) |

Input and output values:

- `0xffff` = none.
- Live input k is stored as `k - 1` (on a live-input strip).
- Bus N is stored as `32 + N`.
- Values 1 to 32 on an output were hardware outputs.
- In the project this was decoded from, every strip that fed the final mix had output
  value 73. Check what your final destination uses with `logic_pd.py strips` and pass it
  as `--main-out`.

## Slot chunks: `UCuA`

The slot chunks of a strip follow its `OCuA` chunk, sorted by slot. Slots 5 to 15 are the
insert slots: slot 5 = insert 1, slot 15 = insert 11. Byte `+0x2a` of the chunk (payload
`+6`) = slot - 5. If you move an insert, change both the slot field and this byte.

### AU insert

Offsets are from the start of the chunk.

| Offset | Field |
|---|---|
| +0x9c | plugin name, NUL-terminated, 12 bytes (truncated, for example `AUSampleDel`) |
| +0xa8 | 12 bytes: manufacturer, type, subtype, each four-char code stored reversed (`lppa xfua ylds` = `appl aufx sdly`) |
| +0xbc | u32 LE, length of the state block that follows (plist + padding) |
| +0xd0 | the AU ClassInfo as an XML plist (`<?xml ...</plist>`), a newline, NUL padding to 4 bytes |
| after | a version 1 UUID (16 bytes), then 4 zero bytes |

The region between `+0xc0` and `+0xd0` contains the marker `46ia` and was copied unchanged
from an existing AU insert. Logic accepted chunks built that way.

The ClassInfo plist is the same dictionary an AU host gets from `kAudioUnitProperty_ClassInfo`:
`type`, `subtype`, `manufacturer` (integers), `version`, `name` (preset name), `data` and
plugin-specific keys.

### Logic's own plugins

Native Logic plugins (Channel EQ, Compressor and so on) have no XML plist in the slot
chunk. A readable name sits near payload `+0x8c`. Their latency is not measured by these
tools. Most report zero. Check the few that do not (linear-phase EQ, look-ahead limiters)
in Logic.

## AUSampleDelay state

Apple's AUSampleDelay (`aufx` / `sdly` / `appl`) stores its delay in the ClassInfo `data`
key: 16 zero bytes, then the delay in samples as a big-endian float32. `logic_pd.py
add-delay` writes it that way.

## Measuring real plugin latency

Logic does not store plugin latency. Measure it:

1. `logic_pd.py extract ProjectData plists/` writes each AU insert's ClassInfo to
   `NNN_<offset>.plist`. The offset ties the measurement back to the insert.
2. On the Mac, build `scripts/aulat.swift` and run it on that folder. For each plist it
   instantiates the AU, sets a 48 kHz stream format, loads the ClassInfo (before and after
   initialize, since some plugins only apply state once initialized), and reads
   `kAudioUnitProperty_Latency`.
3. Run it from Terminal in the logged-in GUI session. Over plain ssh, only Apple's AUs
   register, so third-party plugins come back `NOTFOUND`.

Latency can depend on settings (look-ahead, oversampling, quality modes). That is why the
tool loads each instance's own state. Examples measured at 48 kHz on one machine:

| Plugin | Samples |
|---|---|
| Supertone Clear | 2238 |
| Waves Curves AQ | 1087 |
| Slate Trigger 2 | 192 to 1113, depends on settings |
| Waves Renaissance DeEsser | 64 |
| Waves SSL EV2 | 59 |

## Path latency and alignment

A signal's latency at the final mix = the sum of insert latency on its strip, plus every
aux strip it passes through on the way (bus to aux to bus ...). `logic_pd.py paths` walks
that graph from each live-input strip. `plan` gives each strip the delay that brings it to
the longest path. `add-delay` puts an AUSampleDelay at insert 1 of each strip with that
delay.

This matters when Logic's own plugin delay compensation is off or is not applied to
live inputs, for example a live stream or broadcast mix run through Logic.

## Checking that Logic accepted a patch

Open the patched project in Logic, let it autosave, and look at the newest `.songData`
autosave: it is zlib-compressed after a 16-byte header. Decompress it and check that the
new inserts are there. Also check the strips in Logic itself before you use the project live.

Projects saved by Logic 12.4 opened in Logic 11.0 during testing.
