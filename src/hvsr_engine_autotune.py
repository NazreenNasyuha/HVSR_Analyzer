"""
hvsr_engine_autotune.py
=======================
The auto-tune stage: auto_tune runs the two-stage tuning search over
smoothing widths / window sizes, with _stage2_init / _stage2_job and
sesame_score driving the acceptance criterion.

Split out of hvsr_engine.py.
"""


from hvsr_dsp import (
    fft, rfft_magnitude, resolve_workers, cosine_taper,
    detrend_linear, demean, butter_bandpass, bandpass_filter,
    smooth_spectrum, mute_transients, decimate, parse_paz, paz_deconvolve,
)
from hvsr_engine_core import _finalize_analysis
from hvsr_engine_defaults import DEFAULT_B_VALUE, DEFAULT_FMAX, DEFAULT_FMIN, DEFAULT_NFREQ, DEFAULT_SMOOTHING, DEFAULT_TAPER
from hvsr_engine_spectra import _window_raw_spectra, log_frequencies
from hvsr_engine_support import _smooth_combine, _window_starts

_SMOOTH_DEFAULTS = {
    "konno_ohmachi": 40.0,
    "moving_average": 0.1,
    "triangular_constant": 0.5,
    "triangular_proportional": 0.1,
}

_STAGE2_CTX = {}

def sesame_score(crit):
    """Count of satisfied criteria (6 curve+peak criteria used for tuning)."""
    score = 0
    for key in ("f0_gt_10_over_lw", "nc_gt_200", "sigma_A_ok",
                "drop_below_f0", "drop_above_f0", "a0_gt_2"):
        if crit.get(key):
            score += 1
    return score

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
        """Return the mean curves for one (smoothing, width, combo)
        combination, reusing the cached per-window raw spectra so the full
        sweep costs about one FFT pass."""
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
        """Score one candidate parameter set: finalise the analysis with
        these settings and return the SESAME reliability score."""
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
