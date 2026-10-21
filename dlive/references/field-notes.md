# Field notes: how a working FOH engineer lays out a dLive show

These notes come from real shows, mixed on dLive CTi1500 and DM64 rigs on tour. Script-built shows get
opened, fixed and saved in Director by the engineer. Each rework teaches something, and this page records
it. When a script-built show and the engineer's own save disagree, the engineer's save wins.

Colours: 0 off, 1 red, 2 green, 3 yellow, 4 blue, 5 magenta, 6 cyan, 7 white.

## Mixer config

- Every mono count (mono groups, mono FX sends, mono auxes, mono matrices) must be even. dLive lays mono
  buses out in pairs. An odd count shifts every later stereo mix off its even bus. The console then logs
  "this fn requires the mix number to be even", and Sel on a stereo strip shows a different channel.
  If the show needs an odd number, round up. Leave the spare unused at -inf.
- Use all 64 buses. A typical FOH layout with ears mixed from FOH: 4 mono groups, 9 stereo groups,
  3 stereo FX, 8 mono auxes, 7 stereo auxes, 4 mono matrices, 3 stereo matrices.
- Keep only the stereo matrices that feed something real (PA tops, a socials feed, a dry socials feed).

## Channels and colours

- FOH input = MixRack socket. IEM copy = FOH input + 64. Leave holes. Never pack channels.
- Band inputs and backing vocals are yellow (3). The lead vocal channels are green (2).
- Talkbacks, click, audience mics and utility inputs are white (7).
- Plugin-host returns, FX returns and the FX return DCA are magenta (5).
- IEM copies and ear DCAs are green (2).
- On a linked stereo pair, set the colour on the odd channel. Director shows the pair with the odd channel.

## DCAs

- Layer A holds the FOH DCAs in playing order, one per player, then drums, vocals, options, FX returns and
  playback. Strip order is set in the surface layout, so DCA numbers can stay put.
- A vocal channel belongs to the vocal DCAs (lead, backing) only. Do not also put a vocal on the player's
  DCA.
- Drums split three ways: shells (kick, snares, toms, floor), pads, and everything else (OHs, room, hats).
- FX returns sit on an FX return DCA and are reached by spill. No fader layer carries FX return strips.
- Aux-fed plugin-host sends sit on their own DCA.

## Ears mixed from FOH

- One ear DCA per player, plus one for vocal FX. Each ear DCA holds that player's IEM channels plus the
  player's own vocal IEM channel.
- Ear DCAs are MCAs (Mix Control Association), set in `Show/MCASettings/MCASettings.dat`. When an IEM mix
  is selected, the ear DCA faders move their members' sends to that mix.
- One layer holds the ear DCAs on strips 1-6, in the same player order as layer A, and the IEM masters on
  strips 7-12.
- One Sel/Mix/PAFL combo SoftKey per IEM mix (SoftKey type 0x12).
- The tech IEM transmitter takes the dLive IEM output, which follows PAFL. A combo key therefore puts that
  mix in the engineer's ears.
- IEM copies get their own light processing, not the FOH chain. Miked sources get an HPF, and most get a
  compressor (snares, toms, OHs, hats, guitar amp mics, acoustic guitars, vocals). Line sources stay flat
  (keys, bass DI, pads, modeller, piano, steel, click). The kick IEM channels stay flat. No gates. Only
  the lead vocal IEM channels get PEQ.
- Talkbacks get no IEM copy. Their IEM slots (FOH + 64) stay empty.
- Library presets for the ears: unity-gain compressor starting points (a Distressor model and an opto),
  plus an ear reverb and an ear slap.

## Plugin host (LiveProfessor) and inserts

- Plugin-host inserts sit on the FOH inputs over a Dante card. Talkbacks get no insert.
- Two macro pairs:
  1. LP OFF / LP ON switch only the inserts that return from the Dante card: insert A where the plugin
     host sits on A, insert B where a Dyn8 or FX unit holds A, plus the Main insert. LP OFF is the
     emergency bypass if the plugin host goes down.
  2. INSERTS OFF / INSERTS ON switch every A and B insert on every input, Dyn8 and onboard FX included.
- The LP key lists OFF first (`mf:LP OFF/LP ON`).
- Bus FX run through the plugin host too: mono auxes go out the Dante card and come back on stereo return
  channels.

## Surface layout (CTi1500, left bank, 12 strips x 6 layers)

- A: FOH DCAs. B: groups. C: ear DCAs + IEM masters. D: talkbacks + matrices.
- E: utility DCAs, utility inputs, Main, mono auxes, a spare stereo aux.
- F: the FX send DCA and the FX return DCA. The rest of layer F stays empty.
- Inputs are reached by DCA spill, never by input layers.

## Show file hygiene

- Save in the Director version that matches the console. A Director that goes online with the console runs
  the same firmware. Its event log line `Application Started - V2.xx` names that firmware.
- Read Director's event log when a show misbehaves on the console:
  `~/Library/Application Support/AllenAndHeath/AllenHeath/TLDV2.xx/TLDPersistentData/Director/EventLogs/`.
  When Director is online, the log carries the console's own errors and every mixer config change.
- Name show files with letters, numbers, spaces, `-` and `_` only.
