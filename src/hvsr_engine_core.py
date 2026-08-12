"""
hvsr_engine_core.py
===================
The analysis pipeline: analyze and _finalize_analysis, the HvsrResult
container, peak picking / quality scoring (pick_peak, peak_quality,
_best-index peak finding), SESAME evaluation, vulnerability index and
window rejection.

Split out of hvsr_engine.py.
"""


import math
import statistics
from hvsr_engine_defaults import DEFAULT_B_VALUE, DEFAULT_FMAX, DEFAULT_FMIN, DEFAULT_NFREQ, DEFAULT_SMOOTHING, DEFAULT_SMOOTH_WIDTH, DEFAULT_TAPER, MAX_PICK_FREQ
from hvsr_engine_report import _build_log
from hvsr_engine_spectra import _window_hv_curve, log_frequencies
from hvsr_engine_support import _window_peak_index, _window_starts

# Optional (pure stdlib): global HVSR method standards (SESAME, Japan, ...)
try:
    import hvsr_standards
    _HAVE_STANDARDS = True
except Exception:
    _HAVE_STANDARDS = False

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
