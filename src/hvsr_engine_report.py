"""
hvsr_engine_report.py
=====================
Analysis report writers: _build_log (with its _ok helper), plus
write_target_file / write_report_file used by the GUI export dialogs.

Split out of hvsr_engine.py.
"""


def _build_log(res):
    """Render the plain-text report lines for a completed analysis."""
    log = []
    log.append("=" * 60)
    log.append("            HVSR ANALYZER - RESULTS REPORT")
    log.append("=" * 60)
    log.append("Station                  : %s" % res.station)
    log.append("Window length            : %.1f s" % res.window_len)
    log.append("Window overlap           : %.0f %%" % (res.overlap * 100))
    log.append("Total windows            : %d" % res.n_windows_total)
    log.append("Accepted windows         : %d" % res.n_windows_accepted)
    log.append("Rejected windows         : %d" % (res.n_windows_total - res.n_windows_accepted))
    log.append("Fundamental frequency f0 : %.3f Hz" % res.f0)
    log.append("Peak amplification A0    : %.2f" % res.a0)
    log.append("Std. dev. of f0 (sigma_f): %.3f Hz" % res.sigma_f)
    log.append("Vulnerability index Kg   : %.2f -> %s" % (res.kg, res.kg_level))
    log.append("Smoothing                : %s (width=%s)"
               % (getattr(res, "smoothing", "konno_ohmachi"),
                  getattr(res, "smooth_width", 40.0)))
    log.append("H/V combination          : %s"
               % getattr(res, "combo", "geometric"))
    log.append("")
    log.append("-" * 60)
    log.append("        SESAME 2004 RELIABILITY MATRIX")
    log.append("-" * 60)
    c = res.sesame
    log.append(" [Reliability of the H/V curve]")
    log.append("  f0 > 10/lw        : %s (f0=%.3f Hz, limit=%.3f Hz)"
               % (_ok(c.get("f0_gt_10_over_lw")), res.f0, c.get("limit_f0", 0)))
    log.append("  nc(f0) > 200      : %s (nc=%.1f)"
               % (_ok(c.get("nc_gt_200")), c.get("nc", 0)))
    log.append("  sigma_A < limit   : %s" % _ok(c.get("sigma_A_ok")))
    log.append(" [Clarity of the H/V peak]")
    log.append("  drop below f0/2   : %s (f in [f0/4, f0])" % _ok(c.get("drop_below_f0")))
    log.append("  drop above f0/2   : %s (f in [f0, 4*f0])" % _ok(c.get("drop_above_f0")))
    log.append("  A0 > 2            : %s (A0=%.2f)" % (_ok(c.get("a0_gt_2")), res.a0))
    log.append("  sigma_f < limit   : %s (sigma_f=%.3f, limit=%.3f)"
               % (_ok(c.get("sigma_f_ok")), c.get("sigma_f", 0), c.get("limit_sigma_f", 0)))
    log.append("=" * 60)
    return log

def _ok(flag):
    """Render a boolean as [Ok] / [No] for the text report."""
    return "[Ok]" if flag else "[No]"

def write_target_file(path, freqs, amps, low, high, f0, fmin_frac=0.5, fmax_mult=2.0):
    """Write an inversion target file: freq, amp, stddev (one line per row)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# HVSR inversion target - f0 = %.4f Hz\n" % f0)
        for f, a, lo, hi in zip(freqs, amps, low, high):
            if fmin_frac * f0 <= f <= fmax_mult * f0:
                stddev = max((hi - lo) / 2.0, 0.001)
                fh.write("%.4f\t%.4f\t%.4f\n" % (f, a, stddev))

def write_report_file(path, result):
    """Save the full text report."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(result.report_text + "\n")
