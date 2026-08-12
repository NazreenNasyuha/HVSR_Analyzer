"""
hvsr_plot_spectra.py
====================
SpectraCanvas (overlaid component spectra) and TimeSeriesCanvas (three
stacked traces with analysis windows).  Carries its own palette copy so
it restyles on theme switches (apply_palette refreshes it).

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
WIN_COLOR = hvsr_theme.current["WIN_COLOR"]
TRACE_COLORS = dict(hvsr_theme.current["TRACE_COLORS"])
PLACEHOLDER_COLOR = hvsr_theme.current["PLACEHOLDER_COLOR"]
TEXT_COLOR = hvsr_theme.current["TEXT_COLOR"]
SPEC_FALLBACK_COLORS = tuple(hvsr_theme.current["SPEC_FALLBACK_COLORS"])

def apply_palette():
    """Re-read the active theme colours into this module's globals."""
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

class SpectraCanvas(tk.Canvas):
    """Three-component spectral chart (PSD in dB, or Fourier amplitude).

    A log-frequency, linear-amplitude plot with Z / N / E traces that
    automatically subsamples dense FFT grids so it stays responsive.
    """

    def __init__(self, master, **kw):
        kw.setdefault("bg", CANVAS_BG)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.freqs = []
        self.curves = {}      # {'z': [...], 'n': [...], 'e': [...]}
        self.mode = "PSD"    # "PSD" (dB), "Spectrum" (amp) or "Coherence"
        self.labels = ("Z", "N", "E")
        self.station = ""
        self.fmin = 0.1
        self.fmax = 20.0
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, freqs, curves, mode="PSD", station="", labels=None):
        """Feed spectra for the Z / N / E components.  ``curves`` maps
        component letters to arrays; ``mode`` picks PSD (dB) or Spectrum."""
        self.freqs = list(freqs)
        self.curves = {k: list(v) for k, v in curves.items()}
        self.mode = mode
        self.station = station
        self.labels = tuple(labels) if labels else ("Z", "N", "E")
        if freqs:
            self.fmin = min(freqs)
            self.fmax = max(freqs)
        self.redraw()

    def _geom(self):
        w = max(self.winfo_width(), 100)
        h = max(self.winfo_height(), 100)
        return w, h, 62, w - 22, 30, h - 34

    def _x(self, f, left, right):
        l0, l1 = math.log(self.fmin), math.log(self.fmax)
        t = (math.log(f) - l0) / (l1 - l0) if f > 0 else 0.0
        return left + t * (right - left)

    def redraw(self):
        self.delete("all")
        w, h, left, right, top, bottom = self._geom()
        if not self.freqs or not self.curves:
            self.create_text(w / 2, h / 2,
                             text="Run an analysis with PSD / Spectra enabled",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 12))
            return
        vals = [v for c in ("z", "n", "e") for v in self.curves.get(c, [])]
        if not vals:
            return
        lo = min(vals)
        hi = max(vals)
        if hi - lo < 1e-30:
            hi = lo + 1.0
        pad = (hi - lo) * 0.08
        vmin, vmax = lo - pad, hi + pad

        for f in _nice_ticks(self.fmin, self.fmax):
            x = self._x(f, left, right)
            self.create_line(x, top, x, bottom, fill=GRID_COLOR)
            self.create_text(x, bottom + 8, text=_fmt_tick(f), fill=AXIS_COLOR,
                             font=("Segoe UI", 8))
        for t in range(4):
            v = vmin + t * (vmax - vmin) / 3.0
            y = bottom - (v - vmin) / (vmax - vmin) * (bottom - top)
            self.create_line(left, y, right, y, fill=GRID_COLOR)
            self.create_text(left - 6, y, text=("%.0f" % v), anchor="e",
                             fill=AXIS_COLOR, font=("Segoe UI", 8))
        self.create_line(left, top, left, bottom, fill=AXIS_COLOR)
        self.create_line(left, bottom, right, bottom, fill=AXIS_COLOR)

        step = max(1, len(self.freqs) // max(right - left, 300))
        for i, label in enumerate(self.labels):
            key = ("z", "n", "e")[i % 3]
            cv = self.curves.get(key)
            if not cv:
                continue
            color = TRACE_COLORS.get(label)
            if color is None:
                color = SPEC_FALLBACK_COLORS[i % 3]
            pts = []
            for k in range(0, len(self.freqs), step):
                f = self.freqs[k]
                v = cv[k]
                x = self._x(f, left, right)
                y = bottom - (v - vmin) / (vmax - vmin) * (bottom - top)
                pts.append((x, y))
            self.create_line(pts, fill=color, width=2)
            self.create_text(right - 4, top + 4 + 14 * i, text=label,
                             anchor="e", fill=color, font=("Segoe UI", 9,
                                                            "bold"))

        if self.mode == "PSD":
            unit = "dB (rel.)"
        elif self.mode == "Coherence":
            unit = "gamma^2"
        else:
            unit = "amplitude"
        self.create_text(left, top - 10, text=self.mode + " " + unit,
                         anchor="w", fill=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        self.create_text(left + (right - left) / 2, bottom + 22,
                         text="Frequency (Hz)", fill=TEXT_COLOR,
                         font=("Segoe UI", 9, "bold"))
        if self.station:
            self.create_text(right, 12, text="Station: " + self.station,
                             anchor="e", fill=PLACEHOLDER_COLOR,
                             font=("Segoe UI", 9, "italic"))

    def export_png(self, path):
        from chart_render import HvsrChart
        chart = HvsrChart(width=1100, height=620)
        chart.draw_spectra(self.freqs, self.curves, self.mode, self.station)
        chart.save_png(path)

class TimeSeriesCanvas(tk.Canvas):
    """Three stacked component traces with analysis-window overlays."""

    def __init__(self, master, **kw):
        kw.setdefault("bg", CANVAS_BG)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.traces = []      # list of (label, values)
        self.win_len = 0.0
        self.fs = 1.0
        self.max_t = 0.0
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, traces, fs, win_len=0.0, start=0.0):
        """Feed ``[(label, samples), ...]`` traces at rate ``fs``; a
        non-zero ``win_len`` draws the sliding-window rectangle."""
        self.traces = traces
        self.fs = fs
        self.win_len = win_len
        self.start = start
        self.max_t = max((len(v) / fs for _, v in traces), default=0.0)
        self.redraw()

    def redraw(self):
        self.delete("all")
        w = max(self.winfo_width(), 100)
        h = max(self.winfo_height(), 100)
        if not self.traces:
            self.create_text(w / 2, h / 2, text="Load data to preview traces",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 12))
            return
        n = len(self.traces)
        top, bottom = 10, h - 34
        left, right = 56, w - 14
        band = (bottom - top) / n
        tmax = self.max_t
        for i, (label, values) in enumerate(self.traces):
            y0 = top + band * i
            y1 = y0 + band
            mid = (y0 + y1) / 2
            self.create_text(left - 8, mid, text=label, anchor="e",
                             fill=AXIS_COLOR, font=("Segoe UI", 9, "bold"))
            vm = max((abs(v) for v in values), default=1.0)
            if vm == 0:
                vm = 1.0
            pts = []
            step = max(1, len(values) // max(w - left - right // 4, 200))
            for k in range(0, len(values), step):
                t = self.start + k / self.fs
                x = left + (t / tmax) * (right - left)
                y = mid - (values[k] / vm) * (band * 0.4)
                pts.append((x, y))
            self.create_line(pts, fill=TRACE_COLORS.get(label, TEXT_COLOR),
                             width=1 if len(values) > 5000 else 2)
            self.create_line(left, y0, right, y0, fill=GRID_COLOR)
            self.create_line(left, y1, right, y1, fill=GRID_COLOR)
            # window overlay
            if self.win_len > 0 and tmax > 0:
                for t0 in range(0, int(tmax), int(self.win_len)):
                    x0 = left + (t0 / tmax) * (right - left)
                    x1 = left + (min(t0 + self.win_len, tmax) / tmax) * (right - left)
                    self.create_rectangle(x0, y0 + 2, x1, y1 - 2,
                                          outline=WIN_COLOR, width=1)
        self.create_text(left + (right - left) / 2, h - 12, text="Time (s)",
                         fill=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        for t in range(0, int(tmax) + 1, max(1, int(tmax) // 6)):
            x = left + (t / tmax) * (right - left)
            self.create_text(x, h - 26, text=str(t), fill=AXIS_COLOR,
                             font=("Segoe UI", 8))

    def export_png(self, path):
        chart = HvsrChart(width=1100, height=620)
        chart.draw_timeseries(self.traces, self.fs, self.win_len)
        chart.save_png(path)
