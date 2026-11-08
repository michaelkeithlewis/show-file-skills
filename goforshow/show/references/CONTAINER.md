# The .show container

Spec for the container that `scripts/show_tool.py` reads and writes. Each statement carries a proof label:

- **read**: read from `show-container.js`, the JavaScript library that go·for·show uses to create and read these files. Not run for this document.
- **run**: executed with `scripts/show_tool.py` on Python 3.14.7 during this session.
- **inferred**: follows from read facts or from the documented default of a library, not run.
- **proposed**: a rule this proposal adds. The current library does not follow it.

## 1. Layout

A `.show` file is a ZIP archive (read). Entries, in the order the deterministic profile writes them:

| Entry | Content |
|---|---|
| `mimetype` | The text `application/vnd.gfs.show`, no newline, first entry, stored uncompressed (read) |
| `META-INF/access.json` | `{"version": 1, "modules": {"<module>": {"encrypted": false}}}`. For an encrypted module: `algorithm`, `kdf`, `salt` (base64), optional `key_hint` (read) |
| `META-INF/integrity.json` | `{"version": 1, "algorithm": "SHA-256", "files": {"<path>": "<hex sha256>"}}` (read) |
| `README.txt` | Fixed explanatory text. Not listed in `integrity.json` (read) |
| `passport.gfs` | The manifest, plain JSON, always readable (read) |
| `<module>/<file>` | One file per module folder (read) |

`passport.gfs` holds `gfs_version` (3), `type` ("passport"), `created`, `created_by`, `event` (`name`, `venue`, `city`, `dates`, `stages`), `scope`, `modules` (one summary per module: `version`, `count`, `encrypted`, optional `key_hint`) and `integrity` (read).

Module folder names the library accepts (read): `stageleft`, `settle`, `changeover`, `loadin`, `carnet`, `backline`, `greenroom`, `gainstage`. This proposal adds one: `show` (proposed). The file is `show/show.json` and it is never encrypted. Its fields are in `schema/show.schema.json`.

The library reads only the first file it finds in a module folder (read). The profile therefore allows exactly one file per module (proposed, run).

## 2. Integrity

- Each file in `integrity.json` is the SHA-256 of its stored bytes, in hex (read). For an encrypted module that is the hash of the ciphertext.
- `passport.gfs` is also listed in `integrity.json`, hashed after its `integrity` field is set (read).
- `passport.integrity` is `sha256:` plus the SHA-256 of the module-file hashes joined with no separator, ordered by path, passport excluded (read).
- The library's `verify` checks the hashes of the files `integrity.json` lists. It does not check the passport aggregate and does not notice a file that is in the ZIP but missing from `integrity.json` (read). `show_tool.py check` checks both (run, proposed).

## 3. Encryption

- `settle` and `backline` are always encrypted. Any other module can be (read). The `show` module is never encrypted (proposed).
- Scheme: AES-256-GCM. Key from PBKDF2 with SHA-256, 100,000 iterations, a random 16-byte salt kept in `access.json`. A random 12-byte IV is stored in front of the ciphertext. The file is named `<name>.enc` (read).
- The tool does not encrypt or decrypt. It copies an encrypted module byte for byte and keeps its `access.json` record (run).
- Encrypted output cannot be byte-identical between two exports, because salt and IV are random (inferred from the library calling `crypto.getRandomValues`). The determinism guarantee below covers plain modules only.

## 4. Where the current library is not deterministic

All read from `show-container.js`, except where marked.

| Source of variance | Current behaviour |
|---|---|
| `passport.created` | `new Date().toISOString()` at export time |
| Salt and IV | Random per export (encrypted modules only) |
| JSON key order | `JSON.stringify` keeps insertion order, so two producers can write the same show with different key order |
| JSON layout | Two-space indent, no trailing newline |
| Array order | Whatever the caller passed |
| ZIP entry order | Insertion order: `mimetype`, module files, `passport.gfs`, the `META-INF` files, `README.txt` (inferred: JSZip writes entries in insertion order) |
| ZIP timestamps | Not set by the library, so JSZip's default applies, the current time (inferred) |
| Compression | `mimetype` is stored. Others use JSZip's default, which is stored (inferred from the JSZip default) |
| Number text | JavaScript prints `1`, Python prints `1.0` for the same value |

## 5. Deterministic profile (proposed, run)

The same show in, byte-identical file out. `pack` and `canon` write this profile and `check` reports whether a file already matches it (`canonical: yes` or `no`).

1. **Entry order.** `mimetype` first, then every other entry sorted by path, byte order (run). Paths are ASCII `A-Z a-z 0-9 _ . -` with `/` between parts (run).
2. **Entry metadata.** Modification time 1980-01-01 00:00:00, compression method stored, creator system Unix, file mode 0644, no extra fields, no ZIP comment, no data descriptors (run: `unzip -Zv` shows stored, the 1980 date, Unix origin, no extra field, no comment and no data descriptor on all six entries of an example; the 0644 mode is set in the code and was not checked separately).
3. **JSON text.** UTF-8 with no byte order mark. Object keys sorted by Unicode code point. Two-space indent. Separators `,` and `: `. Non-ASCII characters written as themselves, not as `\u` escapes. LF line endings. One trailing LF (run).
4. **Numbers.** A number with no fractional part is written as an integer. Numbers that are not integers are written the way Python's `repr` writes them. Producers should keep three decimals or fewer. NaN, Infinity and duplicate keys are refused (run).
5. **Array order in the `show` module.** `channels` by `number`, `patch` by `channel`, `outputs` by `number`, `processing` by `channel`, `processing[].sends` by `output`, `stage.elements` by `id`, `stage.elements[].channels` ascending (run). No other array is reordered.
6. **Derived files.** `integrity.json`, `access.json`, the passport `integrity` field and `README.txt` are recomputed on every write. `README.txt` is a fixed text (run).
7. **`passport.created`.** The tool copies it and never reads the clock. A producer that wants identical files for an identical show must write the same `created`. Proposed for producers: use the time of the last edit to the show, not the time of export. This is an open question for the group.
8. **Strings.** Kept exactly as given. The tool does not normalise Unicode, trim whitespace or change case.

What this guarantees, and what it does not:

- Guaranteed (run): for one input file, `canon` run twice gives byte-identical output, and `canon` of its own output gives the same bytes again. `pack` of an unpacked file gives the original bytes. A show module whose arrays are shuffled and whose JSON is indented differently packs to the same bytes as the sorted one.
- Not guaranteed: two different producers get identical bytes unless both pass through this tool, or both follow rules 1 to 8. Encrypted modules are never byte-identical across exports. Output was compared on one Python version only (3.14.7); other versions are untested (guessed to match, because every field of each ZIP header is set explicitly).

## 6. Refusals

`check`, `pack`, `unpack` and `canon` refuse with one sentence, write nothing and exit 1 when any of these holds (run on the cases marked, otherwise read from the code):

- Not a ZIP archive (run). A damaged entry (run). A repeated, directory, absolute or `..` entry name.
- First entry is not `mimetype`, or its text differs.
- `passport.gfs`, `META-INF/access.json` or `META-INF/integrity.json` missing or not valid JSON.
- A file hash that does not match `integrity.json` (run), a ZIP file that `integrity.json` does not list, or a wrong passport aggregate.
- An unknown module folder, a module with more than one file, an access record that disagrees with the file name, a missing salt, `settle` or `backline` stored in plain, an encrypted `show`.
- A `show/show.json` that fails the schema (run), repeats a channel or output number (run), links stereo channels that do not point at each other on opposite sides (run), or refers to a channel or output that does not exist (run).

## 7. Where the container stops

The container carries a description of the show. It does not carry:

- any desk's file encoding, section order, record layout or byte values;
- raw parameter words, scaled integers or firmware-specific limits (name lengths, bus counts, character sets);
- anything a desk fixes by firmware version.

A writer that turns a `.show` into a desk file decides every such detail itself, builds from an empty show saved by that desk's own editor, and sends the result through that editor before it goes near a console. Field-level scope for the `show` module is in the README.
