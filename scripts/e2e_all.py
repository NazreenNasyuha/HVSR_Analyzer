"""e2e_all.py - run the full HVSR pipeline on every SEG-2 recording.

For each station: auto_load -> trim (max 300 s) -> preprocess ->
analyze (fixed manual parameters) -> reliability/standards ->
1D inversion (with ensemble uncertainty) -> report / CSV / profile PNG.
A summary CSV + text table are written incrementally to
HVSR_Results_E2E/ so a partial run is never lost.

Usage:  python e2e_all.py
"""
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from hvsr_io import auto_load
from hvsr_engine import preprocess, analyze, trim_seconds
from hvsr_inversion import (invert_hvsr, write_inversion_report,
                            write_inversion_csv)

# --- Station list for the E2E run ---
# Override with the SIGNAL_DATA_DIR environment variable.
DATA_DIR = os.environ.get("SIGNAL_DATA_DIR") or os.path.expanduser("~/Signal Data")
# Edit this list to point at your own recordings (one .sg2 / .mseed / .eqd
# file per station).  Paths are resolved against DATA_DIR.
STATIONS = [
    os.path.join(DATA_DIR, "station_1.sg2"),
    os.path.join(DATA_DIR, "station_2.sg2"),
    os.path.join(DATA_DIR, "station_3.sg2"),
    os.path.join(DATA_DIR, "station_4.sg2"),
    os.path.join(DATA_DIR, "station_5.sg2"),
    os.path.join(DATA_DIR, "station_6.sg2"),
    os.path.join(DATA_DIR, "station_7.sg2"),
    os.path.join(DATA_DIR, "station_8.sg2"),
]

MAX_SECONDS = 300.0
OUT = os.path.join(HERE, "..", "HVSR_Results_E2E")
SUMMARY_CSV = os.path.join(OUT, "all_stations_summary.csv")
SUMMARY_TXT = os.path.join(OUT, "all_stations_summary.txt")


def analyze_one(path):
    """Return a dict of the pipeline results for one station."""
    t0 = time.time()
    data = auto_load([path])
    loaded = time.time() - t0
    trimmed = ""
    if data.duration > MAX_SECONDS:
        data = trim_seconds(data, 0.0, MAX_SECONDS)
        trimmed = "%.0f s" % data.duration
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True,
                             sta_sec=1.0, lta_sec=30.0, slta_threshold=2.5)
    res = analyze(clean, w_len=30.0, overlap=0.0,
                  rejection=1.5, fmin=0.5, fmax=20.0,
                  nfreq=256, b_value=40.0, combo="geometric",
                  taper=0.05, max_iterations=50,
                  smoothing="konno_ohmachi",
                  smooth_width=40.0,
                  station=os.path.basename(path))
    vs30_anchor = None
    try:
        vs30_anchor = res.standards["sesame"]["vs30"]
    except Exception:
        pass
    sesame_verdict = ""
    sesame_score = None
    try:
        ev = res.standards["sesame"]
        sesame_verdict = ev.get("verdict", "")
        items = ev.get("items", [])
        sesame_score = sum(1 for i in items
                           if i.get("ok") and i.get("key") != "sigma_f_ok")
    except Exception:
        pass
    t1 = time.time()
    inv = invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                      station=os.path.basename(path), n_layers=3,
                      n_iter=400, vs30_anchor=vs30_anchor)
    inv_time = time.time() - t1
    return {
        "file": os.path.basename(path),
        "load_s": round(loaded, 1),
        "trimmed": trimmed,
        "fs_hz": clean.fs,
        "f0_hz": res.f0,
        "a0": res.a0,
        "kg": res.kg,
        "sesame": sesame_score,
        "sesame_verdict": sesame_verdict,
        "vs30": inv.vs30,
        "nehrp": inv.soil_class_nehrp[0],
        "sni": inv.soil_class_sni[0],
        "f0_syn": inv.f0_syn,
        "misfit": inv.misfit,
        "accepted": inv.n_accepted,
        "inv_s": round(inv_time, 1),
        "inv": inv,
        "res": res,
    }


def fmt(x, nd=2):
    if x is None:
        return "-"
    if isinstance(x, float):
        return "%.*f" % (nd, x)
    return str(x)


def main():
    os.makedirs(OUT, exist_ok=True)
    header = ["file", "load_s", "trimmed", "fs_hz", "f0_hz", "a0", "kg",
              "sesame", "sesame_verdict", "vs30", "nehrp", "sni", "f0_syn",
              "misfit", "accepted", "inv_s"]
    rows = []
    for path in STATIONS:
        name = os.path.basename(path)
        try:
            r = analyze_one(path)
        except Exception as exc:
            print("FAIL %-32s : %s" % (name, exc))
            rows.append({"file": name, "load_s": "-", "trimmed": "-",
                         "fs_hz": "-", "f0_hz": "-", "a0": "-", "kg": "-",
                         "sesame": "-", "sesame_verdict": "-", "vs30": "-",
                         "nehrp": "-", "sni": "-", "f0_syn": "-",
                         "misfit": "-", "accepted": "-", "inv_s": "-"})
            _write_summary(header, rows)
            continue
        print("OK   %-28s f0=%.3f A0=%.2f score=%s %-8s | Vs30=%.0f "
              "NEHRP=%s SNI=%s misfit=%.3f (%.1fs)"
              % (name, r["f0_hz"], r["a0"], r["sesame"], r["sesame_verdict"],
                 r["vs30"] or 0, r["nehrp"], r["sni"],
                 r["misfit"] or 0, r["load_s"]))
        # per-station exports
        base = os.path.splitext(name)[0]
        write_inversion_report(os.path.join(OUT, base + "_inv_report.txt"),
                               r["inv"])
        write_inversion_csv(os.path.join(OUT, base + "_inv_model.csv"),
                            r["inv"])
        try:
            from chart_render import HvsrChart
            c = HvsrChart()
            c.draw_vs_profile(r["inv"].layers, vs30=r["inv"].vs30,
                              station=base, note="E2E all-stations",
                              misfit_hist=_hist_of(r["inv"]),
                              misfit_best=r["inv"].misfit,
                              misfit_median=r["inv"].misfit_p50,
                              misfit_p90=r["inv"].misfit_p90)
            c.save_png(os.path.join(OUT, base + "_vs_profile.png"))
        except Exception as exc:
            print("  PNG failed: %s" % exc)
        rows.append(r)
        _write_summary(header, rows)


def _hist_of(inv):
    from hvsr_inversion import misfit_histogram
    return misfit_histogram(inv.misfits)


def _write_summary(header, rows):
    with open(SUMMARY_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: fmt(r.get(k), 3) if k in
                        ("f0_hz", "f0_syn", "misfit", "a0", "kg")
                        else fmt(r.get(k)) for k in header})
    with open(SUMMARY_TXT, "w", encoding="utf-8") as fh:
        fh.write("%-28s %8s %6s %5s %-10s %5s %6s %8s %6s %7s %6s\n"
                 % ("file", "f0(Hz)", "A0", "score", "verdict", "Vs30",
                    "NEHRP", "SNI", "misfit", "accepted", "load_s"))
        fh.write("-" * 104 + "\n")
        for r in rows:
            fh.write("%-28s %8s %6s %5s %-10s %5s %8s %6s %7s %6s %6s\n"
                     % (r["file"], fmt(r["f0_hz"], 3), fmt(r["a0"]),
                        r["sesame"], r["sesame_verdict"], fmt(r["vs30"], 0),
                        r["nehrp"], r["sni"], fmt(r["misfit"], 3),
                        r["accepted"], r["load_s"]))


if __name__ == "__main__":
    main()
