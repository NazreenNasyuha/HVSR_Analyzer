"""
hvsr_inv_ellipticity.py
=======================
Rayleigh-wave ellipticity computation: the _dnka_eg / _evalg / _varsv /
_svup chain and the public rayleigh_ellipticity function that combines
phase velocities with the ellipticity branch.

Split out of hvsr_inversion.py.
"""


import math
from hvsr_inv_forward import TWO_PI, _normc
from hvsr_inv_phasevel import _phase_velocities

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
