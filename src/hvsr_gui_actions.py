"""
hvsr_gui_actions.py
===================
User-action handlers for the HVSR Analyzer GUI: file browsing,
parameter-mode toggling, method recommendations, the live previews
(waveform, filtered, signal analysis, H/V views), sample data, Geopsy
detection and help.  These methods only decide *what* should happen and
hand the work to the worker mixins; they never touch charts directly.
The run / batch starters moved to hvsr_gui_runners.py.  Mixed into
HVSRApp as HVSRAppActionsMixin.
"""


import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import hvsr_geopsy
from hvsr_io import DataError

try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False


class HVSRAppActionsMixin:
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

    def _refresh_preview(self):
        """Kick off a background re-read of the assigned files so the
        waveform preview at the bottom of the input page stays in sync."""
        try:
            files, explicit, swap_h = self._read_files()
        except DataError:
            self._preview.set_data([], 1.0)
            return
        threading.Thread(target=self._preview_worker, args=(files, explicit, swap_h), daemon=True).start()

    def _analyse_signal(self):
        """ANALYSE SIGNAL button: preview PSD / spectrum / coherence of the
        raw waveform without running the full analysis."""
        if self._busy:
            return
        try:
            files, explicit, swap_h = self._read_files()
        except DataError as exc:
            messagebox.showerror("Input Error", str(exc))
            return
        self._set_status("ANALYSING SIGNAL...", busy=True)
        threading.Thread(target=self._sig_worker, args=(files, explicit, swap_h), daemon=True).start()

    def _preview_filtered(self):
        """PREVIEW FILTERED button: run just the pre-processing chain
        (detrend, band-pass, STA/LTA mute, decimation) on a capped excerpt
        and draw the cleaned traces with the analysis window overlaid."""
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

    def _preview_hv_views(self):
        """PREVIEW H/V VIEWS button: compute the four interactive charts
        (time-frequency map, azimuth map, average spectra, average H/V)
        with the current parameters, without saving anything."""
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

    def _detect_geopsy(self):
        p = hvsr_geopsy.find_geopsy()
        if p:
            self._vars["geo_path"].set(p)
            self._vars["geo_enable"].set(True)
            self._log_line("GEOPSY DETECTED: " + p)
        else:
            messagebox.showinfo("Geopsy", "GEOPSY NOT FOUND.")

    def _load_sample(self):
        """LOAD SAMPLE DATA button: generate the bundled synthetic 2 Hz
        test station into src/sample_data and mount it as the Z file."""
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

    def _use_full_time(self):
        for key in ("t0", "t1"):
            w = self._vars.get(key)
            if w is not None:
                w.delete(0, "end")
        self._log_line("TIME RANGE RESET TO FULL RECORDING.")
