"""
hvsr_dsp.py
===========
Pure-standard-library digital signal processing primitives used by the
HVSR Analyzer.  No numpy / scipy / obspy -- everything below is written
from scratch on top of the Python standard library only.

Contents
--------
- fft / ifft          : Cooley-Tukey (radix-2) plus Bluestein for any length
- detrend_linear      : remove best-fit straight line
- demean              : remove the mean
- cosine_taper        : Tukey-style fractional taper
- butter_bandpass     : Butterworth bandpass designed via bilinear transform
- filtfilt            : zero-phase forward-backward IIR filtering
- classic_sta_lta     : STA/LTA transient detector
- decimate            : integer-factor decimation with anti-alias filter
- konno_ohmachi_smooth: Konno-Ohmachi spectral smoothing
- evaluate_pz         : SAC pole-zero (paz) response evaluation
"""

import math
import cmath
import os
from bisect import bisect_left
from functools import lru_cache

TWO_PI = 2.0 * math.pi


# ----------------------------------------------------------------------
# 1. FFT / IFFT (pure Python)
# ----------------------------------------------------------------------
def _fft_radix2(a, inverse):
    """Iterative in-place Cooley-Tukey FFT.  `a` must have length a power of 2."""
    n = len(a)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            a[i], a[j] = a[j], a[i]

    sign = 1.0 if inverse else -1.0
    length = 2
    while length <= n:
        half = length >> 1
        ang = sign * TWO_PI / length
        wlen = complex(math.cos(ang), math.sin(ang))
        for i in range(0, n, length):
            w = 1.0 + 0.0j
            end = i + half
            for j in range(i, end):
                u = a[j]
                v = a[j + half] * w
                a[j] = u + v
                a[j + half] = u - v
                w *= wlen
        length <<= 1
    return a


def _next_pow2(n):
    m = 1
    while m < n:
        m <<= 1
    return m


# Bluestein chirp tables are reused for every window of the same length:
# the chirp and its circular-conjugate FFT depend only on N.
_BLUESTEIN_TABLES = {}


def _bluestein_tables(n):
    """Cached (m, w, B) for the Bluestein FFT of length n (forward sign)."""
    tab = _BLUESTEIN_TABLES.get(n)
    if tab is not None:
        return tab
    m = _next_pow2(2 * n - 1)
    # Chirp: w[k] = exp(-i * pi * k^2 / n)  (forward sign)
    w = [cmath.exp(complex(0.0, -math.pi * (k * k % (2 * n)) / n))
         for k in range(n)]
    b_head = [w[k].conjugate() for k in range(n)]
    b_tail = [w[k].conjugate() for k in range(n - 1, 0, -1)]
    bw = b_head + [0j] * (m - 2 * n + 1) + b_tail
    B = _fft_radix2(bw, False)
    tab = (m, w, B)
    _BLUESTEIN_TABLES[n] = tab
    return tab


def _fft_bluestein(a, inverse):
    """Bluestein's chirp-z FFT -- works for any length N (not just powers of 2)."""
    n = len(a)
    if not inverse:
        m, w, B = _bluestein_tables(n)
    else:
        m = _next_pow2(2 * n - 1)
        sign = 1.0
        w = [cmath.exp(complex(0.0, sign * math.pi * (k * k % (2 * n)) / n))
             for k in range(n)]
        b_head = [w[k].conjugate() for k in range(n)]
        b_tail = [w[k].conjugate() for k in range(n - 1, 0, -1)]
        bw = b_head + [0j] * (m - 2 * n + 1) + b_tail
        B = _fft_radix2(bw, False)

    # a'[k] = a[k] * w[k], zero padded to m
    aw = [a[k] * w[k] for k in range(n)] + [0j] * (m - n)
    A = _fft_radix2(aw, False)
    C = [A[k] * B[k] for k in range(m)]
    c = _fft_radix2(C, True)
    inv_m = 1.0 / m
    return [c[k] * w[k] * inv_m for k in range(n)]


def fft(x):
    """Forward DFT of a real or complex sequence.  Returns a list of complex values."""
    a = [complex(v) for v in x]
    n = len(a)
    if n <= 1:
        return a
    if n & (n - 1) == 0:
        return _fft_radix2(a, False)
    return _fft_bluestein(a, False)


def ifft(x):
    """Inverse DFT (normalised by 1/N).  Returns a list of complex values."""
    a = [complex(v) for v in x]
    n = len(a)
    if n <= 1:
        return a
    if n & (n - 1) == 0:
        return [v / n for v in _fft_radix2(a, True)]
    return [v / n for v in _fft_bluestein(a, True)]


def fft_real(x):
    """FFT of a real sequence via one half-size complex FFT (even length).

    Roughly halves the radix-2 work for the window spectra used by the
    H/V pipeline; falls back to :func:`fft` for odd lengths.
    """
    n = len(x)
    if n < 4 or (n & 1):
        return fft(x)
    h = n // 2
    z = [complex(x[2 * i], x[2 * i + 1]) for i in range(h)]
    Z = fft(z)
    out = [0j] * n
    tw = TWO_PI / n
    for k in range(h):
        zk = Z[k]
        zk2 = Z[(h - k) % h]
        er = 0.5 * (zk.real + zk2.real)
        ei = 0.5 * (zk.imag - zk2.imag)
        o_r = 0.5 * (zk.imag + zk2.imag)
        o_i = 0.5 * (zk2.real - zk.real)
        ang = -tw * k
        wc = math.cos(ang)
        ws = math.sin(ang)
        wr = o_r * wc - o_i * ws
        wi = o_r * ws + o_i * wc
        out[k] = complex(er + wr, ei + wi)
        out[k + h] = complex(er - wr, ei - wi)
    return out


def rfft_magnitude(x):
    """One-sided (positive-frequency) magnitude spectrum of a real signal."""
    n = len(x)
    spec = fft_real(x)
    m = n // 2 + 1
    mags = []
    for k in range(m):
        if k == 0:
            mags.append(abs(spec[0]))
        elif n % 2 == 0 and k == n // 2:
            mags.append(abs(spec[n // 2]))
        else:
            mags.append(2.0 * abs(spec[k]))
    return mags


# ----------------------------------------------------------------------
# 2. Detrending / windowing
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# 3. Butterworth bandpass (bilinear transform, zero phase)
# ----------------------------------------------------------------------
def _poly_mul(p, q):
    """Multiply two polynomials given as coefficient lists (index 0 = highest power)."""
    if not p or not q:
        return [0.0]
    out = [0.0] * (len(p) + len(q) - 1)
    for i, pi in enumerate(p):
        for j, qj in enumerate(q):
            out[i + j] += pi * qj
    return out


def _poly_add(p, q):
    """Add two polynomials (lists of coefficients, index 0 = highest power)."""
    n = max(len(p), len(q))
    p2 = [0.0] * (n - len(p)) + list(p)
    q2 = [0.0] * (n - len(q)) + list(q)
    return [a + b for a, b in zip(p2, q2)]


def _butter_analog_den(order):
    """Denominator polynomial of a normalised Butterworth lowpass of given order."""
    # H(s) = 1 / prod(s - p_k), poles in the left half of the s-plane
    den = [1.0]
    for k in range(order):
        theta = math.pi * (2 * k + order + 1) / (2 * order)
        p = complex(math.cos(theta), math.sin(theta))
        # (s - p)  ->  coefficients [1, -p]
        poly = [1.0, -p]
        den = _poly_mul(den, poly)
    return den


def _lp2bp(poly, w0, bw):
    """Lowpass->bandpass transform on polynomial coefficients.

    poly[k] is the coefficient of s^(order - k) (index 0 = highest power).
    Replaces s with (s^2 + w0^2) / (bw * s) and multiplies through by
    (bw*s)^order so the result is again a plain polynomial.
    """
    order = len(poly) - 1
    result = [0.0]
    s2 = [1.0, 0.0, w0 * w0]
    for k in range(order + 1):
        ck = poly[k]
        if abs(ck) < 1e-300:
            continue
        # monomial s^(order-k) -> (s^2 + w0^2)^(order-k) * (bw*s)^k / (bw*s)^order
        p1 = [1.0]
        for _ in range(order - k):
            p1 = _poly_mul(p1, s2)
        p2 = [1.0]
        for _ in range(k):
            p2 = _poly_mul(p2, [bw, 0.0])
        term = _poly_mul(p1, p2)
        result = _poly_add(result, [ck * v for v in term])
    return result


def _bilinear(poly, ref_order=None):
    """Bilinear transform s = (z-1)/(z+1) on a polynomial, returning digital form.

    poly[k] is the coefficient of s^(deg - k) (index 0 = highest power).
    Each monomial s^m maps to (z-1)^m / (z+1)^m; the result is multiplied
    through by (z+1)^ref_order so numerator and denominator share a common
    (z+1) power when combined into one rational function.
    """
    deg = len(poly) - 1
    order = ref_order if ref_order is not None else deg
    result = [0.0]
    zm1 = [1.0, -1.0]
    zp1 = [1.0, 1.0]
    for k in range(deg + 1):
        ck = poly[k]
        if abs(ck) < 1e-300:
            continue
        m = deg - k  # power of s for this coefficient
        p = [1.0]
        for _ in range(m):
            p = _poly_mul(p, zm1)
        for _ in range(order - m):
            p = _poly_mul(p, zp1)
        result = _poly_add(result, [ck * v for v in p])
    return result


def butter_bandpass(x, f_low, f_high, fs, order=5):
    """Zero-phase Butterworth bandpass filter of the real signal x.

    The filter is designed from scratch: analog prototype poles -> lowpass
    to bandpass mapping -> bilinear transform -> direct-form filtering with
    forward/backward passes for zero phase.
    """
    nyq = 0.5 * fs
    if f_low <= 0.0:
        f_low = 0.001
    if f_high >= nyq:
        f_high = nyq * 0.999
    if f_low >= f_high:
        raise ValueError("f_low must be smaller than f_high")

    # Pre-warp band edges (bilinear)
    w1 = math.tan(math.pi * f_low / fs)
    w2 = math.tan(math.pi * f_high / fs)
    w0 = math.sqrt(w1 * w2)
    bw = w2 - w1

    # Analog lowpass prototype (gain 1)
    den = _butter_analog_den(order)

    # Lowpass -> bandpass: numerator (bw*s)^order, denominator transformed
    den_bp = _lp2bp(den, w0, bw)
    num_bp = [bw ** order] + [0.0] * order  # coefficient of s^order is bw^order

    # Bilinear transform (numerator shares the denominator's (z+1) power)
    bd = _bilinear(den_bp)
    bn = _bilinear(num_bp, ref_order=len(den_bp) - 1)

    # Normalise so that a0 (first coefficient) == 1; the design is conjugate
    # symmetric so the imaginary parts are pure floating-point noise.
    a0 = bd[0]
    if abs(a0) < 1e-300:
        raise ValueError("filter design failed")
    b = [float((v / a0).real) for v in bn]
    a = [float((v / a0).real) for v in bd]

    # For a bandpass both polynomials start with a 1.0; the numerator order
    # may be lower than the denominator order -> pad with leading zeros.
    if len(b) < len(a):
        b = [0.0] * (len(a) - len(b)) + b

    return _filtfilt(b, a, x)


def _chebyshev_analog_den(order, ripple_db=0.5):
    """Denominator polynomial of a normalised Chebyshev type-I lowpass.

    Poles lie on an ellipse with the given passband ripple (dB):
      theta_k = pi*(2k+1)/(2n),  phi = (1/n)*asinh(1/eps)
      p_k = -sinh(phi)*sin(theta_k) + i*cosh(phi)*cos(theta_k)
    """
    eps = math.sqrt(10.0 ** (0.1 * ripple_db) - 1.0)
    phi = math.asinh(1.0 / eps) / order
    den = [1.0]
    for k in range(order):
        theta = math.pi * (2 * k + 1) / (2 * order)
        p = complex(-math.sinh(phi) * math.sin(theta),
                    math.cosh(phi) * math.cos(theta))
        den = _poly_mul(den, [1.0, -p])
    return den


def _bessel_analog_den(order):
    """Reverse Bessel polynomial theta_n(s) (maximally flat group delay).

    Coefficients (index 0 = highest power s^n):
      a_k = (2n-k)! / (2^(n-k) * k! * (n-k)!),  k = 0..n
    """
    n = order
    coeff = [0.0] * (n + 1)
    for k in range(n + 1):
        num = math.factorial(2 * n - k)
        denom = (2 ** (n - k)) * math.factorial(k) * math.factorial(n - k)
        coeff[k] = num / denom  # coefficient of s^(n-k)
    return coeff


def _freqz_point(b, a, f, fs):
    """Complex frequency response H(e^jw) at one frequency f (Hz)."""
    z = cmath.exp(complex(0.0, -TWO_PI * f / fs))
    num = 0.0 + 0.0j
    for c in b:
        num = num * z + c
    den = 0.0 + 0.0j
    for c in a:
        den = den * z + c
    return num / den if abs(den) > 1e-300 else 1.0 + 0.0j


def _design_bandpass(f_low, f_high, fs, order, kind, ripple_db):
    """Design a bandpass IIR via bilinear transform for a given prototype.

    Returns (b, a) digital coefficients with unity gain at the centre
    frequency f0 = sqrt(f_low*f_high) (so all filter types are directly
    comparable in the GUI).
    """
    nyq = 0.5 * fs
    if f_low <= 0.0:
        f_low = 0.001
    if f_high >= nyq:
        f_high = nyq * 0.999
    if f_low >= f_high:
        raise ValueError("f_low must be smaller than f_high")

    w1 = math.tan(math.pi * f_low / fs)
    w2 = math.tan(math.pi * f_high / fs)
    w0 = math.sqrt(w1 * w2)
    bw = w2 - w1

    if kind == "butterworth":
        den = _butter_analog_den(order)
        num_lp = 1.0          # unity DC gain
    elif kind == "chebyshev_i":
        den = _chebyshev_analog_den(order, ripple_db)
        # DC gain = 1 / prod(-p_k); normalise so H(0) = 1
        d0 = den[0]
        if abs(d0) < 1e-300:
            raise ValueError("filter design failed")
        num_lp = 1.0 / d0
    elif kind == "bessel":
        den = _bessel_analog_den(order)
        d0 = den[0]
        if abs(d0) < 1e-300:
            raise ValueError("filter design failed")
        num_lp = 1.0 / d0
    else:
        raise ValueError("unknown filter kind: %s" % kind)

    den_bp = _lp2bp(den, w0, bw)
    num_bp = [num_lp * (bw ** order)] + [0.0] * order

    bd = _bilinear(den_bp)
    bn = _bilinear(num_bp, ref_order=len(den_bp) - 1)

    a0 = bd[0]
    if abs(a0) < 1e-300:
        raise ValueError("filter design failed")
    b = [float((v / a0).real) for v in bn]
    a = [float((v / a0).real) for v in bd]
    if len(b) < len(a):
        b = [0.0] * (len(a) - len(b)) + b

    # normalise the passband peak to unity at the geometric centre
    fc = math.sqrt(f_low * f_high)
    g = abs(_freqz_point(b, a, fc, fs))
    if g > 1e-12:
        b = [v / g for v in b]
    return b, a


def bandpass_filter(x, f_low, f_high, fs, kind="butterworth",
                    order=5, ripple_db=0.5):
    """Zero-phase band-pass filter with selectable prototype.

    kind:
      'butterworth'  maximally flat amplitude (default, recommended)
      'chebyshev_i'  sharper roll-off with passband ripple (ripple_db)
      'bessel'       maximally flat group delay (no ringing)

    All designs are normalised to unity gain at the band centre and
    applied zero-phase (forward/backward).
    """
    b, a = _design_bandpass(f_low, f_high, fs, order, kind, ripple_db)
    return _filtfilt(b, a, x)


def _lfilter(b, a, x):
    """Direct-form I recursive filter: y[n] = sum(b[k] x[n-k]) - sum(a[k] y[n-k])."""
    nb = len(b)
    na = len(a)
    n = len(x)
    y = [0.0] * n
    for i in range(n):
        acc = 0.0
        for k in range(nb):
            j = i - k
            if j >= 0:
                acc += b[k] * x[j]
        for k in range(1, na):
            j = i - k
            if j >= 0:
                acc -= a[k] * y[j]
        y[i] = acc
    return y


def _lfilter_zi(b, a):
    """Steady-state initial conditions for _lfilter_ic.

    Computed directly from the steady-state equations of the direct-form-II
    transposed recursion: with a constant input, the state is constant and
    the output is y_ss = H(1) * input.  This is consistent with _lfilter_ic
    by construction.
    """
    n = max(len(a), len(b))
    be = list(b) + [0.0] * (n - len(b))
    ae = list(a) + [0.0] * (n - len(a))
    den0 = sum(ae)
    yss = sum(be) / den0 if abs(den0) > 1e-300 else 0.0
    m = n - 1
    z = [0.0] * m
    for k in range(m - 1, -1, -1):
        z[k] = be[k + 1] - ae[k + 1] * yss
        if k + 1 < m:
            z[k] += z[k + 1]
    return z


def _lfilter_ic(b, a, x, zi):
    """IIR filter (direct form II transpose) with an initial state vector."""
    n = max(len(a), len(b))
    be = list(b) + [0.0] * (n - len(b))
    ae = list(a) + [0.0] * (n - len(a))
    m = n - 1
    z = list(zi) + [0.0] * (m - len(zi))
    y = [0.0] * len(x)
    for i, xn in enumerate(x):
        yn = be[0] * xn + z[0]
        y[i] = yn
        for k in range(m - 1):
            z[k] = be[k + 1] * xn - ae[k + 1] * yn + z[k + 1]
        z[m - 1] = be[m] * xn - ae[m] * yn
    return y


def _filtfilt(b, a, x):
    """Zero-phase filtering with steady-state initial conditions.

    Uses scipy-style lfilter_zi initial conditions plus constant edge
    padding, so neither pass injects a step-response transient.  The pad
    (3 * filter order) is trimmed after the two passes.
    """
    n = len(x)
    if n < 2:
        return list(x)
    edge = max(len(a), len(b))
    pad = max(3 * edge, n // 3)
    if pad > n // 2:
        pad = max(1, n // 2)
    # Even (mirror) reflection padding keeps the spectral character of the
    # signal at the edges, so the filter state does not relax into a large
    # in-band transient at the padding junction.
    front = [x[k] for k in range(pad, 0, -1)]
    back = [x[n - 2 - k] for k in range(pad)]
    padded = front + list(x) + back
    zi = _lfilter_zi(b, a)
    y1 = _lfilter_ic(b, a, padded, [v * front[0] for v in zi])
    y2 = _lfilter_ic(b, a, list(reversed(y1)), [v * y1[-1] for v in zi])
    y3 = list(reversed(y2))
    return y3[pad:pad + n]


# ----------------------------------------------------------------------
# 4. STA/LTA transient detector
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# 5. Decimation (integer factor, with anti-alias low-pass)
# ----------------------------------------------------------------------
def decimate(x, factor):
    """Integer-factor decimation with a simple anti-alias box filter."""
    if factor <= 1:
        return list(x)
    out = []
    for i in range(0, len(x) - factor + 1, factor):
        out.append(sum(x[i:i + factor]) / factor)
    return out


# ----------------------------------------------------------------------
# Worker-process count (parallel sweeps)
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# 6. Konno-Ohmachi spectral smoothing
# ----------------------------------------------------------------------
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


@lru_cache(maxsize=32)
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


# ----------------------------------------------------------------------
# 7. SAC pole-zero (paz) response evaluation
# ----------------------------------------------------------------------
def parse_paz(text):
    """Parse a SAC pole-zero file (ZEROS / POLES / CONSTANT)."""
    zeros = []
    poles = []
    constant = 1.0
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    i = 0
    while i < len(lines):
        tok = lines[i].upper().split()
        if tok and tok[0] == "ZEROS":
            count = int(tok[1])
            i += 1
            for _ in range(count):
                parts = lines[i].split()
                zeros.append(complex(float(parts[0]), float(parts[1])))
                i += 1
            continue
        if tok and tok[0] == "POLES":
            count = int(tok[1])
            i += 1
            for _ in range(count):
                parts = lines[i].split()
                poles.append(complex(float(parts[0]), float(parts[1])))
                i += 1
            continue
        if tok and tok[0] == "CONSTANT":
            constant = float(tok[1])
            i += 1
            continue
        i += 1
    return {"zeros": zeros, "poles": poles, "constant": constant}


def paz_response(freq, paz):
    """Complex instrument response H(f) from a paz dict at frequency `f` (Hz)."""
    s = complex(0.0, TWO_PI * freq)
    num = paz["constant"]
    for z in paz["zeros"]:
        num *= (s - z)
    den = 1.0 + 0.0j
    for p in paz["poles"]:
        den *= (s - p)
    if abs(den) < 1e-300:
        return 1.0 + 0.0j
    return num / den


def paz_deconvolve(x, fs, paz, low=0.1, high=30.0):
    """Remove instrument response in the frequency domain (spectral division).

    A mild spectral shaping keeps the correction stable far outside the
    analysis band, where the response model is unreliable.
    """
    n = len(x)
    if n < 16:
        return list(x)
    m = _next_pow2(2 * n)  # zero-pad for linear filtering
    spec = fft(list(x) + [0.0] * (m - n))
    out = []
    for k in range(m):
        f = k * (fs / m)
        resp = paz_response(f, paz)
        if abs(resp) < 1e-12:
            out.append(0.0 + 0.0j)
            continue
        # shape: full correction inside (low, high), taper to 1 outside
        shape = 1.0
        if f < low:
            shape = max(0.05, f / low)
        elif f > high:
            shape = max(0.05, (2.0 * fs) / (f + fs))
        out.append(spec[k] / resp * shape)
    y = ifft(out)
    return [y[i].real for i in range(n)]
