"""
hvsr_plot_curve.py
==================
HvsrCurveCanvas: the log-frequency H/V curve chart with +/- 1 sigma band
and f0 marker.  Carries its own palette copy so it restyles on theme
switches (apply_palette refreshes it).

Split out of hvsr_plot.py.
"""

import math
import tkinter as tk
import hvsr_theme
from hvsr_plot_util import _fmt_tick, _nice_ticks
from chart_render import HvsrChart

CANVAS_BG = hvsr_theme.current["CANVAS_BG"]
GRID_COLOR = hvsr_theme.current["GRID_COLOR"]
AXIS_COLOR = hvsr_theme.current["AXIS_COLOR"]
MEAN_COLOR = hvsr_theme.current["MEAN_COLOR"]
BAND_COLOR = hvsr_theme.current["BAND_COLOR"]
F0_COLOR = hvsr_theme.current["F0_COLOR"]
EXTRA_COLOR = hvsr_theme.current["EXTRA_COLOR"]
PLACEHOLDER_COLOR = hvsr_theme.current["PLACEHOLDER_COLOR"]
TEXT_COLOR = hvsr_theme.current["TEXT_COLOR"]

def apply_palette():
    """Re-read the active theme colours into this module's globals."""
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

class HvsrCurveCanvas(tk.Canvas):
    """Log-frequency H/V spectral ratio chart."""

    def __init__(self, master, **kw):
        kw.setdefault("bg", CANVAS_BG)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.freqs = []
        self.mean = []
        self.low = []
        self.high = []
        self.extra = None
        self.f0 = 0.0
        self.a0 = 0.0
        self.station = ""
        self.fmin = 0.5
        self.fmax = 20.0
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, freqs, mean, low, high, f0, a0, station="", extra=None,
                 extra_label=None):
        """Feed the curve data and request a redraw.  ``extra`` is an
        optional second series (e.g. the Geopsy cross-check) drawn as a
        dashed overlay."""
        self.freqs = list(freqs)
        self.mean = list(mean)
        self.low = list(low)
        self.high = list(high)
        self.f0 = f0
        self.a0 = a0
        self.station = station
        self.extra = list(extra) if extra is not None else None
        self.extra_label = extra_label
        if freqs:
            self.fmin = min(freqs)
            self.fmax = max(freqs)
        self.redraw()

    def clear(self):
        self.set_data([], [], [], [], 0.0, 0.0)

    def _geom(self):
        w = max(self.winfo_width(), 100)
        h = max(self.winfo_height(), 100)
        left, right = 62, w - 22
        top, bottom = 30, h - 34
        return w, h, left, right, top, bottom

    def _x(self, f, left, right):
        l0, l1 = math.log(self.fmin), math.log(self.fmax)
        t = (math.log(f) - l0) / (l1 - l0) if f > 0 else 0.0
        return left + t * (right - left)

    def redraw(self):
        self.delete("all")
        w, h, left, right, top, bottom = self._geom()
        if not self.freqs or not self.mean or len(self.mean) != len(self.freqs):
            self.create_text(w / 2, h / 2, text="No data yet - run an analysis",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 12))
            return

        vmax = max(4.0, max(max(self.mean), max(self.high)))
        if self.extra:
            vmax = max(vmax, max(self.extra))
        vmax = math.ceil(vmax + 1.0)

        # grid + tick labels
        for f in _nice_ticks(self.fmin, self.fmax):
            x = self._x(f, left, right)
            self.create_line(x, top, x, bottom, fill=GRID_COLOR)
            self.create_text(x, bottom + 8, text=_fmt_tick(f), fill=AXIS_COLOR,
                             font=("Segoe UI", 8))
        for t in range(1, int(vmax) + 1):
            y = bottom - t * (bottom - top) / vmax
            if t % 2 == 0:
                self.create_line(left, y, right, y, fill=GRID_COLOR)
            self.create_text(left - 6, y, text=str(t), anchor="e", fill=AXIS_COLOR,
                             font=("Segoe UI", 8))

        self.create_line(left, top, left, bottom, fill=AXIS_COLOR)
        self.create_line(left, bottom, right, bottom, fill=AXIS_COLOR)

        # +/- 1 sigma band
        pts = []
        for f, v in zip(self.freqs, self.high):
            pts.append((self._x(f, left, right), bottom - (v / vmax) * (bottom - top)))
        for f, v in reversed(list(zip(self.freqs, self.low))):
            pts.append((self._x(f, left, right), bottom - (v / vmax) * (bottom - top)))
        if len(pts) > 2:
            self.create_polygon(pts, fill=BAND_COLOR, outline="")

        if self.extra:
            self.create_line([(self._x(f, left, right),
                              bottom - (v / vmax) * (bottom - top))
                              for f, v in zip(self.freqs, self.extra)],
                             fill=EXTRA_COLOR, width=3)

        self.create_line([(self._x(f, left, right),
                           bottom - (v / vmax) * (bottom - top))
                          for f, v in zip(self.freqs, self.mean)],
                         fill=MEAN_COLOR, width=2)

        # f0 marker
        if self.f0 > 0:
            x0 = self._x(self.f0, left, right)
            y0 = bottom - (self.a0 / vmax) * (bottom - top)
            self.create_line(x0, top, x0, bottom, fill=F0_COLOR, dash=(5, 3))
            r = 4
            self.create_oval(x0 - r, y0 - r, x0 + r, y0 + r, fill=F0_COLOR,
                             outline=F0_COLOR)

        # legend
        ly = top + 4
        self.create_line(left + 6, ly + 5, left + 42, ly + 5, fill=MEAN_COLOR, width=3)
        self.create_text(left + 48, ly, text="Mean curve", anchor="w",
                         fill=TEXT_COLOR, font=("Segoe UI", 9))
        ly += 16
        for i in range(3):
            self.create_line(left + 6 + i * 2, ly + 3, left + 42, ly + 3,
                             fill=BAND_COLOR, width=2)
        self.create_text(left + 48, ly - 3, text="+/- 1 sigma", anchor="w",
                         fill=TEXT_COLOR, font=("Segoe UI", 9))
        ly += 16
        self.create_line(left + 6, ly + 5, left + 42, ly + 5, fill=F0_COLOR, width=2)
        self.create_text(left + 48, ly, text="f0 = %.3f Hz, A0 = %.2f"
                         % (self.f0, self.a0), anchor="w", fill=TEXT_COLOR,
                         font=("Segoe UI", 9))
        if self.extra is not None:
            ly += 16
            self.create_line(left + 6, ly + 5, left + 42, ly + 5, fill=EXTRA_COLOR,
                             width=3)
            self.create_text(left + 48, ly, text=self.extra_label or "Cross-check",
                             anchor="w", fill=TEXT_COLOR, font=("Segoe UI", 9))

        self.create_text(left, top - 10, text="H/V Amplification", anchor="w",
                         fill=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        self.create_text(left + (right - left) / 2, bottom + 22,
                         text="Frequency (Hz)", fill=TEXT_COLOR,
                         font=("Segoe UI", 9, "bold"))
        if self.station:
            self.create_text(right, 12, text="Station: " + self.station, anchor="e",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 9, "italic"))

    def export_png(self, path):
        chart = HvsrChart(width=1100, height=620)
        chart.draw_hvsr(self.freqs, self.mean, self.low, self.high, self.f0, self.a0,
                        station=self.station, extra=self.extra,
                        extra_label=getattr(self, "extra_label", None),
                        fmin=self.fmin, fmax=self.fmax)
        chart.save_png(path)
