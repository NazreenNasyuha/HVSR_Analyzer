"""
hvsr_plot_inversion.py
======================
Inversion canvases: MisfitHistCanvas (misfit histogram) and
VsProfileCanvas (Vs profile with the 1-sigma band and bedrock hatch).
Carries its own palette copy so it restyles on theme switches
(apply_palette refreshes it).

Split out of hvsr_plot.py.
"""

import math
import tkinter as tk
import hvsr_theme

CANVAS_BG = hvsr_theme.current["CANVAS_BG"]
GRID_COLOR = hvsr_theme.current["GRID_COLOR"]
AXIS_COLOR = hvsr_theme.current["AXIS_COLOR"]
MEAN_COLOR = hvsr_theme.current["MEAN_COLOR"]
F0_COLOR = hvsr_theme.current["F0_COLOR"]
PLACEHOLDER_COLOR = hvsr_theme.current["PLACEHOLDER_COLOR"]
TEXT_COLOR = hvsr_theme.current["TEXT_COLOR"]
HIST_BAR = hvsr_theme.current["HIST_BAR"]
HIST_BAR_EDGE = hvsr_theme.current["HIST_BAR_EDGE"]
MISFIT_BEST = hvsr_theme.current["MISFIT_BEST"]
MISFIT_MEDIAN = hvsr_theme.current["MISFIT_MEDIAN"]
MISFIT_P90 = hvsr_theme.current["MISFIT_P90"]
VS_BAND = hvsr_theme.current["VS_BAND"]
VS_BAND_EDGE = hvsr_theme.current["VS_BAND_EDGE"]
VS_HATCH = hvsr_theme.current["VS_HATCH"]

def apply_palette():
    """Re-read the active theme colours into this module's globals."""
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

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
        """Feed (bins, counts) plus the three marker values."""
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
        """Feed the inverted layer list plus summary values; the misfit
        statistics are forwarded to the histogram below the profile."""
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
