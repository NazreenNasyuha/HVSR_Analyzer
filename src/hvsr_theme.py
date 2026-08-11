"""
hvsr_theme.py
=============
Central theme palettes for the HVSR Analyzer (pure standard library).

The GUI (hvsr_gui.py), the on-screen chart widgets (hvsr_plot.py) and the
PNG rasterizer (chart_render.py) all read their colours from the single
``current`` palette defined here, so switching theme restyles every widget
and every exported image in one step.

Two themes ship with the program:

- ``dark`` (default): the retro black / neon terminal look.
- ``bw``: a high-contrast black-and-white theme designed to be printed in
  a thesis or paper (white backgrounds, black lines, grey shading only).

Usage:

    import hvsr_theme
    hvsr_theme.apply_theme("bw")
    accent = hvsr_theme.current["ACCENT"]
"""

# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------
# Keys shared with hvsr_gui.py:
#   ACCENT, BG, PANEL_BG, TEXT_DARK, TEXT_MUTED, OK_GREEN, NO_RED, HOVER
# Keys shared with hvsr_plot.py (hex strings):
#   CANVAS_BG, GRID_COLOR, AXIS_COLOR, MEAN_COLOR, BAND_COLOR, F0_COLOR,
#   EXTRA_COLOR, WIN_COLOR, TRACE_COLORS, PLACEHOLDER_COLOR, TEXT_COLOR,
#   SPEC_FALLBACK_COLORS, HIST_BAR, HIST_BAR_EDGE, MISFIT_BEST,
#   MISFIT_MEDIAN, MISFIT_P90, VS_BAND, VS_BAND_EDGE, VS_HATCH, CMAP_STOPS
# Keys shared with chart_render.py (RGB tuples):
#   WHITE, BLACK, GRID, AXIS, BAND, MEAN, F0COL, GEOPSY, WINCOL, TS_COLORS,
#   CMAP_STOPS, VS_BAND_RGB, VS_HATCH_RGB, HIST_BAR_RGB, MISFIT_BEST_RGB,
#   MISFIT_MEDIAN_RGB, MISFIT_P90_RGB

_DARK_CMAP = [
    (0.00, (68, 1, 84)), (0.25, (59, 82, 139)), (0.50, (33, 145, 140)),
    (0.75, (94, 201, 98)), (1.00, (253, 231, 37)),
]
_BW_CMAP = [
    (0.00, (255, 255, 255)), (0.25, (212, 212, 212)), (0.50, (128, 128, 128)),
    (0.75, (64, 64, 64)), (1.00, (0, 0, 0)),
]

THEMES = {
    "dark": {
        # --- GUI ---
        "ACCENT": "#FF6600",
        "BG": "#050505",
        "PANEL_BG": "#151515",
        "TEXT_DARK": "#39FF14",
        "TEXT_MUTED": "#D9822B",
        "OK_GREEN": "#39FF14",
        "NO_RED": "#FF0033",
        "HOVER": "#53257F",
        # --- plot canvases (hex) ---
        "CANVAS_BG": "#0d0d0d",
        "GRID_COLOR": "#202026",
        "AXIS_COLOR": "#9aa0aa",
        "MEAN_COLOR": "#FF6600",
        "BAND_COLOR": "#3d2a12",
        "F0_COLOR": "#FF0033",
        "EXTRA_COLOR": "#AA5500",
        "WIN_COLOR": "#39FF14",
        "TRACE_COLORS": {"Z": "#d6dae2", "N": "#00a8ff", "E": "#39FF14"},
        "PLACEHOLDER_COLOR": "#8a8f99",
        "TEXT_COLOR": "#d6dae2",
        "SPEC_FALLBACK_COLORS": ("#d6dae2", "#1456a8", "#0f8a4b"),
        "HIST_BAR": "#27405c",
        "HIST_BAR_EDGE": "#2f4a66",
        "MISFIT_BEST": "#FF0033",
        "MISFIT_MEDIAN": "#1456a8",
        "MISFIT_P90": "#9aa0aa",
        "VS_BAND": "#22293a",
        "VS_BAND_EDGE": "#2b3450",
        "VS_HATCH": "#7f8db0",
        "CMAP_STOPS": _DARK_CMAP,
        # --- PNG rasterizer (RGB) ---
        "WHITE": (13, 13, 13),
        "BLACK": (214, 218, 226),
        "GRID": (32, 32, 38),
        "AXIS": (154, 160, 170),
        "BAND": (61, 42, 18),
        "MEAN": (255, 102, 0),
        "F0COL": (255, 0, 51),
        "GEOPSY": (170, 85, 0),
        "WINCOL": (57, 255, 20),
        "TS_COLORS": {"Z": (214, 218, 226), "N": (0, 168, 255),
                       "E": (57, 255, 20)},
        "VS_BAND_RGB": (34, 41, 58),
        "VS_HATCH_RGB": (43, 52, 80),
        "HIST_BAR_RGB": (157, 182, 216),
        "MISFIT_BEST_RGB": (198, 40, 40),
        "MISFIT_MEDIAN_RGB": (20, 86, 168),
        "MISFIT_P90_RGB": (106, 112, 128),
    },
    "bw": {
        # --- GUI ---
        "ACCENT": "#000000",
        "BG": "#FFFFFF",
        "PANEL_BG": "#F2F2F2",
        "TEXT_DARK": "#000000",
        "TEXT_MUTED": "#444444",
        "OK_GREEN": "#111111",
        "NO_RED": "#999999",
        "HOVER": "#555555",
        # --- plot canvases (hex) ---
        "CANVAS_BG": "#FFFFFF",
        "GRID_COLOR": "#D8D8D8",
        "AXIS_COLOR": "#000000",
        "MEAN_COLOR": "#000000",
        "BAND_COLOR": "#C9C9C9",
        "F0_COLOR": "#404040",
        "EXTRA_COLOR": "#666666",
        "WIN_COLOR": "#555555",
        "TRACE_COLORS": {"Z": "#000000", "N": "#666666",
                          "E": "#B3B3B3"},
        "PLACEHOLDER_COLOR": "#888888",
        "TEXT_COLOR": "#000000",
        "SPEC_FALLBACK_COLORS": ("#000000", "#666666", "#B3B3B3"),
        "HIST_BAR": "#C9C9C9",
        "HIST_BAR_EDGE": "#A6A6A6",
        "MISFIT_BEST": "#000000",
        "MISFIT_MEDIAN": "#666666",
        "MISFIT_P90": "#999999",
        "VS_BAND": "#D9D9D9",
        "VS_BAND_EDGE": "#BDBDBD",
        "VS_HATCH": "#808080",
        "CMAP_STOPS": _BW_CMAP,
        # --- PNG rasterizer (RGB) ---
        "WHITE": (255, 255, 255),
        "BLACK": (0, 0, 0),
        "GRID": (216, 216, 216),
        "AXIS": (0, 0, 0),
        "BAND": (201, 201, 201),
        "MEAN": (0, 0, 0),
        "F0COL": (64, 64, 64),
        "GEOPSY": (102, 102, 102),
        "WINCOL": (85, 85, 85),
        "TS_COLORS": {"Z": (0, 0, 0), "N": (102, 102, 102),
                       "E": (179, 179, 179)},
        "VS_BAND_RGB": (217, 217, 217),
        "VS_HATCH_RGB": (128, 128, 128),
        "HIST_BAR_RGB": (201, 201, 201),
        "MISFIT_BEST_RGB": (0, 0, 0),
        "MISFIT_MEDIAN_RGB": (102, 102, 102),
        "MISFIT_P90_RGB": (153, 153, 153),
    },
}

# The palette in use.  Mutated in place by apply_theme() so modules that
# hold a reference (e.g. ``from hvsr_theme import current``) always see
# the latest colours.
current = dict(THEMES["dark"])

# Aliases so callers can write ``hvsr_theme.dark`` / ``hvsr_theme.bw``.
dark = THEMES["dark"]
bw = THEMES["bw"]


class ThemeError(ValueError):
    """Raised when an unknown theme name is requested."""


def apply_theme(name):
    """Activate a theme by name ("dark" or "bw") and return ``current``."""
    if name not in THEMES:
        raise ThemeError("unknown theme: %r (available: %s)"
                         % (name, ", ".join(sorted(THEMES))))
    current.clear()
    current.update(THEMES[name])
    return current


def get(name=None):
    """Return the active palette, or a named palette when ``name`` is given."""
    if name is None:
        return current
    return THEMES[name]
