"""
hvsr_dsp_fft.py
==============
FFT machinery and instrument-response math (pure standard library):

- fft / ifft / fft_real / rfft_magnitude : mixed-radix + Bluestein DFT,
  with _fft_radix2 / _bluestein_tables as the engine-room helpers,
- parse_paz / paz_response / paz_deconvolve : instrument poles & zeros.

Split out of hvsr_dsp.py.
"""


import cmath
import math

TWO_PI = 2.0 * math.pi

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
    """Smallest power of two greater than or equal to ``n`` (FFT sizing)."""
    m = 1
    while m < n:
        m <<= 1
    return m

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
