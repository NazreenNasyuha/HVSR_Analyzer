"""
sweep_smooth.py
===============
Cheap diagnostic: sweep a boxcar smoothing width over each window's raw
log-amplitude spectrum and measure the resulting per-window f0 scatter
(log-normal sigma).  Goal: find the width whose sigma matches Geopsy's
0.207 on the G4 station (tight window-f0 population).

Uses a sliding-sum boxcar (O(n) per channel) instead of Konno-Ohmachi so
the sweep is fast.  Only the *shape* of the smoothing matters here.
"""

import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from hvsr_io import auto_load
from hvsr_engine import (preprocess, _window_starts, _window_hv_curve,
                         log_frequencies)
from hvsr_dsp import fft, cosine_taper, detrend_linear, demean

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
WIN, FMIN, FMAX = 40.0, 0.5, 20.0
PICK_LO, PICK_HI = 0.5, 10.0


def raw_spectrum(chan, fs, w):
    seg = demean(detrend_linear(chan[:w]))
    win = cosine_taper(w, 0.05)
    seg = [seg[i] * win[i] for i in range(w)]
    spec = fft(seg)
    half = w // 2
    mag = []
    for k in range(half + 1):
        if k == 0:
            mag.append(abs(spec[0]))
        elif w % 2 == 0 and k == half:
            mag.append(abs(spec[half]))
        else:
            mag.append(2.0 * abs(spec[k]))
    return [math.log(max(v, 1e-300)) for v in mag]


def smooth_boxcar(vals, halfw):
    n = len(vals)
    out = [0.0] * n
    if halfw <= 0:
        return list(vals)
    for i in range(n):
        lo, hi = max(0, i - halfw), min(n, i + halfw + 1)
        out[i] = sum(vals[lo:hi]) / (hi - lo)
    return out


def f0_of(freqs, sm, curve):
    best, best_a = None, -1.0
    for k in range(1, len(curve) - 1):
        f = freqs[k]
        if PICK_LO <= f <= PICK_HI and curve[k] > curve[k - 1] and \
                curve[k] >= curve[k + 1] and curve[k] > best_a:
            best, best_a = k, curve[k]
    return freqs[best] if best is not None else None


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
    w = int(round(WIN * clean.fs))
    starts = _window_starts(clean.n_samples, WIN, clean.fs, 0.0)
    freqs = [k * (clean.fs / w) for k in range(w // 2 + 1)]

    # per-window log spectra (z only for speed -- f0 geometry is similar;
    # use geometric-mean H/V instead for realism)
    specs = {"z": [], "n": [], "e": []}
    for s in starts:
        for ch, arr in (("z", clean.z), ("n", clean.n), ("e", clean.e)):
            specs[ch].append(raw_spectrum(arr[s:s + w], clean.fs, w))
    nwin = len(specs["z"])
    print("G4 | windows=%d | Geopsy sigma=0.207\n" % nwin)
    print("%8s %8s %10s" % ("halfw", "sigma", "keep90%"))
    # halfw = half-width in FFT bins; fs=250, w=10000 -> df=0.025 Hz
    for halfw in (0, 2, 5, 10, 20, 40, 80, 160, 320, 640):
        f0s = []
        for i in range(nwin):
            lz = smooth_boxcar(specs["z"][i], halfw)
            ln = smooth_boxcar(specs["n"][i], halfw)
            le = smooth_boxcar(specs["e"][i], halfw)
            hz, hn, he = [math.exp(v) for v in lz], \
                         [math.exp(v) for v in ln], \
                         [math.exp(v) for v in le]
            curve = [math.sqrt((hn[k] / max(hz[k], 1e-300)) *
                               (he[k] / max(hz[k], 1e-300)))
                     for k in range(len(hz))]
            f = f0_of(freqs, None, curve)
            if f is not None:
                f0s.append(f)
        logs = [math.log(f) for f in f0s]
        m, s = statistics.fmean(logs), statistics.pstdev(logs)
        lo, hi = math.exp(m - 1.5 * s), math.exp(m + 1.5 * s)
        keep = sum(1 for f in f0s if lo < f < hi)
        print("%8d %8.3f %10d/%d" % (halfw, s, keep, len(f0s)))


if __name__ == "__main__":
    main()
