"""
validate_all_signals.py
=======================
Loads EVERY miniSEED, .eqd and .sg2 file found under the signal data folder
and runs the full HVSR pipeline on a sample of complete stations, proving
that every supported signal format can be processed end to end.

Run:  python validate_all_signals.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from hvsr_io import auto_load, DataError
from hvsr_engine import preprocess, analyze

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")

# ---------------------------------------------------------------- load check
ms = glob.glob(os.path.join(BASE, "**", "*.mseed"), recursive=True)
eqs = glob.glob(os.path.join(BASE, "**", "*.eqd"), recursive=True)
sg = glob.glob(os.path.join(BASE, "**", "*.sg2"), recursive=True)
print("Found %d .mseed, %d .eqd and %d .sg2 files" % (len(ms), len(eqs),
                                                      len(sg)))

load_fail = []
for p in sorted(ms):
    from mseed_io import read_mseed
    try:
        vals, fs, meta = read_mseed(p)
    except Exception as exc:
        load_fail.append((p, str(exc)))
for p in sorted(eqs):
    from eqd_io import read_eqd
    try:
        z, n, e, fs, meta = read_eqd(p)
    except Exception as exc:
        load_fail.append((p, str(exc)))
for p in sorted(sg):
    from sg2_io import read_sg2
    try:
        traces, meta = read_sg2(p)
        if len(traces) < 3:
            load_fail.append((p, "only %d traces" % len(traces)))
    except Exception as exc:
        load_fail.append((p, str(exc)))

print("Load failures: %d" % len(load_fail))
for p, err in load_fail[:10]:
    print("  [x]", os.path.basename(p), "->", err)

# ------------------------------------------- full pipeline on a station sample
print("\nFull-pipeline runs (one per station folder):")
# collect station folders that contain a complete mseed trio
stations = {}
for p in ms:
    folder = os.path.dirname(p)
    name = os.path.basename(folder)
    stations.setdefault(name, []).append(p)

ok = fail = 0
for name in sorted(stations)[:8]:
    files = sorted(stations[name])
    if len(files) < 3:
        continue
    try:
        data = auto_load(files)
        clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                                 max_fs=200.0)
        res = analyze(clean, w_len=40, overlap=0.0, rejection=1.5,
                      fmin=0.5, fmax=20.0, nfreq=256, b_value=40,
                      combo="geometric", station=name)
        ok += 1
        print("  [ok] %-32s fs=%.0f f0=%.3f Hz A0=%.2f Kg=%.2f (%d/%d windows)"
              % (name, data.fs, res.f0, res.a0, res.kg,
                 res.n_windows_accepted, res.n_windows_total))
    except Exception as exc:
        fail += 1
        print("  [!]  %-32s %s" % (name, exc))

# eqd sample
print()
for p in sorted(eqs)[:4]:
    try:
        data = auto_load([p])
        clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                                 max_fs=200.0)
        res = analyze(clean, w_len=40, overlap=0.0, rejection=1.5,
                      fmin=0.5, fmax=20.0, nfreq=256, b_value=40,
                      combo="geometric", station=os.path.basename(p))
        print("  [ok] %-32s fs=%.0f f0=%.3f Hz A0=%.2f Kg=%.2f (%d/%d windows)"
              % (os.path.basename(p), data.fs, res.f0, res.a0, res.kg,
                 res.n_windows_accepted, res.n_windows_total))
    except Exception as exc:
        print("  [!]  %-32s %s" % (os.path.basename(p), exc))

# sg2 samples
print()
for p in sorted(sg)[:4]:
    try:
        data = auto_load([p])
        clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                                 max_fs=200.0)
        res = analyze(clean, w_len=40, overlap=0.0, rejection=1.5,
                      fmin=0.5, fmax=20.0, nfreq=256, b_value=40,
                      combo="geometric", station=os.path.basename(p))
        print("  [ok] %-32s fs=%.0f f0=%.3f Hz A0=%.2f Kg=%.2f (%d/%d windows)"
              % (os.path.basename(p), data.fs, res.f0, res.a0, res.kg,
                 res.n_windows_accepted, res.n_windows_total))
    except Exception as exc:
        print("  [!]  %-32s %s" % (os.path.basename(p), exc))

print("\nStations analysed OK: %d, failed: %d" % (ok, fail))
