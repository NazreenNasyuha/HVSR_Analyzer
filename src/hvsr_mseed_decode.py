"""
hvsr_mseed_decode.py
====================
Sample-level miniSEED decoding (pure standard library):

- _decode_steim (STEIM-1/2), _decode_int24, _decode_floats, _decode_u64s,
  plus byte-swap / sign-extend primitives,
- MseedError, the shared exception type, and the small scalar readers.

Split out of mseed_io.py.
"""


import struct

class MseedError(Exception):
    """Raised when a miniSEED file cannot be parsed."""

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
    """Convert ``n`` little-endian 16-bit samples to host order (numpy-free)."""
    out = [0] * n
    for i in range(n):
        j = i * 2
        out[i] = (buf[j] << 8) | buf[j + 1]
    return out

def _byte_swap32(buf, n):
    """Convert ``n`` little-endian 32-bit samples to host order (numpy-free)."""
    out = [0] * n
    for i in range(n):
        j = i * 4
        out[i] = (buf[j] << 24) | (buf[j + 1] << 16) | (buf[j + 2] << 8) | buf[j + 3]
    return out

def _decode_int24(buf, n, little):
    """Decode ``n`` signed 24-bit integers (miniSEED packs them on 3-byte
    boundaries, so they cannot be unpacked directly by struct)."""
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

def _ascii(buf, start, end):
    """Decode a miniSEED ASCII field, replacing invalid bytes instead of
    raising, so a slightly damaged header still parses."""
    try:
        return buf[start:end].decode("ascii", "replace").strip()
    except Exception:
        return ""

def _read_u16_be(buf, off):
    """Read an unsigned 16-bit big-endian field (miniSEED fixed header)."""
    return struct.unpack_from(">H", buf, off)[0]

def _read_s16_be(buf, off):
    """Read a signed 16-bit big-endian field (miniSEED fixed header)."""
    return struct.unpack_from(">h", buf, off)[0]

def _enc_bytes(encoding):
    """Bytes per sample for a miniSEED data-encoding code (1=16-bit int,
    2=24-bit, 3=32-bit int, 4=IEEE float32, 5=IEEE float64, 10/11=STEIM)."""
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

def _decode_u64s(buf, n, little):
    """Decode ``n`` 64-bit values (used by the STEIM-2 compression path)."""
    out = [0] * n
    for i in range(n):
        j = i * 8
        if little:
            out[i] = struct.unpack_from("<Q", buf, j)[0]
        else:
            out[i] = struct.unpack_from(">Q", buf, j)[0]
    return out
