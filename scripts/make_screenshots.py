#!/usr/bin/env python
"""
make_screenshots.py
===================
Captures screenshots of the running app for the README and the tutorial
(docs/TUTORIAL.md) - in BOTH themes:

    docs/screenshots/dark_*.png   the default retro dark theme
    docs/screenshots/bw_*.png     the black & white (thesis) theme

The script launches the real GUI, loads the bundled .eqd example signal,
runs a full analysis (+ a short 1D inversion), captures the dark theme
first, then switches to the B&W theme (every chart re-renders) and captures
it again, so both sets show the same data.

Run (requires a display session and Pillow):
    python scripts/make_screenshots.py
"""

import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import hvsr_gui            # noqa: E402
from PIL import ImageGrab  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "screenshots")
EXAMPLE = os.path.join(ROOT, "examples", "example.eqd")


def pump(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.01)


def wait_busy(app, timeout=300.0):
    end = time.time() + timeout
    while app._busy and time.time() < end:
        app.update()
        time.sleep(0.02)
    return not app._busy


def grab(widget, name):
    widget.update_idletasks()
    widget.update()
    # account for Windows display scaling (logical -> physical pixels)
    scale = widget.winfo_fpixels("1i") / 96.0
    x = int(widget.winfo_rootx() * scale)
    y = int(widget.winfo_rooty() * scale)
    w = int(widget.winfo_width() * scale)
    h = int(widget.winfo_height() * scale)
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    path = os.path.join(OUT_DIR, name)
    img.save(path)
    print("  saved %s (%dx%d)" % (name, img.width, img.height))
    return path


def capture_all(app, prefix):
    """Capture the main tabs with the given file-name prefix."""
    nb = app._nb
    shots = {
        "app": (app, "%s_01_input_output.png" % prefix),
        0: (nb, "%s_02_hv_curve.png" % prefix),
        1: (nb, "%s_03_time_series.png" % prefix),
        3: (nb, "%s_04_checklist.png" % prefix),
        4: (nb, "%s_05_report.png" % prefix),
        6: (nb, "%s_06_inversion.png" % prefix),
    }
    # whole window first (input page visible)
    app._pages.select(0)
    pump(app, 0.4)
    grab(app, shots["app"][1])
    for idx, (widget, name) in shots.items():
        if idx == "app":
            continue
        nb.select(idx)
        pump(app, 0.5)
        grab(widget, name)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Building app...")
    app = hvsr_gui.HVSRApp()
    app.geometry("1320x820+40+40")
    app.deiconify()
    app.lift()
    app.focus_force()
    pump(app, 0.5)

    # ---- load the example signal and run a full analysis ----------------
    print("Loading example signal:", os.path.basename(EXAMPLE))
    app._vars["z_entry"].delete(0, "end")
    app._vars["z_entry"].insert(0, EXAMPLE)
    out = tempfile.mkdtemp(prefix="hvsrcap_")
    app._vars["out_entry"].delete(0, "end")
    app._vars["out_entry"].insert(0, out)
    app._vars["sv_png"].set(True)
    app._vars["sv_csv"].set(True)
    app._vars["ask_save"].set(False)
    app._vars["log_csv"].set(False)
    app._vars["geo_enable"].set(False)

    app._refresh_preview()
    if not wait_busy(app, timeout=120.0):
        print("WARN: waveform preview did not finish in time")
    pump(app, 0.3)

    print("Running analysis...")
    app._start_run()
    if not wait_busy(app):
        print("WARN: analysis did not finish in time")
    pump(app, 0.6)

    # ---- run a short inversion so the inversion tab has content ---------
    print("Running short 1D inversion...")
    app._inv_vars["iter"].delete(0, "end")
    app._inv_vars["iter"].insert(0, "150")
    app._start_inversion()
    if not wait_busy(app, timeout=420.0):
        print("WARN: inversion did not finish in time")
    pump(app, 0.6)

    # ---- capture DARK theme (the default) -------------------------------
    print("Capturing DARK theme...")
    capture_all(app, "dark")

    # ---- switch to B&W and capture again (charts re-render) -------------
    print("Switching to B&W theme...")
    app._vars["theme"].set("B&W (THESIS)")
    app._set_theme()
    pump(app, 0.5)
    print("Capturing B&W theme...")
    capture_all(app, "bw")

    shutil.rmtree(out, ignore_errors=True)
    print("Done. Screenshots are in:", OUT_DIR)
    app.destroy()


if __name__ == "__main__":
    main()
