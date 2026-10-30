---
name: liveprofessor-session
description: Read, dump and generate LiveProfessor 2 sessions (.rack2, a JUCE binary ValueTree) without opening LiveProfessor - audio device and channel labels, chains and their plugins, the hardware-in to chain to hardware-out routing - and build a pre-routed insert session (one chain per console channel over Dante or MADI) from a JSON channel list, copying plugin chains from an existing session. Trigger on "LiveProfessor", "LP session", ".rack2", "plugin host session", "build the LP inserts", "route Dante into LiveProfessor", or "what plugins are on this chain". NOT for Waves SuperRack, Gig Performer, or DAW sessions.
---

# LiveProfessor 2 sessions

A `.rack2` file is a JUCE binary ValueTree. `scripts/vt.py` reads and writes it byte for
byte. The other scripts sit on top of it. Format notes: `references/FORMAT.md`.
Requires Python 3.8 or later and nothing else.

## Safety rules

1. Write new files only. Never overwrite the base session.
2. The base must be a session that LiveProfessor saved, with one empty mono chain and one
   empty stereo chain to clone. Chains with plugins are copied from it by name.
3. Run `check_derive.py` on the base first. If it reports a mismatch, the generator's
   current-state rule may not hold for that LiveProfessor version. Stop and compare dumps.
4. Open the output from inside LiveProfessor (on macOS, `open -a` does not load it), check routing and plugins, pass audio,
   and save it from LiveProfessor before the show.

## Commands

```
python3 scripts/vt.py SESSION.rack2 > dump.txt            # full tree, after a round-trip check
python3 scripts/summary.py SESSION.rack2                  # device, chains, plugins, routing
python3 scripts/check_derive.py SESSION.rack2             # current-state rule holds?
python3 scripts/lp_generate.py BASE.rack2 channels.json OUT.rack2
```

`examples/channels.json` shows the channel list. Chain names in it (`BLANK MONO`,
`VOCAL CHAIN` ...) are placeholders. Replace them with chain names from your base (see
`summary.py`).

## New insert session (the recipe)

1. Run `summary.py` on the base. Note an empty mono chain, an empty stereo chain, and the
   chains whose plugins you want to reuse.
2. Write `channels.json` from the console input list: one chain per insert, `inputs` = the
   Dante or MADI channel the console sends, `outputs` = the channel it returns on
   (default: same). Stereo = two channels.
3. Run `check_derive.py` on the base, then `lp_generate.py`.
4. Run `summary.py` on the output and compare it to the input list.
5. Open it in LiveProfessor, check, save.

## Gotchas

- A template chain with plugins can be used once per run. A second use would duplicate
  plugin ids. Duplicate the chain in LiveProfessor first, save, and use the copy.
- The generator removes song snapshots, because each one stores its own routing. Make
  new snapshots in LiveProfessor after you check the file.
- Hardware labels default to the chain name without its channel-number prefix. Override
  them with `labels`.
- Keep each value's type (int vs int64) when you edit with `vt.py`.
