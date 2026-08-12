"""
hvsr_dsp_filters.py
===================
Digital filter design (pure standard library):

- butter_bandpass / bandpass_filter : Butterworth band-pass filter,
- _design_bandpass : shared design core (Butterworth / Chebyshev / Bessel
  analogues + bilinear transform), used with different analog prototypes,
- _filtfilt is applied from hvsr_dsp_lfilter.

Split out of hvsr_dsp.py.
"""


import cmath
import math
from hvsr_dsp_fft import TWO_PI
from hvsr_dsp_lfilter import _filtfilt

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
