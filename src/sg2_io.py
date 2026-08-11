"""
sg2_io.py
=========
Pure-standard-library reader for SEG-2 (.sg2) files - the format written by
SeisPrb from the .eqd raw recordings.

A single .sg2 file contains ALL three components as separate traces (Z, N, E).
The trace component is identified automatically from each trace's NOTE
header field (e.g. "E1000253.N", "E1000253.Z", "E1000253.E"); when no NOTE is
present the conventional order (trace 0 = Z, 1 = N, 2 = E) is used, and the
caller can always override the assignment manually.

Format (SEG-2 revision 1, as parsed by ObsPy's seg2 reader):

  File descriptor block (32 bytes):
     0-1  "U:"              (0x55 0x3A = little endian, 0x3A 0x55 = big)
     2-3  revision          (u16)
     4-5  size of trace pointer sub-block (u16)
     6-7  number of traces  (u16)
     8    size of string terminator
     9-10 string terminator chars
     11   size of line terminator
     12-13 line terminator chars
     14-31 reserved
  Trace pointer sub-block: N x u32 byte offsets to each trace descriptor
  Free-form header fields (u16 length prefix + text + NUL; 0 ends the block)
  Per trace:
     32-byte trace descriptor (id 0x4422, size, samples, format code)
     free-form header (size - 32 bytes)
     data: float32 / int16 / int32 / float64 samples

Data format codes: 1=int16, 2=int32, 3=SEG2 IEEE float32 (3-byte, rare),
4=float32, 5=float64.
"""

import os
import struct


class Sg2Error(Exception):
    """Raised when an .sg2 / SEG-2 file cannot be parsed."""


class Trace:
    """One trace (channel) of an SEG-2 file."""

    def __init__(self, channel, samples, fs, note, start_time):
        self.channel = channel        # "Z", "N", "E" or a raw label
        self.samples = samples        # list of floats
        self.fs = float(fs)
        self.note = note
        self.start_time = start_time


def _clean_ascii(b):
    return "".join(chr(c) for c in b if 32 <= c < 127).strip()


def _read_free_form(buf, endian, string_term):
    """Parse SEG-2 free-form fields into a dict.

    Each field: u16 length prefix + text + string terminator.
    A length of 0 marks the end of the block.
    """
    fields = {}
    off = 0
    n = len(buf)
    while off + 2 <= n:
        slen = struct.unpack_from(endian + "H", buf, off)[0]
        if slen == 0:
            break
        if off + slen > n:
            break
        raw = buf[off + 2:off + slen]
        # strip the string terminator
        if string_term:
            raw = raw.split(string_term, 1)[0]
        text = _clean_ascii(raw)
        key, _, value = text.partition(" ")
        if key:
            fields.setdefault(key, value)
        off += slen
    return fields


def read_sg2(path, order=None):
    """Read a .sg2 file and return (traces, meta).

    ``traces`` is a list of Trace objects in file order.
    ``order`` is an optional 3-tuple of component letters (Z, N, E) to
    assign to traces 0, 1, 2 - overriding auto-detection.
    """
    if not os.path.exists(path):
        raise Sg2Error("file not found: " + path)
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 64:
        raise Sg2Error("file too small to be SEG-2: " + os.path.basename(path))

    # ---- file descriptor block --------------------------------------------
    block = data[0:32]
    if block[0:2] == b"U:":
        endian = "<"
    elif block[1::-1] == b"U:":
        endian = ">"
    else:
        raise Sg2Error("not a SEG-2 file (bad descriptor id): "
                       + os.path.basename(path))
    ptr_block_size = struct.unpack_from(endian + "H", block, 4)[0]
    n_traces = struct.unpack_from(endian + "H", block, 6)[0]
    str_term_size = block[8]
    str_term = block[9:9 + str_term_size] if str_term_size in (1, 2) else b""
    if ptr_block_size <= 0 or ptr_block_size % 4:
        raise Sg2Error("invalid trace pointer sub-block size %d"
                       % ptr_block_size)
    if n_traces <= 0 or n_traces > 512:
        raise Sg2Error("implausible trace count %d" % n_traces)

    # ---- trace pointer sub-block ------------------------------------------
    ptrs = struct.unpack_from(endian + "L" * n_traces, data, 32)
    file_off = 32 + ptr_block_size
    if file_off > len(data):
        raise Sg2Error("truncated SEG-2 header")

    # ---- file free-form header (informational) -----------------------------
    ff_end = ptrs[0] if ptrs[0] > file_off else file_off
    file_fields = _read_free_form(data[file_off:min(ff_end, len(data))],
                                  endian, str_term)
    start_time = file_fields.get("ACQUISITION_DATE", "")
    st_time = file_fields.get("ACQUISITION_TIME", "")
    if start_time and st_time:
        start_time = start_time + " " + st_time

    # ---- traces ------------------------------------------------------------
    traces = []
    for i, ptr in enumerate(ptrs):
        if ptr + 32 > len(data):
            raise Sg2Error("trace %d pointer out of range" % (i + 1))
        desc = data[ptr:ptr + 32]
        if struct.unpack_from(endian + "H", desc, 0)[0] != 0x4422:
            raise Sg2Error("trace %d has an invalid descriptor id" % (i + 1))
        size_this = struct.unpack_from(endian + "H", desc, 2)[0]
        n_samples = struct.unpack_from(endian + "L", desc, 8)[0]
        fmt_code = desc[12]
        if size_this < 32:
            raise Sg2Error("trace %d has an invalid header size" % (i + 1))
        hdr_end = ptr + size_this
        trace_fields = _read_free_form(data[ptr + 32:hdr_end], endian, str_term)

        sample_size, dtype = _fmt_spec(fmt_code, endian)
        data_start = hdr_end
        data_end = data_start + n_samples * sample_size
        if data_end > len(data):
            raise Sg2Error("trace %d data exceeds the file size" % (i + 1))
        samples = _decode_data(data[data_start:data_end], n_samples, dtype,
                               fmt_code, endian)

        note = trace_fields.get("NOTE", "") or ""
        channel = _component_from_note(note)
        if not channel:
            channel = {0: "Z", 1: "N", 2: "E"}.get(i, "CH%d" % (i + 1))
        interval = trace_fields.get("SAMPLE_INTERVAL", "")
        fs = 1.0 / float(interval) if interval else 500.0
        if not (0.1 < fs <= 50000):
            fs = 500.0
        traces.append(Trace(channel, samples, fs, note, start_time))

    # ---- optional manual component order -----------------------------------
    if order is not None:
        if len(order) != len(traces):
            raise Sg2Error("component order must match the trace count")
        for tr, comp in zip(traces, order):
            tr.channel = comp

    meta = {
        "n_traces": n_traces,
        "start_time": start_time,
        "file_fields": file_fields,
        "endian": "little" if endian == "<" else "big",
    }
    return traces, meta


def _fmt_spec(fmt_code, endian):
    if fmt_code == 1:
        return 2, "i2"
    if fmt_code == 2:
        return 4, "i4"
    if fmt_code == 4:
        return 4, "f4"
    if fmt_code == 5:
        return 8, "f8"
    if fmt_code == 3:
        return 2, "i2"  # SEG2 3-byte float: handled specially in _decode_data
    raise Sg2Error("unsupported SEG-2 data format code %d" % fmt_code)


def _decode_data(buf, n, dtype, fmt_code, endian):
    if fmt_code == 3:
        # IEEE float32 stored in 3 bytes: sign + 8-bit exponent + 23-bit
        # mantissa, packed in blocks of 5 int16 words (10 bytes): one
        # exponent word (4 nibbles) + 4 one's-complement sample words.
        out = []
        n_blocks = min(n, len(buf) // 10) // 4
        for blk in range(n_blocks):
            base = blk * 5                       # word index of the block
            exp_word = struct.unpack_from(endian + "H", buf, base * 2)[0]
            exps = [(exp_word >> s) & 0xF for s in (0, 4, 8, 12)]
            for k in range(4):
                raw = struct.unpack_from(endian + "i2", buf,
                                         (base + 1 + k) * 2)[0]
                if raw < 0:
                    raw += 1  # one's complement correction
                out.append(raw * (2.0 ** (exps[k] - 15)))
        return out
    ch = "h" if dtype == "i2" else "i" if dtype == "i4" else \
         "f" if dtype == "f4" else "d"
    size = struct.calcsize(endian + ch)
    n_avail = len(buf) // size
    cnt = min(n, n_avail)
    if cnt <= 0:
        return []
    vals = list(struct.unpack_from(endian + str(cnt) + ch, buf, 0))
    if fmt_code in (1, 2, 3):
        return vals
    return [0.0 if (v != v or abs(v) > 1e300) else v for v in vals]


def _component_from_note(note):
    """Guess the component letter (Z / N / E) from a trace NOTE string."""
    if not note:
        return None
    upper = note.upper()
    # "STATION.COMPONENT" style, e.g. "E1000253.N"
    for token in (".Z", ".N", ".E"):
        if upper.endswith(token) or token in upper:
            return token[-1]
    # words like "VERTICAL", "NORTH", "EAST"
    for word, comp in (("VERTICAL", "Z"), ("UP", "Z"), ("NORTH", "N"),
                       ("EAST", "E"), ("SOUTH", "N"), ("WEST", "E")):
        if word in upper:
            return comp
    # a trailing component letter after a clear delimiter (., -, _, space)
    for delim in (".", "-", "_", " "):
        if delim in upper:
            tail = upper.rsplit(delim, 1)[1]
            if len(tail) == 1 and tail in "ZNE":
                return tail
            if tail and tail[-1] in "ZNE":
                return tail[-1]
    return None


def load_sg2_components(path, order=None):
    """Read a .sg2 file and return a ThreeChannel (z, n, e) using the
    auto-detected component order, or the explicit ``order`` if given."""
    from hvsr_io import ThreeChannel
    from hvsr_io import DataError
    try:
        traces, meta = read_sg2(path, order=order)
    except Sg2Error as exc:
        raise DataError(str(exc))
    if len(traces) < 3:
        raise DataError("SEG-2 file has %d traces - expected 3 components"
                        % len(traces))
    fs = traces[0].fs
    by_comp = {}
    for tr in traces:
        by_comp.setdefault(tr.channel, tr.samples)
    z = by_comp.get("Z", traces[0].samples)
    n = by_comp.get("N", traces[1].samples)
    e = by_comp.get("E", traces[2].samples)
    return ThreeChannel(z, n, e, fs, os.path.basename(path))
