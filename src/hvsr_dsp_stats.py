"""
hvsr_dsp_stats.py
=================
Signal conditioning and spectral smoothing (pure standard library):

- demean / detrend_linear / cosine_taper : pre-processing steps,
- classic_sta_lta / mute_transients : short-term-average trigger,
- konno_ohmachi_weight / _ko_band / _smooth_bands / konno_ohmachi_smooth /
  smooth_spectrum : log-frequency spectral smoothing,
- decimate / resolve_workers : resampling + thread-count helpers.

Split out of hvsr_dsp.py.
"""


from bisect import bisect_left
from functools import lru_cache
import math
import os

def demean(x):
    """Remove the arithmetic mean."""
    n = len(x)
    if n == 0:
        return list(x)
    mean = sum(x) / n
    return [v - mean for v in x]

def detrend_linear(x):
    """Remove the best-fit straight line (least squares)."""
    n = len(x)
    if n < 2:
        return list(x)
    sx = sum(x)
    st = sum(range(n))
    st2 = sum(t * t for t in range(n))
    stx = sum(t * v for t, v in enumerate(x))
    denom = n * st2 - st * st
    if abs(denom) < 1e-30:
        return list(x)
    slope = (n * stx - st * sx) / denom
    intercept = (sx - slope * st) / n
    return [v - (slope * t + intercept) for t, v in enumerate(x)]

def cosine_taper(n, fraction=0.05):
    """Tukey-style cosine taper window of length n with the given taper fraction."""
    if n <= 1:
        return [1.0] * n
    fl = max(1, int(round(fraction * n)))
    window = [1.0] * n
    for i in range(fl):
        val = 0.5 * (1.0 - math.cos(math.pi * i / fl))
        window[i] = val
        window[n - 1 - i] = val
    return window

def classic_sta_lta(x, sta_len, lta_len):
    """Classic STA/LTA characteristic function (as in geophysics software)."""
    n = len(x)
    out = [0.0] * n
    if n == 0:
        return out
    sta_len = max(1, int(sta_len))
    lta_len = max(1, int(lta_len))
    # running energy averages
    sta = 0.0
    lta = 0.0
    sta_sum = 0.0
    lta_sum = 0.0
    sta_win = [0.0] * sta_len
    lta_win = [0.0] * lta_len
    for i in range(n):
        e = x[i] * x[i]
        # STA window (ring buffer)
        old = sta_win[i % sta_len]
        sta_sum += e - old
        sta_win[i % sta_len] = e
        sta = sta_sum / sta_len
        # LTA window
        old2 = lta_win[i % lta_len]
        lta_sum += e - old2
        lta_win[i % lta_len] = e
        lta = lta_sum / lta_len
        if lta > 1e-30:
            out[i] = sta / lta
        else:
            out[i] = 0.0
    return out

def mute_transients(z, n, e, sta_sec, lta_sec, fs, threshold=2.5):
    """Zero-mute samples flagged by the STA/LTA of the vertical channel."""
    cft = classic_sta_lta(z, int(sta_sec * fs), int(lta_sec * fs))
    idx = [i for i, v in enumerate(cft) if v > threshold]
    zz = list(z)
    nn = list(n)
    ee = list(e)
    for i in idx:
        zz[i] = 0.0
        nn[i] = 0.0
        ee[i] = 0.0
    return zz, nn, ee, idx

def decimate(x, factor):
    """Integer-factor decimation with a simple anti-alias box filter."""
    if factor <= 1:
        return list(x)
    out = []
    for i in range(0, len(x) - factor + 1, factor):
        out.append(sum(x[i:i + factor]) / factor)
    return out

def resolve_workers(requested=None, cap=8):
    """Effective worker-process count for the parallel parameter sweeps.

    1. The HVSR_WORKERS environment variable wins (0 / 1 disables
       parallelism entirely - useful on busy or low-RAM machines);
    2. otherwise the explicitly requested count, clamped to [1, cap];
    3. otherwise 1 (fully sequential).
    """
    env = os.environ.get("HVSR_WORKERS", "").strip()
    if env:
        try:
            return max(1, min(int(env), cap))
        except ValueError:
            pass
    if requested is not None:
        try:
            return max(1, min(int(requested), cap))
        except (TypeError, ValueError):
            return 1
    return 1

def konno_ohmachi_weight(freq, freq_center, b_value=40.0):
    """Konno-Ohmachi window value W_b(f/fc)."""
    if freq <= 0.0 or freq_center <= 0.0:
        return 0.0
    ratio = freq / freq_center
    if abs(ratio - 1.0) < 1e-12:
        return 1.0
    lg = math.log10(ratio)
    denom = b_value * lg
    val = math.sin(denom) / denom
    return val ** 4

def _ko_band(fc, b_value):
    """Frequency band around fc where the KO weight is non-negligible."""
    half = 4.5 / b_value  # decades; weight < 1e-4 outside this band
    lo = fc * math.pow(10.0, -half)
    hi = fc * math.pow(10.0, half)
    return lo, hi

def _smooth_bands(method, width, freqs, target_freqs):
    """Per-target (source_index, weight) pairs for a smoothing operator.

    The bands depend only on the frequency axes and the operator, so they
    are computed once per analysis and reused for every window - the per
    target-freq trig calls disappear from the inner smoothing loop.
    """
    bands = []
    if method == "konno_ohmachi":
        for fc in target_freqs:
            lo, hi = _ko_band(fc, width)
            i0 = bisect_left(freqs, lo)
            pairs = []
            for i in range(i0, len(freqs)):
                f = freqs[i]
                if f > hi:
                    break
                if f <= 0.0:
                    continue
                pairs.append((i, konno_ohmachi_weight(f, fc, width)))
            bands.append(pairs)
        return bands
    if method == "moving_average":
        half = 0.5 * width  # decades
        lo_f = lambda fc: fc * math.pow(10.0, -half)
        hi_f = lambda fc: fc * math.pow(10.0, +half)
        wfun = lambda r: 1.0
    elif method == "triangular_constant":
        half = 0.5 * width  # Hz
        lo_f = lambda fc: fc - half
        hi_f = lambda fc: fc + half
        wfun = lambda r: 1.0 - abs(r) * (2.0 / width) if abs(r) < half else 0.0
    elif method == "triangular_proportional":
        half = 0.5 * width  # decades
        lo_f = lambda fc: fc * math.pow(10.0, -half)
        hi_f = lambda fc: fc * math.pow(10.0, +half)
        wfun = lambda r: 1.0 - abs(r) * (2.0 / width) if abs(r) < half else 0.0
    else:
        raise ValueError("unknown smoothing method: %s" % method)
    for fc in target_freqs:
        if fc <= 0.0:
            bands.append([])
            continue
        lo, hi = lo_f(fc), hi_f(fc)
        i0 = bisect_left(freqs, lo)
        pairs = []
        for i in range(i0, len(freqs)):
            f = freqs[i]
            if f > hi:
                break
            if f <= 0.0:
                continue
            if method == "moving_average":
                w = 1.0
            elif method == "triangular_constant":
                w = wfun(f - fc)
            else:  # triangular_proportional
                w = wfun(math.log10(f / fc))
            if w <= 0.0:
                continue
            pairs.append((i, w))
        bands.append(pairs)
    return bands

def konno_ohmachi_smooth(mag_spectrum, freqs, target_freqs, b_value=40.0):
    """Smooth a magnitude spectrum at log-spaced target frequencies.

    Only the (small) band of FFT frequencies around each target where the
    Konno-Ohmachi weight is non-negligible is summed, which keeps the pure
    Python implementation fast enough for interactive use.
    """
    bands = _smooth_bands("konno_ohmachi", b_value,
                          tuple(freqs), tuple(target_freqs))
    smoothed = []
    for pairs in bands:
        total_w = 0.0
        total_s = 0.0
        for i, w in pairs:
            total_w += w
            total_s += w * mag_spectrum[i]
        smoothed.append(total_s / total_w if total_w > 0.0 else 0.0)
    return smoothed

def smooth_spectrum(mag_spectrum, freqs, target_freqs, method="konno_ohmachi",
                    width=40.0):
    """Smooth a magnitude spectrum with one of four selectable operators.

    method / width semantics:
      'konno_ohmachi'           Konno-Ohmachi window (width = b-value,
                                larger = narrower, default 40)
      'moving_average'          boxcar average, constant relative width in
                                decades (width = decades, default 0.1)
      'triangular_constant'     triangular window, constant absolute width
                                in Hz (width = Hz, default 0.5)
      'triangular_proportional' triangular window, width proportional to the
                                centre frequency in decades (default 0.1)

    Returns the smoothed spectrum evaluated at the target frequencies.
    """
    if method == "konno_ohmachi":
        return konno_ohmachi_smooth(mag_spectrum, freqs, target_freqs, width)
    bands = _smooth_bands(method, width, tuple(freqs), tuple(target_freqs))
    smoothed = []
    for pairs in bands:
        total_w = 0.0
        total_s = 0.0
        for i, w in pairs:
            total_w += w
            total_s += w * mag_spectrum[i]
        smoothed.append(total_s / total_w if total_w > 0.0 else 0.0)
    return smoothed
