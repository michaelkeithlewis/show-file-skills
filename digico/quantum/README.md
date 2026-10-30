# DiGiCo Quantum

Covers Q112, Q225, Q225 Pulse, Q326/338, Q338 Pulse, Q5, Q7 and Q852. File extension: `.ses`.

## Tooling

- From `digico/scripts`, read with [`ses.py`](../scripts/ses.py), `sessionmaker.inspect` and `sessionmaker.validate`. Build with `sessionmaker.build`. Edit with `sessionmaker.edit` and `sessionmaker.commands`. List baselines with `sessionmaker.consoles`.
- Per-model table: [`consoles.py`](../scripts/sessionmaker/consoles.py). Docs: [`sessionmaker.md`](../references/sessionmaker.md), [`baselines.md`](../references/baselines.md) and [`FORMAT.md`](../references/FORMAT.md).
- Open every result in the offline editor for that console and build. Use **Files > Save As**. Load only that save on a console.

## What we know

| Key | Model | Family | Default inputs | Max inputs | Mustard cap | Spice Rack slots | Bus budget |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `q112` | Quantum 112 | Q1 | 48 | 80 | 20 | 6 | 26 |
| `q225` | Quantum 225 | Q2 | 48 | 72 | 24 | 6 | 38 |
| `q225p` | Quantum 225 Pulse | Q2 | 48 | 96 | 36 | 6 | not listed |
| `q338` | Quantum 326/338 | Q3 | 48 | 128 | 36 | 8 | 66 |
| `q338p` | Quantum 338 Pulse | Q3 | 48 | 156 | 48 | 8 | not listed |
| `q5` | Quantum 5 | Q5 | 108 | 124 | 24 | 12 | 130 |
| `q7` | Quantum 7 | SDQ | 72 | 253 | 24 | 16 | 130 |
| `q852` | Quantum 852 | Q8 | 72 | 253 | 24 | 32 | 194 |

- Verified: the Q225 Mustard cap of 24 and the Q225 V2242 build. On a Q225, a stereo channel uses 2 Mustard instances, and on load the editor turns off the excess in channel order.
- Quantum 112 inputs, proven on a real console (V2242): a session with 80 inputs, written by bytes, loaded. The same session with 82 inputs was refused on load with "console not supported".
- Default inputs are fallbacks. The newest baseline's own count wins. Bus budget is mono equivalents (FORMAT.md).
- Generated Q225 V2242 sessions loaded in the V2242 offline editor and re-saved unchanged. In-place patches (names, HPF, fader, mute) loaded on a real Quantum 2.
- Pulse models need the Pulse extension on the console, V1742 or newer. Q326 and Q338 share one key.
- TB In sits at 254 on Q2, Q3, Q5 and Q7, and at last input + 1 on Q1 and Q8.
- Snapshot scope, Global Scope, the channel safes and what a recall changes: [`scope-and-recall.md`](../references/scope-and-recall.md). Proven on a Quantum 112 at V2242 and V2242.4 with one-change saves and recalls saved on the console. Shows from the other Quantum models use the same flags.

### Session Structure limits (measured)

The table above shows what `consoles.py` allows today. This table shows what the console's Session Structure dialog allows, read in the real offline editors on 2026-10-24. The limits are the same at every build each editor exists for. A stereo input takes 2 paths, and an FX return counts as an input. See [`engine-findings.md`](../references/engine-findings.md).

| Key | Input paths | Bus slots | Rule | Builds read |
| --- | --- | --- | --- | --- |
| `q112` | 80 | 26 | fixed | V2126, V2232, V2242 |
| `q225` | 72 | 38 | fixed | V1455 to V2242 |
| `q225p` | 96 | 50 | fixed | V1742 to V2242 |
| `q338` | 128 | 66 | fixed | V1455 to V2242 |
| `q338p` | 156 | 74 | fixed | V1742 to V2242 |
| `q5` | 256 | 130 | pool | V1455 to V2242 |
| `q7` | 256 | 130 | fixed | V1455 to V2242 |
| `q852` | 384 | 194 | fixed | V1926 to V2242 |

- Quantum 5 pool: paths + bus slots must be 290 or fewer. Matrix outputs do not count. At the default 36 bus slots this gives 254 paths.
- The `consoles.py` caps for Q5 (124), Q7 (253) and Q852 (253) sit below these limits, and the Q112 cap (80) equals its limit. They count channels, so stereo inputs can still pass the path limit: 253 channels with 4 stereo is 257 paths on a Q7.
- The Quantum 5 load check allows 256 inputs and 134 bus paths and does not know the pool. A file can load and then lose inputs at the first Restructure.

### Other findings

- Snapshots: the pool, the snapshot record and its options, snapshot groups, setlists, and how to add, update and delete a snapshot by bytes: [`snapshots.md`](../references/snapshots.md). Proven on a Quantum 112 at V2242 with one-change saves and with files written by bytes that loaded. Shows from the Quantum 225, 326, 338 and 852 (V1742 to V2242) have the same layout.
- Pulse: header `0x25` bit `0x10` set means Pulse on a Q225 or Q338 file. Every Pulse default session has the bit set, and every plain default has it clear.
- Quantum 7 V2242: the editor clears 48V on load on the Local I/O Mic/Lin inputs (socket 0:Mic/Lin 1 and 3 proven), main and alt inputs. Gain stays. Switch 48V on at the console.
- MADI links: a device on a link past the console's links keeps its sockets, but the editor zeroes its device id, which means not connected. Quantum 225 keeps links 0 to 2 (link 4 was zeroed at V1619 and V2242). Quantum 338, 5, 7 and 852 kept links 0, 2 and 4.
- Spice Rack slots hold a Chilli 6 or a Naga 6. A stereo link of a Chilli 6 and a Naga 6 loads with the link dropped, proven on Q225. Two Chilli 6 slots link. A link of two Naga 6 slots is unverified. A mono channel can use a Naga 6 slot.
- A stereo channel takes the slot pair 1+2, 3+4 or 5+6. A pair written as 2+3 keeps the link, but the editor marks slot 4, not slot 3, so write the pair the editor would take.
- Insert points: inserts A and B and the Mustard strip each hold one of the five points, and they never share one. Slot `e1` of module 08: 0 post-fader, 2 pre-fader, 3 mid-EQ/dyn, 4 pre-EQ/dyn, 5 pre-processing. Defaults: A 4, B 2, Mustard 3. Proven on Q225 V2242.
- Names hold up to 31 characters ([`FORMAT.md`](../references/FORMAT.md), Names). Console-saved sessions from every Quantum model hold longer names, and names of 9 to 13 characters, written in place, loaded on a real Quantum 112 (V2242). The tools write 8 by choice.

### Mustard (contributed notes)

Keys are (module, param) in hex, as in [`FORMAT.md`](../references/FORMAT.md). The full Mustard key list is in [`CHANNEL_MODEL.md`](../references/CHANNEL_MODEL.md).

- Levelling Amp (comp model 8): (1d, 52) peak reduction and (1d, 51) gain, proven by one-change saves on a Quantum 112 at V2242.4. Its attack and release are fixed: no session read holds them.
- Gate (1e, 4c), the MSE release: 0 slow, 1 medium, 2 fast. Proven by one-change saves on a Quantum 5 at V2025.
- A comp or gate type change resets that module's controls to the type's defaults. Write the type first, then the controls. Proven by one-change saves; the editor does the same on load.
- The engine mode at header 0x87 offers 1 (48 kHz) and 4 (96 kHz) only on Quantum ([`session-structure.md`](../references/session-structure.md)).
- Nodal nodes, Spice Rack objects and the Quantum strip kinds: [`session-structure.md`](../references/session-structure.md).

## What we don't know

- Whether a real console processes input paths past the dialog limit: no console test has been run.
- Quantum 852 before V1926 and Quantum 112 before V2126: no editor exists. Pulse before V1742: the extension did not exist.
- The extension option on Q5, Q7, Q852 and Q112: the Enable Console Extensions panels were not opened.
- Mustard caps: Q225 Pulse, Q338 and Q338 Pulse come from DiGiCo's V1742 release notes, and the Q112's 20 from the V2242.4 release notes (no Q112 session numbers a Mustard channel above 19). The 24 on Q5, Q7 and Q852 is unverified.
- Every other model and build: same writers and `validate.py`, marked untested until someone loads one.
- `ses.py` parse floor: `digico/README.md` says V1455, FORMAT.md says V1619. Both list Q2, Q3, Q5, SD8, SD9 and SD12.
- Structural edits on a session with snapshots: refused.
- Mustard Optical attack and recovery, (1d, 48) and (1d, 49): a contributor reading says 0 slow, 1 medium, 2 fast. `CHANNEL_MODEL.md` says 0 fast, 1 medium, 2 slow. Needs a save that settles it: set one known option on the console and compare.
- FET ratio button (1d, 4a) value 0: a contributor reading of the screen order says it is ALL. Unconfirmed; no save holds it.
- Levelling Amp (1d, 50) as Limit or Compress: unconfirmed by a one-change save.
- DiGiCo's release notes say V1143 added Spice Rack, Mustard and nodal processing (Quantum 7), V20 the Mustard MSE, V22 the Levelling Amp and set lists, and V2242.4 lifts the Quantum 225 Pulse to 120 inputs. The dialog limit read here is 96 at V1742 to V2242. V2242.4 has not been read in the dialog.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

- 2026-10-30, Quantum 5 V2025 and Quantum 112 V2242.4, contributed one-change saves on Mustard (Levelling Amp, MSE release, type resets) and nodal nodes ported here and to `references/session-structure.md`.
