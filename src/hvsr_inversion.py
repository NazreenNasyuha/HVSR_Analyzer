"""
hvsr_inversion.py
=================
1D inversion of an observed H/V spectral-ratio curve into a layered
S-wave velocity (Vs) profile.  Pure standard library - no numpy, scipy,
obspy, disba, geopsy.

Two parts:

1. FORWARD MODEL
   The theoretical H/V of a layered soil model is taken as the surface
   ellipticity of the fundamental-mode Rayleigh wave.  This is computed
   from scratch with the classic Thomson-Haskell / Dunkin (1965) compound
   (delta) matrix algorithm - the same algorithm as Herrmann's Computer
   Programs in Seismology 'surf96' / 'swegn96' (and the 'disba' Python
   package, which this port follows) - written here on the standard
   library only.

   - the dispersion (period equation) is evaluated with the real-arithmetic
     Dunkin matrix (CPS 'dltar'),
   - the phase velocity of the fundamental mode is found with the CPS
     bracketing + Neville/bisection hybrid root finder ('getsol'/'nevill'),
   - the surface ellipticity H/V = |u_x/u_z| is recovered from the
     compound vector built upwards from the half-space ('swegn96'
     eigenfunction recursion), which is normalised at every layer so it
     stays stable for thin layers / high frequencies.

   Units are converted internally to km, km/s and g/cm^3 (the CPS
   convention); the public API works in metres and m/s.

2. INVERSION
   A parameterised Monte-Carlo search over the Vs profile:

     - layers 1..n (n user-selectable, default 3) + a half-space,
     - each layer gets a Vs drawn log-uniformly from bounds built around
       an initial model that is *seeded automatically from the H/V result*
       (f0 sets the first-layer thickness via the quarter-wavelength
       relation h1 ~ Vs1/(4*f0); the Vs30 estimate anchors the velocity
       level; deeper layers are progressively faster),
     - optional monotonicity constraint (Vs must increase with depth),
     - the synthetic H/V is compared with the observed curve on a
       log-spaced frequency grid around f0 (log-domain L2 misfit),
     - the best-fitting models are kept and averaged into a final profile,
       with Vs30 (harmonic mean over the top 30 m), NEHRP and SNI
       site classes, and a per-layer soil-type table.

This lets the program answer the classic question: given the H/V
curve, what layered Vs model (layer depths + velocities) produced it, and
what kind of soil is that?
"""

import math
import random

from hvsr_dsp import resolve_workers
import statistics

TWO_PI = 2.0 * math.pi

# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------
def _normc(a):
    """Normalise a 5-vector by its max abs; return (vector, ln(norm))."""
    t1 = max((abs(v) for v in a), default=1.0)
    if t1 < 1.0e-40:
        t1 = 1.0
    return [v / t1 for v in a], math.log(t1)


def _sign(x):
    return 1.0 if x > 0.0 else (-1.0 if x < 0.0 else 0.0)


def misfit_histogram(misfits, nbins=24):
    """Histogram of the finite model misfits -> (edges, counts).

    edges has nbins+1 increasing values and counts has nbins entries.
    Returns (None, []) when fewer than 2 finite values are present
    (e.g. all models degenerate).  inf / None values are skipped.
    """
    vals = sorted(m for m in misfits
                  if m is not None and math.isfinite(m))
    if len(vals) < 2:
        return None, []
    nbins = max(4, int(nbins))
    lo, hi = vals[0], vals[-1]
    if hi <= lo:
        hi = lo + 1e-9
    width = (hi - lo) / nbins
    edges = [lo + width * k for k in range(nbins + 1)]
    counts = [0] * nbins
    for v in vals:
        k = int((v - lo) / width)
        if k >= nbins:
            k = nbins - 1
        counts[k] += 1
    return edges, counts


def _percentile(vals, p):
    """Nearest-rank percentile of a list (deterministic, no interpolation)."""
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    k = max(1, min(n, int(math.ceil(p / 100.0 * n))))
    return s[k - 1]


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


# ----------------------------------------------------------------------
# Physical relations
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# Forward model: Rayleigh-wave ellipticity (CPS surf96 / swegn96 port)
# ----------------------------------------------------------------------
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


def _dnka_real(wvno2, gam, gammk, rho, a0, cpcq, cpy, cpz, cqw, cqx,
               xy, xz, wy, wz, ca):
    """Dunkin's 5x5 compound matrix (real version, CPS 'dltar')."""
    gamm1 = gam - 1.0
    twgm1 = gam + gamm1
    gmgmk = gam * gammk
    gmgm1 = gam * gamm1
    gm1sq = gamm1 * gamm1
    rho2 = rho * rho
    a0pq = a0 - cpcq
    t = -2.0 * wvno2
    ca[0][0] = cpcq - 2.0 * gmgm1 * a0pq - gmgmk * xz - wvno2 * gm1sq * wy
    ca[0][1] = (wvno2 * cpy - cqx) / rho
    ca[0][2] = -(twgm1 * a0pq + gammk * xz + wvno2 * gamm1 * wy) / rho
    ca[0][3] = (cpz - wvno2 * cqw) / rho
    ca[0][4] = -(2.0 * wvno2 * a0pq + xz + wvno2 * wvno2 * wy) / rho2
    ca[1][0] = (gmgmk * cpz - gm1sq * cqw) * rho
    ca[1][1] = cpcq
    ca[1][2] = gammk * cpz - gamm1 * cqw
    ca[1][3] = -wz
    ca[1][4] = ca[0][3]
    ca[3][0] = (gm1sq * cpy - gmgmk * cqx) * rho
    ca[3][1] = -xy
    ca[3][2] = gamm1 * cpy - gammk * cqx
    ca[3][3] = ca[1][1]
    ca[3][4] = ca[0][1]
    ca[4][0] = (-(2.0 * gmgmk * gm1sq * a0pq + gmgmk * gmgmk * xz
                  + gm1sq * gm1sq * wy) * rho2)
    ca[4][1] = ca[3][0]
    ca[4][2] = (-(gammk * gamm1 * twgm1 * a0pq + gam * gammk * gammk * xz
                  + gamm1 * gm1sq * wy) * rho)
    ca[4][3] = ca[1][0]
    ca[4][4] = ca[0][0]
    ca[2][0] = t * ca[4][2]
    ca[2][1] = t * ca[3][2]
    ca[2][2] = a0 + 2.0 * (cpcq - ca[0][0])
    ca[2][3] = t * ca[1][2]
    ca[2][4] = t * ca[0][2]
    return ca


def _dltar4(wvno, omega, d, a, b, rho, llw, ca):
    """Rayleigh-wave period equation value (CPS 'dltar', Dunkin matrix).

    Also returns the surface compound vector `e` (used for the
    eigenfunction-style ellipticity below).
    """
    omega = max(omega, 1.0e-4)
    wvno2 = wvno * wvno
    xka = omega / a[-1]
    xkb = omega / b[-1]
    ra = math.sqrt((wvno + xka) * abs(wvno - xka))
    rb = math.sqrt((wvno + xkb) * abs(wvno - xkb))
    t = b[-1] / omega
    gammk = 2.0 * t * t
    gam = gammk * wvno2
    gamm1 = gam - 1.0
    rho1 = rho[-1]
    e = [0.0] * 5
    e[0] = rho1 * rho1 * (gamm1 * gamm1 - gam * gammk * ra * rb)
    e[1] = -rho1 * ra
    e[2] = rho1 * (gamm1 - gammk * ra * rb)
    e[3] = rho1 * rb
    e[4] = wvno2 - ra * rb
    ee = [0.0] * 5
    for m in range(len(d) - 2, llw, -1):
        xka = omega / a[m]
        xkb = omega / b[m]
        t = b[m] / omega
        gammk = 2.0 * t * t
        gam = gammk * wvno2
        ra = math.sqrt((wvno + xka) * abs(wvno - xka))
        rb = math.sqrt((wvno + xkb) * abs(wvno - xkb))
        dpth = d[m]
        rho1 = rho[m]
        p = ra * dpth
        q = rb * dpth
        (w, cosp, a0, cpcq, cpy, cpz, cqw, cqx, xy, xz, wy,
         wz) = _var(p, q, ra, rb, wvno, xka, xkb, dpth)
        ca = _dnka_real(wvno2, gam, gammk, rho1, a0, cpcq, cpy, cpz,
                        cqw, cqx, xy, xz, wy, wz, ca)
        for i in range(5):
            s = 0.0
            for j in range(5):
                s += e[j] * ca[j][i]
            ee[i] = s
        e, _ = _normc(ee)
    if llw == 0:
        # fluid top layer: apply the free-surface correction (kept for
        # completeness; the HVSR models used here are all solid)
        xka = omega / a[0]
        ra = math.sqrt((wvno + xka) * abs(wvno - xka))
        dpth = d[0]
        rho1 = rho[0]
        p = ra * dpth
        w, cosp, _a0, *_rest = _var(p, 0.0, ra, 1.0e-5, wvno, xka, xkb, dpth)
        dlt = cosp * e[0] - rho1 * w * e[1]
    else:
        dlt = e[0]
    return dlt, e


def _gtsolh(a, b):
    """Rayleigh-wave velocity of a homogeneous half-space (CPS 'gtsolh')."""
    c = 0.95 * b
    for _ in range(5):
        gamma = b / a
        kappa = c / b
        k2 = kappa * kappa
        gk2 = (gamma * kappa) ** 2
        fac1 = math.sqrt(1.0 - gk2)
        fac2 = math.sqrt(1.0 - k2)
        fr = (2.0 - k2) ** 2 - 4.0 * fac1 * fac2
        frp = -4.0 * (2.0 - k2) * kappa
        frp += 4.0 * fac2 * gamma * gamma * kappa / fac1
        frp += 4.0 * fac1 * kappa / fac2
        frp /= b
        if abs(frp) < 1e-30:
            break
        c -= fr / frp
    return c


def _nevill(t, c1, c2, del1, del2, d, a, b, rho, llw, ca):
    """Neville-polynomial / bisection hybrid root refinement (CPS)."""
    x = [0.0] * 20
    y = [0.0] * 20
    omega = TWO_PI / t
    c3 = 0.5 * (c1 + c2)
    del3 = _dltar4(omega / c3, omega, d, a, b, rho, llw, ca)[0]
    nev = 1
    nctrl = 1
    m = 1
    while True:
        nctrl += 1
        if nctrl >= 100:
            break
        if c3 < min(c1, c2) or c3 > max(c1, c2):
            nev = 0
            c3 = 0.5 * (c1 + c2)
            del3 = _dltar4(omega / c3, omega, d, a, b, rho, llw, ca)[0]
        s13 = del1 - del3
        s32 = del3 - del2
        if _sign(del3) * _sign(del1) < 0.0:
            c2 = c3
            del2 = del3
        else:
            c1 = c3
            del1 = del3
        if abs(c1 - c2) <= 1.0e-6 * c1:
            break
        if _sign(s13) != _sign(s32):
            nev = 0
        ss1 = abs(del1)
        s1 = 0.01 * ss1
        ss2 = abs(del2)
        s2 = 0.01 * ss2
        if s1 > ss2 or s2 > ss1 or nev == 0:
            c3 = 0.5 * (c1 + c2)
            del3 = _dltar4(omega / c3, omega, d, a, b, rho, llw, ca)[0]
            nev = 1
            m = 1
        else:
            if nev == 2:
                x[m - 1] = c3
                y[m - 1] = del3
            else:
                x[0] = c1
                y[0] = del1
                x[1] = c2
                y[1] = del2
                m = 1
            flag = 1
            for kk in range(m):
                j = m - kk
                denom = y[m] - y[j]
                if abs(denom) < 1.0e-10 * abs(y[m]):
                    flag = 0
                    break
                x[j - 1] = (-y[j - 1] * x[j] + y[m] * x[j - 1]) / denom
            if flag:
                c3 = x[0]
                del3 = _dltar4(omega / c3, omega, d, a, b, rho, llw, ca)[0]
                nev = 2
                m += 1
                m = min(m, 10)
            else:
                c3 = 0.5 * (c1 + c2)
                del3 = _dltar4(omega / c3, omega, d, a, b, rho, llw, ca)[0]
                nev = 1
                m = 1
    return c3


def _getsol(t1, c1, clow, dc, cm, betmx, ifirst, del1st, d, a, b, rho,
            llw, ca):
    """Bracket the fundamental-mode root and refine it (CPS 'getsol')."""
    omega = TWO_PI / t1
    del1 = _dltar4(omega / c1, omega, d, a, b, rho, llw, ca)[0]
    if ifirst:
        del1st = del1
    if (not ifirst) and _sign(del1st) * _sign(del1) < 0.0:
        idir = -1.0
    else:
        idir = 1.0
    while True:
        c2 = c1 + idir * dc
        if c2 <= clow:
            idir = 1.0
            c1 = clow
        else:
            omega = TWO_PI / t1
            del2 = _dltar4(omega / c2, omega, d, a, b, rho, llw, ca)[0]
            if _sign(del1) != _sign(del2):
                c1 = _nevill(t1, c1, c2, del1, del2, d, a, b, rho, llw, ca)
                iret = c1 > betmx
                break
            c1 = c2
            del1 = del2
        iret = c1 < cm or c1 >= betmx + dc
        if iret:
            break
    return c1, del1st, iret


def _phase_velocities(periods, d, a, b, rho, dc=0.005):
    """Fundamental-mode Rayleigh phase velocity (km/s) per period (s).

    Periods must be sorted ascending (high frequency first) so the
    previous solution can seed the next search.
    """
    kmax = len(periods)
    c = [0.0] * kmax
    ca = [[0.0] * 5 for _ in range(5)]
    llw = 0 if b[0] <= 0.0 else -1
    betmx = -1.0e20
    betmn = 1.0e20
    jmn = 0
    jsol = False
    for i in range(len(d)):
        if b[i] > 0.01 and b[i] < betmn:
            betmn = b[i]
            jmn = i
            jsol = False
        elif b[i] < 0.01 and a[i] < betmn:
            betmn = a[i]
            jmn = i
            jsol = True
        if b[i] > betmx:
            betmx = b[i]
    cc = betmn if jsol else _gtsolh(a[jmn], b[jmn])
    cc *= 0.9
    c1 = cc
    cm = cc
    onea = 1.5
    del1st = 0.0
    for k in range(kmax):
        if k == 0:
            clow = cc
            c1 = cc
        else:
            clow = cm
            c1 = c[k - 1] - onea * dc
        c1, del1st, iret = _getsol(periods[k], c1, clow, dc, cm, betmx,
                                   k == 0, del1st, d, a, b, rho, llw, ca)
        if iret:
            for i in range(k, kmax):
                c[i] = 0.0
            break
        c[k] = c1
    return c


# ----------------------------------------------------------------------
# Eigenfunction recursion (CPS 'swegn96' style) for the surface
# ellipticity at a given wavenumber.
# ----------------------------------------------------------------------
def _evalg(m, d, a, b, rho, wvno, om):
    """Half-space compound vector for the eigenfunction recursion."""
    wvno2 = wvno * wvno
    om2 = om * om
    xka = om / a[m]
    xkb = om / b[m] if b[m] > 0.01 else 0.0
    ra = (wvno2 - xka * xka) ** 0.5
    rb = (wvno2 - xkb * xkb) ** 0.5
    gam = b[m] * wvno / om
    gam = 2.0 * gam * gam
    gamm1 = gam - (1.0 + 0j)
    gbr = [0j] * 5
    if b[m] > 0.01:
        gbr[0] = rho[m] * rho[m] * om2 * om2 * (
            -gam * gam * ra * rb + wvno2 * gamm1 * gamm1)
        gbr[1] = -rho[m] * wvno2 * ra * om2
        gbr[2] = -rho[m] * (-gam * ra * rb + wvno2 * gamm1) * om2 * wvno
        gbr[3] = rho[m] * wvno2 * rb * om2
        gbr[4] = wvno2 * (wvno2 - ra * rb)
        fac = 0.25 / (-rho[m] * rho[m] * om2 * om2 * wvno2 * ra * rb)
        for i in range(5):
            gbr[i] *= fac
    else:
        if all(v < 0.01 for v in b):
            gbr[0] = 0.5 / ra
            gbr[1] = 0.5j / (-rho[m] * om2)
        else:
            gbr[3] = 0.5 * rho[m] * om2 / ra
            gbr[4] = -0.5
    return [v.real for v in gbr]


def _varsv(p, q, rp, rsv, d, iwat):
    """Complex-arithmetic P/S products for the eigenfunction recursion."""
    pr = p.real
    pi = p.imag
    qr = q.real
    qi = q.imag
    pex = pr
    svex = 0.0
    epp = 0.5 * (math.cos(pi) + 1j * math.sin(pi))
    epm = epp.conjugate()
    pfac = math.exp(-2.0 * pr) if pr < 30.0 else 0.0
    cosp = (epp + pfac * epm).real
    sinp = epp - pfac * epm
    rsinp = (rp * sinp).real
    if abs(pr) < 1.0e-5 and abs(rp) < 1.0e-5:
        sinpr = d
    else:
        sinpr = sinp / rp
    if iwat == 1:
        cosq = 1.0
        rsinq = 0.0
        sinqr = 0.0
    else:
        svex = qr
        eqp = 0.5 * (math.cos(qi) + 1j * math.sin(qi))
        eqm = eqp.conjugate()
        svfac = math.exp(-2.0 * qr) if qr < 30.0 else 0.0
        cosq = (eqp + svfac * eqm).real
        sinq = eqp - svfac * eqm
        rsinq = (rsv * sinq).real
        if abs(qr) < 1.0e-5 and abs(rsv) < 1.0e-5:
            sinqr = d
        else:
            sinqr = sinq / rsv
    return cosp, cosq, rsinp, rsinq, sinpr, sinqr, pex, svex


def _dnka_eg(omega, wvno, b, rho, cosp, rsinp, sinpr, cossv, rsinsv,
             sinsvr, ex, exa, iwat):
    """Dunkin's matrix for the eigenfunction recursion (CPS 'sregn')."""
    ca = [[0j] * 5 for _ in range(5)]
    wvno2 = wvno * wvno
    om2 = omega * omega
    if iwat == 1:
        dfac = math.exp(-ex) if ex < 35.0 else 0.0
        ca[2][2] = dfac
        ca[0][0] = cosp
        ca[4][4] = cosp
        ca[0][1] = -rsinp / rho / om2
        ca[1][0] = -rho * sinpr * om2
        ca[1][1] = cosp
        ca[3][3] = cosp
        ca[3][4] = ca[0][1]
        ca[4][3] = ca[1][0]
    else:
        a0 = math.exp(-exa) if exa < 60.0 else 0.0
        cpcq = cosp * cossv
        cpy = cosp * sinsvr
        cpz = cosp * rsinsv
        cqw = cossv * sinpr
        cqx = cossv * rsinp
        xy = rsinp * sinsvr
        xz = rsinp * rsinsv
        wy = sinpr * sinsvr
        wz = sinpr * rsinsv
        rho2 = rho * rho
        gam = 2.0 * b * b * wvno2 / om2
        gam2 = gam * gam
        gamm1 = gam - 1.0
        gamm2 = gamm1 * gamm1
        cqww2 = cqw * wvno2
        cqxw2 = cqx / wvno2
        gg1 = gam * gamm1
        a0c = (2.0 + 0j) * (a0 + 0j - cpcq)
        xz2 = xz / wvno2
        gxz2 = gam * xz2
        g2xz2 = gam2 * xz2
        a0cgg1 = a0c * (gam + gamm1)
        wy2 = wy * wvno2
        g2wy2 = gamm2 * wy2
        g1wy2 = gamm1 * wy2
        temp = a0c * gg1 + g2xz2 + g2wy2
        ca[2][2] = a0 + temp + temp
        ca[0][0] = cpcq - temp
        ca[0][1] = (-cqx + wvno2 * cpy) / rho / om2
        temp = (0.5 + 0j) * a0cgg1 + gxz2 + g1wy2
        ca[0][2] = wvno * temp / rho / om2
        ca[0][3] = (-cqww2 + cpz) / rho / om2
        temp = wvno2 * (a0c + wy2) + xz
        ca[0][4] = -temp / rho2 / om2 / om2
        ca[1][0] = (-gamm2 * cqw + gam2 * cpz / wvno2) * rho * om2
        ca[1][1] = cpcq
        ca[1][2] = (gamm1 * cqww2 - gam * cpz) / wvno
        ca[1][3] = -wz
        ca[1][4] = ca[0][3]
        temp = (0.5 + 0j) * a0cgg1 * gg1 + gam2 * gxz2 + gamm2 * g1wy2
        ca[2][0] = -(2.0 + 0j) * temp * rho * om2 / wvno
        ca[2][1] = -wvno * (gam * cqxw2 - gamm1 * cpy) * (2.0 + 0j)
        ca[2][3] = -2.0 * ca[1][2]
        ca[2][4] = -2.0 * ca[0][2]
        ca[3][0] = (-gam2 * cqxw2 + gamm2 * cpy) * rho * om2
        ca[3][1] = -xy
        ca[3][2] = -0.5 * ca[2][1]
        ca[3][3] = ca[1][1]
        ca[3][4] = ca[0][1]
        temp = gamm2 * (a0c * gam2 + g2wy2) + gam2 * g2xz2
        ca[4][0] = -rho2 * om2 * om2 * temp / wvno2
        ca[4][1] = ca[3][0]
        ca[4][2] = -0.5 * ca[2][0]
        ca[4][3] = ca[1][0]
        ca[4][4] = ca[0][0]
    return [[v.real for v in row] for row in ca]


def _svup(omega, wvno, d, a, b, rho):
    """Compound vectors at every layer boundary, half-space up to surface."""
    mmax = len(d)
    cd = [[0.0] * 5 for _ in range(mmax)]
    exe = [0.0] * mmax
    gbr = _evalg(mmax - 1, d, a, b, rho, wvno, omega)
    cd[mmax - 1] = list(gbr)
    wvno2 = wvno * wvno
    exsum = 0.0
    for m in range(mmax - 2, -1, -1):
        xka = omega / a[m]
        xkb = omega / b[m] if b[m] > 0.01 else 0.0
        rp = (wvno2 - xka * xka) ** 0.5
        rsv = (wvno2 - xkb * xkb) ** 0.5
        p = rp * d[m]
        q = rsv * d[m]
        iwat = 1 if b[m] < 0.01 else 0
        (cosp, cossv, rsinp, rsinsv, sinpr, sinsvr, pex,
         svex) = _varsv(p, q, rp, rsv, d[m], iwat)
        ca = _dnka_eg(omega, wvno, b[m], rho[m], cosp, rsinp, sinpr,
                      cossv, rsinsv, sinsvr, pex, pex + svex, iwat)
        ee = [0.0] * 5
        for i in range(5):
            s = 0.0
            for j in range(5):
                s += cd[m + 1][j] * ca[j][i]
            ee[i] = s
        ee, exn = _normc(ee)
        exsum += pex + svex + exn
        exe[m] = exsum
        cd[m] = ee
    return cd, exe


def rayleigh_ellipticity(freqs_hz, thickness_m, vp_mps, vs_mps, rho_gcc,
                         dc=0.005):
    """H/V of the fundamental-mode Rayleigh wave for a layered model.

    freqs_hz   : ascending list of frequencies (Hz)
    thickness_m: layer thicknesses (m); the LAST entry is the half-space
                 (its thickness is ignored)
    vp_mps, vs_mps: P and S velocities (m/s), one per layer incl. half-space
    rho_gcc    : densities (g/cm3), one per layer incl. half-space

    Returns a list the same length as freqs_hz with the theoretical H/V
    value (None where the fundamental mode does not exist).
    """
    n = len(thickness_m)
    if n < 2 or len(vp_mps) != n or len(vs_mps) != n or len(rho_gcc) != n:
        raise ValueError("model arrays must all have the same length (>=2)")
    if any(v <= 0 for v in vs_mps):
        raise ValueError("Vs must be positive in every layer")
    d = [h / 1000.0 for h in thickness_m]
    a = [v / 1000.0 for v in vp_mps]
    b = [v / 1000.0 for v in vs_mps]
    rho = list(rho_gcc)
    # high frequency first => periods ascending (CPS convention)
    order = sorted(range(len(freqs_hz)), key=lambda i: -freqs_hz[i])
    periods = [1.0 / freqs_hz[i] for i in order]
    cs = _phase_velocities(periods, d, a, b, rho, dc)
    ell = [None] * len(periods)
    for k, cval in enumerate(cs):
        if cval <= 0.0:
            break
        omega = TWO_PI / periods[k]
        wvno = omega / cval
        try:
            cd, _exe = _svup(omega, wvno, d, a, b, rho)
            ur = cd[0][2] / cd[0][1]
            ell[k] = abs(ur)
        except (ZeroDivisionError, ValueError):
            ell[k] = None
    out = [None] * len(freqs_hz)
    for orig, val in zip(order, ell):
        out[orig] = val
    return out


# ----------------------------------------------------------------------
# Model seeding (automatic from the H/V result)
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# Misfit
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# Inversion driver
# ----------------------------------------------------------------------
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


def _build_inversion_log(res):
    L = []
    L.append("=" * 62)
    L.append("            1D HVSR INVERSION - RESULTS")
    L.append("=" * 62)
    L.append("Station          : %s" % res.station)
    L.append("Observed f0 / A0 : %.3f Hz / %.2f" % (res.f0_obs, res.a0_obs))
    L.append("Synthetic f0     : %.3f Hz" % res.f0_syn)
    L.append("Models tested    : %d" % res.n_models)
    L.append("Models accepted  : %d" % res.n_accepted)
    L.append("Best misfit      : %.4f (log10 H/V L2)" % (res.misfit or 0))
    if res.vs30:
        L.append("Vs30 (profile)   : %.0f m/s" % res.vs30)
        L.append("NEHRP site class : %s - %s" % (res.soil_class_nehrp[0],
                                                 res.soil_class_nehrp[1]))
        L.append("SNI site class   : %s - %s" % (res.soil_class_sni[0],
                                                 res.soil_class_sni[1]))
    L.append("")
    L.append("-" * 62)
    L.append(" LAYER   TOP(m)   BOTTOM(m)   Vs(m/s)   Vp(m/s)   rho(g/cc)  "
             "SOIL (NEHRP)")
    L.append("-" * 62)
    try:
        import hvsr_standards
    except Exception:
        hvsr_standards = None
    for lay in res.layers:
        soil = ""
        if hvsr_standards is not None:
            cls, _d = hvsr_standards.soil_class(lay["vs"])
            soil = "class " + cls
        bot = "inf" if lay["bottom"] is None or lay["thickness"] is None \
            else "%.1f" % lay["bottom"]
        L.append("  %3d     %6.1f  %8s   %7.1f  %7.1f   %6.2f    %s"
                 % (lay["layer"] + 1, lay["top"], bot, lay["vs"],
                    lay["vp"], lay["rho"], soil))
    L.append("")
    L.append("-" * 62)
    L.append(" UNCERTAINTY - P16 / P84 of the accepted ensemble "
             "(%d models)" % res.n_accepted)
    L.append("-" * 62)
    for lay in res.layers:
        if lay.get("vs_lo") is not None and lay.get("vs_hi") is not None:
            L.append("  layer %d: Vs = %.0f [%.0f - %.0f] m/s"
                     % (lay["layer"] + 1, lay["vs"], lay["vs_lo"],
                        lay["vs_hi"]))
        if lay.get("thk_lo") is not None and lay.get("thk_hi") is not None:
            L.append("           h  = %.1f [%.1f - %.1f] m"
                     % (lay["thickness"], lay["thk_lo"], lay["thk_hi"]))
    L.append("  misfit: best %.4f | median %.4f | P90 %.4f"
             % (res.misfit or 0, res.misfit_p50 or 0, res.misfit_p90 or 0))
    L.append("=" * 62)
    return L


def write_inversion_csv(path, res):
    """Save the inverted profile as a CSV."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("layer,top_m,bottom_m,thickness_m,Vs_mps,Vp_mps,"
                 "rho_gcc,soil_class,Vs30_mps,vs_p16,vs_p84,"
                 "thk_p16,thk_p84\n")
        try:
            import hvsr_standards
        except Exception:
            hvsr_standards = None
        for lay in res.layers:
            cls = ""
            if hvsr_standards is not None:
                cls = hvsr_standards.soil_class(lay["vs"])[0]
            bot = lay["bottom"] if lay["bottom"] is not None else ""
            thk = lay["thickness"] if lay["thickness"] is not None else ""
            lo = lay.get("vs_lo")
            hi = lay.get("vs_hi")
            tlo = lay.get("thk_lo")
            thi = lay.get("thk_hi")
            fh.write("%d,%.3f,%s,%s,%.2f,%.2f,%.3f,%s,%s,%s,%s,%s,%s\n"
                     % (lay["layer"] + 1, lay["top"], bot, thk, lay["vs"],
                        lay["vp"], lay["rho"], cls,
                        ("%.1f" % res.vs30) if res.vs30 else "",
                        ("%.1f" % lo) if lo is not None else "",
                        ("%.1f" % hi) if hi is not None else "",
                        ("%.1f" % tlo) if tlo is not None else "",
                        ("%.1f" % thi) if thi is not None else ""))


def write_inversion_report(path, res):
    """Save the plain-text inversion report."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(res.report_text + "\n")
