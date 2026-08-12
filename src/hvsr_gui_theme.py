"""
hvsr_gui_theme.py
=================
Live theme switching for the HVSR Analyzer GUI.

HVSRAppThemeMixin: _set_theme() switches the whole application (widgets,
charts and PNG export) between the retro dark theme and the black & white
thesis theme, pushing the new palette into every sibling module that
carries colour aliases; _themed() registers widgets whose explicit
colours must follow the switch.  The palette data lives in hvsr_theme.py.
"""


import hvsr_theme

# Local aliases of the active theme palette.  _set_theme() refreshes
# them here (globals().update) when the user switches theme live, and
# pushes the new palette to every sibling module that carries aliases.
ACCENT = hvsr_theme.current["ACCENT"]
BG = hvsr_theme.current["BG"]
TEXT_DARK = hvsr_theme.current["TEXT_DARK"]


class HVSRAppThemeMixin:
    def _themed(self, widget, key):
        """Track a widget whose explicit colour must follow theme switches."""
        if not hasattr(self, "_themed_widgets"):
            self._themed_widgets = []
        self._themed_widgets.append((widget, key))
        return widget

    def _set_theme(self):
        """Switch the whole application (widgets + charts + PNG export)
        between the retro dark theme and the black & white thesis theme."""
        name = self._vars["theme"].get()
        key = "bw" if name.startswith("B&W") else "dark"
        hvsr_theme.apply_theme(key)
        globals().update(hvsr_theme.current)   # re-bind ACCENT / BG / ... names
        # The UI-construction modules keep their own copies of the palette
        # names; refresh those too so widgets restyled after the switch pick
        # up the new colours.  The list includes every module that carries
        # palette aliases.  Excluded on purpose: this module (hvsr_gui_theme,
        # its aliases were already re-bound by the globals().update() above)
        # and hvsr_gui_core / hvsr_gui_pump / hvsr_gui_previews /
        # hvsr_gui_exports / hvsr_gui_profiles / hvsr_gui_standards /
        # hvsr_gui_workers / hvsr_gui_workhelpers / hvsr_gui_invworker,
        # which carry no aliases at all.
        # Imported here rather than at module level to avoid import cycles
        # (everything is loaded by the time a theme switch can happen).
        import hvsr_gui_layout, hvsr_gui_workflow, hvsr_gui_pages
        import hvsr_gui_style, hvsr_gui_checklist
        import hvsr_gui_inversion, hvsr_gui_tour
        for _mod in (hvsr_gui_layout, hvsr_gui_workflow, hvsr_gui_pages,
                     hvsr_gui_style, hvsr_gui_checklist,
                     hvsr_gui_inversion, hvsr_gui_tour):
            _mod.__dict__.update(hvsr_theme.current)
        self._build_style()                    # restyle every ttk widget
        # if the guided tour is open, refresh its palette with the new theme
        tour = getattr(self, "_tour", None)
        if tour is not None and getattr(tour, "active", False):
            try:
                tour._redraw()
            except Exception:
                pass
        self.configure(bg=BG)
        for w in (getattr(self, "_report", None), getattr(self, "_log", None),
                  getattr(self, "_inv_text", None)):
            if w is not None:
                try:
                    w.config(bg=BG, fg=TEXT_DARK, insertbackground=ACCENT)
                except Exception:
                    pass
        for w, k in getattr(self, "_themed_widgets", []):
            try:
                w.config(foreground=hvsr_theme.current[k])
            except Exception:
                pass
        tut = getattr(self, "_tutorial_win", None)
        if tut is not None and tut.winfo_exists():
            try:
                tut.configure(bg=BG)
                for c in tut.winfo_children():
                    if c.winfo_class() == "Text":
                        c.config(bg=BG, fg=TEXT_DARK, insertbackground=ACCENT)
            except Exception:
                pass
        import hvsr_plot as _hp
        import chart_render as _cr
        _hp.apply_palette()
        _cr.apply_palette()
        for c in (getattr(self, "_preview", None), getattr(self, "_filt", None),
                  getattr(self, "_sig", None), getattr(self, "_tf", None),
                  getattr(self, "_az", None), getattr(self, "_avg_spec", None),
                  getattr(self, "_avg_hv", None), getattr(self, "_curve", None),
                  getattr(self, "_ts", None), getattr(self, "_spec", None),
                  getattr(self, "_inv_canvas", None),
                  getattr(self, "_inv_hist", None)):
            if c is None:
                continue
            try:
                c.config(bg=hvsr_theme.current["CANVAS_BG"])
                redraw = getattr(c, "redraw", None)
                if callable(redraw):
                    redraw()
            except Exception:
                pass
        if getattr(self, "_last_evals", None):
            std_id = self._std_map.get(self._vars["std"].get(), "sesame")
            self._render_standard(std_id)
        self._log_line("THEME ACTIVE: %s" % name)
        tour = getattr(self, "_tour", None)
        if tour is not None and tour.active:
            try:
                tour._draw()
            except Exception:
                pass
