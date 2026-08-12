"""
chart_render_curves.py
======================
ChartCurveMixin: the curve and trace charts - draw_hvsr (H/V with
+/- 1 sigma band and f0 marker), draw_spectra and draw_timeseries.
Carries its own palette copy so it restyles on theme switches
(apply_palette refreshes it).

Split out of chart_render.py.
"""

import hvsr_theme
from chart_font import _text_width

BLACK = hvsr_theme.current["BLACK"]
GRID = hvsr_theme.current["GRID"]
AXIS = hvsr_theme.current["AXIS"]
BAND = hvsr_theme.current["BAND"]
MEAN = hvsr_theme.current["MEAN"]
F0COL = hvsr_theme.current["F0COL"]
GEOPSY = hvsr_theme.current["GEOPSY"]
WINCOL = hvsr_theme.current["WINCOL"]
TS_COLORS = dict(hvsr_theme.current["TS_COLORS"])

def apply_palette(name=None):
    """Activate a theme (or re-apply the current one) and rebind colours."""
    if name is not None:
        hvsr_theme.apply_theme(name)
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

class ChartCurveMixin:
    """Draw mixin: curve and trace charts."""
    def draw_hvsr(self, freqs, mean, low, high, f0, a0, station="",
                  fmin=None, fmax=None, extra=None, extra_label=None,
                  title="H/V Spectral Ratio"):
        """Render the full chart into the pixel buffer."""
        import math
        if fmin is None:
            fmin = 0.5
        if fmax is None:
            fmax = 20.0
        data_max = max(max(mean), max(high), f0)
        if extra:
            data_max = max(data_max, max(extra))
        vmax = max(4.0, math.ceil(data_max + 1.0))

        # title
        self._text(self.left, 14, title, BLACK, 2)
        if station:
            self._text(self.left, 36, "Station: " + station, AXIS, 1)

        self._draw_axes_and_grid(fmin, fmax, vmax)

        xs = [self._x_of(f, fmin, fmax) for f in freqs]
        ys_high = [self._y_of(v, 0, vmax) for v in high]
        ys_low = [self._y_of(v, 0, vmax) for v in low]
        ys_mean = [self._y_of(v, 0, vmax) for v in mean]

        # +/- 1 sigma band
        band_px = []
        for i in range(len(xs)):
            band_px.append((int(xs[i]), int(ys_high[i])))
        for i in range(len(xs) - 1, -1, -1):
            band_px.append((int(xs[i]), int(ys_low[i])))
        for i in range(len(band_px) - 1):
            self._line(band_px[i][0], band_px[i][1], band_px[i + 1][0],
                       band_px[i + 1][1], BAND, 1)

        if extra:
            xs_e = [self._x_of(f, fmin, fmax) for f in freqs]
            ys_e = [self._y_of(v, 0, vmax) for v in extra]
            self._polyline(xs_e, ys_e, GEOPSY, 3)

        self._polyline(xs, ys_mean, MEAN, 2)

        # f0 marker
        xf0 = self._x_of(f0, fmin, fmax)
        yf0 = self._y_of(a0, 0, vmax)
        self._dashed_line(xf0, self.top, xf0, self.bottom, F0COL, 6, 4, 1)
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                if dx * dx + dy * dy <= 9:
                    self._px(xf0 + dx, yf0 + dy, F0COL, 1)

        # legend
        ly = self.top + 8
        self._line(self.left + 4, ly + 4, self.left + 40, ly + 4, MEAN, 3)
        self._text(self.left + 46, ly, "Mean curve (lognormal)", BLACK)
        ly += 16
        for i in range(3):
            self._line(self.left + 4 + i * 2, ly + 3, self.left + 40, ly + 3, BAND, 1)
        self._text(self.left + 46, ly - 3, "+/- 1 sigma", BLACK)
        ly += 16
        self._line(self.left + 4, ly + 4, self.left + 40, ly + 4, F0COL, 2)
        self._text(self.left + 46, ly, "f0 = %.3f Hz   A0 = %.2f" % (f0, a0), BLACK)
        if extra_label:
            ly += 16
            self._line(self.left + 4, ly + 4, self.left + 40, ly + 4, GEOPSY, 3)
            self._text(self.left + 46, ly, extra_label, BLACK)

        self._text(self.left, self.height - 18, "Frequency (Hz)", BLACK, 1)
        self._text(self.right - 150, self.top + 2, "H/V Amplification", BLACK, 1)

    def draw_spectra(self, freqs, curves, mode="PSD", station="",
                     fmin=None, fmax=None):
        """Render PSD (dB) or Fourier amplitude spectra of Z / N / E."""
        import math
        if not freqs or not curves:
            return
        if fmin is None:
            fmin = min(freqs)
        if fmax is None:
            fmax = max(freqs)
        vals = [v for c in ("z", "n", "e") for v in curves.get(c, [])]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-30:
            hi = lo + 1.0
        pad = (hi - lo) * 0.08
        vmin, vmax = lo - pad, hi + pad

        self._text(self.left, 14, (mode + " - " + ("dB (rel.)"
                   if mode == "PSD" else "amplitude")), BLACK, 2)
        if station:
            self._text(self.left, 36, "Station: " + station, AXIS, 1)

        # log-frequency grid
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
                self._line(x, self.top, x, self.bottom, GRID, 1)
                label = ("%.0f" % f if f >= 10 else
                         ("%.1f" % f if f < 1 else "%.0f" % f))
                self._text(x - _text_width(label) // 2, self.bottom + 8,
                           label, AXIS)
            else:
                decade += 1
                continue
            break

        # horizontal grid + numeric labels
        for t in range(5):
            v = vmin + t * (vmax - vmin) / 4.0
            y = int(self._y_of(v, vmin, vmax))
            self._line(self.left, y, self.right, y, GRID, 1)
            self._text(self.left - 8 - _text_width("%.0f" % v), y - 3,
                       "%.0f" % v, AXIS)
        self._line(self.left, self.top, self.left, self.bottom, AXIS, 1)
        self._line(self.left, self.bottom, self.right, self.bottom, AXIS, 1)

        colors = {k.lower(): v for k, v in TS_COLORS.items()}
        ly = self.top + 6
        step = max(1, len(freqs) // (self.right - self.left))
        for key, label in (("z", "Z"), ("n", "N"), ("e", "E")):
            cv = curves.get(key)
            if not cv:
                continue
            xs = [self._x_of(f, fmin, fmax) for f in freqs[::step]]
            ys = [self._y_of(v, vmin, vmax) for v in cv[::step]]
            self._polyline(xs, ys, colors[key], 2)
            self._line(self.left + 4, ly + 4, self.left + 32, ly + 4,
                       colors[key], 3)
            self._text(self.left + 38, ly, label, colors[key])
            ly += 16
        self._text(self.left, self.height - 18, "Frequency (Hz)", BLACK, 1)

    def draw_timeseries(self, traces, fs, win_len=0.0, station=""):
        """Stacked component waveforms with the selectable analysis-window
        overlay (green boxes), matching the GUI TimeSeriesCanvas."""
        if not traces:
            return
        n = len(traces)
        top, bottom = self.top, self.bottom - 26
        left, right = self.left + 30, self.right - 8
        band = (bottom - top) / n
        tmax = max((len(v) / fs for _, v in traces), default=0.0)
        if tmax <= 0:
            return
        self._text(self.left, 14, "Filtered waveforms", BLACK, 2)
        if station:
            self._text(self.left, 36, "Station: " + station, AXIS, 1)
        for i, (label, values) in enumerate(traces):
            y0 = top + band * i
            y1 = y0 + band
            mid = (y0 + y1) / 2
            self._text(left - 22, int(mid) - 3, label, TS_COLORS.get(
                label, BLACK))
            vm = max((abs(v) for v in values), default=1.0)
            if vm == 0:
                vm = 1.0
            xs = []
            ys = []
            step = max(1, len(values) // max(int(right - left), 200))
            for k in range(0, len(values), step):
                t = k / fs
                x = left + (t / tmax) * (right - left)
                y = mid - (values[k] / vm) * (band * 0.4)
                xs.append(x)
                ys.append(y)
            self._polyline(xs, ys, TS_COLORS.get(label, BLACK), 1)
            self._line(left, int(y0), right, int(y0), GRID, 1)
            self._line(left, int(y1), right, int(y1), GRID, 1)
            if win_len > 0 and int(win_len) >= 1:
                step = int(win_len)
                for t0 in range(0, int(tmax), step):
                    x0 = left + (t0 / tmax) * (right - left)
                    x1 = left + (min(t0 + win_len, tmax) / tmax) * (right - left)
                    self._line(int(x0), int(y0) + 2, int(x1), int(y0) + 2,
                               WINCOL, 1)
                    self._line(int(x0), int(y1) - 2, int(x1), int(y1) - 2,
                               WINCOL, 1)
                    self._line(int(x0), int(y0) + 2, int(x0), int(y1) - 2,
                               WINCOL, 1)
                    self._line(int(x1), int(y0) + 2, int(x1), int(y1) - 2,
                               WINCOL, 1)
        self._text(left + (right - left) // 2, self.height - 14,
                   "Time (s)", BLACK, 1)
        for t in range(0, int(tmax) + 1, max(1, int(tmax) // 6)):
            x = left + (t / tmax) * (right - left)
            self._text(int(x) - _text_width(str(t)) // 2, self.bottom - 6,
                       str(t), AXIS)
