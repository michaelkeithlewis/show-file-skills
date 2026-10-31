# DiGiCo engine findings

This page holds facts that the web engine at [I Don't Own a PC](https://idontownapc.com) proved and that the code in this folder does not use yet. A fact about one model line is in [`quantum/README.md`](../quantum/README.md) or [`sd/README.md`](../sd/README.md). Each fact says how it was proven.

The last section lists the guards that the scripts in this folder still lack. A note does not stop a bad file, so read that section before you trust a build.

## Input paths and bus slots

Measured in the real offline editors, Files > Session Structure, at every build the engine writes (V1455 to V2242), on 2026-10-24. No limit changes with the firmware. The numbers per console are in the model READMEs.

- The dialog counts input paths, not channels. A mono input takes 1 path and a stereo input takes 2. Proven on SD7, Quantum 5 and SD12 at V2242: one added stereo input took 2 from the spare count.
- An FX return is an input channel, so it counts the same way. A stereo return takes 2 paths.
- Bus slots are the aux and group widths added together: mono 1, stereo 2, LCR 3, LCRS 4, 5.1 6. The stereo Master counts. The 4 solo paths do not count.
- The dialog allows (widest group width - 2) more bus slots when a group is wider than stereo.
- Three limit rules exist. `fixed`: paths and bus slots have separate limits, and matrix outputs do not count. `q5_pool` and `sd_pool`: paths share a pool (see the model READMEs).
- 96 kHz does not change a limit, except the bus limit on SD5 and SD7. This replaces the comment in `buses.py` that says 96 kHz budgets are not measured.

### A file over the path limit

A file with too many paths loads and re-saves unchanged, because the load check reads channels, not paths. The damage comes later:

1. The Session Structure dialog opens the file clamped to the limit.
2. The first Restructure deletes the last mono inputs, as many as the paths are over. The count box skips stereo inputs.

Proven on Quantum 225: a file with 64 inputs, 12 of them stereo (76 paths), opened at 60, and a Restructure with no change deleted inputs 61 to 64. We do not know if a real console processes paths past the limit. No console test has been run.

## Header console check

Every editor and console runs a console check on the file header. A file that fails loads as the empty default session, with no dialog and no error. Your show is gone from the screen, and a save writes the empty session.

The check reads these header fields. The limits per console and build come from the check routine of each offline editor. The model matched the routine with 0 disagreements on 3,000 fuzzed headers and 162 real headers per build and option state.

| Header | Field | Rule |
| --- | --- | --- |
| `0x26` | input channels | at most the console's input count |
| `0x93` | matrix outputs | at most the console's count |
| `0x94` | control groups | at most the console's count |
| `0x96` | matrix inputs | at most the console's count |
| `0x97` | graphic EQs | at most the console's count |
| `0x36`, `0x46` | aux and group counts per width | sum of width x count, at most the bus limit + (widest group width - 2) |
| all of the above | SD5 and SD7 only | 1 + inputs + matrix outputs + bus paths, at most 256 |

- This limit is not the dialog limit. The Quantum 5 check allows 256 inputs and 134 bus paths and does not know the dialog's pool, so a file can pass this check and still be cut by the dialog.
- The check reads channels. A file with too many channels fails here, and it does not reach the Restructure case above.
- The counts are not the whole check. A plain SD12 editor also refused an SD12-96 file that was inside the plain counts ([`sd/README.md`](../sd/README.md)).

## Header byte 0x25, bit 0x10

The bit means "this console's extension", and its meaning depends on the console:

| Console | Bit means |
| --- | --- |
| SD12 | SD12-96 |
| SD11 | SD11i |
| Quantum 225, Quantum 338 | Pulse |
| SD5, SD5 CS, SD7, SD8, SD9, SD10 | nothing to act on: every default session sets it |

Proven by the header of 121 editor-saved default sessions. Quantum 112, 5, 7 and 852 defaults, and plain Quantum 225, Quantum 338, SD11 and SD12 defaults, have the bit clear.

The extension belongs to the editor, not to the file. The rule for each direction is in [`sd/README.md`](../sd/README.md).

## Inserts: rules for every console

- An input channel's inserts live in module 08. Band 0 is insert A and band 1 is insert B. The slots are `02` on, `fe` send route, `00` return route, and `e1` insert point on Quantum.
- The destination holds the channel as its source, as a tap. Quantum writes `08 <band << 4 | side> <idx> 01`. The SD tap bytes are in [`sd/README.md`](../sd/README.md).
- A stereo channel takes two Spice Rack slots, two graphic EQs, both sides of an FX unit, or two sockets in a row. The channel names only the left one.
- Taking a destination from another channel clears that insert's send, return and on. The editor asks first ("Unroute these and proceed?"). Do the same.
- A destination that an aux, a bus or a direct out feeds is not free. The editor would unroute the feed.
- Clear the inserts before you remove a channel, and clear them on the right channel when two channels become a stereo pair. Clearing gives the destinations back. A tap left behind names a channel that is not on the surface, and the engine's routing check treats that as a fault.
- When a channel changes width, clear its routed inserts first and route them again for the new width. A split's right channel starts with no inserts.
- A snapshot holds its own insert routes and on switches. Store the snapshots again after you route inserts. What a console does when a recalled route names a destination another channel now holds is unverified.

The write op passed editor proofs: every planned slot was byte-exact in the editor's re-save on all 13 V2242 editors, on Quantum 225 V1619, and on a real 32-snapshot Quantum 225 V1619 show.

## FX units

- A TenTap delay takes 4 EngineChannels. Every other unit tested takes 2. This replaces "2 per unit" in the `fx.py` header. Proven on Quantum 225 V2242 and V1619 and SD12 V2242: the unit after a TenTap delay came back at its EngineChannel + 4.
- The editors re-pack the EngineChannels of every FX unit on load. Each pool (reverbs, other effects) fills from its start, in object id order. A hole that a removed unit left is filled. Units follow their object ids, not their rack numbers.
- Write the re-packed numbers on every add and every remove, so the editor's re-save stays identical. Every unit, preset, feed and return was kept in the 12 proof boots.

## I/O devices

The name switch of older editors has no case for some device types. A file for that build must not declare one.

| Device type byte | Device | Editors with no name for it |
| --- | --- | --- |
| `0x0d` | A20-Opto | V1619 and older |
| `0x0e` | Fourier Interface | V1619 and older |
| `0x0f` | Local Dante | V2025 and older |
| `0x39` | DMI AVB | V1455 |

Proven by reading the device-name switch in the Quantum 2 editor binary at each build.

## Fader banks

Tried in the real offline editors on 2026-10-31, at V2242 and, for the Quantum 225 and SD12, at V1619. The bytes are in [`FORMAT.md`](FORMAT.md), "Fader bank placement". The bay map of each console is in the model READMEs.

A bank move takes one bank to another button, layer or bay, or swaps two banks. The site engine follows these rules:

- Write the two u16 in section 212 and the same two in the 211 tail. Change nothing else. This is what the editor's own move writes.
- Allow a move only on a console family whose moves were proven in its editor: `Q2`, `Q3`, `SD5` and `SDC`.
- Refuse a move that would leave layer 1 of a bay with no bank. The editor adds a blank bank there on load. A swap never does this.
- After a move, check the layer the bank left. If its shown button is now empty, point it at a bank that is still in the layer: the button the bank moved to when it stayed in the layer, else the first one. The same move back then restores every byte.
- Refuse when the two copies of section 212 differ.
- Refuse while any snapshot has the Layout switch on in its misc scope, or when the snapshot list cannot be read. The first is a precaution (see "Layout and snapshots").
- A bank on no button can be put on a button. Write the same bytes as a move. The bank that was on the button goes to the bank list.

Proven on the Quantum 225 and SD12 (V2242 and V1619) and on the Quantum 326/338 and SD5 (V2242). The moves tried were inside a layer, across layers, across bays and from the Centre bay. In each editor the Fader Banks screen showed every moved bank. The boot re-save kept section 212 byte for byte and added no bank. A first proof file without the shown-button rule got a blank bank on each layer 1 that a move had emptied. Putting a bank from the list on a button was proven on an SD12.

Not tested: a bank placed on a position the screen does not show, and any family not named above.

### Layout and snapshots

Each snapshot keeps its own copy of section 212 ([`snapshots.md`](snapshots.md), options +0x012). With the misc switch Layout on, a recall puts back which bank each layer shows. A move can change the shown button of a layer, so the site engine refuses while a snapshot has Layout on. [`scope-and-recall.md`](scope-and-recall.md) reports that a recall leaves moved bank buttons where they were, so the refusal may be stricter than needed. No recall was fired on a file after a bank move.

## Fader banks on a console swap

A console swap writes a session for another console and keeps the settings of the old one (for example Quantum 326/338 to SD12). The site engine now carries the fader banks too: names, second lines, colours, strips and where each bank sits. It does so only for a target whose bank moves were proven (`Q2`, `Q3`, `SD5`, `SDC`). Any other target keeps its default layout, and the report says it was reset. Rules:

- Same family: keep every bank, record, layer and button as the source has them, and the button each layer shows.
- Another family: go bay by bay in order (the source's first bay to the target's first bay) and layer by layer. Keep a bank on the same button when the target has that button.
- A bank that does not fit goes to the first free button of the same layer number in reading order, then to the first free button anywhere. With no free button left it stays in the bank list on no button.
- Strips: an input keeps its internal index. An aux, group or matrix strip is matched by the number on the console, because the stored index is the bus's band byte. A strip whose channel the target lacks is emptied. A bank left with no strip at all does not come over.
- For what only the target has (later matrix outputs and control groups), add the target's own default banks with only those strips, on no button.
- A bay whose layer 1 ends with no bank gets a blank bank on its shown button, as the editor does on load.
- Colours: the default colour of each kind of bank becomes the target's default ([`FORMAT.md`](FORMAT.md), set A or set B). The target's set is the one its own default session holds. The Quantum 5 and Quantum 7 defaults hold set B. On an SD target, any other colour becomes the nearest of the seven seen on SD banks.

Proven in the V2242 editors on five swaps: Quantum 326/338 to SD5, Quantum 326/338 to SD12, SD12 (V1619) to Quantum 225, Quantum 225 to Quantum 326/338, and a Quantum 326/338 with a bank on all 36 buttons to SD12 (34 banks, 10 on no button). In each editor the Fader Banks screen showed every bank on its bay, layer and button with its name, second line and colour. The boot re-save kept the bank list and section 212 byte for byte.

Not tested:

- A swap inside one family. The rule keeps the banks, section 212 and its tail copy as the source has them. This was byte-checked on default sessions of each family. No such file was booted in an editor. The model READMEs list the pairs.
- Strips. The runs compared bank names, second lines, colours and positions after the re-save, not the strips. The strip match comes from the site engine's own reading of the section 201 ids.

## Guards this folder does not have yet

These stop a bad file in the web engine. The scripts here do not do them.

1. Path limits: refuse on input paths, not channels, with the pool rules for Quantum 5, SD5 and SD7. `consoles.py` still caps channels. A warning when a file that is already over opens.
2. Option keys: `sd12_96` and `sd11i`, read from header `0x25` bit `0x10`.
3. Header console check: refuse a file the target editor would replace with the empty default.
4. 48V: do not write 48V on the SD7 and Quantum 7 Local I/O Mic/Lin inputs.
5. MADI links: `MADI_LINKS` has only SD9 and SD12. Add SD8, Quantum 225, SD5 and SD7.
6. Inserts: no insert write op exists here. Its rules are the second-insert refusal on SD9 and SD11, the 32 mono post-fader cap, the tap fix-up, the refusal of a Chilli 6 and Naga 6 stereo pair, and clearing inserts on a remove or a width change.
7. FX: `WIDE_ENGINE` for TenTap, and the re-pack on add and remove.
8. Sibling files: refuse an SD8 file for an SD10, or an SD10 file for an SD8.
9. Device names: refuse a device type the target build's editor does not name.
10. Bank bays: `busside.py` reads bays for `Q2` and `SDC` only, as 3 layers of 4 buttons. The site engine reads ten families, each with its own layers and buttons (model READMEs).
11. Bank moves: no op moves a bank here. Follow the rules under "Fader banks". Keep the 211 tail copy equal and each layer's shown button on a bank.
12. Bank carry: no console swap exists here. The rules are under "Fader banks on a console swap".
