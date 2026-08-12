"""
hvsr_standards_eval.py
======================
The per-standard criterion evaluation logic:

- evaluate_sesame / evaluate_japan / evaluate_usgs / evaluate_generic /
  evaluate_indonesia plus the _check / soil_class / soil_class_sni helpers
  and the _EVALUATORS dispatch table,
- evaluate_all / build_standards_report and recommended_params.

Split out of hvsr_standards.py.
"""

from hvsr_standards_data import DEFAULT_STANDARD, STANDARDS, estimate_thickness, estimate_vs30_powerlaw

def soil_class(vs30):
    """NEHRP / Japanese building-code site class from Vs30 (m/s)."""
    if vs30 is None:
        return "N/A", "cannot be assigned"
    if vs30 > 1500:
        return "A", "Hard rock (Vs30 > 1500 m/s)"
    if vs30 > 760:
        return "B", "Rock (760 < Vs30 <= 1500 m/s)"
    if vs30 > 360:
        return "C", "Very dense soil / soft rock (360-760 m/s)"
    if vs30 > 180:
        return "D", "Stiff soil (180-360 m/s)"
    return "E", "Soft soil (Vs30 <= 180 m/s)"

def soil_class_sni(vs30):
    """Indonesian site class (SA-SF) from Vs30 per SNI 1726-2019 Table 5.

    SNI 1726:2019 rounds the NEHRP boundaries to 1500 / 750 / 350 / 175
    m/s and keeps a special class SF for soils that need a site-specific
    evaluation (e.g. liquefiable profiles, SNI 8460-2017).
    """
    if vs30 is None:
        return "N/A", "cannot be assigned"
    if vs30 > 1500:
        return "SA", "Hard rock (Vs30 > 1500 m/s)"
    if vs30 > 750:
        return "SB", "Rock (750 < Vs30 <= 1500 m/s)"
    if vs30 > 350:
        return "SC", "Very dense soil / soft rock (350 < Vs30 <= 750 m/s)"
    if vs30 > 175:
        return "SD", "Stiff soil (175 < Vs30 <= 350 m/s)"
    return "SE", ("Soft soil (Vs30 <= 175 m/s); class SF requires a "
                  "site-specific evaluation (SNI 8460-2017)")

def recommended_params(standard_id=DEFAULT_STANDARD):
    """Recommended processing parameters for a standard."""
    return dict(STANDARDS[standard_id]["params"])

def _check(key, label, desc, ok, detail=""):
    """Build one checklist item dict shown on the reliability tab."""
    return {"key": key, "label": label, "desc": desc, "ok": bool(ok),
            "detail": detail}

def evaluate_sesame(res):
    """SESAME 2004 checklist from an analysed result."""
    c = res.sesame
    items = [
        _check("f0_gt_10_over_lw", "f0 > 10/lw",
               "Fundamental frequency above the window-length limit",
               c.get("f0_gt_10_over_lw"),
               "f0=%.3f Hz, limit=%.3f Hz" % (res.f0, c.get("limit_f0", 0))),
        _check("nc_gt_200", "nc(f0) > 200",
               "Number of significant cycles", c.get("nc_gt_200"),
               "nc=%.1f" % c.get("nc", 0)),
        _check("sigma_A_ok", "sigma_A < limit",
               "Curve scatter below the allowed level",
               c.get("sigma_A_ok")),
        _check("drop_below_f0", "Drop below A0/2 (low f)",
               "Clear peak between f0/4 and f0", c.get("drop_below_f0")),
        _check("drop_above_f0", "Drop below A0/2 (high f)",
               "Clear peak between f0 and 4*f0", c.get("drop_above_f0")),
        _check("a0_gt_2", "A0 > 2", "Peak amplitude above 2",
               c.get("a0_gt_2"), "A0=%.2f" % res.a0),
        _check("sigma_f_ok", "sigma_f < limit",
               "Peak-frequency scatter below the limit",
               c.get("sigma_f_ok"),
               "sigma_f=%.3f, limit=%.3f" % (c.get("sigma_f", 0),
                                             c.get("limit_sigma_f", 0))),
    ]
    core = [it for it in items if it["key"] not in ("sigma_f_ok",)]
    ok = all(it["ok"] for it in core)
    verdict = ("RELIABLE" if ok else "NOT RELIABLE")
    return {"id": "sesame", "items": items, "verdict": verdict,
            "ok": ok}

def evaluate_japan(res):
    """Japan J-SHIS / JAMC checklist."""
    f0, a0 = res.f0, res.a0
    win = res.window_len
    n_win = res.n_windows_accepted
    in_range = 0.2 <= f0 <= 20.0
    a0_clear = a0 >= 2.0
    enough_windows = n_win >= 10
    nc = n_win * win * f0
    nc_ok = nc >= 200
    sigma_rel = (res.sigma_f / f0) if f0 > 0 else 1.0
    stable = sigma_rel <= 0.2

    vs30 = estimate_vs30_powerlaw(f0)
    cls, cls_desc = soil_class(vs30)

    items = [
        _check("f0_in_range", "f0 in 0.2-20 Hz",
               "Fundamental frequency inside the J-SHIS analysis band",
               in_range, "f0=%.3f Hz" % f0),
        _check("n_windows", ">= 10 windows",
               "Enough windows for a stable average", enough_windows,
               "%d windows" % n_win),
        _check("nc_gt_200", "nc(f0) > 200",
               "Number of significant cycles", nc_ok, "nc=%.1f" % nc),
        _check("a0_clear", "A0 >= 2 (clear peak)",
               "Peak amplitude high enough to trust", a0_clear,
               "A0=%.2f" % a0),
        _check("f0_stable", "sigma_f <= 0.2*f0",
               "Peak frequency stable across windows", stable,
               "sigma_f=%.3f (%.0f%% of f0)" % (res.sigma_f, 100 * sigma_rel)),
    ]
    ok = all(it["ok"] for it in items)
    return {"id": "japan", "items": items,
            "verdict": ("PASS" if ok else "FAIL"), "ok": ok,
            "vs30": vs30, "soil_class": cls, "soil_desc": cls_desc}

def evaluate_usgs(res):
    """USGS / NEHRP checklist: peak clarity + site class."""
    f0, a0 = res.f0, res.a0
    a0_clear = a0 >= 2.0
    c = res.sesame
    drop_ok = c.get("drop_below_f0") and c.get("drop_above_f0")
    n_win_ok = res.n_windows_accepted >= 10
    vs30 = estimate_vs30_powerlaw(f0)
    cls, cls_desc = soil_class(vs30)
    items = [
        _check("a0_clear", "A0 > 2", "Clear resonant peak", a0_clear,
               "A0=%.2f" % a0),
        _check("peak_sharp", "Clear drop either side of f0",
               "Peak is a genuine resonance", drop_ok),
        _check("n_windows", ">= 10 windows", "Stable average",
               n_win_ok, "%d windows" % res.n_windows_accepted),
        _check("site_class", "NEHRP site class assigned",
               "Vs30-based soil classification", vs30 is not None,
               "Vs30=%.0f m/s -> class %s" % (vs30 or 0, cls)),
    ]
    ok = a0_clear and drop_ok
    return {"id": "usgs", "items": items,
            "verdict": ("PASS" if ok else "FAIL"), "ok": ok,
            "vs30": vs30, "soil_class": cls, "soil_desc": cls_desc}

def evaluate_generic(res):
    """Generic / industry checklist."""
    f0, a0 = res.f0, res.a0
    items = [
        _check("f0_valid", "f0 in analysis range",
               "Peak inside 0.5-20 Hz", 0.5 <= f0 <= 20.0,
               "f0=%.3f Hz" % f0),
        _check("a0_clear", "A0 > 2", "Clear peak", a0 > 2.0,
               "A0=%.2f" % a0),
        _check("n_windows", ">= 10 windows",
               "Enough windows", res.n_windows_accepted >= 10,
               "%d windows" % res.n_windows_accepted),
        _check("stable", "sigma_f <= 0.2*f0",
               "Peak frequency stable", (res.sigma_f <= 0.2 * f0)
               if f0 > 0 else False,
               "sigma_f=%.3f" % res.sigma_f),
    ]
    ok = all(it["ok"] for it in items)
    return {"id": "generic", "items": items,
            "verdict": ("PASS" if ok else "FAIL"), "ok": ok}

def evaluate_indonesia(res):
    """Indonesia (SNI 1726-2019 / BMKG) checklist."""
    f0, a0 = res.f0, res.a0
    in_range = 0.2 <= f0 <= 20.0
    a0_clear = a0 >= 2.0
    n_win_ok = res.n_windows_accepted >= 10
    nc = res.n_windows_accepted * res.window_len * f0
    sigma_rel = (res.sigma_f / f0) if f0 > 0 else 1.0
    stable = sigma_rel <= 0.2
    vs30 = estimate_vs30_powerlaw(f0)
    cls, cls_desc = soil_class_sni(vs30)
    items = [
        _check("f0_in_range", "f0 in 0.2-20 Hz",
               "Fundamental frequency inside the analysis band", in_range,
               "f0=%.3f Hz" % f0),
        _check("n_windows", ">= 10 windows",
               "Enough windows for a stable average", n_win_ok,
               "%d windows" % res.n_windows_accepted),
        _check("nc_gt_200", "nc(f0) > 200",
               "Number of significant cycles", nc > 200, "nc=%.1f" % nc),
        _check("a0_clear", "A0 >= 2 (clear peak)",
               "Peak amplitude high enough to trust", a0_clear,
               "A0=%.2f" % a0),
        _check("f0_stable", "sigma_f <= 0.2*f0",
               "Peak frequency stable across windows", stable,
               "sigma_f=%.3f (%.0f%% of f0)" % (res.sigma_f,
                                                100 * sigma_rel)),
        _check("site_class", "SNI site class assigned",
               "Vs30-based classification per SNI 1726-2019",
               vs30 is not None,
               "Vs30=%.0f m/s -> %s" % (vs30 or 0, cls)),
    ]
    ok = all(it["ok"] for it in items)
    return {"id": "indonesia", "items": items,
            "verdict": ("PASS" if ok else "FAIL"), "ok": ok,
            "vs30": vs30, "soil_class": cls, "soil_desc": cls_desc}

_EVALUATORS = {
    "sesame": evaluate_sesame,
    "japan": evaluate_japan,
    "usgs": evaluate_usgs,
    "generic": evaluate_generic,
    "indonesia": evaluate_indonesia,
}

def evaluate_all(res, standard_ids=None):
    """Evaluate one or all standards for a result.

    Returns a dict {standard_id: evaluation} and adds a "vs30" / "h"
    estimate block per standard.
    """
    if standard_ids is None:
        standard_ids = list(STANDARDS.keys())
    out = {}
    for sid in standard_ids:
        if sid not in _EVALUATORS:
            continue
        ev = _EVALUATORS[sid](res)
        if res.f0 > 0:
            h = estimate_thickness(res.f0)
            vs30 = estimate_vs30_powerlaw(res.f0)
            ev["thickness"] = h
            ev["vs30"] = vs30
            if "soil_class" not in ev:   # keep per-standard class (e.g. SNI)
                cls, desc = soil_class(vs30)
                ev["soil_class"] = cls
                ev["soil_desc"] = desc
        out[sid] = ev
    return out

def build_standards_report(res, standard_ids=None):
    """Plain-text report block for all requested standards."""
    evals = evaluate_all(res, standard_ids)
    lines = []
    for sid, ev in evals.items():
        std = STANDARDS[sid]
        lines.append("")
        lines.append("-" * 60)
        lines.append("   %s" % std["name"])
        lines.append("   Source: %s" % std["source"])
        lines.append("-" * 60)
        for it in ev["items"]:
            mark = "[Ok]" if it["ok"] else "[No]"
            lines.append("  %s %-22s %s" % (mark, it["label"], it["desc"]))
            if it["detail"]:
                lines.append("        (%s)" % it["detail"])
        if ev.get("vs30") is not None:
            lines.append("  Vs30 estimate : %.0f m/s -> NEHRP class %s"
                         % (ev["vs30"], ev["soil_class"]))
            lines.append("  %s (%s)"
                         % (ev["soil_desc"], ev["soil_class"]))
        if ev.get("thickness") is not None:
            lines.append("  Sediment depth h (from f0): %.1f m"
                         % ev["thickness"])
        lines.append("  VERDICT: %s" % ev["verdict"])
    return "\n".join(lines)
