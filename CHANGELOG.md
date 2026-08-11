# Changelog

All notable changes to HVSR Analyzer are documented here.

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
