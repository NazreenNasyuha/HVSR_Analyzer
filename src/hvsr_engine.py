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

# Optional (pure stdlib): global HVSR method standards (SESAME, Japan, ...)
try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False

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


# ----------------------------------------------------------------------
# Time-range selection
# ----------------------------------------------------------------------
def trim_seconds(data, t0=None, t1=None):
    """Return a ThreeChannel trimmed to the [t0, t1] second range.

    t0 / t1 are in seconds; None means the start / end of the recording.
    The whole program then analyses only the selected part of the signal.
    """
    fs = data.fs
    i0 = 0 if t0 is None else max(0, int(round(t0 * fs)))
    i1 = data.n_samples if t1 is None else min(data.n_samples,
                                               int(round(t1 * fs)))
    if i1 <= i0:
        raise DataError("time range %.2f-%.2f s is empty in this recording"
                        % (t0 or 0.0, t1 or (data.n_samples / fs)))
    return ThreeChannel(data.z[i0:i1], data.n[i0:i1], data.e[i0:i1], fs,
                        data.source_name)


# ----------------------------------------------------------------------
# Pre-processing
# ----------------------------------------------------------------------
def preprocess(data, fs=None, f_low=0.2, f_high=20.0, paz=None,
               sta_sec=1.0, lta_sec=30.0, slta_threshold=2.5,
               mute=True, max_fs=200.0, filter_type=DEFAULT_FILTER,
               filter_order=DEFAULT_FILTER_ORDER,
               filter_ripple=DEFAULT_FILTER_RIPPLE):
    """Clean the raw channels: response, detrend, filter, STA/LTA mute.

    filter_type selects the band-pass prototype: 'butterworth'
    (maximally flat, recommended), 'chebyshev_i' (sharper roll-off with
    passband ripple) or 'bessel' (no ringing, flat group delay).

    Returns a ThreeChannel with cleaned data plus metadata dict.
    """
    fs = fs or data.fs

    # Optional integer decimation to keep the maths fast and honest.
    # Decimation runs BEFORE the (expensive) full-trace response correction
    # so that long recordings are shrunk first.
    dec_factor = 1
    if max_fs and fs > max_fs:
        dec_factor = max(1, int(math.ceil(fs / max_fs)))
        if dec_factor > 1:
            fs = fs / dec_factor

    z = list(data.z)
    n = list(data.n)
    e = list(data.e)

    if dec_factor > 1:
        z = decimate(z, dec_factor)
        n = decimate(n, dec_factor)
        e = decimate(e, dec_factor)

    if paz is not None:
        z = paz_deconvolve(z, fs, paz)
        n = paz_deconvolve(n, fs, paz)
        e = paz_deconvolve(e, fs, paz)

    z = demean(detrend_linear(z))
    n = demean(detrend_linear(n))
    e = demean(detrend_linear(e))

    z = bandpass_filter(z, f_low, f_high, fs, kind=filter_type,
                        order=filter_order, ripple_db=filter_ripple)
    n = bandpass_filter(n, f_low, f_high, fs, kind=filter_type,
                        order=filter_order, ripple_db=filter_ripple)
    e = bandpass_filter(e, f_low, f_high, fs, kind=filter_type,
                        order=filter_order, ripple_db=filter_ripple)

    muted = 0
    if mute:
        z, n, e, idx = mute_transients(z, n, e, sta_sec, lta_sec, fs, slta_threshold)
        muted = len(idx)

    return ThreeChannel(z, n, e, fs), {"dec_factor": dec_factor, "muted": muted,
                                       "f_low": f_low, "f_high": f_high,
                                       "filter_type": filter_type,
                                       "filter_order": filter_order}


# ----------------------------------------------------------------------
# Windowed H/V spectra
# ----------------------------------------------------------------------
def log_frequencies(fmin, fmax, nfreq):
    """Log-spaced frequency grid."""
    if nfreq < 2:
        nfreq = 2
    step = math.log(fmax / fmin) / (nfreq - 1)
    return [fmin * math.exp(step * k) for k in range(nfreq)]


def compute_spectra(data, w_len, overlap=0.0, taper=DEFAULT_TAPER,
                    fmin=0.1, fmax=40.0):
    """Averaged Fourier amplitude spectra and Welch PSDs of Z / N / E.

    Both are computed from the *same* windows used for the H/V analysis
    (detrended and cosine-tapered), which makes the spectra directly
    comparable with the H/V curve.

    Returns a dict:
        freqs    : one-sided FFT frequency grid (Hz)
        spec     : {'z': [...], 'n': [...], 'e': [...]} mean amplitude
        psd      : {'z': [...], 'n': [...], 'e': [...]} Welch PSD (dB rel.)
        n_windows: number of averaged windows
    """
    starts = _window_starts(data.n_samples, w_len, data.fs, overlap)
    w = int(round(w_len * data.fs))
    if w < 8 or not starts:
        return {"freqs": [], "spec": {}, "psd": {}, "n_windows": 0}

    n_bins = w // 2 + 1
    acc_spec = {"z": [0.0] * n_bins, "n": [0.0] * n_bins, "e": [0.0] * n_bins}
    acc_psd = {"z": [0.0] * n_bins, "n": [0.0] * n_bins, "e": [0.0] * n_bins}
    n_win = 0
    for s in starts:
        if s + w > data.n_samples:
            break
        seg = {}
        for ch in ("z", "n", "e"):
            chan = getattr(data, ch)
            x = demean(detrend_linear(chan[s:s + w]))
            win = cosine_taper(w, taper)
            seg[ch] = [x[i] * win[i] for i in range(w)]
        for ch in ("z", "n", "e"):
            mag = _magnitude(seg[ch])
            for k in range(n_bins):
                a = mag[k]
                acc_spec[ch][k] += a
                acc_psd[ch][k] += a * a
        n_win += 1
    if n_win == 0:
        return {"freqs": [], "spec": {}, "psd": {}, "n_windows": 0}

    win = cosine_taper(w, taper)
    wsum = sum(v * v for v in win)
    psd_norm = 1.0 / (data.fs * wsum) if wsum > 0 else 1.0
    freqs = _fft_freqs(data.fs, w)
    spec = {}
    psd = {}
    for ch in ("z", "n", "e"):
        spec[ch] = [acc_spec[ch][k] / n_win for k in range(n_bins)]
        psd[ch] = [10.0 * math.log10(max(acc_psd[ch][k] * psd_norm / n_win,
                                         1e-30)) for k in range(n_bins)]
    # trim to the requested band
    kept = [(f, i) for i, f in enumerate(freqs) if fmin <= f <= fmax]
    if kept:
        i0, i1 = kept[0][1], kept[-1][1] + 1
        freqs = freqs[i0:i1]
        spec = {ch: spec[ch][i0:i1] for ch in ("z", "n", "e")}
        psd = {ch: psd[ch][i0:i1] for ch in ("z", "n", "e")}
    return {"freqs": freqs, "spec": spec, "psd": psd, "n_windows": n_win}


def coherence(x, y, fs, w_len, overlap=0.0, taper=DEFAULT_TAPER,
              fmin=0.1, fmax=40.0):
    """Magnitude-squared coherence between two channels.

    NOTE the argument order: it is (x, y, fs, w_len) - the sampling rate
    comes BEFORE the window length, unlike most engine helpers.  Calling
    it with the order swapped silently produces garbage, so pass both
    as keywords (coherence(x, y, fs=..., w_len=...)) when in doubt.

    Welch-style: the cross-spectral density and the two auto-spectral
    densities are averaged over the same detrended / cosine-tapered
    windows used for the H/V analysis, then

        gamma^2(f) = |Sxy(f)|^2 / (Sxx(f) * Syy(f))

    Returns (freqs, coh) with coh in [0, 1].
    """
    n = min(len(x), len(y))
    starts = _window_starts(n, w_len, fs, overlap)
    w = int(round(w_len * fs))
    if w < 8 or not starts:
        return [], []
    n_bins = w // 2 + 1
    acc_xx = [0.0] * n_bins
    acc_yy = [0.0] * n_bins
    acc_xy = [0.0 + 0.0j] * n_bins
    n_win = 0
    for s in starts:
        if s + w > n:
            break
        sx = demean(detrend_linear(x[s:s + w]))
        sy = demean(detrend_linear(y[s:s + w]))
        win = cosine_taper(w, taper)
        fx = fft([sx[i] * win[i] for i in range(w)])
        fy = fft([sy[i] * win[i] for i in range(w)])
        for k in range(n_bins):
            acc_xx[k] += abs(fx[k]) ** 2
            acc_yy[k] += abs(fy[k]) ** 2
            acc_xy[k] += fx[k] * fy[k].conjugate()
        n_win += 1
    if n_win == 0:
        return [], []
    freqs = _fft_freqs(fs, w)
    peak_xx = max(acc_xx) or 1.0
    peak_yy = max(acc_yy) or 1.0
    coh = []
    for k in range(n_bins):
        # guard against the 0/0 pathology: where either channel has
        # negligible power (noise floor), coherence is meaningless -> 0
        if acc_xx[k] < peak_xx * 1e-9 or acc_yy[k] < peak_yy * 1e-9:
            coh.append(0.0)
            continue
        denom = acc_xx[k] * acc_yy[k]
        c = (abs(acc_xy[k]) ** 2) / denom if denom > 1e-30 else 0.0
        coh.append(min(1.0, c))
    kept = [(f, i) for i, f in enumerate(freqs) if fmin <= f <= fmax]
    if kept:
        i0, i1 = kept[0][1], kept[-1][1] + 1
        freqs = freqs[i0:i1]
        coh = coh[i0:i1]
    return freqs, coh


def hv_vs_time(data, w_len, overlap=0.0, taper=DEFAULT_TAPER, freqs=None,
               b_value=DEFAULT_B_VALUE, combo="geometric",
               smoothing=DEFAULT_SMOOTHING,
               smooth_width=DEFAULT_SMOOTH_WIDTH, max_windows=16):
    """H/V ratio as a time-frequency colour map.

    Returns (times, freqs, grid) where grid[r][c] is the H/V ratio of
    window r (start time times[r]) at frequency freqs[c].  Only a capped
    number of windows is used so the pure-Python computation stays fast
    enough for an interactive preview.
    """
    starts = _window_starts(data.n_samples, w_len, data.fs, overlap)
    if len(starts) > max_windows:
        idx = [int(round(i * (len(starts) - 1) / (max_windows - 1)))
               for i in range(max_windows)]
        starts = [starts[i] for i in idx]
    if freqs is None:
        freqs = log_frequencies(DEFAULT_FMIN, DEFAULT_FMAX, 96)
    times = []
    grid = []
    for s in starts:
        c = _window_hv_curve(data.z[s:], data.n[s:], data.e[s:], data.fs,
                             w_len, taper, freqs, b_value, combo,
                             smoothing, smooth_width)
        if c is not None:
            grid.append(c)
            times.append(s / data.fs)
    return times, freqs, grid


def hv_vs_azimuth(data, w_len, overlap=0.0, taper=DEFAULT_TAPER, freqs=None,
                  b_value=DEFAULT_B_VALUE, combo="geometric",
                  smoothing=DEFAULT_SMOOTHING,
                  smooth_width=DEFAULT_SMOOTH_WIDTH,
                  azimuth_step=15.0, max_windows=12):
    """H/V directionality: ratio as a function of azimuth and frequency.

    For each azimuth the horizontal pair (N, E) is rotated into the
    radial / transverse directions and the H/V curve of the radial
    component is computed; the result is a 2-D map
    (azimuth, frequency).  Returns (azimuths, freqs, grid).
    """
    starts = _window_starts(data.n_samples, w_len, data.fs, overlap)
    if len(starts) > max_windows:
        idx = [int(round(i * (len(starts) - 1) / (max_windows - 1)))
               for i in range(max_windows)]
        starts = [starts[i] for i in idx]
    if freqs is None:
        freqs = log_frequencies(DEFAULT_FMIN, DEFAULT_FMAX, 72)
    w = int(round(w_len * data.fs))
    if w < 8:
        return [], freqs, []
    fft_freqs = _fft_freqs(data.fs, w)
    # FFT is linear: the radial spectrum of a rotated horizontal is the
    # same rotation of the N and E spectra.  Compute each window's three
    # FFTs once, then every azimuth just combines them (12x fewer FFTs).
    win = cosine_taper(w, taper)
    window_ffts = []   # (smooth_z, fn, fe)
    for s in starts:
        if s + w > data.n_samples:
            break
        segz = demean(detrend_linear(data.z[s:s + w]))
        segn = demean(detrend_linear(data.n[s:s + w]))
        sege = demean(detrend_linear(data.e[s:s + w]))
        fz = fft([segz[i] * win[i] for i in range(w)])
        fn = fft([segn[i] * win[i] for i in range(w)])
        fe = fft([sege[i] * win[i] for i in range(w)])
        sz = smooth_spectrum(_magnitude_from_fft(fz, w), fft_freqs,
                             freqs, smoothing, smooth_width)
        window_ffts.append((sz, fn, fe))
    if not window_ffts:
        return [], freqs, []
    half = w // 2
    azimuths = []
    grid = []
    ang = 0.0
    while ang < 180.0:
        azimuths.append(ang)
        rad = math.radians(ang)
        cr, sr = math.cos(rad), math.sin(rad)
        acc = [0.0] * len(freqs)
        for sz, fn, fe in window_ffts:
            srad = []
            for k in range(half + 1):
                rad_c = fn[k] * cr + fe[k] * sr
                srad.append(2.0 * abs(rad_c) if 0 < k < half
                            else abs(rad_c))
            srad = smooth_spectrum(srad, fft_freqs, freqs, smoothing,
                                   smooth_width)
            for i in range(len(freqs)):
                acc[i] += srad[i] / sz[i] if sz[i] > 1e-30 else 0.0
        grid.append([v / len(window_ffts) for v in acc])
        ang += azimuth_step
    return azimuths, freqs, grid


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


def peak_quality(res, strict_a0=2.0):
    """Classify the H/V peak as CLEAR or UNCLEAR/FLAT.

    A clear peak needs a genuine resonance: the curve must drop below
    A0/2 both below and above f0 (SESAME clarity criteria) and the peak
    must be strong enough.  Flat curves get 'FLAT/UNCLEAR' - f0 picks on
    them are not meaningful and are excluded from cross-engine agreement
    statistics.
    """
    c = res.sesame
    if not c:
        return "FLAT/UNCLEAR"
    if c.get("drop_below_f0") and c.get("drop_above_f0") and res.a0 >= strict_a0:
        return "CLEAR"
    if c.get("drop_below_f0") or c.get("drop_above_f0"):
        return "PARTIAL"
    return "FLAT/UNCLEAR"


def _window_raw_spectra(z, n, e, fs, w_len, taper):
    """Detrend / taper one window and return its raw one-sided magnitude
    spectra (before spectral smoothing) for the Z, N, E channels together
    with the FFT frequency axis."""
    w = int(round(w_len * fs))
    if w < 8 or w > len(z):
        return None

    def mag(chan):
        seg = demean(detrend_linear(chan[:w]))
        win = cosine_taper(w, taper)
        seg = [seg[i] * win[i] for i in range(w)]
        return _magnitude(seg)

    return [mag(z), mag(n), mag(e)], _fft_freqs(fs, w)


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


def _window_hv_curve(z, n, e, fs, w_len, taper, freqs, b_value, combo,
                     smoothing=DEFAULT_SMOOTHING,
                     smooth_width=DEFAULT_SMOOTH_WIDTH):
    """Single-window H/V curve at the given frequencies.

    combo selects how the two horizontal components are combined:
      'geometric'  sqrt(HN*HE)          (recommended, SESAME default)
      'arithmetic' (HN+HE)/2
      'quadratic'  sqrt((HN^2+HE^2)/2)  (mean square)
    """
    raw = _window_raw_spectra(z, n, e, fs, w_len, taper)
    if raw is None:
        return None
    (sz, sn, se), fft_f = raw
    return _smooth_combine(sz, sn, se, fft_f, freqs, b_value, combo,
                           smoothing, smooth_width)


def _magnitude(seg):
    """One-sided magnitude spectrum via fft (real-input fast path)."""
    return rfft_magnitude(seg)


def _fft_freqs(fs, n):
    """Frequency axis (Hz) for a one-sided magnitude spectrum."""
    half = n // 2
    return [k * (fs / n) for k in range(half + 1)]


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


# ----------------------------------------------------------------------
# Window rejection and mean curves
# ----------------------------------------------------------------------
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


def reject_windows(curves, freqs, n_sigma=1.5, max_iterations=50,
                   fmin=0.5, fmax=10.0):
    """Geopsy / hvsrpy (Cox et al. 2020, GJI) frequency-domain window
    rejection.

    A window's f0 is the frequency of its highest local H/V peak within
    [fmin, fmax].  Iteratively, the log-normal mean and standard
    deviation of the f0 values of the currently-valid windows are
    computed and windows whose f0 falls outside mean * exp(+/- n_sigma
    * sigma) are rejected; the population is recomputed and the process
    repeats until stable.  Windows with no local peak inside the search
    band are kept for the mean curve but excluded from the f0
    statistics (Geopsy reports 89 curve windows but 88 windows for f0
    on the reference station).

    This is the criterion of the Geopsy 'hv' tool
    (FREQUENCY_WINDOW_REJECTION_STDDEV_FACTOR) and of hvsrpy's
    reject_windows.  The previous any-point curve-band rule did not
    match Geopsy: on real stations it rejected nearly every window
    (median 2% accepted) while Geopsy accepted ~99%.
    """
    nwin = len(curves)
    if nwin == 0:
        return [], 0
    valid = [True] * nwin
    if nwin == 1:
        return valid, 1
    if freqs:
        fmax = min(fmax, freqs[-1])
    f0s = []
    for c in curves:
        k = _window_peak_index(freqs, c, fmin, fmax)
        f0s.append(freqs[k] if k is not None else None)
    has = [f is not None for f in f0s]
    for _ in range(max_iterations):
        idx = [i for i in range(nwin) if valid[i] and has[i]]
        if len(idx) <= 1:
            break
        logs = [math.log(f0s[i]) for i in idx]
        m = statistics.fmean(logs)
        s = statistics.pstdev(logs)
        if s <= 1e-12:
            break
        lo = math.exp(m - n_sigma * s)
        hi = math.exp(m + n_sigma * s)
        changed = False
        for i in idx:
            keep = lo < f0s[i] < hi
            if keep != valid[i]:
                changed = True
            valid[i] = keep
        if not changed:
            break
    if sum(valid) == 0 and nwin > 0:
        valid[0] = True
    return valid, sum(valid)


def mean_and_std_curves(curves, valid):
    """Lognormal mean curve and multiplicative +-1 sigma curves."""
    idx = [i for i, v in enumerate(valid) if v]
    if not idx:
        return [], [], []
    nf = len(curves[idx[0]])
    logs = [[math.log(max(c, 1e-300)) for c in curves[i]] for i in idx]
    mean = [statistics.fmean(col) for col in ([row[k] for row in logs] for k in range(nf))]
    std = [statistics.pstdev(col) for col in ([row[k] for row in logs] for k in range(nf))]
    mean_c = [math.exp(m) for m in mean]
    low = [math.exp(m - s) for m, s in zip(mean, std)]
    high = [math.exp(m + s) for m, s in zip(mean, std)]
    return mean_c, low, high


# ----------------------------------------------------------------------
# Peak picking
# ----------------------------------------------------------------------
def pick_peak(freqs, amps, fmin=0.5, fmax=10.0):
    """f0 / A0 picking with parabolic interpolation of the mean curve peak."""
    if not freqs or not amps:
        return 0.0, 0.0
    best_k = None
    best_a = -1.0
    for k, f in enumerate(freqs):
        if fmin <= f <= fmax and amps[k] > best_a:
            best_a = amps[k]
            best_k = k
    if best_k is None:
        best_k = 0
        best_a = amps[0]
    # parabolic refinement
    k = best_k
    f0 = freqs[k]
    a0 = amps[k]
    if 0 < k < len(freqs) - 1:
        y0, y1, y2 = amps[k - 1], amps[k], amps[k + 1]
        denom = (y0 - 2.0 * y1 + y2)
        if abs(denom) > 1e-30 and (y0 - 2.0 * y1 + y2) != 0:
            offset = 0.5 * (y0 - y2) / denom
            if -1.0 < offset < 1.0:
                # interpolate in log-f
                lf0, lf1, lf2 = math.log(freqs[k - 1]), math.log(freqs[k]), math.log(freqs[k + 1])
                lf = lf1 + offset * (lf2 - lf1) / 2.0
                f0 = math.exp(lf)
                a0 = y1 - 0.25 * (y0 - y2) * offset
    return f0, a0


# ----------------------------------------------------------------------
# SESAME 2004 criteria
# ----------------------------------------------------------------------
def sesame_evaluate(freqs, amps, high, f0, a0, num_windows, win_len, sigma_f):
    """Return a dict of the SESAME 2004 reliability criteria."""
    limit_f0 = 10.0 / win_len
    nc = num_windows * win_len * f0
    curve = [(f, a, h) for f, a, h in zip(freqs, amps, high)
             if 0.5 * f0 <= f <= 2.0 * f0]
    if curve:
        allowed = 2.0 if f0 > 0.5 else 3.0
        sigma_ok = all((h / a) < allowed for f, a, h in curve if a > 0)
    else:
        sigma_ok = False
    minus = any(a < (a0 / 2.0) for f, a in zip(freqs, amps) if f0 / 4.0 <= f <= f0)
    plus = any(a < (a0 / 2.0) for f, a in zip(freqs, amps) if f0 <= f <= 4.0 * f0)
    limit_sigma_f = (0.05 * f0) if f0 > 0.5 else (0.1 * f0)

    return {
        "f0_gt_10_over_lw": f0 > limit_f0,
        "nc_gt_200": nc > 200,
        "sigma_A_ok": sigma_ok,
        "drop_below_f0": minus,
        "drop_above_f0": plus,
        "a0_gt_2": a0 > 2.0,
        "sigma_f_ok": sigma_f is not None and sigma_f < limit_sigma_f,
        "nc": nc,
        "limit_f0": limit_f0,
        "sigma_f": sigma_f,
        "limit_sigma_f": limit_sigma_f,
    }


def sesame_score(crit):
    """Count of satisfied criteria (6 curve+peak criteria used for tuning)."""
    score = 0
    for key in ("f0_gt_10_over_lw", "nc_gt_200", "sigma_A_ok",
                "drop_below_f0", "drop_above_f0", "a0_gt_2"):
        if crit.get(key):
            score += 1
    return score


# ----------------------------------------------------------------------
# Vulnerability index
# ----------------------------------------------------------------------
def vulnerability_kg(a0, f0):
    """Seismic vulnerability index Kg = A0^2 / f0 with a classification."""
    kg = (a0 * a0) / f0 if f0 > 0 else 0.0
    if kg > 20.0:
        level = "HIGH VULNERABILITY"
    elif kg >= 5.0:
        level = "MODERATE VULNERABILITY"
    else:
        level = "LOW VULNERABILITY"
    return kg, level


# ----------------------------------------------------------------------
# Top-level analysis
# ----------------------------------------------------------------------
class HvsrResult:
    """Everything produced by one analysis run."""

    def __init__(self):
        self.station = ""
        self.freqs = []
        self.mean = []
        self.low = []
        self.high = []
        self.f0 = 0.0
        self.a0 = 0.0
        self.sigma_f = 0.0
        self.n_windows_total = 0
        self.n_windows_accepted = 0
        self.window_len = 0.0
        self.overlap = 0.0
        self.kg = 0.0
        self.kg_level = ""
        self.sesame = {}
        self.peak_quality = "FLAT/UNCLEAR"
        self.standards = {}       # {standard_id: evaluation dict}
        self.standard_report = ""  # plain-text block for all standards
        self.log = []
        self.report_text = ""


def _finalize_analysis(curves, freqs, w_len, overlap, rejection,
                       max_iterations, fmin, fmax, station, combo,
                       smoothing, smooth_width):
    """Turn a list of per-window H/V curves into a fully populated result
    (window rejection, mean curve, f0/A0, SESAME scoring, report text).

    Shared by :func:`analyze` and the auto-tuning sweeps so every
    parameter combination is scored identically.
    """
    res = HvsrResult()
    res.station = station
    res.window_len = w_len
    res.overlap = overlap
    res.n_windows_total = len(curves)

    valid = [True] * len(curves)
    n_accept = len(curves)
    if curves:
        valid, n_accept = reject_windows(curves, freqs, rejection,
                                         max_iterations, fmin,
                                         min(fmax, MAX_PICK_FREQ))
        mean, low, high = mean_and_std_curves(curves, valid)
        res.freqs = freqs
        res.mean = mean
        res.low = low
        res.high = high
        res.n_windows_accepted = n_accept

        # f0 and sigma_f
        f0, a0 = pick_peak(freqs, mean)
        res.f0, res.a0 = f0, a0
        valid_idx = [i for i, v in enumerate(valid) if v]
        w_f0s = []
        for i in valid_idx:
            k = _window_peak_index(freqs, curves[i], 0.5, MAX_PICK_FREQ)
            if k is not None:
                w_f0s.append(freqs[k])
        res.sigma_f = statistics.pstdev(w_f0s) if len(w_f0s) > 1 else 0.0

        res.smoothing = smoothing
        res.smooth_width = smooth_width
        res.combo = combo
        res.kg, res.kg_level = vulnerability_kg(a0, f0)
        res.sesame = sesame_evaluate(freqs, mean, high, f0, a0,
                                     n_accept, w_len, res.sigma_f)
        res.peak_quality = peak_quality(res)
        if _HAVE_STANDARDS:
            res.standards = hvsr_standards.evaluate_all(res)
            res.standard_report = hvsr_standards.build_standards_report(res)
        res.log = _build_log(res)
        if res.standard_report:
            res.log.append(res.standard_report)
        res.report_text = "\n".join(res.log)
    else:
        res.log = ["ERROR: no usable windows - check the input data and parameters."]
        res.report_text = res.log[0]
    if not res.freqs or len(res.mean) != len(res.freqs):
        res.log = ["ERROR: analysis produced no curves - check the input data and parameters."]
        res.report_text = res.log[0]
    return res


def analyze(data, w_len=30.0, overlap=0.0, rejection=1.5,
            fmin=DEFAULT_FMIN, fmax=DEFAULT_FMAX, nfreq=DEFAULT_NFREQ,
            b_value=DEFAULT_B_VALUE, taper=DEFAULT_TAPER, combo="geometric",
            max_iterations=50, station="station",
            smoothing=DEFAULT_SMOOTHING,
            smooth_width=DEFAULT_SMOOTH_WIDTH):
    """Run the full HVSR analysis on a preprocessed ThreeChannel.

    smoothing / smooth_width select the spectral smoothing operator
    (konno_ohmachi / moving_average / triangular_constant /
    triangular_proportional) and its width parameter (see hvsr_dsp).
    """
    freqs = log_frequencies(fmin, fmax, nfreq)
    starts = _window_starts(data.n_samples, w_len, data.fs, overlap)
    curves = []
    for s in starts:
        c = _window_hv_curve(data.z[s:], data.n[s:], data.e[s:],
                             data.fs, w_len, taper, freqs, b_value, combo,
                             smoothing, smooth_width)
        if c is not None:
            curves.append(c)
    return _finalize_analysis(curves, freqs, w_len, overlap, rejection,
                              max_iterations, fmin, fmax, station, combo,
                              smoothing, smooth_width)


def _best_index(freqs, curve, fmin, fmax):
    best = 0
    best_a = -1.0
    for k, f in enumerate(freqs):
        if fmin <= f <= fmax and curve[k] > best_a:
            best_a = curve[k]
            best = k
    return best


def _build_log(res):
    log = []
    log.append("=" * 60)
    log.append("            HVSR ANALYZER - RESULTS REPORT")
    log.append("=" * 60)
    log.append("Station                  : %s" % res.station)
    log.append("Window length            : %.1f s" % res.window_len)
    log.append("Window overlap           : %.0f %%" % (res.overlap * 100))
    log.append("Total windows            : %d" % res.n_windows_total)
    log.append("Accepted windows         : %d" % res.n_windows_accepted)
    log.append("Rejected windows         : %d" % (res.n_windows_total - res.n_windows_accepted))
    log.append("Fundamental frequency f0 : %.3f Hz" % res.f0)
    log.append("Peak amplification A0    : %.2f" % res.a0)
    log.append("Std. dev. of f0 (sigma_f): %.3f Hz" % res.sigma_f)
    log.append("Vulnerability index Kg   : %.2f -> %s" % (res.kg, res.kg_level))
    log.append("Smoothing                : %s (width=%s)"
               % (getattr(res, "smoothing", "konno_ohmachi"),
                  getattr(res, "smooth_width", 40.0)))
    log.append("H/V combination          : %s"
               % getattr(res, "combo", "geometric"))
    log.append("")
    log.append("-" * 60)
    log.append("        SESAME 2004 RELIABILITY MATRIX")
    log.append("-" * 60)
    c = res.sesame
    log.append(" [Reliability of the H/V curve]")
    log.append("  f0 > 10/lw        : %s (f0=%.3f Hz, limit=%.3f Hz)"
               % (_ok(c.get("f0_gt_10_over_lw")), res.f0, c.get("limit_f0", 0)))
    log.append("  nc(f0) > 200      : %s (nc=%.1f)"
               % (_ok(c.get("nc_gt_200")), c.get("nc", 0)))
    log.append("  sigma_A < limit   : %s" % _ok(c.get("sigma_A_ok")))
    log.append(" [Clarity of the H/V peak]")
    log.append("  drop below f0/2   : %s (f in [f0/4, f0])" % _ok(c.get("drop_below_f0")))
    log.append("  drop above f0/2   : %s (f in [f0, 4*f0])" % _ok(c.get("drop_above_f0")))
    log.append("  A0 > 2            : %s (A0=%.2f)" % (_ok(c.get("a0_gt_2")), res.a0))
    log.append("  sigma_f < limit   : %s (sigma_f=%.3f, limit=%.3f)"
               % (_ok(c.get("sigma_f_ok")), c.get("sigma_f", 0), c.get("limit_sigma_f", 0)))
    log.append("=" * 60)
    return log


def _ok(flag):
    return "[Ok]" if flag else "[No]"


# ----------------------------------------------------------------------
# Exports
# ----------------------------------------------------------------------
def write_target_file(path, freqs, amps, low, high, f0, fmin_frac=0.5, fmax_mult=2.0):
    """Write an inversion target file: freq, amp, stddev (one line per row)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# HVSR inversion target - f0 = %.4f Hz\n" % f0)
        for f, a, lo, hi in zip(freqs, amps, low, high):
            if fmin_frac * f0 <= f <= fmax_mult * f0:
                stddev = max((hi - lo) / 2.0, 0.001)
                fh.write("%.4f\t%.4f\t%.4f\n" % (f, a, stddev))


def write_report_file(path, result):
    """Save the full text report."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(result.report_text + "\n")


# ----------------------------------------------------------------------
# Parameter auto-tuning (SESAME-score driven, as in the original tool)
# ----------------------------------------------------------------------
_SMOOTH_DEFAULTS = {
    "konno_ohmachi": 40.0,
    "moving_average": 0.1,
    "triangular_constant": 0.5,
    "triangular_proportional": 0.1,
}


_STAGE2_CTX = {}


def _stage2_init(raws, freqs, w_len, rejection, max_iterations, fmin, fmax,
                 station, overlap, b_value):
    """Process-pool initializer: share the cached window spectra once."""
    _STAGE2_CTX["raws"] = raws
    _STAGE2_CTX["freqs"] = freqs
    _STAGE2_CTX["w_len"] = w_len
    _STAGE2_CTX["rejection"] = rejection
    _STAGE2_CTX["max_iterations"] = max_iterations
    _STAGE2_CTX["fmin"] = fmin
    _STAGE2_CTX["fmax"] = fmax
    _STAGE2_CTX["station"] = station
    _STAGE2_CTX["overlap"] = overlap
    _STAGE2_CTX["b_value"] = b_value


def _stage2_job(job):
    """Evaluate one stage-2 (smoothing, width, combo) combination.

    The raw window spectra for the winning window length come from the
    pool initializer, so only the cheap smoothing + combination + scoring
    runs per job.
    """
    smoothing, smooth_width, combo = job
    ctx = _STAGE2_CTX
    curves = []
    for (sz, sn, se), fft_f in ctx["raws"]:
        curves.append(_smooth_combine(sz, sn, se, fft_f, ctx["freqs"],
                                      ctx["b_value"], combo, smoothing,
                                      smooth_width))
    res = _finalize_analysis(curves, ctx["freqs"], ctx["w_len"],
                             ctx["overlap"], ctx["rejection"],
                             ctx["max_iterations"], ctx["fmin"], ctx["fmax"],
                             ctx["station"], combo, smoothing, smooth_width)
    return job, sesame_score(res.sesame), res


def auto_tune(data, window_lengths=(25.0, 30.0, 40.0, 60.0),
              rejections=(1.5, 2.0), full=False,
              smoothings=None, smooth_widths=None, combos=None,
              n_workers=None, progress_cb=None, **kwargs):
    """SESAME-score-driven parameter search for maximum reliability.

    Quick mode (default): sweeps (window length x rejection factor) and
    keeps the best SESAME score (6 curve + peak criteria).

    full=True (the "max reliability" mode): a second stage fixes the
    winning window/rejection and additionally sweeps the smoothing
    operator (Konno-Ohmachi / moving average / triangular constant /
    triangular proportional), its width and the H/V combination, so the
    reported curve is the most reliable one obtainable.

    The window spectra are computed once per window length and reused for
    every (window, rejection, smoothing, width, combo) combination, so the
    full sweep costs about one windowing + FFT pass per window length.
    With n_workers > 1 the stage-2 combinations are evaluated in parallel
    worker processes (falls back to sequential if the platform refuses).

    Returns (result, chosen_window, chosen_rejection); the result carries
    .sesame_score and .tuned (dict of the winning parameters).
    """
    kwargs = dict(kwargs)
    fmin = kwargs.pop("fmin", DEFAULT_FMIN)
    fmax = kwargs.pop("fmax", DEFAULT_FMAX)
    nfreq = kwargs.pop("nfreq", DEFAULT_NFREQ)
    b_value = kwargs.pop("b_value", DEFAULT_B_VALUE)
    overlap = kwargs.pop("overlap", 0.0)
    taper = kwargs.pop("taper", DEFAULT_TAPER)
    max_iterations = kwargs.pop("max_iterations", 50)
    station = kwargs.pop("station", "station")
    base_smoothing = kwargs.pop("smoothing", DEFAULT_SMOOTHING)
    base_width = kwargs.pop("smooth_width", None)
    base_combo = kwargs.pop("combo", "geometric")
    if base_width is None:
        base_width = _SMOOTH_DEFAULTS.get(base_smoothing, 40.0)
    freqs = log_frequencies(fmin, fmax, nfreq)

    # Per-window raw spectra are cached per window length: windowing and
    # the FFTs do not depend on smoothing / width / combo / rejection.
    raw_cache = {}

    def curves_for(w, smoothing, smooth_width, combo):
        raws = raw_cache.get(w)
        if raws is None:
            starts = _window_starts(data.n_samples, w, data.fs, overlap)
            raws = []
            for s in starts:
                raw = _window_raw_spectra(data.z[s:], data.n[s:],
                                          data.e[s:], data.fs, w, taper)
                if raw is not None:
                    raws.append(raw)
            raw_cache[w] = raws
        curves = []
        for (sz, sn, se), fft_f in raws:
            curves.append(_smooth_combine(sz, sn, se, fft_f, freqs,
                                          b_value, combo, smoothing,
                                          smooth_width))
        return curves

    def scored(w, r, smoothing, smooth_width, combo):
        return _finalize_analysis(curves_for(w, smoothing, smooth_width,
                                             combo), freqs, w, overlap, r,
                                  max_iterations, fmin, fmax, station,
                                  combo, smoothing, smooth_width)

    n_workers = resolve_workers(n_workers)
    best_res = None
    best_score = -1
    best_w = window_lengths[0]
    best_r = rejections[0]
    total_steps = len(window_lengths) * len(rejections)
    step_no = 0

    for w in window_lengths:
        for r in rejections:
            res = scored(w, r, base_smoothing, base_width, base_combo)
            step_no += 1
            if progress_cb:
                try:
                    progress_cb(step_no, total_steps)
                except Exception:
                    pass
            if res.n_windows_accepted == 0:
                continue
            score = sesame_score(res.sesame)
            if score > best_score:
                best_score = score
                best_res = res
                best_w = w
                best_r = r
            if best_score >= 6 and not full:
                break
        if best_score >= 6 and not full:
            break

    if full and best_res is not None:
        sms = smoothings or list(_SMOOTH_DEFAULTS.keys())
        cbs = combos or ("geometric", "quadratic")
        jobs = []
        for sm in sms:
            defw = _SMOOTH_DEFAULTS.get(sm, 40.0)
            widths = smooth_widths or (defw * 0.5, defw, defw * 2.0)
            for sw_ in widths:
                for cb in cbs:
                    jobs.append((sm, sw_, cb))
        stage2_results = []
        used_parallel = False
        if n_workers and n_workers > 1 and jobs and best_w in raw_cache:
            try:
                from concurrent.futures import ProcessPoolExecutor
                with ProcessPoolExecutor(
                        max_workers=n_workers,
                        initializer=_stage2_init,
                        initargs=(raw_cache[best_w], freqs, best_w, best_r,
                                  max_iterations, fmin, fmax, station,
                                  overlap, b_value)) as ex:
                    stage2_results = list(ex.map(_stage2_job, jobs,
                                                 chunksize=1))
                used_parallel = True
            except Exception:
                stage2_results = []
                used_parallel = False
        if not used_parallel:
            for job in jobs:
                smoothing, sw_, cb = job
                res = scored(best_w, best_r, smoothing, sw_, cb)
                if res.n_windows_accepted == 0:
                    continue
                stage2_results.append((job, sesame_score(res.sesame), res))
        total_steps += len(jobs)
        for k, (_job, score, res) in enumerate(stage2_results):
            if progress_cb:
                try:
                    progress_cb(len(window_lengths) * len(rejections) + k + 1,
                                total_steps)
                except Exception:
                    pass
            if res.n_windows_accepted == 0:
                continue
            if score > best_score:
                best_score = score
                best_res = res

    if best_res is None:
        best_res = scored(best_w, best_r, base_smoothing, base_width,
                          base_combo)
    best_res.sesame_score = best_score
    best_res.tuned = {
        "window_length": best_w, "rejection": best_r,
        "smoothing": getattr(best_res, "smoothing", base_smoothing),
        "smooth_width": getattr(best_res, "smooth_width", base_width),
        "combo": getattr(best_res, "combo", base_combo),
    }
    return best_res, best_w, best_r
