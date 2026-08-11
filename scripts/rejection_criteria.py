"""
rejection_criteria.py
=====================
Test candidate window-rejection criteria on the G4 station to find which
one reproduces Geopsy's observed acceptance (89 of 90 windows) with the
same parameters (win=40 s, rejection=1.5, 0.5-20 Hz, 256 log freqs).
"""

import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from hvsr_io import auto_load
from hvsr_engine import preprocess, log_frequencies, _window_starts, \
    _window_hv_curve

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
NFREQ = 256
BAND_HI = 256  # index cutoff for a 0.5-10 Hz restricted band


def load_g4():
    ms = sorted(glob.glob(os.path.join(BASE, "**", "*.mseed"), recursive=True))
    by = {}
    for p in ms:
        by.setdefault(os.path.dirname(p), []).append(p)
    trios = {os.path.basename(k): sorted(v) for k, v in by.items()
             if len(v) >= 3}
    name = [n for n in trios if "G4" in n.upper()][0]
    data = auto_load(trios[name])
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                             max_fs=250.0)
    freqs = log_frequencies(0.5, 20.0, NFREQ)
    starts = _window_starts(clean.n_samples, 40.0, clean.fs, 0.0)
    curves = []
    for s in starts:
        c = _window_hv_curve(clean.z[s:], clean.n[s:], clean.e[s:],
                             clean.fs, 40.0, 0.05, freqs, 40.0, "geometric")
        if c is not None:
            curves.append(c)
    return name, freqs, curves


def report(label, keep, nwin, geopsy_kept=89):
    match = "MATCH" if keep == geopsy_kept else \
            ("close" if abs(keep - geopsy_kept) <= 2 else "far")
    print("  %-46s keep %3d/%-3d  (%s)" % (label, keep, nwin, match))


def main():
    name, freqs, curves = load_g4()
    nwin = len(curves)
    print("station:", name, "| windows:", nwin, "| Geopsy accepted: 89/90\n")

    logc = [[math.log(max(c, 1e-300)) for c in w] for w in curves]
    nf = len(logc[0])
    mean = [statistics.fmean(col) for col in
            ([row[k] for row in logc] for k in range(nf))]
    std = [statistics.pstdev(col) for col in
           ([row[k] for row in logc] for k in range(nf))]

    # A: built-in any-point iterative rule
    valid = [True] * nwin
    for _ in range(50):
        idx = [i for i, v in enumerate(valid) if v]
        if len(idx) <= 1:
            break
        m = [statistics.fmean(col) for col in
             ([logc[i][k] for i in idx] for k in range(nf))]
        s = [statistics.pstdev(col) for col in
             ([logc[i][k] for i in idx] for k in range(nf))]
        changed = False
        for pos, i in enumerate(idx):
            if any(s[k] > 1e-30 and not (m[k] - 1.5 * s[k] <= logc[i][k]
                                         <= m[k] + 1.5 * s[k])
                   for k in range(nf)):
                valid[i] = False
                changed = True
        if not changed:
            break
    report("A  any-point, iterative (built-in)", sum(valid), nwin)

    def _avg_dev(hi=nf, nsig=1.5):
        kept = 0
        for pos in range(nwin):
            terms = [abs(logc[pos][k] - mean[k]) / max(std[k], 1e-30)
                     for k in range(hi) if std[k] > 1e-30]
            if statistics.fmean(terms) <= nsig:
                kept += 1
        return kept

    def _dev_vals(hi=nf):
        vals = []
        for pos in range(nwin):
            terms = [abs(logc[pos][k] - mean[k]) / max(std[k], 1e-30)
                     for k in range(hi) if std[k] > 1e-30]
            vals.append(statistics.fmean(terms))
        return sorted(vals)

    report("B  mean |logdev|/std < 1.5 (full band)", _avg_dev(), nwin)
    report("B2 mean |logdev|/std < 1.5 (0.5-10 Hz)", _avg_dev(BAND_HI), nwin)
    report("B3 mean |logdev|/std < 2.0 (full band)", _avg_dev(nsig=2.0), nwin)

    def _rms(hi=nf, nsig=1.5):
        kept = 0
        for pos in range(nwin):
            terms = [(logc[pos][k] - mean[k]) / max(std[k], 1e-30)
                     for k in range(hi) if std[k] > 1e-30]
            rms = math.sqrt(sum(t * t for t in terms) / len(terms))
            if rms <= nsig:
                kept += 1
        return kept

    report("E  RMS dev < 1.5 (full band)", _rms(), nwin)
    report("E2 RMS dev < 1.5 (0.5-10 Hz)", _rms(BAND_HI), nwin)

    # C: per-window mean log-level vs population, |dev| < 1.5*std
    wm = [statistics.fmean(logc[i]) for i in range(nwin)]
    mm, ss = statistics.fmean(wm), statistics.pstdev(wm)
    report("C  window mean-log |dev| < 1.5*std",
           sum(1 for x in wm if abs(x - mm) <= 1.5 * ss), nwin)
    report("C2 window mean-log |dev| < 1.0*std",
           sum(1 for x in wm if abs(x - mm) <= 1.0 * ss), nwin)

    # F: linear-domain window mean level
    lin = [[max(c, 1e-300) for c in w] for w in curves]
    wl = [statistics.fmean(lin[i]) for i in range(nwin)]
    ml, sl = statistics.fmean(wl), statistics.pstdev(wl)
    report("F  window mean-HV |dev| < 1.5*std (linear)",
           sum(1 for x in wl if abs(x - ml) <= 1.5 * sl), nwin)

    # G: |dev| in log(mean ratio): per window mean of log(hv/mean_curve)
    dev_w = [abs(statistics.fmean(logc[i][k] - mean[k] for k in range(nf)))
             for i in range(nwin)]
    md, sd = statistics.fmean(dev_w), statistics.pstdev(dev_w)
    report("G  |mean log(hv/mean_curve)| < 1.5*std",
           sum(1 for x in dev_w if x <= 1.5 * sd), nwin)

    # H: what factor makes B match?  print the sorted deviations
    devs = _dev_vals()
    print("\n  B-deviation distribution: p10=%.2f p50=%.2f p90=%.2f max=%.2f"
          % (devs[len(devs) // 10], devs[len(devs) // 2],
             devs[9 * len(devs) // 10], devs[-1]))
    for th in (1.0, 1.5, 2.0, 2.5, 3.0):
        print("    B threshold %.1f -> keep %d" % (th, sum(1 for d in devs if d <= th)))


if __name__ == "__main__":
    main()
