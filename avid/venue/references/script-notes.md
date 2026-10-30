# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/dshow_tool.py

- tail of a longer string, leave it alone

## scripts/s6l_tool.py

- ---- the container ---------------------------------------------------------------------------------------------------
- the largest show seen is 15 MB real shows nest 4 levels the largest show seen holds 10 823 values bytes in one key (48 at most seen)
- inflated bytes of one snapshot (1.46 MB at most seen) inflated bytes of every snapshot in a show (35.8 MB at most seen) strips in one strip array strips in every array together
- characters of any name read (cut before it is decoded)
- ---- strip records --------------------------------------------------------------------------------------------------- 0.1 dB units; -1440 is -inf +12.0 dB VENUE keeps 16 characters of a name the colour each number shows as on VENUE 8.2's Overview, measured from its screen
- where VENUE 8.2 Standalone's screen showed each number; anything else is the same palette by inference
- the seven output EQ bands in AudioMasterStrip
- ---- plug-ins --------------------------------------------------------------------------------------------------------
- chunk IDs seen in the AAX SDK default format
- the category bits seen in the survey shows (S6L-FORMAT.md 4.1); any other set bit prints as hex
- insert positions 1 to 5 are the ones VENUE wrote in real shows
- ---- snapshots and VENUE 8 Current State ----------------------------------------------------------------------------- a plug-in record: u32 slot (1-based), 4 bytes, 'L', u32 length, then chunks. The regex finds an 'L' with a slot number under 512 eight bytes before it and twelve printable type ID bytes where the first chunk's IDs sit.
- ---- the show --------------------------------------------------------------------------------------------------------
- Main Rack Type: 0, 2, 3 proven on Avid's own demo shows; 4, 5, 7 strong (input and matrix counts match the engine)
- how sure each read is: proven (a VENUE load or a public format source matched it), strong (the data fits, no controlled test), none (not read)
- ---- the read model --------------------------------------------------------------------------------------------------
- entries past the auxes belong to the groups; VENUE rewrites their level bytes on every save, so they are not read as send levels
- ---- checks ----------------------------------------------------------------------------------------------------------
- ---- the gate: what edit may change ----------------------------------------------------------------------------------
- E6L-192, the engine VENUE Standalone simulates
- ---- edit ------------------------------------------------------------------------------------------------------------
- ---- printing --------------------------------------------------------------------------------------------------------
