"""
hvsr_inv_forward.py
===================
Forward model and supporting math for the Monte-Carlo inversion:

- rayleigh_ellipticity helpers live in hvsr_inv_ellipticity / _phasevel;
  here are the shared constants (TWO_PI, _normc, _sign, _var) and the
  model layer: log_frequencies, resample_log, vp_from_vs, density_from_vp,
  vs30_from_profile, seed_model / sample_model and hvsr_misfit.

Split out of hvsr_inversion.py.
"""


import math

TWO_PI = 2.0 * math.pi

def _normc(a):
    """Normalise a 5-vector by its max abs; return (vector, ln(norm))."""
    t1 = max((abs(v) for v in a), default=1.0)
    if t1 < 1.0e-40:
        t1 = 1.0
    return [v / t1 for v in a], math.log(t1)

def _sign(x):
    """Sign function: 1.0 for positive, -1.0 for negative, 0.0 otherwise."""
    return 1.0 if x > 0.0 else (-1.0 if x < 0.0 else 0.0)

def _var(p, q, ra, rb, wvno, xka, xkb, dpth):
    """P/S eigenfunction products for the real-arithmetic Dunkin matrix
    (CPS 'dltar' var)."""
    # P-wave eigenfunctions (c > vp => evanescent)
    pex = 0.0
    if wvno < xka:
        sinp = math.sin(p)
        w = sinp / ra
        x = -ra * sinp
        cosp = math.cos(p)
    elif wvno == xka:
        cosp = 1.0
        w = dpth
        x = 0.0
    else:
        pex = p
        fac = math.exp(-2.0 * p) if p < 16.0 else 0.0
        cosp = (1.0 + fac) * 0.5
        sinp = (1.0 - fac) * 0.5
        w = sinp / ra
        x = ra * sinp
    # S-wave eigenfunctions
    sex = 0.0
    if wvno < xkb:
        sinq = math.sin(q)
        y = sinq / rb
        z = -rb * sinq
        cosq = math.cos(q)
    elif wvno == xkb:
        cosq = 1.0
        y = dpth
        z = 0.0
    else:
        sex = q
        fac = math.exp(-2.0 * q) if q < 16.0 else 0.0
        cosq = (1.0 + fac) * 0.5
        sinq = (1.0 - fac) * 0.5
        y = sinq / rb
        z = rb * sinq
    exa = pex + sex
    a0 = math.exp(-exa) if exa < 60.0 else 0.0
    cpcq = cosp * cosq
    cpy = cosp * y
    cpz = cosp * z
    cqw = cosq * w
    cqx = cosq * x
    xy = x * y
    xz = x * z
    wy = w * y
    wz = w * z
    qmp = sex - pex
    fac = math.exp(qmp) if qmp > -40.0 else 0.0
    # (the scaled cosq/y/z are only needed by the eigenfunction recursion)
    return w, cosp, a0, cpcq, cpy, cpz, cqw, cqx, xy, xz, wy, wz

def log_frequencies(fmin, fmax, nfreq):
    """Log-spaced frequency grid."""
    if nfreq < 2:
        nfreq = 2
    step = math.log(fmax / fmin) / (nfreq - 1)
    return [fmin * math.exp(step * k) for k in range(nfreq)]

def resample_log(xs, ys, target_xs):
    """Log-log linear interpolation of (xs, ys) at target_xs (log-spaced)."""
    out = []
    for tx in target_xs:
        if tx <= xs[0] or tx >= xs[-1]:
            out.append(None)
            continue
        # locate interval in log space
        lx = [math.log(v) for v in xs]
        lt = math.log(tx)
        lo = 0
        hi = len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if lx[mid] <= lt:
                lo = mid
            else:
                hi = mid
        x0, x1 = lx[lo], lx[hi]
        y0, y1 = ys[lo], ys[hi]
        if y0 is None or y1 is None or y0 <= 0 or y1 <= 0:
            out.append(None)
            continue
        t = (lt - x0) / (x1 - x0) if x1 > x0 else 0.0
        out.append(math.exp(math.log(y0) + t * (math.log(y1) - math.log(y0))))
    return out

def vp_from_vs(vs_mps, poisson=0.40):
    """Compressional velocity from Vs and Poisson's ratio (elastic medium)."""
    if vs_mps <= 0 or not (0.0 < poisson < 0.5):
        return None
    return vs_mps * math.sqrt((2.0 - 2.0 * poisson) / (1.0 - 2.0 * poisson))

def density_from_vp(vp_mps):
    """Density (g/cm3) from Vp using Brocher (2005) - valid ~1.5-8 km/s,
    clamped for the soft-soil extrapolation.  rho = 1.6612 vp - 0.4721 vp^2
    + 0.0671 vp^3 - 0.0043 vp^4 + 0.000106 vp^5 (vp in km/s)."""
    vp = max(vp_mps, 150.0) / 1000.0
    rho = (1.6612 * vp - 0.4721 * vp ** 2 + 0.0671 * vp ** 3
           - 0.0043 * vp ** 4 + 0.000106 * vp ** 5)
    return max(1.6, min(2.9, rho))

def vs30_from_profile(thickness_m, vs_mps):
    """Harmonic-mean Vs over the top 30 m of a layered profile.

    thickness_m / vs_mps give every layer; the last entry is treated as a
    half-space (infinite thickness) so it fills any remainder of 30 m.
    """
    if not thickness_m or not vs_mps or vs_mps[-1] <= 0:
        return None
    rem = 30.0
    acc = 0.0
    for h, v in zip(thickness_m[:-1], vs_mps[:-1]):
        if rem <= 0:
            break
        use = min(h, rem)
        acc += use / v
        rem -= use
    if rem > 0 and vs_mps[-1] > 0:
        acc += rem / vs_mps[-1]
    if acc <= 0:
        return None
    return 30.0 / acc

def seed_model(f0, a0=None, vs30=None, n_layers=3, poisson=0.40,
               max_depth=100.0):
    """Build an initial layered model from f0 / A0 / Vs30.

    - the first layer thickness comes from the quarter-wavelength rule
      h1 ~ Vs1 / (4*f0),
    - the velocity level is anchored on the Vs30 estimate (or a default
      soft-soil 300 m/s), with a mild gradient to a stiff half-space,
    - deeper layers get progressively larger thicknesses.
    """
    n_layers = max(1, int(n_layers))
    vs_top = float(vs30) if vs30 and vs30 > 100 else 300.0
    vs_top = max(120.0, min(600.0, vs_top))
    h1 = max(2.0, min(60.0, vs_top / (4.0 * f0) if f0 > 0 else 30.0))
    # depth budget for the remaining layers
    h = [h1]
    rem = max_depth - h1
    for i in range(1, n_layers):
        frac = rem / (n_layers - i + 1)
        hi = max(3.0, min(60.0, frac * 1.4))
        h.append(hi)
        rem -= hi
    vs_half = min(3500.0, max(600.0, 3.0 * vs_top))
    vs = []
    for i in range(n_layers):
        growth = 1.0 + i * 0.35 + (i * i) * 0.03
        v = min(vs_half * 0.92, max(120.0, vs_top * growth))
        vs.append(v)
    vs.append(vs_half)
    h.append(1.0)  # half-space thickness is ignored
    # derived Vp / density
    vp = [vp_from_vs(v, poisson) or v * 2.45 for v in vs]
    rho = [density_from_vp(v) for v in vp]
    return {"thickness": h, "vs": vs, "vp": vp, "rho": rho,
            "poisson": poisson}

def sample_model(seed, rng, vs_factor=1.6, h_factor=2.5, monotonic=True,
                 vs_min=100.0, vs_max=3500.0, h_min=1.0, h_max=100.0):
    """Random perturbation of a seed model (log-uniform sampling)."""
    n = len(seed["vs"]) - 1          # number of finite layers
    vs = []
    for i in range(n):
        lo = max(vs_min, seed["vs"][i] / vs_factor)
        hi = min(vs_max, seed["vs"][i] * vs_factor)
        vs.append(math.exp(rng.uniform(math.log(lo), math.log(hi))))
    if monotonic:
        for i in range(1, n):
            if vs[i] < vs[i - 1] * 0.95:
                vs[i] = vs[i - 1] * rng.uniform(1.0, 1.6)
    vs_half = math.exp(rng.uniform(math.log(max(vs[-1], 400.0)),
                                   math.log(min(vs_max, seed["vs"][-1] * 1.5))))
    vs = vs + [vs_half]
    h = []
    for i in range(n):
        lo = max(h_min, seed["thickness"][i] / h_factor)
        hi = min(h_max, seed["thickness"][i] * h_factor)
        h.append(math.exp(rng.uniform(math.log(lo), math.log(hi))))
    h.append(1.0)
    poisson = seed.get("poisson", 0.40)
    vp = [vp_from_vs(v, poisson) or v * 2.45 for v in vs]
    rho = [density_from_vp(v) for v in vp]
    return {"thickness": h, "vs": vs, "vp": vp, "rho": rho,
            "poisson": poisson}

def hvsr_misfit(hv_obs, hv_syn, scale=True):
    """Log-domain L2 misfit over common valid points.

    With scale=True the synthetic curve is rescaled so its peak equals the
    observed peak.  Measured H/V amplitudes are systematically lower than
    the pure Rayleigh-ellipticity resonance peak, so the fit then focuses
    on the *shape and peak frequency* while keeping the observed amplitude
    level - the standard practice in HVSR inversion (peak-frequency
    driven).  With scale=False the raw amplitudes are compared.
    """
    pairs = [(o, s) for o, s in zip(hv_obs, hv_syn)
             if o and s and o > 0 and s > 0]
    if not pairs:
        return float("inf")
    if scale:
        obs_max = max(o for o, _ in pairs)
        syn_max = max(s for _, s in pairs)
        if syn_max > 0:
            pairs = [(o, s * obs_max / syn_max) for o, s in pairs]
    s = sum((math.log10(o) - math.log10(s)) ** 2 for o, s in pairs)
    return math.sqrt(s / len(pairs))
