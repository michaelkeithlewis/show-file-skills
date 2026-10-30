#!/usr/bin/env python3
"""sesproc.py - DiGiCo channel processing keys and writers, shared by the session maker.

Keys are (module, param, band) for ses.Session.set(). Writer wraps one channel. put_comp() writes the
SD compressor (Dyn1), put_mustard() the Quantum Mustard compressor. Thresholds are dBFS (DiGiCo
thresholds stop at 0). Filters: the strip shows the -3 dB cutoff, the file stores the design
frequency, so use hpf_stored()/lpf_stored() (references/filters-and-thresholds.md).
"""


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fs(db):
    """A threshold as stored dBFS, clamped to the DiGiCo range."""
    return clamp(db, -60.0, 0.0)


TRIM, POLARITY = (0x01, 0x01, 0), (0x01, 0x02, 0)
DELAY, DELAY_ON = (0x09, 0x08, 0), (0x09, 0x07, 0)
LPF_IN, LPF_F, HPF_IN, HPF_F = (0x07, 0x03, 0), (0x07, 0x05, 0), (0x07, 0x03, 1), (0x07, 0x05, 1)
EQ_IN = (0x04, 0x02, 0)
EQ_FREQ, EQ_Q, EQ_GAIN, EQ_SHAPE, EQ_ON = 0x05, 0x06, 0x07, 0x04, 0x03
SHAPE = {'bell': 1.0, 'lf_shelf': 3.0, 'hf_shelf': 4.0}
C_MODE, C_IN, C_THR, C_KNEE, C_ATK, C_REL, C_RATIO, C_MK, C_AUTO = (
    0x3a, 0x02, 0x0e, 0x0f, 0x11, 0x12, 0x10, 0x09, 0x3b)
G_MODE, G_IN, G_THR, G_ATK, G_REL, G_HOLD, G_RANGE = 0x0b, 0x02, 0x0e, 0x11, 0x12, 0x13, 0x0a
PAN = (0x0d, 0x23, 0)
KNEE = {'hard': 0.0, 'medium': 1.0, 'soft': 2.0}
HPF_SHOWN_PER_STORED, LPF_SHOWN_PER_STORED = 1.25, 0.8



class Writer:
    def __init__(self, ses, ch):
        self.s, self.ch, self.notes = ses, ch, []

    def put(self, key, value):
        self.s.set(self.ch, key[0], key[1], key[2], value)

    def note(self, msg):
        self.notes.append(msg)


def hpf_stored(hz):
    return clamp(hz, 20.0, 20000.0) / HPF_SHOWN_PER_STORED


def lpf_stored(hz):
    return clamp(hz, 20.0, 20000.0) / LPF_SHOWN_PER_STORED



def put_comp(w, thr, ratio, atk_ms, rel_ms, knee, makeup, to_fs=None):
    """SD compressor (Dyn1, single band). `thr` is dBFS; `to_fs` can map another scale to stored dBFS."""
    to_fs = to_fs or fs
    w.put((0x05, C_MODE, 0), 0.0)
    w.put((0x05, C_IN, 0), 1.0)
    for band in (0, 1, 2):
        w.put((0x05, C_THR, band), to_fs(thr))
    w.put((0x05, C_RATIO, 0), clamp(ratio, 1.0, 50.0))
    w.put((0x05, C_ATK, 0), clamp(atk_ms, 0.02, 100.0) / 1000.0)
    w.put((0x05, C_REL, 0), clamp(rel_ms, 1.0, 10000.0) / 1000.0)
    w.put((0x05, C_KNEE, 0), KNEE.get(knee, 0.0))
    w.put((0x05, C_MK, 0), clamp(makeup, 0.0, 40.0))


MC = 0x1d
MC_MODEL = {'classic': 0.0, 'vca': 3.0, 'fet': 4.0, 'optical': 5.0, 'levamp': 8.0}
MC_ON, MC_TYPE, MC_MIX, MC_THR, MC_KNEE, MC_ATK, MC_REL, MC_RATIO, MC_OUT = (
    0x02, 0x0b, 0x47, 0x0e, 0x0f, 0x11, 0x12, 0x10, 0x09)
MC_FET_IN, MC_FET_RATIO, MC_FET_OUT = 0x41, 0x4a, 0x4d
FET_IN_DEFAULT = -20.0


def put_mustard(w, model, thr=None, ratio=None, atk_ms=None, rel_ms=None, knee=None, out=None, mix=1.0, to_fs=None):
    """Mustard compressor (Quantum only). `thr` is dBFS; `to_fs` can map another scale to stored dBFS."""
    to_fs = to_fs or fs
    w.put((MC, MC_TYPE, 0), MC_MODEL[model])
    w.put((MC, MC_ON, 0), 1.0)
    w.put((MC, MC_MIX, 0), clamp(mix, 0.0, 1.0))
    if thr is not None:
        w.put((MC, MC_THR, 0), to_fs(thr))
    if ratio is not None:
        w.put((MC, MC_RATIO, 0), clamp(ratio, 1.0, 20.0))
    if atk_ms is not None:
        w.put((MC, MC_ATK, 0), clamp(atk_ms, 0.05, 100.0) / 1000.0)
    if rel_ms is not None:
        w.put((MC, MC_REL, 0), clamp(rel_ms, 5.0, 5000.0) / 1000.0)
    if knee is not None:
        w.put((MC, MC_KNEE, 0), 1.0 if knee == 'hard' else 0.0)
    if out is not None:
        w.put((MC, MC_OUT, 0), clamp(out, -24.0, 24.0))
