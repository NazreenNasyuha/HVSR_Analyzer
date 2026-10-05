"""
test_engine.py
==============
Unit tests for the pure-standard-library HVSR Analyzer engine.
Run with:  python test_engine.py
"""

import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from hvsr_dsp import (fft, ifft, detrend_linear, cosine_taper,
                      butter_bandpass, konno_ohmachi_smooth,
                      parse_paz, paz_response, decimate, classic_sta_lta)
from hvsr_io import read_three_channel, auto_load, DataError
from hvsr_engine import (preprocess, analyze, auto_tune, log_frequencies,
                         sesame_score, write_target_file, write_report_file,
                         coherence, hv_vs_time, hv_vs_azimuth, trim_seconds,
                         pick_secondary_peak, azimuthal_directivity)
from chart_render import write_png, HvsrChart

try:
    from make_sample_data import make_station
except Exception:  # pragma: no cover
    make_station = None


def _dft(x):
    """Reference brute-force DFT for small inputs."""
    n = len(x)
    return [sum(complex(v) * complex(math.cos(-2 * math.pi * k * i / n),
                                     math.sin(-2 * math.pi * k * i / n))
                for i, v in enumerate(x)) for k in range(n)]


class TestFft(unittest.TestCase):
    def test_radix2_matches_dft(self):
        x = [1.0, -2.0, 3.0, 4.0, -1.0, 0.5, 2.0, 3.0]
        a = fft(x)
        b = _dft(x)
        for ca, cb in zip(a, b):
            self.assertAlmostEqual(abs(ca - cb), 0.0, places=8)

    def test_bluestein_matches_dft(self):
        x = [1.0, -2.0, 3.0, 4.0, -1.0]  # length 5, not a power of two
        a = fft(x)
        b = _dft(x)
        for ca, cb in zip(a, b):
            self.assertAlmostEqual(abs(ca - cb), 0.0, places=8)

    def test_ifft_roundtrip(self):
        x = [1.0, -2.0, 3.0, 4.0, -1.0, 0.5, 2.0, 3.0]
        y = ifft(fft(x))
        for v, w in zip(x, y):
            self.assertAlmostEqual(abs(complex(v) - w), 0.0, places=8)


class TestDetrend(unittest.TestCase):
    def test_linear(self):
        x = [3.0 + 2.0 * t for t in range(50)]
        y = detrend_linear(x)
        self.assertLess(max(abs(v) for v in y), 1e-9)


class TestFilter(unittest.TestCase):
    def test_bandpass_keeps_inband_sine(self):
        fs = 200.0
        t = [i / fs for i in range(4000)]
        x = [math.sin(2 * math.pi * 2.0 * tt) for tt in t]
        y = butter_bandpass(x, 0.5, 10.0, fs, order=5)
        # amplitude after transients should stay near 1.0
        mid = y[1500:2500]
        amp = (max(mid) - min(mid)) / 2.0
        self.assertGreater(amp, 0.85)
        self.assertLess(amp, 1.15)

    def test_bandpass_attenuates_outband(self):
        fs = 200.0
        t = [i / fs for i in range(4000)]
        x = [math.sin(2 * math.pi * 40.0 * tt) for tt in t]
        y = butter_bandpass(x, 0.5, 10.0, fs, order=5)
        self.assertLess(max(abs(v) for v in y[500:]), 0.1)


class TestKonnoOhmachi(unittest.TestCase):
    def test_flat_spectrum_stays_flat(self):
        freqs = [f for f in (0.5 + 0.05 * k for k in range(400))]
        mag = [1.0] * len(freqs)
        targets = [0.5 * (20.0 / 0.5) ** (k / 99.0) for k in range(100)]
        out = konno_ohmachi_smooth(mag, freqs, targets, 40.0)
        for v in out:
            self.assertAlmostEqual(v, 1.0, delta=0.1)


class TestPaz(unittest.TestCase):
    def test_parse_and_eval(self):
        text = "ZEROS 2\n0 0\n0 0\nPOLES 2\n-71.1766 0\n-13.8664 0\nCONSTANT 167.742"
        paz = parse_paz(text)
        self.assertEqual(len(paz["zeros"]), 2)
        self.assertEqual(len(paz["poles"]), 2)
        resp = paz_response(1.0, paz)
        self.assertGreater(abs(resp), 0.0)


class TestStaLta(unittest.TestCase):
    def test_transient_detected(self):
        x = [0.01] * 3000
        for i in range(1500, 1515):
            x[i] = 10.0
        cft = classic_sta_lta(x, 100, 1000)
        self.assertGreater(max(cft), 5.0)


class TestDecimate(unittest.TestCase):
    def test_length(self):
        x = list(range(100))
        y = decimate(x, 4)
        self.assertEqual(len(y), 25)
        self.assertAlmostEqual(y[0], 1.5)


class TestIo(unittest.TestCase):
    def _write(self, path, content):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def test_read_three_channel(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "st.csv")
            self._write(p, "# comment\nfs=100\nZ,N,E\n1,2,3\n4,5,6\n7,8,9\n")
            data = read_three_channel(p)
            self.assertEqual(data.z, [1.0, 4.0, 7.0])
            self.assertEqual(data.n, [2.0, 5.0, 8.0])
            self.assertEqual(data.e, [3.0, 6.0, 9.0])
            self.assertAlmostEqual(data.fs, 100.0)

    def test_missing_rate_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "st.csv")
            self._write(p, "1,2,3\n4,5,6\n")
            with self.assertRaises(DataError):
                read_three_channel(p)

    def test_auto_load_three_files(self):
        with tempfile.TemporaryDirectory() as d:
            pz = os.path.join(d, "st_Z.csv")
            pn = os.path.join(d, "st_N.csv")
            pe = os.path.join(d, "st_E.csv")
            for p, v in ((pz, 1.0), (pn, 2.0), (pe, 3.0)):
                body = "\n".join(["%.0f" % v] * 5)
                self._write(p, "fs=10\n" + body + "\n")
            data = auto_load([pz, pn, pe])
            self.assertEqual(data.z, [1.0] * 5)
            self.assertEqual(data.n, [2.0] * 5)
            self.assertEqual(data.e, [3.0] * 5)


class TestAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.z, cls.n, cls.e = make_station(duration=300.0, fs=100.0, f0=2.0, seed=7)
        from hvsr_io import ThreeChannel
        cls.data = ThreeChannel(cls.z, cls.n, cls.e, 100.0)

    def test_recovers_known_f0(self):
        clean, _meta = preprocess(self.data, f_low=0.2, f_high=20.0)
        res = analyze(clean, w_len=30.0, rejection=1.5, fmin=0.5, fmax=20.0)
        self.assertGreater(res.n_windows_accepted, 0)
        self.assertAlmostEqual(res.f0, 2.0, delta=0.3)
        self.assertGreater(res.a0, 1.5)
        self.assertGreater(res.sigma_f, 0.0)

    def test_sesame_score_range(self):
        clean, _ = preprocess(self.data)
        res = analyze(clean, w_len=30.0)
        score = sesame_score(res.sesame)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 6)

    def test_auto_tune_runs(self):
        clean, _ = preprocess(self.data)
        res, w, r = auto_tune(clean, fmin=0.5, fmax=20.0)
        self.assertGreaterEqual(w, 20.0)
        self.assertGreater(res.n_windows_accepted, 0)

    def test_exports(self):
        with tempfile.TemporaryDirectory() as d:
            clean, _ = preprocess(self.data)
            res = analyze(clean, w_len=30.0)
            tp = os.path.join(d, "out.target")
            rp = os.path.join(d, "report.txt")
            write_target_file(tp, res.freqs, res.mean, res.low, res.high, res.f0)
            write_report_file(rp, res)
            self.assertTrue(os.path.getsize(tp) > 100)
            self.assertTrue(os.path.getsize(rp) > 100)


class TestChart(unittest.TestCase):
    def test_png_written(self):
        with tempfile.TemporaryDirectory() as d:
            chart = HvsrChart(400, 300)
            freqs = log_frequencies(0.5, 20.0, 200)
            import math
            mean = [1.0 + 2.0 * math.exp(-((math.log(f) - math.log(2.0)) ** 2) / 0.2)
                    for f in freqs]
            low = [0.7 * m for m in mean]
            high = [1.3 * m for m in mean]
            chart.draw_hvsr(freqs, mean, low, high, 2.0, 3.0, station="TEST")
            p = os.path.join(d, "chart.png")
            chart.save_png(p)
            self.assertGreater(os.path.getsize(p), 500)
            # PNG signature check
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")


class TestCoherenceAndMaps(unittest.TestCase):
    """Tests for the signal-analysis helpers added for the GUI previews:
    coherence(), hv_vs_time(), hv_vs_azimuth() and trim_seconds()."""

    @classmethod
    def setUpClass(cls):
        from hvsr_io import ThreeChannel
        fs = 100.0
        n = 6000
        t = [i / fs for i in range(n)]
        # 2 Hz tone on Z and N (shared), 5 Hz tone on E (different)
        cls.z = [math.sin(2 * math.pi * 2.0 * x) for x in t]
        cls.nch = [math.sin(2 * math.pi * 2.0 * x + 0.3) for x in t]
        cls.e = [math.sin(2 * math.pi * 5.0 * x) for x in t]
        cls.fs = fs
        cls.data = ThreeChannel(cls.z, cls.nch, cls.e, fs, "coh")

    def test_coherence_shared_tone_high(self):
        f, c = coherence(self.z, self.nch, self.fs, 30.0)
        idx = min(range(len(f)), key=lambda k: abs(f[k] - 2.0))
        self.assertGreater(c[idx], 0.9)

    def test_coherence_orthogonal_tone_low(self):
        f, c = coherence(self.z, self.e, self.fs, 30.0)
        idx = min(range(len(f)), key=lambda k: abs(f[k] - 2.0))
        self.assertLess(c[idx], 0.5)

    def test_coherence_returns_grid(self):
        f, c = coherence(self.z, self.nch, self.fs, 30.0)
        self.assertEqual(len(f), len(c))
        self.assertGreater(len(f), 10)
        for v in c:
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_hv_vs_time_shape(self):
        freqs = log_frequencies(0.1, 40.0, 24)
        times, fgrid, grid = hv_vs_time(self.data, 30.0, freqs=freqs,
                                        b_value=40.0, combo="geometric",
                                        smoothing="konno_ohmachi",
                                        smooth_width=40.0)
        self.assertEqual(len(times), len(grid))
        self.assertGreater(len(times), 1)
        for row in grid:
            self.assertEqual(len(row), len(freqs))
        # resonance near 2 Hz should appear in the map
        flat = [v for row in grid for v in row if v == v]
        self.assertTrue(flat)
        self.assertGreater(max(flat), 1.0)

    def test_hv_vs_azimuth_shape(self):
        freqs = log_frequencies(0.1, 40.0, 24)
        azi, fgrid, grid = hv_vs_azimuth(self.data, 30.0, freqs=freqs,
                                         b_value=40.0, combo="geometric",
                                         smoothing="konno_ohmachi",
                                         smooth_width=40.0)
        self.assertEqual(len(azi), len(grid))
        self.assertGreater(len(azi), 2)
        for row in grid:
            self.assertEqual(len(row), len(freqs))
        self.assertEqual(azi[0], 0.0)
        self.assertLessEqual(azi[-1], 180.0)

    def test_trim_seconds(self):
        from hvsr_io import ThreeChannel
        tdata = ThreeChannel([1.0] * 5000, [1.0] * 5000, [1.0] * 5000,
                             100.0, "trim")
        short = trim_seconds(tdata, 0.0, 10.0)
        self.assertAlmostEqual(short.duration, 10.0, places=1)
        self.assertEqual(short.n_samples, 1000)
        # identity when longer than the signal
        same = trim_seconds(tdata, 0.0, 999.0)
        self.assertEqual(same.n_samples, 5000)

    def test_azimuthal_directivity_identifies_peak_azimuth(self):
        azimuths = [0.0, 45.0, 90.0, 135.0]
        freqs = [0.5, 1.0, 2.0, 4.0, 8.0]
        # Azimuth 45 deg has peak amplification at 2.0 Hz
        grid = [
            [1.0, 1.1, 1.2, 1.0, 0.9],
            [1.0, 1.3, 3.5, 1.2, 0.9],  # Peak at 45 deg, 2 Hz
            [1.0, 1.0, 1.5, 1.1, 0.8],
            [1.0, 1.2, 1.8, 1.0, 0.9],
        ]
        res = azimuthal_directivity(azimuths, freqs, grid, f0=2.0)
        self.assertEqual(res["peak_azimuth"], 45.0)
        self.assertAlmostEqual(res["a_max"], 3.5, places=2)
        self.assertGreater(res["directivity_ratio"], 1.5)
        self.assertIn("directivity", res["description"].lower())


class TestSecondaryPeakAndAttributes(unittest.TestCase):
    """Tests for multi-peak detection and result object attributes."""

    def test_pick_secondary_peak_detects_distinct_resonance(self):
        freqs = [0.2 * (1.1 ** k) for k in range(50)]
        # Curve with f0 ~ 1.5 Hz and secondary peak f1 ~ 5.0 Hz
        amps = []
        for f in freqs:
            a0 = 3.0 * math.exp(-0.5 * ((math.log(f / 1.5) / 0.2) ** 2))
            a1 = 2.2 * math.exp(-0.5 * ((math.log(f / 5.0) / 0.2) ** 2))
            amps.append(1.0 + a0 + a1)
        f1, a1 = pick_secondary_peak(freqs, amps, f0=1.5, a0=4.0, fmin=0.2, fmax=10.0)
        self.assertGreater(f1, 4.0)
        self.assertLess(f1, 6.0)
        self.assertGreater(a1, 2.5)

    def test_pick_secondary_peak_none_when_unimodal(self):
        freqs = [0.5 * (1.1 ** k) for k in range(40)]
        amps = [1.0 + 3.0 * math.exp(-0.5 * ((math.log(f / 2.0) / 0.2) ** 2))
                for f in freqs]
        f1, a1 = pick_secondary_peak(freqs, amps, f0=2.0, a0=4.0, fmin=0.5, fmax=10.0)
        self.assertEqual(f1, 0.0)
        self.assertEqual(a1, 0.0)

    def test_result_attributes_populated(self):
        if make_station is None:
            return
        z, n, e = make_station(duration=60.0, fs=100.0, f0=2.0)
        from hvsr_io import ThreeChannel
        data = ThreeChannel(z, n, e, 100.0, "syn_meta")
        res = analyze(data, w_len=20.0, fmin=0.5, fmax=10.0, b_value=40.0, taper=0.05)
        self.assertEqual(res.rejection, 1.5)
        self.assertEqual(res.fmin, 0.5)
        self.assertEqual(res.fmax, 10.0)
        self.assertEqual(res.b_value, 40.0)
        self.assertEqual(res.taper, 0.05)
        self.assertTrue(hasattr(res, "f1"))
        self.assertTrue(hasattr(res, "a1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
