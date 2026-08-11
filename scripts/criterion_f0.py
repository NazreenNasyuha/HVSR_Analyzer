"""
criterion_f0.py
===============
Verify that the Geopsy / hvsrpy (Cox et al. 2020) window rejection --
based on per-window peak frequency f0 within n*sigma of the lognormal
window-f0 mean -- reproduces Geopsy's accepted-window count, while the
built-in any-point curve rule does not.

For each test station:
  * builds the per-window H/V curves exactly like hvsr_engine.analyze,
  * runs hvsrpy's real reject_windows(n) on those same curves,
  * runs a pure-stdlib port of the same algorithm,
  * runs geopsy-hv with identical parameters and reads "# Number of
    windows" from its .hv output,
  * reports all three counts side by side.
"""

import glob
import math
import os
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import hvsr_geopsy
from hvsr_io import auto_load
from hvsr_engine import (preprocess, log_frequencies, _window_starts,
                         _window_hv_curve, _best_index, pick_peak)
from hvsr_geopsy import _write_param, _write_miniseed_signal

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
HERE = os.path.dirname(os.path.abspath(__file__))
WIN, REJ, FMIN, FMAX, NFREQ = 40.0, 1.5, 0.5, 20.0, 256


def window_curves(clean):
    freqs = log_frequencies(FMIN, FMAX, NFREQ)
    curves = []
    for s in _window_starts(clean.n_samples, WIN, clean.fs, 0.0):
        c = _window_hv_curve(clean.z[s:], clean.n[s:], clean.e[s:], clean.fs,
                             WIN, 0.05, freqs, 40.0, "geometric")
        if c is not None:
            curves.append(c)
    return freqs, curves


def reject_f0_stdlib(f0s, n=REJ, max_iter=50):
    """Pure-stdlib port of the hvsrpy / Geopsy (Cox 2020) f0 rejection."""
    valid = [True] * len(f0s)
    for _ in range(1, max_iter + 1):
        idx = [i for i, v in enumerate(valid) if v]
        if len(idx) <= 1:
            break
        logs = [math.log(f0s[i]) for i in idx]
        m = statistics.fmean(logs)
        s = statistics.pstdev(logs)
        lo, hi = math.exp(m - n * s), math.exp(m + n * s)
        kept = 0
        for i in idx:
            valid[i] = (lo < f0s[i] < hi)
            kept += valid[i]
        if kept == 0:
            break
    return sum(valid)


def reject_f0_hvsrpy(freqs, curves):
    """Use the installed hvsrpy's real reject_windows on the same curves.
    Returns None if hvsrpy 1.0.0 chokes on the constructor."""
    try:
        import numpy as np
        from hvsrpy import Hvsr
        amp = np.array(curves)
        hv = Hvsr(amplitude=amp, frequency=np.array(freqs), find_peaks=True,
                  f_low=FMIN, f_high=10.0)
        hv.reject_windows(n=REJ, max_iterations=50)
        return int(hv.valid_window_indices.sum())
    except Exception as exc:
        print("  (hvsrpy skipped: %s)" % exc)
        return None


def geopsy_count(clean, name):
    """Run geopsy-hv with identical params; return (count, f0)."""
    geo = hvsr_geopsy.find_geopsy()
    if not geo:
        return None, None
    temp = os.path.join(HERE, "..", "geo_dbg9", "ref_" + name)
    os.makedirs(temp, exist_ok=True)
    _write_param(os.path.join(temp, "params.param"), WIN, REJ, FMIN, FMAX,
                 NFREQ)
    files = []
    for label, ch in (("EHZ", clean.z), ("EHN", clean.n), ("EHE", clean.e)):
        p = os.path.join(temp, "%s.mseed" % label)
        _write_miniseed_signal(p, ch, clean.fs, label, station=name)
        files.append(p)
    proc = subprocess.run(
        [geo, "-param", os.path.join(temp, "params.param"), "-o", temp] + files,
        capture_output=True, text=True, cwd=os.path.dirname(geo), timeout=600)
    if proc.returncode != 0:
        return None, None
    hv = sorted(glob.glob(os.path.join(temp, "*.hv")),
                key=os.path.getmtime)
    if not hv:
        return None, None
    head = open(hv[0], encoding="utf-8", errors="replace").read()
    count = f0 = None
    for line in head.splitlines():
        if line.startswith("# Number of windows ="):
            count = int(line.split("=")[1].strip())
        if line.startswith("# f0 from average"):
            f0 = float(line.split()[-1])
    return count, f0


def run_station(name, files):
    print("\n" + "=" * 70)
    print("STATION:", name)
    data = auto_load(files)
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                             max_fs=250.0)
    freqs, curves = window_curves(clean)
    f0s = [freqs[_best_index(freqs, c, FMIN, 10.0)] for c in curves]
    nwin = len(curves)
    # built-in rule, exactly as hvsr_engine.reject_windows (Cox f0-based)
    from hvsr_engine import reject_windows
    _, n_any = reject_windows(curves, freqs, REJ)
    n_f0 = reject_f0_stdlib(f0s)
    n_hv = reject_f0_hvsrpy(freqs, curves)
    gcount, gf0 = geopsy_count(clean, name)
    print("windows=%d | built-in any-point: %d | stdlib f0-based: %d | "
          "hvsrpy f0-based: %s | geopsy: %s"
          % (nwin, n_any, n_f0,
             str(n_hv) if n_hv is not None else "N/A",
             str(gcount) if gcount is not None else "N/A"))
    if gcount is not None:
        print("  match geopsy: stdlib %s, hvsrpy %s, built-in %s"
              % ("YES" if n_f0 == gcount else "no",
                 "YES" if n_hv is not None and n_hv == gcount else "no",
                 "YES" if n_any == gcount else "no"))
    return nwin, n_any, n_f0, n_hv, gcount


def main():
    ms = sorted(glob.glob(os.path.join(BASE, "**", "*.mseed"), recursive=True))
    by = {}
    for p in ms:
        by.setdefault(os.path.dirname(p), []).append(p)
    trios = {os.path.basename(k): sorted(v) for k, v in by.items()
             if len(v) >= 3}
    g4 = [n for n in trios if "G4" in n.upper()][0]
    run_station(g4, trios[g4])

    # one sg2 station for a second data point
    sg = sorted(glob.glob(os.path.join(BASE, "**", "*.sg2"), recursive=True))
    if sg:
        p = sg[0]
        name = os.path.splitext(os.path.basename(p))[0]
        run_station(name, [p])


if __name__ == "__main__":
    main()
