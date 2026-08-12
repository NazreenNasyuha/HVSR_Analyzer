# Changelog

All notable changes to HVSR Analyzer are documented here.

## 1.1.0 (unreleased)

- **No Python needed to run the app**: the app is now packaged with
  PyInstaller (`scripts/build_exe.py`), which bundles a private Python
  runtime + tkinter inside the executable.  End users install and run the
  app without ever installing Python.
- **Installer updated**: `installer/HVSR_Analyzer_Setup.iss` now ships the
  packaged app (`dist/HVSR_Analyzer/`) instead of loose source files; the
  Python-detection warning and the per-file source list were removed.  The
  installer also removes the now-obsolete `src/` / `tests/` / `run.bat`
  files left behind by 1.0.0 installs (`[InstallDelete]`), and uninstall
  guarantees the whole app bundle folder is removed (`[UninstallDelete]`).
- **CI**: the installer workflow builds the PyInstaller app before compiling
  the Inno Setup installer.
- **Drag & drop**: the window now accepts a miniSEED/text Z-N-E trio (or a
  single .eqd/.sg2/3-column file) dropped from Explorer, filling the input
  slots automatically (`hvsr_gui_dnd.py`).  Dropping a **folder** starts a
  batch run on it, dropping a **.pz** fills the RESPONSE slot, and the whole
  input card tints while a drag hovers (the banner swaps to "RELEASE TO
  LOAD").  Uses the optional `tkinterdnd2` package, which the installer
  build bundles via `--collect-all`; running from source without the
  package keeps the plain file-picker flow.  This also fixed three-miniSEED
  loading in the GUI (the explicit-load path now routes binary files to the
  miniSEED reader).
- **File associations**: the installer registers `.eqd` / `.sg2` /
  `.mseed` / `.miniseed` (per-user, removed on uninstall), so
  double-clicking a recording opens HVSR Analyzer with that file (or a
  command-line trio) pre-loaded - see the startup-file handling in
  `hvsr_gui.main()`.  A **FILE ASSOCIATIONS** toggle on tab 04
  (`hvsr_gui_assoc.py`, `winreg`) lets users turn the associations on or
  off from inside the app without reinstalling.
- **Batch notification**: when a folder batch finishes, the app beeps and
  flashes the taskbar button (Windows) so users can walk away from long
  runs.
- **Documentation split**: `README.md` is now a short, user-focused guide
  (what the app does, how to install it, what you can do with it), and the
  developer material (architecture, module map, conventions, build/test
  instructions) lives in the new `docs/DEVELOPER.md`.  The tutorial now
  points to the installed app as the primary way to run it.
- **GUI split into focused modules**: the 2,200-line `hvsr_gui.py` is now a
  thin shell (`HVSRApp` composed from mixins) plus nineteen focused mixin
  modules - `hvsr_gui_core.py` (parameters / status strip / file handling),
  `hvsr_gui_theme.py` (live theme switching), `hvsr_gui_pump.py` (the
  queue-based message pump and result handlers),
  `hvsr_gui_pages.py` (card / file-row / scroll helpers) and
  `hvsr_gui_style.py` (the ttk style builder), `hvsr_gui_layout.py`
  (the window frame), `hvsr_gui_workflow.py` (the four workflow pages),
  `hvsr_gui_standards.py` (standard selector) and `hvsr_gui_checklist.py`
  (SESAME checklist rendering), `hvsr_gui_actions.py`
  (browse / preview / help handlers), `hvsr_gui_runners.py` (the run /
  batch starters), `hvsr_gui_workers.py` (the analysis pipeline) and
  `hvsr_gui_workhelpers.py` (the worker's parameter / naming helpers),
  `hvsr_gui_previews.py` (live-preview and folder-batch workers),
  `hvsr_gui_exports.py` (report / PNG / CSV savers),
  `hvsr_gui_profiles.py` (parameter profiles + data-log),
  `hvsr_gui_inversion.py` (1D inversion tab) and `hvsr_gui_invworker.py`
  (the inversion run logic), plus `hvsr_gui_tour.py`
  (tour + tutorial).  The old
  954-line pages module was itself split into pages / standards /
  actions and its monolithic `_build_ui()` further split into focused
  page builders (pages / layout / workflow); the 404-line core module
  into core / theme / pump, the 321-line workers module into workers /
  previews, the actions module into actions / runners, the exports
  module into exports (report / PNG / CSV savers) / profiles (parameter
  profiles + data-log), the standards module into standards
  (selector logic) / checklist (checklist rendering), the pages module
  into pages (card / file-row / scroll helpers) / style (the ttk style
  builder), the workers module into workers (pipeline) / workhelpers
  (parameter / naming helpers), and the inversion module into inversion
  (tab / exports) / invworker (run logic).  Behaviour is unchanged -
  all 213 tests pass.
- **Science modules split into focused modules**: every module over 300
  lines is now split into single-purpose modules that re-export through a
  small facade, so all existing imports keep working.  `hvsr_engine.py`
  (1070) -> engine facade + defaults / spectra / preprocess / core /
  report / autotune / support; `hvsr_dsp.py` (881) -> dsp facade + fft /
  filters / lfilter / stats; `hvsr_inversion.py` (1184) -> inversion
  facade + forward / phasevel / ellipticity / report / driver;
  `hvsr_io.py` (349) -> io facade + data / loaders; `mseed_io.py` (681)
  -> mseed facade + decode / parse / write; `hvsr_standards.py` (503) ->
  standards facade + data / eval; `hvsr_plot.py` (794) -> plot facade
  (palette + `apply_palette()` propagation) + util / curve / spectra /
  colormap / inversion; `chart_render.py` (697) -> chart facade +
  chart_png / chart_font / rasterizer core / curves / maps;
  `hvsr_tour.py` (377) -> `TourOverlay` (control) + `TourDrawing`
  (rendering).  The largest module is now 299 lines; all 213 tests still
  pass and the live theme switch restyles every canvas module.
- **Code comments**: filled the documentation gaps across the source -
  docstrings for the GUI pipeline / preview / batch / inversion methods,
  the miniSEED byte-level decoders, the chart-widget API, the tour overlay
  and the small I/O helpers - so a new developer can find their way
  around without reading the whole codebase.

## 1.0.0 (2026-08-11) - first public release

- **New themes**: the interface now ships with two themes — the default
  retro **dark** look and a **Black & White (Thesis)** theme designed for
  print publication (white backgrounds, black lines, grayscale colour
  maps). The **THEME** selector in the header switches live; every control
  and every exported PNG follows the active theme.
- **First-time-user tutorial**: `docs/TUTORIAL.md` — a step-by-step guide
  that walks through the whole workflow using the bundled example signals.
  The **TUTORIAL** button in the app header opens it from inside the app.
- **Example signals**: `examples/` now bundles one recording per supported
  raw format (`.eqd`, miniSEED trio, SEG-2 `.sg2`), all generated from a
  synthetic microtremor signal with a known 2 Hz resonance. Regenerate with
  `scripts/make_examples.py`.
- **Screenshots**: `scripts/make_screenshots.py` captures the app in both
  themes for the README and the tutorial (`docs/screenshots/`).
- **Installer**: fixed the AppId to a valid GUID, bumped the version, and
  the installer now ships the tutorial and the example signals too.
- **Performance**: the parameter sweeps are much faster without changing
  any result.  The FFT now uses a real-input half-size path and cached
  Bluestein tables, the Konno-Ohmachi / moving-average / triangular
  smoothing weights are computed once per analysis instead of per window,
  and `auto_tune` caches the window spectra so the 32-combination
  max-reliability sweep no longer re-FFTs the recording 32 times.  The
  stage-2 sweep and the 600-model 1D Monte-Carlo inversion can also run
  across multiple worker processes (auto-detected CPU count, safe
  sequential fallback).  Measured on the bundled example (2 min @ 250 Hz):
  full max-reliability auto-tune 17.5 s -> ~4 s, 600-model inversion
  15.7 s -> ~4.7 s, single analysis 2.3 s -> ~0.6 s.  Note: the
  max-reliability sweep now scores every smoothing/width/combo
  combination and keeps the global best (the old build stopped at the
  first score-6 combination), so the reported tuned parameters can
  differ from earlier runs - the SESAME score is never worse.
- **Guided first-run tour**: on launch the app overlays a spotlight
  (box + arrow) on each control, one by one, and explains what it does -
  Next / Back / Skip, keyboard arrows and Escape supported.  Replay it any
  time with the **SHOW TOUR** header button or by setting `HVSR_TOUR=1`.
- **Progress bar with live ETA**: the max-reliability sweep, batch runs
  and the 1D inversion now drive a determinate progress bar with an
  estimated time remaining (`MAX RELIABILITY 14/32 (44%)  ETA 0:23`).
- **Worker override**: the `HVSR_WORKERS` environment variable caps (or
  disables, with 0/1) the parallel worker processes for the sweeps and
  the inversion.
- **Tests**: added example-signal round-trip tests, a tutorial-button GUI
  test, FFT / smoothing / sequential-vs-parallel equivalence checks, a
  worker-env override test and progress-bar / guided-tour GUI checks
  (full suite: 24 + 8 + 62 + 100 + 19 = 213 tests).

## 0.0.14 (previous)

- Under-development snapshot before the theme / tutorial / examples work.

---

Version format follows semantic versioning (`X.Y.Z`).  `1.0.0` is the
first public release.
