"""
hvsr_inv_driver.py
==================
The Monte-Carlo inversion driver: invert_hvsr orchestrates seeding,
sampling, parallel misfit evaluation (_inv_chunk_eval), best-model
tracking and result assembly into InversionResult.

Split out of hvsr_inversion.py.
"""


import math
import random
from hvsr_dsp import resolve_workers
import statistics
from hvsr_inv_ellipticity import rayleigh_ellipticity
from hvsr_inv_forward import hvsr_misfit, log_frequencies, resample_log, sample_model, seed_model, vs30_from_profile
from hvsr_inv_report import _build_inversion_log, _percentile

class InversionResult:
    """Everything produced by one 1D inversion run."""

    def __init__(self):
        self.station = ""
        self.freqs = []            # inversion grid (Hz)
        self.hv_obs = []           # observed H/V on the grid
        self.hv_syn = []           # best-model synthetic H/V on the grid
        self.layers = []           # list of dicts (best model)
        self.ensemble = []         # list of accepted models
        self.vs30 = None
        self.soil_class_nehrp = ("N/A", "")
        self.soil_class_sni = ("N/A", "")
        self.misfit = None
        self.n_models = 0
        self.n_accepted = 0
        self.vs_p16 = []
        self.vs_p84 = []
        self.thickness_p16 = []
        self.thickness_p84 = []
        self.misfits = []
        self.misfit_p50 = None
        self.misfit_p90 = None
        self.f0_obs = 0.0
        self.f0_syn = 0.0
        self.a0_obs = 0.0
        self.poisson = 0.40
        self.report_text = ""
        self.log = []

def _peak_index(freqs, vals):
    """Index of the largest value in ``vals`` (used to locate the H/V peak)."""
    best = 0
    best_v = -1.0
    for k, v in enumerate(vals):
        if v is not None and v > best_v:
            best_v = v
            best = k
    return best, best_v

def _inv_chunk_eval(args):
    """Evaluate a chunk of Monte-Carlo models in a worker process.

    Each model: sample a random Vs profile from the seed, run the
    forward model and compare against the observed curve.  Returns a
    list of (misfit, model, synthetic_curve) for the models that
    evaluated without error.
    """
    seed, base, chunk_idx, count, grid, hv_g, vs_factor, h_factor, \
        monotonic = args
    rng = random.Random((base + chunk_idx) * 7919 % (2 ** 31))
    results = []
    for _ in range(count):
        model = sample_model(seed, rng, vs_factor=vs_factor,
                             h_factor=h_factor, monotonic=monotonic)
        try:
            syn = rayleigh_ellipticity(grid, model["thickness"],
                                       model["vp"], model["vs"],
                                       model["rho"])
        except Exception:
            continue
        results.append((hvsr_misfit(hv_g, syn), model, syn))
    return results

def invert_hvsr(freqs_obs, hv_obs, f0, a0, station="station",
                n_layers=3, n_iter=600, poisson=0.40, vs30_anchor=None,
                monotonic=True, n_grid=48, band_lo=0.5, band_hi=2.0,
                vs_factor=1.6, h_factor=2.5, seed_rng=None,
                progress_cb=None, n_workers=None):
    """Monte-Carlo 1D inversion of an observed H/V curve.

    freqs_obs / hv_obs: the measured H/V curve (f0 / a0 its picked peak).
    Returns an InversionResult.  progress_cb(i, total) is called every 50
    models if provided.
    """
    res = InversionResult()
    res.station = station
    res.f0_obs = f0
    res.a0_obs = a0
    res.poisson = poisson
    res.n_models = n_iter

    fmin = max(min(freqs_obs), f0 * band_lo)
    fmax = min(max(freqs_obs), f0 * band_hi)
    grid = log_frequencies(fmin, fmax, n_grid)
    hv_g = resample_log(freqs_obs, hv_obs, grid)
    # drop invalid edges
    valid = [(f, v) for f, v in zip(grid, hv_g) if v and v > 0]
    if len(valid) < 8:
        res.log = ["inversion band too small - check the observed curve"]
        res.report_text = "\n".join(res.log)
        return res
    grid = [f for f, _ in valid]
    hv_g = [v for _, v in valid]

    rng = seed_rng or random.Random(20260809)
    n_workers = resolve_workers(n_workers)
    seed = seed_model(f0, a0, vs30=vs30_anchor, n_layers=n_layers,
                      poisson=poisson, max_depth=100.0)
    best = None
    best_syn = None
    best_m = float("inf")
    accepted = []
    misfits = []

    # Parallel Monte-Carlo: the models are independent, so the run can be
    # split across worker processes.  Falls back to the sequential loop
    # below on any platform error (frozen apps, restricted environments).
    done_parallel = False
    if n_workers and int(n_workers) > 1 and n_iter > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
            per = max(1, int(math.ceil(n_iter / float(n_workers))))
            base = rng.randrange(0, 2 ** 31)
            chunks = []
            left = n_iter
            while left > 0:
                c = min(per, left)
                chunks.append((seed, base, len(chunks), c, grid, hv_g,
                               vs_factor, h_factor, monotonic))
                left -= c
            if chunks:
                with ProcessPoolExecutor(
                        max_workers=min(int(n_workers), len(chunks))) as ex:
                    for k, chunk_res in enumerate(ex.map(_inv_chunk_eval,
                                                         chunks)):
                        for m, model, syn in chunk_res:
                            misfits.append(m)
                            if m < best_m:
                                best_m = m
                                best = model
                                best_syn = syn
                            accepted.append((m, model))
                        done = min(n_iter, (k + 1) * per)
                        if progress_cb:
                            progress_cb(done, n_iter)
                done_parallel = True
        except Exception:
            done_parallel = False
            misfits = []
            accepted = []
            best = None
            best_syn = None
            best_m = float("inf")

    if not done_parallel:
        for i in range(n_iter):
            model = sample_model(seed, rng, vs_factor=vs_factor,
                                 h_factor=h_factor, monotonic=monotonic)
            try:
                syn = rayleigh_ellipticity(grid, model["thickness"],
                                           model["vp"], model["vs"],
                                           model["rho"])
            except Exception:
                continue
            m = hvsr_misfit(hv_g, syn)
            misfits.append(m)
            if m < best_m:
                best_m = m
                best = model
                best_syn = syn
            accepted.append((m, model))
            if progress_cb and (i + 1) % 50 == 0:
                progress_cb(i + 1, n_iter)

    res.freqs = grid
    res.hv_obs = hv_g
    if best is None:
        res.log = ["no valid models found - check the model bounds"]
        res.report_text = "\n".join(res.log)
        return res

    res.hv_syn = best_syn
    res.misfit = best_m
    accepted.sort(key=lambda t: t[0])
    keep = max(1, int(0.05 * len(accepted)))
    top = [model for _m, model in accepted[:keep]]
    res.n_accepted = len(top)
    res.ensemble = top

    # final profile: layer-by-layer median of the accepted models
    n = len(seed["thickness"]) - 1

    # ensemble uncertainty: P16 / P84 of the accepted models per layer
    res.misfits = misfits
    _finite = [m for m in misfits if math.isfinite(m)]
    if _finite:
        res.misfit_p50 = _percentile(_finite, 50)
        res.misfit_p90 = _percentile(_finite, 90)
    res.vs_p16 = [_percentile([m["vs"][i] for m in top], 16)
                  for i in range(n + 1)]
    res.vs_p84 = [_percentile([m["vs"][i] for m in top], 84)
                  for i in range(n + 1)]
    res.thickness_p16 = [_percentile([m["thickness"][i] for m in top], 16)
                         for i in range(n)]
    res.thickness_p84 = [_percentile([m["thickness"][i] for m in top], 84)
                         for i in range(n)]
    med_vs = [statistics.median(sorted(m["vs"][i] for m in top))
              for i in range(n + 1)]
    med_h = [statistics.median(sorted(m["thickness"][i] for m in top))
             for i in range(n + 1)]
    med_vp = [statistics.median(sorted(m["vp"][i] for m in top))
              for i in range(n + 1)]
    med_rho = [statistics.median(sorted(m["rho"][i] for m in top))
               for i in range(n + 1)]

    # best model for the synthetic curve (more stable than the median for
    # the H/V fit) but the reported profile is the median ensemble
    layers = []
    depth = 0.0
    for i in range(n + 1):
        top_d = depth
        bottom_d = depth + (0.0 if i == n else med_h[i])
        depth = bottom_d
        layers.append({"top": top_d, "bottom": bottom_d,
                       "thickness": med_h[i] if i < n else None,
                       "vs": med_vs[i], "vp": med_vp[i],
                       "rho": med_rho[i], "layer": i,
                       "vs_lo": res.vs_p16[i] if i < len(res.vs_p16) else None,
                       "vs_hi": res.vs_p84[i] if i < len(res.vs_p84) else None,
                       "thk_lo": (res.thickness_p16[i]
                                  if i < len(res.thickness_p16) else None),
                       "thk_hi": (res.thickness_p84[i]
                                  if i < len(res.thickness_p84) else None)})
    res.layers = layers

    res.vs30 = vs30_from_profile(med_h, med_vs)
    try:
        import hvsr_standards
        if res.vs30:
            res.soil_class_nehrp = hvsr_standards.soil_class(res.vs30)
            res.soil_class_sni = hvsr_standards.soil_class_sni(res.vs30)
    except Exception:
        pass

    # synthetic f0 / A0
    k, v = _peak_index(grid, best_syn)
    res.f0_syn = grid[k]
    res.log = _build_inversion_log(res)
    res.report_text = "\n".join(res.log)
    return res
