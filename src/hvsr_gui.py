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

import os
import queue
import sys
import tkinter as tk
# messagebox / filedialog are imported (and re-exported) so callers and the
# test suite can reach - and patch - the exact dialog objects the GUI uses.
from tkinter import filedialog, messagebox  # noqa: F401

import hvsr_theme
from hvsr_io import DataError  # noqa: F401  (re-exported for callers/tests)

from hvsr_gui_assoc import HVSRAppAssocMixin
from hvsr_gui_dnd import DND_AVAILABLE, TK_BASE, HVSRAppDndMixin
from hvsr_gui_core import HVSRAppCore
from hvsr_gui_theme import HVSRAppThemeMixin
from hvsr_gui_pump import HVSRAppPumpMixin
from hvsr_gui_pages import HVSRAppPagesMixin
from hvsr_gui_style import HVSRAppStyleMixin
from hvsr_gui_layout import HVSRAppLayoutMixin
from hvsr_gui_workflow import HVSRAppWorkflowMixin
from hvsr_gui_standards import HVSRAppStandardsMixin
from hvsr_gui_checklist import HVSRAppChecklistMixin
from hvsr_gui_actions import HVSRAppActionsMixin
from hvsr_gui_runners import HVSRAppRunnersMixin
from hvsr_gui_workers import HVSRAppWorkersMixin
from hvsr_gui_workhelpers import HVSRAppWorkHelpersMixin
from hvsr_gui_previews import HVSRAppPreviewsMixin
from hvsr_gui_exports import HVSRAppExportsMixin
from hvsr_gui_profiles import HVSRAppProfilesMixin
from hvsr_gui_inversion import HVSRAppInversionMixin
from hvsr_gui_invworker import HVSRAppInvWorkerMixin
from hvsr_gui_tour import HVSRAppTourMixin

BG = hvsr_theme.current["BG"]

# Tkinter cannot accept OS-level file drops with the standard library alone.
# When the optional tkinterdnd2 package is present (bundled in the installer
# build, see build_exe.py) the window becomes a drop target; without it the
# app is a plain tk.Tk and works exactly as before.
_TK_BASE = TK_BASE if DND_AVAILABLE else tk.Tk


class HVSRApp(_TK_BASE, HVSRAppCore, HVSRAppThemeMixin, HVSRAppPumpMixin,
              HVSRAppPagesMixin, HVSRAppStyleMixin, HVSRAppLayoutMixin,
              HVSRAppWorkflowMixin,
              HVSRAppStandardsMixin, HVSRAppChecklistMixin, HVSRAppActionsMixin,
              HVSRAppRunnersMixin, HVSRAppWorkersMixin, HVSRAppWorkHelpersMixin,
              HVSRAppPreviewsMixin, HVSRAppExportsMixin, HVSRAppProfilesMixin,
              HVSRAppDndMixin, HVSRAppAssocMixin, HVSRAppTourMixin,
              HVSRAppInversionMixin, HVSRAppInvWorkerMixin):
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


def main():
    """Create the app and enter the tkinter main loop.

    The first-run guided tour shows once, remembered via a flag file in the
    user's home directory (or every time when HVSR_TOUR=1).  Any recording
    paths passed on the command line - e.g. double-clicking an associated
    file, see installer/HVSR_Analyzer_Setup.iss - are mounted after
    startup, exactly like a drag-and-drop (one file, or a Z/N/E trio).
    """
    flag = os.path.join(os.path.expanduser("~"), ".hvsr_tour_done")
    first_run = not os.path.exists(flag) or os.environ.get("HVSR_TOUR") == "1"
    open_files = [a for a in sys.argv[1:] if os.path.isfile(a)]
    app = HVSRApp(show_tour=first_run and not open_files)
    if open_files:
        app.after(150, lambda: _mount_startup_files(app, open_files))
    app.mainloop()


def _mount_startup_files(app, paths):
    """Mount command-line files once the window exists.  Guarded so a bad
    path can never take the app down at startup."""
    try:
        app._mount_cli(paths)
    except Exception as exc:  # noqa: BLE001
        try:
            app._log_line("SYS_ERR: could not open: " + str(exc))
        except Exception:
            pass


if __name__ == "__main__":
    main()
