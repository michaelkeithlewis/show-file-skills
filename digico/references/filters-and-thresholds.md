# Filter and threshold gotchas

Two conversions catch everyone who writes DiGiCo values by hand or moves a show from dLive. Both are in the code
already. Read this before you write a filter or a threshold yourself.

## HPF and LPF: the file does not store what the strip shows

The channel strip shows the -3 dB cutoff. The session file stores the filter's design frequency. The two differ by a
fixed factor, measured in the V2242 editor:

| Filter | Shown on the strip | Stored in the file |
|---|---|---|
| HPF | 100 Hz | 100 / 1.25 = 80 Hz |
| LPF | 10 kHz | 10000 / 0.8 = 12.5 kHz |

- To write: stored HPF = shown / 1.25. Stored LPF = shown / 0.8.
- To read: shown HPF = stored x 1.25. Shown LPF = stored x 0.8.
- EQ band frequency, gain and Q are stored as shown. Only the two filters need the factor.
- Keys: HPF frequency (07, 05, 1), LPF frequency (07, 05, 0) as (module, param, band).
- Code: `HPF_SHOWN_PER_STORED` and `LPF_SHOWN_PER_STORED` in `scripts/dlive2digico.py`. The session maker uses the
  same constants (`scripts/sessionmaker/process.py`).

If you skip the factor, every HPF lands 25 percent higher than you meant on the strip, and every LPF 20 percent lower.

## Thresholds: dLive is nominal 0, DiGiCo is dBFS

- dLive levels sit on a nominal 0 dB scale with full scale at +18 dB. That is why dLive thresholds go up to +18.
- DiGiCo thresholds are dBFS and stop at 0.
- To move a dLive threshold to DiGiCo, subtract 18 dB: a dLive comp at -10 becomes -28 dBFS on the DiGiCo. This
  applies to every compressor, gate, ducker, Dyn8 and dynamic EQ threshold.
- To go the other way (a dBFS template onto a dLive show), add 18 dB.
- Code: `DLIVE_TO_DBFS = -18.0` in `scripts/dlive2digico.py`. Results are clamped to -60..0 dBFS.

This assumes both consoles run the same nominal level at the preamp. If your gain structure on the DiGiCo puts
nominal somewhere else, move the thresholds by that difference too. The translator report says which offset it used.

## Times

DiGiCo stores attack, hold and release in seconds. The strip and most plans use milliseconds. dLive stores times in
its own encoding (see `../../dlive/references/format-processing.md`). The tools convert both; hand-written values
must too.
