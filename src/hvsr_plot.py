"""
hvsr_plot.py
============
Tkinter Canvas chart widgets used by the HVSR Analyzer GUI:

- HvsrCurveCanvas : log-frequency H/V curve with +/- 1 sigma band, f0 marker
- TimeSeriesCanvas: three stacked component traces with analysis windows

Both redraw on resize and can be exported to PNG through chart_render.
"""

import math
import tkinter as tk

from chart_render import HvsrChart

# Charts use the colours of the active theme (see hvsr_theme.py).
# apply_palette() re-reads the current theme, so canvases restyle with
# the rest of the GUI when the theme switches.
import hvsr_theme

CANVAS_BG = hvsr_theme.current["CANVAS_BG"]
GRID_COLOR = hvsr_theme.current["GRID_COLOR"]
AXIS_COLOR = hvsr_theme.current["AXIS_COLOR"]
MEAN_COLOR = hvsr_theme.current["MEAN_COLOR"]
BAND_COLOR = hvsr_theme.current["BAND_COLOR"]
F0_COLOR = hvsr_theme.current["F0_COLOR"]
EXTRA_COLOR = hvsr_theme.current["EXTRA_COLOR"]
WIN_COLOR = hvsr_theme.current["WIN_COLOR"]
TRACE_COLORS = dict(hvsr_theme.current["TRACE_COLORS"])
PLACEHOLDER_COLOR = hvsr_theme.current["PLACEHOLDER_COLOR"]
TEXT_COLOR = hvsr_theme.current["TEXT_COLOR"]
SPEC_FALLBACK_COLORS = tuple(hvsr_theme.current["SPEC_FALLBACK_COLORS"])
HIST_BAR = hvsr_theme.current["HIST_BAR"]
HIST_BAR_EDGE = hvsr_theme.current["HIST_BAR_EDGE"]
MISFIT_BEST = hvsr_theme.current["MISFIT_BEST"]
MISFIT_MEDIAN = hvsr_theme.current["MISFIT_MEDIAN"]
MISFIT_P90 = hvsr_theme.current["MISFIT_P90"]
VS_BAND = hvsr_theme.current["VS_BAND"]
VS_BAND_EDGE = hvsr_theme.current["VS_BAND_EDGE"]
VS_HATCH = hvsr_theme.current["VS_HATCH"]
CMAP_STOPS = hvsr_theme.current["CMAP_STOPS"]


def apply_palette():
    """Re-read the active theme colours into this module's globals."""
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value


def _nice_ticks(fmin, fmax, target=6):
    """Return nice log-ticks (1-2-5 decades) in [fmin, fmax]."""
    ticks = []
    decade = math.floor(math.log10(fmin))
    while True:
        base = 10.0 ** decade
        for mult in (1, 2, 5, 10):
            f = base * mult
            if f < fmin - 1e-12:
                continue
            if f > fmax + 1e-12:
                return ticks
            ticks.append(f)
        decade += 1


def _fmt_tick(f):
    if f >= 10:
        return "%.0f" % f
    if f >= 1:
        return "%.0f" % f if abs(f - round(f)) < 1e-9 else "%.1f" % f
    return "%.2f" % f


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


class MisfitHistCanvas(tk.Canvas):
    """Histogram of the Monte-Carlo misfit distribution (finite models)."""

    def __init__(self, master, **kw):
        kw.setdefault("bg", CANVAS_BG)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.hist = (None, [])
        self.best = None
        self.median = None
        self.p90 = None
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, hist, best=None, median=None, p90=None):
        self.hist = hist or (None, [])
        self.best = best
        self.median = median
        self.p90 = p90
        self.redraw()

    def redraw(self):
        self.delete("all")
        w = max(self.winfo_width(), 100)
        h = max(self.winfo_height(), 60)
        edges, counts = self.hist
        if not edges:
            self.create_text(w / 2, h / 2,
                             text="Misfit histogram: no finite models yet",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 10))
            return
        left, right = 46, w - 14
        top, bottom = 18, h - 24
        cmax = max(counts) or 1
        bw = (right - left) / len(counts)
        for k, c in enumerate(counts):
            x0 = left + bw * k
            x1 = x0 + bw - 1
            y1 = bottom - (c / cmax) * (bottom - top)
            self.create_rectangle(x0, y1, x1, bottom, fill=HIST_BAR,
                                  outline=HIST_BAR_EDGE)

        def X(v):
            e0, e1 = edges[0], edges[-1]
            if e1 <= e0:
                return left
            return left + ((v - e0) / (e1 - e0)) * (right - left)

        for val, color, lab in ((self.best, MISFIT_BEST, "best"),
                                (self.median, MISFIT_MEDIAN, "median"),
                                (self.p90, MISFIT_P90, "P90")):
            if val is None:
                continue
            x = X(val)
            self.create_line(x, top - 4, x, bottom, fill=color, width=2)
            self.create_text(x, top + 2, text=lab, fill=color,
                             font=("Segoe UI", 7, "bold"))
        for frac, labv in ((0.0, edges[0]),
                           (0.5, (edges[0] + edges[-1]) / 2.0),
                           (1.0, edges[-1])):
            x = left + frac * (right - left)
            self.create_text(x, bottom + 6, text="%.2f" % labv,
                             fill=AXIS_COLOR, font=("Segoe UI", 7))
        self.create_text(left, top - 6, text="Misfit histogram (log10 H/V "
                                             "L2, finite models)",
                         anchor="w", fill=TEXT_COLOR,
                         font=("Segoe UI", 9, "bold"))


class VsProfileCanvas(tk.Canvas):
    """Staircase Vs-versus-depth chart of an inverted 1D model."""

    def __init__(self, master, **kw):
        kw.setdefault("bg", CANVAS_BG)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.layers = []      # list of dicts: top, bottom, vs, vp, rho, layer
        self.vs30 = None
        self.station = ""
        self.note = ""
        self.hist = (None, [])
        self.mh_best = None
        self.mh_median = None
        self.mh_p90 = None
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, layers, vs30=None, station="", note="", misfits=None,
                 misfit_best=None, misfit_median=None, misfit_p90=None):
        self.layers = list(layers)
        self.vs30 = vs30
        self.station = station
        self.note = note
        if misfits is not None:
            try:
                from hvsr_inversion import misfit_histogram
                self.hist = misfit_histogram(misfits)
            except Exception:
                self.hist = (None, [])
        self.mh_best = misfit_best
        self.mh_median = misfit_median
        self.mh_p90 = misfit_p90
        self.redraw()

    def _geom(self):
        w = max(self.winfo_width(), 100)
        h = max(self.winfo_height(), 100)
        return w, h, 64, w - 18, 26, h - 30

    def redraw(self):
        self.delete("all")
        w, h, left, right, top, bottom = self._geom()
        if not self.layers:
            self.create_text(w / 2, h / 2,
                             text="Run the 1D inversion to see the Vs profile",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 12))
            return
        vs_max = max((l["vs"] for l in self.layers), default=1000.0)
        vs_max = max(vs_max, max((l.get("vs_hi") or 0.0
                                  for l in self.layers), default=0.0))
        vs_max = math.ceil(vs_max / 500.0) * 500.0
        depth_max = max((l["bottom"] or l["top"] for l in self.layers),
                        default=30.0)
        depth_max = max(10.0, math.ceil(depth_max / 10.0) * 10.0)

        def X(v):
            return left + (v / vs_max) * (right - left)

        def Y(d):
            return top + (d / depth_max) * (bottom - top)

        for t in range(0, int(vs_max) + 1, 500):
            x = X(t)
            self.create_line(x, top, x, bottom, fill=GRID_COLOR)
            self.create_text(x, bottom + 8, text=str(t), fill=AXIS_COLOR,
                             font=("Segoe UI", 8))
        for t in range(0, int(depth_max) + 1, 10):
            y = Y(t)
            self.create_line(left, y, right, y, fill=GRID_COLOR)
            self.create_text(left - 6, y, text=str(t), anchor="e",
                             fill=AXIS_COLOR, font=("Segoe UI", 8))

        # uncertainty band: P16-P84 of the accepted ensemble per layer
        for lay in self.layers:
            lo = lay.get("vs_lo")
            hi = lay.get("vs_hi")
            if lo is None or hi is None:
                continue
            x0 = X(lo)
            x1 = X(hi)
            y0 = Y(lay["top"])
            y1 = Y(lay["bottom"] or lay["top"])
            self.create_rectangle(x0, y0, x1, y1, fill=VS_BAND,
                                  outline=VS_BAND_EDGE, width=1)

        # staircase profile
        prev_x = X(self.layers[0]["vs"])
        prev_y = Y(0.0)
        for lay in self.layers:
            x = X(lay["vs"])
            y0 = Y(lay["top"])
            y1 = Y(lay["bottom"] or lay["top"])
            self.create_line(prev_x, prev_y, x, y0, fill=MEAN_COLOR, width=2)
            self.create_line(x, y0, x, y1, fill=MEAN_COLOR, width=2)
            prev_x, prev_y = x, y1

        # half-space hatch
        last = self.layers[-1]
        xl = X(last["vs"])
        ytop = Y(last["top"])
        for i in range(0, 8):
            off = i * 8
            self.create_line(left + off, ytop, xl + off, ytop + 24,
                             fill=VS_HATCH)

        if self.vs30:
            y30 = Y(30.0)
            self.create_line(left, y30, right, y30, fill=F0_COLOR,
                             dash=(4, 3))
            self.create_text(right - 4, y30 - 8, text="30 m", anchor="e",
                             fill=F0_COLOR, font=("Segoe UI", 8, "bold"))

        self.create_line(left, top, left, bottom, fill=AXIS_COLOR)
        self.create_line(left, bottom, right, bottom, fill=AXIS_COLOR)
        self.create_text(left, top - 8, text="Vs (m/s)", anchor="w",
                         fill=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        self.create_text(left + (right - left) / 2, h - 10, text="Depth (m)",
                         fill=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        self.create_text(right, 12, text="Inverted Vs profile" +
                         (" - " + self.station if self.station else ""),
                         anchor="e", fill=PLACEHOLDER_COLOR,
                         font=("Segoe UI", 9, "italic"))
        if self.note:
            self.create_text(left, top + 14, text=self.note, anchor="w",
                             fill=PLACEHOLDER_COLOR, font=("Segoe UI", 8))

    def export_png(self, path):
        from chart_render import HvsrChart
        chart = HvsrChart(width=1100, height=620)
        chart.draw_vs_profile(self.layers, vs30=self.vs30,
                              station=self.station, note=self.note,
                              misfit_hist=self.hist,
                              misfit_best=self.mh_best,
                              misfit_median=self.mh_median,
                              misfit_p90=self.mh_p90)
        chart.save_png(path)
