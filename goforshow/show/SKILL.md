---
name: show-container
description: Check, pack, unpack and deterministically re-pack .show files, the proposed neutral interchange container for live-audio shows (input list with channel names, sources and instruments, patch, stage plot, outputs, processing intent). Validates the ZIP container, the SHA-256 integrity records and the show JSON against a JSON Schema, and refuses a bad file with one sentence. Trigger on ".show file", "show container", "interchange file", "neutral show file", "canonical show", "is this .show valid", "pack a show from JSON", or any request to move a show between desk tools through a middle file. NOT a console file format and NOT a desk conversion engine.
---

# .show container

A `.show` file carries the show, not any desk's encoding of it. Spec: `references/CONTAINER.md`. Fields: `references/schema/show.schema.json`.

## Safety rules (read first)

1. A `.show` is not a desk file. Never hand one to a console. A desk file written from a `.show` goes through that desk's own editor first.
2. Run `scripts/show_tool.py check <file>` before you read or write a `.show` from someone else. Do not use a file that is refused.
3. Write new files only. `pack`, `canon` and `unpack` never overwrite an input, and `unpack` refuses a target directory that is not empty.
4. Treat a `.show` as untrusted input. The tool reads entries into memory, refuses names with `..`, absolute paths or directories, and never runs anything from the archive.
5. Encrypted modules (`.enc`) are copied, never decrypted, and never logged. Do not ask the user for a passphrase to work on the `show` module, which is plain.
6. Keep desk-specific data out of the `show` module: no raw parameter words, no firmware limits, no desk file bytes. See "Where it stops" in the README.
7. No real client, artist or venue names in examples. Examples live under `examples/` only.

## Tools (all `python3 scripts/show_tool.py ...`; standard library only, Python 3.9+)

| Command | Does |
|---|---|
| `check file.show` | Validates the container, the hashes and `show/show.json`. Prints `ok` and `canonical: yes` or `no`. Refuses with one sentence and exit 1. |
| `pack dir out.show` | Builds a `.show` from `passport.gfs` plus one folder per module, in the deterministic profile. |
| `unpack file.show dir` | Writes every entry into a new or empty directory. |
| `canon in.show out.show` | Re-packs deterministically. Same show in, byte-identical file out. |

## Recipe: make a .show from an input list

1. Write `show/show.json` to the schema: `channels` (number, name, source, instrument, phantom, polarity_inverted, stereo_link), optional `patch`, `stage`, `outputs`, `processing`.
2. Write `passport.gfs` with `gfs_version` 3, `type` "passport", `created`, `event.name`, and `modules` with a `show` summary. Pick `created` once and keep it, or the file changes on every export.
3. `pack` the folder. `check` the result. `canon` it again and compare hashes.

## Gotchas

- Stereo links are mirrored: channel 8 names partner 9 on the left, channel 9 names partner 8 on the right. One-sided links are refused.
- Arrays in the `show` module are sorted by their key on write. Do not rely on the order you gave.
- A whole number is written without a decimal point (`6`, not `6.0`).
- A `.show` from the go·for·show library is expected to report `canonical: no`. Run `canon` to normalise it. See `references/CONTAINER.md` section 4.
- Not every `.show` in the wild is this container. Some go·for·show code paths write a plain JSON plot under the same extension. `check` says "not a ZIP archive" for those.
