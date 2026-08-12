"""
hvsr_gui_workflow.py
====================
The four workflow pages of the HVSR Analyzer GUI.

HVSRAppWorkflowMixin: the page builders that fill the left notebook
tabs - _build_page1 (input / output), _build_page2 (pre-processing),
_build_page3 (H/V parameters) and _build_page4 (save options + run
buttons).  They are called by _build_ui() in hvsr_gui_layout.py, which
owns the window frame (header, notebook shell, results panel).
"""


import sys
import tkinter as tk
from tkinter import ttk

import hvsr_geopsy
import hvsr_theme
from hvsr_gui_dnd import DND_AVAILABLE
from hvsr_plot import (HvsrCurveCanvas, TimeSeriesCanvas, SpectraCanvas,
                       ColorMapCanvas)

WINDOW_PRESETS = ["25", "30", "40", "60", "90", "120"]
REJECT_PRESETS = ["1.0", "1.5", "2.0", "2.5", "3.0"]

# Local aliases of the active theme palette.  They are refreshed by
# HVSRAppCore._set_theme() when the user switches theme live, so widgets
# restyled after a switch pick up the new colours.
TEXT_MUTED = hvsr_theme.current["TEXT_MUTED"]
NO_RED = hvsr_theme.current["NO_RED"]


class HVSRAppWorkflowMixin:
    def _build_page1(self, p_in, p_out):
        """Page 1: input data - file links, time range, waveform preview,
        signal analysis - plus the output-directory card.  The tab is named
        01_INPUT/OUTPUT, so this builder writes into both p_in (input) and
        p_out (the output-directory card); _build_page4 fills the rest of
        p_out (save options + run buttons)."""

        f_in = self._card(p_in, "Input Data Link", 0)
        self._drop_card = f_in  # tinted while a drag hovers (DnD feedback)
        if DND_AVAILABLE:
            # banner only when drag & drop is wired up; it highlights while
            # a drag hovers over the window (see HVSRAppDndMixin)
            self._drop_hint_base = ("\u25bc DROP DATA FILES HERE \u2014 3 "
                                    "component files, 1 .eqd/.sg2/3-column "
                                    "file, or a folder to BATCH-PROCESS")
            self._drop_hint = ttk.Label(f_in, text=self._drop_hint_base,
                                        style="Card.TLabel")
            self._drop_hint.pack(fill="x", pady=(0, 6))
        else:
            self._drop_hint = None
            self._drop_hint_base = ""
        self._add_file_row(f_in, "VERTICAL (Z)", "z", 0)
        self._add_file_row(f_in, "NORTH (N)", "n", 1)
        self._add_file_row(f_in, "EAST (E)", "e", 2)
        row = ttk.Frame(f_in, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="AUTO-ASSIGN...", width=20,
                   command=self._auto_assign).pack(side="left")
        ttk.Label(row, text="  Select 1 file (.eqd/.sg2/3-col)\n"
                            "  or 3 distinct files.",
                  style="Card.TLabel").pack(side="left")
        self._add_file_row(f_in, "RESPONSE", "pz", 3)
        self._themed(ttk.Label(f_in, text="Optional SAC pole-zero (.pz) file required to correct\ninstrument response parameters.", style="Card.TLabel",
                  foreground=TEXT_MUTED), "TEXT_MUTED").pack(anchor="w", padx=(100, 0))
        self._vars["swap_h"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_in, text="SWAP N/E CHANNELS (Corrections for .eqd/.sg2)",
                        variable=self._vars["swap_h"],
                        command=self._refresh_preview,
                        style="Card.TCheckbutton").pack(anchor="w", pady=2)
        tr = ttk.Frame(f_in, style="Card.TFrame")
        tr.pack(fill="x", pady=(6, 0))
        ttk.Label(tr, text="TIME RANGE(s)", style="Card.TLabel").pack(side="left")
        ttk.Label(tr, text="START", style="Card.TLabel").pack(side="left", padx=(8, 2))
        e0 = ttk.Entry(tr, width=7)
        e0.pack(side="left")
        self._vars["t0"] = e0
        self._vars["t0_w"] = e0
        ttk.Label(tr, text="END", style="Card.TLabel").pack(side="left", padx=(8, 2))
        e1 = ttk.Entry(tr, width=7)
        e1.pack(side="left")
        self._vars["t1"] = e1
        self._vars["t1_w"] = e1
        ttk.Button(tr, text="USE FULL", width=10, command=self._use_full_time).pack(side="left", padx=(8, 0))

        ttk.Label(f_in, text="// WAVEFORM_PREVIEW", style="H.TLabel").pack(anchor="w", pady=(12, 2))
        self._preview = TimeSeriesCanvas(f_in, height=170)
        self._preview.pack(fill="x")
        self._themed(ttk.Label(f_in, text="Awaiting synchronization...", style="Card.TLabel", foreground=TEXT_MUTED), "TEXT_MUTED").pack(anchor="w")

        ttk.Label(f_in, text="// SIGNAL_ANALYSIS (RAW)", style="H.TLabel").pack(anchor="w", pady=(12, 2))
        srow = ttk.Frame(f_in, style="Card.TFrame")
        srow.pack(fill="x")
        ttk.Button(srow, text="ANALYSE SIGNAL", width=18, command=self._analyse_signal).pack(side="left")
        self._vars["sig_mode"] = tk.StringVar(value="PSD")
        for text, val in (("PSD", "PSD"), ("SPECTRUM", "Spectrum"), ("COHERENCE", "Coherence")):
            ttk.Radiobutton(srow, text=text, value=val, variable=self._vars["sig_mode"], command=self._redraw_sig, style="Card.TRadiobutton").pack(side="left", padx=(6, 0))
        ttk.Button(srow, text="EXPORT PNG", width=12, command=self._export_sig_png).pack(side="left", padx=(8, 0))
        self._sig = SpectraCanvas(f_in, height=140)
        self._sig.pack(fill="x", pady=(2, 0))

        f_out = self._card(p_in, "Output Directory", 1)
        self._add_file_row(f_out, "SAVE TARGET", "out", 0)

    def _build_page2(self, p_pre):
        """Page 2: pre-processing - band-pass, STA/LTA muting, decimation
        and the filtered-waveform preview."""

        f_proc = self._card(p_pre, "Pre-Processing Protocols", 0)
        row = ttk.Frame(f_proc, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 2))
        ttk.Label(row, text="BAND-PASS", style="Card.TLabel").pack(side="left")
        e = ttk.Entry(row, width=6)
        e.insert(0, "0.2")
        e.pack(side="left", padx=4)
        self._vars["f_low"] = e
        self._vars["f_low_w"] = e
        ttk.Label(row, text="-", style="Card.TLabel").pack(side="left")
        e = ttk.Entry(row, width=6)
        e.insert(0, "20.0")
        e.pack(side="left", padx=4)
        self._vars["f_high"] = e
        self._vars["f_high_w"] = e
        ttk.Label(row, text="Hz", style="Card.TLabel").pack(side="left")
        self._vars["mute"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_proc, text="STA/LTA TRANSIENT MUTING", variable=self._vars["mute"], style="Card.TCheckbutton").pack(anchor="w", pady=(2, 0))
        sl = ttk.Frame(f_proc, style="Card.TFrame")
        sl.pack(fill="x", pady=(0, 2))
        ttk.Label(sl, text="STA", style="Card.TLabel").pack(side="left")
        e = ttk.Entry(sl, width=5)
        e.insert(0, "1.0")
        e.pack(side="left", padx=(4, 2))
        self._vars["sta_sec"] = e
        self._vars["sta_sec_w"] = e
        ttk.Label(sl, text="s  LTA", style="Card.TLabel").pack(side="left")
        e = ttk.Entry(sl, width=5)
        e.insert(0, "30.0")
        e.pack(side="left", padx=2)
        self._vars["lta_sec"] = e
        self._vars["lta_sec_w"] = e
        ttk.Label(sl, text="s  TRIGGER", style="Card.TLabel").pack(side="left")
        e = ttk.Entry(sl, width=5)
        e.insert(0, "2.5")
        e.pack(side="left", padx=2)
        self._vars["slta_threshold"] = e
        self._vars["slta_threshold_w"] = e
        ttk.Label(sl, text="x", style="Card.TLabel").pack(side="left")

        dc = ttk.Frame(f_proc, style="Card.TFrame")
        dc.pack(fill="x", pady=(0, 2))
        self._vars["decimate"] = tk.BooleanVar(value=True)
        self._decimate_cb = ttk.Checkbutton(dc, text="DECIMATE IF RATE >",
                                            variable=self._vars["decimate"],
                                            style="Card.TCheckbutton")
        self._decimate_cb.pack(side="left")
        e = ttk.Entry(dc, width=5)
        e.insert(0, "250")
        e.pack(side="left", padx=4)
        self._vars["max_fs"] = e
        self._vars["max_fs_w"] = e
        self._themed(ttk.Label(dc, text="Hz (Auto-scaled for GEOPSY)", style="Card.TLabel", foreground=TEXT_MUTED), "TEXT_MUTED").pack(side="left")

        ttk.Label(f_proc, text="// FILTERED_WAVEFORM_PREVIEW", style="H.TLabel").pack(anchor="w", pady=(8, 2))
        wrow = ttk.Frame(f_proc, style="Card.TFrame")
        wrow.pack(fill="x")
        ttk.Button(wrow, text="PREVIEW FILTERED", width=18, command=self._preview_filtered).pack(side="left")
        ttk.Button(wrow, text="EXPORT PNG", width=12, command=self._export_filt_png).pack(side="left", padx=(6, 0))
        ttk.Label(wrow, text="WINDOW", style="Card.TLabel").pack(side="left", padx=(8, 2))
        e = ttk.Entry(wrow, width=6)
        e.insert(0, "30")
        e.pack(side="left")
        self._vars["pv_win"] = e
        ttk.Label(wrow, text="s", style="Card.TLabel").pack(side="left", padx=2)
        self._filt = TimeSeriesCanvas(f_proc, height=150)
        self._filt.pack(fill="x", pady=(2, 0))

    def _build_page3(self, p_hv):
        """Page 3: H/V parameters - window / overlap / rejection, smoothing,
        method recommendations, auto-tune and the H/V view canvases."""

        f_hv = self._card(p_hv, "H/V Parameters", 0)
        mode_row = ttk.Frame(f_hv, style="Card.TFrame")
        mode_row.pack(fill="x", pady=(0, 6))
        self._vars["param_mode"] = tk.StringVar(value="manual")
        ttk.Label(mode_row, text="MODE:", style="Card.TLabel").pack(side="left")
        ttk.Radiobutton(mode_row, text="MANUAL", value="manual", variable=self._vars["param_mode"], command=self._toggle_param_mode, style="Card.TRadiobutton").pack(side="left", padx=(6, 0))
        ttk.Radiobutton(mode_row, text="AUTO", value="auto", variable=self._vars["param_mode"], command=self._toggle_param_mode, style="Card.TRadiobutton").pack(side="left", padx=(6, 0))

        grid = ttk.Frame(f_hv, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        rows = [
            ("WINDOW (s)", "win_len", WINDOW_PRESETS, "30"),
            ("OVERLAP (%)", "overlap", ["0", "25", "50"], "0"),
            ("REJECTION (n-sigma)", "rejection", REJECT_PRESETS, "1.5"),
            ("FREQ. MIN (Hz)", "fmin", None, "0.5"),
            ("FREQ. MAX (Hz)", "fmax", None, "20.0"),
            ("LOG SAMPLES", "nfreq", None, "512"),
            ("SMOOTHING", "smoothing", ["konno_ohmachi", "moving_average", "triangular_constant", "triangular_proportional"], "konno_ohmachi"),
            ("SMOOTH WIDTH", "smooth_width", None, "40"),
            ("KO b-VALUE", "b_value", None, "40"),
            ("TAPER (alpha)", "taper", None, "0.05"),
            ("REJECT MAX ITERS", "max_iterations", None, "50"),
        ]
        for i, (label, key, values, default) in enumerate(rows):
            ttk.Label(grid, text=label, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=2)
            if values:
                var = tk.StringVar(value=default)
                cb = ttk.Combobox(grid, textvariable=var, values=values, width=19)
                cb.grid(row=i, column=1, sticky="w", pady=2)
                self._vars[key] = var
                self._vars[key + "_w"] = cb
            else:
                e = ttk.Entry(grid, width=21)
                e.insert(0, default)
                e.grid(row=i, column=1, sticky="w", pady=2)
                self._vars[key] = e
                self._vars[key + "_w"] = e

        self._vars["combo"] = tk.StringVar(value="geometric")
        ttk.Label(grid, text="H/V FORMULA", style="Card.TLabel").grid(row=len(rows), column=0, sticky="w", pady=2)
        ttk.Combobox(grid, textvariable=self._vars["combo"], width=19, values=["geometric", "quadratic", "arithmetic"], state="readonly").grid(row=len(rows), column=1, sticky="w")

        sugg = ttk.Frame(f_hv, style="Card.TFrame")
        sugg.pack(fill="x", pady=(6, 0))
        ttk.Button(sugg, text="APPLY METHOD RECS", command=self._apply_suggestions).pack(side="left")

        self._vars["autotune"] = tk.BooleanVar(value=False)
        self._autotune_cb = ttk.Checkbutton(f_hv, text="AUTO-TUNE WINDOW/REJECT (SESAME)",
                                            variable=self._vars["autotune"],
                                            style="Card.TCheckbutton")
        self._autotune_cb.pack(anchor="w", pady=(6, 0))
        self._full_at_btn = ttk.Button(f_hv, text="AUTO-TUNE MAX RELIABILITY...",
                                       command=self._start_full_autotune)
        self._full_at_btn.pack(anchor="w", pady=(4, 0))

        std_row = ttk.Frame(f_hv, style="Card.TFrame")
        std_row.pack(fill="x", pady=(8, 0))
        ttk.Label(std_row, text="STANDARD", style="Card.TLabel").pack(side="left")
        std_names = ["SESAME 2004 (Europe)", "Japan (J-SHIS / JAMC)", "Indonesia (SNI 1726-2019 / BMKG)", "USGS / NEHRP", "Generic / Industry"]
        self._std_map = {"SESAME 2004 (Europe)": "sesame", "Japan (J-SHIS / JAMC)": "japan", "Indonesia (SNI 1726-2019 / BMKG)": "indonesia", "USGS / NEHRP": "usgs", "Generic / Industry": "generic"}
        self._vars["std"] = tk.StringVar(value="SESAME 2004 (Europe)")
        cb = ttk.Combobox(std_row, textvariable=self._vars["std"], values=std_names, width=28, state="readonly")
        cb.bind("<<ComboboxSelected>>", lambda e: self._on_std_change())
        cb.pack(side="left", padx=6)

        prof = ttk.Frame(f_hv, style="Card.TFrame")
        prof.pack(fill="x", pady=(8, 0))
        ttk.Label(prof, text="PROFILE:", style="Card.TLabel").pack(side="left")
        ttk.Button(prof, text="SAVE...", width=8, command=self._save_params).pack(side="left", padx=(8, 0))
        ttk.Button(prof, text="LOAD...", width=8, command=self._load_params).pack(side="left", padx=(4, 0))

        ttk.Label(f_hv, text="// H/V_ANALYSIS_VIEWS", style="H.TLabel").pack(anchor="w", pady=(12, 2))
        brow = ttk.Frame(f_hv, style="Card.TFrame")
        brow.pack(fill="x")
        ttk.Button(brow, text="PREVIEW H/V VIEWS", width=20, command=self._preview_hv_views).pack(side="left")
        ttk.Button(brow, text="EXPORT PNG", width=12, command=self._export_hv_views).pack(side="left", padx=(6, 0))

        self._tf = ColorMapCanvas(f_hv, height=150)
        self._tf.pack(fill="x", pady=(4, 0))
        self._az = ColorMapCanvas(f_hv, height=150)
        self._az.pack(fill="x", pady=(4, 0))
        self._avg_spec = SpectraCanvas(f_hv, height=130)
        self._avg_spec.pack(fill="x", pady=(4, 0))
        self._avg_hv = HvsrCurveCanvas(f_hv, height=140)
        self._avg_hv.pack(fill="x", pady=(4, 0))

    def _build_page4(self, p_out):
        """Page 4: save options, extra subroutines, Geopsy sync and the
        run-sequence / batch buttons."""

        f_save = self._card(p_out, "Save Protocol Options", 0)
        save_row = ttk.Frame(f_save, style="Card.TFrame")
        save_row.pack(fill="x", pady=(0, 4))
        self._vars["sv_report"] = tk.BooleanVar(value=True)
        self._vars["sv_target"] = tk.BooleanVar(value=True)
        self._vars["sv_png"] = tk.BooleanVar(value=True)
        self._vars["sv_csv"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(save_row, text="REPORT", variable=self._vars["sv_report"], style="Card.TCheckbutton").pack(side="left")
        ttk.Checkbutton(save_row, text="TARGET", variable=self._vars["sv_target"], style="Card.TCheckbutton").pack(side="left", padx=6)
        ttk.Checkbutton(save_row, text="CHART PNG", variable=self._vars["sv_png"], style="Card.TCheckbutton").pack(side="left", padx=6)
        ttk.Checkbutton(save_row, text="DATA CSV", variable=self._vars["sv_csv"], style="Card.TCheckbutton").pack(side="left")
        self._vars["ask_save"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_save, text="PROMPT SAVE LOCATIONS", variable=self._vars["ask_save"], style="Card.TCheckbutton").pack(anchor="w", pady=2)
        self._vars["log_csv"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_save, text="APPEND TO DATA_LOG.CSV", variable=self._vars["log_csv"], style="Card.TCheckbutton").pack(anchor="w", pady=2)

        f_extra = self._card(p_out, "Extra Analysis Subroutines", 1)
        self._vars["do_psd"] = tk.BooleanVar(value=True)
        self._vars["do_spec"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_extra, text="POWER SPECTRAL DENSITY (dB)", variable=self._vars["do_psd"], style="Card.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(f_extra, text="FOURIER AMPLITUDE (Z/N/E)", variable=self._vars["do_spec"], style="Card.TCheckbutton").pack(anchor="w", pady=2)

        # File Associations card (Windows only: the toggle writes HKCU
        # registry keys, so there is nothing to show on other platforms)
        if sys.platform == "win32":
            self._build_assoc_toggle(p_out, 2)
            geo_row = 3
        else:
            geo_row = 2

        f_geo = self._card(p_out, "Geopsy Cross-Check Sync", geo_row)
        self._vars["geo_enable"] = tk.BooleanVar(value=False)
        self._vars["geo_path"] = tk.StringVar(value=hvsr_geopsy.find_geopsy() or "")
        ttk.Checkbutton(f_geo, text="ENABLE GEOPSY SYNC", variable=self._vars["geo_enable"], style="Card.TCheckbutton").pack(anchor="w")
        row = ttk.Frame(f_geo, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        e = ttk.Entry(row, textvariable=self._vars["geo_path"])
        e.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="DETECT", width=8, command=self._detect_geopsy).pack(side="left", padx=(6, 0))
        if not self._vars["geo_path"].get():
            self._themed(ttk.Label(f_geo, text="GEOPSY NOT DETECTED.", style="Card.TLabel", foreground=NO_RED), "NO_RED").pack(anchor="w")

        btns = ttk.Frame(p_out, style="TFrame")
        btns.grid(row=geo_row + 1, column=0, sticky="ew", padx=12,
                  pady=(2, 10))
        self._run_btn = ttk.Button(btns, text="INITIATE RUN SEQUENCE", style="Accent.TButton", command=self._start_run)
        self._run_btn.pack(fill="x", ipady=6)
        self._batch_btn = ttk.Button(btns, text="BATCH PROCESS FOLDER", command=self._start_batch)
        self._batch_btn.pack(fill="x", pady=(6, 0), ipady=4)
