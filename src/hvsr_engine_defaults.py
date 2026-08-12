"""
hvsr_engine_defaults.py
=======================
The DEFAULT_* processing defaults and MAX_PICK_FREQ used across the
analysis pipeline (fmin / fmax / taper / filter / smoothing / b-value).

Split out of hvsr_engine.py.
"""


DEFAULT_FMIN = 0.5

DEFAULT_FMAX = 20.0

DEFAULT_NFREQ = 512

DEFAULT_B_VALUE = 40.0

DEFAULT_TAPER = 0.05

DEFAULT_FILTER = "butterworth"

DEFAULT_FILTER_ORDER = 5

DEFAULT_FILTER_RIPPLE = 0.5

DEFAULT_SMOOTHING = "konno_ohmachi"

DEFAULT_SMOOTH_WIDTH = 40.0

MAX_PICK_FREQ = 10.0
