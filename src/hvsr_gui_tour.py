"""
hvsr_gui_tour.py
===============
Guided tour and tutorial window for the HVSR Analyzer GUI.

The tour steps live here too, so editing what the first-run
walkthrough says never touches the rest of the UI.  The overlay widget
itself is hvsr_tour.TourOverlay.

Split out of hvsr_gui.py; mixed into HVSRApp as HVSRAppTourMixin.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox

import hvsr_theme
from hvsr_tour import TourOverlay

# Local aliases of the active theme palette.  They are refreshed by
# HVSRAppCore._set_theme() when the user switches theme live, so widgets
# restyled after a switch pick up the new colours.
ACCENT = hvsr_theme.current["ACCENT"]
BG = hvsr_theme.current["BG"]
PANEL_BG = hvsr_theme.current["PANEL_BG"]
TEXT_DARK = hvsr_theme.current["TEXT_DARK"]
TEXT_MUTED = hvsr_theme.current["TEXT_MUTED"]
OK_GREEN = hvsr_theme.current["OK_GREEN"]
NO_RED = hvsr_theme.current["NO_RED"]
HOVER = hvsr_theme.current["HOVER"]



class HVSRAppTourMixin:
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
