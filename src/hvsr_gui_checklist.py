"""
hvsr_gui_checklist.py
=====================
The SESAME reliability checklist card for the HVSR Analyzer GUI: the
widget container (_build_sesame_widgets), the per-criterion renderer
that rebuilds the CHECKLIST tab for a guideline standard (_render_standard
- OK/WARN status boxes, reliability score, Vs30 / thickness and verdict)
and the _set_sesame hook.  The standard-selector handlers live in
hvsr_gui_standards.py.  Mixed into HVSRApp as HVSRAppChecklistMixin.
"""


import tkinter as tk
from tkinter import ttk

import hvsr_theme

try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False
# The flag above is only read by the selector module (hvsr_gui_standards);
# this module renders the checklist with hvsr_standards.STANDARDS directly
# and is only reached once the selector's guard has confirmed the module is
# available.  The guarded import is kept so that a missing hvsr_standards
# cannot crash this module at import time (a live theme switch would
# otherwise try to render a checklist with no data).


# Local aliases of the active theme palette (only the ones this
# module uses).  Refreshed by HVSRAppThemeMixin._set_theme() on a
# live theme switch.
BG = hvsr_theme.current["BG"]
NO_RED = hvsr_theme.current["NO_RED"]
OK_GREEN = hvsr_theme.current["OK_GREEN"]


class HVSRAppChecklistMixin:
    def _build_sesame_widgets(self):
        self._sesame_items = []

    def _render_standard(self, std_id):
        """Rebuild the CHECKLIST tab for the given guideline standard,
        showing each criterion with an OK/WARN box, the reliability score,
        and the Vs30 / thickness / verdict summary from the last run."""
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
