"""
hvsr_inv_phasevel.py
====================
Phase-velocity dispersion computation for the layered-earth forward
model: the root-finding chain (_dltar4 -> _nevill -> _getsol ->
_gtsolh) with _dnka_real and _phase_velocities.

Split out of hvsr_inversion.py.
"""


import math
from hvsr_inv_forward import TWO_PI, _normc, _sign, _var

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
