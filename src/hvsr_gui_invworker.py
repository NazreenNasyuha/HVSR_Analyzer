"""
hvsr_gui_invworker.py
=====================
The 1D-inversion run logic for the HVSR Analyzer GUI: _start_inversion
validates the inputs and spawns the worker thread, and _inversion_worker
runs the Monte-Carlo search off the UI thread, reporting progress and the
finished model through the message queue.  The tab UI, result rendering
and exports live in hvsr_gui_inversion.py.  Mixed into HVSRApp as
HVSRAppInvWorkerMixin.
"""


import threading
from tkinter import messagebox


class HVSRAppInvWorkerMixin:
    def _start_inversion(self):
        """RUN 1D INVERSION button: validate inputs, seed from the last H/V
        result, then run the Monte-Carlo inversion on a worker thread."""
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
        """Background thread for the 1D inversion; reports progress every
        100 models and posts the finished model via the queue."""
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
