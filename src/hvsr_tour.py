# -*- coding: utf-8 -*-
"""
hvsr_tour.py
============
Guided tour overlay for the HVSR Analyzer.

A full-window overlay that spotlights one control at a time with a box,
a name tag, an arrow and an explanatory card (Next / Back / Skip).

How it works: the overlay is a separate borderless Toplevel whose canvas
background is a colour that Windows renders fully transparent
(-transparentcolor).  Everything drawn in a *different* colour is a solid,
opaque layer; the unpainted areas let the real application show through.
The tour therefore dims everything OUTSIDE the spotlight box with a
clearly-visible dim layer, while the boxed control stays fully visible.

The rendering lives in TourDrawing (hvsr_tour_draw.py); this module keeps
the control flow.
"""

import tkinter as tk
import tkinter.font as tkfont

try:
    import hvsr_theme
except Exception:                      # pragma: no cover
    hvsr_theme = None

from hvsr_tour_draw import TourDrawing

class TourOverlay(TourDrawing):
    """One-at-a-time guided tour overlay for a tkinter root window."""

    def __init__(self, app, steps):
        """Overlay a full-window canvas on top of the app and store the
        tour steps; the overlay is created but not shown until start()."""
        self._app = app
        self._steps = list(steps)
        self._idx = 0
        self._win = None
        self._canvas = None
        self._card = None
        self._configure_binding = None
        self._key_bindings = {}

    @property
    def active(self):
        """True while the overlay exists on screen."""
        return self._win is not None and self._win.winfo_exists()

    @property
    def index(self):
        """Current step index (0-based)."""
        return self._idx

    def start(self):
        """Show the overlay at the first step."""
        if self.active:
            return
        app = self._app
        win = tk.Toplevel(app)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        transparent = True
        try:
            win.attributes("-transparentcolor", self.TRANSPARENT)
        except tk.TclError:
            transparent = False   # non-Windows: solid theme backdrop
        canvas = tk.Canvas(win, highlightthickness=0, bd=0, cursor="arrow",
                           bg=self.TRANSPARENT if transparent
                           else self._palette()["bg"])
        canvas.pack(fill="both", expand=True)

        canvas.bind("<Escape>", lambda e: self._skip())
        canvas.bind("<Right>", lambda e: self._next())
        canvas.bind("<Left>", lambda e: self._prev())
        canvas.bind("<Configure>", lambda e: self._redraw())
        canvas.focus_set()
        self._win = win
        self._canvas = canvas
        # bind the shortcuts on the app root too: an overrideredirect window
        # does not reliably hold keyboard focus, but the main window always
        # does -- so the keys work whichever window has focus
        self._key_bindings = {
            "<Escape>": app.bind("<Escape>", lambda e: self._skip()),
            "<Right>": app.bind("<Right>", lambda e: self._next()),
            "<Left>": app.bind("<Left>", lambda e: self._prev()),
        }
        # follow the app window when it moves or resizes; position the
        # overlay while still withdrawn so it never flashes at a wrong size
        self._configure_binding = app.bind("<Configure>",
                                           lambda e: self._sync_geometry())
        self._sync_geometry()
        win.deiconify()
        try:
            win.focus_force()   # overrideredirect windows need explicit focus
        except Exception:
            pass
        self._draw()

    def _sync_geometry(self):
        """Position the overlay exactly over the app window (clamped to the
        screen, so a maximised window still gets a full overlay)."""
        if not self.active:
            return
        app = self._app
        x = max(0, app.winfo_rootx())
        y = max(0, app.winfo_rooty())
        w = app.winfo_width()
        h = app.winfo_height()
        # clamp to the visible desktop area
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        w = max(8, min(w, sw - x))
        h = max(8, min(h, sh - y))
        self._win.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self._win.update_idletasks()

    def _redraw(self):
        """Repaint the tour after the window moves or resizes."""
        if self.active:
            self._sync_geometry()
            self._draw()

    def _prev(self):
        """Move one step backwards (no-op on the first step)."""
        if self._idx > 0:
            self._idx -= 1
            self._draw()

    def _next(self):
        """Move one step forwards (no-op on the last step)."""
        if self._idx < len(self._steps) - 1:
            self._idx += 1
            self._draw()
        else:
            self._skip()

    def _skip(self):
        """Close the tour overlay and call the app's on-closed hook."""
        if self.active:
            try:
                if self._configure_binding:
                    self._app.unbind("<Configure>", self._configure_binding)
                for seq, bid in (self._key_bindings or {}).items():
                    try:
                        self._app.unbind(seq, bid)
                    except Exception:
                        pass
            except Exception:
                pass
            self._configure_binding = None
            self._key_bindings = {}
            try:
                self._win.destroy()
            except Exception:
                pass
        self._win = None
        self._canvas = None
        self._card = None
        on_close = getattr(self._app, "_on_tour_closed", None)
        if on_close:
            try:
                on_close()
            except Exception:
                pass

    def _apply_pre(self, step):
        """Run a step's pre-actions (switch pages / result tabs)."""
        pages = getattr(self._app, "_pages", None)
        page = step.get("page")
        if pages is not None and page is not None:
            try:
                pages.select(page)
            except Exception:
                pass
        nb = getattr(self._app, "_nb", None)
        tab = step.get("nb_tab")
        if nb is not None and tab:
            for i, tid in enumerate(nb.tabs()):
                if tab.lower() in nb.tab(tid, "text").lower():
                    try:
                        nb.select(i)
                    except Exception:
                        pass
                    break

    def _resolve_target(self, step):
        """Resolve a step's target (a widget, a string name, or a callable
        returning one) into an actual tkinter widget, or None."""
        target = step.get("target")
        if callable(target):
            try:
                return target()
            except Exception:
                return None
        return target
