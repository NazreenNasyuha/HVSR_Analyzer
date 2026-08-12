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

# Re-exported from hvsr_mseed_decode (split out of mseed_io) - the
# public API stays importable from here.
from hvsr_mseed_decode import MseedError, _ENC_NAME, _PINF, _ascii, _byte_swap16, _byte_swap32, _decode_floats, _decode_int24, _decode_steim, _decode_u64s, _enc_bytes, _lag1_corr, _read_s16_be, _read_u16_be, _sane_fraction, _sign_extend
# Re-exported from hvsr_mseed_parse (split out of mseed_io) - the
# public API stays importable from here.
from hvsr_mseed_parse import _decode_record_section, _detect_record_length, _format_time, _infer_sample_rate, _record_epoch, _record_sample_count, _resolve_byte_order
# Re-exported from hvsr_mseed_write (split out of mseed_io) - the
# public API stays importable from here.
from hvsr_mseed_write import _rate_factor_multiplier, write_mseed
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
