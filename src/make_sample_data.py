"""
make_sample_data.py
===================
Generates synthetic 3-component microtremor data with a KNOWN resonance
at 2 Hz in the horizontal components.  Useful for verifying that the HVSR
engine recovers the expected fundamental frequency.

Output: sample_data/station_A.csv  (columns: Z N E)
"""

import cmath
import math
import os
import random


def _bandpass_resonator(x, f0, q, fs):
    """Second-order bandpass resonator with poles placed exactly at f0.

    z-plane poles: z = r * exp(+/-i*w0) with r = 1 - sin(w0)/(2q); zeros at
    DC and Nyquist.  The output is normalized so the peak gain at f0 is 1.
    """
    w0 = 2.0 * math.pi * f0 / fs
    alpha = math.sin(w0) / (2.0 * q)
    r = 1.0 - alpha
    b0 = 1.0
    b2 = -1.0
    a1 = -2.0 * r * math.cos(w0)
    a2 = r * r

    # numerical peak gain at w0 (for normalization)
    jw = cmath.exp(complex(0.0, w0))
    num = b0 + b2 * jw ** -2
    den = 1.0 + a1 * jw ** -1 + a2 * jw ** -2
    gain = abs(num / den)
    if gain < 1e-12:
        gain = 1.0

    # Scale the forward (numerator) coefficients only -- scaling the whole
    # right-hand side would move the poles and destroy the resonance.
    b0 = b0 / gain
    b2 = b2 / gain
    out = [0.0] * len(x)
    for i in range(len(x)):
        x0 = x[i]
        x2 = x[i - 2] if i >= 2 else 0.0
        y1 = out[i - 1] if i >= 1 else 0.0
        y2 = out[i - 2] if i >= 2 else 0.0
        out[i] = b0 * x0 + b2 * x2 - a1 * y1 - a2 * y2
    return out


def make_station(duration=600.0, fs=100.0, f0=2.0, seed=42):
    """Return (z, n, e) lists of synthetic noise with a horizontal resonance.

    - vertical: flat white noise (amplitude ~1), no resonance
    - horizontal: clear resonance at f0 with peak H/V ~4, plus a small floor
    """
    rng = random.Random(seed)
    n = int(duration * fs)
    noise = [rng.gauss(0.0, 1.0) for _ in range(n)]

    z = list(noise)

    h_raw = _bandpass_resonator(noise, f0, 5.0, fs)
    n_comp = [4.0 * h_raw[i] + 0.10 * noise[i] for i in range(n)]
    e_comp = [4.5 * h_raw[i] + 0.10 * noise[i] for i in range(n)]

    return z, n_comp, e_comp


def write_station(folder, name="station_A", duration=600.0, fs=100.0, f0=2.0, seed=42):
    """Generate the synthetic station and write it as a 3-column CSV into
    ``folder``; returns the path to the Z component file."""
    os.makedirs(folder, exist_ok=True)
    z, n, e = make_station(duration, fs, f0, seed)
    path = os.path.join(folder, name + ".csv")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# synthetic 3-component microtremor, fs=%.0f Hz, f0=%.1f Hz\n" % (fs, f0))
        fh.write("fs=%.1f\n" % fs)
        fh.write("Z,N,E\n")
        for i in range(len(z)):
            fh.write("%.6f,%.6f,%.6f\n" % (z[i], n[i], e[i]))
    return path


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "sample_data")
    p = write_station(out)
    print("Sample data written to:", p)
    print("Open it in the app, or load '%s'." % p)
