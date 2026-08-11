"""
hvsr_gui.py
===========
Tkinter GUI for the HVSR Analyzer (pure standard library, no external
packages).  Features:

- 1 three-column file, 3 component files, or a single .eqd / .sg2 file
  (components auto-detected) as input, optional pole-zero file
- full parameter control of every engine setting: window length, overlap,
  rejection, frequency range, log samples, Konno-Ohmachi b-value, cosine
  taper, rejection iterations, STA/LTA muting, decimation target rate,
  H/V combination and band-pass
- 'Apply Method recommendations' fills every field from the selected
  method standard (SESAME 2004 / Japan / USGS / Generic), then you can
  adjust any of them by hand
- SESAME-score auto-tuning of window length and rejection factor
- optional Geopsy cross-check (auto-detected, never blocks the analysis)
- single-station analysis and batch processing of a whole folder
- interactive charts (H/V curve, time series) with PNG / report / target export
- SESAME reliability checklist and full text report
"""

import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from hvsr_io import DataError, auto_load
from hvsr_engine import (preprocess, analyze, auto_tune, compute_spectra,
                         log_frequencies,
                         write_target_file, write_report_file, trim_seconds,
                         coherence, hv_vs_time, hv_vs_azimuth)
from hvsr_plot import (HvsrCurveCanvas, TimeSeriesCanvas, SpectraCanvas,
                       VsProfileCanvas, MisfitHistCanvas, ColorMapCanvas)
from hvsr_dsp import resolve_workers
from hvsr_tour import TourOverlay
import hvsr_geopsy
import hvsr_theme
try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False

# ======================================
# THEME PALETTES (shared with hvsr_plot / chart_render via hvsr_theme.py)
# ======================================
ACCENT = hvsr_theme.current["ACCENT"]
BG = hvsr_theme.current["BG"]
PANEL_BG = hvsr_theme.current["PANEL_BG"]
TEXT_DARK = hvsr_theme.current["TEXT_DARK"]
TEXT_MUTED = hvsr_theme.current["TEXT_MUTED"]
OK_GREEN = hvsr_theme.current["OK_GREEN"]
NO_RED = hvsr_theme.current["NO_RED"]
HOVER = hvsr_theme.current["HOVER"]
# ======================================

WINDOW_PRESETS = ["25", "30", "40", "60", "90", "120"]
REJECT_PRESETS = ["1.0", "1.5", "2.0", "2.5", "3.0"]

# Fallbacks applied to any parameter left empty / unresolved by Auto mode.
PARAM_DEFAULTS = {
    "f_low": 0.2, "f_high": 20.0, "win_len": 30.0, "rejection": 1.5,
    "fmin": 0.5, "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
    "overlap": 0.0, "taper": 0.05, "max_iterations": 50,
    "sta_sec": 1.0, "lta_sec": 30.0, "slta_threshold": 2.5,
    "max_fs": 250.0, "smoothing": "konno_ohmachi", "smooth_width": 40.0,
}


class HVSRApp(tk.Tk):
    def __init__(self, show_tour=False):
        super().__init__()
        self.title("HVSR Analyzer")
        self.geometry("1320x820")
        self.minsize(1080, 700)
        self.configure(bg=BG)

        self._queue = queue.Queue()
        self._busy = False
        self._last = None  # (result, data, meta, geo_freqs, geo_amps)
        self._last_evals = {}
        self._last_inv = None
        self._autotune_full = False
        self._tour = None
        self._vars = {}
        self._build_style()
        self._build_ui()
        self.after(120, self._poll_queue)
        if show_tour:
            self.after(800, self._start_tour)

    # ------------------------------------------------------------------ UI
    def _build_style(self):
        style = self._style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
            
        # Global overrides for the active theme (dark or black & white)
        style.configure(".", background=BG, foreground=TEXT_DARK, font=("Courier New", 10, "bold"))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL_BG)
        
        style.configure("TLabel", background=BG, foreground=TEXT_DARK, font=("Courier New", 10, "bold"))
        style.configure("Card.TLabel", background=PANEL_BG, foreground=TEXT_DARK, font=("Courier New", 10, "bold"))
        style.configure("Title.TLabel", background=BG, foreground=ACCENT, font=("Courier New", 18, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=TEXT_MUTED, font=("Courier New", 9, "bold"))
        style.configure("H.TLabel", background=PANEL_BG, foreground=ACCENT, font=("Courier New", 11, "bold"))
        
        # Checkboxes and Radiobuttons
        style.configure("TRadiobutton", background=BG, foreground=TEXT_DARK)
        style.configure("Card.TRadiobutton", background=PANEL_BG, foreground=TEXT_DARK, indicatorcolor=BG)
        style.configure("TCheckbutton", background=BG, foreground=TEXT_DARK)
        style.configure("Card.TCheckbutton", background=PANEL_BG, foreground=TEXT_DARK, indicatorcolor=BG)
        
        # Frames
        style.configure("TLabelframe", background=PANEL_BG, bordercolor=ACCENT)
        style.configure("TLabelframe.Label", background=PANEL_BG, foreground=ACCENT, font=("Courier New", 10, "bold"))
        
        # Buttons.  lightcolor/darkcolor are forced to match the active theme
        # so the clam theme's light-gray top/left edge never shows on any
        # button; hover keeps the orange fill (or purple for accent buttons).
        style.configure("TButton", font=("Courier New", 10, "bold"),
                        background=PANEL_BG, foreground=ACCENT, bordercolor=ACCENT,
                        lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        style.map("TButton",
                  background=[("active", ACCENT), ("disabled", "#333333"),
                              ("!disabled", PANEL_BG)],
                  foreground=[("active", BG), ("disabled", "#777777"),
                              ("!disabled", ACCENT)],
                  lightcolor=[("active", ACCENT), ("disabled", "#333333"),
                              ("!disabled", PANEL_BG)],
                  darkcolor=[("active", ACCENT), ("disabled", "#333333"),
                             ("!disabled", PANEL_BG)],
                  bordercolor=[("active", ACCENT), ("disabled", "#333333"),
                               ("!disabled", ACCENT)])

        style.configure("Accent.TButton", background=ACCENT, foreground=BG,
                        font=("Courier New", 11, "bold"),
                        lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("active", HOVER), ("disabled", "#333333")],
                  foreground=[("active", "#FFFFFF"), ("disabled", "#777777")],
                  lightcolor=[("active", HOVER), ("disabled", "#333333"),
                              ("!active", ACCENT)],
                  darkcolor=[("active", HOVER), ("disabled", "#333333"),
                             ("!active", ACCENT)],
                  bordercolor=[("active", HOVER), ("disabled", "#333333"),
                               ("!active", ACCENT)])
        
        # Notebook / Tabs (tab borders forced dark so the clam theme's
        # light-gray seam and white edge-line never show through; the
        # notebook container keeps its orange accent frame)
        style.configure("TNotebook", background=BG, bordercolor=ACCENT, tabmargins=[2, 5, 2, 0],
                        lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        style.configure("TNotebook.Tab", background=PANEL_BG, foreground=ACCENT,
                        font=("Courier New", 10, "bold"), padding=(12, 6),
                        borderwidth=0, lightcolor=PANEL_BG, darkcolor=PANEL_BG,
                        focusthickness=0)
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT), ("!selected", PANEL_BG)],
                  foreground=[("selected", BG), ("!selected", ACCENT)],
                  lightcolor=[("selected", ACCENT), ("!selected", PANEL_BG)],
                  darkcolor=[("selected", ACCENT), ("!selected", PANEL_BG)],
                  bordercolor=[("selected", ACCENT), ("!selected", PANEL_BG)])
        
        # Entries & Comboboxes (dark mode).  lightcolor/darkcolor force the
        # top/bottom borders orange to match the left/right accent frame -
        # clam's default light-gray edges never show through.
        style.configure("TEntry", fieldbackground=BG, foreground=TEXT_DARK,
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("TCombobox", fieldbackground=BG, foreground=TEXT_DARK,
                        bordercolor=ACCENT, arrowcolor=ACCENT,
                        lightcolor=ACCENT, darkcolor=ACCENT)
        # disabled entries/comboboxes (Auto mode) keep the dark field +
        # muted text instead of clam's light-gray disabled background
        style.map("TEntry",
                  fieldbackground=[("disabled", BG), ("!disabled", BG)],
                  foreground=[("disabled", TEXT_MUTED), ("!disabled", TEXT_DARK)])
        style.map("TCombobox",
                  fieldbackground=[("readonly", BG), ("disabled", BG),
                                   ("!disabled", BG)],
                  selectbackground=[("readonly", ACCENT)],
                  selectforeground=[("readonly", BG)],
                  foreground=[("disabled", TEXT_MUTED), ("!disabled", TEXT_DARK)])
        # combobox drop-down list: force the popdown listbox dark too
        self.option_add("*TCombobox*Listbox.background", BG)
        self.option_add("*TCombobox*Listbox.foreground", TEXT_DARK)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", BG)
        
        # Scrollbars (full state map - kills clam's light active/disabled rendering
        # and the light 3D borders; keeps the active theme's look on every page)
        style.configure("Vertical.TScrollbar", background=PANEL_BG, bordercolor=PANEL_BG,
                        arrowcolor=ACCENT, troughcolor=BG,
                        lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        style.map("Vertical.TScrollbar",
                  background=[("pressed", PANEL_BG), ("active", PANEL_BG),
                              ("disabled", PANEL_BG), ("!disabled", PANEL_BG)],
                  troughcolor=[("disabled", BG), ("!disabled", BG)],
                  arrowcolor=[("disabled", TEXT_MUTED), ("!disabled", ACCENT)],
                  bordercolor=[("disabled", PANEL_BG), ("!disabled", PANEL_BG)],
                  lightcolor=[("disabled", PANEL_BG), ("!disabled", PANEL_BG)],
                  darkcolor=[("disabled", PANEL_BG), ("!disabled", PANEL_BG)])

        # Progress bar (status strip) - dark trough, orange bar, dark borders.
        # Style both the base and the horizontal variant (ttk resolves the
        # default-orientation progressbar to "Horizontal.TProgressbar").
        for _pb_style in ("TProgressbar", "Horizontal.TProgressbar"):
            style.configure(_pb_style, background=ACCENT, troughcolor=BG,
                            bordercolor=PANEL_BG, lightcolor=PANEL_BG,
                            darkcolor=PANEL_BG)
            style.map(_pb_style,
                      background=[("active", ACCENT), ("!active", ACCENT)],
                      troughcolor=[("disabled", BG), ("!disabled", BG)])

    def _card(self, parent, title, row):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=12)
        frame.grid(row=row, column=0, sticky="nsew", padx=12, pady=(0, 10))
        ttk.Label(frame, text=f"// {title.upper()}", style="H.TLabel").pack(anchor="w", pady=(0, 8))
        return frame

    def _add_file_row(self, parent, label, var_name, row):
        row_f = ttk.Frame(parent, style="Card.TFrame")
        row_f.pack(fill="x", pady=3)
        ttk.Label(row_f, text=label, style="Card.TLabel", width=14).pack(side="left")
        entry = ttk.Entry(row_f)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, "")
        self._vars[var_name + "_entry"] = entry
        ttk.Button(row_f, text="BROWSE...", width=9,
                   command=lambda v=var_name: self._browse(v)).pack(side="left", padx=(6, 0))

    def _browse(self, var_name):
        if var_name == "out":
            p = filedialog.askdirectory(
                title="Choose the output folder (create one if needed)")
        elif var_name == "pz":
            p = filedialog.askopenfilename(
                title="Select instrument response (.pz)",
                filetypes=[("SAC pole-zero", "*.pz"), ("All files", "*.*")])
        elif var_name in ("z", "n", "e"):
            p = filedialog.askopenfilename(
                title="Select component signal file",
                filetypes=[
                    ("Seismic files", "*.mseed *.miniseed *.eqd *.sg2 *.csv "
                                      "*.txt *.dat *.asc *.tsv *.sac"),
                    ("MiniSEED", "*.mseed *.miniseed"),
                    (".eqd", "*.eqd"),
                    ("SEG-2 (.sg2)", "*.sg2"),
                    ("Text / CSV", "*.csv *.txt *.dat *.asc *.tsv *.sac"),
                    ("All files", "*.*")])
        else:
            p = filedialog.askopenfilename(title="Select file")
        if p:
            self._vars[var_name + "_entry"].delete(0, "end")
            self._vars[var_name + "_entry"].insert(0, p)
            if var_name in ("z", "n", "e") and hasattr(self, "_preview"):
                self._refresh_preview()
            if var_name in ("z",) and p.lower().endswith(".eqd"):
                self._log_line("SYS: Single .eqd file provides all 3 components.")
            elif var_name in ("z",) and p.lower().endswith(".sg2"):
                self._log_line("SYS: Single .sg2 file holds all 3 components "
                               "(Z/N/E detected automatically).")

    def _toggle_param_mode(self):
        auto = self._vars["param_mode"].get() == "auto"
        for key in ("win_len", "rejection", "f_low", "f_high", "b_value",
                    "fmin", "fmax", "nfreq", "taper", "max_iterations",
                    "sta_sec", "lta_sec", "slta_threshold", "max_fs",
                    "smooth_width"):
            w = self._vars.get(key + "_w") or self._vars.get(key)
            if w is None or isinstance(w, tk.Variable):
                continue
            w.config(state="disabled" if auto else "normal")
        self._vars["autotune"].set(auto)

    def _set_param(self, key, value):
        w = self._vars.get(key + "_w") or self._vars.get(key)
        if w is None:
            return
        if isinstance(w, tk.Variable):
            w.set(str(value))
        else:
            w.delete(0, "end")
            w.insert(0, str(value))

    def _apply_suggestions(self):
        if not _HAVE_STANDARDS:
            self._log_line("SYS_ERR: standards module unavailable - cannot apply recommendations")
            return
        self._vars["param_mode"].set("manual")
        self._toggle_param_mode()
        std_id = self._std_map.get(self._vars["std"].get(), "sesame")
        rec = hvsr_standards.recommended_params(std_id)
        for key, val in rec.items():
            if key == "overlap":
                val = int(round(val * 100)) 
            self._set_param(key, val)
        self._log_line("SYS: Applied %s recommended parameters - review them and "
                       "adjust any field, then initiate Run Sequence."
                       % self._vars["std"].get())

    def _scroll_page(self, parent):
        # Each page gets its OWN container frame so its scrollbar is packed
        # inside that page only. (Packing the scrollbars directly into the
        # shared notebook body stacked all 4 scrollbars on top of each other
        # on the right edge - the "scroll overlap" in the left layout.)
        container = ttk.Frame(parent, style="TFrame")
        canvas = tk.Canvas(container, highlightthickness=0, bd=0, bg=BG)
        sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        page = ttk.Frame(canvas, style="TFrame")
        win = canvas.create_window((0, 0), window=page, anchor="nw")
        page._scroll_canvas = canvas

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _width(e):
            canvas.itemconfigure(win, width=e.width)

        page.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)
        return container, page

    def _bind_page_wheel(self, page):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            page.bind(seq, self._page_wheel)
            for child in page.winfo_children():
                self._bind_wheel_children(child, seq)

    def _bind_wheel_children(self, widget, seq):
        widget.bind(seq, self._page_wheel)
        for child in widget.winfo_children():
            self._bind_wheel_children(child, seq)

    def _page_wheel(self, event):
        w = event.widget
        canvas = None
        node = w
        while node is not None:
            canvas = getattr(node, "_scroll_canvas", None)
            if canvas is not None:
                break
            node = node.master
        if canvas is None:
            return
        step = max(1, abs(getattr(event, "delta", 120)) // 120)
        if getattr(event, "num", None) == 4:
            canvas.yview_scroll(-step, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(step, "units")
        else:
            canvas.yview_scroll(-step if event.delta > 0 else step,
                                "units")
        return "break"

    def _build_ui(self):
        # header
        header = ttk.Frame(self, padding=(16, 10))
        header.pack(fill="x")
        ttk.Label(header, text="HVSR ANALYZER", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="  100% STANDARD LIBRARY", style="Sub.TLabel").pack(side="left")
        self._load_btn = ttk.Button(header, text="LOAD SAMPLE DATA", width=18,
                                    command=self._load_sample)
        self._load_btn.pack(side="right")
        self._help_btn = ttk.Button(header, text="HELP", width=8,
                                    command=self._show_help)
        self._help_btn.pack(side="right", padx=6)
        self._tutorial_btn = ttk.Button(header, text="TUTORIAL", width=10,
                                        command=self._open_tutorial)
        self._tutorial_btn.pack(side="right", padx=6)
        self._tour_btn = ttk.Button(header, text="SHOW TOUR", width=10,
                                    command=self._start_tour)
        self._tour_btn.pack(side="right", padx=6)
        self._vars["theme"] = tk.StringVar(value="DARK (CLASSIC)")
        self._theme_cb = ttk.Combobox(header, textvariable=self._vars["theme"], width=15,
                                      values=["DARK (CLASSIC)", "B&W (THESIS)"],
                                      state="readonly")
        self._theme_cb.bind("<<ComboboxSelected>>", lambda e: self._set_theme())
        self._theme_cb.pack(side="right", padx=(0, 6))
        ttk.Label(header, text="THEME", style="Sub.TLabel").pack(side="right", padx=(6, 0))

        main = ttk.Frame(self, style="TFrame")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        left = ttk.Frame(main, style="TFrame", width=478)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = ttk.Frame(main, style="TFrame")
        right.pack(side="left", fill="both", expand=True)

        self._pages = ttk.Notebook(left, width=470)
        self._pages.pack(fill="both", expand=True, padx=(0, 8))

        _c, p_in = self._scroll_page(self._pages)
        self._pages.add(_c, text=" 01_INPUT/OUTPUT ")
        p_in.columnconfigure(0, weight=1)
        _c, p_pre = self._scroll_page(self._pages)
        self._pages.add(_c, text=" 02_PRE_PROCESS ")
        p_pre.columnconfigure(0, weight=1)
        _c, p_hv = self._scroll_page(self._pages)
        self._pages.add(_c, text=" 03_HV_PARAMS ")
        p_hv.columnconfigure(0, weight=1)
        _c, p_out = self._scroll_page(self._pages)
        self._pages.add(_c, text=" 04_OUTPUT_DATA ")
        p_out.columnconfigure(0, weight=1)
        self._page_frames = [p_in, p_pre, p_hv, p_out]

        # ---------------- page 1: input data + output folder -------------
        f_in = self._card(p_in, "Input Data Link", 0)
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

        # ---------------- page 2: pre-processing -------------
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

        # ---------------- page 3: H/V parameters -------------
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

        # ---------------- page 4: output data -------------
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

        f_geo = self._card(p_out, "Geopsy Cross-Check Sync", 2)
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
        btns.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 10))
        self._run_btn = ttk.Button(btns, text="INITIATE RUN SEQUENCE", style="Accent.TButton", command=self._start_run)
        self._run_btn.pack(fill="x", ipady=6)
        self._batch_btn = ttk.Button(btns, text="BATCH PROCESS FOLDER", command=self._start_batch)
        self._batch_btn.pack(fill="x", pady=(6, 0), ipady=4)

        for page in self._page_frames:
            self._bind_page_wheel(page)

        # ---------- right panel ----------
        self._nb = ttk.Notebook(right)
        self._nb.pack(fill="both", expand=True)

        tab_curve = ttk.Frame(self._nb)
        self._nb.add(tab_curve, text=" [ H/V CURVE ] ")
        bar = ttk.Frame(tab_curve)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="EXPORT PNG", command=self._export_png).pack(side="left")
        ttk.Button(bar, text="EXPORT REPORT (.TXT)", command=self._export_report).pack(side="left", padx=6)
        ttk.Button(bar, text="EXPORT TARGET", command=self._export_target).pack(side="left")
        self._curve = HvsrCurveCanvas(tab_curve)
        self._curve.pack(fill="both", expand=True)
        self._curve.bind("<Button-3>", lambda e: self._export_png())

        tab_ts = ttk.Frame(self._nb)
        self._nb.add(tab_ts, text=" [ TIME SERIES ] ")
        self._ts = TimeSeriesCanvas(tab_ts)
        self._ts.pack(fill="both", expand=True)

        tab_spec = ttk.Frame(self._nb)
        self._nb.add(tab_spec, text=" [ PSD & SPECTRA ] ")
        bar = ttk.Frame(tab_spec)
        bar.pack(fill="x", pady=4)
        self._vars["spec_mode"] = tk.StringVar(value="PSD")
        ttk.Radiobutton(bar, text="PSD (dB)", value="PSD", variable=self._vars["spec_mode"], command=self._redraw_spectra).pack(side="left")
        ttk.Radiobutton(bar, text="FOURIER", value="Spectrum", variable=self._vars["spec_mode"], command=self._redraw_spectra).pack(side="left", padx=6)
        ttk.Button(bar, text="EXPORT PNG", command=self._export_spectra_png).pack(side="left", padx=12)
        self._spec = SpectraCanvas(tab_spec)
        self._spec.pack(fill="both", expand=True)

        tab_ses = ttk.Frame(self._nb)
        self._nb.add(tab_ses, text=" [ CHECKLIST ] ")
        self._sesame_frame = ttk.Frame(tab_ses, padding=16)
        self._sesame_frame.pack(fill="both", expand=True)
        self._sesame_items = []
        self._build_sesame_widgets()

        self._build_inversion_tab()

        # TERMINAL-STYLE REPORTS & LOGS
        tab_rep = ttk.Frame(self._nb)
        self._nb.add(tab_rep, text=" [ REPORT ] ")
        self._report = tk.Text(tab_rep, wrap="word", font=("Courier New", 10, "bold"), bg=BG, fg=TEXT_DARK, insertbackground=ACCENT)
        sb = ttk.Scrollbar(tab_rep, command=self._report.yview)
        self._report.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._report.pack(side="left", fill="both", expand=True)

        tab_log = ttk.Frame(self._nb)
        self._nb.add(tab_log, text=" [ SYSTEM LOG ] ")
        self._log = tk.Text(tab_log, wrap="word", font=("Courier New", 10, "bold"), bg=BG, fg=TEXT_DARK, insertbackground=ACCENT, state="disabled")
        sb2 = ttk.Scrollbar(tab_log, command=self._log.yview)
        self._log.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)

        self._status = ttk.Label(self, text="SYSTEM READY.", style="Sub.TLabel", anchor="w", padding=(14, 4))
        self._status.pack(fill="x")
        progrow = ttk.Frame(self, style="TFrame")
        progrow.pack(fill="x", pady=(0, 4))
        self._progress = ttk.Progressbar(progrow, mode="indeterminate")
        self._progress.pack(side="left", fill="x", expand=True, padx=(14, 0))
        self._progress_label = ttk.Label(progrow, text="", style="Sub.TLabel", anchor="e", padding=(10, 0))
        self._progress_label.pack(side="right", padx=(0, 14))

    def _build_sesame_widgets(self):
        self._sesame_items = []

    def _render_standard(self, std_id):
        for child in self._sesame_frame.winfo_children():
            child.destroy()
        self._sesame_items = []
        std = hvsr_standards.STANDARDS.get(std_id)
        if std is None:
            ttk.Label(self._sesame_frame, text="NO CHECKLIST AVAILABLE.", style="TLabel").pack(anchor="w")
            return
        ttk.Label(self._sesame_frame, text=std["name"], style="H.TLabel").pack(anchor="w")
        ttk.Label(self._sesame_frame, text=std["source"], style="Sub.TLabel", wraplength=760).pack(anchor="w", pady=(0, 6))

        ev = self._last_evals.get(std_id, {})
        items = ev.get("items") or []
        if not items:
            ttk.Label(self._sesame_frame, text="RUN ANALYSIS TO GENERATE CHECKLIST.", style="Sub.TLabel").pack(anchor="w")
            return
        for it in items:
            row = ttk.Frame(self._sesame_frame, style="TFrame")
            row.pack(fill="x", pady=3)
            ok = bool(it.get("ok"))
            # High contrast status boxes
            box = tk.Label(row, text=" [ OK ] " if ok else " [ WARN ] ", bg=OK_GREEN if ok else NO_RED, fg=BG, font=("Courier New", 10, "bold"), width=10)
            box.pack(side="left", padx=(0, 8))
            col = ttk.Frame(row, style="TFrame")
            col.pack(side="left")
            ttk.Label(col, text=it.get("label", ""), style="TLabel").pack(anchor="w")
            detail = it.get("desc", "")
            if it.get("detail"):
                detail += "  (" + it["detail"] + ")"
            ttk.Label(col, text=detail, style="Sub.TLabel").pack(anchor="w")
            self._sesame_items.append((box, it.get("key")))
            
        if std_id == "sesame" and items:
            core = [it for it in items if it.get("key") != "sigma_f_ok"]
            score = sum(1 for it in core if it.get("ok"))
            ttk.Label(self._sesame_frame, text=f"RELIABILITY SCORE: {score}/{len(core)} (SESAME CURVE + PEAK)", style="H.TLabel").pack(anchor="w", pady=(8, 0))

        if ev.get("vs30") is not None:
            ttk.Label(self._sesame_frame, text="Vs30 ESTIMATE: %.0f m/s -> NEHRP CLASS %s (%s)" % (ev["vs30"], ev.get("soil_class", "?"), ev.get("soil_desc", "")), style="TLabel").pack(anchor="w", pady=(10, 0))
        if ev.get("thickness") is not None:
            ttk.Label(self._sesame_frame, text="SEDIMENT DEPTH h (FROM f0): %.1f m" % ev["thickness"], style="TLabel").pack(anchor="w", pady=(2, 0))
        
        verdict = ev.get("verdict", "")
        vcol = OK_GREEN if ev.get("ok") else NO_RED
        ttk.Label(self._sesame_frame, text="VERDICT: " + verdict.upper(), foreground=vcol, font=("Courier New", 12, "bold")).pack(anchor="w", pady=(10, 0))

    def _set_sesame(self, crit):
        pass

    def _log_line(self, text):
        self._log.config(state="normal")
        self._log.insert("end", "> " + text + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _set_status(self, text, busy=None):
        self._status.config(text=text)
        if busy is not None:
            self._busy = busy
            if busy:
                self._progress_t0 = time.time()
                self._progress.config(mode="indeterminate")
                self._progress.start(10)
                self._progress_label.config(text="")
                self._run_btn.config(state="disabled")
                self._batch_btn.config(state="disabled")
            else:
                self._progress.stop()
                self._progress.config(mode="indeterminate", value=0)
                self._progress_label.config(text="")
                self._progress_t0 = None
                self._run_btn.config(state="normal")
                self._batch_btn.config(state="normal")

    def _set_progress(self, done, total, note=""):
        """Update the determinate progress bar with a live ETA."""
        try:
            total = max(int(total), 1)
            done = max(0, min(int(done), total))
        except (TypeError, ValueError):
            return
        frac = done / float(total)
        if self._progress.cget("mode") != "determinate":
            self._progress.stop()
            self._progress.config(mode="determinate", maximum=100.0, value=0.0)
        self._progress.config(value=round(frac * 100.0, 1))
        eta = ""
        t0 = getattr(self, "_progress_t0", None)
        if t0 is None:
            t0 = time.time()
            self._progress_t0 = t0
        if 0.02 < frac < 0.999:
            rem = (time.time() - t0) * (1.0 - frac) / frac
            eta = "   ETA %d:%02d" % (int(rem // 60), int(rem % 60))
        self._progress_label.config(
            text="%s %d/%d (%d%%)%s" % (note, done, total,
                                        int(round(frac * 100.0)), eta))

    def _themed(self, widget, key):
        """Track a widget whose explicit colour must follow theme switches."""
        if not hasattr(self, "_themed_widgets"):
            self._themed_widgets = []
        self._themed_widgets.append((widget, key))
        return widget

    def _set_theme(self):
        """Switch the whole application (widgets + charts + PNG export)
        between the retro dark theme and the black & white thesis theme."""
        name = self._vars["theme"].get()
        key = "bw" if name.startswith("B&W") else "dark"
        hvsr_theme.apply_theme(key)
        globals().update(hvsr_theme.current)   # re-bind ACCENT / BG / ... names
        self._build_style()                    # restyle every ttk widget
        # if the guided tour is open, refresh its palette with the new theme
        tour = getattr(self, "_tour", None)
        if tour is not None and getattr(tour, "active", False):
            try:
                tour._redraw()
            except Exception:
                pass
        self.configure(bg=BG)
        for w in (getattr(self, "_report", None), getattr(self, "_log", None),
                  getattr(self, "_inv_text", None)):
            if w is not None:
                try:
                    w.config(bg=BG, fg=TEXT_DARK, insertbackground=ACCENT)
                except Exception:
                    pass
        for w, k in getattr(self, "_themed_widgets", []):
            try:
                w.config(foreground=hvsr_theme.current[k])
            except Exception:
                pass
        tut = getattr(self, "_tutorial_win", None)
        if tut is not None and tut.winfo_exists():
            try:
                tut.configure(bg=BG)
                for c in tut.winfo_children():
                    if c.winfo_class() == "Text":
                        c.config(bg=BG, fg=TEXT_DARK, insertbackground=ACCENT)
            except Exception:
                pass
        import hvsr_plot as _hp
        import chart_render as _cr
        _hp.apply_palette()
        _cr.apply_palette()
        for c in (getattr(self, "_preview", None), getattr(self, "_filt", None),
                  getattr(self, "_sig", None), getattr(self, "_tf", None),
                  getattr(self, "_az", None), getattr(self, "_avg_spec", None),
                  getattr(self, "_avg_hv", None), getattr(self, "_curve", None),
                  getattr(self, "_ts", None), getattr(self, "_spec", None),
                  getattr(self, "_inv_canvas", None),
                  getattr(self, "_inv_hist", None)):
            if c is None:
                continue
            try:
                c.config(bg=hvsr_theme.current["CANVAS_BG"])
                redraw = getattr(c, "redraw", None)
                if callable(redraw):
                    redraw()
            except Exception:
                pass
        if getattr(self, "_last_evals", None):
            std_id = self._std_map.get(self._vars["std"].get(), "sesame")
            self._render_standard(std_id)
        self._log_line("THEME ACTIVE: %s" % name)
        tour = getattr(self, "_tour", None)
        if tour is not None and tour.active:
            try:
                tour._draw()
            except Exception:
                pass

    def _params(self):
        def f(key, cast=float):
            w = self._vars.get(key)
            if w is None:
                return None
            try:
                raw = w.get().strip()
            except AttributeError:
                raw = w
            if not raw:
                return None
            try:
                return cast(raw)
            except (ValueError, KeyError):
                return None
        auto = self._vars["param_mode"].get() == "auto"
        ov = f("overlap", int)
        return {
            "std_id": self._std_map.get(self._vars["std"].get(), "sesame"),
            "mode": "auto" if auto else "manual",
            "f_low": None if auto else f("f_low"),
            "f_high": None if auto else f("f_high"),
            "win_len": None if auto else f("win_len"),
            "overlap": (ov if ov is not None else 0) / 100.0,
            "rejection": None if auto else f("rejection"),
            "fmin": None if auto else f("fmin"),
            "fmax": None if auto else f("fmax"),
            "nfreq": f("nfreq", int),
            "b_value": None if auto else f("b_value"),
            "taper": None if auto else f("taper"),
            "max_iterations": None if auto else f("max_iterations", int),
            "sta_sec": None if auto else f("sta_sec"),
            "lta_sec": None if auto else f("lta_sec"),
            "slta_threshold": None if auto else f("slta_threshold"),
            "max_fs": None if auto else f("max_fs"),
            "t0": f("t0"),
            "t1": f("t1"),
            "smoothing": self._vars["smoothing"].get(),
            "smooth_width": None if auto else f("smooth_width"),
            "combo": self._vars["combo"].get(),
            "mute": self._vars["mute"].get(),
            "decimate": self._vars["decimate"].get(),
            "do_psd": self._vars["do_psd"].get(),
            "do_spec": self._vars["do_spec"].get(),
        }

    def _save_opts(self):
        return {
            "report": self._vars["sv_report"].get(),
            "target": self._vars["sv_target"].get(),
            "png": self._vars["sv_png"].get(),
            "csv": self._vars["sv_csv"].get(),
            "ask": self._vars["ask_save"].get(),
            "log": self._vars["log_csv"].get(),
        }

    def _read_files(self):
        z = self._vars["z_entry"].get().strip()
        n = self._vars["n_entry"].get().strip()
        e = self._vars["e_entry"].get().strip()
        files = [p for p in (z, n, e) if p]
        if not files:
            raise DataError("ERR: SELECT AT LEAST ONE DATA FILE (.eqd/.sg2/3-col)")
        explicit = (z, n, e) if (z and n and e) else None
        return files, explicit, self._vars["swap_h"].get()

    def _start_run(self):
        if self._busy:
            return
        try:
            files, explicit, swap_h = self._read_files()
            p = self._params()
            pz_path = self._vars["pz_entry"].get().strip()
            geo = (self._vars["geo_enable"].get(), self._vars["geo_path"].get())
            autotune = self._vars["autotune"].get()
            full_autotune = getattr(self, "_autotune_full", False)
            self._autotune_full = False
            opts = self._save_opts()
            out_dir = self._out_dir()
        except (ValueError, TypeError, DataError) as exc:
            messagebox.showerror("Input Error", str(exc))
            return
        self._set_status("EXECUTING ANALYSIS...", busy=True)
        self._log_line("=" * 60)
        self._log_line("INITIATING RUN SEQUENCE")
        threading.Thread(target=self._worker,
                         args=(files, explicit, swap_h, p, pz_path, geo,
                               autotune, full_autotune, opts, out_dir),
                         daemon=True).start()

    def _fill_defaults(self, p):
        for key, val in PARAM_DEFAULTS.items():
            if p.get(key) is None:
                p[key] = val
        return p

    def _worker(self, files, explicit, swap_h, p, pz_path, geo, autotune,
                full_autotune, opts, out_dir):
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

    def _resolve_auto(self, p, fs):
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

    def _on_std_change(self):
        if not _HAVE_STANDARDS:
            return
        std_id = self._std_map.get(self._vars["std"].get(), "sesame")
        rec = hvsr_standards.recommended_params(std_id)
        self._log_line("METHOD = %s | REC WINDOW %.0f s, REJECT %.1f, RANGE %.1f-%.1f Hz" % (self._vars["std"].get(), rec["win_len"], rec["rejection"], rec["fmin"], rec["fmax"]))
        if self._last_evals and std_id in self._last_evals:
            self._render_standard(std_id)

    def _station_name(self, data):
        base = data.source_name or "STATION"
        for ext in (".csv", ".txt", ".dat", ".asc", ".tsv", ".sac", ".mseed", ".miniseed", ".eqd", ".sg2"):
            if base.lower().endswith(ext):
                base = base[: -len(ext)]
                break
        return base or "STATION"

    def _out_dir(self):
        out = self._vars["out_entry"].get().strip()
        if not out:
            out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HVSR_Results")
        os.makedirs(out, exist_ok=True)
        return out

    def _analyze_one(self, clean, station, p, autotune, full_autotune=False):
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

    def _save_outputs(self, res, clean, station, out_dir, opts=None):
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

    def _append_data_log(self, res, clean, station, source, out_dir):
        import datetime as _dt
        path = os.path.join(out_dir, "data_log.csv")
        new = not os.path.exists(path)

        def esc(s):
            s = str(s)
            if "," in s or '"' in s or "\n" in s:
                return '"' + s.replace('"', '""') + '"'
            return s

        with open(path, "a", encoding="utf-8", newline="") as fh:
            if new:
                fh.write("timestamp,station,source,fs_hz,n_samples,window_len_s,rejection,f0_hz,A0,Kg,kg_level,windows_accepted,windows_total,bandpass_hz\n")
            fh.write("%s,%s,%s,%.1f,%d,%.1f,%.2f,%.4f,%.2f,%.2f,%s,%d,%d,%.1f-%.1f\n" % (
                         _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         esc(station), esc(source), clean.fs, clean.n_samples,
                         res.window_len, res.rejection, res.f0, res.a0, res.kg,
                         esc(res.kg_level), res.n_windows_accepted,
                         res.n_windows_total, res.f_low, res.f_high))

    def _on_done(self, res, clean, station, geo_freqs, geo_amps, opts, out_dir):
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

    def _poll_queue(self):
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
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    # ------------------------------------------------------------ helpers
    def _auto_assign(self):
        paths = filedialog.askopenfilenames(
            title="Select 1 file (3-column .eqd/.sg2/text) or 3 files (Z, N, E)",
            filetypes=[
                ("Seismic files", "*.mseed *.miniseed *.eqd *.sg2 *.csv "
                                  "*.txt *.dat *.asc *.tsv *.sac"),
                ("MiniSEED", "*.mseed *.miniseed"),
                (".eqd", "*.eqd"),
                ("SEG-2 (.sg2)", "*.sg2"),
                ("Text / CSV", "*.csv *.txt *.dat *.asc *.tsv *.sac"),
                ("All files", "*.*")])
        if not paths:
            return
        paths = list(paths)
        from hvsr_io import classify_component

        def _set(slot, path):
            w = self._vars[slot + "_entry"]
            w.delete(0, "end")
            w.insert(0, path or "")

        if len(paths) == 1:
            p0 = paths[0]
            ext = os.path.splitext(p0)[1].lower()
            if ext in (".eqd", ".sg2"):
                _set("z", p0)
                _set("n", "")
                _set("e", "")
                self._log_line("SINGLE %s DETECTED (Z/N/E AUTO): %s" % (ext, os.path.basename(p0)))
            elif ext in (".mseed", ".miniseed"):
                self._log_line("WARN: SINGLE MINISEED HOLDS ONE COMPONENT. SELECT ALL 3.")
                return
            else:
                _set("z", p0)
                _set("n", "")
                _set("e", "")
                self._log_line("SINGLE FILE DETECTED (MUST CONTAIN Z/N/E COLUMNS): " + os.path.basename(p0))
        elif len(paths) == 3:
            mapping = {c: None for c in "ZNE"}
            leftovers = []
            for p0 in paths:
                c = classify_component(p0)
                if c and mapping[c] is None:
                    mapping[c] = p0
                else:
                    leftovers.append(p0)
            missing = [c for c, p0 in mapping.items() if p0 is None]
            for c, p0 in zip(missing, leftovers):
                mapping[c] = p0
            if None in mapping.values():
                self._log_line("ERR: COULD NOT ASSIGN Z/N/E CHANNELS.")
                return
            for c, slot in (("Z", "z"), ("N", "n"), ("E", "e")):
                _set(slot, mapping[c])
            self._log_line("Z/N/E CHANNELS ASSIGNED.")
        else:
            self._log_line("ERR: SELECT EXACTLY ONE OR THREE FILES.")
            return
        self._refresh_preview()

    def _refresh_preview(self):
        try:
            files, explicit, swap_h = self._read_files()
        except DataError:
            self._preview.set_data([], 1.0)
            return
        threading.Thread(target=self._preview_worker, args=(files, explicit, swap_h), daemon=True).start()

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

    # ------------------------------------------------------- signal analysis
    def _analyse_signal(self):
        if self._busy:
            return
        try:
            files, explicit, swap_h = self._read_files()
        except DataError as exc:
            messagebox.showerror("Input Error", str(exc))
            return
        self._set_status("ANALYSING SIGNAL...", busy=True)
        threading.Thread(target=self._sig_worker, args=(files, explicit, swap_h), daemon=True).start()

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

    # --------------------------------------------------- filtered preview
    def _preview_filtered(self):
        if self._busy:
            return
        try:
            files, explicit, swap_h = self._read_files()
            p = self._params()
        except (ValueError, TypeError, DataError) as exc:
            messagebox.showerror("Input Error", str(exc))
            return
        try:
            win = float(self._vars["pv_win"].get() or 0.0)
        except ValueError:
            win = 0.0
        self._set_status("FILTERING PREVIEW...", busy=True)
        threading.Thread(target=self._filt_worker, args=(files, explicit, swap_h, p, win), daemon=True).start()

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

    # --------------------------------------------------- H/V analysis views
    def _preview_hv_views(self):
        if self._busy:
            return
        try:
            files, explicit, swap_h = self._read_files()
            p = self._params()
        except (ValueError, TypeError, DataError) as exc:
            messagebox.showerror("Input Error", str(exc))
            return
        self._set_status("COMPUTING H/V VIEWS...", busy=True)
        threading.Thread(target=self._hv_worker, args=(files, explicit, swap_h, p), daemon=True).start()

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

    def _apply_hv_views(self, res, sp, tf, az):
        times, freqs, tf_grid = tf
        azi, afreqs, az_grid = az
        self._tf.set_data(times, freqs, tf_grid, title="H/V VS TIME", ylabel="TIME (s)")
        self._az.set_data(azi, afreqs, az_grid, title="H/V VS AZIMUTH", ylabel="AZIMUTH (deg)")
        self._avg_spec.set_data(sp["freqs"], sp["psd"], mode="PSD", station=res.station)
        self._avg_hv.set_data(res.freqs, res.mean, res.low, res.high, res.f0, res.a0, station=res.station)

    def _detect_geopsy(self):
        p = hvsr_geopsy.find_geopsy()
        if p:
            self._vars["geo_path"].set(p)
            self._vars["geo_enable"].set(True)
            self._log_line("GEOPSY DETECTED: " + p)
        else:
            messagebox.showinfo("Geopsy", "GEOPSY NOT FOUND.")

    def _load_sample(self):
        try:
            import make_sample_data
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
            p = make_sample_data.write_station(folder)
            self._vars["z_entry"].delete(0, "end")
            self._vars["z_entry"].insert(0, p)
            for slot in ("n", "e"):
                self._vars[slot + "_entry"].delete(0, "end")
            self._log_line("SAMPLE DATA MOUNTED: " + p)
            self._log_line("INITIATE RUN SEQUENCE TO VERIFY.")
            self._refresh_preview()
        except Exception as exc:
            messagebox.showerror("Sample data Error", str(exc))

    def _show_help(self):
        text = (
            "HVSR ANALYZER HELP\n"
            "==================\n\n"
            "01. MOUNT SIGNAL DATA:\n"
            "     - .sg2 (SEG-2)\n"
            "     - .eqd\n"
            "     - 3-column text/csv\n"
            "     - 3 distinct files (Z/N/E)\n\n"
            "02. (OPTIONAL) Mount SAC pole-zero (.pz) file.\n\n"
            "03. PARAMETER CONTROL:\n"
            "    Use AUTO to let the program select, or MANUAL to adjust window, overlap, rejection, etc.\n\n"
            "04. EXECUTE RUN SEQUENCE.\n\n"
            "All signal processing relies strictly on standard python libraries."
        )
        messagebox.showinfo("SYS_HELP", text)

    def _open_tutorial(self):
        """Open the bundled first-time-user tutorial (docs/TUTORIAL.md)
        in a scrollable window."""
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = (os.path.join(here, "..", "docs", "TUTORIAL.md"),
                      os.path.join(here, "docs", "TUTORIAL.md"))
        path = None
        for c in candidates:
            if os.path.isfile(c):
                path = os.path.normpath(c)
                break
        if not path:
            messagebox.showinfo("TUTORIAL", "TUTORIAL.md not found next to the app - see docs/TUTORIAL.md in the project folder.")
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception as exc:
            messagebox.showerror("TUTORIAL", "Cannot read tutorial: %s" % exc)
            return
        win = tk.Toplevel(self)
        win.title("HVSR Analyzer - Tutorial")
        win.geometry("780x640")
        win.configure(bg=BG)
        self._tutorial_win = win
        text = tk.Text(win, wrap="word", font=("Consolas", 10),
                       bg=BG, fg=TEXT_DARK, insertbackground=ACCENT)
        sb = ttk.Scrollbar(win, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", content)
        text.config(state="disabled")
        self._themed((text, "TEXT_DARK"), "TEXT_DARK")
        self._log_line("TUTORIAL OPENED: " + path)

    def _start_tour(self):
        """Launch the guided first-run tour overlay (box + arrow, step by
        step).  Also reachable from the SHOW TOUR header button."""
        if self._busy:
            return
        if getattr(self, "_tour", None) is not None and self._tour.active:
            return
        try:
            self._tour = TourOverlay(self, self._tour_steps())
            self._tour.start()
            self._log_line("GUIDED TOUR STARTED (use Next / Back / Skip).")
        except Exception as exc:
            self._log_line("TOUR ERR: %s" % exc)

    def _on_tour_closed(self):
        self._log_line("GUIDED TOUR CLOSED.")
        try:
            flag = os.path.join(os.path.expanduser("~"), ".hvsr_tour_done")
            with open(flag, "w", encoding="utf-8") as fh:
                fh.write("1\n")
        except Exception:
            pass

    def _tour_steps(self):
        """Step definitions for the guided tour overlay.  Each step can
        switch the left-panel page and/or the results tab before its
        spotlight target is measured."""
        v = self._vars
        return [
            {"title": "Welcome to HVSR Analyzer",
             "text": "This is a complete Horizontal-to-Vertical Spectral "
                     "Ratio (HVSR) microtremor analysis program.  The "
                     "4-step workflow on the left prepares the signal, the "
                     "result tabs on the right show the H/V curve, and the "
                     "1D inversion builds a soil model.  This tour explains "
                     "what each feature does - press Next to walk through "
                     "it, or Skip to close.", "target": None},
            {"title": "Load a signal",
             "text": "Start here: load your recording - one 3-column file "
                     "(.eqd, .sg2, text/CSV) or three component files "
                     "(Z, N, E); miniSEED works too.  LOAD SAMPLE DATA loads "
                     "the bundled 2 Hz example if you have no field data "
                     "yet.", "target": getattr(self, "_load_btn", None)},
            {"title": "Input files & output folder",
             "text": "Set the VERTICAL / NORTH / EAST files (or one "
                     "3-column file), optionally a SAC pole-zero response "
                     "file, and choose where results are saved below.  SWAP "
                     "N/E fixes recordings whose channels are crossed.",
             "page": 0, "target": v.get("z_entry")},
            {"title": "Time range",
             "text": "Leave START / END empty to use the whole recording, "
                     "or type seconds to analyse only the calmest part.  "
                     "Fewer samples also means a faster analysis.",
             "page": 0, "target": v.get("t0")},
            {"title": "Pre-processing & decimation",
             "text": "STA/LTA muting removes transients.  DECIMATE IF RATE "
                     "> 250 Hz downsamples high-rate recorders - this alone "
                     "can cut the analysis time several times with no loss "
                     "of low-frequency information.", "page": 1,
             "target": getattr(self, "_decimate_cb", None)},
            {"title": "H/V parameters",
             "text": "The WINDOW length and REJECTION factor follow SESAME "
                     "guidelines; frequency band, smoothing and H/V formula "
                     "are adjustable.  APPLY METHOD RECS fills them from the "
                     "selected standard.", "page": 2,
             "target": v.get("win_len_w")},
            {"title": "Auto-tune (quick)",
             "text": "Tick AUTO-TUNE WINDOW/REJECT to sweep window lengths "
                     "x rejection factors (up to 8 analyses) and keep the "
                     "most reliable SESAME result.", "page": 2,
             "target": getattr(self, "_autotune_cb", None)},
            {"title": "Auto-tune MAX RELIABILITY",
             "text": "The full sweep also tries every smoothing operator, "
                     "width and H/V combination (up to 32 analyses) for the "
                     "most reliable curve possible.  It shows live progress "
                     "with an ETA and uses all CPU cores - set the "
                     "HVSR_WORKERS environment variable to cap that.",
             "page": 2, "target": getattr(self, "_full_at_btn", None)},
            {"title": "Run the analysis",
             "text": "INITIATE RUN SEQUENCE runs the whole pipeline: "
                     "pre-processing, windowing, H/V curve, SESAME "
                     "reliability, and saves the report, PNG and data files "
                     "to the output folder.", "page": 3,
             "target": self._run_btn},
            {"title": "Result tabs",
             "text": "Every result appears in the tabs on the right: H/V "
                     "CURVE with f0 and A0, TIME SERIES, PSD & SPECTRA, the "
                     "SESAME CHECKLIST, the full REPORT and the SYSTEM LOG.",
             "nb_tab": "H/V CURVE", "target": self._nb},
            {"title": "1D inversion",
             "text": "RUN 1D INVERSION turns the H/V curve into a layered "
                     "soil model: a Monte-Carlo search (600 models by "
                     "default, parallelised across CPU cores) matches the "
                     "theoretical Rayleigh-wave ellipticity, then reports "
                     "layer Vs, Vs30 and the soil class.",
             "nb_tab": "1D INVERSION", "target": getattr(self, "_inv_run_btn", None)},
            {"title": "Theme, tutorial & help",
             "text": "Switch THEME between the dark look and the Black & "
                     "White thesis theme (every exported PNG follows), and "
                     "re-open this tour, the written tutorial or HELP any "
                     "time from the header.",
             "target": getattr(self, "_theme_cb", None)},
        ]

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

    # ------------------------------------------- preview exports (new views)
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

    # ------------------------------------------- parameter profiles (JSON)
    _PROFILE_KEYS = (
        "f_low", "f_high", "mute", "sta_sec", "lta_sec", "slta_threshold", "decimate", "max_fs",
        "win_len", "overlap", "rejection", "fmin", "fmax", "nfreq", "smoothing", "smooth_width", 
        "b_value", "taper", "max_iterations", "combo", "autotune", "std",
    )

    def _profile_values(self):
        out = {"app": "HVSR Analyzer", "version": 1, "mode": self._vars["param_mode"].get(), "parameters": {}}
        for key in self._PROFILE_KEYS:
            w = self._vars.get(key + "_w") or self._vars.get(key)
            if w is None:
                continue
            try:
                out["parameters"][key] = w.get().strip()
            except AttributeError:
                out["parameters"][key] = str(w.get())
        return out

    def _save_params(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON profile", "*.json")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(self._profile_values(), fh, indent=2)
            self._log_line("PROFILE SAVED TO " + p)
        except OSError as exc:
            messagebox.showerror("Save profile Error", str(exc))

    def _load_params(self):
        p = filedialog.askopenfilename(filetypes=[("JSON profile", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Load profile Error", str(exc))
            return
        if isinstance(data, dict):
            mode = data.get("mode", "manual")
            if mode in ("manual", "auto"):
                self._vars["param_mode"].set(mode)
            raw = data.get("parameters", data)
        else:
            raw = {}
        params = raw if isinstance(raw, dict) else {}
        n = 0
        for key, val in params.items():
            if key in self._PROFILE_KEYS:
                self._set_param(key, val)
                n += 1
        self._on_std_change()
        self._toggle_param_mode()
        self._log_line("PROFILE LOADED FROM " + p + " (%d PARAMS)" % n)

    def _start_batch(self):
        if self._busy:
            return
        folder = filedialog.askdirectory(title="Select folder of station subfolders")
        if not folder:
            return
        try:
            p = self._params()
            autotune = self._vars["autotune"].get()
            opts = self._save_opts()
            opts["ask"] = False 
            out_dir = self._out_dir()
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Input Error", str(exc))
            return
        self._set_status("BATCH PROCESSING...", busy=True)
        self._log_line("=" * 60)
        self._log_line("BATCH TARGET: " + folder)
        threading.Thread(target=self._batch_worker, args=(folder, p, autotune, opts, out_dir, self._vars["swap_h"].get()), daemon=True).start()

    def _batch_worker(self, folder, p, autotune, opts, out_dir, swap_h):
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

    def _use_full_time(self):
        for key in ("t0", "t1"):
            w = self._vars.get(key)
            if w is not None:
                w.delete(0, "end")
        self._log_line("TIME RANGE RESET TO FULL RECORDING.")

    def _parallel_workers(self, cap=8):
        """Worker-process count for the parallel parameter sweeps.

        The HVSR_WORKERS environment variable overrides everything
        (set it to 1 to force sequential mode on busy machines).
        Otherwise the CPU count is used, capped at `cap`.
        """
        return resolve_workers(os.cpu_count() or 2, cap=cap)

    def _start_full_autotune(self):
        if self._busy:
            return
        self._autotune_full = True
        self._log_line("MAX-RELIABILITY AUTO-TUNE ENABLED. COMMENCING FULL "
                       "PARAMETER SWEEP (%d WORKERS)."
                       % self._parallel_workers())
        self._start_run()

    # ------------------------------------------------- 1D inversion
    def _build_inversion_tab(self):
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

    def _start_inversion(self):
        if self._busy:
            return
        if not self._last:
            messagebox.showinfo("1D Inversion Error", "RUN HVSR ANALYSIS FIRST.")
            return
        res = self._last[0]
        if not res.freqs or not res.mean:
            messagebox.showinfo("1D Inversion Error", "NO H/V CURVE AVAILABLE.")
            return
        try:
            n_layers = int(self._inv_vars["layers"].get().strip() or "3")
            n_iter = int(self._inv_vars["iter"].get().strip() or "600")
            poisson = float(self._inv_vars["poisson"].get().strip() or "0.40")
        except ValueError:
            messagebox.showerror("1D Inversion Error", "LAYERS/ITERATIONS/POISSON MUST BE NUMERIC.")
            return
        if not (1 <= n_layers <= 6):
            messagebox.showerror("1D Inversion Error", "LAYERS MUST BE [1-6].")
            return
        station = self._last[2]
        vs30_anchor = None
        try:
            vs30_anchor = res.standards["sesame"]["vs30"]
        except Exception:
            pass
        self._set_status("INVERTING H/V CURVE...", busy=True)
        self._log_line("INITIATING 1D INVERSION (%d LAYERS, %d MODELS, %d WORKERS)" % (n_layers, n_iter, self._parallel_workers()))
        threading.Thread(
            target=self._inversion_worker,
            args=(res, station, n_layers, n_iter, poisson,
                  self._inv_vars["monotonic"].get(), vs30_anchor),
            daemon=True).start()

    def _inversion_worker(self, res, station, n_layers, n_iter, poisson,
                          monotonic, vs30_anchor):
        try:
            from hvsr_inversion import invert_hvsr
            def progress(done, total):
                self._queue.put(("progress", (done, total, "1D INVERSION")))
                if done % 100 == 0:
                    self._queue.put(("log", "INVERSION PROGRESS: %d/%d MODELS" % (done, total)))
            inv = invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                              station=station, n_layers=n_layers,
                              n_iter=n_iter, poisson=poisson,
                              vs30_anchor=vs30_anchor, monotonic=monotonic,
                              progress_cb=progress,
                              n_workers=self._parallel_workers())
            self._queue.put(("inv_done", inv))
        except Exception as exc:
            self._queue.put(("error", "INVERSION ERR: %s" % exc))

    def _on_inversion_done(self, inv):
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
        if not getattr(self, "_last_inv", None):
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if p:
            from hvsr_inversion import write_inversion_report
            write_inversion_report(p, self._last_inv)
            self._log_line("INVERSION REPORT SAVED TO " + p)

    def _export_inv_csv(self):
        if not getattr(self, "_last_inv", None):
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p:
            from hvsr_inversion import write_inversion_csv
            write_inversion_csv(p, self._last_inv)
            self._log_line("INVERSION MODEL CSV SAVED TO " + p)

    def _on_idle(self):
        self._set_status("BATCH SEQUENCE COMPLETE.", busy=False)


def main():
    flag = os.path.join(os.path.expanduser("~"), ".hvsr_tour_done")
    first_run = not os.path.exists(flag) or os.environ.get("HVSR_TOUR") == "1"
    app = HVSRApp(show_tour=first_run)
    app.mainloop()


if __name__ == "__main__":
    main()
