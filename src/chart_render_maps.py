"""
chart_render_maps.py
====================
ChartMapMixin: the 2D charts - draw_timeseries, draw_colormap (with the
_viridis colour map) and draw_vs_profile.  Carries its own palette copy
so it restyles on theme switches (apply_palette refreshes it).

Split out of chart_render.py.
"""

import hvsr_theme
from chart_font import _text_width
def _viridis(t):
    """Theme colour-map colour for t in [0, 1]; returns an (r, g, b) tuple.
    Mirrors the palette used by the on-screen ColorMapCanvas."""
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
            return (r, g, b)
    return stops[-1][1]


BLACK = hvsr_theme.current["BLACK"]
GRID = hvsr_theme.current["GRID"]
AXIS = hvsr_theme.current["AXIS"]
MEAN = hvsr_theme.current["MEAN"]
F0COL = hvsr_theme.current["F0COL"]
VS_BAND_RGB = hvsr_theme.current["VS_BAND_RGB"]
VS_HATCH_RGB = hvsr_theme.current["VS_HATCH_RGB"]
HIST_BAR_RGB = hvsr_theme.current["HIST_BAR_RGB"]
MISFIT_BEST_RGB = hvsr_theme.current["MISFIT_BEST_RGB"]
MISFIT_MEDIAN_RGB = hvsr_theme.current["MISFIT_MEDIAN_RGB"]
MISFIT_P90_RGB = hvsr_theme.current["MISFIT_P90_RGB"]
CMAP_STOPS = list(hvsr_theme.current["CMAP_STOPS"])

def apply_palette(name=None):
    """Activate a theme (or re-apply the current one) and rebind colours."""
    if name is not None:
        hvsr_theme.apply_theme(name)
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

class ChartMapMixin:
    """Draw mixin: 2D time/colormap/profile charts."""
    def draw_colormap(self, y_labels, freqs, grid, vmin=None, vmax=None,
                      title="", ylabel="", log_freq=True):
        """2-D colour map (H/V vs time / azimuth) with a viridis palette
        and a vertical colour legend, matching ColorMapCanvas."""
        import math
        if not grid or not freqs:
            return
        vals = [v for row in grid for v in row if v == v]  # skip nan
        if vmin is None:
            vmin = min(vals) if vals else 0.0
        if vmax is None:
            vmax = max(vals) if vals else 1.0
        if vmax <= vmin:
            vmax = vmin + 1.0
        bar_w = 30
        left, right = self.left, self.right - bar_w - 14
        top, bottom = self.top, self.bottom - 30
        nrows = len(grid)
        ncols = len(freqs)
        rh = (bottom - top) / nrows
        cw = (right - left) / ncols
        span = vmax - vmin
        for ri in range(nrows):
            y0 = bottom - rh * ri - rh
            y1 = bottom - rh * ri
            for ci in range(ncols):
                v = grid[ri][ci]
                t = (v - vmin) / span if span > 0 else 0.0
                x0 = left + cw * ci
                x1 = left + cw * (ci + 1)
                self._fill_rect(int(x0), int(y0), int(x1), int(y1),
                                _viridis(t))
        # axes
        self._line(left, top, left, bottom, AXIS, 1)
        self._line(left, bottom, right, bottom, AXIS, 1)
        fmin, fmax = freqs[0], freqs[-1]
        if log_freq and fmin > 0:
            decade = math.floor(math.log10(fmin))
            while True:
                base = 10.0 ** decade
                for mult in (1, 2, 5, 10):
                    f = base * mult
                    if f < fmin - 1e-12:
                        continue
                    if f > fmax + 1e-12:
                        break
                    x = int(self._x_of(f, fmin, fmax))
                    self._line(x, bottom, x, bottom + 4, AXIS, 1)
                    label = ("%.0f" % f if f >= 10 else
                             ("%.1f" % f if f < 1 else "%.0f" % f))
                    self._text(x - _text_width(label) // 2, bottom + 8,
                               label, AXIS)
                else:
                    decade += 1
                    continue
                break
        # row labels (a handful)
        nl = min(5, nrows)
        for i in range(nl):
            ri = int(i * (nrows - 1) / max(1, nl - 1))
            lab = y_labels[ri]
            y = bottom - rh * ri - rh / 2
            text = "%.0f" % lab if abs(lab) >= 10 else "%.1f" % lab
            self._text(left - 8 - _text_width(text), int(y) - 3, text, AXIS)
        # colour legend bar
        bar_x = right + 8
        steps = 40
        for i in range(steps):
            t = i / (steps - 1)
            yy0 = bottom - (bottom - top) * i / steps
            yy1 = bottom - (bottom - top) * (i + 1) / steps
            self._fill_rect(bar_x, int(yy1), bar_x + bar_w, int(yy0),
                            _viridis(t))
        self._text(bar_x + bar_w // 2 - _text_width("%.2f" % vmax) // 2,
                   top - 12, "%.2f" % vmax, AXIS)
        self._text(bar_x + bar_w // 2 - _text_width("%.2f" % vmin) // 2,
                   bottom + 8, "%.2f" % vmin, AXIS)
        self._text(left, 14, title, BLACK, 2)
        self._text(left + (right - left) // 2, self.height - 12,
                   "Frequency (Hz)", BLACK, 1)
        if ylabel:
            self._text(left - 6, (top + bottom) // 2, ylabel, BLACK, 1)

    def draw_vs_profile(self, layers, vs30=None, station="", note="",
                         title="Inverted Vs profile", misfit_hist=None,
                         misfit_best=None, misfit_median=None,
                         misfit_p90=None):
        """Staircase Vs-versus-depth chart of a 1D inverted model.

        misfit_hist: optional (edges, counts) pair from
        hvsr_inversion.misfit_histogram; when provided the bottom ~22% of
        the chart becomes a misfit histogram panel with best/median/P90
        markers (misfit_best / misfit_median / misfit_p90).
        """
        import math
        if not layers:
            return
        hist_ht = 0
        if misfit_hist:
            _e, _c = misfit_hist
            if _e and _c:
                hist_ht = int((self.bottom - self.top) * 0.22)
        _saved_bottom = self.bottom
        self.bottom = self.bottom - hist_ht
        vs_max = max((l["vs"] for l in layers), default=1000.0)
        vs_max = max(vs_max, max((l.get("vs_hi") or 0.0
                                  for l in layers), default=0.0))
        vs_max = math.ceil(vs_max / 500.0) * 500.0
        depth_max = max((l["bottom"] or l["top"] for l in layers),
                        default=30.0)
        depth_max = max(10.0, math.ceil(depth_max / 10.0) * 10.0)
        self._text(self.left, 14, title, BLACK, 2)
        if station:
            self._text(self.left, 36, "Station: " + station, AXIS, 1)

        def X(v):
            return self.left + (v / vs_max) * (self.right - self.left)

        def Y(d):
            return self.top + (d / depth_max) * (self.bottom - self.top)

        for t in range(0, int(vs_max) + 1, 500):
            x = int(X(t))
            self._line(x, self.top, x, self.bottom, GRID, 1)
            self._text(x - _text_width(str(t)) // 2, self.bottom + 8,
                       str(t), AXIS)
        for t in range(0, int(depth_max) + 1, 10):
            y = int(Y(t))
            self._line(self.left, y, self.right, y, GRID, 1)
            self._text(self.left - 8 - _text_width(str(t)), y - 3, str(t),
                       AXIS)

        # uncertainty band: P16-P84 of the accepted ensemble per layer
        for lay in layers:
            lo = lay.get("vs_lo")
            hi = lay.get("vs_hi")
            if lo is None or hi is None:
                continue
            self._fill_rect(X(lo), Y(lay["top"]), X(hi),
                            Y(lay["bottom"] or lay["top"]),
                            VS_BAND_RGB)

        prev_x, prev_y = X(layers[0]["vs"]), Y(0.0)
        for lay in layers:
            x, y0 = X(lay["vs"]), Y(lay["top"])
            y1 = Y(lay["bottom"] or lay["top"])
            self._line(prev_x, prev_y, x, y0, MEAN, 2)
            self._line(x, y0, x, y1, MEAN, 2)
            prev_x, prev_y = x, y1
        last = layers[-1]
        ytop = Y(last["top"])
        for i in range(8):
            off = i * 8
            self._line(self.left + off, ytop, X(last["vs"]) + off, ytop + 24,
                       VS_HATCH_RGB, 1)
        if vs30:
            y30 = Y(30.0)
            self._dashed_line(self.left, y30, self.right, y30, F0COL, 5, 4, 1)
            self._text(self.right - 6 - _text_width("30 m"), y30 - 12,
                       "30 m", F0COL)
        self._line(self.left, self.top, self.left, self.bottom, AXIS, 1)
        self._line(self.left, self.bottom, self.right, self.bottom, AXIS, 1)
        self._text(self.left, self.height - 18 - hist_ht, "Depth (m)", BLACK, 1)
        self._text(self.left, self.top - 14, "Vs (m/s)", BLACK, 1)

        # misfit histogram panel (optional)
        if hist_ht:
            top0 = _saved_bottom - hist_ht + 8
            bot0 = _saved_bottom - 8
            edges, counts = misfit_hist
            cmax = max(counts) or 1
            bw = (self.right - self.left) / len(counts)
            for k, c in enumerate(counts):
                x0 = self.left + bw * k
                x1 = x0 + bw - 1
                y1 = bot0 - (c / cmax) * (bot0 - top0)
                self._fill_rect(int(x0), int(y1), int(x1), int(bot0),
                                HIST_BAR_RGB)
            def HX(v):
                e0, e1 = edges[0], edges[-1]
                if e1 <= e0:
                    return self.left
                return self.left + ((v - e0) / (e1 - e0)) * (self.right - self.left)
            for val, color, lab in ((misfit_best, MISFIT_BEST_RGB, "best"),
                                    (misfit_median, MISFIT_MEDIAN_RGB, "median"),
                                    (misfit_p90, MISFIT_P90_RGB, "P90")):
                if val is None:
                    continue
                x = int(HX(val))
                self._line(x, top0 - 4, x, bot0, color, 2)
                self._text(x - _text_width(lab) // 2, top0 + 2, lab, color)
            self._line(self.left, bot0, self.right, bot0, AXIS, 1)
            self._text(self.left, _saved_bottom - 4,
                       "Misfit histogram (log10 H/V L2)", BLACK, 1)
        self.bottom = _saved_bottom
