"""
hvsr_gui_profiles.py
====================
Parameter profiles and the batch data-log for the HVSR Analyzer GUI.

HVSRAppProfilesMixin: _profile_values collects the current parameter
values, _save_params / _load_params persist them to JSON profile files,
and _append_data_log appends one finished run to the shared
data_log.csv.  The report / PNG / CSV savers live in hvsr_gui_exports.py.
"""


import json
import os
from tkinter import filedialog, messagebox


class HVSRAppProfilesMixin:
    _PROFILE_KEYS = (
        "f_low", "f_high", "mute", "sta_sec", "lta_sec", "slta_threshold", "decimate", "max_fs",
        "win_len", "overlap", "rejection", "fmin", "fmax", "nfreq", "smoothing", "smooth_width", 
        "b_value", "taper", "max_iterations", "combo", "autotune", "std",
    )

    def _append_data_log(self, res, clean, station, source, out_dir):
        """Append one run to data_log.csv (creating it with a header on the
        first run).  Values are CSV-escaped so station names with commas or
        quotes do not corrupt the log."""
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
        """SAVE... (parameter profile): write every analysis parameter to a
        JSON file so a tuned setup can be reused or shared."""
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
        """LOAD... (parameter profile): restore the fields from a saved
        JSON profile and refresh the method checklist accordingly."""
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
