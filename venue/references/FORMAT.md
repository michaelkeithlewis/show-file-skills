# Avid VENUE / D-Show show file (.dsh) format notes

**Correction (2026-10-26).** The show these notes came from is an S6L show saved by VENUE 8.2, not a classic show.
The token table below is also wrong in part: `0x0B` is a dictionary (a u32 count, then key and value pairs), `0x0C`
is an array and `0x0D` is a blob (a u32 length, then raw bytes), and `0x06` is a signed 32-bit integer.
`S6L-FORMAT.md` section 1 has the full container grammar. Classic shows use the same container: Avid's VENUE 2.9
and 4.5 demo shows parse and write back byte for byte. The rest of this file stays as the record of the first
decode, and `dshow_tool.py` still works the way it describes.

Decoded by hand from one show saved by a classic VENUE system (Profile / SC48 / D-Show
family, show path `D:\D-Show\User Data\Shows\...`). Avid does not publish this format.
These notes cover what was observed in that file. Other software versions and console
types (S6L, S3L) were not checked.

## Not DiGiCo

The `.dsh` extension looks like a DiGiCo file. It is not. The magic string is
`Digidesign Storage - 1.0`. Digidesign was the original maker of VENUE.

## Token stream

The file starts with byte `0x0a`, then the magic string and a NUL. After that the file
is a serialized tree of typed tokens. A token is one type byte and then a value.

| Type byte | Value |
|---|---|
| `0x0a` | NUL-terminated ASCII string (keys and string values) |
| `0x01`, `0x03` | 1-byte integer |
| `0x06`, `0x0b` | 4-byte little-endian unsigned integer |
| `0x0c`, `0x0d` | object or section marker, starts a sub-object |

## System config block

The first block after the magic is a clean list of key and value pairs: a `0x0a` key
string and then one typed value. `dshow_tool.py dump` prints it. Keys seen:

`Bus count`, `Channel Count`, `DSP Card count`, `Bus Config Mode`, `Extended Bus Config Mode`,
`Group count`, `Matrix count`, `VCA count`, `VCA count v2`, `FX Returns count`,
`Graphic EQ count`, `Sample Rate`, `Main Rack Type`, card presence flags
(`HDx1 Present`, `MADI1 Present`, `RTX Present`, `MTS Screen Present`, ...),
card counts (`AVB Card Count`, `MLN-192 Card Count`), and two software version fields
(`Full Support SW Version`, `Partial Support SW Version`).

The block ends at the first byte that is not a known type byte.

## After the config block

Object blocks follow, mixed with large binary parameter arrays. Regions full of
`ff`, `60`, `fa` bytes hold gains, EQ, levels and similar values. These regions are not a
flat token stream. Do not tokenize them and do not edit them by hand.

## Channel strips

Each strip object starts with:

```
0a "Strip" 00   0d <uint32 LE strip id> <1 flag byte>   <name> 00 ...
```

The flag byte was 0 or 1 in the sample. The name follows the flag directly.
Unused strips have an empty name. The sample file had 267 strip slots for a
192-channel config (inputs, FX returns, buses, groups, matrices and so on).

## Where names repeat

Each strip name was found in three places:

1. The strip object (above).
2. Two packed name tables later in the file. A table is a run of NUL-terminated
   names, back to back, for example `KICKS\0SNARES\0TOMS\0OHS\0\0\0`.

The packed tables have no length prefix that was found. The reader most likely walks
them string by string. That is why the rename rule below pads with spaces.

## Safe hand edit: rename a strip

A rename is safe only if no byte offset in the file moves:

- The new name must be the same length as the old name, or shorter.
- Replace every whole copy of `old\0` (the byte before it must not be a printable
  character, or the match is the tail of a longer name).
- Pad the new name to the old length so the file size stays the same.

Two padding choices:

- **Spaces, then NUL** (default in `dshow_tool.py`): `Kick In\0` becomes `Kik    \0`.
  The packed tables keep the same number of strings in the same order. The strip name
  has trailing spaces.
- **NUL, then NULs** (`--pad nul`): `Kick In\0` becomes `Kik\0\0\0\0\0`. The strip object
  reads correctly, but in a packed table the extra NULs can read as extra empty names and
  shift the table. This was the first method tried. Treat it as unproven.

Longer names, numeric parameters (gain, EQ, dynamics), routing and the patch live in
the binary arrays or in length-dependent structures. Do not hand-edit them. Use the
VENUE software (console or the standalone editor) for those changes.

## What is proven and what is not

- Proven: the tool reads the config block and every strip name from the sample file.
  A rename changes only the bytes of the renamed name copies (3 copies, file size unchanged).
- Not proven: that a renamed file opens in the VENUE software. Open every renamed file
  in the VENUE standalone software, check it, and save it from there before it goes near
  a console.
