"""
hvsr_dsp_lfilter.py
===================
Applying digital filters (pure standard library):

- _filtfilt : zero-phase forward-backward filtering,
- _lfilter / _lfilter_zi / _lfilter_ic : the direct-form II transposed
  filter loop with computed initial conditions.

Split out of hvsr_dsp.py.
"""


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
