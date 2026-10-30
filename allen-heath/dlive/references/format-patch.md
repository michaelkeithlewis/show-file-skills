# dLive Director V2.12: `Channel Mapper` scene section

Binary: the dLive Director V2.12 macOS executable (Mach-O x86_64, sha256 `60a99e45…5764`).
Sample: a stored StageBox scene from a Director-saved FOH show.
Addresses are virtual addresses in the binary (image base `0x100000000`; for
`__TEXT` the file offset is `addr - 0x100000000`).

Status: DONE, see "Final" at the bottom. (confirmed) is read from the
instructions and checked against the sample; (inferred) is reasoning from names.

## 1. Read / write functions (confirmed)

| Role | Function | Address |
| --- | --- | --- |
| Write (serialize whole section) | `cChannelMapper::GetStatus(cAHNetMessage&)` | `0x1001cefe0` |
| Read (deserialize) | `cChannelMapper::SetStatus(cAHNetMessage&, bool, int)` | `0x1001d0720` |
| Talkback tail writer | `cChannelMapper::FillInTalkbackMessageData(...)` | `0x1001d0020` |
| Talkback tail reader | `cChannelMapper::UnpackTalkbackInfo(...)` | `0x1001d0160` |

`GetStatus` calls `cAHNetMessage::SetLength(0x288c)` and then
`SetDataBufferUBYTE(6, 0)`: the payload is a fixed 10380 bytes and byte 0 is the
format version, 6.

Framing check on the sample: the `u16be` before the label is `0x289b` = 10395 =
15 (`"Channel Mapper\0"`) + 10380. The section length counts label + NUL +
payload, and the payload length is the constant `0x288c`.

## 2. Payload layout (confirmed from `GetStatus`)

`ref` = 3 bytes: `type` (u8, `eAudioSourceType`) + `number` (u16 big-endian).
In memory an `sAudioSource` is 8 bytes (`int type` at +0, `u16 number` at +4).

| Offset | Size | Count | `this+` | Content |
| --- | --- | --- | --- | --- |
| 0x0000 | 1 | 1 |: | version = 6 |
| 0x0001 | 13 | 128 | 0x80, 0x88, 0x90, 0x98, 0xa0 | per input channel: active source (u8) + ref A + ref B + ref C + ref D |
| 0x0681 | 3 | 128 | 0xa8 | ref array |
| 0x0801 | 3 | 128 | 0x158 | ref array |
| 0x0981 | 1 | 128 | 0x1a8 | bool array |
| 0x0a01 | 1 | 1 | 0x1b8 | byte |
| 0x0a02 | 1 | 1 | 0x1c0 | byte |
| 0x0a03 | 1 | 1 | 0x1c8 | byte |
| 0x0a04 | 3 | 128 | 0xb0 | ref array |
| 0x0b84 | 3 | 128 | 0xb8 | ref array |
| 0x0d04 | 3 | 512 | 0x178 | ref array |
| 0x1304 | 3 | 64 | 0xc0 | ref array |
| 0x13c4 | 3 | 32 | 0xc8 | ref array |
| 0x1424 | 3 | 64 | 0xd0 | ref array |
| 0x14e4 | 3 | 32 | 0xd8 | ref array |
| 0x1544 | 3 | 6 | 0xe0 | ref array |
| 0x1556 | 3 | 64 | 0xe8 | ref array |
| 0x1616 | 3 | 32 | 0xf0 | ref array |
| 0x1676 | 3 | 64 | 0xf8 | ref array |
| 0x1736 | 3 | 32 | 0x100 | ref array |
| 0x1796 | 3 | 64 | 0x108 | ref array |
| 0x1856 | 3 | 32 | 0x110 | ref array |
| 0x18b6 | 3 | 6 | 0x118 | ref array |
| 0x18c8 | 3 | 64 | 0x120 | ref array |
| 0x1988 | 3 | 32 | 0x128 | ref array |
| 0x19e8 | 3 | 32 | 0x130 | ref array |
| 0x1a48 | 3 | 1 | 0x138 | ref |
| 0x1a4b | 3 | 32 | 0x140 | ref array |
| 0x1aab | 3 | 16 | 0x148 | ref array |
| 0x1adb | 3 | 16 | 0x150 | ref array |
| 0x1b0b | 3 | 128 | 0x160 | ref array |
| 0x1c8b | 3 | 128 | 0x168 | ref array |
| 0x1e0b | 3 | 128 | 0x170 | ref array |
| 0x1f8b | 3 | 32 | 0x180 | ref array |
| 0x1feb | 3 | 32 | 0x188 | ref array |
| 0x204b | 3 | 40 | 0x190 | ref array |
| 0x20c3 | 3 | 64 | 0x198 | ref array |
| 0x2183 | 3 | 4 | 0x1a0 | ref array |
| 0x218f | 1789 |: |: | talkback block (`FillInTalkbackMessageData`), ends at 0x288c |

Meaning of each `this+` member: see "Final" below.

## Method note

The tables above were read from raw disassembly (GNU objdump plus the demangled
Mach-O symbol table). A full Ghidra import of the 125 MB binary was not needed.

## Final (2026-10-11)

Status: DONE for the input/output patch. Tool: `scripts/dlive_patch.py`.

eAudioSourceType (one enum for sources, from CSVImportUtilities LocationsToUsefulTypes /
ChannelsToUsefulTypes static tables + sample data): 00 MixRack sockets, 01 Surface (0-11 local,
12-43 DX 5/6, 44-171 I/O Port 4, 172-299 I/O Port 5, 300+ USB; outputs 0-15/16/48/176/304),
02-04 MixRack I/O Port 1-3, 05 DX 1/2, 06 DX 3/4, 07 Ip direct out, 08/09 Ip insert A/B send,
0C Grp, 0D St Grp, 0E Aux, 0F St Aux, 10 Main, 11 Mtx, 12 St Mtx (stereo = 2*(n-1)+L0/R1),
13 PAFL, 14 unassigned, 15-1B mix insert sends (Grp, St Grp, Aux, St Aux, Main, Mtx, St Mtx),
1C FX return, 1D FX send, 1E Wedge, 21 IEM, 26 VSC playback port socket, 27 Dyn unit out,
28 Ip VSC record point, 2A SigGen, 2B Talkback, 2D UFX return, 2E UFX send.
Active byte: 0 ABCD off (A), 1-4 A-D (GetActiveInputChannelSource jump table @0x1004fe140).

Member -> meaning from the per-destination patch methods (LocalOutputPatch +0x130,
IOModule1-3OutputPatch +0x160/168/170, GACEOutputPatch +0x178, TSnake1/2OutputPatch +0x180/188,
MEOutputPatch +0x190, DynamicsUnitPatch +0x198, RackPatch +0x140, AHFXRackPatch +0x148, ...).

Verified against Director V2.12 screenshots of a real show: MixRack, I/O port and surface sources, ABCD active state and talkback source all match.

Note: a Ghidra import of the 125 MB binary needs more than 6 GB of RAM. The decode came from the
symbol table, objdump disassembly and Director's own tables.

## Virtual soundcheck

- `0x0a01` port, `0x0a02` range start, `0x0a03` range end. Port is an I/O port index; Director maps it with
  `cSocket::IOPortToLocation` @0x100737ba0 (table [9,10,11,3,4,14]): 0-2 = MixRack I/O Port 1-3, 3-4 = Surface
  I/O Port 4-5 (the CTi1500 has one, "IO 4" in the tools), 5 = location 14. Start byte = first socket - 1, end byte
  = last socket (`SetVirtualSoundCheckRangeStart/End` @0x1001c6850/@0x1001c6910 clamp to 0x7f / 0x80).
- `0x0681` VSC input source per channel: type 0x26 "VSC port n", n = socket on the VSC port.
  `cChannelMapperBase::VirtualInputActive` @0x1004fe090: flag[ch] (`0x0981`) and n inside [start, end) and VSC
  mode == 2 and type == 0x26. A channel with no VSC source keeps its live input in playback.
- `0x0801` VSC record send, indexed by port socket: type 0x28 "Ip n VSC rec". The companion test @0x1004fe0f0
  is true in mode 1, so record outputs only run in VSC mode 1 (one SoftKey for mode 1, one for mode 2).
  One touring show also kept normal output patches on the same sockets (they apply when VSC is inactive).
- The VSC mode is not in this section. Seen: port 0 (IO 1) 75-124 on one show, port 3 (IO 4) on others.
- Insert sends as output sources: 0x08/0x09 "Ip n Ins A/B send", 0x19 "Main Ins send 1 L/R"; `Main Ins return`
  rows 1/2 = L/R.
