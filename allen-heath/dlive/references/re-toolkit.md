# Extending the decode (how this was built)

## Method: Director as the oracle
1. Find the serializer in the Director binary (`<Class>::GetStatus` / `PackMessage` / `operator<<`) and read
   the field order. Class and method names are in the Mach-O symbol table.
2. Get a ground-truth pair: the same show saved by Director before and after one change. Diff it with the
   section walker. Implement the change, run it on "before", and diff against Director's "after".
3. Keep going until the only differences are explained (GUI edits made in between, format upgrades).
This is how the patch, mixer config, Mix Mixer, scene safes (port of FitFilterToMixerConfig) and SoftKeys
were validated.

## Tools
- The Director binary from the macOS app bundle (`dLive Director V2.12.app/Contents/MacOS/`). Demangle the
  Mach-O symbol table to find serializers; GNU objdump is enough to read one function at a time.
- Ghidra works but a full import of the 125 MB binary needs more than 6 GB of RAM.
- Never write to Director's live state folder (`~/Library/Application Support/AllenAndHeath/...`); it includes
  a binary SRAM image.

## Ground truth that ships with Director
Director installs the A&H factory shows (FoH, Monitors, LCR+, Surround, MultiSurface; 2.11 and 2.12 ship the
same files). They are clean, Director-written references for every section and for main modes other than LR.
Use them to check a writer, but do not redistribute them.

## Not decoded yet
SoftKey types 0x12, 0x1e and several older types; parameter-level meaning of PEQ/Comp/Gate payloads (they are
copied whole); surface strip types 0x0e/0x0f names; main modes other than LR; Version <14 shows.
