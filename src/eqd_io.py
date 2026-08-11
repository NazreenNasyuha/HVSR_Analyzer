"""
eqd_io.py
=========
Pure-standard-library reader for the ".eqd" raw 3-component format.

Format (reverse-engineered from raw field recordings):

  offset 0     : magic bytes  b"edad"
  offset 2     : u16 BE  number of channels (3)
  offset 4     : u16 BE  sampling rate in Hz (500)
  offset 6..   : more header fields (version / station / sizes)
  offset 0x100 : data - interleaved 16-bit little-endian samples, one per
                 channel in the order  Z, N, E.

For these recordings the only component order that produces a physically
sensible H/V curve is Z=ch0, N=ch1, E=ch2, which is used as the default.
"""

import os
import struct


class EqdError(Exception):
    """Raised when an .eqd file cannot be parsed."""


MAGIC = b"\xed\xad"   # hex bytes 0xED 0xAD
DATA_OFFSET = 0x100


def read_eqd(path, order=("Z", "N", "E")):
    """Read an .eqd file and return (z, n, e, fs, meta).

    ``order`` is a 3-tuple of the component letters assigned to channels
    0, 1, 2 in sequence (default: Z, N, E).
    """
    if not os.path.exists(path):
        raise EqdError("file not found: " + path)
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < DATA_OFFSET + 64:
        raise EqdError("file too small to be an .eqd recording: "
                       + os.path.basename(path))
    if data[0:2] != MAGIC:
        raise EqdError("not an .eqd file (bad magic): " + os.path.basename(path))

    nch = struct.unpack_from(">H", data, 2)[0]
    rate = struct.unpack_from(">H", data, 4)[0]
    if nch not in (1, 2, 3, 4):
        raise EqdError("unexpected channel count %d in %s"
                       % (nch, os.path.basename(path)))
    if not (1 <= rate <= 5000):
        raise EqdError("unexpected sampling rate %d in %s"
                       % (rate, os.path.basename(path)))

    n16 = (len(data) - DATA_OFFSET) // 2
    n_use = n16 - (n16 % nch)
    if n_use <= 0:
        raise EqdError("no data samples in " + os.path.basename(path))

    vals = struct.unpack_from("<%dh" % n_use, data, DATA_OFFSET)

    if nch == 1:
        z = list(vals)
        n = list(vals)
        e = list(vals)
    elif nch == 2:
        z = list(vals[0::2])
        n = list(vals[1::2])
        e = list(vals[1::2])
    else:
        channels = [list(vals[c::nch]) for c in range(min(nch, 3))]
        mapping = {"Z": 0, "N": 1, "E": 2}
        z = channels[mapping.get(order[0], 0)]
        n = channels[mapping.get(order[1], 1)]
        e = channels[mapping.get(order[2], 2)]

    meta = {
        "channels": nch,
        "rate_hz": rate,
        "n_samples": n_use,
        "n_per_channel": n_use // max(1, nch),
    }
    return z, n, e, float(rate), meta
