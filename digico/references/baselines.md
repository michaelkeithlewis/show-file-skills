# Making a baseline in the DiGiCo offline editor

Every tool here edits a session the DiGiCo offline editor saved. Nothing writes a session from nothing, because the
file also holds editor caches and heap data that only the editor can produce. The console rebuilds those caches on
load. So you start each job from a baseline: an editor-saved session for the console and software build you will
load it on.

There are two kinds of baseline.

## 1. Default sessions (for the session maker)

The session maker (`scripts/sessionmaker/`) builds a new session from the console's own default session and
changes its layout, buses, FX and patch by bytes.

1. Get the offline editor for the console family and software version you need from DiGiCo's website. The editors
   are Windows programs. Each console family has its own editor (Quantum 225, Quantum 338, SD12 and so on).
2. Open the editor. Start a new session (do not open a show file).
3. Do not change anything.
4. Save the session as `<key>_v<build>.ses` in `digico/scripts/baselines/`. Make the folder if it does not exist,
   or put the files in any folder and set the environment variable `SM_BASELINES` to it.
   - `<key>` is the console key: `q112`, `q225`, `q225p` (225 Pulse), `q338`, `q338p` (338 Pulse), `q5`, `q7`,
     `q852`, `sd5`, `sd5cs`, `sd7`, `sd8`, `sd9`, `sd10`, `sd11`, `sd12`.
   - `<build>` is the software build, the last number of the editor version (V2242 for editor 22.0.2242).
   - Example: `q225_v2242.ses`.
5. Check it: `python3 -m sessionmaker.consoles` (from `digico/scripts`) lists every console and build it found. A
   file the reader cannot map is left out of the list.

Notes:
- One default per console and build. Add more builds to support older consoles: a session saved by a newer build
  does not load on an older console.
- The FX choices in a build read their preset groups from a V2242 Quantum default (`q225_v2242.ses` first). Without
  one, the FX still build, but the preset group names are missing from the plan.
- New I/O devices in a patch borrow their records from a default that already declares that device. If no default
  has it, the patch op is refused with a plain sentence.
- Optional: `console_facts.json` in the same folder overrides the console table without code changes, for example
  `{"q112": {"max_inputs": 72, "max_inputs_verified": true}}`. The session maker also writes an
  `options_facts.json` cache there.

## Always

- Open every generated session in the same editor, check it, and **Files > Save As** a new file. Only the editor's
  save goes to a console.
- First load on a real console happens at prep or rehearsal, never at the show.
- Do not publish baselines or default sessions. They are DiGiCo editor output.
