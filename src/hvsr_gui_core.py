"""
hvsr_gui_core.py
================
Shared GUI services for the HVSR Analyzer GUI (pure standard library).

The HVSRApp core mixin: the system log / status / progress strip,
parameter reading, save options, input-file handling, the output-folder
helper and the worker-count helper.  The queue-based message pump moved
to hvsr_gui_pump.py and the live theme system to hvsr_gui_theme.py.
Mixed into HVSRApp in hvsr_gui.py.
"""


import os
import sys
import time

from hvsr_dsp import resolve_workers
from hvsr_io import DataError


class HVSRAppCore:
    def _log_line(self, text):
        """Append one line to the SYSTEM LOG tab (thread-safe only when
        called from the UI thread; worker threads must go through the queue)."""
        self._log.config(state="normal")
        self._log.insert("end", "> " + text + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _notify_done(self):
        """Draw attention when a long batch finishes: beep and flash the
        taskbar button (Windows).  Best-effort - never raises."""
        try:
            self.bell()
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                import ctypes

                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                if not hwnd:
                    hwnd = self.winfo_id()

                class _FLASHWINFO(ctypes.Structure):
                    _fields_ = [("cbSize", ctypes.c_uint),
                                ("hwnd", ctypes.c_void_p),
                                ("dwFlags", ctypes.c_uint),
                                ("uCount", ctypes.c_uint),
                                ("dwTimeout", ctypes.c_uint)]

                # FLASHW_ALL = 3: flash caption + taskbar button
                info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), hwnd, 3, 3, 0)
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
            except Exception:
                pass

    def _set_status(self, text, busy=None):
        """Update the status strip; when busy, lock the run buttons and start
        the indeterminate progress spinner (and unlock them again when done)."""
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

    def _params(self):
        """Read every processing field into a plain dict for the engine.

        In Auto mode the parameter fields are left None (the engine fills
        them); in Manual mode they are parsed from the entry widgets.  A
        missing / unparseable field yields None rather than crashing.
        """
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
        """Collect the Z / N / E file paths from the entry widgets.

        Returns (files, explicit, swap_h): files is the list of non-empty
        paths, explicit is the 3-tuple when all three are given (None
        otherwise, letting auto_load route by content), and swap_h is the
        Swap N/E checkbox state.
        """
        z = self._vars["z_entry"].get().strip()
        n = self._vars["n_entry"].get().strip()
        e = self._vars["e_entry"].get().strip()
        files = [p for p in (z, n, e) if p]
        if not files:
            raise DataError("ERR: SELECT AT LEAST ONE DATA FILE (.eqd/.sg2/3-col)")
        explicit = (z, n, e) if (z and n and e) else None
        return files, explicit, self._vars["swap_h"].get()

    def _out_dir(self):
        out = self._vars["out_entry"].get().strip()
        if not out:
            if getattr(sys, "frozen", False):
                # Packaged app (PyInstaller --onedir): put results next to the
                # exe.  In a frozen build __file__ points into the internal
                # bundle directory, which is not where users expect data, and
                # the installer's uninstall cleanup only watches the exe dir.
                base = os.path.dirname(os.path.abspath(sys.executable))
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            out = os.path.join(base, "HVSR_Results")
        os.makedirs(out, exist_ok=True)
        return out

    def _parallel_workers(self, cap=8):
        """Worker-process count for the parallel parameter sweeps.

        The HVSR_WORKERS environment variable overrides everything
        (set it to 1 to force sequential mode on busy machines).
        Otherwise the CPU count is used, capped at `cap`.
        """
        return resolve_workers(os.cpu_count() or 2, cap=cap)
