"""
hvsr_engine.py
==============
From-scratch Horizontal-to-Vertical Spectral Ratio (HVSR) analysis engine.

Builds on hvsr_dsp (pure-stdlib DSP) and hvsr_io (text/CSV loading).  No
numpy / scipy / obspy / hvsrpy.

Pipeline
--------
1. optional pole-zero instrument correction
2. detrend + band-pass filtering (0.2 - 20 Hz) + STA/LTA transient muting
3. optional decimation if the sampling rate is much higher than needed
4. sliding-window H/V spectra with Konno-Ohmachi smoothing at log-spaced
   frequencies (geometric mean of the two directional ratios)
5. iterative window rejection (mean +/- n * sigma, log domain)
6. mean curve (lognormal) with +/- 1 sigma band
7. f0 / A0 picking (parabolic interpolation) and seismic vulnerability Kg
8. SESAME 2004 reliability criteria evaluation
9. text report + inversion target file export
"""
import os
import math
import statistics
from hvsr_dsp import (
    fft, rfft_magnitude, resolve_workers, cosine_taper,
    detrend_linear, demean, butter_bandpass, bandpass_filter,
    smooth_spectrum, mute_transients, decimate, parse_paz, paz_deconvolve,
)
from hvsr_io import ThreeChannel, auto_load, DataError
try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False
# (the flag's real consumer is _finalize_analysis in hvsr_engine_core.py,
#  which carries its own copy of this guarded import; this block is kept
#  for compatibility with any code reading hvsr_engine._HAVE_STANDARDS)


# Re-exported from hvsr_engine_autotune (split out of hvsr_engine) - the
# public API stays importable from here.
from hvsr_engine_autotune import _SMOOTH_DEFAULTS, _STAGE2_CTX, _stage2_init, _stage2_job, auto_tune, sesame_score
# Re-exported from hvsr_engine_core (split out of hvsr_engine) - the
# public API stays importable from here.
from hvsr_engine_core import HvsrResult, _finalize_analysis, analyze, mean_and_std_curves, peak_quality, pick_peak, reject_windows, sesame_evaluate, vulnerability_kg
# Re-exported from hvsr_engine_defaults (split out of hvsr_engine) - the
# public API stays importable from here.
from hvsr_engine_defaults import DEFAULT_B_VALUE, DEFAULT_FILTER, DEFAULT_FILTER_ORDER, DEFAULT_FILTER_RIPPLE, DEFAULT_FMAX, DEFAULT_FMIN, DEFAULT_NFREQ, DEFAULT_SMOOTHING, DEFAULT_SMOOTH_WIDTH, DEFAULT_TAPER, MAX_PICK_FREQ
# Re-exported from hvsr_engine_preprocess (split out of hvsr_engine) - the
# public API stays importable from here.
from hvsr_engine_preprocess import preprocess, trim_seconds
# Re-exported from hvsr_engine_report (split out of hvsr_engine) - the
# public API stays importable from here.
from hvsr_engine_report import _build_log, _ok, write_report_file, write_target_file
# Re-exported from hvsr_engine_spectra (split out of hvsr_engine) - the
# public API stays importable from here.
from hvsr_engine_spectra import _window_hv_curve, _window_raw_spectra, coherence, compute_spectra, hv_vs_azimuth, hv_vs_time, log_frequencies
# Re-exported from hvsr_engine_support (split out of hvsr_engine) - the
# public API stays importable from here.
from hvsr_engine_support import _best_index, _fft_freqs, _magnitude, _magnitude_from_fft, _smooth_combine, _window_peak_index, _window_starts
