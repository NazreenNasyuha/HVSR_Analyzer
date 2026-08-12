"""
hvsr_plot_colormap.py
=====================
ColorMapCanvas: a time-frequency colour map with the theme cmap stops.
Carries its own palette copy so it restyles on theme switches
(apply_palette refreshes it).

Split out of hvsr_plot.py.
"""

import math
import tkinter as tk
import hvsr_theme
from hvsr_plot_util import _fmt_tick, _nice_ticks
from chart_render import HvsrChart

CANVAS_BG = hvsr_theme.current["CANVAS_BG"]
AXIS_COLOR = hvsr_theme.current["AXIS_COLOR"]
PLACEHOLDER_COLOR = hvsr_theme.current["PLACEHOLDER_COLOR"]
TEXT_COLOR = hvsr_theme.current["TEXT_COLOR"]
CMAP_STOPS = hvsr_theme.current["CMAP_STOPS"]

def apply_palette():
    """Re-read the active theme colours into this module's globals."""
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

class ColorMapCanvas(tk.Canvas):
    """2-D colour map (e.g. H/V vs time or H/V vs azimuth) with legend.

    set_data(y_labels, freqs, grid, vmin, vmax, title, ylabel, log_freq):
      grid[r][c] is the value of row r (y_labels[r]) at frequency freqs[c].
    Rows are drawn from the bottom up; a vertical colour bar with the
    min/max labels sits on the right edge.  The map is subsampled so a
    large grid (many windows x hundreds of frequencies) stays responsive.
    """

    def __init__(self, master, **kw):
        kw.setdefault("bg", CANVAS_BG)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.y_labels = []
        self.freqs = []
        self.grid = []
        self.vmin = 0.0
        self.vmax = 1.0
        self.title = ""
        self.ylabel = ""
        self.log_freq = True
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, y_labels, freqs, grid, vmin=None, vmax=None,
                 title="", ylabel="", log_freq=True):
        """Feed the map: rows ``y_labels`` (times or azimuths), columns
        ``freqs``, and the 2-D H/V value grid to colourise."""
        self.y_labels = list(y_labels)
        self.freqs = list(freqs)
        self.grid = [list(row) for row in grid]
        vals = [v for row in self.grid for v in row if v == v]  # skip nan
        if vmin is None:
            self.vmin = min(vals) if vals else 0.0
        else:
            self.vmin = vmin
        if vmax is None:
            self.vmax = max(vals) if vals else 1.0
        else:
            self.vmax = vmax
        if self.vmax <= self.vmin:
            self.vmax = self.vmin + 1.0
        self.title = title
        self.ylabel = ylabel
        self.log_freq = log_freq
        self.redraw()

    def clear(self):
        self.set_data([], [], [], title=self.title, ylabel=self.ylabel)

    def _x(self, f, left, right):
        if not self.freqs or len(self.freqs) < 2:
            return left
        if self.log_freq:
            l0, l1 = math.log(max(self.freqs[0], 1e-9)), math.log(self.freqs[-1])
            if l1 <= l0:
                return left
            return left + (math.log(max(f, 1e-9)) - l0) / (l1 - l0) * (right - left)
        return left + (f - self.freqs[0]) / (self.freqs[-1] - self.freqs[0]) * (right - left)

    @staticmethod
    def _color(t):
        """Theme colour-map colour for t in [0, 1]."""
        t = max(0.0, min(1.0, t))
        stops = CMAP_STOPS
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t <= t1:
                u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                r = int(c0[0] + (c1[0] - c0[0]) * u)
                g = int(c0[1] + (c1[1] - c0[1]) * u)
                b = int(c0[2] + (c1[2] - c0[2]) * u)
                return "#%02x%02x%02x" % (r, g, b)
        return "#%02x%02x%02x" % stops[-1][1]

    def redraw(self):
        self.delete("all")
        w = max(self.winfo_width(), 100)
        h = max(self.winfo_height(), 100)
        if not self.grid or not self.freqs:
            self.create_text(w / 2, h / 2,
                             text="Run the preview to draw the map",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 12))
            return
        bar_w = 26
        left, right = 52, w - bar_w - 18
        top, bottom = 28, h - 30
        nrows = len(self.grid)
        ncols = len(self.freqs)
        # subsample to keep the canvas responsive
        max_r, max_c = 60, 140
        rstep = max(1, int(math.ceil(nrows / max_r)))
        cstep = max(1, int(math.ceil(ncols / max_c)))
        row_idx = list(range(0, nrows, rstep))
        col_idx = list(range(0, ncols, cstep))
        rh = (bottom - top) / len(row_idx)
        cw = (right - left) / len(col_idx)
        span = self.vmax - self.vmin
        for ri, r in enumerate(row_idx):
            y0 = bottom - rh * ri - rh
            y1 = bottom - rh * ri
            for ci, c in enumerate(col_idx):
                v = self.grid[r][c]
                t = (v - self.vmin) / span if span > 0 else 0.0
                x0 = left + cw * ci
                x1 = left + cw * (ci + 1)
                self.create_rectangle(x0, y0, x1, y1, fill=self._color(t),
                                      outline="")
        # axes
        self.create_line(left, top, left, bottom, fill=AXIS_COLOR)
        self.create_line(left, bottom, right, bottom, fill=AXIS_COLOR)
        for f in _nice_ticks(max(self.freqs[0], 1e-9), self.freqs[-1], target=5):
            x = self._x(f, left, right)
            self.create_line(x, bottom, x, bottom + 4, fill=AXIS_COLOR)
            self.create_text(x, bottom + 8, text=_fmt_tick(f), fill=AXIS_COLOR,
                             font=("Segoe UI", 8))
        # row labels (a handful)
        nl = min(5, len(row_idx))
        for i in range(nl):
            ri = row_idx[int(i * (len(row_idx) - 1) / max(1, nl - 1))]
            lab = self.y_labels[ri]
            y = bottom - rh * row_idx.index(ri) - rh / 2
            text = "%.0f" % lab if abs(lab) >= 10 else "%.1f" % lab
            self.create_text(left - 6, y, text=text, anchor="e",
                             fill=AXIS_COLOR, font=("Segoe UI", 8))
        # colour legend
        bar_top, bar_bottom = top, bottom
        bar_x = right + 8
        steps = 40
        for i in range(steps):
            t = i / (steps - 1)
            yy0 = bar_bottom - (bar_bottom - bar_top) * i / steps
            yy1 = bar_bottom - (bar_bottom - bar_top) * (i + 1) / steps
            self.create_rectangle(bar_x, yy0, bar_x + bar_w, yy1,
                                  fill=self._color(t), outline="")
        self.create_text(bar_x + bar_w / 2, bar_top - 10,
                         text=self.title + " max", fill=TEXT_COLOR,
                         font=("Segoe UI", 8, "bold"))
        self.create_text(bar_x + bar_w / 2, bar_bottom + 12,
                         text="%.2f" % self.vmin, fill=AXIS_COLOR,
                         font=("Segoe UI", 8))
        self.create_text(bar_x + bar_w / 2, bar_top + 2,
                         text="%.2f" % self.vmax, fill=AXIS_COLOR,
                         font=("Segoe UI", 8))
        # titles
        self.create_text(left, top - 12, text=self.title, anchor="w",
                         fill=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        self.create_text(left + (right - left) / 2, h - 8,
                         text="Frequency (Hz)", fill=TEXT_COLOR,
                         font=("Segoe UI", 9, "bold"))
        if self.ylabel:
            self.create_text(14, (top + bottom) / 2, text=self.ylabel,
                             angle=90, fill=TEXT_COLOR, font=("Segoe UI", 9,
                                                              "bold"))

    def export_png(self, path):
        chart = HvsrChart(width=1100, height=620)
        chart.draw_colormap(self.y_labels, self.freqs, self.grid,
                            vmin=self.vmin, vmax=self.vmax,
                            title=self.title, ylabel=self.ylabel,
                            log_freq=self.log_freq)
        chart.save_png(path)
