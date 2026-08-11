"""
criterion_f0_peaks.py
=====================
Refined test of the Cox et al. (2020) / Geopsy FWA window rejection.

The previous attempt (criterion_f0.py) used the GLOBAL maximum of each
window's H/V curve as its f0, which scatters at the band edges.  Geopsy
(and hvsrpy/scipy) pick LOCAL maxima (real peaks).  This script compares
both pickers on the G4 and one sg2 station against Geopsy's accepted
window counts (89/90 and 42/43).
"""

import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from hvsr_io import auto_load
from hvsr_engine import (preprocess, log_frequencies, _window_starts,
                         _window_hv_curve)

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
WIN, REJ, FMIN, FMAX, NFREQ = 40.0, 1.5, 0.5, 20.0, 256
PICK_LO, PICK_HI = 0.5, 10.0


def local_peaks(curve):
    """Indices of local maxima (strictly higher than both neighbours)."""
    out = []
    for k in range(1, len(curve) - 1):
        if curve[k] > curve[k - 1] and curve[k] >= curve[k + 1]:
            out.append(k)
    return out


def f0_global(freqs, curve):
    best, best_a = 0, -1.0
    for k, f in enumerate(freqs):
        if PICK_LO <= f <= PICK_HI and curve[k] > best_a:
            best, best_a = k, curve[k]
    return freqs[best]


def f0_peaks(freqs, curve):
    """Highest local max within [PICK_LO, PICK_HI]; None if no peak."""
    best, best_a = None, -1.0
    for k in local_peaks(curve):
        if PICK_LO <= freqs[k] <= PICK_HI and curve[k] > best_a:
            best, best_a = k, curve[k]
    return freqs[best] if best is not None else None


def cox_reject(f0s, n=REJ, max_iter=50):
    """Iterative Cox lognormal f0 rejection over the provided f0 list."""
    f0s = [f for f in f0s if f is not None]
    if not f0s:
        return 0, len(f0s)
    valid = [True] * len(f0s)
    for _ in range(max_iter):
        idx = [i for i, v in enumerate(valid) if v]
        if len(idx) <= 1:
            break
        logs = [math.log(f0s[i]) for i in idx]
        m, s = statistics.fmean(logs), statistics.pstdev(logs)
        lo, hi = math.exp(m - n * s), math.exp(m + n * s)
        kept = 0
        for i in idx:
            valid[i] = lo < f0s[i] < hi
            kept += valid[i]
        if kept == 0:
            break
    return sum(valid), len(f0s)


def run_station(name, files, label):
    print("\n" + "=" * 70)
    print("%s  STATION: %s" % (label, name))
    data = auto_load(files)
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                             max_fs=250.0)
    freqs = log_frequencies(FMIN, FMAX, NFREQ)
    curves = []
    for s in _window_starts(clean.n_samples, WIN, clean.fs, 0.0):
        c = _window_hv_curve(clean.z[s:], clean.n[s:], clean.e[s:], clean.fs,
                             WIN, 0.05, freqs, 40.0, "geometric")
        if c is not None:
            curves.append(c)
    nwin = len(curves)

    g_f0 = [f0_global(freqs, c) for c in curves]
    p_f0 = [f0_peaks(freqs, c) for c in curves]
    n_peak_less = sum(1 for f in p_f0 if f is None)

    n_g, tot_g = cox_reject(g_f0)
    n_p, tot_p = cox_reject(p_f0)

    # with a proper peak, where do the picks land?
    pv = sorted(f for f in p_f0 if f is not None)
    print("  windows=%d (geopsy: %d accepted)" % (nwin, geopsy_ref[name]))
    print("  f0 GLOBAL-max picks : keep %d/%d" % (n_g, tot_g))
    print("  f0 LOCAL-max picks  : keep %d/%d (no-peak windows: %d)"
          % (n_p, tot_p, n_peak_less))
    if pv:
        print("  local-max f0: min=%.3f p10=%.3f med=%.3f p90=%.3f max=%.3f"
              % (pv[0], pv[len(pv) // 10], pv[len(pv) // 2],
                 pv[9 * len(pv) // 10], pv[-1]))
        logs = [math.log(f) for f in pv]
        print("  lognormal mean=%.3f sigma=%.3f -> 1.5-sigma band [%.2f, %.2f]"
              % (math.exp(statistics.fmean(logs)), statistics.pstdev(logs),
                 math.exp(statistics.fmean(logs) - 1.5 * statistics.pstdev(logs)),
                 math.exp(statistics.fmean(logs) + 1.5 * statistics.pstdev(logs))))


geopsy_ref = {}


def main():
    ms = sorted(glob.glob(os.path.join(BASE, "**", "*.mseed"), recursive=True))
    by = {}
    for p in ms:
        by.setdefault(os.path.dirname(p), []).append(p)
    trios = {os.path.basename(k): sorted(v) for k, v in by.items()
             if len(v) >= 3}
    g4 = [n for n in trios if "G4" in n.upper()][0]
    geopsy_ref[g4] = 89
    run_station(g4, trios[g4], "[mseed]")

    sg = sorted(glob.glob(os.path.join(BASE, "**", "*.sg2"), recursive=True))
    if sg:
        p = sg[0]
        name = os.path.splitext(os.path.basename(p))[0]
        geopsy_ref[name] = 42
        run_station(name, [p], "[sg2  ]")


if __name__ == "__main__":
    main()
