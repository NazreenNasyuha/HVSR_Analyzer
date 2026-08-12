"""
hvsr_plot_util.py
================
Pure tick helpers shared by the canvases: _nice_ticks (1-2-5 log
placement) and _fmt_tick (log-frequency label formatting).

Split out of hvsr_plot.py.
"""

import math

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
