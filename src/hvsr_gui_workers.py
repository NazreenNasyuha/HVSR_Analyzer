"""
hvsr_gui_workers.py
===================
The single-station analysis pipeline for the HVSR Analyzer GUI.

HVSRAppWorkersMixin: the daemon-thread analysis worker (_worker) and the
analysis dispatch (_analyze_one).  It posts (kind, payload) tuples to
``self._queue``; the queue pump lives in hvsr_gui_pump.py.  The shared
parameter fallbacks / Auto-mode recommendations / station-naming helpers
moved to hvsr_gui_workhelpers.py (HVSRAppWorkHelpersMixin); the preview /
batch workers moved to hvsr_gui_previews.py (HVSRAppPreviewsMixin).
"""


import os

import hvsr_geopsy
from hvsr_engine import (preprocess, analyze, auto_tune, compute_spectra, trim_seconds)
from hvsr_io import DataError, auto_load


class HVSRAppWorkersMixin:
    def _worker(self, files, explicit, swap_h, p, pz_path, geo, autotune,
                full_autotune, opts, out_dir):
        """Run one full analysis on a background thread (daemon).

        Loads -> trims -> resolves auto params -> preprocesses -> analyzes
        (with optional auto-tune and Geopsy cross-check) -> saves outputs,
        then posts a ("done", ...) or ("error", ...) message to the queue
        for the UI thread to consume.
        """
        try:
            data = auto_load(files, explicit, swap_h=swap_h)
            if p.get("t0") is not None or p.get("t1") is not None:
                t0, t1 = p.get("t0"), p.get("t1")
                if t0 is not None and t0 < 0:
                    raise DataError("START TIME MUST BE >= 0")
                if t0 is not None and t1 is not None and t1 <= t0:
                    raise DataError("END TIME MUST SUCCEED START TIME")
                data = trim_seconds(data, t0, t1)
                self._queue.put(("log", "TIME RANGE: %.2f - %.2f s (%.1f s DATA USED)" % (t0 or 0.0, t1 or data.duration, data.duration)))
            else:
                self._queue.put(("log", "RECORDING LENGTH: %.1f s" % data.duration))

            p = self._resolve_auto(p, data.fs)
            p = self._fill_defaults(p)
            pz = None
            if pz_path and os.path.exists(pz_path):
                with open(pz_path, "r", encoding="utf-8", errors="replace") as fh:
                    from hvsr_dsp import parse_paz
                    pz = parse_paz(fh.read())
            elif pz_path:
                self._queue.put(("log", "WARN: RESPONSE FILE NOT FOUND. SKIPPING."))

            clean, meta = preprocess(data, f_low=p["f_low"], f_high=p["f_high"],
                                     paz=pz, mute=p["mute"],
                                     sta_sec=p["sta_sec"], lta_sec=p["lta_sec"],
                                     slta_threshold=p["slta_threshold"],
                                     max_fs=p["max_fs"] if p["decimate"] else None)
            self._queue.put(("log", "PRE-PROC: MUTED %d SAMPLES, DECIMATION x%d" % (meta["muted"], meta["dec_factor"])))

            station = self._station_name(data)
            res, w_used, r_used = self._analyze_one(clean, station, p, autotune, full_autotune)

            if p.get("do_psd") or p.get("do_spec"):
                res.spectra = compute_spectra(
                    clean, w_used, overlap=p["overlap"], taper=p["taper"],
                    fmin=0.1, fmax=40.0)

            geo_freqs = geo_amps = None
            geo_enable, geo_path = geo
            if geo_enable and geo_path:
                geo_freqs, geo_amps, glog = hvsr_geopsy.run_geopsy_hv(
                    geo_path, clean, out_dir, w_used, r_used,
                    p["fmin"], p["fmax"], p["nfreq"], station,
                    b_value=p["b_value"], combo=p["combo"])
                for line in glog:
                    self._queue.put(("log", line))

            res.rejection = r_used
            res.f_low = p["f_low"]
            res.f_high = p["f_high"]
            self._save_outputs(res, clean, station, out_dir, opts)
            self._queue.put(("done", (res, clean, station, geo_freqs, geo_amps, opts, out_dir)))
        except Exception as exc:
            self._queue.put(("error", str(exc)))

    def _analyze_one(self, clean, station, p, autotune, full_autotune=False):
        """Dispatch the analysis to the right engine call.

        Three paths: the full max-reliability sweep (all smoothing / width /
        combo combinations), the quick SESAME auto-tune (window + rejection),
        or a plain manual run with the parameters as entered.
        """
        if full_autotune:
            res, w, r = auto_tune(clean, fmin=p["fmin"], fmax=p["fmax"],
                                  nfreq=p["nfreq"], overlap=p["overlap"],
                                  taper=p["taper"],
                                  max_iterations=p["max_iterations"],
                                  station=station, full=True,
                                  n_workers=self._parallel_workers(),
                                  progress_cb=lambda d, t: self._queue.put(
                                      ("progress", (d, t, "MAX RELIABILITY"))))
            tuned = getattr(res, "tuned", {})
            self._queue.put(("log", "MAX RELIABILITY TUNING: W=%gs REJ=%g SM=%s WIDTH=%s COMBO=%s -> SCORE %d/6" % (w, r, tuned.get("smoothing"), tuned.get("smooth_width"), tuned.get("combo"), getattr(res, "sesame_score", 0))))
            self._queue.put(("set_params", tuned))
            return res, w, r
        if autotune or p.get("win_len") is None or p.get("rejection") is None:
            res, w, r = auto_tune(clean, fmin=p["fmin"], fmax=p["fmax"],
                                  nfreq=p["nfreq"], b_value=p["b_value"],
                                  combo=p["combo"], overlap=p["overlap"],
                                  taper=p["taper"],
                                  smoothing=p.get("smoothing", "konno_ohmachi"),
                                  smooth_width=p.get("smooth_width", 40.0),
                                  max_iterations=p["max_iterations"],
                                  station=station)
            self._queue.put(("log", "AUTO-TUNE: WINDOW=%gs REJECTION=%g" % (w, r)))
            return res, w, r
        res = analyze(clean, w_len=p["win_len"], overlap=p["overlap"],
                      rejection=p["rejection"], fmin=p["fmin"], fmax=p["fmax"],
                      nfreq=p["nfreq"], b_value=p["b_value"], combo=p["combo"],
                      taper=p["taper"], max_iterations=p["max_iterations"],
                      smoothing=p.get("smoothing", "konno_ohmachi"),
                      smooth_width=p.get("smooth_width", 40.0),
                      station=station)
        return res, p["win_len"], p["rejection"]
