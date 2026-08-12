"""
chart_render_core.py
====================
ChartRenderer: the software-rasterizer primitives behind HvsrChart
(pixel buffer setup, _px / _line / _dashed_line / _polyline / _fill_rect,
bitmap _text and the log axes + grid).  Carries its own palette copy so
it restyles on theme switches (apply_palette refreshes it).

Split out of chart_render.py.
"""

import hvsr_theme
from chart_font import _draw_text, _text_width

WHITE = hvsr_theme.current["WHITE"]
BLACK = hvsr_theme.current["BLACK"]
GRID = hvsr_theme.current["GRID"]
AXIS = hvsr_theme.current["AXIS"]

def apply_palette(name=None):
    """Activate a theme (or re-apply the current one) and rebind colours."""
    if name is not None:
        hvsr_theme.apply_theme(name)
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

class ChartRenderer:
    """Software-rasterizer primitives shared by every chart."""
    def __init__(self, width=1100, height=620):
        self.width = width
        self.height = height
        self.left = 78
        self.right = width - 30
        self.top = 64
        self.bottom = height - 62
        self.pixels = [[WHITE for _ in range(width)] for _ in range(height)]

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

    def _x_of(self, f, fmin, fmax):
        import math
        l0, l1 = math.log(fmin), math.log(fmax)
        t = (math.log(f) - l0) / (l1 - l0) if f > 0 else 0
        return self.left + t * (self.right - self.left)

    def _y_of(self, v, vmin, vmax):
        t = (v - vmin) / (vmax - vmin) if vmax > vmin else 0
        return self.bottom - t * (self.bottom - self.top)

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
