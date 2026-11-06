# DiGiCo I/O patch: racks, input patch, output patch and snapshots

This page gives the rules to change the I/O patch of a session by bytes. The page covers adding, swapping and removing a rack, the input patch with gain, 48V and pad, and the output patch of the buses. The page also says what a snapshot keeps of the patch and what a recall does to a patch change.

[`FORMAT.md`](FORMAT.md), "FX units, sends, buses and patch", and [`session-structure.md`](session-structure.md), "Ports, sockets and patch", give the layout of the device records, the sockets and the routes. This page adds what the offline editors proved on 2026-11-01. The site engine below is the web engine at [I Don't Own a PC](https://idontownapc.com).

Each fact says how it was proven:

- "Editor load": the offline editor opened a file written by bytes, and its re-save kept the change.
- "Plain boot": what the editor changes in an unchanged file when it loads and saves the file. A difference from the plain boot belongs to the change.
- "Recall experiment": a snapshot fired in the editor on a file with a live change, then saved and compared.
- "Not proven": no editor run covers it.

Keys are (module, param, band) in hex, as in [`FORMAT.md`](FORMAT.md). A key written `12/00` is module 12, param 00.

## Racks

- Port 0 is the Local I/O. A rack sits on port 1 to 19.
- A rack is declared in four places, all keyed by its port k: section 246 record k, an input socket group and an output socket group in section 201, one socket object per socket in section 211, and the patch-bay pages at the head of section 201. The `patch.py` part of [`script-notes.md`](script-notes.md) has the detail.
- Add: the new rack takes the first free port. Editor load: an SD Rack on the Quantum 225 at V2242 and V1619, and an MQ-Rack on the Quantum 225 at V2242.
- Swap: the new device takes the port of the old one, and every route to the old sockets clears. Editor load: MADI 64 swapped for an SD Rack on the SD12 at V2242 and V1619.
- Remove: the record, the two socket groups, the socket objects and the patch-bay labels of the port go. The page ids stay, as on the empty ports of a default session. Editor load: Rack 1 removed on the Quantum 225 at V2242. The removal cleared 33 routes.

### Routes to a removed rack

- A remove clears every route to the sockets of the rack. The routes are input patches, insert sends and returns, direct outs, key inputs, bus outputs and socket copies.
- The clear also empties the output route (`0e/fe`) of a bus that fed a socket of the rack. The empty route is a fault when the bus fed another socket too. In a default session the Master feeds a Local I/O output and a rack output.
- The checker then reports: socket 0:Line 1 is fed by Master, whose own output route is empty.
- After a remove or a swap, point the output route of each bus side at a socket that still carries the bus. Clear the route when no socket carries the bus.
- Editor load: Quantum 225 V2242, a rack removed. The editor kept the repaired route.

### A rack on a link the console lacks

- A console keeps a rack only on a MADI link that the console has. On a link past them, the editor keeps the sockets and sets the device id to 0, which means not connected. The MADI bullets in [`quantum/README.md`](../quantum/README.md) and [`sd/README.md`](../sd/README.md) list the links of each console.
- An add on a console whose links are all in use declares the rack and gets that result. Refuse such an add. The SD12 and the SD9 take a swap, not an add.
- The Quantum 225 has three links, so the site engine refuses a second added rack there.

## Input patch, gain, 48V and pad

- One write puts a run of channels on consecutive sockets of a device, from a chosen socket. The write matches the console's auto patch. A stereo channel takes two sockets. Gain and 48V move with the channel.
- Gain, 48V and pad belong to the input socket, not to the channel. Module `11` holds them: params `86` (gain), `83` (48V) and `89` (pad). The gain of a channel is the gain of the socket under the channel.
- A stereo channel has no alt input. A mono channel has one.
- The I/O screen of the site engine added no new bytes for inputs and gain. The older writers made the files below.

## Output patch

The bytes for one bus side:

- The output socket's source route (`12/00`) is the bus side's object: `00 00 <index> <type>`.
- The bus side's own output route (`0e/fe`) is that socket.
- A side that fed other sockets clears first. An FX unit feed stays.
- The bus that fed the socket before keeps a route of its own. The route points at a socket that still carries the bus, or it clears.
- A socket that an insert send or a direct out feeds has a tap byte in its source route. Refuse such a socket as a target.
- The INTERNAL outputs (type `4d`: solo and talkback) are not rack outputs. Do not offer them.

The rules for buses:

- A stereo bus has two side objects. The left side goes on the socket and the right side goes on the next socket. Each side has its own routes.
- A run of buses goes in order onto consecutive sockets of one device. A stereo bus takes two sockets. Stop with a sentence when the device runs out of outputs.
- The older `sends.patch_output` writes the same bytes for a whole bus, mono or stereo.

Only aux outputs are proven. A group, matrix or Master output on a rack socket has not been written and booted in an editor. Unpatching a group output is in the proof files, so the site engine allows it. The site engine refuses to unpatch a matrix or Master output.

## Proven changes

| Change | Console and build | Proof |
| --- | --- | --- |
| Input patch, gain, 48V, pad and aux output patch | 115 console and build pairs of Session Maker builds that held an input patch, 48V and monitor mixes on rack outputs | editor load, re-save with no difference |
| Add an SD Rack | Quantum 225 at V2242 and V1619 | editor load |
| Add an MQ-Rack | Quantum 225 at V2242 | editor load |
| Swap a rack | SD12 at V2242 and V1619 | editor load |
| Swap a rack | SD9 at V2242, Standard MADI for a D2-Rack | earlier editor run, the rack change only |
| Remove a rack | Quantum 225 at V2242 | editor load |

The site engine closes every other pair. The refusal is one sentence that names the proven consoles.

## Proof files (2026-11-01)

Each file came from a sample session or an editor default. The writers above made the change. Each file carries:

- the rack change;
- channels 1 to 8 on the rack from socket 1 (channel 8 is stereo in the sample, so nine sockets);
- 48V and +30 dB on one socket, and pad and +12.5 dB on another;
- aux 1 and 2 on rack outputs 1 and 2, and aux 3 on output 9;
- group 1 with no output.

| Console and build | Change | Result |
| --- | --- | --- |
| Quantum 225 V2242, sample session | add an SD Rack on port 3 | Loads. The strips read `01 3:Mic 1` to `08 3:Mic 8`, with +30.0 and the 48V lamp on one and +12.5 on another. The re-save equals the plain boot |
| Quantum 225 V2242, same session | remove Rack 1 (33 routes cleared) | Loads. The re-save equals the plain boot |
| Quantum 225 V2242, editor default | add an MQ-Rack | Loads. The re-save equals the plain boot |
| Quantum 225 V1619, editor default | add an SD Rack | Loads. The re-save differs only in section 219 stamps and section 243 heap words |
| SD12 V2242, editor default | MADI 64 swapped for an SD Rack | Loads. The re-save equals the plain boot |
| SD12 V1619, sample session | MADI 64 swapped for an SD Rack | Loads. The re-save differs only in sections 219 and 243 and the two FX name flags, as the unchanged sample does |

A plain boot of the unchanged file changes:

- section 219 (module stamps) and section 243 (bank heap words);
- one byte of section 210, and six bytes of section 201 on the Quantum 225 V2242;
- the Solo objects `0b00` and `0b01`;
- on the sample session, the two FX name flags (`0e00`, `0e01`).

In every file the differences from the editor's save are a subset of that list. No route, gain, 48V, pad, rack record or socket group differs.

## Snapshots

A snapshot holds a copy of the patch. Read from a Quantum 225 V2242 session with 3 snapshots:

- Every snapshot keeps pool states for the live strips. The states hold the channel source routes (`01/00`), the bus output routes (`0e/fe`), the output socket sources (`12/00`), and the gain, 48V and pad of the input sockets (`11/86`, `11/83`, `11/89`).
- In that session every one of them equalled the live value.
- Module `11` params `80`, `84`, `c8`, `c9` and `fe` are never kept ([`snapshots.md`](snapshots.md), "Params a snapshot never keeps").

### Recall experiment (Quantum 225 V2242)

The start file was that session. A live change was written by bytes:

- input 1 moved from `1:Mic 1` to `1:Mic 40`;
- input 2 gain went from 19.0 to 33.5;
- input 3 got 48V and pad;
- aux 1 went on `1:Line out 20`.

The editor loaded the file, fired snapshot 1 and saved.

| After snapshot 1 | Before the recall | After the recall |
| --- | --- | --- |
| Input 1 source | `1:Mic 40` | `1:Mic 1`. The snapshot's route came back |
| Aux 1 output | `1:Line out 20` | none. The snapshot's route came back |
| Input 2 gain | 33.5 | 33.5. Kept |
| Input 3 48V and pad | on, on | on, on. Kept |

Snapshots 2 and 3, fired one after the other in the same boot, gave the same result.

What the experiment shows:

- A patch change made by bytes on a session with snapshots lasts only until the next recall that reaches it.
- Gain, 48V and pad stayed in this session. Its Global Scope is the default, and the default recalls no module of the input ports ([`scope-and-recall.md`](scope-and-recall.md), "Global Scope defaults and the clear"). A show whose Global Scope recalls its I/O ports could bring them back. No run tested another scope.
- The aux output fits "Output sockets follow their feeder" in [`scope-and-recall.md`](scope-and-recall.md): a socket's source comes back with the Outputs of the strip that feeds it. The snapshot held the socket with no source, so aux 1's recalled Outputs left it empty. Six recalls fired and saved at V2242 follow the same rule: five in Quantum 112 files, one in the Quantum 326/338 editor.
- The experiment ran on one console and build. No SD file was tested.

## Rules the site engine follows

1. Run a change only for a console and build in "Proven changes". Refuse every other pair with one sentence that names the proven ones.
2. Refuse every I/O change on a session with snapshots. The sentence says to patch on the console, or to remove all snapshots first. The next recall would bring the snapshot's routes back.
3. Patch aux outputs only. Allow unpatching an aux or a group. Refuse to patch a group, matrix or Master output, and refuse to unpatch a matrix or Master output.
4. Refuse an add when no port is free, and when the console has no free MADI link.
5. Refuse a target socket that an insert send or a direct out feeds. Do not offer the INTERNAL outputs.
6. After a remove or a swap, repair the output route of each bus side.
7. Offer three rack types: the SD Rack, the MQ-Rack and the D2-Rack. No pair is proven for adding a D2-Rack, so the site engine refuses that add everywhere.

## Not proven, so closed

- Group, matrix and Master outputs on a rack socket: no file was booted with one.
- Add a rack on the Quantum 326/338: the older proof predates the change to the device writer that clears the routes of the new sockets. A file from the current writer was never booted.
- Add a D2-Rack: no editor run is recorded.
- Any I/O change on a session with snapshots: the next recall undoes the routes, and no editor capture shows what the editor's own patch change writes into the snapshot copies.
- Every console and build outside "Proven changes".

## What we don't know

- The editor's Patch screen and Session Report were not driven. The Channel Surface strips show the same data: the socket name, gain, 48V and pad of every patched channel.
- The Quantum 326/338 and SD9 editors were not part of these runs. The SD9 swap comes from an earlier run and proves the rack change only. The combined patch was not run again.
- Whether the editor's own patch change on a session with snapshots writes only the live copy. If it does, a write of the live copy equals it.
- A carry that writes the new route into every snapshot copy that held the old route. Nothing builds it, and no editor capture exists.
- Adding a D-Rack, Standard MADI, MADI 64, USB or Local Dante device: not part of these runs.
