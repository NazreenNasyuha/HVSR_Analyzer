"""
hvsr_inv_report.py
==================
Inversion reporting: _build_inversion_log, misfit_histogram,
_percentile and the write_inversion_csv / write_inversion_report
exporters used by the GUI and scripts.

Split out of hvsr_inversion.py.
"""


import math

def misfit_histogram(misfits, nbins=24):
    """Histogram of the finite model misfits -> (edges, counts).

    edges has nbins+1 increasing values and counts has nbins entries.
    Returns (None, []) when fewer than 2 finite values are present
    (e.g. all models degenerate).  inf / None values are skipped.
    """
    vals = sorted(m for m in misfits
                  if m is not None and math.isfinite(m))
    if len(vals) < 2:
        return None, []
    nbins = max(4, int(nbins))
    lo, hi = vals[0], vals[-1]
    if hi <= lo:
        hi = lo + 1e-9
    width = (hi - lo) / nbins
    edges = [lo + width * k for k in range(nbins + 1)]
    counts = [0] * nbins
    for v in vals:
        k = int((v - lo) / width)
        if k >= nbins:
            k = nbins - 1
        counts[k] += 1
    return edges, counts

def _percentile(vals, p):
    """Nearest-rank percentile of a list (deterministic, no interpolation)."""
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    k = max(1, min(n, int(math.ceil(p / 100.0 * n))))
    return s[k - 1]

def _build_inversion_log(res):
    """Format the plain-text inversion report lines from a finished model."""
    L = []
    L.append("=" * 62)
    L.append("            1D HVSR INVERSION - RESULTS")
    L.append("=" * 62)
    L.append("Station          : %s" % res.station)
    L.append("Observed f0 / A0 : %.3f Hz / %.2f" % (res.f0_obs, res.a0_obs))
    L.append("Synthetic f0     : %.3f Hz" % res.f0_syn)
    L.append("Models tested    : %d" % res.n_models)
    L.append("Models accepted  : %d" % res.n_accepted)
    L.append("Best misfit      : %.4f (log10 H/V L2)" % (res.misfit or 0))
    if res.vs30:
        L.append("Vs30 (profile)   : %.0f m/s" % res.vs30)
        L.append("NEHRP site class : %s - %s" % (res.soil_class_nehrp[0],
                                                 res.soil_class_nehrp[1]))
        L.append("SNI site class   : %s - %s" % (res.soil_class_sni[0],
                                                 res.soil_class_sni[1]))
    L.append("")
    L.append("-" * 62)
    L.append(" LAYER   TOP(m)   BOTTOM(m)   Vs(m/s)   Vp(m/s)   rho(g/cc)  "
             "SOIL (NEHRP)")
    L.append("-" * 62)
    try:
        import hvsr_standards
    except Exception:
        hvsr_standards = None
    for lay in res.layers:
        soil = ""
        if hvsr_standards is not None:
            cls, _d = hvsr_standards.soil_class(lay["vs"])
            soil = "class " + cls
        bot = "inf" if lay["bottom"] is None or lay["thickness"] is None \
            else "%.1f" % lay["bottom"]
        L.append("  %3d     %6.1f  %8s   %7.1f  %7.1f   %6.2f    %s"
                 % (lay["layer"] + 1, lay["top"], bot, lay["vs"],
                    lay["vp"], lay["rho"], soil))
    L.append("")
    L.append("-" * 62)
    L.append(" UNCERTAINTY - P16 / P84 of the accepted ensemble "
             "(%d models)" % res.n_accepted)
    L.append("-" * 62)
    for lay in res.layers:
        if lay.get("vs_lo") is not None and lay.get("vs_hi") is not None:
            L.append("  layer %d: Vs = %.0f [%.0f - %.0f] m/s"
                     % (lay["layer"] + 1, lay["vs"], lay["vs_lo"],
                        lay["vs_hi"]))
        if lay.get("thk_lo") is not None and lay.get("thk_hi") is not None:
            L.append("           h  = %.1f [%.1f - %.1f] m"
                     % (lay["thickness"], lay["thk_lo"], lay["thk_hi"]))
    L.append("  misfit: best %.4f | median %.4f | P90 %.4f"
             % (res.misfit or 0, res.misfit_p50 or 0, res.misfit_p90 or 0))
    L.append("=" * 62)
    return L

def write_inversion_csv(path, res):
    """Save the inverted profile as a CSV."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("layer,top_m,bottom_m,thickness_m,Vs_mps,Vp_mps,"
                 "rho_gcc,soil_class,Vs30_mps,vs_p16,vs_p84,"
                 "thk_p16,thk_p84\n")
        try:
            import hvsr_standards
        except Exception:
            hvsr_standards = None
        for lay in res.layers:
            cls = ""
            if hvsr_standards is not None:
                cls = hvsr_standards.soil_class(lay["vs"])[0]
            bot = lay["bottom"] if lay["bottom"] is not None else ""
            thk = lay["thickness"] if lay["thickness"] is not None else ""
            lo = lay.get("vs_lo")
            hi = lay.get("vs_hi")
            tlo = lay.get("thk_lo")
            thi = lay.get("thk_hi")
            fh.write("%d,%.3f,%s,%s,%.2f,%.2f,%.3f,%s,%s,%s,%s,%s,%s\n"
                     % (lay["layer"] + 1, lay["top"], bot, thk, lay["vs"],
                        lay["vp"], lay["rho"], cls,
                        ("%.1f" % res.vs30) if res.vs30 else "",
                        ("%.1f" % lo) if lo is not None else "",
                        ("%.1f" % hi) if hi is not None else "",
                        ("%.1f" % tlo) if tlo is not None else "",
                        ("%.1f" % thi) if thi is not None else ""))

def write_inversion_report(path, res):
    """Save the plain-text inversion report."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(res.report_text + "\n")
