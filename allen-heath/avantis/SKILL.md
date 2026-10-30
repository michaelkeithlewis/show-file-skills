---
name: avantis-showfile
description: Reference for Allen & Heath Avantis and Avantis Solo show files (.tar.gz, Bridge-4 for firmware 1.x, Bridge-5 for firmware 2.x) and for converting shows between Avantis and dLive - archive and scene layout, section names, mixer config and bus budget (with and without dPack), mixer sections and send rows, FollowPanSettings, Bridge-4 filter coefficients, compressor and GEQ byte maps, channel mapper, preamp sockets, strip types, FX type IDs, console limits and file name rules. Trigger on "Avantis", "Avantis Solo", "Avantis Director", "Bridge-4", "Bridge-5", "dPack", "Ultra FX", "convert my dLive show to Avantis", "Avantis show to dLive". Documentation only for now; for writing dLive shows use the dlive skill.
---

# Avantis show files

This skill is documentation. There are no Avantis scripts yet. Use it to answer questions about the format,
to plan a conversion, or to check a show by hand. For dLive work use `allen-heath/dlive/`.

## Read first

1. `README.md`: Avantis vs dLive in one table.
2. `references/console-safety.md`: limits by firmware, dPack and Ultra FX card, file names, what crashed.

## Then, by task

- Reading a show: `references/FORMAT.md`, then `references/mixer.md`.
- Processing values: `references/processing.md` (Bridge-4 needs coefficients, Bridge-5 does not).
- Patch, preamps, surface: `references/patch-and-io.md`.
- Talkback, PAFL, AMM, gangs, layers, soft keys: `references/settings-and-surface.md`.
- SQ and SQ+ (a different, folder-based format): `../sq/references/FORMAT.md`.
- dLive to Avantis or back: `references/translate-dlive.md`, plus the dLive docs it links.

## Rules

- Never write over a show. Every generated show goes through Avantis Director before a console.
- File names: 14 characters at most before `.tar.gz`, no underscores.
- Mono bus counts even, at most 16 buses per type, stay inside the budget (38 ways, 52 with dPack).
- MixConfig, the scene header copy, FollowPanSettings and the mixer section headers must agree.
- Mark anything you infer but did not see in a console save as unconfirmed.
