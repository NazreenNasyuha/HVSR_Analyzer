"""
merge_fullcmp.py
================
Merge the 6 parallel compare_geopsy.py output CSVs (fullcmp_0..5.csv)
into a single ThreeWay_Comparison_FULL.csv and print the aggregate
summary: clear/flat counts, built-in vs Geopsy and vs hvsrpy f0
agreement, and window-acceptance statistics.

Run:  python merge_fullcmp.py
"""

import glob
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
HEADER = ("station,kind,fs_hz,n_samples,py_f0,py_a0,py_quality,"
          "py_windows,py_total,hv_f0,hv_a0,hv_ok,hv_diff_pct,"
          "geo_f0,geo_a0,geo_ok,geo_diff_pct,error")


def rows():
    cols = HEADER.split(",")
    for p in sorted(glob.glob(os.path.join(HERE, "..", "fullcmp_*.csv"))):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line == HEADER:
                    continue
                parts = line.split(",")
                while len(parts) < len(cols):
                    parts.append("")
                yield dict(zip(cols, parts[:len(cols)]))


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    all_rows = list(rows())
    out = os.path.join(HERE, "..", "HVSR_Results",
                       "ThreeWay_Comparison_FULL.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(HEADER + "\n")
        for r in all_rows:
            fh.write(",".join(r.get(c, "") for c in HEADER.split(","))
                     + "\n")
    print("Merged %d station rows -> %s" % (len(all_rows), out))
    print("=" * 62)

    ok = [r for r in all_rows if not r.get("error")]
    clear = [r for r in ok if r.get("py_quality") == "CLEAR"]
    flat = [r for r in ok if r.get("py_quality") != "CLEAR"]
    print("Total stations            : %d" % len(all_rows))
    print("Errors                    : %d"
          % sum(1 for r in all_rows if r.get("error")))
    print("CLEAR peaks               : %d" % len(clear))
    print("FLAT / UNCLEAR            : %d" % len(flat))

    for lbl, sub in (("clear-peak", clear), ("all", ok)):
        for pair, key, diff in (
                ("built-in vs Geopsy", "geo_ok", "geo_diff_pct"),
                ("built-in vs hvsrpy", "hv_ok", "hv_diff_pct")):
            rows2 = [r for r in sub if r.get(key) and f(r.get(diff))
                     is not None]
            if not rows2:
                continue
            diffs = [abs(f(r[diff])) for r in rows2]
            med = sorted(diffs)[len(diffs) // 2]
            w50 = sum(1 for d in diffs if d <= 50)
            w60 = sum(1 for d in diffs if d <= 60)
            w20 = sum(1 for d in diffs if d <= 20)
            print("  [%-11s] %-20s n=%3d mean=%5.1f%% med=%5.1f%% "
                  "max=%5.0f%% | <=20%%:%3d <=50%%:%3d <=60%%:%3d"
                  % (lbl, pair, len(rows2),
                     sum(diffs) / len(diffs), med, max(diffs),
                     w20, w50, w60))

    # window acceptance across all stations (the rejection-bug footprint)
    acc = [f(r["py_windows"]) for r in ok if f(r["py_windows"]) is not None]
    tot = [f(r["py_total"]) for r in ok if f(r["py_total"]) is not None]
    if acc:
        ratios = [a / t if t else 0.0 for a, t in zip(acc, tot)]
        ratios.sort()
        print("\nbuilt-in window acceptance: median %.0f%%  "
              "(p25=%.0f%% p75=%.0f%%)" %
              (100 * ratios[len(ratios) // 2],
               100 * ratios[len(ratios) // 4],
               100 * ratios[3 * len(ratios) // 4]))
        bad = sum(1 for a, t in zip(acc, tot)
                  if t > 10 and a / t < 0.5)
        print("stations keeping <50%% of windows: %d / %d"
              % (bad, len(acc)))

    # f0 sanity: py vs geo for clear stations
    geo_f0s = [f(r["geo_f0"]) for r in clear if r.get("geo_ok")]
    py_f0s = [f(r["py_f0"]) for r in clear if r.get("geo_ok")]
    if geo_f0s:
        ratios = [p / g for p, g in zip(py_f0s, geo_f0s)]
        ratios.sort()
        print("\nclear stations f0 ratio (py/geo): med=%.3f "
              "(min=%.3f max=%.3f)" % (ratios[len(ratios) // 2],
                                       ratios[0], ratios[-1]))


if __name__ == "__main__":
    main()
