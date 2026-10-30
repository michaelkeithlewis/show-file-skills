# Agent guide

Read this before you change anything in this repo. `CLAUDE.md` points here.

## Layout

Every folder follows `manufacturer/product`. A skill folder holds the tooling, and a model folder holds what we learned about one model line.

```
<manufacturer>/                 yamaha/, digico/ (skill at this level)
<manufacturer>/<product>/       allen-heath/dlive/, avid/venue/, avid/protools/ (skill at this level)
  SKILL.md                      instructions the agent loads
  README.md                     for people: what it does, quick start, status
  scripts/                      Python that reads and writes the binary files
  references/                   format notes, one file per subject
  references/script-notes.md    facts that used to be code comments
  examples/                     synthetic inputs only
  <model>/README.md             what we know and do not know about that model line
```

One engine serves every model that shares a file format. Do not copy a script into a model folder. A model gets its own script only when its file format needs different code.

## Where a new fact goes

1. A fact about one model line goes in `<model>/README.md`. If the product has no model folders, it goes in the product `README.md`.
2. A fact about the file format goes in `references/` too.
3. A rule that stops a bad file goes in the tool as a refusal, and in the checker as an error. A note alone does not stop a bad file.

## Notes on every session

Keep notes while you work, not at the end. After each session on a real file, add one line to `## Session notes`:

`YYYY-MM-DD, firmware or software version, what you found.`

Move a line to `## What we know` when a test proves it. Add a line to `## What we don't know` when you find a gap. State how each fact was proven. Do not write a guess as a fact.

## Translation notes

A translation note says how a show moves from one console to another. It is research. It does not promise a tool.

1. Put the note in the source product's `references/` folder, named `translate-<target>.md`, for example `allen-heath/avantis/references/translate-dlive.md`. One file covers both directions. Link it from the SKILL.md of both products.
2. Build the target from an empty show that the target's own editor saved. Do not convert a source show in place.
3. Give each mapping its proof: the translated file loaded in the target editor, or on a console. Mark a mapping that is only read from the two formats as unconfirmed.
4. List what carries over, what changes, and what gets lost.
5. Link to the format facts in each product's `references/`. Do not copy them. A format fact that a translation finds goes in that product's `references/` too.
6. A translated file goes through the target editor before it goes near a console, the same as any written show.
7. A translation script goes in the target product's `scripts/`, and the target's checker must pass on its output.

## Python stays free of comments

Put no `#` comments in Python. The reason for the code goes in the README. A docstring holds usage only. `.github/strip-comments.py` removes comments and prints each one, so read that output and move any fact to the README. It refuses a change that alters the AST.

## Guards

A tool must refuse a file the console cannot use. Refuse with one sentence and write nothing. Add the same rule to the checker, because the checker also reads files that other tools made. Test a new checker rule on real editor-saved shows before it becomes an error. If a real show breaks the rule, make it a warning.

## Do not commit

No audio, vendor binaries, screenshots, client names, personal paths, addresses or keys. `.github/scrub-check.sh` runs on every pull request. No em-dashes in Markdown.

## Example show files

A contributor can add a show file or session as an example. This is the contributor's choice. Put it in an `examples/` folder, like `allen-heath/dlive/examples/` or `digico/examples/`. The check refuses a show file anywhere else. The check cannot read inside a show file, so the contributor must own the file and must have the right to share it. Do not add a show file on your own decision.

## Pull requests

Every format folder README ends with the "Built on tour" line. Keep it. Do not overwrite text that a merged pull request added.
