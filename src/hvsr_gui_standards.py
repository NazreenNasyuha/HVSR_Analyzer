"""
hvsr_gui_standards.py
=====================
Standard-selector logic for the HVSR Analyzer GUI: the handler that
responds to the guideline-standard picker (logging the recommended
parameters and refreshing the checklist) and the AUTO-ASSIGN FILES
helper that routes one or three selected files into the Z/N/E slots.
The SESAME checklist-card rendering moved to hvsr_gui_checklist.py.
Mixed into HVSRApp as HVSRAppStandardsMixin.
"""


import os
from tkinter import filedialog

try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False


class HVSRAppStandardsMixin:
    def _on_std_change(self):
        if not _HAVE_STANDARDS:
            return
        std_id = self._std_map.get(self._vars["std"].get(), "sesame")
        rec = hvsr_standards.recommended_params(std_id)
        self._log_line("METHOD = %s | REC WINDOW %.0f s, REJECT %.1f, RANGE %.1f-%.1f Hz" % (self._vars["std"].get(), rec["win_len"], rec["rejection"], rec["fmin"], rec["fmax"]))
        if self._last_evals and std_id in self._last_evals:
            self._render_standard(std_id)

    def _auto_assign(self):
        """AUTO-ASSIGN FILES... button: one file (.eqd/.sg2/3-col) or three
        files (Z/N/E) selected together are routed into the right slots.
        For three files the component is guessed from the file name.
        """
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
