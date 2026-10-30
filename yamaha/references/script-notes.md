# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/yamaha_tool.py

- Generation 1: CL and QL (.CLF). Container facts: FORMAT.md section 2. Value facts: FORMAT.md section 3.
- (path, body offset, body size) of every data record scene id -> (body offset, [(tag, data offset, data size)])
- ---- CL/QL scene values (offsets from the start of a scene's MEMAPI data, big-endian). Test ids: FORMAT.md 1.2 ------ MEMAPI data size -> scene format (BB-RESAVE) u16 scene format (BB-RESAVE)
- BB-CSV-1: characters 1-4 of every slot, then 5-8 of every slot BB-CSV-1 BB-CSV-1 BB-CSV-1: ST L, ST R, MONO BB-CSV-1 BB-LOAD-G BB-CSV-1, BB-CSV-1, BB-CSV-2 (u8 per slot) BB-CSV-1 BB-CSV-1 BB-CSV-1 BB-LOAD-F: u8 index per slot BB-LOAD-F: 12-byte masks, slot n = bit (n-1)%8 of byte (n-1)//8, 1 = on BB-LOAD-G: DCA k mask at 10004 + 12(k-1) BB-SAVE-H: mute group k mask at 9908 + 12(k-1) (read only here)
- BB-LOAD-F: u16 per slot BB-LOAD-F, BB-QL: 4-byte mask and u8 per local port (dB = value - 6) BB-LOAD-F, BB-LOAD-R
- BB-LOAD-F: what the editor showed for each index
- BB-CSV-1: stored colour code -> (our key, label); the CSV word is the label's Yamaha CSV spelling
- BB-CSV-1: stored icon code -> Yamaha's CSV icon word (code 0 to 39)
- Which writes an editor test opened (FORMAT.md section 5). Keys: rename colour icon patch gain phantom hpf fader on dca name_bus, and 'scenes' for the stored scenes.
- BB-MODEL: a .CLF does not record the model. The editor's default comment ("CL [" / "QL [") or a patch to INPUT 9 to 32 (QL only, BB-CSV-2) is a hint, never proof.
- ---- gates ------------------------------------------------------------------------------------------------------
- ---- reading ----------------------------------------------------------------------------------------------------
- stored scene titles: formats 5 and 7 only
- ---- writing ----------------------------------------------------------------------------------------------------
- BB-LOAD-G: the editor's ON click changes L and R
- the patch as edited so far in this call
- Generation 2: the '#YAMAHA MBDF' container (DM7, DM5, DM3, TF, RIVAGE PM). FORMAT.md section 4.
- per schema every schema of a file, each use counted schemas parsed fresh (a repeat is reused)
- a body with no schema of its own (RIVAGE PM's compressed fields)
- ---- generation-2 values. Test ids: FORMAT.md 4.4 -------------------------------------------------------------------- The shape (type, sizes, most) every file read so far gives each parameter used here (BB-DM-SHAPE). Type 0 text, 1 signed, 2 unsigned; size 0 is one bit. Any other shape is refused as damaged, so nothing is read or written as the wrong kind of value.
- TF Editor and DM3 Editor files store channel on as one byte
- BB-DM-MODEL: the header model is DM7 for DM7, DM7 Compact, DM5 and DM5 Compact; ProjectInfo tells them apart. Only the ProductSubName values an editor-made file showed are here (BB-DM-MODEL, and the DM3 and TF5 sessions of BB-G2-WALK). Any other value falls back to the family name.
- BB-DM-LOAD: DM Editor's name field shows 8 characters BB-DM-SAVE: the words stored in Label.Color, in DM Editor's Channel List column order -> (our key, label)
- BB-DM-RANGE: Fader.Level 0.01 dB, -32768 = -inf BB-DM-LOAD: HeadAmp.Gain 0.01 dB, whole dB written BB-DM-RANGE: HPF.Frequency 0.1 Hz
- ---- gates ------------------------------------------------------------------------------------------------------
- ---- reading ----------------------------------------------------------------------------------------------------
- ---- writing ----------------------------------------------------------------------------------------------------
- BB-DM-ORDER: the port this channel is patched to now, as edited so far in this call
