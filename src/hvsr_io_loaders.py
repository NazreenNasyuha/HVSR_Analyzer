"""
hvsr_io_loaders.py
==================
The file loaders: read_three_channel / read_single_column (text), plus
load_three_files, load_mseed, load_eqd, load_sg2 and the auto_load
dispatcher that picks a loader from the file extension.

Split out of hvsr_io.py.
"""


import os
from hvsr_io_data import (DataError, ThreeChannel, _is_comment,
                          _parse_sample_rate, _split_row, assign_components)

# miniSEED file extensions that carry one binary channel per file; a trio of
# these routes to the binary reader instead of the text column parser.
_MSEED_EXTS = {".mseed", ".miniseed"}

def read_three_channel(path):
    """Read a single file holding Z, N, E columns (at least 3 columns)."""
    rows = []
    fs = None
    first_col_time = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or _is_comment(line):
                continue
            rate = _parse_sample_rate(line)
            if rate:
                fs = rate
                continue
            parts = _split_row(line)
            if not parts:
                continue
            if all(isinstance(p, float) for p in parts):
                rows.append(parts)
            else:
                continue  # header or junk row

    if not rows:
        raise DataError("no numeric data rows found in " + os.path.basename(path))
    ncol = len(rows[0])
    if ncol < 3:
        raise DataError(
            "expected at least 3 columns (Z N E) in %s but found %d"
            % (os.path.basename(path), ncol)
        )

    # Detect a time column: strictly increasing with a (nearly) constant step
    # across the whole file (not just the first rows), so a ramping data
    # channel that only looks linear locally is not mistaken for a time axis.
    first_col_time = False
    dts = []
    if len(rows) >= 3:
        dts = [rows[i + 1][0] - rows[i][0] for i in range(len(rows) - 1)]
        if all(d > 0.0 for d in dts):
            d0 = dts[0]
            if all(abs(d - d0) <= 1e-9 * max(1.0, abs(d0)) for d in dts):
                first_col_time = True

    if fs is None and first_col_time:
        dt = dts[0]
        if dt > 0:
            fs = 1.0 / dt

    if fs is None:
        raise DataError(
            "cannot determine the sampling rate. Add a line like 'dt=0.01' or "
            "'fs=100' at the top of the file, or include a time column."
        )

    # Skip a leading time column when one was detected: it is used only to
    # infer the sampling interval, so the Z N E data start at column 1.
    use_time_col = first_col_time and ncol >= 4
    z = [r[1] if use_time_col else r[0] for r in rows]
    n = [r[2] if use_time_col else r[1] for r in rows]
    e = [r[3] if use_time_col else r[2] for r in rows]
    return ThreeChannel(z, n, e, fs, os.path.basename(path))

def read_single_column(path):
    """Read a one-column file, honouring comment / metadata lines."""
    values = []
    fs = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or _is_comment(line):
                continue
            rate = _parse_sample_rate(line)
            if rate:
                fs = rate
                continue
            parts = _split_row(line)
            if len(parts) == 1 and isinstance(parts[0], float):
                values.append(parts[0])
    if not values:
        raise DataError("no numeric values found in " + os.path.basename(path))
    return values, fs

def load_three_files(z_path, n_path, e_path):
    """Load three separate component files.  Returns a ThreeChannel."""
    zv, zfs = read_single_column(z_path)
    nv, nfs = read_single_column(n_path)
    ev, efs = read_single_column(e_path)
    rates = [r for r in (zfs, nfs, efs) if r]
    fs = rates[0] if rates else None
    if fs is None:
        raise DataError("sampling rate not found; add 'fs=100' to one of the files")
    return ThreeChannel(zv, nv, ev, fs, os.path.basename(z_path))

def load_mseed(path):
    """Read a miniSEED file (one channel) into (values, fs, meta)."""
    from mseed_io import read_mseed
    try:
        return read_mseed(path)
    except Exception as exc:
        raise DataError("miniSEED read failed: %s" % exc)

def load_eqd(path, swap_h=False):
    """Read an .eqd 3-component recording into a ThreeChannel.

    The default channel order is Z, N, E; ``swap_h`` swaps N and E.
    """
    from eqd_io import read_eqd, EqdError
    try:
        order = ("Z", "E", "N") if swap_h else ("Z", "N", "E")
        z, n, e, fs, meta = read_eqd(path, order=order)
    except EqdError:
        raise
    except Exception as exc:
        raise DataError(".eqd read failed: %s" % exc)
    return ThreeChannel(z, n, e, fs, os.path.basename(path))

def load_sg2(path, swap_h=False):
    """Read an SEG-2 (.sg2) file into a ThreeChannel.

    A single .sg2 holds all three traces; the components are detected
    automatically from each trace's NOTE field (e.g. "E1000253.N").
    ``swap_h`` swaps N and E as a manual fallback.
    """
    from sg2_io import read_sg2
    try:
        traces, _meta = read_sg2(path)
        if swap_h:
            for tr in traces:
                if tr.channel == "N":
                    tr.channel = "E"
                elif tr.channel == "E":
                    tr.channel = "N"
        by_comp = {}
        for tr in traces:
            by_comp.setdefault(tr.channel, tr.samples)
        if len(traces) < 3:
            raise DataError("SEG-2 file has %d traces - expected 3 components"
                            % len(traces))
        z = by_comp.get("Z", traces[0].samples)
        n = by_comp.get("N", traces[1].samples)
        e = by_comp.get("E", traces[2].samples)
        return ThreeChannel(z, n, e, traces[0].fs,
                            os.path.basename(path))
    except DataError:
        raise
    except Exception as exc:
        raise DataError(".sg2 read failed: %s" % exc)

def _load_mseed_trio(paths):
    """Load an ordered {Z, N, E} mapping of miniSEED files into a
    ThreeChannel via the binary reader (one channel per file).

    Shared by the explicit and non-explicit 3-file paths of auto_load.
    """
    vals, fs = {}, None
    for c in "ZNE":
        v, f, _meta = load_mseed(paths[c])
        vals[c] = v
        fs = f if fs is None else fs
    if fs is None:
        raise DataError("sampling rate not found in the miniSEED headers")
    return ThreeChannel(vals["Z"], vals["N"], vals["E"], fs,
                        os.path.basename(paths["Z"]))


def auto_load(file_paths, explicit=None, swap_h=False):
    """Load a set of files into a ThreeChannel.

    - If 1 file is an .eqd or .sg2 it is read as a 3-component recording
      (Z, N, E; .sg2 components come from each trace's NOTE field).
    - If 3 files are miniSEED/text single-component files they are assigned
      to Z / N / E by name; if the names are not informative, alphabetical
      order Z, N, E is used.
    - If 1 text file is given it must contain at least 3 columns (Z N E).
    """
    if explicit:
        z, n, e = explicit
        # a single .eqd / .sg2 file already holds all three components; if it
        # was dropped into the Z slot alongside stray N/E files, just use it
        for p in (z, n, e):
            if os.path.splitext(p)[1].lower() in (".eqd", ".sg2"):
                return (load_eqd(p, swap_h=swap_h)
                        if p.lower().endswith(".eqd")
                        else load_sg2(p, swap_h=swap_h))
        # three miniSEED files use the binary reader (one channel each);
        # route by extension exactly like the non-explicit 3-file path
        exts = {os.path.splitext(p)[1].lower() for p in (z, n, e)}
        if exts <= _MSEED_EXTS and exts:
            return _load_mseed_trio({"Z": z, "N": n, "E": e})
        if exts & _MSEED_EXTS:
            raise DataError(
                "the 3 selected files mix binary miniSEED with text files - "
                "select either 3 miniSEED files or 3 text files")
        return load_three_files(z, n, e)

    if len(file_paths) == 1:
        p = file_paths[0]
        ext = os.path.splitext(p)[1].lower()
        if ext == ".eqd":
            return load_eqd(p, swap_h=swap_h)
        if ext == ".sg2":
            return load_sg2(p, swap_h=swap_h)
        if ext in (".mseed", ".miniseed"):
            raise DataError(
                "one miniSEED file holds a single component - select the Z, N "
                "and E files together, or pick a 3-column text file")
        return read_three_channel(p)

    if len(file_paths) == 3:
        # assign by filename (or fill the empty slots in the given order),
        # then route by extension: a miniSEED trio uses the binary reader
        mapping = assign_components(file_paths)
        exts = {os.path.splitext(mapping[c])[1].lower() for c in "ZNE"}
        if exts <= _MSEED_EXTS and exts:
            return _load_mseed_trio(mapping)
        if exts & _MSEED_EXTS:
            raise DataError(
                "the 3 selected files mix binary miniSEED with text files - "
                "select either 3 miniSEED files or 3 text files")
        return load_three_files(mapping["Z"], mapping["N"], mapping["E"])

    raise DataError(
        "expected 1 file (3-column text or .eqd) or 3 files (one per "
        "component), got %d" % len(file_paths)
    )
