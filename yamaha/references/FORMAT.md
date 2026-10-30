# Yamaha console show file notes

Yamaha's current mixing consoles save their shows in two file generations. Yamaha does not publish either format.
This page holds only what a black-box test proved. Each fact names its test, and section 1 describes every test.

| Generation | Consoles | Show file | Container |
| --- | --- | --- | --- |
| 1 | CL1, CL3, CL5, QL1, QL5 | `.CLF` | a big-endian record tree with word-sum checksums (section 2) |
| 2 | DM7, DM7 Compact, DM5, DM5 Compact | `.dm7f`, `.dmxf` | `#YAMAHA MBDF`, zlib entries, a schema inside every section (section 4) |
| 2 | DM3, DM3 Standard | `.dm3f` | the same |
| 2 | TF1, TF3, TF5, TF-RACK | `.tff` | the same |
| 2 | RIVAGE PM3, PM5, PM7, PM10 | `.RIVAGEPM` | the same container; this tool does not read these files yet |

## 1. How each fact was proven

Every fact here is PROVEN: a test gave the result, and the test is named. A fact that no test proved is not on this
page as a fact. Section 6 lists what is still unknown and the test that would settle each item.

The tests used the free Yamaha offline editors under Wine on Linux: CL Editor 5.8.1, QL Editor 5.8.1, DM Editor
2.0.1, DM3 Editor 3.1.0, TF Editor 4.50 and RIVAGE PM Editor 7.2.0. Each test is one of two kinds:

- Save and read. Set a value in the editor, by a click or through Yamaha's documented CSV import, save the session,
  and find the value in the saved file.
- Write and load. Write a value into a file, open the file in the editor, read the value on the screen, then save
  from the editor and check that the save holds every written and every untouched value.

"This code" in the tests below is the engine behind idontownapc.com/yamaha, which `scripts/yamaha_tool.py` was ported
from. For the same changes the two write byte-identical files.

The files read were new sessions saved from the editors and real show files from the author's own work. No show file
is published. Every fact here was proven by a black-box test named on this page. No table, text or file from a Yamaha
program, descriptor, template, preset, font or screenshot is copied here, and no Yamaha file ships with this folder.

### 1.1 Container tests

| Id | Test | Result |
| --- | --- | --- |
| BB-WALK | Every CL and QL file at hand walked as a record tree: 16 `.CLF` and 4 `.CLU` from real shows, and the sessions saved by CL Editor and QL Editor | Every walk ends on the exact last byte, with no gap and no overlap |
| BB-SUM | The checksum rule of 2.3 computed for every block (199 data blocks, 254 scene sections); a file with one name byte changed and the old checksum, opened in CL Editor | Every checksum matches, including every block CL Editor wrote on a re-save. CL Editor refused the changed file with "Checksum error. (-2)" |
| BB-KIND | All-data and scene-only files opened with File > Open in CL Editor | Kind `0x05C0` opens. Kind `0x1040` is refused: "Different Kinds of Data! (-7). The file kind is 'SCENE MEMORY'." |
| BB-G2-WALK | Every generation-2 file at hand: real DM7 shows (firmware V1.53, V1.73) and new sessions saved by DM Editor 2.0.1, DM3 Editor 3.1.0, TF Editor 4.50 and RIVAGE PM Editor 7.2.0 | Every file walks to its exact end and rebuilds byte for byte. For every collection, the layout rule of 4.3 gives the stored size |
| BB-G2-ZLIB | DM Editor 2.0.1 loaded a DM7 file whose entries were inflated, edited and compressed again (other compressed sizes); then a copy with a broken zlib stream | The first file loaded and showed the edit. The broken copy did not load |

### 1.2 CL and QL value tests

| Id | Test | Result |
| --- | --- | --- |
| BB-CSV-1 | A CSV set (InName, StName, MixName, MtxName, StMonoName, DCAName) with a different name, colour word and icon word on every row, imported into a new CL5 session, saved, and compared with the new session | Only the name, icon and colour bytes of section 3 changed, plus the checksum. DCA colours and icons in the CSV changed nothing |
| BB-CSV-2 | InPatch.csv rows naming every port kind on different channels: three imports in CL Editor, one in QL Editor | The patch codes of 3.4 |
| BB-CSV-3 | A CSV set with one file holding rows and the other eight header only, imported onto an existing show in CL and QL Editor 5.8.1, saved, and compared with the show's own re-save | 0 error boxes. Only the rows in the set changed (156 bytes), plus the checksum. A seven-file set raised 2 error boxes and InName.csv alone raised 8, one per missing file |
| BB-LOAD-F | CL Editor loaded files written by this code with 72 fader values, HPF index 4 to 63 on 60 channels, HPF on and channel on on 8 channels each, and gain and +48V on OMNI 1 to 8; seven more loads with fader values 0 to 503 | The Overview showed every value. The fader, HPF, on and head amp rules of section 3 |
| BB-LOAD-G | CL Editor loaded a written file with DCA assigns on 7 channels, ST IN fader, on and HPF values, and 8 mute group names | The DCA Group window, the ST IN strips and the Mute Group window showed the values |
| BB-SAVE-H | Three mute group assigns clicked in the Mute Group window, saved, compared | Exactly three bits changed |
| BB-SCENE | A new session with 2 stored scenes, made in CL Editor with Store; this code wrote a title and a channel name into each | The Scene Memory list showed the titles. A recall of each scene showed its written name on the strip |
| BB-QL | QL Editor loaded a written QL5 file with gain on all 32 local inputs and +48V on 8 | Every value matched |
| BB-MODEL | One CL session saved with Model Select CL5, CL3 and CL1; QL Editor saved as QL5 and QL1 | The three CL saves are byte-identical. QL1 and QL5 differ only in the new session's default patch |
| BB-RESAVE | CL Editor loaded format 5 and format 6 shows with values this code wrote, and saved them | The saves are format 7 and hold every written value at the same offset |
| BB-LOAD-R | CL Editor loaded a written file with OMNI 2 gain +60 dB and a fader at stored value 870 | The Overview showed `+60dB` and `2.35dB`; the re-save matched all 147 compared items |
| BB-RACK | A patch to GEQ 4A written into a new CL5 session; a patch to FX 3B written into a QL show with another rack set-up | The editor turned both into NONE on load |

### 1.3 DM7 value tests (DM Editor 2.0.1)

| Id | Test | Result |
| --- | --- | --- |
| BB-DM-SAVE | In a new DM7 session: one colour column clicked on each of CH 1 to 11 in the Channel List, three DCA assigns, HPF on and five steps up on CH 1; saved and read by schema path | The colour words, the DCA bits and the HPF location and unit of 4.5 |
| BB-DM-LOAD | This code wrote names, colours, fader levels, channel on, OMNI 1 to 4 gain and +48V, HPF and patches into a new session; DM Editor loaded it | The bay, the selected channel bar and the Channel List showed every value; the re-save matched all 208 compared items |
| BB-DM-RANGE | Written HPF frequencies of 20, 87, 125, 600, 1500 and 2000 Hz and fader levels of -138, -137.99, -120, +3.33 and +10 dB | The channel bar showed each value as written, and the re-save held each one |
| BB-DM-ORDER | In one pass: CH 9 repatched from OMNI 9 to OMNI 13, then +40 dB and +48V; CH 40 repatched from DANTE 8 to OMNI 14, then +51 dB and +48V | The editor showed CH 9 on OMNI 13 at +40 dB with +48V lit. The head amp change reached the port the channel was patched to at that point |
| BB-DM-MODEL | New sessions saved as DM7, DM7 Compact, DM5 and DM5 Compact | The header model is `DM7` in all four. `ProjectInfo` tells them apart (4.4) |
| BB-DM-SHAPE | The schema of every generation-2 file at hand, read for each parameter this tool uses | The same type, size and count in every file (4.6) |

## 2. Generation 1 container: CL and QL `.CLF`

### 2.1 Records

The file is a tree of big-endian records. Each record has an 8-byte header: u16 type, u16 0, u32 body length.
(BB-WALK)

| Type | Body |
| --- | --- |
| `0x0100` head | u16 family, u16 kind, u16 entry count, u16 0. The outermost head adds a 32-byte free-text comment, so its body is 40 bytes; every other head body is 8 bytes |
| `0x0200` index | one 8-byte entry per item: u16 id, u16 0, u32 absolute file offset |
| `0x0300` data | the block bytes, or nothing for an unused slot |

A head is followed by its index. An index entry points at a data record or at a nested head (a sub-container). The
records tile the file exactly. The family word of the outermost head is always `0x0170`. Some sub-containers use
other family words; their meaning is unknown, and this tool copies them unchanged. (BB-WALK)

### 2.2 File kinds

The kind word of the outermost head:

| Kind | File | Test |
| --- | --- | --- |
| `0x05C0` | all data: the whole show (File > Save) | BB-KIND |
| `0x1040` | scene memory only | BB-KIND: the editor refuses it on File > Open |
| `0x04C0` | user key (`.CLU`) | seen only in `.CLU` files (BB-WALK). User keys hold the console's user accounts, so this tool refuses them unread |

The comment is free text typed on save. A new session's default comment starts with `CL [` or `QL [`, but it is a
hint only (BB-MODEL).

### 2.3 Checksum

Every non-empty data block ends with a 4-byte checksum:

```
checksum = NOT( sum of the big-endian u32 words before it ) mod 2**32, stored big-endian
```

A scene's MEMAPI section (2.4) ends with its own checksum by the same rule. A file with a wrong checksum does not
load. (BB-SUM)

### 2.4 Scene memory

The top-level index entry `0x10` is a sub-container of scenes. Entry `0xFFFE` is the current scene (the show as it
stands), and entries 1 to 300 are the stored scenes. A value written into `0xFFFE` shows in the editor (BB-CSV-1,
BB-LOAD-F). A stored scene is a full copy with its own names, colours and patch, and a recall brings them back
(BB-SCENE).

A scene block is a list of sections. Each section has a 20-byte little-endian header: u16 `0x6CFF`, u16 0,
u32 header size (20), an 8-byte ASCII tag, u32 data size. The data follows. The `MEMAPI` section holds the scene
values (big-endian) and ends with the checksum. This tool changes nothing else in a scene block. (BB-WALK, BB-SUM)

### 2.5 Scene formats

The size of the MEMAPI data gives the scene format, and the u16 at offset 16 of that data holds the same number
(BB-RESAVE):

| MEMAPI data size | Scene format |
| --- | --- |
| 38,824 | 5 |
| 39,448 | 6 |
| 39,452 | 7 (written by CL Editor and QL Editor 5.8.1) |

CL Editor 5.8.1 re-saves format 5 and 6 files as format 7, and every value in section 3 sits at the same offset in
all three formats (BB-RESAVE). One exception: no test looked at the stored scene titles of a format 6 file, so `show`
marks the stored scenes of a format 6 file with `?`. The bytes that formats 6 and 7 add are not understood. This
tool never changes the scene format and copies every byte it does not write.

### 2.6 No model field

A `.CLF` does not record which CL or QL model made it (BB-MODEL). The data always holds the largest layout: 96 input
slots, 24 mixes, 8 matrices, ST L, ST R, MONO, 16 DCAs and 8 mute groups. The split name tables fix each count:
characters 5 to 8 of each name sit 4N bytes after characters 1 to 4, with N = 96, 24, 8, 3 and 16 (BB-CSV-1) and
8 for the mute groups (BB-LOAD-G). A reader must ask for the model, and the
model sets only how many channels the console shows (Yamaha's published counts: CL5 72, CL3 64, CL1 48, QL5 64,
QL1 32 mono inputs; CL 24 mixes, QL 16).

## 3. CL and QL values

Offsets are bytes from the start of a scene's MEMAPI data. Every value is big-endian.

### 3.1 Slots, names and masks

- An input slot is 1 to 96. CH 1 to 72 are slots 1 to 72. ST IN 1L, 1R, 2L ... 8R are slots 73 to 88. Slots 89 to 96
  are not used. (BB-CSV-1: the StName rows landed in slots 73 to 88)
- A name has 8 ASCII characters, zero padded, stored in two halves. For a table of N names at offset T, characters
  1 to 4 of name i are at `T + 4(i-1)` and characters 5 to 8 at `T + 4N + 4(i-1)`. (BB-CSV-1)
- A mask is 12 bytes, one bit per slot: slot n is bit `(n-1) mod 8` (least significant bit first) of byte
  `(n-1) div 8`. 1 = on or assigned. (BB-LOAD-F)

### 3.2 Where each value lives

| Value | Offset | Encoding | Test |
| --- | --- | --- | --- |
| Scene title | 0 | 16 ASCII bytes, space padded | BB-SCENE (format 7), BB-RESAVE (format 5: the Scene Memory list matched). Format 6: not tested (2.5) |
| Scene format | 16 | u16: 5, 6 or 7 | BB-RESAVE |
| Input names | 29,240 | 96 names, split as in 3.1 | BB-CSV-1 |
| Input icon | 30,008 | u8 per slot, code in 3.3 | BB-CSV-1 |
| Input colour | 30,104 | u8 per slot, code in 3.3 | BB-CSV-1 |
| Input patch | 28,971 | u8 per slot, code in 3.4 | BB-CSV-2 |
| Fader | 2,586 | u16 per slot, rule in 3.5 | BB-LOAD-F |
| Channel on (the ON key) | 2,382 | mask, 1 = on | BB-LOAD-F |
| HPF on | 6,692 | mask, 1 = on | BB-LOAD-F |
| HPF frequency | 6,704 | u8 index per slot, table in 3.6 | BB-LOAD-F |
| DCA k assign | 10,004 + 12(k-1) | mask, k = 1 to 16 | BB-LOAD-G |
| Mute group k assign | 9,908 + 12(k-1) | mask, k = 1 to 8 | BB-SAVE-H |
| Head amp +48V | 1,373 | 4-byte mask, port p = bit `(p-1) mod 8` of byte `(p-1) div 8` | BB-LOAD-F, BB-QL |
| Head amp gain | 1,377 | u8 per port (32), rule in 3.7 | BB-LOAD-F, BB-QL, BB-LOAD-R |
| Mix names | 30,604 | 24 names, split | BB-CSV-1 |
| Mix icon, colour | 30,884, 30,908 | u8 x 24 each | BB-CSV-1 |
| Matrix names | 30,796 | 8 names, split | BB-CSV-1 |
| Matrix icon, colour | 30,932, 30,940 | u8 x 8 each | BB-CSV-1 |
| ST L, ST R, MONO names | 30,860 | 3 names, split | BB-CSV-1 |
| ST L, ST R, MONO icon, colour | 30,948, 30,951 | u8 x 3 each | BB-CSV-1 |
| DCA names | 21,524 | 16 names, split | BB-CSV-1 |
| Mute group names | 34,392 | 8 names, split | BB-LOAD-G |

An ST IN strip shows the fader, ON key and HPF of its L slot. The editor's own ON click changes the L and the R bit,
so this tool writes both (BB-LOAD-G).

### 3.3 Colour and icon codes (BB-CSV-1)

Colour, with Yamaha's CSV word where it differs from the label:

| Code | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Colour | Blue | Orange | Yellow | Purple | Sky blue (`Cyan`) | Pink (`Magenta`) | Red | Green | Off, a black label (`Off`) |

Icon codes 0 to 39 follow Yamaha's CSV icon words in this order: Kick, Snare, Hi-Hat, Tom, DrumKit, Perc., A.Bass,
Strings, E.Bass, A.Guitar, E.Guitar, BassAmp, GuitarAmp, Trumpet, Trombone, Saxophone, Piano, Organ, Keyboard, Male,
Female, Choir, Dynamic, Condenser, Wireless, Podium, Wedge, 2way, In-Ear, Effector, Media1, Media2, Video, Mixer, PC,
Processor, Audience, Star1, Star2, Blank.

### 3.4 Input patch codes (BB-CSV-2)

| Code | CL source | QL source |
| --- | --- | --- |
| 0 | none | none |
| 1 to 64 | DANTE 1 to 64 | DANTE 1 to 64 |
| 65 to 72 | OMNI 1 to 8 | INPUT 1 to 8 |
| 73, 74 | PB L, PB R | PB L, PB R |
| 75 to 90, 91 to 106, 107 to 122 | SLOT1, SLOT2, SLOT3 inputs 1 to 16 | the same |
| 123 to 138 | FX 1A to 8B | FX 1A to 8B |
| 139 to 154 | PRFX 1A to 8B | PRFX 1A to 8B |
| 155 to 170 | GEQ 1A to 8B | not named by a test |
| 193 to 216 | not named by a test (CL Editor ignored the INPUT rows) | INPUT 9 to 32 |

The rack outputs (FX, PRFX, GEQ) exist only as the show's rack is set up: a written rack output came back as NONE
(BB-RACK). This tool shows them on read and never writes them.

### 3.4.1 CSV import needs all nine files (BB-CSV-3)

A CL or QL CSV set has nine files: `InName`, `StName`, `MixName`, `MtxName`, `StMonoName`, `DCAName`, `InPatch`, `OutPatch` and `PortRackPatch`, each `.csv`. The editor shows one error box per missing file (`Document "OutPatch.csv" not loaded.`), although the import still works. Write all nine. A file with its header and no rows raises no box, and the editor leaves those settings as they are. Tested in CL and QL Editor 5.8.1. CL1 and CL3 sets were not imported: every CL import was a CL5 set.

### 3.5 Fader values (BB-LOAD-F, BB-LOAD-R)

The u16 runs from 0 to 1023. The editor showed every value from 0 to 503 and 45 values from 504 to 1023, and every one
sits on these lines:

| Stored value v | dB shown |
| --- | --- |
| 0 | -inf |
| 1 to 15 | -141 + 3v |
| 15 to 33 | -111 + v |
| 33 to 223 | -78 + 0.2(v - 33) |
| 223 to 423 | -40 + 0.1(v - 223) |
| 423 to 1023 | 0.05(v - 823) |

So 823 is 0.00 dB, 1023 is +10.00 dB and 1 is -138 dB. Stored value 870 showed `2.35dB` (BB-LOAD-R).

### 3.6 HPF frequency index (BB-LOAD-F)

The editor showed this frequency for every index from 4 to 63:

| Index | Hz |
| --- | --- |
| 4 to 15 | 20.0, 21.2, 22.4, 23.6, 25.0, 26.5, 28.0, 30.0, 31.5, 33.5, 35.5, 37.5 |
| 16 to 27 | 40.0, 42.5, 45.0, 47.5, 50.0, 53.0, 56.0, 60.0, 63.0, 67.0, 71.0, 75.0 |
| 28 to 39 | 80, 85, 90, 95, 100, 106, 112, 118, 125, 132, 140, 150 |
| 40 to 51 | 160, 170, 180, 190, 200, 212, 224, 236, 250, 265, 280, 300 |
| 52 to 63 | 315, 335, 355, 375, 400, 425, 450, 475, 500, 530, 560, 600 |

This tool writes the index whose frequency is nearest on a log scale.

### 3.7 Head amps (BB-LOAD-F, BB-QL, BB-LOAD-R)

The head amp table covers the console's own inputs only. On a CL, ports 1 to 8 are OMNI 1 to 8 (patch codes 65 to 72).
On a QL, ports 1 to 32 are INPUT 1 to 32 (patch codes 65 to 72 and 193 to 216). Gain in dB is the stored value
minus 6. The editor showed every value from -6 to +50 dB, +60 dB and +66 dB. A channel patched from Dante or a
slot has its head amp on another device, so this tool refuses a head amp change on it.

## 4. Generation 2 container: `#YAMAHA MBDF`

### 4.1 Header (BB-G2-WALK)

| Offset | Size | Content |
| --- | --- | --- |
| 0x00 | 24 | `#YAMAHA MBDF` and the file kind: `ProjectFile` (a show), `Backup`, `Scene`, `Preset` or `UserKey` |
| 0x18 | 4 | u32 big-endian `0x24` |
| 0x1C | 8 | zero |
| 0x24 | 16 | model text: `DM7`, `DM3`, `TF`, `Rivage` |
| 0x34 | 4 | version: a letter, major, minor, 0. `56 02 01 00` is V2.01 |
| 0x38 | 16 | bytes that change on every save; this tool copies them |
| 0x48 | | records |

The version bytes of the real DM7 shows (V1.53, V1.73) are on Yamaha's DM7 firmware list, and every editor session
carries its editor's version (V2.01, V3.10, V4.50, V7.20). (BB-G2-WALK)

### 4.2 Records (BB-G2-WALK)

Each record starts with a 12-byte tag. Records are padded to 4 bytes.

| Tag | Layout |
| --- | --- |
| `#MMS FIELD` (also `#MMS FACADE`) | name (12), u32 BE extension size, u32 BE body size, u32 BE 0, the extension, the body |
| `#FILE` | group (12), u32 BE name length + 8, u32 BE compressed size, u32 BE 0, u16 BE name length, u16 0, u32 BE 8, the name padded to 4, a zlib stream padded to 4 |
| `#END` | 24 zero bytes. Nothing follows |

An `#MMS` body is a self-describing section: `MMSXLIT` and a zero byte (8), the function name (16), 8 bytes, a version
text (12), the MD5 of the schema as 32 hex characters, u32 LE 0, u32 LE schema size, u32 LE data size, the schema, the
data. The MD5 is the MD5 of the schema bytes, so it names the schema version; values can change without touching it.

A `#FILE` entry inflates to another MBDF file (kind `Backup`, `Scene` or `Preset`). No offset points across the
container, and the only checks are zlib's own and the schema MD5, so an entry can change size (BB-G2-ZLIB). Python's
`zlib.compress(data, 1)` writes the same `78 01` header as Yamaha but other bytes; DM Editor loads it (BB-G2-ZLIB).

### 4.3 The schema (BB-G2-WALK)

Every section carries the schema of its own data, so one reader reads every firmware by name, with no per-firmware
table. The schema is a tree of collections. Integers are little-endian.

A collection record is 48 bytes:

| Offset | Size | Content |
| --- | --- | --- |
| 0 | 4 | `COL0` |
| 4 | 24 | name, zero padded |
| 28 | 4 | bytes of parameter records that follow (32 each) |
| 32 | 4 | bytes of child collection records that follow the parameters |
| 36 | 4 | offset of this collection inside one element of its parent |
| 40 | 4 | size of one element |
| 44 | 4 | element count |

A parameter record is 32 bytes: `PR ` (3 bytes), type (1 byte: 0 text, 1 signed, 2 unsigned), u16 size in bytes (0 =
one bit), u16 array count, name (24 bytes).

Layout of one element:

1. Parameters are packed in record order with no alignment.
2. Consecutive 1-bit parameters share one bit stream. Array elements take consecutive bits, least significant bit
   first (BB-DM-SAVE: DCA k is bit k-1 of `DCA.Assign`; BB-DM-LOAD: the written `Fader.On`, `HPF.On` and `+48V` bits
   showed in the editor).
3. The next wider parameter starts on the next byte.
4. Child collections sit at their stored offset, after the parameters.

The rule gives the stored element size of every collection in every file read (BB-G2-WALK). The schema changes with
firmware: the DM7 `Mixing` section is 308,622 bytes at V1.53, 309,618 at V1.73 and 310,514 at V2.01. Read and write
by name, never by a fixed offset.

### 4.4 What a DM7 or DM5 show holds (BB-G2-WALK, BB-DM-MODEL)

| `#FILE` group | Entries |
| --- | --- |
| `Current` | `CurrentBackupFile.bup` and `CurrentBackupFile.bup.old`. Their sections, by field name (function name): `Mixing`, `Process` (`Processing`), `FX`, `PremiumRack`, `Scene` (`SceneInfo`), `Preset` (`PresetInfo`) |
| `Setup` | `SetupBackupFile.bup` and its `.old` copy |
| `PresetList`, `SceneList` | the library and scene lists |
| `Scn/UserA` | one `.dm7s` file per stored scene, with its own `SceneInfo` and `Mixing` |
| `Lib/<type>` | one `.dm7p` file per library preset |

The outer file also has a `Project` section (function `ProjectInfo`). Its `Info.ProductName` is `DM7` or `DM5`, and its
`Info.ProductSubName` is `DM7`, `DM7C`, `DM5` or `DM5C` (BB-DM-MODEL). A TF Editor session has `ProductName` `TF` and
`ProductSubName` `TF5` (BB-G2-WALK).

The tests wrote every change into `CurrentBackupFile.bup` and into its `.old` copy, and the editor loaded the result
(BB-DM-LOAD). This tool does the same and copies every other entry byte for byte.

### 4.5 DM7 values (paths in the file's own schema)

Paths are in the `Mixing` section of `CurrentBackupFile.bup` unless named. `[ch]` is the input channel, 0 based.

| Value | Path | Encoding | Test |
| --- | --- | --- | --- |
| Name | `InputChannel[ch]/Label.Name` | text, 64 bytes. DM Editor shows 8 characters, so this tool writes at most 8 | BB-DM-LOAD |
| Colour | `InputChannel[ch]/Label.Color` | text: `Blue`, `Orange`, `Yellow`, `Purple`, `SkyBlue`, `Pink`, `Red`, `Green`, `LtGreen`, `White`, `OFF` (the Channel List's column order) | BB-DM-SAVE |
| Fader | `InputChannel[ch]/Fader.Level` | signed 16-bit, 0.01 dB; -32768 = -inf. Any 0.01 dB from -138 to +10 dB | BB-DM-LOAD, BB-DM-RANGE |
| Channel on | `InputChannel[ch]/Fader.On` | bit, 1 = on | BB-DM-LOAD |
| Patch | `InputChannel[ch]/InPatch.Select` picks the bank; `InputChannel[ch]/InPatch[0]/Bank[Select].Source` holds the code | u32 code, below | BB-DM-LOAD |
| HPF | `InputChannel[ch]/HPF[0].On`, `.Frequency` when `InputChannel[ch]/PEQ.ActorSelect` is 0 | bit; u32 in 0.1 Hz. Any 0.1 Hz from 20 to 2000 Hz | BB-DM-SAVE, BB-DM-RANGE |
| Head amp | `Processing` section: `Omni[0]/InputPort[n-1]/HeadAmp.Gain`, `.48V` for OMNI n | signed 16-bit, 0.01 dB, written in whole dB; bit, 1 = on | BB-DM-LOAD, BB-DM-ORDER |
| DCA assign | `InputChannel[ch]/DCA.Assign` | 24 bits, bit k-1 = DCA k | BB-DM-SAVE |

Patch codes (BB-DM-LOAD, BB-DM-ORDER): 0 = none; `(0x0140 << 16) + 0x1000 + (n-1)` = OMNI n (1 to 32);
`(0x01A0 << 16) + (n-1)` = DANTE n (1 to 144). The tests wrote and the editor showed OMNI 9, 13 and 14, DANTE 5 and
DANTE 144, and none. Other codes are shown as raw numbers.

A head amp change goes to the port that the channel is patched to at that moment, after any repatch earlier in the
same pass (BB-DM-ORDER). A channel on another EQ type keeps its HPF in another element; that element is not proven,
so this tool neither reads nor writes it.

### 4.6 Parameter shapes (BB-DM-SHAPE)

Every generation-2 file at hand gives these parameters the same shape. This tool refuses a file with any other shape
as damaged, so it never reads or writes a value as the wrong kind.

| Parameter | Shape |
| --- | --- |
| `Label.Name` (inputs, mixes, matrices, stereo, DCAs) | text, 64 bytes |
| `Label.Color` | text, 8 bytes |
| `Label.Icon` | text, 12 bytes |
| `Fader.Level` | signed, 2 bytes |
| `Fader.On` | a bit (TF and DM3: unsigned, 1 byte) |
| `InPatch.Select`, `HPF.On`, `HeadAmp.48V` | a bit |
| `InPatch/Bank.Source`, `HPF.Frequency` | unsigned, 4 bytes |
| `PEQ.ActorSelect` | unsigned, 1 byte |
| `DCA.Assign` | 24 bits |
| `HeadAmp.Gain` | signed, 2 bytes |
| `SceneInfo/Info.Title` | text, 64 bytes |
| `ProjectInfo/Info.ProductName`, `ProductSubName` | text, 32 bytes |

## 5. What this tool writes, and the proof

| Console and file | Writes | Proof (write and load, the engine this script was ported from; byte-identical writes) |
| --- | --- | --- |
| CL, scene format 5, 6 or 7 | names, colours, icons, patch (none, DANTE, OMNI, PB, SLOT), OMNI gain and +48V, HPF on and frequency, faders, channel on, DCA assigns on mono channels, mix, matrix, DCA and mute group names | A new CL5 session (format 7) and two real CL shows (formats 5 and 6) with every one of these writes: CL Editor showed each value, and its re-save and CSV export matched 147 items with 0 mismatches each |
| QL, scene format 6 or 7 | the same, with INPUT 1 to 32 | A new QL1 session and a real QL show (format 6): 99 and 131 items, 0 mismatches |
| CL, scene format 7, stored scenes | names, colours and patch | A session with 2 stored scenes: the re-save held each scene's values, and a recall showed them (BB-SCENE) |
| DM7 (ProductSubName `DM7`), firmware V2.01 | names (8 characters), colours, patch (none, OMNI 1 to 32, DANTE 1 to 144), OMNI gain and +48V, HPF, faders, channel on | DM Editor 2.0.1 showed every value; its re-save matched 208 items with 0 mismatches (BB-DM-LOAD, BB-DM-RANGE, BB-DM-ORDER) |

Every write keeps the file kind, the scene format or firmware version, the record tree and every byte it does not
change. A CL or QL write keeps the file size and fixes each checksum it touches. A DM7 write recompresses only the two
current backups.

No written file has been loaded on a real console yet. The editor is the gate: open the file in the editor, save it
there, and load that save.

## 6. Not proven: read-only or refused

| Item | Status | The test that would settle it |
| --- | --- | --- |
| Sends (every console) | not read | set send levels, on and pre in the editor, save, compare |
| EQ, dynamics, delay, inserts, output patch | not read | the same, one parameter at a time |
| Mix, matrix and stereo faders, ON keys and bus types | not read | the same |
| Mute group assigns (CL, QL) | read only | a write-and-load test |
| DCA assigns on an ST IN | refused | a write to both slots, loaded in CL Editor |
| Rack outputs as a patch source | read only | reading the rack set-up first (BB-RACK) |
| Rio and other stage box head amps | not read | set gain and +48V on a stage box input in CL Editor, save, compare |
| Stored scenes on CL formats 5 and 6, on QL and on DM7; stored-scene writes of anything but names, colours and patch; bus names in stored scenes | refused | a recall test like BB-SCENE for each |
| Stored scene titles in scene format 6 | read, marked `?` | a format 6 file with stored scenes opened in CL Editor, the Scene Memory list compared |
| QL files in scene format 5 | read only | a QL show in format 5 through the write-and-load test |
| DM7 firmware 1.x files | read only | the DM7 test in DM7 Editor 1.7.5, the editor for firmware 1.x |
| DM7 firmware other than V2.01; DM7 Compact, DM5, DM5 Compact | read only | the DM7 test on a session of that firmware or model |
| DM7 icons, DCA assigns, mix, matrix and DCA names | read only (icons and names as stored, unproven) | a write-and-load test of each |
| DM3 and TF | read only; names, colours, icons, faders and ON keys are read by the DM7 paths, unproven | a rename test in DM3 Editor and TF Editor, then the rest |
| RIVAGE PM | refused | a reader for its sections |
| User keys (`.CLU`, `.dm7u`), scene-only and library files | refused by design | none: they hold passwords or are not a show |
| A console load of a written file | not tested | one written CL or QL file and one DM7 file loaded on a console at prep |
