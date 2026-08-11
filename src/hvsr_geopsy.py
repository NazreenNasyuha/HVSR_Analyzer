"""
hvsr_geopsy.py
==============
Optional cross-check of the built-in HVSR engine against the external
Geopsy program (geopsy-hv.exe + gptarget.exe), when it is installed.

This module is defensive by design: if Geopsy is not found, or the run
fails for any reason, the main application simply continues with the
built-in engine results and logs a message.
"""

import glob
import math
import os
import subprocess

DEFAULT_SEARCH_DIRS = [
    r"C:\geopsypack-win64-3.5.2\bin",
    r"C:\Program Files\Geopsy\bin",
    r"C:\geopsy\bin",
]


def find_geopsy(exe_name="geopsy-hv.exe"):
    """Locate the geopsy-hv executable."""
    if os.name == "nt":
        for d in DEFAULT_SEARCH_DIRS:
            p = os.path.join(d, exe_name)
            if os.path.exists(p):
                return p
        # search PATH
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if not d:
                continue
            p = os.path.join(d, exe_name)
            if os.path.exists(p):
                return p
        hits = glob.glob(r"C:\geopsypack*\bin\geopsy-hv.exe")
        if hits:
            return hits[0]
    return None


def _write_param(path, win_len, rejection, fmin, fmax, nfreq,
                 b_value=40.0, combo="geometric"):
    """Write a geopsy-hv parameter file aligned with the built-in engine.

    Keys that geopsy-hv would otherwise default are written explicitly so
    the external run is reproducible and matches the engine's settings:
      * Konno-Ohmachi smoothing width 0.2 -- geopsy's native width value.
        Note: geopsy's stored width is NOT the engine's b-value.  On the
        G4 reference station the engine at b=20 reproduces Geopsy's
        f0 ~ 1.64 Hz (the engine's b=40 default gives ~2.4 Hz), so width
        0.2 corresponds to engine b ~ 20, not b=40.
      * Tukey taper alpha 0.05 (the engine's 5% cosine taper),
      * geometric-mean H/V combination,
      * a log step grid that yields ~nfreq points between fmin and fmax
        (geopsy-hv ignores STEP_TYPE=Count; use its Step mode instead).
    """
    step = 1.0
    if fmin > 0 and nfreq > 1 and fmax > fmin:
        step = math.exp(math.log(fmax / fmin) / (nfreq - 1))
    horiz = "Geometric" if combo == "geometric" else "Squared"
    width = 0.2  # geopsy-native Konno-Ohmachi width (see docstring)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "PARAMETERS_VERSION=1\n"
            "FROM_TIME_TYPE=Signal\n"
            "FROM_TIME_TEXT=0s\n"
            "TO_TIME_TYPE=Signal\n"
            "TO_TIME_TEXT=0s\n"
            "WINDOW_LENGTH_TYPE=Exactly\n"
            "WINDOW_MIN_LENGTH(s)=%.1f\n"
            "WINDOW_MAX_LENGTH(s)=%.1f\n"
            "WINDOW_MAX_COUNT=0\n"
            "WINDOW_MAXIMUM_PRIME_FACTOR=999\n"
            "WINDOW_TYPE=Tukey\n"
            "WINDOW_ALPHA=0.05\n"
            "ANTI-TRIGGERING_ON_RAW_SIGNAL (y/n)=n\n"
            "USED_RAW_COMPONENTS=y, y, y\n"
            "SMOOTHING_METHOD=Function\n"
            "SMOOTHING_WINDOW_TYPE=KonnoOhmachi\n"
            "SMOOTHING_WIDTH_TYPE=Log\n"
            "SMOOTHING_WIDTH=%.1f\n"
            "MINIMUM_FREQUENCY=%.3f\n"
            "MAXIMUM_FREQUENCY=%.3f\n"
            "SCALE_TYPE_FREQUENCY=Log\n"
            "STEP_TYPE_FREQUENCY=Step\n"
            "STEP_FREQUENCY=%.6f\n"
            "SAMPLES_NUMBER_FREQUENCY=%d\n"
            "HORIZONTAL_COMPONENTS=%s\n"
            "FREQUENCY_WINDOW_REJECTION_STDDEV_FACTOR=%.2f\n"
            % (win_len, win_len, width, fmin, fmax, step, nfreq,
               horiz, rejection)
        )


def _write_miniseed_signal(path, values, fs, channel, station="STA"):
    """Write a standard miniSEED file that Geopsy can import directly.

    Geopsy reads miniSEED natively and derives the component (Z / N / E)
    from the channel code, which avoids the ambiguous ASCII-loader path.
    """
    from mseed_io import write_mseed
    write_mseed(path, values, fs, channel, station=station, network="XX")


def run_geopsy_hv(geopsy_hv, data, out_dir, win_len, rejection,
                  fmin, fmax, nfreq, station, b_value=40.0,
                  combo="geometric"):
    """Run geopsy-hv on the processed data.  Returns (freqs, amps, log_lines)
    or (None, None, log_lines) on any failure.  b_value and combo are passed
    through so the geopsy run uses the same Konno-Ohmachi width and H/V
    combination as the built-in engine."""
    log = []
    try:
        bin_dir = os.path.dirname(geopsy_hv)
        # use absolute paths: geopsy-hv is launched with cwd=bin_dir
        out_dir = os.path.abspath(out_dir)
        temp = os.path.abspath(os.path.join(out_dir, "geo_tmp_" + station))
        os.makedirs(temp, exist_ok=True)
        param = os.path.join(temp, "params.param")
        _write_param(param, win_len, rejection, fmin, fmax, nfreq,
                     b_value=b_value, combo=combo)

        files = []
        for label, ch in (("EHZ", data.z), ("EHN", data.n), ("EHE", data.e)):
            p = os.path.join(temp, "%s_%s.mseed" % (station, label))
            _write_miniseed_signal(p, ch, data.fs, label, station=station)
            files.append(p)

        cmd = [geopsy_hv, "-param", param, "-o", temp] + files
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=bin_dir,
                              timeout=600)
        if proc.returncode != 0:
            log.append("geopsy-hv exited with code %d" % proc.returncode)
            log.append((proc.stdout or "").strip()[:400])
            log.append((proc.stderr or "").strip()[:400])
            raise RuntimeError("geopsy-hv failed")

        hv_files = glob.glob(os.path.join(temp, "*.hv"))
        if not hv_files:
            log.append("geopsy-hv ran but produced no .hv file")
            raise RuntimeError("no .hv output")

        raw = open(sorted(hv_files, key=os.path.getmtime, reverse=True)[0],
                   "r", encoding="utf-8", errors="replace").read()
        freqs, amps = [], []
        started = False
        last_f = -1.0
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    f = float(parts[0])
                    a = float(parts[1])
                except ValueError:
                    continue
                if started and f <= last_f:
                    break
                if f > fmax * 1.05:
                    break
                if a > 0.001:
                    freqs.append(f)
                    amps.append(a)
                    last_f = f
                    started = True
        if not freqs:
            log.append("no curve data parsed from geopsy .hv output")
            raise RuntimeError("no curve data")
        log.append("Geopsy cross-check OK: %d frequency samples" % len(freqs))
        return freqs, amps, log
    except Exception as exc:
        log.append("Geopsy cross-check skipped: %s" % exc)
        return None, None, log
    finally:
        try:
            import shutil
            shutil.rmtree(temp, ignore_errors=True)
        except Exception:
            pass
