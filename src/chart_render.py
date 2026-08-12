"""
chart_render.py
===============
Chart rendering without matplotlib or PIL.  Public facade for the
software rasterizer: write_png lives in chart_png.py, the bitmap
font in chart_font.py, and HvsrChart composes ChartRenderer
(primitives), ChartCurveMixin and ChartMapMixin from the focused
modules.  This module keeps the palette block and re-exports the
public API (HvsrChart, write_png, GRID/AXIS/BLACK, _text_width).
"""

import hvsr_theme
import chart_render_core, chart_render_curves, chart_render_maps
from chart_png import write_png
from chart_font import _FONT, FONT_W, FONT_H, _text_width, _draw_text
from chart_render_core import ChartRenderer
from chart_render_curves import ChartCurveMixin
from chart_render_maps import ChartMapMixin

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
    """Re-read the active theme colours into every chart module's globals."""
    """Activate a theme (or re-apply the current one) and rebind colours."""
    if name is not None:
        hvsr_theme.apply_theme(name)
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value
    for _mod in (chart_render_core, chart_render_curves, chart_render_maps):
        _mod.apply_palette(name)

class HvsrChart(ChartRenderer, ChartCurveMixin, ChartMapMixin):
    """Pure-stdlib chart rasterizer: draws log-frequency H/V charts,
    spectra, time series, colour maps and Vs profiles into an
    off-screen pixel buffer and exports them as PNG files."""

    def save_png(self, path):
        write_png(path, self.width, self.height, self.pixels)
