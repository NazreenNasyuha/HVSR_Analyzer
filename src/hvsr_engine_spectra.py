"""
hvsr_engine_spectra.py
======================
Windowed spectral processing:

- compute_spectra / coherence : per-window FFT spectra and their
  agreement,
- hv_vs_time / hv_vs_azimuth : H/V curves as functions of time / azimuth,
- _window_raw_spectra / _window_hv_curve : the window pipeline
  primitives, and log_frequencies.

Split out of hvsr_engine.py.
"""


from hvsr_dsp import (
    fft, rfft_magnitude, resolve_workers, cosine_taper,
    detrend_linear, demean, butter_bandpass, bandpass_filter,
    smooth_spectrum, mute_transients, decimate, parse_paz, paz_deconvolve,
)
import math
from hvsr_engine_defaults import DEFAULT_B_VALUE, DEFAULT_FMAX, DEFAULT_FMIN, DEFAULT_SMOOTHING, DEFAULT_SMOOTH_WIDTH, DEFAULT_TAPER
from hvsr_engine_support import _fft_freqs, _magnitude, _magnitude_from_fft, _smooth_combine, _window_starts

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

def azimuthal_directivity(azimuths, freqs, grid, f0, band_ratio=0.2):
    """Compute the peak directivity azimuth and polarization / anisotropy
    ratio from an H/V vs azimuth grid.

    Searches for the maximum H/V amplitude in the frequency band around f0
    ([f0 * (1 - band_ratio), f0 * (1 + band_ratio)]).

    Returns a dict:
        peak_azimuth       : angle in degrees [0, 180) with highest amplification
        a_max              : maximum H/V amplitude at peak azimuth near f0
        a_min              : minimum H/V amplitude across azimuths near f0
        directivity_ratio  : a_max / a_min (>= 1.0)
        anisotropy_index   : (a_max - a_min) / a_max
        description        : interpretation text ('Isotropic / 1D flat layer', etc.)
    """
    if not azimuths or not freqs or not grid or f0 <= 0:
        return {
            "peak_azimuth": 0.0, "a_max": 0.0, "a_min": 0.0,
            "directivity_ratio": 1.0, "anisotropy_index": 0.0,
            "description": "Insufficient data"
        }
    lo_f = f0 * (1.0 - band_ratio)
    hi_f = f0 * (1.0 + band_ratio)
    k_indices = [k for k, f in enumerate(freqs) if lo_f <= f <= hi_f]
    if not k_indices:
        best_k = min(range(len(freqs)), key=lambda k: abs(freqs[k] - f0))
        k_indices = [best_k]

    az_amps = []
    for row in grid:
        vals = [row[k] for k in k_indices if k < len(row)]
        az_amps.append(max(vals) if vals else 0.0)

    best_az_idx = max(range(len(az_amps)), key=lambda i: az_amps[i])
    a_max = az_amps[best_az_idx]
    a_min = min(az_amps) if az_amps else a_max
    peak_az = azimuths[best_az_idx]

    ratio = (a_max / a_min) if a_min > 1e-12 else 1.0
    aniso = ((a_max - a_min) / a_max) if a_max > 1e-12 else 0.0

    if ratio < 1.25:
        desc = "Isotropic / 1D flat layer"
    elif ratio < 1.6:
        desc = "Moderate directivity / 2D valley effect"
    else:
        desc = "Strong directivity / Fault or 3D structure"

    return {
        "peak_azimuth": peak_az,
        "a_max": a_max,
        "a_min": a_min,
        "directivity_ratio": ratio,
        "anisotropy_index": aniso,
        "description": desc,
    }

def _window_raw_spectra(z, n, e, fs, w_len, taper):
    """Detrend / taper one window and return its raw one-sided magnitude
    spectra (before spectral smoothing) for the Z, N, E channels together
    with the FFT frequency axis."""
    w = int(round(w_len * fs))
    if w < 8 or w > len(z):
        return None

    def mag(chan):
        """Window magnitude spectrum: detrend, cosine-taper, FFT, and the
        magnitude of the positive-frequency bins."""
        seg = demean(detrend_linear(chan[:w]))
        win = cosine_taper(w, taper)
        seg = [seg[i] * win[i] for i in range(w)]
        return _magnitude(seg)

    return [mag(z), mag(n), mag(e)], _fft_freqs(fs, w)

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
