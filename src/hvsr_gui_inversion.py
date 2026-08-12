"""
hvsr_gui_inversion.py
=====================
The 1D inversion tab of the HVSR Analyzer GUI: the controls, the Vs-profile
and misfit-histogram canvases, the result rendering (_on_inversion_done)
and the report / CSV exports.  The run logic - _start_inversion and the
background worker thread - moved to hvsr_gui_invworker.py.  The inversion
engine itself is hvsr_inversion.py; this module is only the tab's UI
wiring.  Mixed into HVSRApp as HVSRAppInversionMixin.
"""


import os
import tkinter as tk
from tkinter import ttk, filedialog

import hvsr_theme
from hvsr_plot import VsProfileCanvas, MisfitHistCanvas


# Local aliases of the active theme palette (only the ones this
# module uses).  Refreshed by HVSRAppThemeMixin._set_theme() on a
# live theme switch.
ACCENT = hvsr_theme.current["ACCENT"]
BG = hvsr_theme.current["BG"]
TEXT_DARK = hvsr_theme.current["TEXT_DARK"]


class HVSRAppInversionMixin:
    def _build_inversion_tab(self):
        """Create the 1D INVERSION result tab: controls (layers, iterations,
        Poisson ratio, monotonicity), the Vs profile canvas, the misfit
        histogram and the terminal-style inversion log."""
        tab = ttk.Frame(self._nb)
        self._nb.add(tab, text=" [ 1D INVERSION ] ")
        self._inv_vars = {}
        ctrl = ttk.Frame(tab, style="TFrame")
        ctrl.pack(fill="x", padx=10, pady=8)
        for label, key, default, width in (
                ("LAYERS", "layers", "3", 4),
                ("ITERATIONS", "iter", "600", 7),
                ("POISSON", "poisson", "0.40", 5)):
            ttk.Label(ctrl, text=label, style="TLabel").pack(side="left")
            e = ttk.Entry(ctrl, width=width)
            e.insert(0, default)
            e.pack(side="left", padx=(2, 10))
            self._inv_vars[key] = e
        self._inv_vars["monotonic"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Vs INCREASES W/ DEPTH", variable=self._inv_vars["monotonic"], style="TCheckbutton").pack(side="left", padx=(4, 0))
        self._inv_run_btn = ttk.Button(ctrl, text="RUN 1D INVERSION", style="Accent.TButton", command=self._start_inversion)
        self._inv_run_btn.pack(side="left", padx=12)
        ttk.Button(ctrl, text="EXPORT REPORT", command=self._export_inv_report).pack(side="left")
        ttk.Button(ctrl, text="EXPORT MODEL CSV", command=self._export_inv_csv).pack(side="left", padx=6)
        ttk.Label(tab, text="MODEL SEEDED AUTOMATICALLY FROM H/V DATA.", style="Sub.TLabel").pack(fill="x", padx=12, pady=(0, 2))
        self._inv_summary = ttk.Label(tab, text="AWAITING H/V ANALYSIS DATA.", style="TLabel")
        self._inv_summary.pack(fill="x", padx=12)

        self._inv_canvas = VsProfileCanvas(tab)
        self._inv_canvas.pack(fill="both", expand=True, padx=10, pady=(4, 2))
        self._inv_hist = MisfitHistCanvas(tab, height=118)
        self._inv_hist.pack(fill="x", padx=10, pady=(0, 4))

        # TERMINAL-STYLE INVERSION LOG
        self._inv_text = tk.Text(tab, wrap="none", font=("Courier New", 10, "bold"), bg=BG, fg=TEXT_DARK, insertbackground=ACCENT, height=9)
        sb = ttk.Scrollbar(tab, command=self._inv_text.yview)
        self._inv_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._inv_text.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 8))

    def _on_inversion_done(self, inv):
        """UI-thread handler for a finished inversion: draw the Vs profile
        and misfit histogram, fill the summary line and the text log."""
        self._last_inv = inv
        note = "BEST MISFIT %.4f" % (inv.misfit or 0)
        if inv.misfit_p50 is not None:
            note += " | MEDIAN %.4f" % inv.misfit_p50
        note += " | %d MODELS ACCEPTED" % inv.n_accepted
        l1 = inv.layers[0] if inv.layers else None
        top_vs = ""
        if (l1 is not None and l1.get("vs_lo") is not None
                and l1.get("vs_hi") is not None):
            top_vs = "   |   L1 Vs %.0f [%.0f - %.0f] m/s" % (l1["vs"], l1["vs_lo"], l1["vs_hi"])
        self._inv_canvas.set_data(inv.layers, vs30=inv.vs30,
                                  station=inv.station, note=note,
                                  misfits=inv.misfits,
                                  misfit_best=inv.misfit,
                                  misfit_median=inv.misfit_p50,
                                  misfit_p90=inv.misfit_p90)
        from hvsr_inversion import misfit_histogram
        self._inv_hist.set_data(misfit_histogram(inv.misfits),
                                best=inv.misfit, median=inv.misfit_p50,
                                p90=inv.misfit_p90)
        if inv.vs30:
            self._inv_summary.config(
                text="Vs30 = %.0f m/s   |   NEHRP CLASS %s   |   SNI CLASS "
                     "%s   |   SYNTH f0 = %.3f Hz   |   MISFIT %.4f%s"
                     % (inv.vs30, inv.soil_class_nehrp[0],
                        inv.soil_class_sni[0], inv.f0_syn, inv.misfit or 0,
                        top_vs))
        else:
            self._inv_summary.config(
                text="ERR: NO USABLE MODEL PRODUCED. ADJUST ITERATIONS/LAYERS.")
        self._inv_text.delete("1.0", "end")
        self._inv_text.insert("1.0", inv.report_text)
        self._log_line("1D INVERSION COMPLETE: Vs30 = %s, SYNTH f0 = %.3f Hz"
                       % ("%.0f m/s" % inv.vs30 if inv.vs30 else "N/A", inv.f0_syn))
        try:
            out_dir = self._out_dir()
            self._save_inversion_outputs(inv, out_dir)
            self._log_line("INVERSION REPORT & MODEL CSV SAVED.")
        except Exception as exc:
            self._log_line("INVERSION SAVE ERR: %s" % exc)
        self._set_status("INVERSION COMPLETE - Vs30 = %s" % ("%.0f m/s" % inv.vs30 if inv.vs30 else "N/A"), busy=False)

    def _save_inversion_outputs(self, inv, out_dir):
        from hvsr_inversion import (write_inversion_report,
                                    write_inversion_csv)
        write_inversion_report(os.path.join(out_dir, inv.station
                                            + "_inversion_report.txt"), inv)
        write_inversion_csv(os.path.join(out_dir, inv.station
                                         + "_inversion_model.csv"), inv)

    def _export_inv_report(self):
        """Save the full inversion report text via a file dialog."""
        if not getattr(self, "_last_inv", None):
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if p:
            from hvsr_inversion import write_inversion_report
            write_inversion_report(p, self._last_inv)
            self._log_line("INVERSION REPORT SAVED TO " + p)

    def _export_inv_csv(self):
        """Save the layered model table (with uncertainty ranges) as CSV."""
        if not getattr(self, "_last_inv", None):
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p:
            from hvsr_inversion import write_inversion_csv
            write_inversion_csv(p, self._last_inv)
            self._log_line("INVERSION MODEL CSV SAVED TO " + p)
