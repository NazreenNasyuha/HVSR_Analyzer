"""
hvsr_gui_layout.py
==================
Window frame builders for the HVSR Analyzer GUI.

HVSRAppLayoutMixin: _build_ui() assembles the window - the header bar
(_build_header), the four-tab notebook shell (_build_pages_shell) and
the right-hand results panel (_build_right_panel: H/V curve, time
series, spectra, checklist, inversion, report, log).  The four workflow
pages that fill the notebook moved to hvsr_gui_workflow.py; the style /
card / scroll helpers live in hvsr_gui_pages.py (HVSRAppPagesMixin).
"""


import tkinter as tk
from tkinter import ttk

import hvsr_theme
from hvsr_plot import (HvsrCurveCanvas, TimeSeriesCanvas, SpectraCanvas)

# Local aliases of the active theme palette.  They are refreshed by
# HVSRAppCore._set_theme() when the user switches theme live, so widgets
# restyled after a switch pick up the new colours.
ACCENT = hvsr_theme.current["ACCENT"]
BG = hvsr_theme.current["BG"]
TEXT_DARK = hvsr_theme.current["TEXT_DARK"]


class HVSRAppLayoutMixin:
    def _build_header(self):
        """Header bar: title, sample-data / help / tutorial / tour buttons
        and the live THEME selector."""

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

    def _build_pages_shell(self):
        """Left column: the four-tab notebook that hosts the workflow pages.
        Returns the four page frames so each page builder can fill them."""

        main = ttk.Frame(self, style="TFrame")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        left = ttk.Frame(main, style="TFrame", width=478)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._right = ttk.Frame(main, style="TFrame")
        self._right.pack(side="left", fill="both", expand=True)

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
        return p_in, p_pre, p_hv, p_out

    def _build_right_panel(self):
        """Right panel: the results tabs (H/V curve, time series, spectra,
        checklist, inversion, report, system log) and the status strip."""

        self._nb = ttk.Notebook(self._right)
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

    def _build_ui(self):
        """Assemble the whole window: header bar, the four workflow
        pages in the left notebook, and the results panel on the right.
        Each piece is built by its own method so the layout reads
        top-to-bottom like the window itself."""
        self._build_header()
        p_in, p_pre, p_hv, p_out = self._build_pages_shell()
        self._build_page1(p_in, p_out)
        self._build_page2(p_pre)
        self._build_page3(p_hv)
        self._build_page4(p_out)
        for page in self._page_frames:
            self._bind_page_wheel(page)
        self._build_right_panel()
        # drag & drop registration must run last, after every widget exists
        self._register_drop_target()
