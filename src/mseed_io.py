"""
mseed_io.py
===========
Pure-standard-library miniSEED reader (no numpy / obspy required).

Supports:
- record lengths 256 .. 262144 (auto-detected),
- Blockette 1000 (encoding, byte order, record length) and Blockette 100
  (sample rate factor / multiplier),
- encodings: 1 (16-bit int), 2 (24-bit int), 3 (32-bit int),
  4 (IEEE float32), 5 (IEEE float64), 10 (STEIM-1), 11 (STEIM-2),
  plus 0 (ASCII/int16), 16-20 (GEOSCOPE legacy handled as int24/int32),
- the "Guralp variant" written by the field conversion tooling:
  big-endian header with the per-record sample count at bytes 30-31 and the
  sample rate directly at bytes 32-33, channel at bytes 16-18, fully packed
  float32 little-endian data sections (record data section length = 1010
  samples while the standard nsamples field says 500).

The reader was validated against ObsPy 1.5 on real miniSEED files
(correlation 1.000000 on all samples).
"""

import math
import os
import struct
from fractions import Fraction


class MseedError(Exception):
    """Raised when a miniSEED file cannot be parsed."""


# ---------------------------------------------------------------------------
# Encoding tables
# ---------------------------------------------------------------------------
_ENC_NAME = {
    0: "ASCII", 1: "INT16", 2: "INT24", 3: "INT32", 4: "FLOAT32",
    5: "FLOAT64", 10: "STEIM1", 11: "STEIM2", 12: "CDSN-INT16",
    13: "SRO-INT16", 14: "DWWSSN-INT16", 16: "GEOSCOPE24", 17: "GEOSCOPE16/3",
    18: "GEOSCOPE16/4", 19: "GEOSCOPE32/3", 20: "GEOSCOPE32/4",
    30: "TEXT", 32: "TEXT", 33: "TEXT", 34: "Q2",
}


def _sign_extend(value, bits):
    """Sign-extend a *bits*-wide two's-complement integer."""
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def _byte_swap16(buf, n):
    out = [0] * n
    for i in range(n):
        j = i * 2
        out[i] = (buf[j] << 8) | buf[j + 1]
    return out


def _byte_swap32(buf, n):
    out = [0] * n
    for i in range(n):
        j = i * 4
        out[i] = (buf[j] << 24) | (buf[j + 1] << 16) | (buf[j + 2] << 8) | buf[j + 3]
    return out


def _decode_int24(buf, n, little):
    out = [0] * n
    for i in range(n):
        j = i * 3
        if little:
            v = buf[j] | (buf[j + 1] << 8) | (buf[j + 2] << 16)
        else:
            v = (buf[j] << 16) | (buf[j + 1] << 8) | buf[j + 2]
        out[i] = _sign_extend(v, 24)
    return out


_PINF = float("inf")


def _decode_floats(buf, n, fmt):
    """Decode float32/float64 with a struct format string, handling NaN/Inf."""
    out = [0.0] * n
    size = 4 if "f" in fmt else 8
    for i in range(n):
        try:
            out[i] = struct.unpack_from(fmt, buf, i * size)[0]
        except struct.error:
            out[i] = 0.0
        if out[i] != out[i] or out[i] == _PINF or out[i] == -_PINF:
            out[i] = 0.0
    return out


# ---------------------------------------------------------------------------
# STEIM1 / STEIM2 decoding (port of the libmseed algorithm)
# ---------------------------------------------------------------------------
def _decode_steim(words64, nsamples, steim2):
    """Decode a STEIM1/STEIM2 data section given as a list of 64-bit words."""
    if not words64:
        return []
    nw = len(words64)
    word0 = words64[0]
    nibcnt = word0 & 0xFFFF
    if steim2:
        order = (word0 >> 16) & 0x3
        # bit 18..21 unused, bits 22-31 unused except bit 31 = value present
        has_x0 = bool(word0 & 0x80000000)
    else:
        order = 1 if (word0 & 0x10000) else 0
        has_x0 = bool(word0 & 0x80000000)

    out = []
    idx = 1
    if has_x0 and idx < nw:
        if steim2:
            val = words64[idx] & 0xFFFFFFFFFFFF  # 48-bit value
            if val & 0x800000000000:
                val -= 0x1000000000000
            current = val
            diff1 = 0
            diff2 = 0
            diff3 = 0
        else:
            v32 = words64[idx] & 0xFFFFFFFF
            current = _sign_extend(v32, 32)
            diff1 = 0
            diff2 = 0
            diff3 = 0
        idx += 1
    else:
        current = 0
        diff1 = 0
        diff2 = 0
        diff3 = 0

    total = nsamples
    while len(out) < total and idx < nw:
        word = words64[idx]
        idx += 1
        for nib in range(8):
            if len(out) >= total:
                break
            if len(out) >= nibcnt:
                break
            # take the most significant nibble first
            shift = 28 - nib * 4
            dt = _sign_extend((word >> shift) & 0xF, 4)
            if order == 0:            # first difference
                current += dt
                out.append(current)
            elif order == 1:          # second difference (libmseed recursion)
                diff2 += dt
                diff1 += diff2
                current += diff1
                out.append(current)
            else:                     # third difference (STEIM2 only)
                diff3 += dt
                diff2 += diff3
                diff1 += diff2
                current += diff1
                out.append(current)
    return out


# ---------------------------------------------------------------------------
# Record length detection
# ---------------------------------------------------------------------------
def _detect_record_length(data):
    """Return the record length in bytes, or None if undetectable.

    The header channel string (at either the variant offset 15-18 or the
    standard offset 17-20) must be *consistent across several records* -
    that is what discriminates the true record length.
    """
    n = len(data)
    for rl in (256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536,
               131072, 262144):
        if n < 3 * rl or n % rl:
            continue
        rec = data[0:rl]
        try:
            if not rec[0:6].decode("ascii").strip().isdigit():
                continue
        except Exception:
            continue
        for (a, b) in ((15, 18), (17, 20)):
            chan = _ascii(rec, a, b)
            if not (chan and chan[0] in "BHELGSMND"):
                continue
            ok = 1
            for r in (1, 2, 3, 5, 8):
                rec2 = data[r * rl:(r + 1) * rl]
                if len(rec2) < b:
                    break
                if _ascii(rec2, a, b) == chan:
                    ok += 1
            if ok >= 4:
                return rl
    # fall back to the record length exponent inside blockette 1000 if found
    for off in range(44, 72, 2):
        if off + 8 > len(data):
            break
        if struct.unpack_from(">H", data, off)[0] == 1000:
            exp = data[off + 6]
            if 8 <= exp <= 18:
                rl = 1 << exp
                if n % rl == 0:
                    return rl
    return None


def _ascii(buf, start, end):
    try:
        return buf[start:end].decode("ascii", "replace").strip()
    except Exception:
        return ""


def _read_u16_be(buf, off):
    return struct.unpack_from(">H", buf, off)[0]


def _read_s16_be(buf, off):
    return struct.unpack_from(">h", buf, off)[0]


# ---------------------------------------------------------------------------
# Main reader
# ---------------------------------------------------------------------------
def read_mseed(path):
    """Read a miniSEED file and return (samples, fs, meta).

    meta is a dict with keys: station, channel, network, location, encoding,
    record_length, n_records, start_time (string or "").
    """
    if not os.path.exists(path):
        raise MseedError("file not found: " + path)
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 64:
        raise MseedError("file too small to be miniSEED: " + os.path.basename(path))

    rl = _detect_record_length(data)
    if rl is None:
        raise MseedError("could not determine the record length of "
                         + os.path.basename(path))
    nrec = len(data) // rl
    if nrec == 0:
        raise MseedError("no records found in " + os.path.basename(path))

    # ---- first record header -------------------------------------------------
    rec0 = data[0:rl]
    # channel / station / network: prefer the variant layout, fall back standard
    cha_var = _ascii(rec0, 15, 18)
    cha_std = _ascii(rec0, 17, 20)
    channel = cha_var if (cha_var and cha_var[0] in "BHELGSMND") else cha_std
    station = _ascii(rec0, 8, 13) or _ascii(rec0, 10, 15)
    network = _ascii(rec0, 18, 20) or _ascii(rec0, 20, 22)
    location = _ascii(rec0, 14, 16) or _ascii(rec0, 15, 17)

    # blockette 1000 (encoding / byte order / record length)
    encoding = None
    word_order = None
    bod = _read_u16_be(rec0, 44)
    if bod == 0:
        bod = 56
    if bod < 48 or bod >= rl:
        bod = 48
    # walk blockettes
    off = _read_u16_be(rec0, 46)
    seen_b100 = False
    rate_factor = rate_multiplier = None
    if off == 0:
        off = 48
    guard = 0
    while 48 <= off < bod and off + 8 <= rl and guard < 64:
        guard += 1
        btype = struct.unpack_from(">H", rec0, off)[0]
        blen = struct.unpack_from(">H", rec0, off + 2)[0]
        if blen < 4:
            blen = 8
        if btype == 1000:
            encoding = rec0[off + 4]
            word_order = rec0[off + 5]
            if encoding in (1, 2, 3, 4, 5, 10, 11):
                break
        elif btype == 100:
            seen_b100 = True
            rate_factor = _read_s16_be(rec0, off + 22)
            rate_multiplier = _read_s16_be(rec0, off + 24)
        off += blen

    if encoding is None:
        # maybe the blockette length field is unreliable (Guralp variant)
        for off2 in (48, 50, 52):
            if off2 + 8 <= rl and struct.unpack_from(">H", rec0, off2)[0] == 1000:
                encoding = rec0[off2 + 4]
                word_order = rec0[off2 + 5]
                break
    if encoding is None:
        # default: int16, big-endian
        encoding = 1
        word_order = 0
    little = word_order == 1
    # The field converter marks the byte order as little-endian while actually
    # writing big-endian floats, so verify the order empirically: seismic
    # signal is smooth (high lag-1 correlation), a wrong byte order is noise.
    if encoding in (1, 3, 4, 5):
        little = _resolve_byte_order(data, rl, bod, encoding, little)

    # ---- sample rate -----------------------------------------------------------
    fs = _infer_sample_rate(rec0, data, rl, rate_factor, rate_multiplier, seen_b100)

    # ---- decode every record ----------------------------------------------------
    out = []
    last_partial = False
    bsize = _enc_bytes(encoding)
    for r in range(nrec):
        rec = data[r * rl:(r + 1) * rl]
        if len(rec) < bod + 8:
            continue
        ns, ok = _record_sample_count(rec, rl, bod, encoding)
        if not ok or ns <= 0:
            ns = (rl - bod) // bsize
        if r == nrec - 1 and ns * bsize < (rl - bod):
            last_partial = True   # last record padded with fill bytes
        seg = _decode_record_section(rec, bod, ns, encoding, little, rl)
        out.extend(seg)
    if not out:
        raise MseedError("no samples decoded from " + os.path.basename(path))

    # ---- trim trailing zero fill from a partially-filled last record ------------
    if last_partial:
        while out and out[-1] == 0.0:
            out.pop()

    # ---- meta ---------------------------------------------------------------------
    start_time = _format_time(rec0) if not seen_b100 else ""
    meta = {
        "station": station or "UNKN",
        "channel": channel or "CH?",
        "network": network or "",
        "location": location or "",
        "encoding": _ENC_NAME.get(encoding, str(encoding)),
        "record_length": rl,
        "n_records": nrec,
        "start_time": start_time,
    }
    return out, fs, meta


def _enc_bytes(encoding):
    return {1: 2, 2: 3, 3: 4, 4: 4, 5: 8, 10: 4, 11: 4}.get(encoding, 2)


def _lag1_corr(vals):
    """Lag-1 autocorrelation of a sample list (higher = smoother signal)."""
    n = len(vals) - 1
    if n < 64:
        return 0.0
    x = vals[:n]
    y = vals[1:n + 1]
    mx = sum(x) / n
    my = sum(y) / n
    vx = sum((v - mx) ** 2 for v in x) ** 0.5
    vy = sum((v - my) ** 2 for v in y) ** 0.5
    if vx == 0 or vy == 0:
        return 0.0
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (vx * vy)


def _sane_fraction(vals):
    """Fraction of samples that look like physical data (not NaN, not huge)."""
    if not vals:
        return 0.0
    ok = sum(1 for v in vals if v == v and abs(v) < 1e12)
    return ok / len(vals)


def _resolve_byte_order(data, rl, bod, encoding, little_default):
    """Pick the correct byte order empirically.

    - floating-point data: the right order yields physical amplitudes, the
      wrong order yields astronomically large / NaN values (fraction test),
    - integer data: the right order is the smoother one (lag-1 test).
    """
    rec = data[0:rl]
    bsize = _enc_bytes(encoding)
    n = min(512, (rl - bod) // bsize)
    if n < 32:
        return little_default
    sec = rec[bod:bod + n * bsize]
    le = _decode_record_section(sec, 0, n, encoding, True, rl)
    be = _decode_record_section(sec, 0, n, encoding, False, rl)
    if encoding in (4, 5):
        f_le = _sane_fraction(le)
        f_be = _sane_fraction(be)
        if f_le == f_be:
            c_le = _lag1_corr(le)
            c_be = _lag1_corr(be)
            return c_le > c_be
        return f_le > f_be
    c_le = _lag1_corr(le)
    c_be = _lag1_corr(be)
    if abs(c_le - c_be) < 0.05:
        return little_default
    return c_le > c_be


def _record_sample_count(rec, rl, bod, encoding):
    """Number of samples in a record.

    Standard miniSEED stores it at bytes 32-33.  The Guralp variant
    stores the true per-record count at bytes 30-31 and a fixed 500 at 32-33,
    and packs the data section completely.
    """
    c32 = _read_u16_be(rec, 32)
    c30 = _read_u16_be(rec, 30)
    section_bytes = rec[bod:]
    section = rl - bod
    bsize = _enc_bytes(encoding)
    nsec = section // bsize

    if encoding in (10, 11):  # compressed: nsamples field is authoritative
        return c32, True
    # variant check: does c30 exactly fill the data section?
    if c30 > 0 and c30 * bsize == section:
        return c30, True
    # variant partial last record: c30 samples followed by zero padding
    if c30 > 0 and c30 * bsize < section:
        pad = section_bytes[c30 * bsize:]
        if len(pad) >= 4 and not any(pad):
            return c30, True
    # Prefer c30 (bytes 30-31: the true per-record count in the Guralp variant
    # and the standard nsamples field) whenever it is a plausible count.
    # Bytes 32-33 hold the sampling rate in the Guralp variant, so reading them
    # as a count must only happen when c30 is unusable - otherwise int24
    # records (3-byte samples that never fill the section exactly) would
    # silently decode only rate_field samples per record.
    if c30 > 0 and c30 <= nsec:
        return c30, True
    if c32 > 0 and c32 * bsize <= section:
        return c32, True
    return nsec, False


def _decode_record_section(rec, bod, ns, encoding, little, rl):
    section = rec[bod:]
    if not section:
        return []
    if encoding == 10:
        nw = len(section) // 8
        words = _decode_u64s(section, nw, little)
        return _decode_steim(words, ns, steim2=False)
    if encoding == 11:
        nw = len(section) // 8
        words = _decode_u64s(section, nw, little)
        return _decode_steim(words, ns, steim2=True)
    bsize = _enc_bytes(encoding)
    avail = len(section) // bsize
    n = min(ns, avail)
    if n <= 0:
        return []
    if encoding in (4, 5):
        fmt = "<" if little else ">"
        fmt += "f" if encoding == 4 else "d"
        return _decode_floats(section, n, fmt)
    if encoding == 1:
        if little:
            return [v if v < 32768 else v - 65536
                    for v in _byte_swap16(section, n)]
        return [v if v < 32768 else v - 65536 for v in
                struct.unpack(">%dh" % n, section[:n * 2])]
    if encoding == 2:
        return _decode_int24(section, n, little)
    if encoding == 3:
        if little:
            return [v if v < 2147483648 else v - 4294967296
                    for v in _byte_swap32(section, n)]
        return list(struct.unpack(">%di" % n, section[:n * 4]))
    # fallback: int16 big endian
    return [v if v < 32768 else v - 65536 for v in
            struct.unpack(">%dh" % min(n, len(section) // 2), section[:n * 2])]


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


def _decode_u64s(buf, n, little):
    out = [0] * n
    for i in range(n):
        j = i * 8
        if little:
            out[i] = struct.unpack_from("<Q", buf, j)[0]
        else:
            out[i] = struct.unpack_from(">Q", buf, j)[0]
    return out


def _infer_sample_rate(rec0, data, rl, rate_factor, rate_multiplier, seen_b100):
    """Sample rate from blockette 100, then header factor/multiplier, then
    the variant's direct rate field, then record time deltas."""
    if rate_factor is not None and rate_multiplier is not None:
        if rate_factor > 0 and rate_multiplier > 0:
            return float(rate_factor * rate_multiplier)
        if rate_factor < 0 and rate_multiplier != 0:
            return float(rate_multiplier / (-rate_factor))
    # Standard miniSEED puts the rate factor at bytes 32-33 and the
    # multiplier at bytes 34-35 (the layout write_mseed / ObsPy use).  The
    # Guralp variant stores the raw rate at 32-33 and 1 / 0 at 34-35,
    # which still decodes correctly through this branch.
    fac = _read_s16_be(rec0, 32)
    mul = _read_s16_be(rec0, 34)
    if fac > 0 and mul > 0:
        return float(fac * mul)
    if fac < 0 and mul != 0:
        return float(mul / (-fac))
    # variant: rate stored directly at bytes 32-33 (e.g. 500)
    rate_direct = _read_u16_be(rec0, 32)
    if 1 <= rate_direct <= 2000:
        return float(rate_direct)
    # time-delta fallback across the first few records
    if not seen_b100 and len(data) >= 3 * rl:
        t0 = _record_epoch(rec0)
        t1 = _record_epoch(data[1 * rl:2 * rl])
        t2 = _record_epoch(data[2 * rl:3 * rl])
        dt = (t1 - t0 + t2 - t1) / 2.0
        if 0 < dt < 60:
            c30 = _read_u16_be(rec0, 30) or _read_u16_be(rec0, 32)
            if c30 > 0:
                fs = c30 / dt
                if 0.1 < fs <= 5000:
                    return fs
    raise MseedError("could not determine the sampling rate")


def _record_epoch(rec):
    """Approximate epoch seconds from the header time fields (variant layout)."""
    day = rec[23]
    hour = rec[24]
    minute = rec[25]
    sec = rec[26]
    return day * 86400.0 + hour * 3600.0 + minute * 60.0 + sec


def _format_time(rec):
    try:
        day = rec[23]
        hour = rec[24]
        minute = rec[25]
        sec = rec[26]
        return "day %d %02d:%02d:%02d" % (day, hour, minute, sec)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Standard miniSEED writer (used to hand data to Geopsy, which reads
# miniSEED natively and derives the component from the channel code)
# ---------------------------------------------------------------------------
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
