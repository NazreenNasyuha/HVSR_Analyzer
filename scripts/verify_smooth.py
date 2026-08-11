"""
verify_smooth.py
================
Quick characterisation of the residual f0 gap between the built-in engine
and Geopsy on the G4 reference station (Geopsy mean-curve f0 = 1.639 Hz,
89/90 windows accepted with its native width-0.2 Konno-Ohmachi):

runs the full engine at several Konno-Ohmachi b values and reports f0 /
A0 / accepted windows for each.  Geopsy reference: f0=1.639, A0~17.6,
89/90 windows.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from hvsr_io import auto_load
from hvsr_engine import preprocess, analyze

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")


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
    print("G4 | Geopsy reference: f0=1.639 Hz A0=17.6 windows 89/90\n")
    print("%-5s %8s %8s %8s %8s" % ("b", "f0", "A0", "accepted", "sigma_f"))
    for b in (5, 10, 20, 40, 60, 100):
        res = analyze(clean, w_len=40.0, rejection=1.5, fmin=0.5, fmax=20.0,
                      nfreq=256, b_value=b, combo="geometric",
                      station=g4)
        print("%-5d %8.3f %8.2f %7d/%-2d %8.3f"
              % (b, res.f0, res.a0, res.n_windows_accepted,
                 res.n_windows_total, res.sigma_f))


if __name__ == "__main__":
    main()
