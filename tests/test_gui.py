"""
test_gui.py
===========
Automated tests for the tkinter GUI (hvsr_gui.HVSRApp).

The app window is withdrawn (never shown on screen) and the Tk event
loop is pumped manually, so the whole test runs headless-friendly.

Covered:
  * app construction (tabs, status bar, widget tree)
  * parameter parsing in manual and auto modes
  * input validation (no files -> DataError)
  * station name stripping
  * a full analysis run on synthetic data (f0 ~ 2 Hz) via the real
    worker thread + queue pump, including PNG/report/target/CSV outputs
    and the spectra tab
  * data-log append
  * Method checklist rendering
  * sample-data loading, Geopsy detection
  * auto-assign of Z/N/E files and a single .eqd
  * export buttons (PNG / report / target / spectra PNG)
  * batch processing of a whole folder
"""

import math
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import hvsr_gui
from hvsr_gui import HVSRApp, DataError

PASS = FAIL = 0
FAILURES = []


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   - %s" % name)
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL - %s  %s" % (name, extra))


def pump(app, seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.01)


def wait_busy(app, timeout=240.0):
    end = time.time() + timeout
    while app._busy and time.time() < end:
        app.update()
        time.sleep(0.02)
    return not app._busy


def main():
    print("=" * 60)
    print("GUI TEST SUITE (hvsr_gui.py)")
    print("=" * 60)

    # ---- patch blocking dialogs so tests never hang -------------------
    dialogs = []
    hvsr_gui.messagebox.showerror = \
        lambda *a, **k: dialogs.append(("error", a))
    hvsr_gui.messagebox.showinfo = \
        lambda *a, **k: dialogs.append(("info", a))
    hvsr_gui.filedialog.askdirectory = lambda *a, **k: "PATCHED_DIR"
    hvsr_gui.filedialog.askopenfilename = lambda *a, **k: "PATCHED_FILE"
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: "PATCHED_SAVE"

    td = tempfile.mkdtemp(prefix="gui_test_")

    # ---- construction --------------------------------------------------
    try:
        app = HVSRApp()
    except Exception as exc:
        print("FATAL: cannot create Tk app: %r" % exc)
        print("(tkinter needs a display session; skipping GUI tests)")
        return 2
    app.withdraw()
    pump(app, 0.3)

    check("app builds; >=5 notebook tabs", len(app._nb.tabs()) >= 5,
          len(app._nb.tabs()))
    check("status shows Ready", "READY" in app._status.cget("text").upper(),
          app._status.cget("text"))
    for key in ("z_entry", "n_entry", "e_entry", "pz_entry", "out_entry"):
        check("entry widget %s exists" % key, key in app._vars)

    # ---- parameter parsing (manual defaults) ---------------------------
    p = app._params()
    check("win_len default 30", p["win_len"] == 30.0, p.get("win_len"))
    check("overlap default 0", p["overlap"] == 0.0, p.get("overlap"))
    check("rejection default 1.5", p["rejection"] == 1.5)
    check("fmin/fmax 0.5/20", p["fmin"] == 0.5 and p["fmax"] == 20.0)
    check("nfreq 512", p["nfreq"] == 512, p.get("nfreq"))
    check("b_value 40", p["b_value"] == 40.0)
    check("taper 0.05", p["taper"] == 0.05, p.get("taper"))
    check("max_iterations 50", p["max_iterations"] == 50,
          p.get("max_iterations"))
    check("sta_sec 1.0", p["sta_sec"] == 1.0, p.get("sta_sec"))
    check("lta_sec 30.0", p["lta_sec"] == 30.0, p.get("lta_sec"))
    check("slta_threshold 2.5", p["slta_threshold"] == 2.5,
          p.get("slta_threshold"))
    check("max_fs 250.0", p["max_fs"] == 250.0, p.get("max_fs"))
    check("combo geometric", p["combo"] == "geometric")
    check("mute+decimate on", p["mute"] and p["decimate"])
    check("mode manual", p["mode"] == "manual")
    check("std_id sesame", p["std_id"] == "sesame", p.get("std_id"))

    # ---- Apply Method recommendations (fills every manual field) --------
    app._vars["std"].set("Japan (J-SHIS / JAMC)")
    app._apply_suggestions()
    p = app._params()
    check("apply suggestions: japan win_len 60", p["win_len"] == 60.0,
          p.get("win_len"))
    check("apply suggestions: japan fmin 0.2", p["fmin"] == 0.2,
          p.get("fmin"))
    check("apply suggestions: rejection 2.0", p["rejection"] == 2.0,
          p.get("rejection"))
    check("apply suggestions: taper filled", p["taper"] == 0.05,
          p.get("taper"))
    check("apply suggestions: max_iters filled",
          p["max_iterations"] == 50, p.get("max_iterations"))
    check("apply suggestions: stays manual", p["mode"] == "manual")
    app._vars["std"].set("SESAME 2004 (Europe)")
    app._apply_suggestions()
    p = app._params()
    check("apply suggestions: back to sesame 30s", p["win_len"] == 30.0,
          p.get("win_len"))

    # auto mode
    app._vars["param_mode"].set("auto")
    app._toggle_param_mode()
    check("auto mode enables autotune",
          app._vars["autotune"].get() is True)
    p = app._params()
    check("auto mode -> auto params filled", p["mode"] == "auto"
          and p["win_len"] is None and p["rejection"] is None)
    app._vars["param_mode"].set("manual")
    app._toggle_param_mode()

    # ---- input validation ----------------------------------------------
    try:
        app._read_files()
        check("no files raises DataError", False)
    except DataError:
        check("no files raises DataError", True)
    except Exception as exc:
        check("no files raises DataError", False, repr(exc))

    # ---- station name stripping ----------------------------------------
    fake = type("D", (), {"source_name": "SITE_12.mseed"})()
    check("station name strips .mseed",
          app._station_name(fake) == "SITE_12", app._station_name(fake))

    # ---- full analysis run ---------------------------------------------
    import make_sample_data
    pfile = make_sample_data.write_station(td, name="guiA", duration=240.0,
                                           fs=50.0, f0=2.0)
    app._vars["z_entry"].delete(0, "end")
    app._vars["z_entry"].insert(0, pfile)
    out = os.path.join(td, "out")
    app._vars["out_entry"].delete(0, "end")
    app._vars["out_entry"].insert(0, out)
    app._vars["sv_png"].set(True)
    app._vars["sv_csv"].set(True)
    app._vars["ask_save"].set(False)
    app._vars["log_csv"].set(False)
    app._vars["geo_enable"].set(False)

    app._start_run()
    done = wait_busy(app)
    check("analysis finishes", done)
    res = app._last[0] if app._last else None
    check("result object produced", res is not None)
    if res:
        check("f0 ~ 2 Hz (synthetic)", abs(res.f0 - 2.0) < 0.3,
              "f0=%.3f" % res.f0)
        check("A0 > 1", res.a0 > 1.0, "A0=%.2f" % res.a0)
        check("windows accepted > 0", res.n_windows_accepted > 0)
        check("report text non-empty", len(res.report_text) > 300)
        check("curve canvas has data", bool(len(getattr(
            app._curve, "freqs", []) or [])))
        check("spectra computed", bool(getattr(
            res, "spectra", {}).get("freqs")))
        check("Kg computed", res.kg > 0)
        check("status done", "COMPLETE" in app._status.cget("text").upper(),
              app._status.cget("text"))
        for f in ("guiA_report.txt", "guiA_inversion.target",
                  "guiA_HVSR.png", "guiA_data.csv", "guiA_spectra.csv"):
            check("saved %s" % f, os.path.exists(os.path.join(out, f)))
        # data-log append
        clean = app._last[1]
        station = app._last[2]
        app._append_data_log(res, clean, station, clean.source_name, out)
        dlog = os.path.join(out, "data_log.csv")
        check("data-log written", os.path.exists(dlog)
              and os.path.getsize(dlog) > 50)
        # checklist tab
        app._render_standard("sesame")
        check("checklist items rendered", len(app._sesame_items) > 0,
              "items=%d" % len(app._sesame_items))
        app._on_std_change()
        # spectra tab modes
        app._vars["spec_mode"].set("Spectrum")
        app._redraw_spectra()
        app._vars["spec_mode"].set("PSD")
        app._redraw_spectra()
        check("spectra redraw no crash", True)
    else:
        check("report present in text widget", False)
        print("  LOG so far:")
        print(app._log.get("1.0", "end"))

    # ---- exports (patched save dialogs) --------------------------------
    save_path = os.path.join(td, "export.png")
    hvsr_gui.filedialog.asksaveasfilename = \
        lambda *a, **k: save_path
    app._export_png()
    check("export PNG", os.path.exists(save_path))
    rp = os.path.join(td, "export.txt")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: rp
    app._export_report()
    check("export report", os.path.exists(rp))
    tp = os.path.join(td, "export.target")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: tp
    app._export_target()
    check("export target", os.path.exists(tp))
    sp = os.path.join(td, "spectra.png")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: sp
    app._export_spectra_png()
    check("export spectra PNG", os.path.exists(sp))

    # ---- preview exports (new views) ------------------------------------
    app._analyse_signal()
    done = wait_busy(app, timeout=120.0)
    check("signal analysis before export", done)
    sp = os.path.join(td, "sig_export.png")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: sp
    app._export_sig_png()
    check("export signal-analysis PNG", os.path.exists(sp)
          and os.path.getsize(sp) > 500)

    app._preview_filtered()
    done = wait_busy(app, timeout=120.0)
    check("filtered preview before export", done)
    fp = os.path.join(td, "filt_export.png")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: fp
    app._export_filt_png()
    check("export filtered-preview PNG", os.path.exists(fp)
          and os.path.getsize(fp) > 500)

    app._preview_hv_views()
    done = wait_busy(app, timeout=180.0)
    check("H/V views before export", done)
    base = os.path.join(td, "hv_export")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: base + ".png"
    app._export_hv_views()
    for suffix in ("_timefreq", "_azimuth", "_spectra", "_curve"):
        p = base + suffix + ".png"
        check("export H/V view %s" % suffix, os.path.exists(p)
              and os.path.getsize(p) > 500)

    # ---- parameter profile save / load ----------------------------------
    app._set_param("win_len", "45")
    app._set_param("b_value", "55")
    prof = os.path.join(td, "profile.json")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: prof
    app._save_params()
    check("parameter profile saved", os.path.exists(prof)
          and '"win_len"' in open(prof, encoding="utf-8").read())
    app._set_param("win_len", "10")
    app._set_param("b_value", "5")
    hvsr_gui.filedialog.askopenfilename = lambda *a, **k: prof
    app._load_params()
    pump(app, 0.2)
    check("parameter profile restores fields",
          app._vars["win_len"].get() == "45"
          and app._vars["b_value"].get() == "55",
          "win=%s b=%s" % (app._vars["win_len"].get(),
                           app._vars["b_value"].get()))
    # mode round-trips: save in Auto, load while Manual -> becomes Auto
    app._vars["param_mode"].set("auto")
    hvsr_gui.filedialog.asksaveasfilename = lambda *a, **k: prof
    app._save_params()
    app._vars["param_mode"].set("manual")
    hvsr_gui.filedialog.askopenfilename = lambda *a, **k: prof
    app._load_params()
    pump(app, 0.2)
    check("parameter profile restores mode",
          app._vars["param_mode"].get() == "auto",
          app._vars["param_mode"].get())
    # malformed profile (parameters not a dict) must not crash
    bad = os.path.join(td, "bad.json")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write('{"parameters": [1, 2, 3]}')
    hvsr_gui.filedialog.askopenfilename = lambda *a, **k: bad
    app._load_params()
    pump(app, 0.2)
    check("malformed profile handled gracefully",
          app._vars["win_len"].get() == "45")

    # ---- auto-assign (file-based: pick 1 or 3 files) --------------------
    fa = os.path.join(td, "filesA")
    os.makedirs(fa, exist_ok=True)
    three = []
    for comp in ("Z", "N", "E"):
        p3 = os.path.join(fa, "S1_%s.csv" % comp)
        with open(p3, "w") as fh:
            fh.write("Z,N,E" + chr(10) + "0,0,0" + chr(10))
        three.append(p3)
    hvsr_gui.filedialog.askopenfilenames = lambda *a, **k: three
    app._auto_assign()
    got = {s: app._vars[s + "_entry"].get() for s in ("z", "n", "e")}
    check("auto-assign 3 files fills Z/N/E", all(
        got[s].endswith("S1_%s.csv" % c) for s, c in
        (("z", "Z"), ("n", "N"), ("e", "E"))), got)

    fb = os.path.join(td, "fileB")
    os.makedirs(fb, exist_ok=True)
    eqd = os.path.join(fb, "S2.eqd")
    open(eqd, "w").close()
    hvsr_gui.filedialog.askopenfilenames = lambda *a, **k: [eqd]
    app._auto_assign()
    check("auto-assign single .eqd -> z slot",
          app._vars["z_entry"].get().endswith("S2.eqd"),
          app._vars["z_entry"].get())
    check("n/e cleared for eqd",
          not app._vars["n_entry"].get() and not app._vars["e_entry"].get())

    # single 3-column text file -> z slot
    t3 = os.path.join(fb, "S3_3col.txt")
    with open(t3, "w") as fh:
        fh.write("dt=0.01" + chr(10) + "Z,N,E" + chr(10) + "0,0,0" + chr(10) + "0,0,0" + chr(10))
    hvsr_gui.filedialog.askopenfilenames = lambda *a, **k: [t3]
    app._auto_assign()
    check("auto-assign single 3-col text -> z slot",
          app._vars["z_entry"].get().endswith("S3_3col.txt"),
          app._vars["z_entry"].get())

    # waveform preview is populated after a successful auto-assign
    pump(app, 0.5)
    check("preview canvas exists", hasattr(app, "_preview"))

    # ---- Geopsy detection ------------------------------------------------
    import hvsr_geopsy
    app._detect_geopsy()
    if hvsr_geopsy.find_geopsy():
        check("geopsy detected + enabled",
              bool(app._vars["geo_path"].get())
              and app._vars["geo_enable"].get())
    else:
        check("geopsy absent handled gracefully",
              not app._vars["geo_path"].get()
              and not app._vars["geo_enable"].get())

    # ---- sample data button ----------------------------------------------
    app._load_sample()
    check("load sample fills z_entry",
          app._vars["z_entry"].get().endswith(".csv"),
          app._vars["z_entry"].get())

    # ---- signal analysis preview (Input tab) ------------------------------
    app._analyse_signal()
    done = wait_busy(app, timeout=120.0)
    check("signal analysis finishes", done)
    sig = getattr(app, "_sig_payload", None)
    check("sig payload has spectra + coherence",
          sig is not None and len(sig[0]["freqs"]) > 10
          and len(sig[1][0]) > 10 and len(sig[2][0]) > 10 and len(sig[3][0]) > 10)
    check("sig canvas has items", len(app._sig.find_all()) > 0)
    app._vars["sig_mode"].set("Spectrum")
    app._redraw_sig()
    app._vars["sig_mode"].set("Coherence")
    app._redraw_sig()
    check("sig mode switch redraws", len(app._sig.find_all()) > 0)

    # ---- filtered waveform preview (Preprocessing tab) ---------------------
    app._preview_filtered()
    done = wait_busy(app, timeout=120.0)
    check("filtered preview finishes", done)
    filt_traces = getattr(app._filt, "traces", None)
    check("filtered preview has 3 traces",
          filt_traces is not None and len(filt_traces) == 3,
          "traces=%r" % (filt_traces and len(filt_traces)))
    check("filtered preview canvas has items",
          len(app._filt.find_all()) > 0)

    # ---- H/V views (HV Parameters tab) ------------------------------------
    app._preview_hv_views()
    done = wait_busy(app, timeout=180.0)
    check("H/V views finish", done)
    tf_grid = getattr(app._tf, "grid", None)
    az_grid = getattr(app._az, "grid", None)
    check("time-freq map populated",
          tf_grid is not None and len(tf_grid) > 1 and len(tf_grid[0]) > 1)
    check("azimuth map populated",
          az_grid is not None and len(az_grid) > 2 and len(az_grid[0]) > 1)
    avg_spec = getattr(app._avg_spec, "freqs", None)
    check("average spectra populated", avg_spec and len(avg_spec) > 10)
    avg_hv = getattr(app._avg_hv, "mean", None)
    check("average H/V curve populated", avg_hv and len(avg_hv) > 10)
    check("tf map canvas has items", len(app._tf.find_all()) > 0)

    # ---- batch processing ------------------------------------------------
    batch = os.path.join(td, "batch")
    for name, f0 in (("A1", 2.0), ("A2", 3.0)):
        make_sample_data.write_station(os.path.join(batch, name),
                                       name=name, duration=60.0, fs=50.0,
                                       f0=f0)
    bout = os.path.join(td, "batchout")
    os.makedirs(bout, exist_ok=True)  # the real app does this via _out_dir()
    bp = app._params()
    bopts = app._save_opts()
    bopts["ask"] = False
    bopts["log"] = True
    app._batch_worker(batch, bp, autotune=False, opts=bopts,
                      out_dir=bout, swap_h=False)
    pump(app, 0.5)  # drain the queue into the log widget
    log_txt = app._log.get("1.0", "end")
    check("batch processed 2 stations",
          "BATCH COMPLETE: 2 OK, 0 FAILED" in log_txt
          and os.path.exists(os.path.join(bout, "A1_report.txt"))
          and os.path.exists(os.path.join(bout, "A2_report.txt")),
          log_txt[-200:])
    dlog = os.path.join(bout, "data_log.csv")
    check("batch wrote data-log rows", os.path.exists(dlog)
          and len(open(dlog).read().splitlines()) == 3)

    # ---- in-app TUTORIAL button -----------------------------------------
    app._open_tutorial()
    pump(app, 0.2)
    tut_open = False
    for w in app.winfo_children():
        if w.winfo_class() == "Toplevel" and "Tutorial" in w.title():
            for c in w.winfo_children():
                if c.winfo_class() == "Text" and "First-Time User Tutorial" in c.get("1.0", "end"):
                    tut_open = True
            w.destroy()
    check("tutorial button opens the guide", tut_open)

    # ---- progress bar + ETA ---------------------------------------------
    app._set_status("WORKING...", busy=True)
    app._set_progress(4, 32, "MAX RELIABILITY")
    pump(app, 0.1)
    plabel = app._progress_label.cget("text")
    pval = app._progress.cget("value")
    check("progress label shows step + ETA",
          "4/32" in plabel and "ETA" in plabel, plabel)
    check("progress bar value tracks fraction", abs(pval - 12.5) < 0.6, pval)
    app._set_progress(32, 32, "MAX RELIABILITY")
    check("no ETA at completion", "ETA" not in app._progress_label.cget("text"))
    app._set_status("DONE.", busy=False)
    check("progress label resets on idle",
          app._progress_label.cget("text") == "")

    # ---- guided tour overlay ---------------------------------------------
    app._start_tour()
    pump(app, 0.3)
    check("tour overlay activates", app._tour is not None and app._tour.active)
    steps = app._tour_steps()
    while app._tour.active and app._tour.index < len(steps) - 1:
        app._tour._next()
        pump(app, 0.05)
    app._tour._next()  # finish
    pump(app, 0.2)
    check("tour closes after last step",
          app._tour is None or not app._tour.active)
    app._start_tour()
    pump(app, 0.2)
    app._tour._skip()
    pump(app, 0.2)
    check("tour skip closes the overlay",
          app._tour is None or not app._tour.active)

    app.destroy()
    # Only ERROR dialogs are failures.  The app legitimately shows an info
    # popup ("GEOPSY NOT FOUND.") when Geopsy is not installed, which is
    # normal on machines / CI runners without Geopsy; treat those as OK.
    check("no blocking error dialogs appeared",
          not any(t == "error" for t, _ in dialogs), str(dialogs))
    print("\n" + "=" * 60)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    if FAILURES:
        print("Failed: " + ", ".join(FAILURES))
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
