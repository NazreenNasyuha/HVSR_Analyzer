#!/usr/bin/env python
"""
make_examples.py
================
Regenerates the three bundled example signals used by the first-time-user
tutorial (docs/TUTORIAL.md):

    examples/example.eqd        - .eqd raw 3-component recording
    examples/example_Z.mseed    - miniSEED vertical component
    examples/example_N.mseed    - miniSEED north component
    examples/example_E.mseed    - miniSEED east component
    examples/example.sg2        - SEG-2 file with three traces (Z, N, E)

All files are generated from the SAME synthetic microtremor recording with a
known 2 Hz resonance (see src/make_sample_data.py), so the tutorial walks the
user through the same analysis regardless of the format chosen.

Run:  python scripts/make_examples.py
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from make_sample_data import make_station          # noqa: E402

FS = 500.0        # sample rate, Hz (matches the field Guralp rate)
DURATION = 120.0  # seconds
F0 = 2.0          # known resonance, Hz
STATION = "EX001"


def write_eqd(path, z, n, e, fs=FS):
    """Write the .eqd raw format: 3 interleaved int16 LE channels."""
    with open(path, "wb") as fh:
        fh.write(b"\xed\xad")
        fh.write(struct.pack(">H", 3))            # channels
        fh.write(struct.pack(">H", int(fs)))      # rate
        fh.write(b"\x00\x01\x00\x07\x00\x12")  # misc header fields
        fh.write(b"\x00" * (0x100 - 12))          # pad to data offset
        for i in range(len(z)):
            def clip(v):
                return max(-32767, min(32767, int(round(v * 2000.0))))
            fh.write(struct.pack("<hhh", clip(z[i]), clip(n[i]), clip(e[i])))


def write_sg2(path, z, n, e, fs=FS, order=("Z", "N", "E")):
    """Write a minimal SEG-2 file: float32 LE, one NOTE field per trace."""
    endian = "<"
    comps = {"Z": z, "N": n, "E": e}
    with open(path, "wb") as fh:
        fd = bytearray(32)
        fd[0:2] = b"U:"
        struct.pack_into(endian + "H", fd, 4, 12)   # pointer block size
        struct.pack_into(endian + "H", fd, 6, 3)    # 3 traces
        fd[8] = 1
        fd[9] = 0                                   # string terminator
        fd[11] = 2
        fd[12:14] = b"\r\n"
        fh.write(bytes(fd))
        ptr_off = 32
        ptrs = [0, 0, 0]
        fh.write(struct.pack(endian + "3L", *ptrs))
        fh.write(struct.pack(endian + "H", 0))      # file FF block end

        def ff_field(key, value):
            body = key + b" " + value + b"\x00"
            return struct.pack(endian + "H", len(body) + 2) + body

        for i, comp in enumerate(order):
            ptrs[i] = fh.tell()
            ff = (ff_field(b"ACQUISITION_DATE", b"11/08/2026")
                  + ff_field(b"SAMPLE_INTERVAL",
                             (b"%.6f" % (1.0 / fs)).rstrip(b"0").rstrip(b"."))
                  + ff_field(b"NOTE", STATION.encode() + b"." + comp.encode()))
            desc_size = 32 + len(ff)
            desc = bytearray(32)
            struct.pack_into(endian + "H", desc, 0, 0x4422)
            struct.pack_into(endian + "H", desc, 2, desc_size)
            struct.pack_into(endian + "L", desc, 8, len(comps[comp]))
            desc[12] = 4                            # float32
            fh.write(bytes(desc))
            fh.write(ff)
            for v in comps[comp]:
                fh.write(struct.pack(endian + "f", v))
        with open(path, "r+b") as fh2:
            fh2.seek(ptr_off)
            fh2.write(struct.pack(endian + "3L", *ptrs))


def write_mseed_trio(folder, z, n, e, fs=FS):
    """Write three single-component miniSEED files (Z / N / E)."""
    from mseed_io import write_mseed
    out = {}
    for comp, vals in (("Z", z), ("N", n), ("E", e)):
        p = os.path.join(folder, "example_%s.mseed" % comp)
        write_mseed(p, vals, fs, "EH" + comp, station=STATION, network="XX")
        out[comp] = p
    return out


def make_examples(out_dir):
    """Generate all example signals into out_dir. Returns dict of paths."""
    os.makedirs(out_dir, exist_ok=True)
    z, n, e = make_station(duration=DURATION, fs=FS, f0=F0, seed=42)
    paths = {
        "eqd": os.path.join(out_dir, "example.eqd"),
        "sg2": os.path.join(out_dir, "example.sg2"),
    }
    write_eqd(paths["eqd"], z, n, e)
    write_sg2(paths["sg2"], z, n, e)
    paths.update(write_mseed_trio(out_dir, z, n, e))
    return paths


def validate(paths):
    """Load each example with the app's own readers and check f0 ~ 2 Hz."""
    from hvsr_io import auto_load, DataError
    from hvsr_engine import preprocess, analyze
    tests = [
        ("eqd", [paths["eqd"]]),
        ("sg2", [paths["sg2"]]),
        ("mseed trio", [paths["Z"], paths["N"], paths["E"]]),
    ]
    ok = True
    for label, files in tests:
        try:
            data = auto_load(files)
            # max_fs=250 matches the GUI default: 500 Hz recordings are
            # decimated to 250 Hz before the band-pass (see hvsr_gui).
            clean, _meta = preprocess(data, f_low=0.2, f_high=20.0,
                                      max_fs=250.0)
            res = analyze(clean, station=label)
            good = abs(res.f0 - F0) < 0.3
            ok = ok and good
            print("  %-11s fs=%.0f n=%d  f0=%.3f Hz  %s"
                  % (label, data.fs, data.n_samples, res.f0,
                     "OK" if good else "FAIL"))
        except Exception as exc:
            ok = False
            print("  %-11s ERROR: %s" % (label, exc))
    return ok


if __name__ == "__main__":
    out = os.path.join(ROOT, "examples")
    print("Generating example signals in:", out)
    paths = make_examples(out)
    for key, p in sorted(paths.items()):
        print("  %-10s %s (%d bytes)" % (key, p, os.path.getsize(p)))
    print("Validating with the app's own readers...")
    if not validate(paths):
        sys.exit(1)
    print("ALL EXAMPLES VALIDATED")
