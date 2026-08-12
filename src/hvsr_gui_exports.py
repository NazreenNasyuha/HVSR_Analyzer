"""
hvsr_gui_exports.py
===================
File savers for the HVSR Analyzer GUI: reports, inversion-target files
and chart PNGs - both the button-triggered exporters and the Save
Protocol auto-writers - plus the spectra / data CSVs and the ask-user
save dialogs.  The parameter profiles and the batch data-log moved to
hvsr_gui_profiles.py.  Mixed into HVSRApp as HVSRAppExportsMixin.
"""


import os
from tkinter import filedialog

from hvsr_engine import write_report_file, write_target_file


class HVSRAppExportsMixin:
    def _save_outputs(self, res, clean, station, out_dir, opts=None):
        """Write the requested result files (report / target / PNG / CSV)
        into out_dir without asking, based on the Save Protocol toggles."""
        opts = opts or {}
        out = out_dir
        if opts.get("report", True):
            write_report_file(os.path.join(out, station + "_report.txt"), res)
        if opts.get("target", True):
            write_target_file(os.path.join(out, station + "_inversion.target"),
                              res.freqs, res.mean, res.low, res.high, res.f0)
        if opts.get("png", True):
            try:
                from chart_render import HvsrChart
                chart = HvsrChart()
                chart.draw_hvsr(res.freqs, res.mean, res.low, res.high,
                                res.f0, res.a0, station=station,
                                fmin=res.freqs[0], fmax=res.freqs[-1])
                chart.save_png(os.path.join(out, station + "_HVSR.png"))
            except Exception:
                pass
        if opts.get("csv", True):
            try:
                self._write_data_csv(os.path.join(out, station + "_data.csv"), clean, res)
            except Exception:
                pass
        if getattr(res, "spectra", None) and opts.get("csv", True):
            try:
                self._write_spectra_csv(os.path.join(out, station + "_spectra.csv"), res)
            except Exception:
                pass
        self._queue.put(("log", "RESULTS EXPORTED TO " + out))

    def _write_spectra_csv(self, path, res):
        sp = res.spectra
        freqs = sp.get("freqs") or []
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("freq_Hz,psd_z_db,psd_n_db,psd_e_db,spec_z,spec_n,spec_e\n")
            psd, spec = sp.get("psd", {}), sp.get("spec", {})
            for i, f in enumerate(freqs):
                fh.write("%.6f,%.4f,%.4f,%.4f,%.6g,%.6g,%.6g\n" % (f, psd["z"][i], psd["n"][i], psd["e"][i], spec["z"][i], spec["n"][i], spec["e"][i]))

    def _write_data_csv(self, path, clean, res):
        n = min(len(clean.z), len(clean.n), len(clean.e))
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("time_s,Z,N,E,freq_Hz,HV\n")
            dt = 1.0 / clean.fs
            freqs = res.freqs
            means = res.mean
            nf = len(freqs)
            for i in range(n):
                fv = freqs[i] if i < nf else ""
                hv = means[i] if i < nf else ""
                fh.write("%.6f,%.8g,%.8g,%.8g,%s,%s\n" % (i * dt, clean.z[i], clean.n[i], clean.e[i], fv, hv))

    def _ask_saves(self, res, clean, station, opts):
        if opts.get("png"):
            png = filedialog.asksaveasfilename(
                title="Save chart PNG for " + station,
                initialfile=station + "_HVSR.png", defaultextension=".png",
                filetypes=[("PNG image", "*.png")])
            if png:
                try:
                    from chart_render import HvsrChart
                    chart = HvsrChart()
                    chart.draw_hvsr(res.freqs, res.mean, res.low, res.high,
                                    res.f0, res.a0, station=station,
                                    fmin=res.freqs[0], fmax=res.freqs[-1])
                    chart.save_png(png)
                    self._log_line("CHART SAVED TO " + png)
                except Exception as exc:
                    self._log_line("CHART SAVE ERR: %s" % exc)
        if opts.get("report"):
            rep = filedialog.asksaveasfilename(
                title="Save report for " + station,
                initialfile=station + "_report.txt", defaultextension=".txt",
                filetypes=[("Text", "*.txt")])
            if rep:
                write_report_file(rep, res)
                self._log_line("REPORT SAVED TO " + rep)
        if opts.get("target"):
            tgt = filedialog.asksaveasfilename(
                title="Save inversion target for " + station,
                initialfile=station + "_inversion.target",
                defaultextension=".target",
                filetypes=[("Target file", "*.target")])
            if tgt:
                write_target_file(tgt, res.freqs, res.mean, res.low, res.high, res.f0)
                self._log_line("TARGET SAVED TO " + tgt)

    def _export_spectra_png(self):
        if not self._last:
            return
        res = self._last[0]
        sp = getattr(res, "spectra", None)
        if not sp or not sp.get("freqs"):
            return
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if p:
            mode = self._vars["spec_mode"].get()
            curves = sp.get("psd") if mode == "PSD" else sp.get("spec")
            self._spec.set_data(sp["freqs"], curves, mode=mode, station=res.station)
            self._spec.export_png(p)
            self._log_line("SPECTRA CHART SAVED TO " + p)

    def _export_png(self):
        if not self._last:
            return
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if p:
            self._curve.export_png(p)
            self._log_line("CHART SAVED TO " + p)

    def _export_report(self):
        if not self._last:
            return
        res = self._last[0]
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if p:
            write_report_file(p, res)

    def _export_target(self):
        if not self._last:
            return
        res = self._last[0]
        p = filedialog.asksaveasfilename(defaultextension=".target", filetypes=[("Target file", "*.target")])
        if p:
            write_target_file(p, res.freqs, res.mean, res.low, res.high, res.f0)

    def _export_sig_png(self):
        if not getattr(self, "_sig_payload", None):
            return
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if p:
            self._redraw_sig()
            self._sig.export_png(p)
            self._log_line("SIGNAL CHART SAVED TO " + p)

    def _export_filt_png(self):
        if not getattr(self._filt, "traces", None):
            return
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if p:
            self._filt.export_png(p)
            self._log_line("FILTERED WAVEFORM SAVED TO " + p)

    def _export_hv_views(self):
        if not getattr(self._tf, "grid", None) or not self._tf.grid:
            return
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if not p:
            return
        base, ext = os.path.splitext(p)
        saved = []
        for suffix, canvas in (("_timefreq", self._tf), ("_azimuth", self._az), ("_spectra", self._avg_spec), ("_curve", self._avg_hv)):
            out = base + suffix + (ext or ".png")
            canvas.export_png(out)
            saved.append(out)
        self._log_line("H/V VIEWS SAVED: " + ", ".join(saved))
