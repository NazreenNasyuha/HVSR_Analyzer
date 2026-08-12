"""
hvsr_gui_previews.py
====================
Live-preview and folder-batch workers for the HVSR Analyzer GUI.

HVSRAppPreviewsMixin: the daemon-thread workers behind the live previews
(waveform, filtered signal, spectra / coherence, H/V time & azimuth maps)
plus the batch sweep over a whole station folder (_batch_worker).  They
post (kind, payload) tuples to ``self._queue`` for the pump in
hvsr_gui_pump.py; the single-station analysis pipeline lives in
hvsr_gui_workers.py (HVSRAppWorkersMixin).
"""

import os

from hvsr_engine import (preprocess, analyze, compute_spectra, coherence,
                         hv_vs_time, hv_vs_azimuth, trim_seconds,
                         log_frequencies)
from hvsr_io import auto_load


class HVSRAppPreviewsMixin:

    def _preview_worker(self, files, explicit, swap_h):
        try:
            data = auto_load(files, explicit, swap_h=swap_h)
        except Exception as exc:
            self._queue.put(("preview", (None, str(exc))))
            return
        self._queue.put(("preview", (data, None)))

    def _preview_data(self, data, max_sec=120.0):
        if data.duration > max_sec:
            return trim_seconds(data, 0.0, max_sec)
        return data

    def _sig_worker(self, files, explicit, swap_h):
        try:
            data = self._preview_data(auto_load(files, explicit, swap_h=swap_h))
            w_len = min(30.0, max(5.0, data.duration / 3.0))
            sp = compute_spectra(data, w_len, overlap=0.0, taper=0.05, fmin=0.1, fmax=40.0)
            f_zn, c_zn = coherence(data.z, data.n, data.fs, w_len)
            f_ze, c_ze = coherence(data.z, data.e, data.fs, w_len)
            f_ne, c_ne = coherence(data.n, data.e, data.fs, w_len)
            payload = (sp, (f_zn, c_zn), (f_ze, c_ze), (f_ne, c_ne))
            self._queue.put(("sig", (payload, None)))
        except Exception as exc:
            self._queue.put(("sig", (None, str(exc))))

    def _filt_worker(self, files, explicit, swap_h, p, win):
        try:
            data = self._preview_data(auto_load(files, explicit, swap_h=swap_h))
            p = self._fill_defaults(p)
            clean, meta = preprocess(
                data, f_low=p["f_low"], f_high=p["f_high"],
                mute=p["mute"], sta_sec=p["sta_sec"], lta_sec=p["lta_sec"],
                slta_threshold=p["slta_threshold"],
                max_fs=p["max_fs"] if p["decimate"] else None)
            self._queue.put(("filt", (clean, win, meta, None)))
        except Exception as exc:
            self._queue.put(("filt", (None, 0.0, {}, str(exc))))

    def _hv_worker(self, files, explicit, swap_h, p):
        try:
            data = self._preview_data(auto_load(files, explicit, swap_h=swap_h))
            p = self._fill_defaults(p)
            clean, meta = preprocess(
                data, f_low=p["f_low"], f_high=p["f_high"],
                mute=p["mute"], sta_sec=p["sta_sec"], lta_sec=p["lta_sec"],
                slta_threshold=p["slta_threshold"],
                max_fs=p["max_fs"] if p["decimate"] else None)
            w_used = p["win_len"] or 30.0
            sp = compute_spectra(clean, w_used, overlap=p["overlap"], taper=p["taper"], fmin=0.1, fmax=40.0)
            map_freqs = log_frequencies(0.1, 40.0, 96)
            times, freqs, tf_grid = hv_vs_time(
                clean, w_used, overlap=p["overlap"], taper=p["taper"],
                freqs=map_freqs, b_value=p["b_value"], combo=p["combo"],
                smoothing=p["smoothing"], smooth_width=p["smooth_width"])
            azi, afreqs, az_grid = hv_vs_azimuth(
                clean, w_used, overlap=p["overlap"], taper=p["taper"],
                freqs=map_freqs, b_value=p["b_value"], combo=p["combo"],
                smoothing=p["smoothing"], smooth_width=p["smooth_width"])
            res = analyze(clean, w_len=w_used, overlap=p["overlap"], rejection=p["rejection"], fmin=p["fmin"], fmax=p["fmax"], nfreq=p["nfreq"], b_value=p["b_value"], combo=p["combo"], taper=p["taper"], max_iterations=p["max_iterations"], smoothing=p["smoothing"], smooth_width=p["smooth_width"], station=self._station_name(data))
            payload = (res, sp, (times, freqs, tf_grid), (azi, afreqs, az_grid))
            self._queue.put(("hv", (payload, None)))
        except Exception as exc:
            self._queue.put(("hv", (None, str(exc))))

    def _batch_worker(self, folder, p, autotune, opts, out_dir, swap_h):
        """Loop over every station subfolder of ``folder``: discover the
        signal files, run the same per-station pipeline as a single run,
        save the enabled outputs and log each result with a progress tick.
        """
        import glob as gl
        try:
            pats = []
            for ext in ("*.mseed", "*.miniseed", "*.eqd", "*.sg2", "*.csv", "*.txt", "*.dat", "*.asc", "*.tsv", "*.sac"):
                pats += gl.glob(os.path.join(folder, "**", ext), recursive=True)
            stations = {}
            single_eqd = {}
            for path in pats:
                parent = os.path.basename(os.path.dirname(path))
                if parent.lower() in ("sample_data",):
                    continue
                if path.lower().endswith((".eqd", ".sg2")):
                    single_eqd.setdefault(parent, path)
                else:
                    stations.setdefault(parent, []).append(path)
            done = 0
            failed = 0
            total = len(stations) + len(single_eqd)
            for name, files in sorted(stations.items()):
                try:
                    data = auto_load(files, swap_h=swap_h)
                    if p.get("t0") is not None or p.get("t1") is not None:
                        data = trim_seconds(data, p.get("t0"), p.get("t1"))
                    p_run = self._resolve_auto(p, data.fs)
                    p_run = self._fill_defaults(p_run)
                    clean, meta = preprocess(
                        data, f_low=p_run["f_low"], f_high=p_run["f_high"],
                        mute=p_run["mute"], sta_sec=p_run["sta_sec"], lta_sec=p_run["lta_sec"],
                        slta_threshold=p_run["slta_threshold"],
                        max_fs=p_run["max_fs"] if p_run["decimate"] else None)
                    res, _w, _r = self._analyze_one(clean, name, p_run, autotune)
                    if p_run.get("do_psd") or p_run.get("do_spec"):
                        res.spectra = compute_spectra(clean, _w, overlap=p_run["overlap"], taper=p_run["taper"], fmin=0.1, fmax=40.0)
                    res.rejection = _r
                    res.f_low = p_run["f_low"]
                    res.f_high = p_run["f_high"]
                    self._save_outputs(res, clean, name, out_dir, opts)
                    if opts.get("log"):
                        self._append_data_log(res, clean, name, data.source_name, out_dir)
                    done += 1
                    self._queue.put(("log", "[%d] %s: f0=%.3f Hz A0=%.2f" % (done, name, res.f0, res.a0)))
                    self._queue.put(("progress", (done + failed, total, "BATCH")))
                except Exception as exc:
                    failed += 1
                    self._queue.put(("log", "[!] %s: %s" % (name, exc)))
                    self._queue.put(("progress", (done + failed, total, "BATCH")))
            for name, path in sorted(single_eqd.items()):
                try:
                    data = auto_load([path], swap_h=swap_h)
                    p_run = self._resolve_auto(p, data.fs)
                    p_run = self._fill_defaults(p_run)
                    clean, meta = preprocess(
                        data, f_low=p_run["f_low"], f_high=p_run["f_high"],
                        mute=p_run["mute"], sta_sec=p_run["sta_sec"], lta_sec=p_run["lta_sec"],
                        slta_threshold=p_run["slta_threshold"],
                        max_fs=p_run["max_fs"] if p_run["decimate"] else None)
                    res, _w, _r = self._analyze_one(clean, name, p_run, autotune)
                    if p_run.get("do_psd") or p_run.get("do_spec"):
                        res.spectra = compute_spectra(clean, _w, overlap=p_run["overlap"], taper=p_run["taper"], fmin=0.1, fmax=40.0)
                    res.rejection = _r
                    res.f_low = p_run["f_low"]
                    res.f_high = p_run["f_high"]
                    self._save_outputs(res, clean, name, out_dir, opts)
                    if opts.get("log"):
                        self._append_data_log(res, clean, name, data.source_name, out_dir)
                    done += 1
                    self._queue.put(("log", "[%d] %s (%s): f0=%.3f Hz A0=%.2f" % (done, name, os.path.splitext(path)[1], res.f0, res.a0)))
                    self._queue.put(("progress", (done + failed, total, "BATCH")))
                except Exception as exc:
                    failed += 1
                    self._queue.put(("log", "[!] %s (%s): %s" % (name, os.path.splitext(path)[1], exc)))
                    self._queue.put(("progress", (done + failed, total, "BATCH")))
            self._queue.put(("log", "BATCH COMPLETE: %d OK, %d FAILED" % (done, failed)))
            self._queue.put(("idle", None))
        except Exception as exc:
            self._queue.put(("error", str(exc)))
