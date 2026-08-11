"""
verify_fix.py
=============
Validation for the two fixes:

1. hvsr_engine.reject_windows is now the Cox et al. (2020) f0-based
   rejection (Geopsy FREQUENCY_WINDOW_REJECTION_STDDEV_FACTOR).  Runs the
   full engine on two real stations and reports accepted-window counts
   (previously 1/90 and 1/43; Geopsy accepted 89/90 and 42/43).

2. hvsr_geopsy._write_param now writes engine-aligned settings
   (Konno-Ohmachi width 40, Tukey alpha 0.05, geometric H/V, ~256-point
   log step grid).  Re-runs geopsy-hv with the new param file on the
   same stations and reads its accepted-window count and f0.

Run:  python verify_fix.py
"""

import glob
import os
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import hvsr_geopsy
from hvsr_io import auto_load
from hvsr_engine import preprocess, analyze
from hvsr_geopsy import _write_param, _write_miniseed_signal

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
HERE = os.path.dirname(os.path.abspath(__file__))


def geopsy_hv(clean, name, win_len=40.0, rejection=1.5, fmin=0.5,
              fmax=20.0, nfreq=256, b_value=40.0, combo="geometric"):
    geo = hvsr_geopsy.find_geopsy()
    temp = os.path.join(HERE, "..", "geo_dbg9", "fix_" + name)
    os.makedirs(temp, exist_ok=True)
    _write_param(os.path.join(temp, "params.param"), win_len, rejection,
                 fmin, fmax, nfreq, b_value=b_value, combo=combo)
    files = []
    for label, ch in (("EHZ", clean.z), ("EHN", clean.n), ("EHE", clean.e)):
        p = os.path.join(temp, "%s.mseed" % label)
        _write_miniseed_signal(p, ch, clean.fs, label, station=name)
        files.append(p)
    proc = subprocess.run(
        [geo, "-param", os.path.join(temp, "params.param"), "-o", temp]
        + files, capture_output=True, text=True,
        cwd=os.path.dirname(geo), timeout=600)
    if proc.returncode != 0:
        return None, None, proc.stdout[:200] + proc.stderr[:200]
    hv = sorted(glob.glob(os.path.join(temp, "*.hv")),
                key=os.path.getmtime)
    if not hv:
        return None, None, "no .hv"
    head = open(hv[0], encoding="utf-8", errors="replace").read()
    count = f0 = None
    for line in head.splitlines():
        if line.startswith("# Number of windows ="):
            count = int(line.split("=")[1].strip())
        if line.startswith("# f0 from average"):
            f0 = float(line.split()[-1])
    # also check the echoed parameter grid
    log = os.path.join(temp, "XX_" + name.split()[0].replace("_", "") +
                       ".log")
    return count, f0, None


def run_station(name, files, label):
    print("\n" + "=" * 70)
    print("%s  STATION: %s" % (label, name))
    data = auto_load(files)
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                             max_fs=250.0)
    res = analyze(clean, w_len=40.0, overlap=0.0, rejection=1.5,
                  fmin=0.5, fmax=20.0, nfreq=256, b_value=40,
                  combo="geometric", station=name)
    print("engine : accepted %d/%d windows | f0=%.3f Hz A0=%.2f "
          "sigma_f=%.3f" % (res.n_windows_accepted, res.n_windows_total,
                            res.f0, res.a0, res.sigma_f))
    gcount, gf0, err = geopsy_hv(clean, name)
    if err:
        print("geopsy : FAILED - %s" % err[:160])
        return
    print("geopsy : accepted %d/%d windows | f0=%.3f Hz"
          % (gcount, res.n_windows_total, gf0 or -1))


def main():
    ms = sorted(glob.glob(os.path.join(BASE, "**", "*.mseed"), recursive=True))
    by = {}
    for p in ms:
        by.setdefault(os.path.dirname(p), []).append(p)
    trios = {os.path.basename(k): sorted(v) for k, v in by.items()
             if len(v) >= 3}
    g4 = [n for n in trios if "G4" in n.upper()][0]
    run_station(g4, trios[g4], "[mseed]")

    sg = sorted(glob.glob(os.path.join(BASE, "**", "*.sg2"), recursive=True))
    if sg:
        p = sg[0]
        name = os.path.splitext(os.path.basename(p))[0]
        run_station(name, [p], "[sg2  ]")


if __name__ == "__main__":
    main()
