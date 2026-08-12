"""
hvsr_engine_preprocess.py
=========================
Input conditioning: trim_seconds and preprocess (detrend, demean, taper
and band-pass filtering with the configured DEFAULT_FILTER).

Split out of hvsr_engine.py.
"""


from hvsr_io import ThreeChannel, auto_load, DataError
from hvsr_dsp import (
    fft, rfft_magnitude, resolve_workers, cosine_taper,
    detrend_linear, demean, butter_bandpass, bandpass_filter,
    smooth_spectrum, mute_transients, decimate, parse_paz, paz_deconvolve,
)
import math
from hvsr_engine_defaults import DEFAULT_FILTER, DEFAULT_FILTER_ORDER, DEFAULT_FILTER_RIPPLE

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
