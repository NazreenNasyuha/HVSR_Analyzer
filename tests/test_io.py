"""
test_io.py
==========
Round-trip tests for the pure-stdlib miniSEED, .eqd and SEG-2 (.sg2)
readers.
Run:  python test_io.py
"""
import math
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from mseed_io import read_mseed, MseedError
from eqd_io import read_eqd, EqdError
from sg2_io import read_sg2, Sg2Error


def write_test_mseed(path, channels, fs=500.0, n_records=8, rl=4096,
                     n_per_record=1010, word_order=1):
    """Write a miniSEED file in the Guralp variant layout."""
    with open(path, "wb") as fh:
        for r in range(n_records):
            rec = bytearray(rl)
            rec[0:6] = b"%06d" % (r + 1)
            rec[6] = ord("D")
            rec[7:9] = b"  "
            rec[8:13] = b"00253"       # station (real files: 6 chars)
            rec[14:15] = b"0"
            rec[15:18] = channels[r % 3].encode()  # channel at 15-18
            rec[18:20] = b"GU"                     # network at 18-20
            rec[21:23] = b"\xea\x00"
            rec[23:24] = struct.pack("B", 4)[0:1]     # day
            rec[24:25] = struct.pack("B", 1)[0:1]     # hour
            rec[25:26] = struct.pack("B", 47)[0:1]    # minute
            rec[26:27] = struct.pack("B", 41)[0:1]    # second
            rec[27:30] = b"\x00\x00\x00"
            struct.pack_into(">H", rec, 30, n_per_record)   # samples
            struct.pack_into(">H", rec, 32, int(fs))        # rate
            struct.pack_into(">h", rec, 34, 1)              # factor
            struct.pack_into(">h", rec, 36, 0)              # multiplier
            rec[44:46] = struct.pack(">H", 56)              # beginning of data
            rec[46:48] = struct.pack(">H", 48)              # first blockette
            # blockette 1000 at 48 (length 0, encoding float32, word order,
            # record length exponent)
            rec[48:50] = struct.pack(">H", 1000)
            rec[50:52] = struct.pack(">H", 0)
            rec[52] = 4            # encoding = float32
            rec[53] = word_order   # claimed byte order (real files lie: BE)
            rec[54] = 12           # record length 2^12 = 4096
            # data: float32 samples, big-endian (matching the Guralp files)
            data = bytearray()
            for i in range(n_per_record):
                v = math.sin(2 * math.pi * 2.0 * i / fs) * 1000.0
                data += struct.pack(">f", v)
            rec[56:56 + len(data)] = data
            fh.write(bytes(rec))


def write_test_eqd(path, fs=500.0, n_samples=3000):
    """Write a test .eqd file: 3 interleaved int16 LE channels."""
    with open(path, "wb") as fh:
        fh.write(b"\xed\xad")
        fh.write(struct.pack(">H", 3))     # channels
        fh.write(struct.pack(">H", int(fs)))  # rate
        fh.write(b"\x00\x01\x00\x07\x00\x12")  # misc header fields
        fh.write(b"\x00" * (0x100 - 12))       # pad to data offset
        for i in range(n_samples):
            z = int(2000 * math.sin(2 * math.pi * 2.0 * i / fs))
            n = int(1000 * math.sin(2 * math.pi * 1.5 * i / fs))
            e = int(900 * math.sin(2 * math.pi * 1.3 * i / fs))
            fh.write(struct.pack("<hhh", z, n, e))


class TestMseedIo(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "test.mseed")
            write_test_mseed(p, ["EHZ", "EHN", "EHE"], fs=500.0)
            vals, fs, meta = read_mseed(p)
            self.assertEqual(len(vals), 8 * 1010)
            self.assertAlmostEqual(fs, 500.0)
            self.assertIn(meta["channel"], ("EHZ", "EHN", "EHE"))
            self.assertEqual(meta["station"].strip(), "00253")
            # values must decode to sane floats around the 2 Hz sine
            self.assertTrue(all(abs(v) < 5000 for v in vals[:2000]))
            self.assertAlmostEqual(max(abs(v) for v in vals[:1010]), 1000.0,
                                   delta=100.0)

    def test_wrong_order_heuristic(self):
        """The reader must detect the true (big-endian) byte order even when
        the blockette claims little-endian, as the real Guralp files do."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "test.mseed")
            write_test_mseed(p, ["EHZ", "EHN", "EHE"], word_order=1)
            vals, fs, meta = read_mseed(p)
            self.assertAlmostEqual(max(abs(v) for v in vals[:1010]), 1000.0,
                                   delta=150.0)

    def test_bad_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "junk.mseed")
            with open(p, "wb") as fh:
                fh.write(b"not a mseed file at all" * 10)
            with self.assertRaises(MseedError):
                read_mseed(p)


def write_test_sg2(path, fs=500.0, n_samples=3000, order=("N", "E", "Z")):
    """Write a minimal SEG-2 file in the field layout (float32 LE, one
    NOTE field per trace saying which component it is)."""
    endian = "<"
    with open(path, "wb") as fh:
        # file descriptor block (32 bytes)
        fd = bytearray(32)
        fd[0:2] = b"U:"
        struct.pack_into(endian + "H", fd, 4, 12)          # pointer block size
        struct.pack_into(endian + "H", fd, 6, 3)           # 3 traces
        fd[8] = 1
        fd[9] = 0                                          # string terminator
        fd[11] = 2
        fd[12:14] = b"\r\n"                               # line terminator
        fh.write(bytes(fd))
        # trace pointer sub-block (3 x u32, patched later)
        ptr_off = 32
        ptrs = [0, 0, 0]
        fh.write(struct.pack(endian + "3L", *ptrs))
        # file free-form block: end marker (u16 length 0)
        ff_off = fh.tell()
        fh.write(struct.pack(endian + "H", 0))
        def ff_field(key, value):
            """One SEG-2 free-form field: u16 length (INCLUDING the 2-byte
            length prefix itself, per the SEG-2 spec) + 'KEY value' + NUL."""
            body = key + b" " + value + b"\x00"
            return struct.pack(endian + "H", len(body) + 2) + body

        # per-trace blocks
        for i, comp in enumerate(order):
            ptrs[i] = fh.tell()
            ff = (ff_field(b"ACQUISITION_DATE", b"10/02/2026")
                  + ff_field(b"SAMPLE_INTERVAL", b"0.002")
                  + ff_field(b"NOTE", b"E1000253." + comp.encode()))
            desc_size = 32 + len(ff)
            desc = bytearray(32)
            struct.pack_into(endian + "H", desc, 0, 0x4422)
            struct.pack_into(endian + "H", desc, 2, desc_size)
            struct.pack_into(endian + "L", desc, 8, n_samples)
            desc[12] = 4                                  # float32
            fh.write(bytes(desc))
            fh.write(ff)
            # data: sine waves, different per component
            for k in range(n_samples):
                f = {0: 1.5, 1: 1.3, 2: 2.0}[i]
                v = 1000.0 * math.sin(2 * math.pi * f * k / fs)
                fh.write(struct.pack(endian + "f", v))
        # patch trace pointers
        with open(path, "r+b") as fh2:
            fh2.seek(ptr_off)
            fh2.write(struct.pack(endian + "3L", *ptrs))


class TestSg2Io(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "test.sg2")
            write_test_sg2(p, fs=500.0, n_samples=3000)
            traces, meta = read_sg2(p)
            self.assertEqual(len(traces), 3)
            self.assertEqual(meta["n_traces"], 3)
            self.assertEqual([t.channel for t in traces], ["N", "E", "Z"])
            self.assertAlmostEqual(traces[0].fs, 500.0)
            self.assertEqual(len(traces[0].samples), 3000)
            # vertical trace (Z) is the 2 Hz sine -> peak at 1000 near 1/4 cycle
            zt = [t for t in traces if t.channel == "Z"][0]
            self.assertAlmostEqual(max(abs(v) for v in zt.samples), 1000.0,
                                   delta=100.0)

    def test_manual_order(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "test.sg2")
            write_test_sg2(p, fs=500.0, n_samples=3000)
            traces, _ = read_sg2(p, order=("Z", "N", "E"))
            self.assertEqual([t.channel for t in traces], ["Z", "N", "E"])

    def test_bad_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "junk.sg2")
            with open(p, "wb") as fh:
                fh.write(b"\x00" * 128)
            with self.assertRaises(Sg2Error):
                read_sg2(p)


class TestEqdIo(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "test.eqd")
            write_test_eqd(p, fs=500.0, n_samples=3000)
            z, n, e, fs, meta = read_eqd(p)
            self.assertEqual(len(z), 3000)
            self.assertEqual(len(n), 3000)
            self.assertEqual(len(e), 3000)
            self.assertAlmostEqual(fs, 500.0)
            self.assertEqual(meta["channels"], 3)
            self.assertAlmostEqual(z[0], 0.0, delta=5.0)
            # quarter cycle of the 2 Hz vertical sine at 500 Hz = sample 62.5
            self.assertAlmostEqual(z[62], 2000.0, delta=150.0)

    def test_bad_magic(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "bad.eqd")
            with open(p, "wb") as fh:
                fh.write(b"\x00\x00" + b"\x00" * 0x200)
            with self.assertRaises(EqdError):
                read_eqd(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
