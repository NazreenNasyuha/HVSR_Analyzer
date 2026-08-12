"""
hvsr_mseed_parse.py
===================
Record-structure and metadata parsing for the miniSEED reader:

- _detect_record_length / _decode_record_section / _resolve_byte_order /
  _record_sample_count : record framing and section decoding,
- _infer_sample_rate : sample rate from Blockette 100 factor/multiplier,
- _record_epoch / _format_time : B-time conversion helpers.

Split out of mseed_io.py.
"""


import struct
from hvsr_mseed_decode import MseedError, _ascii, _byte_swap16, _byte_swap32, _decode_floats, _decode_int24, _decode_steim, _decode_u64s, _enc_bytes, _lag1_corr, _read_s16_be, _read_u16_be, _sane_fraction

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
    """Decode one record's data section (from byte offset ``bod``) into
    ``ns`` samples, dispatching on the miniSEED encoding code."""
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
    """Parse the miniSEED fixed-header start time (bytes 20-29) into a
    (year, julian_day, hour, minute, second, fraction) tuple."""
    try:
        day = rec[23]
        hour = rec[24]
        minute = rec[25]
        sec = rec[26]
        return "day %d %02d:%02d:%02d" % (day, hour, minute, sec)
    except Exception:
        return ""
