"""
sweep_b2.py
===========
Efficient sweep: precompute the raw FFT magnitude spectra of every window
once, then for each Konno-Ohmachi b-value smooth only the 0.5-4 Hz band
(40 log-spaced target frequencies -- the peak lives there) and measure the
per-window f0 log-normal sigma on the G4 station.

Geopsy reference (same data, same windows): sigma_log = 0.207,
mean f0 = 1.65, 88-89 of 90 windows accepted.
"""

import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from hvsr_io import auto_load
from hvsr_engine import (preprocess, _window_starts, log_frequencies)
from hvsr_dsp import fft, cosine_taper, detrend_linear, demean, \
    konno_ohmachi_smooth

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
WIN, TAPER = 40.0, 0.05
PICK_LO, PICK_HI = 0.5, 10.0


def magnitude(seg):
    n = len(seg)
    spec = fft(seg)
    half = n // 2
    mag = []
    for k in range(half + 1):
        if k == 0:
            mag.append(abs(spec[0]))
        elif n % 2 == 0 and k == half:
            mag.append(abs(spec[half]))
        else:
            mag.append(2.0 * abs(spec[k]))
    return mag


def peaks_above(curve, freqs, lo, hi):
    best, best_a = None, -1.0
    for k in range(1, len(curve) - 1):
        if lo <= freqs[k] <= hi and curve[k] > curve[k - 1] and \
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
    fft_freqs = [k * (clean.fs / w) for k in range(w // 2 + 1)]

    # precompute per-window raw magnitude spectra
    raw = {"z": [], "n": [], "e": []}
    for s in starts:
        for ch, arr in (("z", clean.z), ("n", clean.n), ("e", clean.e)):
            seg = demean(detrend_linear(arr[s:s + w]))
            win = cosine_taper(w, TAPER)
            seg = [seg[i] * win[i] for i in range(w)]
            raw[ch].append(magnitude(seg))
    nwin = len(raw["z"])
    print("G4 | windows=%d | Geopsy: sigma_log=0.207 mean=1.65 keep 88-89\n"
          % nwin)

    # focused log grid 0.5-4 Hz (40 points) for cheap KO
    fg = log_frequencies(0.5, 4.0, 40)
    print("%-6s %-10s %8s %8s %8s" % ("b", "combo", "sigma", "keep1.5s",
                                       "mean_f0"))
    for b in (5, 10, 20, 40, 60, 100, 200):
        for combo in ("geometric", "quadratic"):
            f0s = []
            for i in range(nwin):
                sz = konno_ohmachi_smooth(raw["z"][i], fft_freqs, fg, b)
                sn = konno_ohmachi_smooth(raw["n"][i], fft_freqs, fg, b)
                se = konno_ohmachi_smooth(raw["e"][i], fft_freqs, fg, b)
                if combo == "geometric":
                    curve = [math.sqrt((sn[k] / max(sz[k], 1e-300)) *
                                       (se[k] / max(sz[k], 1e-300)))
                             for k in range(len(fg))]
                else:
                    curve = [math.sqrt((sn[k] ** 2 + se[k] ** 2) /
                                       (2.0 * max(sz[k], 1e-300) ** 2))
                             for k in range(len(fg))]
                f = peaks_above(curve, fg, PICK_LO, PICK_HI)
                if f is not None:
                    f0s.append(f)
            logs = [math.log(f) for f in f0s]
            m, s = statistics.fmean(logs), statistics.pstdev(logs)
            lo, hi = math.exp(m - 1.5 * s), math.exp(m + 1.5 * s)
            keep = sum(1 for f in f0s if lo < f < hi)
            print("%-6d %-10s %8.3f %8d %8.3f" % (b, combo, s, keep,
                                                  math.exp(m)))


if __name__ == "__main__":
    main()
