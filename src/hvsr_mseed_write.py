"""
hvsr_mseed_write.py
===================
miniSEED writer (pure standard library): write_mseed emits a float32
record stream with Blockette 1000 / 100 headers, plus the
_rate_factor_multiplier helper.

Split out of mseed_io.py.
"""


from fractions import Fraction
import math
import struct
from hvsr_mseed_decode import MseedError

def write_mseed(path, values, fs, channel, station="STA", network="XX",
                location="", record_length=4096, little=False):
    """Write a standard miniSEED file of float32 samples.

    Layout (standard, data-only): 48-byte fixed header + blockette 1000
    (8 bytes) at offset 48, data at offset 56.  The Guralp files use the same
    56-byte header, which is why geopsy-hv accepts both.

    The sampling rate is encoded exactly via the rate factor / multiplier
    pair (e.g. 500 Hz / 3 -> factor=-3, multiplier=500 for 166.67 Hz) so
    that Geopsy's window prime-factor check sees the true rate instead of a
    rounded (possibly prime) integer like 167.
    """
    enc = 4            # IEEE float32
    word_order = 1 if little else 0
    if record_length not in (256, 512, 1024, 2048, 4096, 8192, 16384):
        record_length = 4096
    bod = 56
    per_rec = (record_length - bod) // 4
    if per_rec <= 0:
        raise MseedError("record length too small")

    # Fixed header layout: station at 8-13, channel at 15-18, network at
    # 18-20, year at 20-21, day at 22-23, hour 24 / minute 25 / second 26,
    # per-record sample count at 30-31, sampling rate at 32-33, rate factor
    # at 34-35, multiplier at 36-37, data offset at 44-45 (56), first
    # blockette at 46-47 (48).  This is byte-for-byte the layout ObsPy
    # writes (and therefore what Geopsy's libmseed reads).
    n = len(values)
    n_recs = (n + per_rec - 1) // per_rec
    with open(path, "wb") as fh:
        for r in range(n_recs):
            rec = bytearray(record_length)
            rec[0:6] = ("%06d" % (r + 1)).encode()
            rec[6] = ord("D")
            rec[7] = 0x20
            rec[8:14] = station[:6].ljust(6).encode()
            rec[14] = (location[:1] or " ").ljust(1).encode()[0]
            rec[15:18] = channel[:3].ljust(3).encode()
            rec[18:20] = network[:2].ljust(2).encode()
            struct.pack_into(">H", rec, 20, 2026)    # year
            struct.pack_into(">H", rec, 22, 1)       # day of year
            # start time of this record: base + r * record_duration, with the
            # sub-second fraction in bytes 28-29 (units of 1/10000 s).
            # Correct timestamps let Geopsy stitch the records into one
            # continuous signal instead of seeing 6-second fragments.
            rec_sec = per_rec / float(fs)
            total = r * rec_sec
            hh = int(total // 3600)
            mm = int((total % 3600) // 60)
            ss = int(total % 60)
            frac = int(round((total - int(total)) * 10000))
            rec[24] = hh                      # hour
            rec[25] = mm                      # minute
            rec[26] = ss                      # second
            struct.pack_into(">H", rec, 28, frac)   # sub-second (1/10000 s)
            rec[39] = 1                       # number of blockettes
            start = r * per_rec
            ns = min(per_rec, n - start)
            struct.pack_into(">H", rec, 30, ns)      # samples in record
            # sample rate factor at 32-33, multiplier at 34-35 (the layout
            # ObsPy writes: factor=200, multiplier=1 for a 200 Hz rate).
            fac, mul = _rate_factor_multiplier(fs)
            struct.pack_into(">h", rec, 32, fac)     # rate factor
            struct.pack_into(">h", rec, 34, mul)     # rate multiplier
            struct.pack_into(">H", rec, 44, bod)     # beginning of data
            struct.pack_into(">H", rec, 46, 48)      # first blockette
            # blockette 1000
            struct.pack_into(">H", rec, 48, 1000)
            struct.pack_into(">H", rec, 50, 0)       # next blockette
            rec[52] = enc
            rec[53] = 1 if not little else 0  # 1 = big-endian word order
            rec[54] = int(math.log(record_length, 2))
            rec[55] = 0
            # float32 data
            fmt = "<" if little else ">"
            for k in range(ns):
                v = values[start + k]
                if v != v:
                    v = 0.0
                struct.pack_into(fmt + "f", rec, bod + k * 4, float(v))
            fh.write(bytes(rec))

def _rate_factor_multiplier(fs):
    """Encode a sampling rate as a (factor, multiplier) pair.

    miniSEED stores rate = factor * multiplier when factor > 0, or
    multiplier / |factor| when factor < 0.  A reduced rational form of the
    rate keeps the values small and exact (e.g. 166.67 -> factor=-3,
    multiplier=500 gives 500/3).  Whole rates use factor=rate, multiplier=1
    exactly as ObsPy writes them.
    """
    if fs <= 0:
        return 1, 0
    # try integer rates first (factor=fs, multiplier=1)
    if abs(fs - round(fs)) < 1e-6:
        return int(round(fs)), 1
    # fractional: find the exact reduced rational form (denominator <= 1000),
    # e.g. 500/3 -> factor=-3, multiplier=500.  fractions.Fraction also
    # handles rounded decimal inputs like 166.6667 that a simple tolerance
    # scan would miss (and wrongly turn into 167/1).  The multiplier is the
    # numerator, which must fit the signed-16-bit miniSEED field.
    fr = Fraction(fs).limit_denominator(1000)
    if fr.denominator > 1 and 0 < fr.numerator <= 32767:
        return -fr.denominator, fr.numerator
    return -1, int(round(fs))
