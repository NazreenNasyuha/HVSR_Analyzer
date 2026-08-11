"""
sweep_b.py
==========
Sweep the Konno-Ohmachi b-value and the H/V combination on the G4 station
to find the settings whose per-window f0 statistics match Geopsy's
(log-normal sigma ~0.207, 88-89 of 90 windows within the 1.5-sigma band).
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
WIN, FMIN, FMAX, NFREQ = 40.0, 0.5, 20.0, 256
PICK_LO, PICK_HI = 0.5, 10.0


def local_peaks(curve):
    return [k for k in range(1, len(curve) - 1)
            if curve[k] > curve[k - 1] and curve[k] >= curve[k + 1]]


def f0_peaks(freqs, curve):
    best, best_a = None, -1.0
    for k in local_peaks(curve):
        if PICK_LO <= freqs[k] <= PICK_HI and curve[k] > best_a:
            best, best_a = k, curve[k]
    return freqs[best] if best is not None else None


def cox_band_stats(f0s, n=1.5):
    f0s = [f for f in f0s if f is not None]
    logs = [math.log(f) for f in f0s]
    m, s = statistics.fmean(logs), statistics.pstdev(logs)
    lo, hi = math.exp(m - n * s), math.exp(m + n * s)
    return m, s, lo, hi, sum(1 for f in f0s if lo < f < hi), len(f0s)


def main():
    ms = sorted(glob.glob(os.path.join(BASE, "**", "*.mseed"), recursive=True))
    by = {}
    for p in ms:
        by.setdefault(os.path.dirname(p), []).append(p)
    trios = {os.path.basename(k): sorted(v) for k, v in by.items()
             if len(v) >= 3}
    g4 = [n for n in trios if "G4" in n.upper()][0]
    data = auto_load(trios[g4])
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                             max_fs=250.0)
    freqs = log_frequencies(FMIN, FMAX, NFREQ)
    starts = _window_starts(clean.n_samples, WIN, clean.fs, 0.0)

    print("G4 station | windows=%d | Geopsy: sigma=0.207, keep 89/90\n"
          % len(starts))
    print("%-6s %-10s %8s %8s %10s" % ("b", "combo", "sigma_log", "keep",
                                        "mean_f0"))
    for b in (5, 10, 20, 30, 40, 60, 100):
        for combo in ("geometric", "quadratic"):
            curves = []
            for s in starts:
                c = _window_hv_curve(clean.z[s:], clean.n[s:], clean.e[s:],
                                     clean.fs, WIN, 0.05, freqs, b, combo)
                if c is not None:
                    curves.append(c)
            f0s = [f0_peaks(freqs, c) for c in curves]
            m, s, lo, hi, keep, tot = cox_band_stats(f0s)
            print("%-6d %-10s %8.3f %8d %10.3f  (band [%.2f, %.2f])"
                  % (b, combo, s, keep, math.exp(m), lo, hi))


if __name__ == "__main__":
    main()
