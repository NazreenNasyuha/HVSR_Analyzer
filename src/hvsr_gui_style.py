"""
hvsr_gui_style.py
=================
The ttk style setup for the HVSR Analyzer GUI: _build_style() configures
every ttk widget class (frames, labels, buttons, notebook tabs, entries,
comboboxes, scrollbars, progress bars) for the active theme.  It runs at
startup and again on every live theme switch.  The card / file-row /
scroll helpers live in hvsr_gui_pages.py.  Mixed into HVSRApp as
HVSRAppStyleMixin.
"""


from tkinter import ttk

import hvsr_theme


# Local aliases of the active theme palette (only the ones this
# module uses).  Refreshed by HVSRAppThemeMixin._set_theme() on a
# live theme switch.
ACCENT = hvsr_theme.current["ACCENT"]
BG = hvsr_theme.current["BG"]
HOVER = hvsr_theme.current["HOVER"]
PANEL_BG = hvsr_theme.current["PANEL_BG"]
TEXT_DARK = hvsr_theme.current["TEXT_DARK"]
TEXT_MUTED = hvsr_theme.current["TEXT_MUTED"]


class HVSRAppStyleMixin:
    def _build_style(self):
        """Configure every ttk widget class for the active theme (frames,
        labels, buttons, notebook tabs, entries, comboboxes, scrollbars,
        progress bars).  Runs at startup and again on each live theme
        switch, so widgets built after the switch pick up the new colours."""
        style = self._style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Global overrides for the active theme (dark or black & white)
        style.configure(".", background=BG, foreground=TEXT_DARK, font=("Courier New", 10, "bold"))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL_BG)
        # drag-hover feedback: the input card switches to this style while a
        # drag is over the window (see HVSRAppDndMixin._highlight_hint)
        style.configure("CardHover.TFrame", background=HOVER)

        style.configure("TLabel", background=BG, foreground=TEXT_DARK, font=("Courier New", 10, "bold"))
        style.configure("Card.TLabel", background=PANEL_BG, foreground=TEXT_DARK, font=("Courier New", 10, "bold"))
        style.configure("Title.TLabel", background=BG, foreground=ACCENT, font=("Courier New", 18, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=TEXT_MUTED, font=("Courier New", 9, "bold"))
        style.configure("H.TLabel", background=PANEL_BG, foreground=ACCENT, font=("Courier New", 11, "bold"))

        # Checkboxes and Radiobuttons
        style.configure("TRadiobutton", background=BG, foreground=TEXT_DARK)
        style.configure("Card.TRadiobutton", background=PANEL_BG, foreground=TEXT_DARK, indicatorcolor=BG)
        style.configure("TCheckbutton", background=BG, foreground=TEXT_DARK)
        style.configure("Card.TCheckbutton", background=PANEL_BG, foreground=TEXT_DARK, indicatorcolor=BG)

        # Frames
        style.configure("TLabelframe", background=PANEL_BG, bordercolor=ACCENT)
        style.configure("TLabelframe.Label", background=PANEL_BG, foreground=ACCENT, font=("Courier New", 10, "bold"))

        # Buttons.  lightcolor/darkcolor are forced to match the active theme
        # so the clam theme's light-gray top/left edge never shows on any
        # button; hover keeps the orange fill (or purple for accent buttons).
        style.configure("TButton", font=("Courier New", 10, "bold"),
                        background=PANEL_BG, foreground=ACCENT, bordercolor=ACCENT,
                        lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        style.map("TButton",
                  background=[("active", ACCENT), ("disabled", "#333333"),
                              ("!disabled", PANEL_BG)],
                  foreground=[("active", BG), ("disabled", "#777777"),
                              ("!disabled", ACCENT)],
                  lightcolor=[("active", ACCENT), ("disabled", "#333333"),
                              ("!disabled", PANEL_BG)],
                  darkcolor=[("active", ACCENT), ("disabled", "#333333"),
                             ("!disabled", PANEL_BG)],
                  bordercolor=[("active", ACCENT), ("disabled", "#333333"),
                               ("!disabled", ACCENT)])

        style.configure("Accent.TButton", background=ACCENT, foreground=BG,
                        font=("Courier New", 11, "bold"),
                        lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("active", HOVER), ("disabled", "#333333")],
                  foreground=[("active", "#FFFFFF"), ("disabled", "#777777")],
                  lightcolor=[("active", HOVER), ("disabled", "#333333"),
                              ("!active", ACCENT)],
                  darkcolor=[("active", HOVER), ("disabled", "#333333"),
                             ("!active", ACCENT)],
                  bordercolor=[("active", HOVER), ("disabled", "#333333"),
                               ("!active", ACCENT)])

        # Notebook / Tabs (tab borders forced dark so the clam theme's
        # light-gray seam and white edge-line never show through; the
        # notebook container keeps its orange accent frame)
        style.configure("TNotebook", background=BG, bordercolor=ACCENT, tabmargins=[2, 5, 2, 0],
                        lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        style.configure("TNotebook.Tab", background=PANEL_BG, foreground=ACCENT,
                        font=("Courier New", 10, "bold"), padding=(12, 6),
                        borderwidth=0, lightcolor=PANEL_BG, darkcolor=PANEL_BG,
                        focusthickness=0)
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT), ("!selected", PANEL_BG)],
                  foreground=[("selected", BG), ("!selected", ACCENT)],
                  lightcolor=[("selected", ACCENT), ("!selected", PANEL_BG)],
                  darkcolor=[("selected", ACCENT), ("!selected", PANEL_BG)],
                  bordercolor=[("selected", ACCENT), ("!selected", PANEL_BG)])

        # Entries & Comboboxes (dark mode).  lightcolor/darkcolor force the
        # top/bottom borders orange to match the left/right accent frame -
        # clam's default light-gray edges never show through.
        style.configure("TEntry", fieldbackground=BG, foreground=TEXT_DARK,
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("TCombobox", fieldbackground=BG, foreground=TEXT_DARK,
                        bordercolor=ACCENT, arrowcolor=ACCENT,
                        lightcolor=ACCENT, darkcolor=ACCENT)
        # disabled entries/comboboxes (Auto mode) keep the dark field +
        # muted text instead of clam's light-gray disabled background
        style.map("TEntry",
                  fieldbackground=[("disabled", BG), ("!disabled", BG)],
                  foreground=[("disabled", TEXT_MUTED), ("!disabled", TEXT_DARK)])
        style.map("TCombobox",
                  fieldbackground=[("readonly", BG), ("disabled", BG),
                                   ("!disabled", BG)],
                  selectbackground=[("readonly", ACCENT)],
                  selectforeground=[("readonly", BG)],
                  foreground=[("disabled", TEXT_MUTED), ("!disabled", TEXT_DARK)])
        # combobox drop-down list: force the popdown listbox dark too
        self.option_add("*TCombobox*Listbox.background", BG)
        self.option_add("*TCombobox*Listbox.foreground", TEXT_DARK)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", BG)

        # Scrollbars (full state map - kills clam's light active/disabled rendering
        # and the light 3D borders; keeps the active theme's look on every page)
        style.configure("Vertical.TScrollbar", background=PANEL_BG, bordercolor=PANEL_BG,
                        arrowcolor=ACCENT, troughcolor=BG,
                        lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        style.map("Vertical.TScrollbar",
                  background=[("pressed", PANEL_BG), ("active", PANEL_BG),
                              ("disabled", PANEL_BG), ("!disabled", PANEL_BG)],
                  troughcolor=[("disabled", BG), ("!disabled", BG)],
                  arrowcolor=[("disabled", TEXT_MUTED), ("!disabled", ACCENT)],
                  bordercolor=[("disabled", PANEL_BG), ("!disabled", PANEL_BG)],
                  lightcolor=[("disabled", PANEL_BG), ("!disabled", PANEL_BG)],
                  darkcolor=[("disabled", PANEL_BG), ("!disabled", PANEL_BG)])

        # Progress bar (status strip) - dark trough, orange bar, dark borders.
        # Style both the base and the horizontal variant (ttk resolves the
        # default-orientation progressbar to "Horizontal.TProgressbar").
        for _pb_style in ("TProgressbar", "Horizontal.TProgressbar"):
            style.configure(_pb_style, background=ACCENT, troughcolor=BG,
                            bordercolor=PANEL_BG, lightcolor=PANEL_BG,
                            darkcolor=PANEL_BG)
            style.map(_pb_style,
                      background=[("active", ACCENT), ("!active", ACCENT)],
                      troughcolor=[("disabled", BG), ("!disabled", BG)])
