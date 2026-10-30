# Avantis console limits and safety

Read `allen-heath/dlive/references/console-safety.md` first. The same rules apply. This page adds what is specific to
Avantis.

## Console options decide the limits

| Firmware | dPack | Ultra FX card | Inputs | Buses (ways) | Ultra FX |
|---|---|---|---|---|---|
| 1.x | no | no | 64 | 42 (38) | 0 |
| 2.x | no | no | 64 | 42 (38) | 0 |
| 2.x | yes | no | 96 | 56 (52) | 0 |
| 2.x | yes | yes | 96 | 56 (52) | 8 |

- dPack needs FW 2.0. The RackUltra FX card needs dPack. CompStortion needs FW 2.0.
- Ask which firmware and options the console has before you build. A show for a dPack console does not fit
  a console without it.

## File names

- At most 14 characters before `.tar.gz`. Avantis Director does not open longer names.
- No underscores. Spaces are fine.
- Always end in `.tar.gz`.
- dLive Director, for comparison: at most 16 characters, longer names get cut and the show is not found.

## Things that broke Director or the console

- FollowPanSettings not matching the bus config: Avantis Director crashes on load (`mixer.md`).
- Odd mono bus counts: not allowed on Avantis either.
- Mixer section header config read as if it were MixConfig: rows misread, scenes dropped (a reader bug, not a
  console one, but it hides real data).

## Test workflow

1. Write a new file, never overwrite.
2. Open it in Avantis Director offline. Check names, bus config, patch, a few channels' processing.
3. Save it from Director and load only that save.
4. First load on the console from a USB stick at prep. If it fails, the console log says why; keep it.
5. Keep a known-good show on the stick.
