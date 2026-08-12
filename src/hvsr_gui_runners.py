"""
hvsr_gui_runners.py
===================
Run / batch starters for the HVSR Analyzer GUI.

HVSRAppRunnersMixin: the button handlers that kick off analysis -
_start_run (single station), _start_batch (folder sweep) and
_start_full_autotune (the max-reliability sweep, a _start_run variant).
They gather the parameters, validate the inputs and spawn the daemon
worker threads; the workers themselves live in hvsr_gui_workers.py.
"""


import threading
from tkinter import filedialog, messagebox

from hvsr_io import DataError


class HVSRAppRunnersMixin:
    def _start_run(self):
        """Button handler for INITIATE RUN SEQUENCE: validate the inputs on
        the UI thread, then hand the work to a daemon worker thread."""
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

    def _start_batch(self):
        """BATCH PROCESS FOLDER button: pick a folder of station subfolders
        and analyse every compatible recording in it on a worker thread."""
        if self._busy:
            return
        folder = filedialog.askdirectory(title="Select folder of station subfolders")
        if folder:
            self._run_batch(folder)

    def _run_batch(self, folder):
        """Start a batch analysis of ``folder`` on a worker thread.

        Shared by the BATCH PROCESS FOLDER button (via _start_batch) and
        by dropping a folder onto the window.  Guarded so a second batch
        can never start while one is already running (the drop path calls
        this directly, bypassing _start_batch's pre-dialog check)."""
        if self._busy:
            self._log_line("SYS_ERR: analysis already running - wait for it "
                           "to finish before starting another batch")
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

    def _start_full_autotune(self):
        """AUTO-TUNE MAX RELIABILITY... button: flag the next run to do the
        full smoothing / width / H/V-combination sweep."""
        if self._busy:
            return
        self._autotune_full = True
        self._log_line("MAX-RELIABILITY AUTO-TUNE ENABLED. COMMENCING FULL "
                       "PARAMETER SWEEP (%d WORKERS)."
                       % self._parallel_workers())
        self._start_run()
