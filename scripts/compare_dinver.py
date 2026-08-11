"""compare_dinver.py - compare the program's 1D inversion of a recording
with an official Dinver 5-layer search parameterisation
(reference_5_layer_model.param).

The .param file is a gzip-compressed tar archive holding contents.xml
(UTF-16 XML, Dinver format).  It defines the SEARCH BOUNDS used for the
reference Dinver inversion: Vs0..Vs4 with [topMin, topMax],
fixed densities and Poisson ranges.  This script:

  1. parses those bounds,
  2. runs the program's full pipeline (SEG-2 -> H/V -> 1D inversion with
     n_layers=4 to mirror Dinver's 5-layer model) on the
     recording,
  3. checks whether the inverted Vs (median + P16/P84) falls inside the
     Dinver search window layer by layer,
  4. computes the Vs30 range that the Dinver search space permits and
     compares it with the program's Vs30,
  5. writes a comparison report + CSV and draws an overlay PNG.

Usage:  python compare_dinver.py [station.sg2]
"""
import io
import math
import os
import sys
import tarfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from hvsr_io import auto_load
from hvsr_engine import preprocess, analyze, trim_seconds
from hvsr_inversion import (invert_hvsr, vs30_from_profile,
                            misfit_histogram, write_inversion_report)
from chart_render import GRID, AXIS, BLACK

DINVER_PARAM = (os.environ.get("DINVER_PARAM") or os.path.expanduser(
    "~/Signal Data/reference_5_layer_model.param"))
DEFAULT_STATION = (os.environ.get("HVSR_STATION") or
               os.path.join(os.path.expanduser("~/Signal Data"),
                            "station.sg2"))
OUT = os.path.join(HERE, "..", "HVSR_Results_E2E")


def read_dinver_param(path):
    """Parse a Dinver .param (gzip tar > contents.xml, UTF-16) and return
    {shortName: [ {name, topMin, topMax, dhMin, dhMax, linkedTo}, ... ]}."""
    with tarfile.open(path, mode="r:*") as tf:
        xml_bytes = tf.extractfile("contents.xml").read()
    text = None
    for enc in ("utf-16", "utf-8"):
        try:
            text = xml_bytes.decode(enc)
            break
        except Exception:
            continue
    root = ET.fromstring(text)
    profiles = {}
    for prof in root.iter("ParamProfile"):
        short = (prof.findtext("shortName") or "").strip()
        layers = []
        for lay in prof.findall("ParamLayer"):
            def num(tag):
                v = lay.findtext(tag)
                return float(v) if v is not None else None
            layers.append({
                "name": lay.get("name"),
                "top_min": num("topMin"),
                "top_max": num("topMax"),
                "dh_min": num("dhMin"),
                "dh_max": num("dhMax"),
                "linked": lay.findtext("linkedTo"),
            })
        if short:
            profiles[short] = layers
    return profiles


def dinver_nominal_depths(vs_layers):
    """Nominal layer depths from the mid-point of each dh search range."""
    depths = [0.0]
    acc = 0.0
    for lay in vs_layers:
        if lay["dh_min"] is None or lay["dh_max"] is None:
            dh = 10.0
        else:
            dh = (lay["dh_min"] + lay["dh_max"]) / 2.0
        acc += dh
        depths.append(acc)
    return depths


def dinver_vs30_range(vs_layers, rho_layers):
    """Vs30 range spanned by the Dinver search space (all-min vs all-max
    Vs at the nominal thicknesses)."""
    depths = dinver_nominal_depths(vs_layers)
    thk = [depths[i + 1] - depths[i] for i in range(len(vs_layers))]
    vs_min = [l["top_min"] for l in vs_layers]
    vs_max = [l["top_max"] for l in vs_layers]
    rho = [l["top_min"] for l in rho_layers] or [2000.0] * len(vs_layers)
    v30_min = vs30_from_profile(thk, vs_min)
    v30_max = vs30_from_profile(thk, vs_max)
    return v30_min, v30_max


def main():
    station = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STATION
    os.makedirs(OUT, exist_ok=True)

    profs = read_dinver_param(DINVER_PARAM)
    vs = profs.get("Vs", [])
    rho = profs.get("Rho", [])
    nu = profs.get("Nu", [])
    if not vs:
        print("no Vs profile found in the param")
        return 1

    # ---- run the program's pipeline with 4 layers (5 incl. half-space) ----
    data = auto_load([station])
    if data.duration > 300.0:
        data = trim_seconds(data, 0.0, 300.0)
    clean, meta = preprocess(data, f_low=0.2, f_high=20.0, mute=True)
    res = analyze(clean, w_len=30.0, overlap=0.0, rejection=1.5,
                  fmin=0.5, fmax=20.0, nfreq=256, b_value=40.0,
                  combo="geometric", taper=0.05, max_iterations=50,
                  smoothing="konno_ohmachi", smooth_width=40.0,
                  station=os.path.basename(station))
    vs30_anchor = None
    try:
        vs30_anchor = res.standards["sesame"]["vs30"]
    except Exception:
        pass
    inv = invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                      station=os.path.basename(station), n_layers=4,
                      n_iter=600, vs30_anchor=vs30_anchor)

    v30_lo, v30_hi = dinver_vs30_range(vs, rho)
    my_in = v30_lo is not None and v30_hi is not None and \
        v30_lo - 1.0 <= (inv.vs30 or 0) <= v30_hi + 1.0

    L = []
    L.append("=" * 78)
    L.append("  PROGRAM 1D INVERSION  vs  DINVER REFERENCE SEARCH MODEL")
    L.append("  %s" % os.path.basename(station))
    L.append("  reference: %s" % os.path.basename(DINVER_PARAM))
    L.append("=" * 78)
    L.append("H/V result      : f0 = %.3f Hz  A0 = %.2f" % (res.f0, res.a0))
    L.append("Inverted Vs30   : %.0f m/s  (NEHRP %s / SNI %s)"
             % (inv.vs30 or 0, inv.soil_class_nehrp[0],
                inv.soil_class_sni[0]))
    L.append("Dinver Vs30 range: %.0f - %.0f m/s  ->  %s"
             % (v30_lo or 0, v30_hi or 0,
                "INSIDE the reference search space" if my_in
                else "OUTSIDE the reference search space"))
    L.append("Best misfit     : %.4f (median %.4f, P90 %.4f)"
             % (inv.misfit or 0, inv.misfit_p50 or 0, inv.misfit_p90 or 0))
    L.append("")
    L.append("%-6s %-12s %-34s %-16s %s" % (
        "layer", "depth (m)", "program Vs (m/s)", "Dinver Vs bounds",
        "verdict"))
    L.append("-" * 78)
    n_inside = 0
    for i, lay in enumerate(inv.layers):
        dv = vs[i] if i < len(vs) else vs[-1]
        d_lo, d_hi = dv["top_min"], dv["top_max"]
        lo, hi = lay.get("vs_lo"), lay.get("vs_hi")
        inside = lo is not None and hi is not None and lo >= d_lo - 1 and \
            hi <= d_hi + 1
        n_inside += 1 if inside else 0
        mid = lay["top"] + (lay["bottom"] - lay["top"]) / 2.0 \
            if lay["bottom"] is not None else lay["top"]
        L.append("%-6s %-12s %-34s %-16s %s" % (
            str(lay["layer"] + 1), "%.1f" % mid,
            "%.0f [%.0f - %.0f]" % (lay["vs"], lo or 0, hi or 0),
            "[%.0f - %.0f]" % (d_lo, d_hi),
            "INSIDE" if inside else "outside"))
    L.append("-" * 78)
    L.append("Layers inside the Dinver search window: %d/%d"
             % (n_inside, len(inv.layers)))
    L.append("")

    txt_path = os.path.join(OUT, "dinver_comparison.txt")
    io.open(txt_path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))

    # CSV
    csv_path = os.path.join(OUT, "dinver_comparison.csv")
    with io.open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write("layer,program_vs_median,program_vs_p16,program_vs_p84,"
                 "dinver_vs_min,dinver_vs_max,inside\n")
        for i, lay in enumerate(inv.layers):
            dv = vs[i] if i < len(vs) else vs[-1]
            lo, hi = lay.get("vs_lo"), lay.get("vs_hi")
            inside = lo is not None and hi is not None and \
                lo >= dv["top_min"] - 1 and hi <= dv["top_max"] + 1
            fh.write("%d,%.1f,%s,%s,%.1f,%.1f,%s\n" % (
                lay["layer"] + 1, lay["vs"],
                "%.1f" % lo if lo is not None else "",
                "%.1f" % hi if hi is not None else "",
                dv["top_min"], dv["top_max"],
                "INSIDE" if inside else "outside"))

    # report + PNG
    rep_path = os.path.join(OUT, "dinver_comparison_inversion_report.txt")
    write_inversion_report(rep_path, inv)
    _draw_overlay(inv, vs, os.path.join(OUT, "dinver_comparison.png"))
    print("\nSaved: %s / %s / %s" % (txt_path, csv_path,
                                     os.path.join(OUT,
                                                  "dinver_comparison.png")))
    return 0


def _draw_overlay(inv, vs_layers, path):
    """Overlay PNG: program Vs staircase + P16/P84 band, Dinver search
    envelope (per-layer [topMin, topMax] at nominal depths)."""
    from chart_render import HvsrChart

    layers = inv.layers
    depths = dinver_nominal_depths(vs_layers)
    dmax = max((l["bottom"] or l["top"] for l in layers), default=50.0)
    dmax = max(dmax, depths[-1] if depths else 50.0)
    dmax = max(20.0, math.ceil(dmax / 20.0) * 20.0)
    vs_all = [l["vs"] for l in layers] + \
             [l.get("vs_hi") or l["vs"] for l in layers] + \
             [l.get("vs_lo") or l["vs"] for l in layers] + \
             [l["top_max"] for l in vs_layers]
    vs_max = max(100.0, math.ceil(max(vs_all) / 500.0) * 500.0)

    c = HvsrChart(width=1100, height=620)
    L, R, T, B = c.left + 8, c.right, c.top, c.bottom

    def X(v):
        return L + (v / vs_max) * (R - L)

    def Y(d):
        return T + (d / dmax) * (B - T)

    # grid
    for t in range(0, int(vs_max) + 1, 500):
        x = int(X(t))
        c._line(x, T, x, B, GRID, 1)
        c._text(x - _tw(str(t)) // 2, B + 6, str(t), AXIS)
    for t in range(0, int(dmax) + 1, 20):
        y = int(Y(t))
        c._line(L, y, R, y, GRID, 1)
        c._text(L - 6 - _tw(str(t)), y - 3, str(t), AXIS)

    # Dinver envelope (shaded, at nominal depths)
    for i, dv in enumerate(vs_layers):
        y0 = Y(depths[i])
        y1 = Y(depths[i + 1]) if i + 1 < len(depths) else B
        c._fill_rect(int(X(dv["top_min"])), int(y0),
                     int(X(dv["top_max"])), int(y1), (222, 232, 244))
    # program band + staircase
    for lay in layers:
        lo = lay.get("vs_lo")
        hi = lay.get("vs_hi")
        y0 = Y(lay["top"])
        y1 = Y(lay["bottom"] or lay["top"])
        if lo is not None and hi is not None:
            c._fill_rect(int(X(lo)), int(y0), int(X(hi)), int(y1),
                         (157, 182, 216))
    prev = (X(layers[0]["vs"]), Y(0.0))
    for lay in layers:
        x = X(lay["vs"])
        y0 = Y(lay["top"])
        y1 = Y(lay["bottom"] or lay["top"])
        c._line(prev[0], prev[1], x, y0, (20, 86, 168), 3)
        c._line(x, y0, x, y1, (20, 86, 168), 3)
        prev = (x, y1)

    c._line(L, T, L, B, AXIS, 1)
    c._line(L, B, R, B, AXIS, 1)
    c._text(L, T - 12, "Vs (m/s)", BLACK, 1)
    c._text(L, c.height - 16, "Depth (m)", BLACK, 1)
    c._text(L, 12, "Program inversion vs Dinver search model (reference site)",
            BLACK, 2)
    c._fill_rect(L + 10, T + 30, L + 34, T + 42, (222, 232, 244))
    c._text(L + 40, T + 30, "Dinver Vs search range", (90, 95, 105), 1)
    c._fill_rect(L + 10, T + 46, L + 34, T + 58, (157, 182, 216))
    c._text(L + 40, T + 46, "Program Vs (P16-P84 band)", (90, 95, 105), 1)
    c.save_png(path)


def _tw(t):
    from chart_render import _text_width
    return _text_width(str(t))


if __name__ == "__main__":
    sys.exit(main())
