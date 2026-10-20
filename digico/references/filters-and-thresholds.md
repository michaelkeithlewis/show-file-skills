# Filter and threshold gotchas

A few conversions catch everyone who writes DiGiCo values by hand. They are in the code already. Read this before you write a filter or a threshold yourself.

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
- Code: `HPF_SHOWN_PER_STORED`, `LPF_SHOWN_PER_STORED`, `hpf_stored()` and `lpf_stored()` in `scripts/sesproc.py`.

If you skip the factor, every HPF lands 25 percent higher than you meant on the strip, and every LPF 20 percent lower.

## Thresholds

DiGiCo thresholds are dBFS and stop at 0. `sesproc.fs()` clamps every written threshold to -60..0 dBFS.

## Times

DiGiCo stores attack, hold and release in seconds. The strip and most plans use milliseconds. The tools convert; hand-written values
must too.
