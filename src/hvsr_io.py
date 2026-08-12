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


# Re-exported from hvsr_io_data (split out of hvsr_io) - the
# public API stays importable from here.
from hvsr_io_data import (DataError, ThreeChannel, _DT_PATTERNS,
                          _SUPPORTED_EXTENSIONS, _is_comment,
                          _parse_sample_rate, _split_row, classify_component,
                          assign_components)
# Re-exported from hvsr_io_loaders (split out of hvsr_io) - the
# public API stays importable from here.
from hvsr_io_loaders import auto_load, load_eqd, load_mseed, load_sg2, load_three_files, read_single_column, read_three_channel
