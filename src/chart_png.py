"""
chart_png.py
===========
A real PNG encoder built on the standard-library zlib and struct
modules: write_png emits an 8-bit RGB PNG from an iterable of pixel rows.

Split out of chart_render.py.
"""


import struct
import zlib

def write_png(path, width, height, pixel_rows):
    """Write an 8-bit RGB PNG.  pixel_rows is an iterable of rows, each row
    an iterable of (r, g, b) tuples of length `width`."""
    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out

    raw = bytearray()
    for row in pixel_rows:
        raw.append(0)  # filter type: none
        for px in row:
            raw.extend((px[0] & 255, px[1] & 255, px[2] & 255))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = signature
    data += chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(data)
