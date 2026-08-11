"""
test_extras.py
==============
Second wave of unit tests for the HVSR Analyzer - covers code paths that
test_engine.py / test_io.py do not:

  * STEIM-1 / STEIM-2 decoding (hand-crafted 64-bit words),
  * full-file miniSEED decoding for int16 / int24 / int32 and STEIM-1,
  * the write_mseed -> read_mseed round trip (whole and fractional rates),
  * the hvsr_standards module (thickness / Vs30 / soil class / checklists),
  * engine internals (Kg, peak picking, SESAME criteria, window rejection),
  * pre-processing with decimation and with a pole-zero response,
  * hvsr_io format routing (.eqd / .sg2 / miniSEED trios, swap N/E),
  * hvsr_geopsy parameter-file writing and Geopsy discovery.

Run:  python test_extras.py
"""

import math
import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from mseed_io import (read_mseed, write_mseed, _decode_steim,
                      _rate_factor_multiplier, MseedError)
from eqd_io import read_eqd
from sg2_io import read_sg2
from hvsr_io import (ThreeChannel, auto_load, load_eqd, load_sg2,
                     read_three_channel, read_single_column,
                     classify_component, DataError)
from hvsr_engine import (preprocess, analyze, compute_spectra, pick_peak,
                         sesame_evaluate, vulnerability_kg, reject_windows,
                         mean_and_std_curves, HvsrResult)
from hvsr_dsp import parse_paz
import hvsr_standards
import hvsr_geopsy
from chart_render import write_png, HvsrChart

from test_io import write_test_eqd, write_test_sg2


# ---------------------------------------------------------------------------
# STEIM word-level decoding
# ---------------------------------------------------------------------------
class TestSteim(unittest.TestCase):
    def test_steim1_first_difference(self):
        """STEIM-1 order-0: x0 then nibbles added to the running sample."""
        word0 = 0x80000000 | 6          # x0 present, nibcnt=6, order 0
        x0 = 10
        data = 0x1E3C5A00               # diffs 1,-2,3,-4,5,-6 (nibbles)
        out = _decode_steim([word0, x0, data], 6, steim2=False)
        self.assertEqual(out, [11, 9, 12, 8, 13, 7])

    def test_steim1_second_difference(self):
        """STEIM-1 order-1: dt feeds diff2 -> diff1 -> current."""
        word0 = 0x80010000 | 3          # order bit 16 set
        x0 = 100
        data = 0x12F00000               # diffs 1,2,-1
        out = _decode_steim([word0, x0, data], 3, steim2=False)
        self.assertEqual(out, [101, 105, 111])

    def test_steim2_second_difference(self):
        """STEIM-2 order-1 uses the same recursion (order at bits 16-17)."""
        word0 = 0x80010000 | 3
        x0 = 100
        data = 0x12F00000
        out = _decode_steim([word0, x0, data], 3, steim2=True)
        self.assertEqual(out, [101, 105, 111])

    def test_steim2_third_difference(self):
        """STEIM-2 order-2: triple integration of the nibbles."""
        word0 = 0x80020000 | 3          # order = 2
        x0 = 100
        data = 0x12F00000               # diffs 1,2,-1
        out = _decode_steim([word0, x0, data], 3, steim2=True)
        # diff3: 1,3,2 | diff2: 1,4,6 | diff1: 1,5,11 | current: 101,106,117
        self.assertEqual(out, [101, 106, 117])

    def test_nibcnt_stops_decode(self):
        """Only nibcnt nibbles are consumed even if more words exist."""
        word0 = 0x80000000 | 2          # only 2 differences wanted
        x0 = 10
        data = 0x1E000000               # nibbles 1, -2 (then junk)
        out = _decode_steim([word0, x0, data], 2, steim2=False)
        self.assertEqual(out, [11, 9])


# ---------------------------------------------------------------------------
# miniSEED: full-file decoding of the integer encodings + STEIM
# ---------------------------------------------------------------------------
def _variant_record(rl=4096, encoding=4, word_order=0, n_per_rec=1010,
                    rate=500, data_bytes=b""):
    """One Guralp-variant miniSEED record with the given encoding byte."""
    rec = bytearray(rl)
    rec[0:6] = b"%06d" % 1
    rec[6] = ord("D")
    rec[8:14] = b"00253 "
    rec[15:18] = b"EHZ"
    rec[18:20] = b"GU"
    struct.pack_into(">H", rec, 30, n_per_rec)
    struct.pack_into(">H", rec, 32, rate)
    struct.pack_into(">H", rec, 44, 56)
    struct.pack_into(">H", rec, 46, 48)
    struct.pack_into(">H", rec, 48, 1000)
    struct.pack_into(">H", rec, 50, 0)
    rec[52] = encoding
    rec[53] = word_order
    rec[54] = 12
    rec[56:56 + len(data_bytes)] = data_bytes
    return bytes(rec)


def _write_variant_mseed(path, records):
    with open(path, "wb") as fh:
        for r in records:
            fh.write(r)


class TestMseedEncodings(unittest.TestCase):
    @staticmethod
    def _write_int_file(td, encoding, scale, fmt, bsize, n_records=3,
                        rate=100.0):
        """Write N records of a 2 Hz sine quantised to an int format."""
        n_per = (4096 - 56) // bsize
        recs = []
        for r in range(n_records):
            data = bytearray()
            for i in range(n_per):
                v = int(scale * math.sin(2 * math.pi * 2.0 * i / rate))
                if fmt == ">h":
                    data += struct.pack(fmt, v)
                elif bsize == 3:
                    b = struct.pack(">i", v)[1:4]   # 24-bit big-endian
                    data += b
                else:
                    data += struct.pack(fmt, v)
            recs.append(_variant_record(encoding=encoding, word_order=0,
                                        n_per_rec=n_per, rate=100,
                                        data_bytes=bytes(data)))
        p = os.path.join(td, "int.mseed")
        _write_variant_mseed(p, recs)
        return p

    def test_int16(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_int_file(td, 1, 20000, ">h", 2)
            vals, fs, meta = read_mseed(p)
            self.assertAlmostEqual(fs, 100.0)
            self.assertEqual(len(vals), 3 * 2020)
            self.assertAlmostEqual(max(abs(v) for v in vals), 20000.0,
                                   delta=50.0)
            self.assertEqual(meta["encoding"], "INT16")

    def test_int24(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_int_file(td, 2, 2000000, ">i", 3)
            vals, fs, meta = read_mseed(p)
            self.assertAlmostEqual(fs, 100.0)
            # 1346 x 3-byte samples per record; the reader must NOT read the
            # rate field (bytes 32-33) as the sample count here
            self.assertEqual(len(vals), 3 * 1346)
            # a discrete 2 Hz sine never samples exactly at its peak:
            # the largest |sample| is ~0.998 * amplitude
            self.assertAlmostEqual(max(abs(v) for v in vals), 2000000.0,
                                   delta=20000.0)
            self.assertEqual(meta["encoding"], "INT24")

    def test_int32(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_int_file(td, 3, 2000000000, ">i", 4)
            vals, fs, meta = read_mseed(p)
            self.assertAlmostEqual(fs, 100.0)
            self.assertEqual(len(vals), 3 * 1010)
            self.assertAlmostEqual(max(abs(v) for v in vals), 2000000000.0,
                                   delta=20000000.0)
            self.assertEqual(meta["encoding"], "INT32")

    def test_int16_wrong_claimed_order(self):
        """Claim little-endian while data is big-endian: the lag-1 heuristic
        must pick the smoother (correct) order."""
        with tempfile.TemporaryDirectory() as td:
            p = self._write_int_file(td, 1, 20000, ">h", 2)
            # rewrite record 0's word-order byte to lie (offset 53 is inside
            # the first record; the byte-order resolver only reads record 0)
            with open(p, "r+b") as fh:
                fh.seek(53)
                fh.write(b"\x01")
            vals, _fs, _meta = read_mseed(p)
            self.assertAlmostEqual(max(abs(v) for v in vals), 20000.0,
                                   delta=50.0)

    def test_steim1_full_file(self):
        """A real miniSEED file whose data section is packed STEIM-1 words."""
        per_rec = 6
        recs = []
        for r in range(3):
            base = r * 100
            v0 = 10 + base
            diffs = [1, -2, 3, -4, 5, -6]
            word0 = 0x80000000 | per_rec
            word1 = v0 & 0xFFFFFFFF
            word2 = 0
            for k, d in enumerate(diffs):
                word2 |= (d & 0xF) << (28 - k * 4)
            words = [word0, word1, word2]
            data = struct.pack(">3Q", *words) + b"\x00" * (4040 - 24)
            recs.append(_variant_record(encoding=10, n_per_rec=per_rec,
                                        rate=per_rec, data_bytes=data))
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "steim.mseed")
            _write_variant_mseed(p, recs)
            vals, _fs, meta = read_mseed(p)
            self.assertEqual(meta["encoding"], "STEIM1")
            self.assertEqual(len(vals), 3 * per_rec)
            # per record: [base+11, base+9, base+12, base+8, base+13, base+7]
            for r in range(3):
                base = r * 100
                self.assertEqual(vals[r * per_rec:(r + 1) * per_rec],
                                 [base + 11, base + 9, base + 12, base + 8,
                                  base + 13, base + 7])


# ---------------------------------------------------------------------------
# write_mseed -> read_mseed round trip
# ---------------------------------------------------------------------------
class TestMseedRoundTrip(unittest.TestCase):
    @staticmethod
    def _roundtrip(fs):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "rt.mseed")
            vals = [1000.0 * math.sin(2 * math.pi * 2.0 * i / fs)
                    for i in range(4000)]
            write_mseed(p, vals, fs, "EHZ", station="TEST")
            out, rfs, meta = read_mseed(p)
            return vals, out, rfs, meta

    def test_whole_rate(self):
        vals, out, rfs, meta = self._roundtrip(100.0)
        self.assertAlmostEqual(rfs, 100.0, delta=0.01)
        self.assertEqual(len(out), len(vals))
        self.assertEqual(meta["station"].strip(), "TEST")
        self.assertEqual(meta["channel"].strip(), "EHZ")

    def test_fractional_rate(self):
        """A fractional sampling rate (500/3 Hz, the post-decimation rate)
        must survive the round trip exactly (factor=-3, multiplier=500)."""
        vals, out, rfs, meta = self._roundtrip(500.0 / 3.0)
        self.assertAlmostEqual(rfs, 500.0 / 3.0, delta=0.01)
        self.assertEqual(len(out), len(vals))
        # sample values must come back close to what was written
        diff = max(abs(a - b) for a, b in zip(vals[1000:2000], out[1000:2000]))
        self.assertLess(diff, 0.5)


class TestRateFactorMultiplier(unittest.TestCase):
    def test_whole_rate(self):
        self.assertEqual(_rate_factor_multiplier(100.0), (100, 1))

    def test_exact_fraction(self):
        self.assertEqual(_rate_factor_multiplier(500.0 / 3.0), (-3, 500))

    def test_rounded_fraction(self):
        """A human-typed 166.6667 must still encode as 500/3, not 167/1."""
        self.assertEqual(_rate_factor_multiplier(166.6667), (-3, 500))


# ---------------------------------------------------------------------------
# hvsr_standards
# ---------------------------------------------------------------------------
class TestStandards(unittest.TestCase):
    def test_thickness_default(self):
        # 96.0 * 2.0**-1.388
        self.assertAlmostEqual(hvsr_standards.estimate_thickness(2.0),
                               36.68, delta=0.1)
        self.assertIsNone(hvsr_standards.estimate_thickness(0.0))

    def test_thickness_other_relation(self):
        h = hvsr_standards.estimate_thickness(2.0, "Parolai et al. (2002)")
        self.assertAlmostEqual(h, 108.0 * 2.0 ** -1.551, delta=0.1)

    def test_vs30_powerlaw(self):
        self.assertAlmostEqual(hvsr_standards.estimate_vs30_powerlaw(2.0),
                               38.0 * 2.0 ** 0.997, delta=0.1)

    def test_vs30_from_thickness_thick(self):
        # f0 = 0.5 Hz -> h ~ 251 m >= 30 m -> pure soft soil velocity
        self.assertAlmostEqual(
            hvsr_standards.estimate_vs30_from_thickness(0.5), 300.0, delta=1.0)

    def test_vs30_from_thickness_thin(self):
        # f0 = 10 Hz -> h ~ 3.9 m -> mixed with bedrock down to 30 m
        vs = hvsr_standards.estimate_vs30_from_thickness(10.0)
        self.assertGreater(vs, 300.0)
        self.assertLess(vs, 800.0)

    def test_soil_class_boundaries(self):
        self.assertEqual(hvsr_standards.soil_class(1510.0)[0], "A")
        self.assertEqual(hvsr_standards.soil_class(1500.0)[0], "B")
        self.assertEqual(hvsr_standards.soil_class(760.0)[0], "C")
        self.assertEqual(hvsr_standards.soil_class(360.0)[0], "D")
        self.assertEqual(hvsr_standards.soil_class(180.0)[0], "E")
        self.assertEqual(hvsr_standards.soil_class(None)[0], "N/A")

    def test_evaluate_all(self):
        res = HvsrResult()
        res.f0, res.a0 = 2.0, 4.0
        res.window_len, res.n_windows_accepted = 30.0, 12
        res.sigma_f = 0.05
        res.sesame = {"f0_gt_10_over_lw": True, "nc_gt_200": True,
                      "sigma_A_ok": True, "drop_below_f0": True,
                      "drop_above_f0": True, "a0_gt_2": True,
                      "sigma_f_ok": True}
        evals = hvsr_standards.evaluate_all(res)
        self.assertEqual(set(evals), {"sesame", "japan", "indonesia",
                                      "usgs", "generic"})
        for sid, ev in evals.items():
            self.assertIn("items", ev)
            self.assertGreater(ev["vs30"], 0.0)
            self.assertGreater(ev["thickness"], 0.0)
        self.assertEqual(evals["sesame"]["verdict"], "RELIABLE")
        self.assertEqual(evals["japan"]["verdict"], "PASS")
        self.assertEqual(evals["indonesia"]["verdict"], "PASS")
        self.assertIn(evals["indonesia"]["soil_class"],
                      ("SA", "SB", "SC", "SD", "SE"))
        report = hvsr_standards.build_standards_report(res)
        self.assertIn("SESAME 2004", report)
        self.assertIn("VERDICT:", report)
        self.assertIn("Sediment depth h", report)

    def test_recommended_params(self):
        p = hvsr_standards.recommended_params("japan")
        self.assertEqual(p["win_len"], 60.0)
        self.assertEqual(p["rejection"], 2.0)


# ---------------------------------------------------------------------------
# engine internals
# ---------------------------------------------------------------------------
class TestEngineInternals(unittest.TestCase):
    def test_vulnerability_kg(self):
        kg, level = vulnerability_kg(5.0, 1.0)
        self.assertAlmostEqual(kg, 25.0)
        self.assertEqual(level, "HIGH VULNERABILITY")
        kg, level = vulnerability_kg(3.5, 1.5)
        self.assertEqual(level, "MODERATE VULNERABILITY")
        kg, level = vulnerability_kg(2.0, 2.0)
        self.assertEqual(level, "LOW VULNERABILITY")

    def test_pick_peak_parabolic(self):
        from hvsr_engine import log_frequencies
        freqs = log_frequencies(0.5, 20.0, 256)
        amps = [1.0 + 3.0 * math.exp(-((math.log(f) - math.log(2.0)) ** 2) / 0.1)
                for f in freqs]
        f0, a0 = pick_peak(freqs, amps)
        self.assertAlmostEqual(f0, 2.0, delta=0.1)
        self.assertGreater(a0, 3.5)

    def test_pick_peak_empty(self):
        self.assertEqual(pick_peak([], []), (0.0, 0.0))

    def test_sesame_evaluate(self):
        from hvsr_engine import log_frequencies
        freqs = log_frequencies(0.5, 20.0, 128)
        amps = [1.0 + 3.0 * math.exp(-((math.log(f) - math.log(2.0)) ** 2) / 0.05)
                for f in freqs]
        high = [1.1 * a for a in amps]
        f0, a0 = pick_peak(freqs, amps)
        crit = sesame_evaluate(freqs, amps, high, f0, a0, 12, 30.0, 0.05)
        self.assertTrue(crit["f0_gt_10_over_lw"])
        self.assertTrue(crit["nc_gt_200"])
        self.assertTrue(crit["a0_gt_2"])
        self.assertTrue(crit["drop_below_f0"])
        self.assertTrue(crit["drop_above_f0"])
        self.assertTrue(crit["sigma_A_ok"])

    def test_reject_windows_f0_outlier(self):
        """The Cox/Geopsy criterion rejects the window whose f0 lies
        outside the log-normal band of the window-f0 population."""
        from hvsr_engine import log_frequencies
        freqs = log_frequencies(0.5, 20.0, 128)

        def curve(fc):
            return [1.0 + 3.0 * math.exp(
                -((math.log(f) - math.log(fc)) / 0.1) ** 2)
                for f in freqs]

        curves = [curve(fc) for fc in (1.8, 2.0, 2.2, 4.0)]
        valid, n = reject_windows(curves, freqs, 1.5)
        self.assertEqual(n, 3)
        self.assertFalse(valid[-1])      # 4.0 Hz window rejected
        self.assertTrue(all(valid[:-1]))

    def test_reject_windows_no_peak_kept(self):
        """A window with no local peak in the search band is kept for the
        mean curve but excluded from the f0 statistics (Geopsy behaviour:
        89 curve windows but 88 windows for f0)."""
        from hvsr_engine import log_frequencies
        freqs = log_frequencies(0.5, 20.0, 64)
        flat = [2.0] * len(freqs)        # constant curve -> no local peak
        peaked = [1.0 + 3.0 * math.exp(
            -((math.log(f) - math.log(2.0)) / 0.1) ** 2) for f in freqs]
        curves = [flat] + [peaked] * 4
        valid, n = reject_windows(curves, freqs, 1.5)
        self.assertTrue(valid[0])
        self.assertEqual(n, 5)

    def test_mean_and_std(self):
        curves = [[1.0, 2.0], [2.0, 4.0], [4.0, 8.0]]
        mean, low, high = mean_and_std_curves(curves, [True, True, True])
        self.assertAlmostEqual(mean[0], 2.0, delta=0.01)
        self.assertAlmostEqual(mean[1], 4.0, delta=0.01)
        for lo, m, hi in zip(low, mean, high):
            self.assertLess(lo, m)
            self.assertLess(m, hi)

    def test_preprocess_decimation(self):
        import random
        rng = random.Random(1)
        n = [rng.gauss(0, 1) for _ in range(6000)]
        data = ThreeChannel(list(n), list(n), list(n), 500.0)
        clean, meta = preprocess(data, f_low=0.2, f_high=20.0,
                                 mute=True, max_fs=200.0)
        self.assertEqual(meta["dec_factor"], 3)
        self.assertAlmostEqual(clean.fs, 500.0 / 3.0, delta=0.01)
        self.assertEqual(clean.n_samples, 2000)

    def test_preprocess_with_paz(self):
        text = ("ZEROS 2\n0 0\n0 0\nPOLES 2\n-71.1766 0\n-13.8664 0\n"
                "CONSTANT 167.742")
        paz = parse_paz(text)
        import random
        rng = random.Random(2)
        n = [rng.gauss(0, 1) for _ in range(3000)]
        data = ThreeChannel(list(n), list(n), list(n), 100.0)
        clean, meta = preprocess(data, paz=paz)
        self.assertEqual(clean.n_samples, 3000)
        self.assertEqual(clean.fs, 100.0)

    def test_compute_spectra(self):
        import random
        rng = random.Random(3)
        n = [rng.gauss(0, 1) for _ in range(5000)]
        data = ThreeChannel(list(n), list(n), list(n), 100.0)
        out = compute_spectra(data, w_len=30.0)
        self.assertGreater(out["n_windows"], 0)
        self.assertTrue(out["freqs"])
        self.assertEqual(len(out["spec"]["z"]), len(out["freqs"]))
        self.assertEqual(len(out["psd"]["n"]), len(out["freqs"]))

    def test_analyze_quadratic_combo(self):
        from make_sample_data import make_station
        z, n, e = make_station(duration=120.0, fs=100.0, f0=2.0, seed=11)
        data = ThreeChannel(z, n, e, 100.0)
        clean, _ = preprocess(data)
        res = analyze(clean, w_len=30.0, combo="quadratic")
        self.assertGreater(res.n_windows_accepted, 0)
        self.assertAlmostEqual(res.f0, 2.0, delta=0.5)
        self.assertIn("SESAME 2004", res.report_text)
        self.assertTrue(res.standards)


# ---------------------------------------------------------------------------
# hvsr_io routing
# ---------------------------------------------------------------------------
class TestFormatRouting(unittest.TestCase):
    def test_auto_load_eqd(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "st.eqd")
            write_test_eqd(p, fs=500.0, n_samples=3000)
            data = auto_load([p])
            self.assertAlmostEqual(data.fs, 500.0)
            self.assertEqual(data.n_samples, 3000)
            # Z is the 2 Hz sine: quarter cycle near sample 62
            self.assertAlmostEqual(data.z[62], 2000.0, delta=150.0)

    def test_auto_load_sg2(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "st.sg2")
            write_test_sg2(p, fs=500.0, n_samples=3000)
            data = auto_load([p])
            self.assertAlmostEqual(data.fs, 500.0)
            # Z trace is the 2 Hz sine (amplitude 1000)
            self.assertAlmostEqual(max(abs(v) for v in data.z), 1000.0,
                                   delta=100.0)

    def test_auto_load_sg2_swap(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "st.sg2")
            write_test_sg2(p, fs=500.0, n_samples=3000)
            swapped = auto_load([p], swap_h=True)
            plain = auto_load([p])
            self.assertNotAlmostEqual(swapped.n[62], plain.n[62], places=0)
            self.assertAlmostEqual(swapped.e[62], plain.n[62], places=0)

    def test_auto_load_mseed_trio(self):
        from test_io import write_test_mseed
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for comp in ("EHZ", "EHN", "EHE"):
                p = os.path.join(td, "ST_%s.mseed" % comp)
                write_test_mseed(p, [comp] * 8, fs=500.0)
                paths.append(p)
            data = auto_load(paths)
            self.assertAlmostEqual(data.fs, 500.0)
            self.assertEqual(data.n_samples, 8 * 1010)
            self.assertAlmostEqual(max(abs(v) for v in data.z[:1010]), 1000.0,
                                   delta=150.0)

    def test_auto_load_single_mseed_raises(self):
        from test_io import write_test_mseed
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "one.mseed")
            write_test_mseed(p, ["EHZ"] * 8, fs=500.0)
            with self.assertRaises(DataError):
                auto_load([p])

    def test_read_three_channel_dt(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "dt.csv")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("# comment\ndt=0.01\nZ,N,E\n1,2,3\n4,5,6\n7,8,9\n")
            data = read_three_channel(p)
            self.assertAlmostEqual(data.fs, 100.0)
            self.assertEqual(data.z, [1.0, 4.0, 7.0])

    def test_read_three_channel_time_column(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "t.csv")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("0.0,1,2,3\n0.01,4,5,6\n0.02,7,8,9\n")
            data = read_three_channel(p)
            self.assertAlmostEqual(data.fs, 100.0)
            self.assertEqual(data.n, [2.0, 5.0, 8.0])

    def test_classify_component(self):
        self.assertEqual(classify_component("ST_EHZ.mseed"), "Z")
        self.assertEqual(classify_component("ST_HHN.mseed"), "N")
        self.assertEqual(classify_component("ST_EHE.mseed"), "E")
        self.assertIsNone(classify_component("noise.csv"))

    def test_read_single_column(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "z.txt")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("fs=100\n1\n2\n3\n")
            vals, fs = read_single_column(p)
            self.assertEqual(vals, [1.0, 2.0, 3.0])
            self.assertEqual(fs, 100.0)


# ---------------------------------------------------------------------------
# hvsr_geopsy (param writing + discovery, no external run)
# ---------------------------------------------------------------------------
class TestGeopsyHelpers(unittest.TestCase):
    def test_write_param(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "params.param")
            hvsr_geopsy._write_param(p, 40.0, 1.5, 0.5, 20.0, 256)
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("WINDOW_LENGTH_TYPE=Exactly", text)
            self.assertIn("WINDOW_MAX_LENGTH(s)=40.0", text)
            self.assertIn("MINIMUM_FREQUENCY=0.500", text)
            self.assertIn("MAXIMUM_FREQUENCY=20.000", text)
            self.assertIn("SAMPLES_NUMBER_FREQUENCY=256", text)
            self.assertIn("FREQUENCY_WINDOW_REJECTION_STDDEV_FACTOR=1.50",
                          text)
            # parameter parity with the built-in engine (new keys)
            self.assertIn("SMOOTHING_WIDTH=0.2", text)   # geopsy-native KO width
            self.assertIn("HORIZONTAL_COMPONENTS=Geometric", text)
            self.assertIn("WINDOW_ALPHA=0.05", text)
            self.assertIn("STEP_TYPE_FREQUENCY=Step", text)
            self.assertIn("STEP_FREQUENCY=1.014", text)   # ~256 log points

    def test_find_geopsy(self):
        exe = hvsr_geopsy.find_geopsy()
        self.assertTrue(exe is None or exe.endswith("geopsy-hv.exe"))


# ---------------------------------------------------------------------------
# chart renderer sanity (simple axis/scales paths not covered by test_engine)
# ---------------------------------------------------------------------------
class TestChartExtra(unittest.TestCase):
    def test_draw_spectra(self):
        from hvsr_engine import log_frequencies
        with tempfile.TemporaryDirectory() as td:
            chart = HvsrChart(480, 320)
            freqs = log_frequencies(0.5, 20.0, 120)
            curves = {"z": [1.0 + 0.01 * i for i in range(120)],
                      "n": [2.0 + 0.01 * i for i in range(120)],
                      "e": [1.5 + 0.01 * i for i in range(120)]}
            chart.draw_spectra(freqs, curves, mode="PSD", station="T")
            p = os.path.join(td, "t.png")
            chart.save_png(p)
            self.assertGreater(os.path.getsize(p), 500)

    def test_draw_timeseries(self):
        import math
        fs = 50.0
        n = 1000
        t = [i / fs for i in range(n)]
        traces = [("Z", [math.sin(2 * math.pi * 2 * x) for x in t]),
                  ("N", [math.cos(2 * math.pi * 3 * x) for x in t]),
                  ("E", [math.sin(2 * math.pi * 5 * x) for x in t])]
        with tempfile.TemporaryDirectory() as td:
            chart = HvsrChart(480, 320)
            chart.draw_timeseries(traces, fs, win_len=10.0, station="T")
            p = os.path.join(td, "ts.png")
            chart.save_png(p)
            self.assertGreater(os.path.getsize(p), 500)

    def test_draw_colormap(self):
        import math
        freqs = [0.1 * (10 ** (i / 20.0)) for i in range(41)]
        grid = [[math.sin(r * 0.8) * math.cos(c * 0.3) + 2.0
                 for c in range(len(freqs))] for r in range(12)]
        with tempfile.TemporaryDirectory() as td:
            chart = HvsrChart(480, 320)
            chart.draw_colormap(list(range(12)), freqs, grid,
                                title="H/V vs time", ylabel="Time (s)")
            p = os.path.join(td, "cm.png")
            chart.save_png(p)
            self.assertGreater(os.path.getsize(p), 500)

    def test_dark_theme_palette(self):
        """Exported charts keep the default dark palette: near-black corners,
        light text, accent markers (matches hvsr_theme.py's "dark" set)."""
        import math
        from hvsr_engine import log_frequencies
        chart = HvsrChart(480, 320)
        freqs = log_frequencies(0.5, 20.0, 120)
        amps = [1.0 + 3.0 * math.exp(-((math.log(f) - math.log(2.0)) ** 2)
                                     / 0.1) for f in freqs]
        high = [1.2 * a for a in amps]
        chart.draw_hvsr(freqs, amps, [0.8 * a for a in amps], high,
                        2.0, 4.0, station="T")
        # corners must be the dark background (13, 13, 13), not white
        for cx, cy in ((2, 2), (chart.width - 3, 2),
                       (2, chart.height - 3), (chart.width - 3,
                                               chart.height - 3)):
            self.assertEqual(chart.pixels[cy][cx], (13, 13, 13),
                             "chart corner not dark")
        # the mean curve is drawn in the accent colour (#FF6600)
        self.assertIn((255, 102, 0),
                      [c for row in chart.pixels for c in row])
        # f0 marker in emergency red (#FF0033)
        self.assertIn((255, 0, 51),
                      [c for row in chart.pixels for c in row])

    def test_bw_theme_palette(self):
        """The black & white (thesis) theme exports white-background charts
        with black lines - ready for grayscale print / thesis submission."""
        import math
        import chart_render as cr
        from hvsr_engine import log_frequencies
        try:
            cr.apply_palette("bw")
            chart = cr.HvsrChart(480, 320)
            freqs = log_frequencies(0.5, 20.0, 120)
            amps = [1.0 + 3.0 * math.exp(
                -((math.log(f) - math.log(2.0)) ** 2) / 0.1)
                for f in freqs]
            high = [1.2 * a for a in amps]
            chart.draw_hvsr(freqs, amps, [0.8 * a for a in amps], high,
                            2.0, 4.0, station="T")
            # corners must be pure white, not the dark-theme (13, 13, 13)
            for cx, cy in ((2, 2), (chart.width - 3, 2),
                           (2, chart.height - 3), (chart.width - 3,
                                                   chart.height - 3)):
                self.assertEqual(chart.pixels[cy][cx], (255, 255, 255),
                                 "chart corner not white in B&W theme")
            # the mean curve is drawn in pure black
            self.assertIn((0, 0, 0),
                          [c for row in chart.pixels for c in row])
        finally:
            # restore the default theme for the rest of the suite
            cr.apply_palette("dark")


# ---------------------------------------------------------------------------
# Bundled example signals (examples/): each format must load and recover
# the known 2 Hz resonance so the tutorial's expected result stays valid.
# ---------------------------------------------------------------------------
class TestExampleSignals(unittest.TestCase):
    EXAMPLES = os.path.join(HERE, "..", "examples")

    def _load_and_check(self, label, files):
        data = auto_load(files)
        self.assertEqual(data.fs, 500.0)
        clean, _meta = preprocess(data, f_low=0.2, f_high=20.0, max_fs=250.0)
        res = analyze(clean, station=label)
        self.assertTrue(abs(res.f0 - 2.0) < 0.3,
                        "%s: f0 = %.3f" % (label, res.f0))
        self.assertGreater(res.a0, 1.0)

    def test_example_eqd(self):
        self._load_and_check("eqd",
                             [os.path.join(self.EXAMPLES, "example.eqd")])

    def test_example_sg2(self):
        self._load_and_check("sg2",
                             [os.path.join(self.EXAMPLES, "example.sg2")])

    def test_example_mseed_trio(self):
        self._load_and_check("mseed trio", [
            os.path.join(self.EXAMPLES, "example_Z.mseed"),
            os.path.join(self.EXAMPLES, "example_N.mseed"),
            os.path.join(self.EXAMPLES, "example_E.mseed"),
        ])

    def test_example_files_exist(self):
        for f in ("example.eqd", "example.sg2",
                  "example_Z.mseed", "example_N.mseed",
                  "example_E.mseed"):
            self.assertTrue(os.path.exists(os.path.join(self.EXAMPLES, f)),
                            "missing " + f)


class TestSpeedups(unittest.TestCase):
    """The performance work must not change results:

    * fft_real == fft (real-input fast path),
    * the memoized Konno-Ohmachi bands == direct weight recomputation,
    * the cached / parallel auto-tune path == the sequential path,
    * the parallel Monte-Carlo inversion still converges.
    """

    _data = None

    @classmethod
    def _load(cls):
        if cls._data is None:
            import hvsr_io
            from hvsr_engine import preprocess
            data = hvsr_io.auto_load(
                [os.path.join(HERE, "..", "examples", "example.eqd")],
                swap_h=False)
            clean, _ = preprocess(data, f_low=0.2, f_high=40.0, mute=0.2,
                                  sta_sec=1.0, lta_sec=10.0,
                                  slta_threshold=3.0, max_fs=250)
            cls._data = clean
        return cls._data

    def test_fft_real_matches_fft(self):
        import hvsr_dsp
        for n in (2, 3, 4, 7, 8, 9, 16, 625, 1000, 3125, 4096, 6250):
            x = [math.sin(0.1 * k) + 0.5 * math.cos(0.37 * k)
                 for k in range(n)]
            a = hvsr_dsp.fft(x)
            b = hvsr_dsp.fft_real(x)
            # the two paths use different FFT algorithms (direct vs
            # half-size), so a small float roundoff is expected at large n
            for k in range(n):
                self.assertAlmostEqual(a[k].real, b[k].real, places=8)
                self.assertAlmostEqual(a[k].imag, b[k].imag, places=8)

    def test_rfft_magnitude_fast_path(self):
        import hvsr_dsp
        x = [math.sin(0.13 * k) for k in range(600)]
        fast = hvsr_dsp.rfft_magnitude(x)
        # reference: one-sided magnitudes computed straight from fft()
        spec = hvsr_dsp.fft(x)
        n = len(x)
        ref = []
        for k in range(n // 2 + 1):
            if k == 0:
                ref.append(abs(spec[0]))
            elif n % 2 == 0 and k == n // 2:
                ref.append(abs(spec[n // 2]))
            else:
                ref.append(2.0 * abs(spec[k]))
        self.assertEqual(len(fast), 301)
        for a, b in zip(fast, ref):
            self.assertAlmostEqual(a, b, places=9)

    def test_ko_smoothing_matches_direct(self):
        import hvsr_dsp
        freqs = [k * (100.0 / 512) for k in range(513)]
        targets = [0.6, 1.0, 2.5, 7.0, 20.0]
        mag = [abs(math.sin(0.03 * k)) + 0.01 for k in freqs]
        ko = hvsr_dsp.konno_ohmachi_smooth(mag, freqs, targets, 40.0)
        ref = []
        for fc in targets:
            lo = fc * 10 ** (-4.5 / 40.0)
            hi = fc * 10 ** (4.5 / 40.0)
            tw = ts = 0.0
            for i, f in enumerate(freqs):
                if f < lo or f > hi or f <= 0.0:
                    continue
                r = f / fc
                if abs(r - 1.0) < 1e-12:
                    w = 1.0
                else:
                    denom = 40.0 * math.log10(r)
                    w = (math.sin(denom) / denom) ** 4
                tw += w
                ts += w * mag[i]
            ref.append(ts / tw if tw > 0.0 else 0.0)
        for a, b in zip(ko, ref):
            self.assertAlmostEqual(a, b, places=12)

    def test_analyze_still_recovers_f0(self):
        from hvsr_engine import analyze
        clean = self._load()
        res = analyze(clean, w_len=30.0, rejection=1.5)
        self.assertAlmostEqual(res.f0, 2.0, delta=0.15)

    def test_auto_tune_full_parallel_equals_sequential(self):
        from hvsr_engine import auto_tune
        clean = self._load()
        res1, w1, r1 = auto_tune(clean, full=True, n_workers=1)
        res2, w2, r2 = auto_tune(clean, full=True, n_workers=2)
        self.assertEqual(res1.sesame_score, res2.sesame_score)
        self.assertEqual(res1.tuned, res2.tuned)
        self.assertAlmostEqual(res1.f0, res2.f0, places=9)
        for a, b in zip(res1.mean, res2.mean):
            self.assertAlmostEqual(a, b, places=12)

    def test_auto_tune_full_score_ge_quick(self):
        from hvsr_engine import auto_tune
        clean = self._load()
        quick, _, _ = auto_tune(clean, full=False)
        full, _, _ = auto_tune(clean, full=True, n_workers=1)
        self.assertGreaterEqual(full.sesame_score, quick.sesame_score)

    def test_inversion_parallel_valid(self):
        from hvsr_engine import analyze
        import hvsr_inversion as inv
        clean = self._load()
        res = analyze(clean, w_len=30.0, rejection=2.0)
        a = inv.invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                            station="spd", n_layers=3, n_iter=60,
                            monotonic=True, n_workers=1)
        b = inv.invert_hvsr(res.freqs, res.mean, res.f0, res.a0,
                            station="spd", n_layers=3, n_iter=60,
                            monotonic=True, n_workers=2)
        self.assertTrue(a.vs30 and a.vs30 > 0, "sequential failed")
        self.assertTrue(b.vs30 and b.vs30 > 0, "parallel failed")
        self.assertLess(a.misfit or 1.0, 1.0)
        self.assertLess(b.misfit or 1.0, 1.0)
        self.assertEqual(b.n_models, 60)


class TestWorkerOverride(unittest.TestCase):
    """HVSR_WORKERS environment override for the parallel sweeps."""

    def _set_env(self, value):
        if value is None:
            os.environ.pop("HVSR_WORKERS", None)
        else:
            os.environ["HVSR_WORKERS"] = value

    def test_resolve_workers_env(self):
        from hvsr_dsp import resolve_workers
        old = os.environ.get("HVSR_WORKERS")
        try:
            self._set_env(None)
            self.assertEqual(resolve_workers(None), 1)   # default sequential
            self.assertEqual(resolve_workers(8), 8)      # requested count
            self._set_env("2")
            self.assertEqual(resolve_workers(8), 2)      # env wins
            self._set_env("0")
            self.assertEqual(resolve_workers(8), 1)      # 0 disables
            self._set_env("1")
            self.assertEqual(resolve_workers(None), 1)   # 1 disables
            self._set_env("99")
            self.assertEqual(resolve_workers(None), 8)   # capped
            self._set_env("bogus")
            self.assertEqual(resolve_workers(4), 4)      # bad env ignored
        finally:
            self._set_env(old)


if __name__ == "__main__":
    unittest.main(verbosity=2)
