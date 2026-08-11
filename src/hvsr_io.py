"""
hvsr_io.py
==========
Flexible time-series loading for the HVSR Analyzer.

Supports (all pure standard library):
- one text file containing Z N E columns (3 columns or more),
- three separate text files, one per component (Z, N, E),
- miniSEED files (.mseed / .miniseed) - float / int / STEIM encodings,
- .eqd raw 3-component recordings,
- SEG-2 (.sg2) files - a single file holding all 3 traces (Z, N, E),
  components are detected automatically from each trace's NOTE field
  (manual N/E override supported),
- comma / space / tab / semicolon delimiters,
- comment lines starting with #, ; or //,
- an optional header row,
- an optional sample-rate line such as  dt=0.01, fs=100, samplerate=100, freq=100
- an optional time column as the first column (the sampling interval is then
  inferred from the first two time samples).

The loaded data is stored in a simple 3Channel data container.
"""

import os
import re

_SUPPORTED_EXTENSIONS = (".csv", ".txt", ".dat", ".asc", ".tsv", ".sac",
                         ".ascii", ".mseed", ".miniseed", ".eqd", ".sg2")

_DT_PATTERNS = (
    re.compile(r"dt\s*=\s*([0-9.eE+-]+)", re.IGNORECASE),
    re.compile(r"(?:fs|sr|samplerate|sampling\s*rate|freq|frequency)\s*=\s*([0-9.eE+-]+)",
               re.IGNORECASE),
)


class DataError(Exception):
    """Raised when the input data cannot be parsed."""


class ThreeChannel:
    """Container for the three components plus the sampling rate."""

    def __init__(self, z, n, e, fs, source_name="unknown"):
        self.z = list(z)
        self.n = list(n)
        self.e = list(e)
        self.fs = float(fs)
        self.source_name = source_name

    @property
    def n_samples(self):
        return len(self.z)

    @property
    def duration(self):
        return self.n_samples / self.fs if self.fs else 0.0

    def common_length(self):
        """Trim all channels to the shortest length."""
        m = min(len(self.z), len(self.n), len(self.e))
        return ThreeChannel(self.z[:m], self.n[:m], self.e[:m], self.fs, self.source_name)


def _parse_sample_rate(line):
    """Return a float sample rate if the line looks like a metadata line."""
    for pat in _DT_PATTERNS:
        m = pat.search(line)
        if m:
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            # A dt= line gives the sampling interval, not the rate
            if line.lower().lstrip().startswith("dt") or "dt=" in line.lower():
                return 1.0 / val if val > 0 else None
            return val
    return None


def _is_comment(line):
    s = line.lstrip()
    return s.startswith("#") or s.startswith(";") or s.startswith("//")


def _split_row(line):
    """Split a data row on any common delimiter, dropping empties."""
    if "," in line:
        parts = line.replace(",", " ").split()
    else:
        parts = line.split()
    out = []
    for p in parts:
        try:
            out.append(float(p))
        except ValueError:
            out.append(p)  # keep non-numeric tokens (header detection)
    return out


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


def classify_component(filename):
    """Guess the component (Z / N / E) of a file from its name."""
    name = os.path.basename(filename).upper()
    for token, comp in (("EHZ", "Z"), ("HHZ", "Z"), ("CH1", "Z"), ("BHZ", "Z"),
                        ("EHN", "N"), ("HHN", "N"), ("CH2", "N"), ("BHN", "N"),
                        ("EHE", "E"), ("HHE", "E"), ("CH3", "E"), ("BHE", "E")):
        if token in name:
            return comp
    for char in "ZNE":
        if ("_" + char + ".") in name or ("-" + char + ".") in name:
            return char
    # last-resort: single letters
    if "Z" in name and "N" not in name and "E" not in name:
        return "Z"
    if "N" in name and "Z" not in name and "E" not in name:
        return "N"
    if "E" in name and "Z" not in name and "N" not in name:
        return "E"
    return None


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
        mapping = {c: None for c in "ZNE"}
        leftovers = []
        for p in file_paths:
            c = classify_component(p)
            if c and mapping[c] is None:
                mapping[c] = p
            else:
                leftovers.append(p)
        missing = [c for c, p in mapping.items() if p is None]
        for c, p in zip(missing, leftovers):
            mapping[c] = p
        if None in mapping.values():
            raise DataError("could not assign the 3 files to Z, N and E components")
        # route by extension: miniSEED trio uses the binary reader
        exts = {os.path.splitext(mapping[c])[1].lower() for c in "ZNE"}
        mseed_exts = {".mseed", ".miniseed"}
        if exts <= mseed_exts and exts:
            vals = {}
            fs = None
            for c in "ZNE":
                v, f, meta = load_mseed(mapping[c])
                vals[c] = v
                fs = f if fs is None else fs
            return ThreeChannel(vals["Z"], vals["N"], vals["E"], fs,
                                os.path.basename(mapping["Z"]))
        if exts & mseed_exts:
            raise DataError(
                "the 3 selected files mix binary miniSEED with text files - "
                "select either 3 miniSEED files or 3 text files")
        return load_three_files(mapping["Z"], mapping["N"], mapping["E"])

    raise DataError(
        "expected 1 file (3-column text or .eqd) or 3 files (one per "
        "component), got %d" % len(file_paths)
    )
