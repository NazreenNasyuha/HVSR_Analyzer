"""
investigate_rejection.py
========================
Diagnostic for the extreme window rejection seen on real stations
(e.g. G4: only 2 of 89 windows accepted).

For one mseed station it reports:
  1. data / decimation / STA-LTA mute statistics,
  2. an iteration-by-iteration trace of the built-in reject_windows,
  3. per-window deviation statistics (mean-normalised abs deviation,
     as a Geopsy-like average criterion, vs the built-in any-point rule),
  4. the per-window f0 spread,
  5. the fraction of zeroed (muted) samples inside every window,
  6. a reference geopsy-hv run with identical parameters (its stdout
     reports how many windows Geopsy itself keeps).
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
                         _window_hv_curve, _best_index)
from hvsr_geopsy import _write_param, _write_miniseed_signal

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
HERE = os.path.dirname(os.path.abspath(__file__))

WIN_LEN, REJ, FMIN, FMAX, NFREQ = 40.0, 1.5, 0.5, 20.0, 256
B_VALUE, TAPER, COMBO = 40.0, 0.05, "geometric"


def main():
    ms = sorted(glob.glob(os.path.join(BASE, "**", "*.mseed"), recursive=True))
    by = {}
    for p in ms:
        by.setdefault(os.path.dirname(p), []).append(p)
    trios = {os.path.basename(k): sorted(v) for k, v in by.items()
             if len(v) >= 3}
    g4 = [n for n in trios if "G4" in n.upper()]
    name = g4[0] if g4 else sorted(trios)[0]
    print("=" * 72)
    print("STATION:", name, " (%d other trios available)" % (len(trios) - 1))
    print("=" * 72)

    data = auto_load(trios[name])
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                             max_fs=250.0)
    print("raw    : fs=%.1f Hz, n=%d (%.1f min)"
          % (data.fs, data.n_samples, data.n_samples / data.fs / 60.0))
    print("clean  : fs=%.1f Hz, n=%d | decimation x%d"
          % (clean.fs, clean.n_samples, meta["dec_factor"]))
    print("STA/LTA: muted %d samples = %.1f%% of the trace"
          % (meta["muted"], 100.0 * meta["muted"] / data.n_samples))

    freqs = log_frequencies(FMIN, FMAX, NFREQ)
    starts = _window_starts(clean.n_samples, WIN_LEN, clean.fs, 0.0)
    curves = []
    for s in starts:
        c = _window_hv_curve(clean.z[s:], clean.n[s:], clean.e[s:],
                             clean.fs, WIN_LEN, TAPER, freqs, B_VALUE, COMBO)
        if c is not None:
            curves.append(c)
    nwin = len(curves)
    print("\n%d windows of %.0f s at fs=%.0f -> w=%d samples"
          % (nwin, WIN_LEN, clean.fs, int(round(WIN_LEN * clean.fs))))

    # ------------------------------------------------------- 1) iteration trace
    print("\n--- built-in reject_windows (any-point rule, n_sigma=%.1f) ---"
          % REJ)
    valid = [True] * nwin
    for it in range(12):
        idx = [i for i, v in enumerate(valid) if v]
        if len(idx) <= 1:
            break
        nf = len(curves[idx[0]])
        logc = [[math.log(max(c, 1e-300)) for c in curves[i]] for i in idx]
        mean = [statistics.fmean(col) for col in
                ([row[k] for row in logc] for k in range(nf))]
        std = [statistics.pstdev(col) for col in
               ([row[k] for row in logc] for k in range(nf))]
        changed = 0
        for pos, i in enumerate(idx):
            bad = any(
                std[k] > 1e-30 and not (mean[k] - REJ * std[k] <= logc[pos][k]
                                        <= mean[k] + REJ * std[k])
                for k in range(nf))
            if bad:
                valid[i] = False
                changed += 1
        print("  pass %d: %3d valid -> %3d rejected (remain %d)"
              % (it, len(idx), changed, sum(valid)))
        if not changed:
            break

    # ------------------------------------- 2) per-window deviation distribution
    print("\n--- per-window deviation (mean |log(HV)-log(mean)|/std, over freqs) ---")
    logc = [[math.log(max(c, 1e-300)) for c in w] for w in curves]
    nf = len(logc[0])
    mean = [statistics.fmean(col) for col in
            ([row[k] for row in logc] for k in range(nf))]
    std = [statistics.pstdev(col) for col in
           ([row[k] for row in logc] for k in range(nf))]
    devs = []
    for pos in range(nwin):
        terms = [abs(logc[pos][k] - mean[k]) / max(std[k], 1e-300)
                 for k in range(nf) if std[k] > 1e-30]
        devs.append((statistics.fmean(terms), pos))
    devs.sort(reverse=True)
    print("  window deviation: min=%.2f med=%.2f max=%.2f"
          % (devs[-1][0], statistics.median(d for d, _ in devs), devs[0][0]))
    print("  keep if avg-dev < 1.5 : %d / %d" %
          (sum(1 for d, _ in devs if d <= REJ), nwin))
    print("  keep if avg-dev < 1.0 : %d / %d" %
          (sum(1 for d, _ in devs if d <= 1.0), nwin))
    print("  worst windows: " + ", ".join("w%d=%.2f" % (p, d)
                                          for d, p in devs[:6]))

    # --------------------------------------------------- 3) per-window f0 spread
    w_f0s = [freqs[_best_index(freqs, c, 0.5, 10.0)] for c in curves]
    w_f0s.sort()
    lo, hi = w_f0s[len(w_f0s) // 10], w_f0s[min(nwin - 1, 9 * nwin // 10)]
    print("\nper-window f0: min=%.3f p10=%.3f med=%.3f p90=%.3f max=%.3f Hz"
          % (w_f0s[0], lo, w_f0s[nwin // 2], hi, w_f0s[-1]))

    # ---------------------------------------- 4) muted-zero fraction per window
    w = int(round(WIN_LEN * clean.fs))
    zeros = []
    for s in starts:
        seg = clean.z[s:s + w]
        if len(seg) >= w:
            zeros.append(sum(1 for v in seg if abs(v) < 1e-12) / w)
    if zeros:
        print("\nzeroed(muted) fraction inside windows: min=%.0f%% "
              "med=%.0f%% max=%.0f%%" %
              (100 * min(zeros), 100 * statistics.median(zeros),
               100 * max(zeros)))

    # ------------------------------------------------------ 5) Geopsy reference
    geo = hvsr_geopsy.find_geopsy()
    print("\nGeopsy reference run (same params, win=%.0fs rej=%.1f):"
          % (WIN_LEN, REJ))
    if not geo:
        print("  geopsy not found, skipping")
        return
    out = os.path.join(HERE, "..", "geo_dbg9")
    temp = os.path.join(out, "diag_" + name)
    os.makedirs(temp, exist_ok=True)
    _write_param(os.path.join(temp, "params.param"), WIN_LEN, REJ,
                 FMIN, FMAX, NFREQ)
    files = []
    for label, ch in (("EHZ", clean.z), ("EHN", clean.n), ("EHE", clean.e)):
        p = os.path.join(temp, "%s.mseed" % label)
        _write_miniseed_signal(p, ch, clean.fs, label, station=name)
        files.append(p)
    proc = subprocess.run(
        [geo, "-param", os.path.join(temp, "params.param"), "-o", temp] + files,
        capture_output=True, text=True, cwd=os.path.dirname(geo), timeout=600)
    print("  geopsy-hv return code: %d" % proc.returncode)
    for line in proc.stdout.splitlines():
        if any(k in line.lower() for k in ("window", "reject", "count",
                                           "selection", "curve")):
            print("  GEO: " + line.strip()[:170])
    for line in proc.stderr.splitlines()[:10]:
        print("  GEO-ERR: " + line.strip()[:170])
    print("  geopsy outputs: " + ", ".join(
        os.path.basename(p) for p in sorted(glob.glob(os.path.join(temp, "*")))))
    hv = sorted(glob.glob(os.path.join(temp, "*.hv")),
                key=os.path.getmtime)
    if hv:
        head = open(hv[0], encoding="utf-8", errors="replace").read()
        print("  --- first 25 lines of %s ---" % os.path.basename(hv[0]))
        print("\n".join(head.splitlines()[:25]))


if __name__ == "__main__":
    main()
