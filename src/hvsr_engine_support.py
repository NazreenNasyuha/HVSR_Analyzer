"""
hvsr_engine_support.py
======================
Small numerical helpers shared by the spectra and analysis modules:

- _fft_freqs / _magnitude / _magnitude_from_fft : FFT output helpers,
- _window_starts : analysis-window placement,
- _window_peak_index / _best_index : peak finding on a curve,
- _smooth_combine : combines windowed Z/N/E spectra into an H/V curve.

Split out of hvsr_engine.py.
"""


import math
from hvsr_dsp import (
    fft, rfft_magnitude, resolve_workers, cosine_taper,
    detrend_linear, demean, butter_bandpass, bandpass_filter,
    smooth_spectrum, mute_transients, decimate, parse_paz, paz_deconvolve,
)

def _fft_freqs(fs, n):
    """Frequency axis (Hz) for a one-sided magnitude spectrum."""
    half = n // 2
    return [k * (fs / n) for k in range(half + 1)]

def _magnitude(seg):
    """One-sided magnitude spectrum via fft (real-input fast path)."""
    return rfft_magnitude(seg)

def _magnitude_from_fft(spec, n):
    """One-sided magnitude spectrum from a full FFT output."""
    half = n // 2
    mag = []
    for k in range(half + 1):
        if k == 0 or (n % 2 == 0 and k == half):
            mag.append(abs(spec[k]))
        else:
            mag.append(2.0 * abs(spec[k]))
    return mag

def _window_starts(n_samples, w_len, fs, overlap):
    """Window start indices.  overlap is a fraction in [0, 1)."""
    w = int(round(w_len * fs))
    if w >= n_samples:
        return [0]
    step = max(1, int(round(w * (1.0 - overlap))))
    starts = list(range(0, n_samples - w + 1, step))
    if not starts:
        starts = [0]
    return starts

def _window_peak_index(freqs, curve, fmin, fmax):
    """Index of the highest local maximum of a window's H/V curve within
    [fmin, fmax] (Geopsy-style per-window f0).  Returns None if the curve
    has no local peak inside the band."""
    best, best_a = None, -1.0
    for k in range(1, len(curve) - 1):
        f = freqs[k]
        if fmin <= f <= fmax and curve[k] > curve[k - 1] and \
                curve[k] > curve[k + 1] and curve[k] > best_a:
            best, best_a = k, curve[k]
    return best

def _best_index(freqs, curve, fmin, fmax):
    """Index of the largest curve value whose frequency lies inside
    [fmin, fmax] (used for f0 / A0 picking)."""
    best = 0
    best_a = -1.0
    for k, f in enumerate(freqs):
        if fmin <= f <= fmax and curve[k] > best_a:
            best_a = curve[k]
            best = k
    return best

def _smooth_combine(sz, sn, se, fft_freqs, freqs, b_value, combo,
                    smoothing, smooth_width):
    """Smooth the three raw channel spectra and combine them into the
    window H/V curve at the target frequencies."""
    sz = smooth_spectrum(sz, fft_freqs, freqs, smoothing, smooth_width)
    sn = smooth_spectrum(sn, fft_freqs, freqs, smoothing, smooth_width)
    se = smooth_spectrum(se, fft_freqs, freqs, smoothing, smooth_width)
    out = []
    for i in range(len(freqs)):
        if sz[i] <= 1e-30:
            out.append(0.0)
            continue
        hn = sn[i] / sz[i]
        he = se[i] / sz[i]
        if combo == "geometric":
            out.append(math.sqrt(hn * he) if (hn > 0 and he > 0) else 0.0)
        elif combo == "arithmetic":
            out.append(0.5 * (hn + he))
        else:  # quadratic mean (mean square, SESAME convention)
            out.append(math.sqrt((sn[i] ** 2 + se[i] ** 2) / (2.0 * sz[i] ** 2)))
    return out
