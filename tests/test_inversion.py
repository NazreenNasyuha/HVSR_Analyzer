"""
test_inversion.py
=================
Tests for the new 1D inversion feature set:

- the from-scratch Rayleigh ellipticity forward model (CPS surf96 /
  swegn96 port) against analytic half-space and quarter-wavelength
  resonance results,
- the Monte-Carlo 1D inversion recovering a known synthetic model,
- the time-range trim helper in the engine,
- the expanded (max-reliability) auto-tune,
- the Indonesia (SNI 1726-2019) standard and SNI site classes.

Run with:  python test_inversion.py
"""

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import hvsr_inversion as inv
import hvsr_standards
from hvsr_engine import trim_seconds, auto_tune, analyze, preprocess
from hvsr_io import ThreeChannel


def _peak(freqs, vals):
    best = (0.0, 0.0)
    for f, v in zip(freqs, vals):
        if v and v > best[1]:
            best = (f, v)
    return best


class ForwardModelTests(unittest.TestCase):
    def test_halfspace_ellipticity_nu025(self):
        """Uniform half-space, nu=0.25 (Vp/Vs=sqrt(3)): analytic surface
        ellipticity |ux/uz| = 0.6815."""
        vp = 1000.0 * math.sqrt(3.0)
        ell = inv.rayleigh_ellipticity([1.0, 2.0, 5.0], [40.0, 1.0],
                                       [vp, vp], [1000.0, 1000.0],
                                       [2.0, 2.0])
        for e in ell:
            self.assertIsNotNone(e)
            self.assertAlmostEqual(e, 0.6815, delta=0.01)

    def test_soft_layer_peak_position(self):
        """Soft layer over stiff half-space: peak near Vs1/(4*h1)."""
        freqs = inv.log_frequencies(0.3, 12.0, 60)
        for h1, vs1, expect in ((40.0, 300.0, 1.875),
                                (80.0, 300.0, 0.94),
                                (20.0, 250.0, 3.125)):
            ell = inv.rayleigh_ellipticity(freqs, [h1, 1.0],
                                           [vs1 * 2.0, 3000.0],
                                           [vs1, 1500.0], [1.9, 2.2])
            fpeak, _ = _peak(freqs, ell)
            self.assertGreater(fpeak, 0.0)
            self.assertAlmostEqual(fpeak, expect, delta=0.35 * expect)

    def test_no_contrast_flat(self):
        """No impedance contrast -> no resonance peak (flat curve)."""
        freqs = inv.log_frequencies(0.5, 10.0, 30)
        ell = inv.rayleigh_ellipticity(freqs, [40.0, 1.0],
                                       [3000.0, 3000.0],
                                       [1500.0, 1500.0], [2.0, 2.0])
        vals = [e for e in ell if e]
        self.assertEqual(len(vals), len(freqs))
        self.assertLess(max(vals) / min(vals), 1.2)

    def test_vp_density_relations(self):
        self.assertAlmostEqual(inv.vp_from_vs(1000.0, 0.25),
                               1000.0 * math.sqrt(3.0), delta=1.0)
        rho = inv.density_from_vp(2000.0)
        self.assertTrue(1.6 <= rho <= 2.9)

    def test_vs30_from_profile(self):
        # 2 layers of 15 m at 300 m/s over a 600 m/s half-space
        vs30 = inv.vs30_from_profile([15.0, 15.0, 1.0], [300.0, 300.0,
                                                         600.0])
        self.assertAlmostEqual(vs30, 300.0, delta=1.0)
        # half-space fills the remainder below the layers
        vs30b = inv.vs30_from_profile([20.0, 1.0], [200.0, 800.0])
        self.assertAlmostEqual(vs30b, 30.0 / (20.0 / 200.0 + 10.0 / 800.0),
                               delta=1.0)


class TrimTests(unittest.TestCase):
    def _data(self, n=1000, fs=100.0):
        return ThreeChannel(list(range(n)), list(range(n)),
                            list(range(n)), fs)

    def test_trim_seconds(self):
        d = self._data(1000, 100.0)   # 10 s
        t = trim_seconds(d, 2.0, 8.0)
        self.assertEqual(t.n_samples, 600)
        self.assertEqual(t.z[0], 200)
        self.assertEqual(t.z[-1], 799)

    def test_trim_open_ends(self):
        d = self._data(1000, 100.0)
        t0 = trim_seconds(d, None, 5.0)
        self.assertEqual(t0.n_samples, 500)
        t1 = trim_seconds(d, 5.0, None)
        self.assertEqual(t1.n_samples, 500)

    def test_trim_empty_raises(self):
        d = self._data(1000, 100.0)
        with self.assertRaises(Exception):
            trim_seconds(d, 8.0, 2.0)


class AutoTuneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import make_sample_data
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sample_data")
        p = make_sample_data.write_station(folder)
        data = __import__("hvsr_io").auto_load([p])
        cls.clean, _ = preprocess(data, f_low=0.2, f_high=20.0, mute=True)

    def test_quick_autotune(self):
        res, w, r = auto_tune(self.clean, fmin=0.5, fmax=20.0, nfreq=256,
                              window_lengths=(25.0, 30.0),
                              rejections=(1.5, 2.0), station="s")
        self.assertGreater(res.sesame_score, 0)
        self.assertAlmostEqual(res.f0, 2.0, delta=0.3)
        self.assertIn("window_length", res.tuned)

    def test_full_autotune(self):
        res, w, r = auto_tune(self.clean, fmin=0.5, fmax=20.0, nfreq=256,
                              window_lengths=(25.0,),
                              rejections=(1.5,),
                              smoothings=("konno_ohmachi",
                                          "moving_average"),
                              smooth_widths=(40.0,),
                              combos=("geometric",),
                              station="s", full=True)
        self.assertGreaterEqual(res.sesame_score,
                                getattr(res, "sesame_score", 0))
        self.assertIn("smoothing", res.tuned)
        self.assertIn("combo", res.tuned)


class IndonesiaStandardTests(unittest.TestCase):
    def test_sni_soil_classes(self):
        self.assertEqual(hvsr_standards.soil_class_sni(1510.0)[0], "SA")
        self.assertEqual(hvsr_standards.soil_class_sni(1500.0)[0], "SB")
        self.assertEqual(hvsr_standards.soil_class_sni(1000.0)[0], "SB")
        self.assertEqual(hvsr_standards.soil_class_sni(750.0)[0], "SC")
        self.assertEqual(hvsr_standards.soil_class_sni(400.0)[0], "SC")
        self.assertEqual(hvsr_standards.soil_class_sni(350.0)[0], "SD")
        self.assertEqual(hvsr_standards.soil_class_sni(200.0)[0], "SD")
        self.assertEqual(hvsr_standards.soil_class_sni(175.0)[0], "SE")
        self.assertEqual(hvsr_standards.soil_class_sni(None)[0], "N/A")

    def test_indonesia_in_standards(self):
        self.assertIn("indonesia", hvsr_standards.STANDARDS)
        rec = hvsr_standards.recommended_params("indonesia")
        self.assertEqual(rec["win_len"], 30.0)
        self.assertEqual(rec["smoothing"], "konno_ohmachi")

    def test_evaluate_indonesia(self):
        class R:
            f0 = 2.0
            a0 = 3.5
            sigma_f = 0.05
            window_len = 30.0
            n_windows_accepted = 12
            sesame = {"nc": 720}

        ev = hvsr_standards.evaluate_indonesia(R())
        self.assertTrue(ev["ok"])
        # Vs30 from the default power law for f0=2: 38*2^0.997 ~ 76 m/s -> SE
        self.assertEqual(ev["soil_class"], "SE")
        self.assertIsNotNone(ev["vs30"])

    def test_evaluate_all_keeps_sni_class(self):
        class R:
            f0 = 2.0
            a0 = 3.5
            sigma_f = 0.05
            window_len = 30.0
            n_windows_accepted = 12
            sesame = {"nc": 720}

        evals = hvsr_standards.evaluate_all(R(), ["indonesia"])
        ev = evals["indonesia"]
        self.assertIn(ev["soil_class"], ("SA", "SB", "SC", "SD", "SE"))


class InversionTests(unittest.TestCase):
    def test_inversion_recovers_synthetic_curve(self):
        """Invert the synthetic 2 Hz station and check the peak frequency
        and Vs30 land in a sensible range."""
        import make_sample_data
        from hvsr_io import auto_load
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sample_data")
        p = make_sample_data.write_station(folder)
        data = auto_load([p])
        clean, _ = preprocess(data, f_low=0.2, f_high=20.0, mute=True)
        res = analyze(clean, w_len=30.0, rejection=1.5, fmin=0.5, fmax=20.0,
                      nfreq=192, station="sample")
        self.assertAlmostEqual(res.f0, 2.0, delta=0.3)

        vs30_anchor = res.standards["sesame"]["vs30"]
        inv_res = inv.invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                                  station="sample", n_layers=3, n_iter=150,
                                  vs30_anchor=vs30_anchor)
        self.assertIsNotNone(inv_res.vs30)
        self.assertTrue(120 < inv_res.vs30 < 800, inv_res.vs30)
        self.assertGreater(inv_res.f0_syn, 0.0)
        # synthetic peak within ~50% of the observed one
        ratio = inv_res.f0_syn / res.f0
        self.assertTrue(0.5 < ratio < 1.6, "f0 ratio %.2f" % ratio)
        self.assertEqual(len(inv_res.layers), 4)  # 3 layers + half-space
        self.assertTrue(inv_res.report_text.startswith("="))
        self.assertIn("SNI site class", inv_res.report_text)

    def test_inversion_report_and_csv(self):
        import tempfile
        import make_sample_data
        from hvsr_io import auto_load
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sample_data")
        p = make_sample_data.write_station(folder)
        data = auto_load([p])
        clean, _ = preprocess(data, f_low=0.2, f_high=20.0, mute=True)
        res = analyze(clean, w_len=30.0, rejection=1.5, fmin=0.5, fmax=20.0,
                      nfreq=128, station="sample")
        inv_res = inv.invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                                  station="sample", n_layers=2, n_iter=60)
        tmp = tempfile.mkdtemp()
        rep = os.path.join(tmp, "rep.txt")
        csv = os.path.join(tmp, "model.csv")
        inv.write_inversion_report(rep, inv_res)
        inv.write_inversion_csv(csv, inv_res)
        self.assertTrue(os.path.exists(rep))
        self.assertTrue(os.path.exists(csv))
        with open(csv, "r", encoding="utf-8") as fh:
            head = fh.readline()
        self.assertTrue(head.startswith("layer,top_m"))

    def test_misfit_histogram(self):
        """Finite misfits are binned; inf/None and tiny samples are safe."""
        edges, counts = inv.misfit_histogram(
            [0.1, 0.2, 0.3, 0.4, 0.5, 1.0, float("inf"), None])
        self.assertIsNotNone(edges)
        self.assertEqual(len(edges), 25)          # 24 bins
        self.assertEqual(len(counts), 24)
        self.assertEqual(sum(counts), 6)          # only the 6 finite values
        self.assertAlmostEqual(edges[0], 0.1)
        self.assertAlmostEqual(edges[-1], 1.0)
        e2, c2 = inv.misfit_histogram([1.0])
        self.assertIsNone(e2)
        self.assertEqual(c2, [])
        e3, c3 = inv.misfit_histogram([])
        self.assertIsNone(e3)

    def test_percentile_helper(self):
        """Nearest-rank percentiles are deterministic and well-behaved."""
        self.assertEqual(inv._percentile([1, 2, 3, 4, 5], 16), 1)
        self.assertEqual(inv._percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertEqual(inv._percentile([1, 2, 3, 4, 5], 84), 5)
        self.assertEqual(inv._percentile([7], 84), 7)
        self.assertEqual(inv._percentile([1, 1, 1, 1], 50), 1)
        self.assertIsNone(inv._percentile([], 50))

    def test_inversion_uncertainty_fields(self):
        """The accepted-ensemble P16/P84 ranges are computed, attached to
        every layer, reported, and exported to the CSV."""
        import make_sample_data
        from hvsr_io import auto_load
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sample_data")
        p = make_sample_data.write_station(folder)
        data = auto_load([p])
        clean, _ = preprocess(data, f_low=0.2, f_high=20.0, mute=True)
        res = analyze(clean, w_len=30.0, rejection=1.5, fmin=0.5, fmax=20.0,
                      nfreq=128, station="sample")
        inv_res = inv.invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                                  station="sample", n_layers=3, n_iter=120,
                                  seed_rng=random.Random(7))
        self.assertEqual(len(inv_res.layers), 4)          # 3 + half-space
        self.assertEqual(len(inv_res.vs_p16), 4)
        self.assertEqual(len(inv_res.vs_p84), 4)
        self.assertEqual(len(inv_res.thickness_p16), 3)
        self.assertEqual(len(inv_res.misfits), 120)
        self.assertIsNotNone(inv_res.misfit_p50)
        self.assertIsNotNone(inv_res.misfit_p90)
        for lay in inv_res.layers:
            lo, hi = lay.get("vs_lo"), lay.get("vs_hi")
            self.assertIsNotNone(lo)
            self.assertIsNotNone(hi)
            self.assertLessEqual(lo, lay["vs"] + 1e-9)
            self.assertGreaterEqual(hi, lay["vs"] - 1e-9)
            self.assertLessEqual(lo, hi)
        self.assertIn("UNCERTAINTY", inv_res.report_text)
        import tempfile
        tmp = tempfile.mkdtemp()
        csv = os.path.join(tmp, "m.csv")
        inv.write_inversion_csv(csv, inv_res)
        with open(csv, encoding="utf-8") as fh:
            head = fh.readline()
        self.assertIn("vs_p16", head)
        self.assertIn("thk_p84", head)


if __name__ == "__main__":
    unittest.main()
