# Can a script-edited show hurt a dLive console?

Short answer: the realistic failure is a show that will not load, or loads with some settings at default.
Bricking a console from a show file is very unlikely, and even then it is recoverable on site. The
Director round-trip below takes the remaining risk close to zero. Investigated 2026-10-11.

## Why the risk is low

1. **Director is the console's own code.** The Director V2.12 binary is built from the console source
   trees: `StageBox/Core` (the MixRack engine: cChannelMapper, cMixMixer, cMixer, cAnalogueInput ...),
   `Surface/Core` and `Surface/Core/ShowManagement` (the surface show loader). A show that loads in Director
   offline and plays back correctly has been through the same parsing code the console runs.
2. **The loader is defensive.** `cShowFileManager::IsValidShowVersion` checks `Version.dat` first; there is a
   "Corrupt show file" path for archives that do not unpack; each section's `SetStatus` checks its own
   version byte and skips the section on a mismatch (cChannelMapper::SetStatus: "Version number mismatch"),
   and per-element loops are bounded (128 inputs etc.). A bad section is ignored rather than trusted.
3. **The writers only produce shapes Director itself writes.** Every structure change (mixer config,
   per-mix sections, scene safes, patch, SoftKeys, layout) was checked byte-for-byte against Director's own
   output (a Director config change, Director-saved IEM sends, no-op round trips). Script-written
   shows have loaded in Director and been edited there.
4. **dlive_lint.py** checks framing, lengths (against every length seen in 9 Director-saved shows),
   cross-file consistency, enum ranges and value ranges. It passes all Director-saved shows with 0 errors
   and caught 18 of 18 deliberately corrupted files (stale chain length, truncation, wrong patch
   length/version, unknown source type, mixer tables disagreeing, fader above +10 dB, unterminated name,
   bad preamp flag, safes/config mismatch, >64 buses, FollowPan out of step, bad strip type, garbled macro,
   wrong PEQ length, unknown show version).
5. **The tools never touch** firmware, network/IP settings (MixrackStartup, IP controllers), clocking,
   user profiles/passwords, or Dante card settings (those live in the card, not the show).

## What can actually go wrong

| Risk | Likelihood | Effect | Guard |
|---|---|---|---|
| Console firmware older than the Director that saved the show | Most likely real problem | Show refuses to load, or newer-format sections load as defaults | Ask the rental shop for the firmware version; open and save in the matching Director (keep more than one Director version installed) |
| A writer bug producing a malformed section | Low (lint + byte checks) | Section skipped or show rejected | dlive_lint.py, then Director round-trip |
| A well-formed show with a config the console cannot lay out (odd mono bus count) | Happened once on a script-built show | Show loads, console logs "this fn requires the mix number to be even", Sel on a stereo strip shows another channel | dlive_lint.py ERROR; dlive_mix.py refuses odd mono counts; fix on the console with a mixer config change to an even count |
| Wrong but well-formed values (wrong patch, 48V on a ribbon) | Depends on the plan | Audio wrong, or a damaged ribbon mic | Plans come from the input list; ribbons are asserted 48V-off; check the I/O screen in Director |
| A loaded show crashes the console and the bad state persists across reboots | Very low, never observed | Console stuck until reset | Hard reset (below); keep a known-good show on USB |

## Workflow that removes the remaining risk

1. Edit with the scripts, then `dlive_lint.py <show>`. Do not continue on any ERROR.
2. Open the show in dLive Director **offline** (never connected to a live MixRack). Check the screens the
   edit touched (I/O patch, Mixer Config, a processing page, the SoftKeys).
3. Save from Director under a new name. The console only ever sees Director's serialization of the show,
   not ours. Director also upgrades older section formats on save.
4. Load that file on the console at prep or rehearsal, not first at the gig. Keep the previous show and the
   rental shop's default show on the same USB stick.

## If a console ever did get stuck

From Allen & Heath support (articles "dLive MixRack hard reset" and "dLive Surface Hard Reset"):

- **Surface:** switch the PSU off while the surface is running (skip the safe shutdown); on the next start a
  10-second window offers the advanced boot-loader menu with reset options.
- **MixRack:** newer DM racks have a recessed switch; hold it while powering on (15 s+) to reset network
  settings. Older racks have a 4-way DIP switch (inside the I/O port on C Class, inside Power 2 on S Class):
  Switch 1 ON, power on until READY, power off, Switch 1 back OFF for a full factory reset.
- Stored shows on USB are not affected; recall a known-good show afterwards.

Sources: support.allen-heath.com/hc/en-gb/articles/4402906507537 (MixRack hard reset),
support.allen-heath.com/hc/en-gb/articles/4402906647057 (Surface hard reset); forum + release notes:
"Shows stored on newer firmware will not load on systems running earlier versions; earlier shows load on
later firmware."
