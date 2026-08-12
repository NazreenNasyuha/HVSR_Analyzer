"""
hvsr_io_data.py
===============
The data container and text-parsing helpers shared by all loaders:

- ThreeChannel : the Z/N/E sample container used across the app,
- DataError : the loader exception type,
- classify_component / assign_components : filename -> component helpers,
  _split_row, _parse_sample_rate, _is_comment and the shared
  regex/extension tables.

Split out of hvsr_io.py.
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
        """Number of samples in each component (all three share it)."""
        return len(self.z)

    @property
    def duration(self):
        """Recording length in seconds (0 when the rate is unknown)."""
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
    """True when a text line is a comment (#, ;, or //) and should be
    skipped while parsing columnar data."""
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


def assign_components(file_paths):
    """Assign a list of three file paths to the Z / N / E slots.

    Files whose names identify a component (see classify_component) go
    straight to that slot; the remaining files fill the empty slots in
    the order given (the GUI's file dialogs return them alphabetically).
    Raises DataError when the set cannot be split into the three
    components.  Returns an ordered dict {"Z": path, "N": path,
    "E": path}.
    """
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
        raise DataError(
            "could not assign the %d files to Z, N and E components"
            % len(file_paths))
    return mapping
