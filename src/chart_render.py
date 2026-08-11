"""
chart_render.py
===============
Chart rendering without matplotlib or PIL.

- write_png(): a real PNG encoder built on the standard-library zlib and
  struct modules.
- HvsrChart: a small software rasterizer that draws a log-frequency H/V
  chart (axes, grid, mean curve, +/- 1 sigma band, f0 marker, legend) using
  a built-in 5x7 bitmap font, and exports it as a PNG file.
"""

import struct
import zlib

# ----------------------------------------------------------------------
# PNG encoder (pure standard library)
# ----------------------------------------------------------------------
def write_png(path, width, height, pixel_rows):
    """Write an 8-bit RGB PNG.  pixel_rows is an iterable of rows, each row
    an iterable of (r, g, b) tuples of length `width`."""
    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out

    raw = bytearray()
    for row in pixel_rows:
        raw.append(0)  # filter type: none
        for px in row:
            raw.extend((px[0] & 255, px[1] & 255, px[2] & 255))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = signature
    data += chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(data)


# ----------------------------------------------------------------------
# 5x7 bitmap font (compact string rows, '#' = filled pixel)
# ----------------------------------------------------------------------
_FONT = {
    " ": ("00000",) * 7,
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "a": ("00000", "00000", "01110", "00001", "01111", "10001", "01111"),
    "b": ("10000", "10000", "10110", "11001", "10001", "10001", "11110"),
    "c": ("00000", "00000", "01110", "10000", "10000", "10001", "01110"),
    "d": ("00001", "00001", "01101", "10011", "10001", "10001", "01111"),
    "e": ("00000", "00000", "01110", "10001", "11111", "10000", "01110"),
    "f": ("00110", "01001", "01000", "11100", "01000", "01000", "01000"),
    "g": ("00000", "00000", "01111", "10001", "01111", "00001", "01110"),
    "h": ("10000", "10000", "10110", "11001", "10001", "10001", "10001"),
    "i": ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
    "j": ("00010", "00000", "00110", "00010", "00010", "10010", "01100"),
    "k": ("10000", "10000", "10010", "10100", "11000", "10100", "10010"),
    "l": ("01100", "00100", "00100", "00100", "00100", "00100", "01110"),
    "m": ("00000", "00000", "11010", "10101", "10101", "10001", "10001"),
    "n": ("00000", "00000", "10110", "11001", "10001", "10001", "10001"),
    "o": ("00000", "00000", "01110", "10001", "10001", "10001", "01110"),
    "p": ("00000", "00000", "11110", "10001", "11110", "10000", "10000"),
    "q": ("00000", "00000", "01101", "10011", "01111", "00001", "00001"),
    "r": ("00000", "00000", "10110", "11001", "10000", "10000", "10000"),
    "s": ("00000", "00000", "01111", "10000", "01110", "00001", "11110"),
    "t": ("01000", "01000", "11100", "01000", "01000", "01001", "00110"),
    "u": ("00000", "00000", "10001", "10001", "10001", "10011", "01101"),
    "v": ("00000", "00000", "10001", "10001", "10001", "01010", "00100"),
    "w": ("00000", "00000", "10001", "10001", "10101", "10101", "01010"),
    "x": ("00000", "00000", "10001", "01010", "00100", "01010", "10001"),
    "y": ("00000", "00000", "10001", "10001", "01111", "00001", "01110"),
    "z": ("00000", "00000", "11111", "00010", "00100", "01000", "11111"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "=": ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    ",": ("00000", "00000", "00000", "00000", "01100", "01100", "00100"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "|": ("00100", "00100", "00100", "00100", "00100", "00100", "00100"),
    "~": ("00000", "01101", "10010", "00000", "00000", "00000", "00000"),
}

FONT_W = 5
FONT_H = 7


def _text_width(text):
    return len(text) * (FONT_W + 1) - 1


def _draw_text(pixels, x, y, text, color, scale=1):
    """Draw text at (x, y) top-left.  Unknown characters are skipped."""
    w = FONT_W + 1
    h = FONT_H + 1
    for ch in text:
        glyph = _FONT.get(ch)
        if glyph is not None:
            for row in range(FONT_H):
                for col in range(FONT_W):
                    if row < 7 and col < 5 and glyph[row][col] == "#":
                        px = x + col
                        py = y + row
                        if scale == 1:
                            if 0 <= px < len(pixels[0]) and 0 <= py < len(pixels):
                                pixels[py][px] = color
                        else:
                            for dy in range(scale):
                                for dx in range(scale):
                                    sx = x + col * scale + dx
                                    sy = y + row * scale + dy
                                    if 0 <= sx < len(pixels[0]) and 0 <= sy < len(pixels):
                                        pixels[sy][sx] = color
        x += w * scale


# ----------------------------------------------------------------------
# H/V chart rasterizer
# ----------------------------------------------------------------------
import hvsr_theme

WHITE = hvsr_theme.current["WHITE"]
BLACK = hvsr_theme.current["BLACK"]
GRID = hvsr_theme.current["GRID"]
AXIS = hvsr_theme.current["AXIS"]
BAND = hvsr_theme.current["BAND"]
MEAN = hvsr_theme.current["MEAN"]
F0COL = hvsr_theme.current["F0COL"]
GEOPSY = hvsr_theme.current["GEOPSY"]
WINCOL = hvsr_theme.current["WINCOL"]
TS_COLORS = dict(hvsr_theme.current["TS_COLORS"])
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


class HvsrChart:
    """Software-rendered log-frequency H/V chart exported to PNG."""

    def __init__(self, width=1100, height=620):
        self.width = width
        self.height = height
        self.left = 78
        self.right = width - 30
        self.top = 64
        self.bottom = height - 62
        self.pixels = [[WHITE for _ in range(width)] for _ in range(height)]

    # -- low-level helpers ------------------------------------------------
    def _px(self, x, y, color, size=1):
        for dy in range(size):
            for dx in range(size):
                px = int(x) + dx
                py = int(y) + dy
                if 0 <= px < self.width and 0 <= py < self.height:
                    self.pixels[py][px] = color

    def _line(self, x0, y0, x1, y1, color, width=1):
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(steps + 1):
            t = i / steps
            self._px(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, color, width)

    def _dashed_line(self, x0, y0, x1, y1, color, dash=6, gap=4, width=1):
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        on = True
        count = 0
        for i in range(steps + 1):
            t = i / steps
            if on:
                self._px(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, color, width)
            count += 1
            if count >= (dash if on else gap):
                count = 0
                on = not on

    def _polyline(self, xs, ys, color, width=1):
        for i in range(len(xs) - 1):
            self._line(xs[i], ys[i], xs[i + 1], ys[i + 1], color, width)

    def _fill_rect(self, x0, y0, x1, y1, color):
        """Solid rectangle (x0<=x1, y0<=y1) drawn with scan lines."""
        x0, x1 = int(max(x0, 0)), int(min(x1, self.width - 1))
        y0, y1 = int(max(y0, 0)), int(min(y1, self.height - 1))
        for y in range(y0, y1 + 1):
            self._line(x0, y, x1, y, color, 1)

    def _text(self, x, y, text, color=BLACK, scale=1):
        _draw_text(self.pixels, int(x), int(y), text, color, scale)

    # -- mapping -----------------------------------------------------------
    def _x_of(self, f, fmin, fmax):
        import math
        l0, l1 = math.log(fmin), math.log(fmax)
        t = (math.log(f) - l0) / (l1 - l0) if f > 0 else 0
        return self.left + t * (self.right - self.left)

    def _y_of(self, v, vmin, vmax):
        t = (v - vmin) / (vmax - vmin) if vmax > vmin else 0
        return self.bottom - t * (self.bottom - self.top)

    # -- drawing -----------------------------------------------------------
    def _draw_axes_and_grid(self, fmin, fmax, vmax, vmin=0.0):
        # vertical grid + labels at 1-2-5 decades
        import math
        decade = math.floor(math.log10(fmin))
        while True:
            base = 10.0 ** decade
            for mult in (1, 2, 5, 10):
                f = base * mult
                if f < fmin - 1e-12:
                    continue
                if f > fmax + 1e-12:
                    return
                x = int(self._x_of(f, fmin, fmax))
                self._line(x, self.top, x, self.bottom, GRID, 1)
                label = "%.0f" % f if f >= 10 else ("%.1f" % f if f < 1 else "%.0f" % f)
                self._text(x - _text_width(label) // 2, self.bottom + 8, label, AXIS)
            decade += 1

        # horizontal grid
        for tick in range(1, int(vmax) + 2):
            if tick > vmax + 0.5:
                break
            y = int(self._y_of(tick, vmin, vmax))
            if tick % 2 == 0:
                self._line(self.left, y, self.right, y, GRID, 1)
            self._text(self.left - 8 - _text_width(str(tick)), y - 3, str(tick), AXIS)

        self._line(self.left, self.top, self.left, self.bottom, AXIS, 1)
        self._line(self.left, self.bottom, self.right, self.bottom, AXIS, 1)

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

    def save_png(self, path):
        write_png(path, self.width, self.height, self.pixels)
