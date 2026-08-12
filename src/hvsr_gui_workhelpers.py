"""
hvsr_gui_workhelpers.py
=======================
Shared helpers for the HVSR Analyzer GUI's analysis worker: _fill_defaults
applies PARAM_DEFAULTS to any parameter left empty, _resolve_auto fills
every field from the selected guideline standard in Auto mode, and
_station_name derives the output-file base name from the source file.
The pipeline that calls them lives in hvsr_gui_workers.py.  Mixed into
HVSRApp as HVSRAppWorkHelpersMixin.
"""


import hvsr_standards  # used by _resolve_auto (Auto parameter mode)


# Fallbacks applied to any parameter left empty / unresolved by Auto mode.
PARAM_DEFAULTS = {
    "f_low": 0.2, "f_high": 20.0, "win_len": 30.0, "rejection": 1.5,
    "fmin": 0.5, "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
    "overlap": 0.0, "taper": 0.05, "max_iterations": 50,
    "sta_sec": 1.0, "lta_sec": 30.0, "slta_threshold": 2.5,
    "max_fs": 250.0, "smoothing": "konno_ohmachi", "smooth_width": 40.0,
}


class HVSRAppWorkHelpersMixin:
    def _fill_defaults(self, p):
        for key, val in PARAM_DEFAULTS.items():
            if p.get(key) is None:
                p[key] = val
        return p

    def _resolve_auto(self, p, fs):
        """Fill every parameter from the selected guideline standard when the
        user picked Auto mode.  The window length and rejection are left
        None so the engine auto-tunes them from the data."""
        if p.get("mode") != "auto":
            return p
        p = dict(p)
        fs = fs or 100.0
        std_id = p.get("std_id", "sesame")
        rec = hvsr_standards.recommended_params(std_id)
        p["f_low"] = rec.get("f_low", 0.2)
        p["f_high"] = min(rec.get("f_high", 20.0), max(1.0, fs / 4.0))
        p["win_len"] = None      
        p["rejection"] = None    
        p["fmin"] = rec["fmin"]
        p["fmax"] = min(rec["fmax"], max(2.0, fs / 2.0))
        p["nfreq"] = rec.get("nfreq", 512)
        p["b_value"] = rec.get("b_value", 40.0)
        p["taper"] = rec.get("taper", 0.05)
        p["smoothing"] = rec.get("smoothing", "konno_ohmachi")
        p["smooth_width"] = rec.get("smooth_width", 40.0)
        p["max_iterations"] = rec.get("max_iterations", 50)
        p["sta_sec"] = rec.get("sta_sec", 1.0)
        p["lta_sec"] = rec.get("lta_sec", 30.0)
        p["slta_threshold"] = rec.get("slta_threshold", 2.5)
        p["max_fs"] = rec.get("max_fs", 250.0)
        self._queue.put(("log", "AUTO MODE (%s): BP %.1f-%.1f Hz, fmin %.1f Hz, KO b=%.0f" % (std_id, p["f_low"], p["f_high"], p["fmin"], p["b_value"])))
        return p

    def _station_name(self, data):
        """Derive the output-file base name from the source file name,
        stripping any known extension."""
        base = data.source_name or "STATION"
        for ext in (".csv", ".txt", ".dat", ".asc", ".tsv", ".sac", ".mseed", ".miniseed", ".eqd", ".sg2"):
            if base.lower().endswith(ext):
                base = base[: -len(ext)]
                break
        return base or "STATION"
