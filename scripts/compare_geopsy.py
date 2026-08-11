"""
compare_geopsy.py
=================
Three-way batch comparison of the built-in HVSR engine, hvsrpy and the
external Geopsy program (geopsy-hv.exe), across every .sg2 and .mseed
station in the signal data folder.

For every station it:
  1. loads the signal (single .sg2, or a .mseed Z/N/E trio),
  2. pre-processes identically for all engines,
  3. runs the built-in engine, hvsrpy and geopsy-hv on the same data,
  4. picks f0 / A0 from every curve and computes the agreement,
  5. appends one row to Geopsy_Comparison.csv,
  6. prints a summary at the end.

Stations whose H/V curve has no genuine resonance (peak_quality =
FLAT/UNCLEAR) are flagged; their f0 picks are not meaningful and are
reported separately so they do not pollute the agreement statistics.

Run:  python compare_geopsy.py            (all stations)
      python compare_geopsy.py --limit 20 (first 20 stations, for a quick run)
      python compare_geopsy.py --sg2      (only .sg2 files)
      python compare_geopsy.py --mseed    (only .mseed trios)
      python compare_geopsy.py --no-hvsrpy (skip the hvsrpy engine)
"""

import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import hvsr_geopsy
from hvsr_io import auto_load, DataError
from hvsr_engine import preprocess, analyze, pick_peak, peak_quality

# --- Signal data folder for this dev tool ---
# Override with the SIGNAL_DATA_DIR environment variable, e.g.
#     set SIGNAL_DATA_DIR=C:\path	o\your\signal\data
BASE = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "HVSR_Results")
CSV_PATH = os.path.join(OUT_DIR, "ThreeWay_Comparison.csv")

DECIMATE_TO = 250.0   # prime-factor friendly for Geopsy (10000 = 2^4 * 5^4 @ 40 s)


def collect_stations(include_sg2=True, include_mseed=True):
    """Return a list of (station_name, [files], kind)."""
    stations = []
    if include_sg2:
        for p in sorted(glob.glob(os.path.join(BASE, "**", "*.sg2"),
                                  recursive=True)):
            stations.append((os.path.splitext(os.path.basename(p))[0],
                             [p], "sg2"))
    if include_mseed:
        by_folder = {}
        for p in glob.glob(os.path.join(BASE, "**", "*.mseed"),
                           recursive=True):
            folder = os.path.dirname(p)
            by_folder.setdefault(folder, []).append(p)
        for folder, files in sorted(by_folder.items()):
            if len(files) >= 3:
                name = os.path.basename(folder)
                stations.append((name, sorted(files), "mseed"))
    return stations


_HAS_PATCHED_HVSRPY = False


def _patch_hvsrpy():
    """Work around a bug in hvsrpy 1.0.0's Hvsr.update_peaks.

    In hvsrpy 1.0.0 the peak index returned by np.where() is only
    converted to a scalar when there is MORE than one match; a single
    match stays a 1-element array, so assigning self.amp[c_window,
    c_index] into a float slot raises 'setting an array element with a
    sequence' on essentially every window.  The patched version always
    scalarises the index.
    """
    global _HAS_PATCHED_HVSRPY
    if _HAS_PATCHED_HVSRPY:
        return True
    try:
        import hvsrpy.hvsr as _H
        import numpy as _np

        def _update_peaks(self, **kwargs):
            if not self._initialized_peaks:
                self._initialized_peaks = True
            peak_indices, _ = self.find_peaks(
                self.amp[self.valid_window_indices, self.i_low:self.i_high],
                starting_index=self.i_low, **kwargs)
            valid_indices = _np.zeros(self.nseries, dtype=bool)
            valid_count = 0
            for c_window, valid in enumerate(self.valid_window_indices):
                if not valid:
                    continue
                c_window_peaks = peak_indices[valid_count]
                try:
                    hits = _np.where(self.amp[c_window] == _np.max(
                        self.amp[c_window, c_window_peaks]))[0]
                    c_index = int(hits[0]) if len(hits) else 0
                    self._main_peak_amp[c_window] = \
                        float(self.amp[c_window, c_index])
                    self._main_peak_frq[c_window] = self.frq[c_index]
                    valid_indices[c_window] = True
                except ValueError as e:
                    if len(c_window_peaks) == 0:
                        pass
                    else:
                        raise e
                valid_count += 1
            self.valid_window_indices = valid_indices

        _H.Hvsr.update_peaks = _update_peaks
        _HAS_PATCHED_HVSRPY = True
        return True
    except Exception:
        return False


def run_hvsrpy(data, win_len, rejection, fmin, fmax, nfreq):
    """Run hvsrpy (if installed) on the processed data.
    Returns (freqs, amps, log_lines)."""
    try:
        import hvsrpy
        import sigpropy
        import numpy as np
    except Exception as exc:
        return None, None, ["hvsrpy not available: %s" % exc]
    if not _patch_hvsrpy():
        return None, None, ["could not patch hvsrpy 1.0.0 bug"]
    try:
        dt = 1.0 / data.fs
        sensor = hvsrpy.Sensor3c(
            ns=sigpropy.TimeSeries(np.asarray(data.n), dt),
            ew=sigpropy.TimeSeries(np.asarray(data.e), dt),
            vt=sigpropy.TimeSeries(np.asarray(data.z), dt))
        bp_filter = {"flag": False, "flow": fmin, "fhigh": fmax, "order": 5}
        resampling = {"minf": fmin, "maxf": fmax, "nf": nfreq,
                      "res_type": "log"}
        hv = sensor.hv(win_len, bp_filter, 0.05, 40.0, resampling,
                       "geometric-mean")
        hv.reject_windows(n=rejection, max_iterations=50)
        frq = list(hv.frq)
        amp = list(hv.mean_curve(distribution="lognormal"))
        if not frq or not amp:
            return None, None, ["hvsrpy produced no curve"]
        return frq, amp, ["hvsrpy OK: %d samples" % len(frq)]
    except Exception as exc:
        return None, None, ["hvsrpy failed: %s" % exc]


def run_station(name, files, kind, win_len=40.0, rejection=1.5,
                fmin=0.5, fmax=20.0, nfreq=256, use_hvsrpy=True):
    """Run all engines on one station.  Returns a result dict or None."""
    try:
        data = auto_load(files)
        clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                                 max_fs=DECIMATE_TO)
        res = analyze(clean, w_len=win_len, overlap=0.0, rejection=rejection,
                      fmin=fmin, fmax=fmax, nfreq=nfreq, b_value=40,
                      combo="geometric", station=name)
        py_f0, py_a0 = res.f0, res.a0
        py_quality = peak_quality(res)
    except Exception as exc:
        return {"station": name, "kind": kind, "error": str(exc)}

    geo = hvsr_geopsy.find_geopsy()
    geo_f0 = geo_a0 = None
    geo_ok = False
    if geo:
        gfreqs, gamps, glog = hvsr_geopsy.run_geopsy_hv(
            geo, clean, OUT_DIR, win_len, rejection, fmin, fmax, nfreq,
            name, b_value=40, combo="geometric")
        if gfreqs and gamps:
            geo_f0, geo_a0 = pick_peak(gfreqs, gamps, fmin, fmax)
            geo_ok = geo_f0 > 0

    hv_f0 = hv_a0 = None
    hv_ok = False
    if use_hvsrpy:
        hfreqs, hamp, hlog = run_hvsrpy(clean, win_len, rejection,
                                        fmin, fmax, nfreq)
        if hfreqs and hamp:
            hv_f0, hv_a0 = pick_peak(hfreqs, hamp, fmin, fmax)
            hv_ok = hv_f0 > 0

    row = {
        "station": name, "kind": kind, "fs": data.fs,
        "n_samples": data.n_samples,
        "py_f0": py_f0, "py_a0": py_a0,
        "py_quality": py_quality,
        "py_windows": res.n_windows_accepted,
        "py_total": res.n_windows_total,
        "hv_f0": hv_f0, "hv_a0": hv_a0, "hv_ok": hv_ok,
        "geo_f0": geo_f0, "geo_a0": geo_a0, "geo_ok": geo_ok,
        "error": "",
    }
    if geo_ok:
        row["geo_ratio"] = py_f0 / geo_f0 if geo_f0 else None
        row["geo_diff_pct"] = 100.0 * (py_f0 - geo_f0) / geo_f0
    if hv_ok:
        row["hv_ratio"] = py_f0 / hv_f0 if hv_f0 else None
        row["hv_diff_pct"] = 100.0 * (py_f0 - hv_f0) / hv_f0
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sg2", action="store_true")
    ap.add_argument("--mseed", action="store_true")
    ap.add_argument("--slice", default="")
    ap.add_argument("--csv", default="")
    ap.add_argument("--no-hvsrpy", action="store_true")
    args = ap.parse_args()

    include_sg2 = args.sg2 or not args.mseed
    include_mseed = args.mseed or not args.sg2
    stations = collect_stations(include_sg2, include_mseed)
    if args.slice:
        a, b = args.slice.split(":")
        stations = stations[int(a):int(b)]
    if args.limit:
        stations = stations[: args.limit]
    csv_path = args.csv or CSV_PATH
    print("Comparing %d stations (Geopsy: %s)" %
          (len(stations), hvsr_geopsy.find_geopsy() or "NOT FOUND"))
    if not hvsr_geopsy.find_geopsy():
        print("Geopsy not found - nothing to compare against. Exiting.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    header = ("station,kind,fs_hz,n_samples,py_f0,py_a0,py_quality,"
              "py_windows,py_total,hv_f0,hv_a0,hv_ok,hv_diff_pct,"
              "geo_f0,geo_a0,geo_ok,geo_diff_pct,error")
    rows = []
    t0 = time.time()
    for i, (name, files, kind) in enumerate(stations, 1):
        row = run_station(name, files, kind, use_hvsrpy=not args.no_hvsrpy)
        rows.append(row)
        if row.get("error"):
            print("[%3d/%d] %-34s ERROR %s" % (i, len(stations), name,
                                               row["error"]))
        else:
            bits = ["py %.3f" % row["py_f0"]]
            if row.get("hv_ok"):
                bits.append("hv %.3f(%+5.0f%%)" % (row["hv_f0"],
                                                    row["hv_diff_pct"]))
            if row.get("geo_ok"):
                bits.append("geo %.3f(%+5.0f%%)" % (row["geo_f0"],
                                                     row["geo_diff_pct"]))
            print("[%3d/%d] %-34s %s [%s]" % (i, len(stations), name,
                                               "  ".join(bits),
                                               row["py_quality"]))
        sys.stdout.flush()

    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(header + "\n")
        for r in rows:
            fh.write(",".join(_csv(r.get(k)) for k in header.split(","))
                     + "\n")

    # summary: split by peak quality; flat curves have meaningless f0 picks
    ok = [r for r in rows if not r.get("error")]
    clear = [r for r in ok if r.get("py_quality") == "CLEAR"]
    print("\n" + "=" * 60)
    print("THREE-WAY COMPARISON SUMMARY")
    print("=" * 60)
    print("Stations compared         : %d" % len(rows))
    print("Errors                    : %d"
          % sum(1 for r in rows if r.get("error")))
    print("Clear-peak stations       : %d" % len(clear))
    print("Flat / unclear peaks      : %d" % (len(ok) - len(clear)))
    for lbl, sub in (("clear-peak", clear), ("all", ok)):
        for pair, gk, hv in (("built-in vs Geopsy", "geo_ok", "geo_diff_pct"),
                             ("built-in vs hvsrpy", "hv_ok", "hv_diff_pct")):
            rows2 = [r for r in sub if r.get(gk) and r.get(hv) is not None]
            if not rows2:
                continue
            diffs = [abs(r[hv]) for r in rows2]
            med = sorted(diffs)[len(diffs) // 2]
            within50 = sum(1 for d in diffs if d <= 50)
            within60 = sum(1 for d in diffs if d <= 60)
            print("  [%s] %-20s n=%3d mean=%.1f%% med=%.1f%% max=%.0f%% | "
                  "<=50%%: %d  <=60%%: %d"
                  % (lbl, pair, len(rows2), sum(diffs) / len(diffs), med,
                     max(diffs), within50, within60))
    print("CSV report: " + csv_path)
    print("Elapsed: %.1f s" % (time.time() - t0))


def _csv(v):
    if v is None:
        return ""
    s = str(v)
    if "," in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


if __name__ == "__main__":
    main()
