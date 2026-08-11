"""
hvsr_standards.py
=================
Global HVSR (microtremor H/V) method guidelines and regional standards.

This module lets the same H/V result be checked against the *official*
procedures used in different parts of the world, so one recording can be
verified following the method of the country that will receive the report:

  * SESAME 2004 (Europe) ......... the European guideline from the SESAME
                                   project (Bard & SESAME Team, 2004) -
                                   full 7-criterion reliability matrix.
  * Japan J-SHIS / JAMC ......... the Japanese microtremor survey guideline
                                   (JAMC, "Shin-jishin..." / NIED J-SHIS
                                   practice): 30-60 s windows, >=10 windows,
                                   0.2-20 Hz range, clear-peak criteria and
                                   a Vs30 estimate from f0.
  * USGS / NEHRP ............... American practice: peak clarity + NEHRP
                                   site-class (Vs30-based) assignment.
  * Generic / industry .......... a portable best-practice checklist
                                   (used by Geometrics and most surveyors).

Each standard contributes:
  - recommended processing parameters (window length, rejection, range),
  - a pass/fail checklist computed from the analysed curve,
  - empirical estimates of sediment thickness h and Vs30 from f0 (with
    published relations whose constants are user-adjustable).

Empirical relations implemented (thickness h [m] from f0 [Hz]):
  * Ibs-von Seht & Wohlenberg (1999), Germany:  h = 96.0 * f0^-1.388
  * Delgado et al. (2000), SE Spain:             h = 55.0 * f0^-1.214
  * Parolai et al. (2002), Cologne:              h = 108.0 * f0^-1.551
  * D'Amico et al. (2008), Italy:                h = 121.3 * f0^-1.217
  * Birgören et al. (2009), Istanbul:            h = 66.7 * f0^-1.092

Vs30 is estimated two ways:
  1. from a published power law Vs30 = a * f0^b (constants adjustable),
  2. from the estimated thickness and an assumed average shear velocity
     of the sedimentary column (Vs_avg default 300 m/s) when the depth is
     >= 30 m, otherwise mixing Vs_avg with a bedrock velocity (Vs_bedrock
     default 800 m/s) for the remaining depth to 30 m.

All processing stays pure standard library.
"""

import math

# ----------------------------------------------------------------------
# Empirical relations: sediment thickness h (m) from f0 (Hz)
# ----------------------------------------------------------------------
# name -> (a, b, region, citation)
THICKNESS_RELATIONS = {
    "Ibs-von Seht & Wohlenberg (1999)": (
        96.0, -1.388, "Germany (Rhine area)",
        "Ibs-von Seht, M. & Wohlenberg, J. (1999). Microtremor measurements "
        "used to map thickness of soft sediments. Bull. Seism. Soc. Am. 89."),
    "Delgado et al. (2000)": (
        55.0, -1.214, "SE Spain (alluvial basins)",
        "Delgado, J. et al. (2000). Microtremors as a geophysical "
        "exploration tool. J. Applied Geophysics."),
    "Parolai et al. (2002)": (
        108.0, -1.551, "Cologne, Germany",
        "Parolai, S., Bormann, P. & Milkereit, C. (2002). New relationships "
        "between Vs, thickness of sediments, and resonance frequency. "
        "Bull. Seism. Soc. Am. 92."),
    "D'Amico et al. (2008)": (
        121.3, -1.217, "Italy",
        "D'Amico, V., Picozzi, M., et al. (2008). Quick estimates of soft "
        "sediment thickness from ambient noise H/V. Boll. Geofis. Teor. "
        "Appl. 49."),
    "Birgören et al. (2009)": (
        66.7, -1.092, "Istanbul, Turkey",
        "Birgören, G., Özel, O. & Siyahi, B. (2009). Bedrock depth mapping "
        "of the coast south of Istanbul by ambient noise. Geophys. J. Int."),
}

DEFAULT_THICKNESS_RELATION = "Ibs-von Seht & Wohlenberg (1999)"

# Vs30 power law defaults: Vs30 = a * f0^b
# (a "typical" soft-soil calibration; edit for local geology)
DEFAULT_VS30_A = 38.0
DEFAULT_VS30_B = 0.997
VS30_RELATION_CITATION = (
    "Vs30 = a * f0^b power law, e.g. the calibration used in Italian "
    "soft-soil studies (Vs30 = 38 * f0^0.997); constants are site-specific "
    "and can be adjusted in the GUI.")

# Average shear velocity of the sedimentary column / bedrock for the
# thickness-based Vs30 estimate.
DEFAULT_VS_AVG = 300.0     # m/s
DEFAULT_VS_BEDROCK = 800.0  # m/s


def estimate_thickness(f0, relation=DEFAULT_THICKNESS_RELATION):
    """Sediment thickness h (m) from f0 using a published relation."""
    if f0 <= 0:
        return None
    a, b, region, citation = THICKNESS_RELATIONS[relation]
    return max(a * (f0 ** b), 0.0)


def estimate_vs30_powerlaw(f0, a=DEFAULT_VS30_A, b=DEFAULT_VS30_B):
    """Vs30 from f0 using Vs30 = a * f0^b."""
    if f0 <= 0:
        return None
    return a * (f0 ** b)


def estimate_vs30_from_thickness(f0, relation=DEFAULT_THICKNESS_RELATION,
                                 vs_avg=DEFAULT_VS_AVG,
                                 vs_bedrock=DEFAULT_VS_BEDROCK):
    """Vs30 from the estimated sediment thickness and assumed velocities.

    If the sediment column is >= 30 m deep the whole 30 m profile is soft
    sediment (Vs ~ Vs_avg).  If it is thinner, the remaining depth down to
    30 m is assumed to be bedrock (Vs ~ Vs_bedrock).
    """
    h = estimate_thickness(f0, relation)
    if h is None:
        return None
    if h >= 30.0:
        return vs_avg
    if h <= 0.0:
        return None
    return (vs_avg * h + vs_bedrock * (30.0 - h)) / 30.0


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


# ----------------------------------------------------------------------
# Standard definitions
# ----------------------------------------------------------------------
STANDARDS = {
    "sesame": {
        "id": "sesame",
        "name": "SESAME 2004 (Europe)",
        "region": "Europe / international",
        "source": "SESAME Project, 2004 - 'Guidelines for the "
                  "implementation of the H/V spectral ratio technique on "
                  "ambient vibrations' (Bard & SESAME Team).",
        "params": {"win_len": 30.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Full 7-criterion reliability matrix (curve + peak). "
                   "Reliable when the curve and peak criteria all pass.",
    },
    "japan": {
        "id": "japan",
        "name": "Japan (J-SHIS / JAMC)",
        "region": "Japan",
        "source": "Japanese microtremor survey guideline (JAMC) and NIED "
                  "J-SHIS practice: 30-60 s windows, >= 10 windows, "
                  "0.2-20 Hz analysis range, clear-peak criteria, Vs30 "
                  "estimate from f0.",
        "params": {"win_len": 60.0, "rejection": 2.0, "fmin": 0.2,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Requires a clear f0 in the 0.2-20 Hz band, at least 10 "
                   "windows and a stable peak; reports Vs30 and NEHRP "
                   "site class.",
    },
    "indonesia": {
        "id": "indonesia",
        "name": "Indonesia (SNI 1726-2019 / BMKG)",
        "region": "Indonesia",
        "source": "SNI 1726-2019 site classes (SA-SF, Vs30 thresholds "
                  "1500/750/350/175 m/s) applied to the HVSR result; H/V "
                  "processing follows the SESAME 2004 criteria as used in "
                  "Indonesian microzonation studies (BMKG practice).",
        "params": {"win_len": 30.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "SESAME-style reliability checks plus the SNI 1726-2019 "
                   "Vs30 site class (SA-SF) used by the Indonesian seismic "
                   "code.",
    },
    "usgs": {
        "id": "usgs",
        "name": "USGS / NEHRP",
        "region": "United States",
        "source": "NEHRP site classification (Vs30-based, NEHRP 2003 / "
                  "ASCE 7) applied to the HVSR result; peak-clarity "
                  "practice per USGS microtremor studies.",
        "params": {"win_len": 30.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Assigns the NEHRP site class (A-E) from the Vs30 "
                   "estimate and checks peak clarity.",
    },
    "generic": {
        "id": "generic",
        "name": "Generic / Industry",
        "region": "portable",
        "source": "Common surveyor practice (e.g. Geometrics H/V "
                  "guidelines): >= 10 windows, clear peak A0 > 2, f0 in "
                  "range, stable f0 across windows.",
        "params": {"win_len": 40.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Portable best-practice checklist that works for any "
                   "region.",
    },
}

DEFAULT_STANDARD = "sesame"


def recommended_params(standard_id=DEFAULT_STANDARD):
    """Recommended processing parameters for a standard."""
    return dict(STANDARDS[standard_id]["params"])


# ----------------------------------------------------------------------
# Checklist evaluation
# ----------------------------------------------------------------------
def _check(key, label, desc, ok, detail=""):
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
