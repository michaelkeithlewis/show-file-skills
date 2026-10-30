# Avantis show file format

Avantis and dLive share the same family of show files. Most of `allen-heath/dlive/references/format-*.md` applies.
This page lists what is the same and what differs on Avantis.

## Archive

- Outer file: `<name>.tar.gz` with a `Show/` tree. Scenes are inner `.tar.gz` files:
  `Show/Scenes/StageBoxSceneNNN.tar.gz` and `SurfaceSceneNNN.tar.gz`. Scene 65535 is the live console state.
- Write the archive in console style: ustar, uname and gname `bridge`, gzip without a stored file name.
  Director opens other tar flavours, the console is pickier.
- `Show/Version.dat` names the format:

| Value | Console | Notes |
|---|---|---|
| `Bridge-4` | Avantis firmware 1.x | Filters stored as biquad coefficients (see `processing.md`) |
| `Bridge-5` | Avantis firmware 2.x | Parameter based, most sections are byte for byte the dLive sections |
| `13` | dLive firmware 1.x | Older Mix Mixer layout |
| `14` | dLive firmware 2.x | What `allen-heath/dlive/` writes |

- Avantis firmware 2.x loads a Bridge-4 show and saves it back as Bridge-5. Writing Bridge-4 is therefore the
  safe target for both firmware lines. Writing Bridge-5 directly needs empty Bridge-5 shows saved on the
  console (not from Director) in several bus configurations as templates. Not done yet.

## Scene file

Same idea as dLive: a fixed header, then a chain of labelled sections, then one trailing byte.

- Bytes 2 to 320: scene title, NUL terminated.
- Bytes 330 to 342: a 13-byte mixer config copy, same layout as `Show/MixConfig/MixConfig.dat`
  (`mixer.md`). On older Avantis shows this copy is all zero. Do not trust it; the mixer sections carry their
  own config (see `mixer.md`, "Mixer section header").
- Empty scene slots are header only: Avantis 77245 bytes, dLive 122426 bytes.
- Recall filter and scene safes: the Avantis layout is not the dLive one (`dlive_safes.py` does not apply).
  Not decoded yet.

### Finding the section chain

- Bridge-5 (and dLive): scan from byte 320 for a big-endian u32 that equals the number of bytes after it
  minus 1 (the trailing byte). The chain starts right after that u32.
- Bridge-4: there is no such length field in the same place. The chain starts 2 bytes before the first
  `Mix Delay, ` label (the 2 bytes are that section's length).

### Sections

Same as dLive: `u16be length` (label + NUL + payload), ASCII label, NUL, payload. A robust reader stops at the
first label that is not printable ASCII or longer than 80 bytes.

## Section names that differ from dLive

| Avantis | dLive |
|---|---|
| `Ultra FX Manager NN` | `AHFX Manager NN` |
| `Ultra FX Dynamics, UFX Channel NN` | `AHFX Dynamics, FX Channel NN` |
| `Parametric EQ, Ultra FX Channel NN` | `Parametric EQ, AHFX Channel NN` |
| `Stereo Ultra FX Send Channel Name Colour Manager` | `Stereo AHFX Send Channel Name Colour Manager` |
| `Ultra FX Return Channel Name Colour Manager` | `AHFX Return Channel Name Colour Manager` |
| `StageBox GX Analogue Input, Number NN` (SLink preamps) | no equivalent |

The `RETURN` / `SEND ... SCF` variants of the dynamics sections follow the same rename.

## Names and colours

`<Group> Name Colour Manager`, groups: `Input Channel`, `Mono Group Channel`, `Stereo Group Channel`,
`Mono Aux Channel`, `Stereo Aux Channel`, `Mono FX Send Channel`, `Stereo FX Send Channel`, `Main Channel`,
`Mono Matrix Channel`, `Stereo Matrix Channel`, `FX Return Channel`, `DCA Channel`, plus the Ultra FX groups
above.

- Payload: `[version][k x 9-byte name][k colour bytes]`, with `k = (len - 1) / 10`.
- Names are Latin-1 in a 9-byte field, NUL terminated. Bytes after the NUL can be garbage; ignore them.
- The slot count is fixed per group and does not follow the bus config. Avantis slots:

| Group | Slots |
|---|---|
| Input Channel | 96 |
| Mono Group, Mono Aux, Mono Matrix | 56 each |
| Stereo Group, Stereo Aux, Stereo Matrix | 28 each |
| Mono FX Send, Stereo FX Send | 16 each |
| FX Return | 16 |
| DCA | 16 |
| Main | 6 |
| Monitor | 2 |

## FX rack

`FX Manager NN` (12 on Avantis, 16 on dLive): `[header][type][20-byte preset name][parameters][padding]`.
The type byte sits at offset 3 on Avantis and offset 2 on dLive. Section length: dLive 124, Bridge-4 171,
Bridge-5 173 bytes. The parameter block has the same layout on all three: factory presets (Hall 480,
Plate Gold US, EMT 250, DeEsser Hard) are byte for byte identical between the consoles. Type IDs differ, see
`translate-dlive.md`.

`Ultra FX Manager NN`: type byte at offset 3, preset name at bytes 5 to 25.
