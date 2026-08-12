"""
hvsr_gui_pump.py
================
UI-thread message pump and result pipeline for the HVSR Analyzer GUI.

Worker threads never touch widgets directly: they post (kind, payload)
tuples on a queue.Queue and HVSRAppPumpMixin._poll_queue() - scheduled every
120 ms by ``after`` - dispatches them on the UI thread (log lines, finished
analyses, previews, progress, errors) into every chart and tab.  The
status / progress strip and theme services live in hvsr_gui_core.py.
"""

import os
import queue
from tkinter import messagebox

try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False


class HVSRAppPumpMixin:

    def _on_done(self, res, clean, station, geo_freqs, geo_amps, opts, out_dir):
        """UI-thread handler when a background analysis finishes: push the
        results into every chart and tab, render the checklist, write the
        report, and (if requested) prompt for save locations / log the run."""
        self._last = (res, clean, station, geo_freqs, geo_amps)
        self._curve.set_data(res.freqs, res.mean, res.low, res.high,
                             res.f0, res.a0, station=station,
                             extra=geo_amps, extra_label="GEOPSY X-CHECK")
        self._ts.set_data([("Z", clean.z), ("N", clean.n), ("E", clean.e)], clean.fs, res.window_len)
        self._redraw_spectra()
        self._inv_hist.set_data((None, []))
        self._set_sesame(res.sesame)
        self._last_evals = res.standards if _HAVE_STANDARDS else {}
        if self._last_evals:
            std_id = self._std_map.get(self._vars["std"].get(), "sesame")
            self._render_standard(std_id)
        self._report.delete("1.0", "end")
        self._report.insert("1.0", res.report_text)
        self._log_line("f0 = %.3f Hz | A0 = %.2f | Kg = %.2f (%s)" % (res.f0, res.a0, res.kg, res.kg_level))
        if getattr(res, "sesame_score", None) is not None:
            self._log_line("RELIABILITY SCORE: %d/6" % res.sesame_score)

        if opts.get("ask"):
            self._ask_saves(res, clean, station, opts)
        if opts.get("log"):
            try:
                self._append_data_log(res, clean, station, clean.source_name, out_dir)
                self._log_line("DATA LOG UPDATED: " + os.path.join(out_dir, "data_log.csv"))
            except Exception as exc:
                self._log_line("DATA LOG ERR: %s" % exc)
        self._set_status("SEQUENCE COMPLETE - f0 = %.3f Hz, A0 = %.2f" % (res.f0, res.a0), busy=False)

    def _redraw_spectra(self):
        if not self._last:
            return
        res = self._last[0]
        sp = getattr(res, "spectra", None)
        if not sp or not sp.get("freqs"):
            self._spec.set_data([], {}, mode="PSD", station="")
            return
        mode = self._vars["spec_mode"].get()
        curves = sp.get("psd") if mode == "PSD" else sp.get("spec")
        self._spec.set_data(sp["freqs"], curves, mode=mode, station=res.station)

    def _redraw_sig(self):
        payload = getattr(self, "_sig_payload", None)
        if not payload:
            return
        sp, zn, ze, ne = payload
        mode = self._vars["sig_mode"].get()
        if mode == "Spectrum":
            self._sig.set_data(sp["freqs"], sp["spec"], mode="Spectrum", station="")
        elif mode == "Coherence":
            f = zn[0]
            self._sig.set_data(f, {"z": zn[1], "n": ze[1], "e": ne[1]}, mode="Coherence", station="", labels=("Z-N", "Z-E", "N-E"))
        else:
            self._sig.set_data(sp["freqs"], sp["psd"], mode="PSD", station="")

    def _apply_hv_views(self, res, sp, tf, az):
        times, freqs, tf_grid = tf
        azi, afreqs, az_grid = az
        self._tf.set_data(times, freqs, tf_grid, title="H/V VS TIME", ylabel="TIME (s)")
        self._az.set_data(azi, afreqs, az_grid, title="H/V VS AZIMUTH", ylabel="AZIMUTH (deg)")
        self._avg_spec.set_data(sp["freqs"], sp["psd"], mode="PSD", station=res.station)
        self._avg_hv.set_data(res.freqs, res.mean, res.low, res.high, res.f0, res.a0, station=res.station)

    def _poll_queue(self):
        """UI-thread message pump, scheduled every 120 ms by ``after``.

        Worker threads never touch widgets directly - they post (kind,
        payload) tuples here and this method dispatches them (log lines,
        done results, previews, progress, errors).
        """
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._log_line(payload)
                elif kind == "done":
                    self._on_done(*payload)
                elif kind == "set_params":
                    for key, val in payload.items():
                        self._set_param(key, val)
                    self._log_line("TUNED PARAMETERS APPLIED.")
                elif kind == "preview":
                    data, err = payload
                    if data is not None:
                        self._preview.set_data([("Z", data.z), ("N", data.n), ("E", data.e)], data.fs)
                        self._log_line("WAVEFORM PREVIEW ACTIVE: %.1f s @ %.1f Hz (%s)" % (data.duration, data.fs, data.source_name))
                    elif err:
                        self._preview.set_data([], 1.0)
                        self._log_line("PREVIEW ERR: " + err)
                elif kind == "sig":
                    payload, err = payload
                    if payload is not None:
                        self._sig_payload = payload
                        self._redraw_sig()
                        self._log_line("SIGNAL ANALYSIS COMPLETE")
                    elif err:
                        self._log_line("SIGNAL ANALYSIS ERR: " + err)
                    self._set_status("SIGNAL ANALYSIS COMPLETE.", busy=False)
                elif kind == "filt":
                    clean, win, meta, err = payload
                    if clean is not None:
                        self._filt.set_data([("Z", clean.z), ("N", clean.n), ("E", clean.e)], clean.fs, win)
                        self._log_line("FILTERED PREVIEW ACTIVE: %.1f s @ %.1f Hz (MUTED %d, DEC x%d)" % (clean.duration, clean.fs, meta.get("muted", 0), meta.get("dec_factor", 1)))
                    elif err:
                        self._log_line("FILTERED PREVIEW ERR: " + err)
                    self._set_status("FILTERED PREVIEW COMPLETE.", busy=False)
                elif kind == "hv":
                    payload, err = payload
                    if payload is not None:
                        self._apply_hv_views(*payload)
                        self._log_line("H/V VIEWS GENERATED.")
                        if not getattr(self._tf, "grid", None):
                            self._log_line("H/V VIEWS WARN: INVALID WINDOWS")
                    elif err:
                        self._log_line("H/V VIEWS ERR: " + err)
                    self._set_status("H/V VIEWS COMPLETE.", busy=False)
                elif kind == "progress":
                    self._set_progress(*payload)
                elif kind == "inv_done":
                    self._on_inversion_done(payload)
                elif kind == "error":
                    self._set_status("SYSTEM ERROR", busy=False)
                    messagebox.showerror("Analysis error", payload)
                    self._log_line("ERROR: " + payload)
                elif kind == "idle":
                    self._set_status("BATCH SEQUENCE COMPLETE.", busy=False)
                    # the batch worker is the only "idle" producer - beep +
                    # flash the taskbar so a finished batch is noticed
                    self._notify_done()
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

