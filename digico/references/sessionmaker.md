# The session maker library

`scripts/sessionmaker/` builds a new DiGiCo session from an input list, and edits any existing session, by bytes.
It starts from an editor-saved default session (see `baselines.md`). Run every command from `digico/scripts`.
Python 3.9 or later, standard library only.

## What it does

| Module | Job |
|---|---|
| `consoles` | Console table (16 models, Quantum and SD). Finds the default sessions by file name. `python3 -m sessionmaker.consoles` lists them. |
| `listparse` | Reads an input list: CSV, TSV, XLSX, XLS, DOCX, PDF text, HTML or pasted text. L/R rows become one stereo channel, names are cut to 8 characters. No network. |
| `taxonomy` | 50 instrument categories and the rules that put a channel name in one. |
| `intake` | Input list and/or a plain description ("a five piece band with tracks and three IEM mixes") to a channel plan. |
| `build` | A request (console, build, channels, options) to a session file, a read-back, checks and a report. |
| `layout` | Input count, order and mono/stereo by bytes (the editor's Session Structure change). |
| `process` | Per-instrument starting processing from `data/templates.json`, and the read-back of what a channel holds. |
| `options` | The order and starting values for buses, FX, monitor mixes, sends, patch and preamps. |
| `buses`, `fx`, `sends`, `patch`, `busside` | The writers: bus layout, SD FX units and their feeds and returns, aux sends and group assigns, input patch and I/O devices, bus masters, matrix and control groups. |
| `validate` | Structural invariants every generated session must meet (section table, engine channels, banks). |
| `inspect` | Read-only checker: console, build, what it loads on, channels, patch, mixes, FX, problems. |
| `edit` | Open any session as a model and apply edit ops (set processing, rename, move, stereo, patch, sends, FX, buses). Every op is checked; an op that cannot be made is refused with a sentence. |
| `commands` | Plain-English edit commands ("hpf vox 120, gate the toms") to edit ops, by grammar rules. |

## Quick use

```
cd digico/scripts
python3 -m sessionmaker.consoles                                   # which defaults it found
python3 -m sessionmaker.listparse ../examples/input_list.csv --table
python3 -m sessionmaker.intake ../examples/input_list.csv           # channel plan with categories
python3 -m sessionmaker.build ../examples/build_request.json out.ses   # also writes out.md and out.json
python3 -m sessionmaker.inspect out.ses
python3 -m sessionmaker.commands out.ses "hpf vox 120, gate the toms"
python3 -m sessionmaker.edit out.ses '[{"op":"set","target":{"channels":[12]},"hpf":{"on":true,"freq":120}}]' out2.ses
python3 -m sessionmaker.validate out2.ses
```

The request format is in the `build.py` docstring. The op format is in the `edit.py` docstring.

## Starting processing (`data/templates.json`)

One template per instrument category: HPF, LPF, four EQ bands, gate, compressor and Mustard comp. The values are
show-weighted medians of real FOH and monitor sessions (aggregate numbers only). They are starting points for a
console and gain structure you have not heard yet, not a mix. Frequencies are as shown on the strip and thresholds
are dBFS; `process.py` applies the conversions in `filters-and-thresholds.md`.

## The optional classifier hook

The original tool sent channel names the rules were not sure of to an external closed-set classifier. That service
is not in this repo. Everything runs on the rules without it. To add your own, set `intake.CLASSIFIER` to a callable;
the contract is in the comment above it in `intake.py`. The names `jev_*` and `JEV_*` in the code refer to this hook.

## Proven vs not

- Output for the Quantum 225 at V2242 has been loaded in the real editor and re-saved. The other consoles and builds
  are built from their own editor defaults with the same writers and pass `validate.py`, but are marked untested in
  the console table until someone loads them.
- Long names (over 8 characters) are not written; names are cut to 8.
- Snapshots: a session with snapshots blocks structural edits (count, order, stereo), because the snapshot copies of
  the channel blocks are not rewritten.
