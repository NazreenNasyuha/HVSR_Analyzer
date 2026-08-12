"""
hvsr_plot.py
===========
Public facade for the tkinter canvas chart widgets.  Each canvas
class now lives in its own focused module (hvsr_plot_curve /
_spectra / _colormap / _inversion); this module keeps the shared
palette block and re-exports every class so existing importers
keep working.  apply_palette() propagates to every canvas module
so a theme switch restyles all charts.
"""

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
    """Re-read the active theme colours into every plot module's globals."""
    import hvsr_plot_curve, hvsr_plot_spectra, hvsr_plot_colormap, hvsr_plot_inversion
    for _mod in (hvsr_plot_curve, hvsr_plot_spectra,
                 hvsr_plot_colormap, hvsr_plot_inversion):
        _mod.apply_palette()
    for _key, _value in hvsr_theme.current.items():
        if _key in globals():
            globals()[_key] = _value

# Re-exported from the focused canvas modules (public API stays here).
from hvsr_plot_util import _fmt_tick, _nice_ticks
from hvsr_plot_curve import HvsrCurveCanvas
from hvsr_plot_spectra import SpectraCanvas, TimeSeriesCanvas
from hvsr_plot_colormap import ColorMapCanvas
from hvsr_plot_inversion import MisfitHistCanvas, VsProfileCanvas
