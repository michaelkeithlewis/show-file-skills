# Converting between X32 / M32 and Yamaha DM7

What carries over, what changes, what gets lost. One direction has been loaded in an editor: an M32 scene
into DM7 Editor. The reverse direction (DM7 to X32) has not been loaded anywhere and is unconfirmed throughout.
Everything below says which of the two it rests on.

## Approach

Start from an empty DM7 show that DM7 Editor saved, then fill it from the scene. Never patch a scene into a DM7
show in place, and never rename or reorder a source scene's lines to look like the target.

- X32 or M32 to DM7: read the scene, build the DM7 show from the empty one, write only what the DM7 show can hold.
- DM7 to X32 or M32: start from an empty scene that X32-Edit saved, and match the firmware generation of the scene
  you want to load (see `FORMAT.md` for the section order). Unconfirmed.

DM7, DM7 Compact, DM5 and DM5 Compact share one file layout (`yamaha/references/dm7-fields.md`), so a note about
DM7 applies to the other three on format grounds. Only DM7 was loaded for this pair. The others are unconfirmed.

## What carries over

Proven by the load below (X32 or M32 scene to DM7, shown in DM7 Editor):

- Channel names, in channel order. All 13 named channels of the source scene appeared on the DM7 strips.
- Per channel on/off state of the high-pass filter, EQ, gate and compressor. Three channels with three different
  combinations showed three different states in the editor, and the indicator changed from one channel to the next
  as the written states changed, so it was not a default or a selection effect.

Expected to carry, but not proven for this pair (inferred from both formats; verify in the editor):

- Names as typed, up to the shorter limit of the two desks.
- High-pass corner frequency and slope, EQ band frequency, gain and Q, gate and compressor values, fader, pan and
  mute. The two formats have fields for each. No editor has shown a translated value of these.

## What changes

All of this is inferred from the two formats, not from a load.

- Names: an X32 name is at most twelve plain ASCII characters with no double quote. Going to DM7 nothing needs
  cutting. Going to X32, a longer DM7 name has to be shortened and any character outside plain ASCII replaced, and
  the engineer must be told which names changed.
- Colours: X32 has eight colours plus inverted forms. DM7 has its own palette. Map each source colour to the nearest
  hue the target has. Where the target palette lacks a hue, use the nearest and say so. A colour that has no match
  is left at the target's default, not invented.
- High-pass filter: the X32 low cut runs 20 to 400 Hz. DM7 runs 20 Hz to 2 kHz in slopes of 6, 12, 18 and 24 dB per
  octave. X32 to DM7 always fits. DM7 to X32 clamps any corner above 400 Hz to 400 Hz and fits the slope to what the
  X32 low cut offers. Both are losses to disclose.
- Low-pass filter: the X32 channel strip has no low-pass control. DM7 has one. DM7 to X32 drops it. Do not
  write a low pass onto an X32 channel.
- EQ band count: each X32 input channel has four bands, and each DM7 input has four, with a shelf switch on the
  first and last. So the counts match and bands map by position when types agree. An X32 band set to a type with no
  DM7 equivalent (the vintage bell whose width changes with gain, or a band used as a cut filter) has to be fitted to
  the nearest bell or moved to the DM7 filter, and disclosed.
- Q versus width: both desks store a true Q, so no conversion is needed for this pair. For a desk that stores
  width in octaves N, the conversion is Q = sqrt(2^N) / (2^N - 1), and the inverse is solved for N. Apply it only at
  the file edge of such a desk.
- Grid snapping: the target governs. X32 gain moves in quarter-dB steps within plus or minus 15 dB and its Q has a
  fixed list of 72 points between 0.3 and 10. A DM7 value finer than that snaps to the nearest X32 step. A value
  outside the target range is clamped to its end.
- Dynamics: ranges and curve shapes differ. Threshold, ratio, attack and release scale from the source range into the
  target range. Gate range and compressor makeup are clamped. A processor type with no counterpart (a ducker, or a
  compressor model the target lacks) carries its on/off state at most and is disclosed.
- Stereo: do not model a pair as one stereo channel. Keep two mono channels and a link between them. X32 pairs must
  sit on an odd and the next even channel. DM7 pairs may sit on any two channels. DM7 to X32 may need a pair moved,
  which the writer must not do silently; it should refuse or ask, and name the channels.
- Channel counts: the X32 has 32 input channels, DM7 has 120 inputs. DM7 to X32 needs the engineer to choose which
  32 to keep.

## What gets lost

The writer must say each of these to the engineer at export, with channel numbers, before the file is used.

Proven (the load above):

- The source scene's 48V states were deliberately not written to the DM7 show in that run, and the export said so.
  Whether a later writer carries 48V for this pair is unconfirmed here.
- Only on/off states were checked. Nothing here says a threshold, ratio or EQ gain arrived with the right value.

Inferred, not loaded:

- Anything the target has no control for: the X32 vintage bell, low-pass on X32, DM7 filter banks beyond the first.
- Names that had to be shortened or re-spelt, colours that were fitted, filter corners that were clamped.
- Effects racks, insert routing, scenes and snapshots, show-control data and surface layout. A translation covers the
  channel strip and its sends, not the rack.
- Console state such as the selected channel or the current bank. It is not show content and is never translated.

## Proof

- X32 or M32 to DM7. Source: a scene saved by an M32 desk, 13 named channels. The scene was read, a handful of
  channels were given distinct on/off settings for high-pass, EQ, gate and compressor in the source tool (the source had
  every one of them off), and a DM7 show was written. The file was loaded in Yamaha DM7 Editor (version recorded as
  1.7.5) on 2026-08-09. The editor showed the 12 visible strip names in order, with the 13th on the next strip page,
  and showed the written states channel by channel in its own selected-channel view. The read-back of the same file
  by our reader matched 22 of 22 checks, which is supporting evidence only. Scope is names plus on/off of those four
  blocks. Values, colours, 48V and stereo links were not checked in this run.
- DM7 to X32 or M32. Unconfirmed. No file written this way has been loaded in X32-Edit or on a desk.
- DM7, DM7 Compact, DM5, DM5 Compact as targets other than the one run above. Unconfirmed.
- Sibling Yamaha desks as targets (DM3, RIVAGE) and every other target in the repo. A translated show has not been
  loaded in their editors. Unconfirmed.

The translated file goes through DM7 Editor (or X32-Edit for the reverse) before it goes near a console, the same as
any written show.

## See also

- X32 format facts: `FORMAT.md` in this folder.
- DM7 format facts: `yamaha/references/dm7-fields.md`.
