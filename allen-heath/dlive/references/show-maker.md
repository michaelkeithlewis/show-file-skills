# Building a new dLive show from an input list (the Show Maker method)

This repo does not ship the Show Maker code. It was built inside a web app, it shares its request format and
channel model with the DiGiCo session maker's editor, and it starts from an A&H factory show that cannot be
redistributed. The method is below. Every step uses a script that is in `scripts/`, so you can repeat it by hand
or in your own wrapper.

## Start point

Use the A&H factory FoH show that installs with dLive Director 2.11 or 2.12 (`FoH.tar.gz`). It is a clean,
Director-written show: 8 mono and 8 stereo auxes, a full FX rack (Hall 480, EMT 250, Plate, Stereo Tap, BBD, ADT,
Gated, Chorus), every input at Director's defaults. Copy it, never edit it in place.

## Steps

1. **Mixer config.** Grow the auxes for the mixes you need (one stereo aux per IEM mix, one mono aux per wedge).
   Stay inside 64 buses: when the plan does not fit, take buses back from mono auxes, stereo matrices, mono
   matrices, stereo groups and mono groups, in that order. Tool: `dlive_mix.py reconfigure ... sAux=10 mAux=4`.
   `MixConfig.buses_used` counts the main and PAFL buses from MixConfig bytes 8 and 11.
2. **Input numbers.** Put the channels on inputs 1, 2, 3 ... in input-list order. A stereo channel takes an
   odd/even pair. When a stereo channel would start on an even input, leave that input as a spare. dLive has 128
   inputs.
3. **Stereo pairs.** Write `Show/InputConfig/InputConfig.dat` and the mono flag (byte 7 of each input channel
   section: 0 for both sides of a pair, 1 for mono) in every scene. For a newly linked pair, also write Director's
   stereo defaults for PEQ, Compressor, Gate, SCF Gate and LPF from `scripts/input_defaults.json` (`stereo`).
   `build_show.py` does the flag and InputConfig for a plan.
4. **Names and colours.** 8 characters. Colour by instrument group (drums red, bass yellow, guitars blue, keys
   magenta, vocals green, playback cyan, comms white). Unmute, leave faders down as the factory show does.
5. **Patch and preamps.** MixRack sockets in order from a first socket, both sides of a pair. Every pair starts on an odd socket: leave an even socket spare before a pair, and never split a pair over the last socket of the rack. Past the rack's
   socket count (or on a DM0) leave the rest unpatched and say so. Set a starting gain and 48V by mic type, and
   never 48V on a passive ribbon. Tools: `dlive_patch.py apply`, `dlive_preamps.py set`.
6. **Processing (optional).** Per-instrument starting points (HPF, LPF, PEQ, gate, compressor as Manual Peak).
   If your templates come from a dBFS console, add 18 dB to every threshold for dLive. Tool: write the sections
   with the layouts in `format-processing.md`, or copy from a show that already has them with
   `dlive_processing.py copy` and an instrument map.
7. **Mixes and FX.** Name each aux after its player. Send every channel pre-fader at a starting level, the
   player's own sources 6 dB up, masters at 0 dB. Pick the factory FX rack units by kind (hall, plate, room,
   delay, slap, chorus), name their FX sends and returns, and set channel sends to them. Tool: `dlive_mix.py apply`.
   The factory show keeps FX send masters 1-8 muted, so every FX unit you feed is silent until you unmute its master.
   Add each one to the plan: `"mixes": {"FX 2": {"mute": false, "fader": 0}}`. Also bring up the FX return. FX sends are
   numbered mono first, then stereo (`format-fx.md`). The factory DCAs also read muted: check them before a soundcheck
   (`format-processing-surface.md`).
8. **Stored scenes.** The factory show has none to inherit. If you start from your own template instead, drop its
   stored scenes: `dlive_scenes.py drop`.
9. **Check.** `dlive_lint.py`, then dump each section and compare it to the input list, then open the show in
   Director offline and save it from there.
