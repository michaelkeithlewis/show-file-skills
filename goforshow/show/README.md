# .show: an open interchange container for live-audio tooling

A proposal. `.show` is a plain ZIP file that carries the show itself, meaning the input list, patch, stage plot, outputs and processing intent as an engineer states them, and not any desk's encoding of it. Writers and readers for different consoles meet in this file instead of translating desk to desk.

This folder holds the container spec, a JSON Schema for the show module, a validator and packer in plain Python, and two synthetic example files. It is a Claude Code skill (`SKILL.md`) and a set of scripts you can run yourself.

## The problem

Every console has its own file. Every tool that writes one starts from an input list, a patch and a plot the engineer already typed somewhere else. Moving a show between desks costs one translation per pair of desks, and each new format adds a pair. The desk files cannot be the common ground: none is neutral and none is documented by its maker. With a neutral file between them, each tool needs one reader and one writer for `.show` and no code for the other desks.

## What a .show is

- A ZIP archive. `mimetype` is the first entry, stored uncompressed.
- A plaintext manifest, `passport.gfs`: event name, which modules are inside, and an integrity value.
- One folder per module, one JSON file in each. The module this proposal adds is `show/show.json`; its fields are in `references/schema/show.schema.json`.
- `META-INF/access.json` says which modules are encrypted. `META-INF/integrity.json` holds a SHA-256 per file.
- Modules that hold money or personal data are encrypted with AES-256-GCM, key from PBKDF2-SHA256 at 100,000 iterations. The `show` module is plain JSON so any script can read it.

The full layout, the hash rules and the encryption scheme are in `references/CONTAINER.md`, each with how it was proven.

## What it is not

- Not a console format. A `.show` never replaces a desk file.
- Not a conversion engine. How a desk encodes a show stays in each project's own code.
- Not a shortcut past the vendor editor. A desk file written from a `.show` goes through that desk's own editor before it goes near a console, like any written file.
- Nobody has to change their tools. A thin import and export of `.show` is enough to join.
- Not the Midas HD96 show file, which also ends in `.show`. The two are told apart by their first bytes (question 4 below).

## Where it stops

In scope for the `show` module (an engineer would say these out loud):

- Input list: channel number, name, source kind and model, instrument, phantom power, polarity inversion, stereo link.
- Patch: which stage box or location and socket feeds each channel.
- Stage plot: stage size and positions of performers, instruments, monitors and boxes, with the channels each one feeds.
- Outputs: number, name, kind (main, group, aux, matrix, monitor, in-ear, FX send, direct), stereo or mono.
- Processing intent: high-pass frequency, gate on or off, a compressor level (off, light, medium, heavy), EQ notes as text, send levels in dB.

Out of scope, on purpose:

- Any desk's file encoding, section order or record layout.
- Raw parameter words, scaled integers, bus or channel counts a firmware imposes, name-length and character limits.
- Firmware and software versions, scene and snapshot structure, console-specific routing (layers, banks, DCA and mute-group assignment, user keys).
- Plugin and effect-rack internals.

Each writer applies its desk's limits itself (truncating a name, refusing a stereo link that starts on an even channel) and says so. The `show` file keeps what the engineer meant.

## Determinism

The same show in must give a byte-identical file out. The tool guarantees this for the deterministic profile (`references/CONTAINER.md` section 5):

- Entry order: `mimetype`, then every other entry sorted by path.
- JSON: keys sorted, two-space indent, UTF-8 without a byte order mark, LF line endings, one trailing LF.
- Arrays in the `show` module sorted by their key (channels by number, and so on).
- ZIP: every entry dated 1980-01-01 00:00:00, stored (no compression), mode 0644, no extra fields, no comment.
- Derived files (`integrity.json`, `access.json`, the passport hash) recomputed on every write.

What it does not guarantee: encrypted modules (salt and IV are random, so two exports differ), two producers that skip this tool and break one of the rules above, and Python versions other than the one tested. `passport.created` is copied, never read from the clock, so identical bytes also need an identical `created` from the producer.

The library go·for·show uses today does not meet this profile: it writes the current time into `created`, keeps JSON keys in insertion order, and leaves ZIP dates to its ZIP library. `references/CONTAINER.md` section 4 lists each difference.

### Determinism check

Run on Python 3.14.7. `canon` was run twice on each example, then once more on its own output; `pack` was run on the unpacked folder. SHA-256 of all four outputs:

```
examples/festival-24.show  canon run 1   b1f041bd6c181db1efce70c6e70691b3c04ddacd65a328df141ec7741bba05eb
examples/festival-24.show  canon run 2   b1f041bd6c181db1efce70c6e70691b3c04ddacd65a328df141ec7741bba05eb
examples/four-piece.show   canon run 1   11142b63dfe9c0254e32ac5035529d61e6aacb591f0eebbdfcdd20b2dee7f9d9
examples/four-piece.show   canon run 2   11142b63dfe9c0254e32ac5035529d61e6aacb591f0eebbdfcdd20b2dee7f9d9
```

Both pairs are equal, and both equal the hash of the committed example. Feeding the festival show to `pack` with every array reversed and the JSON indented four spaces gave the same hash as well.

## Quick start

```
cd goforshow/show/scripts
python3 show_tool.py check ../examples/festival-24.show
python3 show_tool.py unpack ../examples/festival-24.show /tmp/festival
python3 show_tool.py pack /tmp/festival /tmp/festival-again.show
python3 show_tool.py canon some-export.show some-export-canonical.show
```

`check` prints `ok` and `canonical: yes` or `canonical: no`. Any problem prints one sentence beginning `Refused:` and exits 1. `pack` and `canon` write nothing when they refuse.

Requires Python 3.9 or later, standard library only. The examples in `examples/` are synthetic: made-up acts, no real people, venues or artists. Each `.show` has its unpacked folder beside it for reading.

## Layout

- `scripts/show_tool.py`: check, pack, unpack, canon.
- `references/CONTAINER.md`: the container spec and the determinism profile.
- `references/schema/show.schema.json`: JSON Schema (draft 2020-12) for `show/show.json`.
- `examples/`: two synthetic shows (4 channels, 24 channels).

## Status

Proposal. Not a standard and not affiliated with any console maker.

Proven (run, Python 3.14.7):
- `check` passes both examples and refuses a non-ZIP file, a damaged entry, a hash mismatch, a repeated channel number, a wrong field type and a stereo link that does not point back.
- `canon` is repeatable and `pack` of `unpack` returns the same bytes (hashes above).

Proven by reading the JavaScript source only (not run): the container layout, hash rules and encryption scheme in `references/CONTAINER.md`.

Not covered:
- No file produced by the go·for·show library has been run through `check` for this proposal. Real exports are expected to report `canonical: no` and may be refused where the library is looser (an unlisted file, a passport aggregate that does not match).
- No desk writer reads the `show` module yet. No translation note is written against it.
- The JSON Schema is checked by `show_tool.py`'s own small validator, which implements only the keywords the schema uses. It has not been run through an independent draft 2020-12 validator.
- Encrypted modules are passed through, never decrypted, so their contents are untested here.
- The module name `show`, the file names `passport.gfs` and `mimetype` text `application/vnd.gfs.show` are the current library's names for everything except `show`. A neutral renaming is an open question.

## Questions for the group

1. Does a neutral show file solve a problem you have, or do you work desk to desk and never want a middle file?
2. Which fields would you need on day one for your formats? Which of the ones above do you consider desk-specific and out of scope?
3. Should the manifest and mimetype be renamed to something vendor-neutral before anyone depends on them?
4. The Midas HD96 Edit show file also uses the `.show` extension (it is gzip-compressed XML, first bytes `1f 8b`; this container is a ZIP, first bytes `PK`). A tool can always tell them apart by content, never by name. Should the interchange take a different extension so an HD96 user never hands one tool the other file?
5. Should `passport.created` be the time of the last edit, so an unchanged show always exports to the same bytes?
6. Which extension mechanism, if any: a free-form `extensions` object per channel, or none and a new schema version for each addition?
7. Would you co-author the schema, so it is the group's file and not one company's?

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, tool version, what you found.`*

2026-11-07, Python 3.14.7, first draft: examples packed and re-packed to identical hashes (see Determinism check).

## Credits

Proposed by go·for·show, tools for live-sound engineers, built by a touring front-of-house and monitor engineer. Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).
