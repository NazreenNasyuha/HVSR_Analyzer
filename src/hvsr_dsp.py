"""
hvsr_dsp.py
===========
Pure-standard-library digital signal processing primitives used by the
HVSR Analyzer.  No numpy / scipy / obspy -- everything below is written
from scratch on top of the Python standard library only.

Contents
--------
- fft / ifft          : Cooley-Tukey (radix-2) plus Bluestein for any length
- detrend_linear      : remove best-fit straight line
- demean              : remove the mean
- cosine_taper        : Tukey-style fractional taper
- butter_bandpass     : Butterworth bandpass designed via bilinear transform
- filtfilt            : zero-phase forward-backward IIR filtering
- classic_sta_lta     : STA/LTA transient detector
- decimate            : integer-factor decimation with anti-alias filter
- konno_ohmachi_smooth: Konno-Ohmachi spectral smoothing
- evaluate_pz         : SAC pole-zero (paz) response evaluation
"""
import math
import cmath
import os
from bisect import bisect_left
from functools import lru_cache


# Re-exported from hvsr_dsp_fft (split out of hvsr_dsp) - the
# public API stays importable from here.
from hvsr_dsp_fft import TWO_PI, _BLUESTEIN_TABLES, _bluestein_tables, _fft_bluestein, _fft_radix2, _next_pow2, fft, fft_real, ifft, parse_paz, paz_deconvolve, paz_response, rfft_magnitude
# Re-exported from hvsr_dsp_filters (split out of hvsr_dsp) - the
# public API stays importable from here.
from hvsr_dsp_filters import _bessel_analog_den, _bilinear, _butter_analog_den, _chebyshev_analog_den, _design_bandpass, _freqz_point, _lp2bp, _poly_add, _poly_mul, bandpass_filter, butter_bandpass
# Re-exported from hvsr_dsp_lfilter (split out of hvsr_dsp) - the
# public API stays importable from here.
from hvsr_dsp_lfilter import _filtfilt, _lfilter, _lfilter_ic, _lfilter_zi
# Re-exported from hvsr_dsp_stats (split out of hvsr_dsp) - the
# public API stays importable from here.
from hvsr_dsp_stats import _ko_band, _smooth_bands, classic_sta_lta, cosine_taper, decimate, demean, detrend_linear, konno_ohmachi_smooth, konno_ohmachi_weight, mute_transients, resolve_workers, smooth_spectrum
