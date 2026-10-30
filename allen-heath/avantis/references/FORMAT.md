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

## More container detail (markcarlberg, pull request #2)

From Avantis Director V1.30 and V2.01 saves, compared file by file. How each line was proven is in brackets:
save-proven (one change, save, the named bytes moved), seen in every file (consistent, never moved alone), or
unconfirmed. Where these notes read something differently from the text above, the text above stands and the
difference is listed under What we don't know in `../README.md`.

- Show-wide settings: about fifty `Show/<Area>/<Area>.dat` files, all text (a version line, then lines or comma
  fields) except `MixConfig.dat` and the scene safes. [seen in every file]
- Bridge-5 adds `SIPSettings/UFXSIPSettings.dat`, moves `FollowPanSettings.dat` to version line `2` and
  `Preferences.dat` to version 3, and changes `MIDISettings.dat`. [save-proven by diff]
- Scene slots 001-500 plus 65535. A fresh show stores every slot: an empty StageBox `.dat` is the header plus
  one byte (77,245 bytes on V1.30, 85,478 on V2.01), an empty Surface `.dat` 611 or 613 bytes. Only the live
  state holds the input patch by default, but every stored scene carries its own `Channel Mapper`.
  [save-proven]
- StageBox header length 0x12DBC (77,244) on Bridge-4 and 0x14DE5 (85,477) on Bridge-5. The Surface chain
  starts at 0x262 on Bridge-4. [seen in every file]
- The header opens `01 01`, then the scene name and description NUL-terminated, then the recall filter (mostly
  zero). The MixConfig copy at 330-342 follows `3B 02` (Bridge-4) or `3B 03` (Bridge-5). [seen in every file]
- Labels are exact strings. Mono mix labels end in a trailing space (`... Mono Matrix Channel 02 `); stereo ones
  end ` Left` or ` Right`. Some input labels have no comma (`Digital Attenuator Input Channel NN`,
  `Lowpass Filter Input Channel NN`, `Stereo Image Input Channel NN`); the mix forms have one
  (`Digital Attenuator, <strip>`). [save-proven]
- Payload offsets in these notes count from the byte after the label's NUL; byte 0 is the block's version.
- Scene safes files open `01 01 02` (Bridge-4) or `01 01 03` (Bridge-5) and a MixConfig copy; 76,912 bytes on
  Bridge-4, 8,233 longer on Bridge-5. [seen in every file]
- Name managers: an unnamed strip holds its own number as text. [seen in every file]
- Nothing inside the archive carries the show's name; it is the file name alone. [save-proven]

### FX racks

- `FX Manager NN` (171 bytes V1.30, 173 V2.01): [0..2] `05 01 00` or `05 02 00`, [3] engine, [4..21] name
  padded to 18, [22] NUL, [23..26] record words, [27..170] 72 parameter words, V2.01 [171..172] level `00 64`.
  [seen in every file]
- `Ultra FX Manager NN` (246): [0..2] `06 03 00`, [3] engine, [4] a Spaces reverb's space (3, 4, 5), [5..22]
  name, [23] NUL, [24..27] record words, [28..171] 72 words, [172..173] level, then FF. [seen in every file]
- The parameter words are the SQ's numbers in big-endian order (`../../sq/references/FORMAT.md` has the reverb
  and delay words). Avantis and SQ+ engine codes: 00 Empty, 02 Reverb, 03 SMR Reverb, 04 EMT 250, 05 Room,
  06 Flanger, 07 Chorus, 08 ADT, 09 Symphonic, 0A Sub Harmonics, 0B Gated Verb, 0C Phaser, 0D De-Esser,
  11 Dynamic EQ, 12 Multi Band Comp 4, 13 Multi Band Comp 3, 14 Transient Controller, 15 Bucket Brigade,
  16 Stereo Tap Delay, 17 Echo, 18 Dimension Chorus. Ultra FX: 1C Spaces Reverb, 1D Plate Reverb, 1E Vocal
  Tuner, 22 Vocal Harmoniser 4, 23 Vocal Harmoniser 2, 24 Vocal Shifter, 25 MIDI Harmoniser, 28 Vocal Gridder,
  2A Amp Cab, 2B Saturator, 2D Ultra Delay. [seen in every file, read from library preset names]
