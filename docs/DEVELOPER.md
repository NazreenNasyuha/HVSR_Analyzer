# Developer Documentation

Welcome, future developer. This file is the map of the codebase: how the
pieces fit together, the rules we follow, and how to build, test and extend
the app. It is written for people who will *change* the code — if you only
want to *use* the app, you're in the wrong place. Head back to the
[README](../README.md).

## The one rule that shapes everything

**This project is pure Python standard library. No numpy. No scipy. No
obspy, matplotlib or any other third-party runtime dependency.**

The one exception is `tkinterdnd2` (with its bundled native `tkdnd`
library), used **only** for OS-level drag-and-drop of data files - Tkinter
cannot do that with the standard library alone. It is *optional*: the
installer build collects it into the exe (`build_exe.py` passes
`--collect-all tkinterdnd2`), while a source install without it simply runs
without drag-and-drop (`hvsr_gui_dnd.py` guards the import).

Every FFT, filter, smoothing operator, PNG encoder, miniSEED reader and the
1D inversion forward model is written from scratch. That constraint is a
feature, not a limitation:

- the app runs on any bare Python 3.8+ install (and, packaged, on machines
  with no Python at all),
- there is no dependency matrix to break,
- and the science is fully visible in the source — easy to audit, easy to
  adapt to a thesis committee's questions.

A new feature must work on a bare Python 3.8+ install. PyInstaller is used
**only as a build-time tool** (see [Building](#building)) — it adds no
runtime dependency.

## Repository layout

```
HVSR_Analyzer/
├── src/                  # the application (engine, DSP, I/O, GUI, inversion)
│   ├── main.py           # entry point
│   ├── hvsr_gui.py       # GUI shell: HVSRApp composed from the mixins below
│   ├── hvsr_gui_core.py  #   mixin: state, parameters, status strip, I/O
│   ├── hvsr_gui_theme.py #   mixin: live theme switching
│   ├── hvsr_gui_pump.py  #   mixin: the queue-based message pump
│   ├── hvsr_gui_pages.py #   mixin: card / file-row / scroll helpers
│   ├── hvsr_gui_style.py #   mixin: the ttk style builder
│   ├── hvsr_gui_layout.py #   mixin: the window frame builders
│   ├── hvsr_gui_workflow.py#   mixin: the four workflow pages
│   ├── hvsr_gui_standards.py # mixin: standard-selector logic
│   ├── hvsr_gui_checklist.py #  mixin: SESAME checklist rendering
│   ├── hvsr_gui_actions.py #  mixin: browse / preview / help handlers
│   ├── hvsr_gui_runners.py #  mixin: the run / batch starters
│   ├── hvsr_gui_workers.py#   mixin: the analysis pipeline
│   ├── hvsr_gui_workhelpers.py# mixin: worker parameter/name helpers
│   ├── hvsr_gui_previews.py#  mixin: preview + batch workers
│   ├── hvsr_gui_exports.py#   mixin: saving reports/charts/CSVs
│   ├── hvsr_gui_profiles.py#   mixin: parameter profiles + data-log
│   ├── hvsr_gui_inversion.py # mixin: the 1D inversion tab
│   ├── hvsr_gui_invworker.py # mixin: the inversion run logic
│   ├── hvsr_gui_tour.py  #   mixin: guided tour + tutorial window
│   ├── hvsr_engine*.py   # analysis - facade hvsr_engine.py re-exports the
│   │                     #   defaults / spectra / preprocess / core / report /
│   │                     #   autotune / support modules
│   ├── hvsr_dsp*.py      # DSP - facade hvsr_dsp.py re-exports the
│   │                     #   fft / filters / lfilter / stats modules
│   ├── hvsr_inv_*.py     # inversion - facade hvsr_inversion.py re-exports
│   │                     #   forward / phasevel / ellipticity / report / driver
│   ├── hvsr_io*.py       # loading - facade hvsr_io.py re-exports the
│   │                     #   data container + loaders modules
│   ├── mseed_io*.py      # miniSEED - reader + decode / parse / write modules
│   ├── eqd_io.py         # pure-Python .eqd reader
│   ├── sg2_io.py         # pure-Python SEG-2 (.sg2) reader
│   ├── hvsr_standards*.py# standards - facade hvsr_standards.py re-exports
│   │                     #   the data tables + evaluators modules
│   ├── hvsr_plot*.py     # Canvas widgets - facade hvsr_plot.py re-exports
│   │                     #   curve / spectra / colormap / inversion / util
│   ├── chart_render*.py  # PNG encoder (chart_png) + font (chart_font) +
│   │                     #   rasterizer core / curves / maps + facade
│   ├── hvsr_theme.py     # dark / black & white theme palettes
│   ├── hvsr_tour*.py     # guided tour - TourDrawing (hvsr_tour_draw) +
│   │                     #   TourOverlay (hvsr_tour)
│   ├── hvsr_geopsy.py    # optional external Geopsy cross-check
│   └── make_sample_data.py  # synthetic test-station generator
├── tests/                # 5 suites, 213 tests (see Testing)
├── scripts/              # dev/validation tools (see Scripts)
├── examples/             # 3 example signals with a known 2 Hz resonance
├── docs/                 # TUTORIAL.md (users), DEVELOPER.md (you), screenshots/
├── installer/            # Inno Setup script -> HVSR_Analyzer_Setup.exe
├── .github/workflows/    # CI: tests + installer build
├── README.md             # user documentation
├── CHANGELOG.md          # version history
└── LICENSE               # MIT License
```

## How the pieces fit together

### Data flow

```
auto_load()  (hvsr_io: detect format, read -> ThreeChannel)
    -> preprocess()      (hvsr_engine: detrend, band-pass, STA/LTA mute,
                          optional decimation)
    -> analyze()         (hvsr_engine: sliding-window H/V -> _finalize_analysis:
                          rejection, mean curve, f0/A0, SESAME scoring)
    -> invert_hvsr()     (hvsr_inversion: model seeding -> Monte-Carlo ->
                          ensemble uncertainty stats)
```

The GUI never blocks: long work runs on daemon worker threads and ships
results back through a `queue.Queue` polled every 120 ms by
`HVSRAppPumpMixin._poll_queue` in `hvsr_gui_pump.py`.

### Module guide (what lives where)

| Module | Responsibility |
|---|---|
| `main.py` | Entry point; installs the source dir on `sys.path`, calls `multiprocessing.freeze_support()` (required by the frozen build), and turns startup crashes into a visible error box + log instead of silent death under `pythonw`. |
| `hvsr_gui.py` | The GUI shell: `HVSRApp` (a `tk.Tk` subclass) composed from the nineteen mixins below, plus `main()`. Kept deliberately small. |
| `hvsr_gui_core.py` | `HVSRAppCore` mixin: status/progress strip, parameter reading, file handling and the worker-count helper. |
| `hvsr_gui_theme.py` | `HVSRAppThemeMixin`: the live theme switcher (`_set_theme`) and the `_themed` widget registry; re-binds the palette in every sibling module that carries colour aliases. |
| `hvsr_gui_pump.py` | `HVSRAppPumpMixin`: the UI-thread message pump (`_poll_queue`) that worker threads feed through a `queue.Queue`, plus the handlers that push finished results into every chart and tab. |
| `hvsr_gui_pages.py` | `HVSRAppPagesMixin`: the card / file-row widgets, the scrollable page canvases and the mouse-wheel scrolling helpers. |
| `hvsr_gui_style.py` | `HVSRAppStyleMixin`: the ttk style builder - `_build_style()` configures every widget class for the active theme (run at startup and on each live theme switch). |
| `hvsr_gui_layout.py` | `HVSRAppLayoutMixin`: the window frame - `_build_ui()` assembles the header, the four-tab notebook shell and the right-hand results panel. |
| `hvsr_gui_workflow.py` | `HVSRAppWorkflowMixin`: the four workflow-page builders (input/output, pre-processing, H/V parameters, output data) that fill the notebook tabs. |
| `hvsr_gui_standards.py` | `HVSRAppStandardsMixin`: the standard-selector logic - `_on_std_change` (logs recommended parameters, refreshes the checklist) and `_auto_assign` (routes one/three files into the Z/N/E slots). |
| `hvsr_gui_checklist.py` | `HVSRAppChecklistMixin`: the SESAME checklist card rendering - `_build_sesame_widgets`, `_render_standard` (per-criterion OK/WARN boxes, score, Vs30 / thickness / verdict) and the `_set_sesame` hook. |
| `hvsr_gui_actions.py` | `HVSRAppActionsMixin`: the browse / preview / help handlers - file browsing, parameter mode, method recommendations, live previews, sample data, Geopsy detection, help. |
| `hvsr_gui_runners.py` | `HVSRAppRunnersMixin`: the run / batch starters - `_start_run`, `_start_batch`, `_start_full_autotune` - which validate inputs and spawn the worker threads. |
| `hvsr_gui_workers.py` | `HVSRAppWorkersMixin`: the single-station analysis pipeline - `_worker` and the analysis dispatch `_analyze_one`. |
| `hvsr_gui_workhelpers.py` | `HVSRAppWorkHelpersMixin`: the worker's shared helpers - `_fill_defaults` (PARAM_DEFAULTS fallbacks), `_resolve_auto` (Auto-mode recommendations) and `_station_name` (output-file naming). |
| `hvsr_gui_previews.py` | `HVSRAppPreviewsMixin`: the daemon-thread preview workers (waveform, filtered, spectra/coherence, H/V maps) and the folder batch sweep. |
| `hvsr_gui_exports.py` | `HVSRAppExportsMixin`: saving reports, targets, PNGs and CSVs - the Save-Protocol auto-writers plus the button-triggered exporters and the ask-user save dialogs. |
| `hvsr_gui_profiles.py` | `HVSRAppProfilesMixin`: parameter profiles - `_profile_values` / `_save_params` / `_load_params` (JSON) - and `_append_data_log`, the batch data-log writer. |
| `hvsr_gui_inversion.py` | `HVSRAppInversionMixin`: the 1D inversion tab (controls, Vs-profile / misfit canvases, result rendering, report / CSV exports). |
| `hvsr_gui_invworker.py` | `HVSRAppInvWorkerMixin`: the inversion run logic - `_start_inversion` validates and spawns, `_inversion_worker` runs the Monte-Carlo search on a daemon thread. |
| `hvsr_gui_tour.py` | `HVSRAppTourMixin`: the guided-tour steps, tour start/close, and the in-app tutorial window. |
| `hvsr_tour.py` | `TourOverlay`: the guided-tour control flow (start / next / back / skip / geometry); inherits the rendering from `TourDrawing`. |
| `hvsr_tour_draw.py` | `TourDrawing`: the spotlight-box / arrow / callout-card rendering and the class constants (fonts, paddings, transparent colour). |
| `hvsr_theme.py` | The two theme palettes (dark, black & white), shared by the GUI, the charts and PNG export so saved images match the screen. |
| `hvsr_plot.py` | **Facade** for the canvas widgets; `apply_palette()` propagates a theme switch to every canvas module. |
| `hvsr_plot_util.py` | The log-tick helpers (`_nice_ticks`, `_fmt_tick`). |
| `hvsr_plot_curve.py` | `HvsrCurveCanvas` - the log-frequency H/V curve chart. |
| `hvsr_plot_spectra.py` | `SpectraCanvas` + `TimeSeriesCanvas`. |
| `hvsr_plot_colormap.py` | `ColorMapCanvas` (time-frequency colour map). |
| `hvsr_plot_inversion.py` | `MisfitHistCanvas` + `VsProfileCanvas`. |
| `chart_render.py` | **Facade** rasterizer: `HvsrChart` composed from `ChartRenderer` / `ChartCurveMixin` / `ChartMapMixin`, the palette block + `apply_palette()` propagation, and re-exports (`write_png`, the font, the colour constants). |
| `chart_png.py` | The pure-stdlib PNG encoder (`write_png`). |
| `chart_font.py` | The 5x7 bitmap font + `_draw_text` / `_text_width`. |
| `chart_render_core.py` | `ChartRenderer`: pixel buffer + drawing primitives + log axes/grid. |
| `chart_render_curves.py` | `ChartCurveMixin`: `draw_hvsr` / `draw_spectra` / `draw_timeseries`. |
| `chart_render_maps.py` | `ChartMapMixin`: `draw_colormap` / `draw_vs_profile` + the `_viridis` colour map. |
| `hvsr_engine.py` | **Facade** for the analysis pipeline (all names re-exported). |
| `hvsr_engine_defaults.py` | The `DEFAULT_*` processing defaults + `MAX_PICK_FREQ`. |
| `hvsr_engine_spectra.py` | Windowed spectra: `compute_spectra`, `coherence`, `hv_vs_time` / `hv_vs_azimuth`, the window primitives, `log_frequencies`. |
| `hvsr_engine_preprocess.py` | `trim_seconds` + `preprocess` (detrend / taper / band-pass). |
| `hvsr_engine_core.py` | `analyze` / `_finalize_analysis`, `HvsrResult`, peak picking + quality, SESAME evaluation, window rejection. |
| `hvsr_engine_report.py` | `_build_log` + `write_target_file` / `write_report_file`. |
| `hvsr_engine_autotune.py` | The two-stage auto-tune sweep (`auto_tune`, `_stage2_*`, `sesame_score`, `_SMOOTH_DEFAULTS`). |
| `hvsr_engine_support.py` | Shared FFT / window / peak-finding helpers. |
| `hvsr_dsp.py` | **Facade** for the DSP modules (all names re-exported). |
| `hvsr_dsp_fft.py` | FFT (radix-2 + Bluestein + real-input fast path) and instrument pole-zero (`parse_paz`, `paz_response`, `paz_deconvolve`). |
| `hvsr_dsp_filters.py` | Filter design: Butterworth / Chebyshev-I / Bessel + `butter_bandpass` / `bandpass_filter`. |
| `hvsr_dsp_lfilter.py` | Filter application: `_filtfilt` + the `_lfilter` family. |
| `hvsr_dsp_stats.py` | Demean / detrend / taper, STA/LTA, the four smoothing operators, `decimate`, `resolve_workers`. |
| `hvsr_standards.py` | **Facade** for the standards modules (re-exports everything). |
| `hvsr_standards_data.py` | The `STANDARDS` table, thickness & Vs30 relations, the `estimate_*` helpers. |
| `hvsr_standards_eval.py` | The `evaluate_*` criteria, `_EVALUATORS`, `evaluate_all` / `build_standards_report` / `recommended_params`. |
| `hvsr_inversion.py` | **Facade** for the inversion modules (re-exports everything). |
| `hvsr_inv_forward.py` | Model layer: log-frequency helpers, `vp_from_vs`, `density_from_vp`, `vs30_from_profile`, model seeding, `hvsr_misfit`. |
| `hvsr_inv_phasevel.py` | Phase-velocity dispersion (the `_dltar4` / `_nevill` / `_getsol` root-finding chain). |
| `hvsr_inv_ellipticity.py` | The Rayleigh-wave ellipticity branch (`_dnka_eg` / `_svup` / `rayleigh_ellipticity`). |
| `hvsr_inv_report.py` | Inversion log / CSV / report writers + `misfit_histogram` / `_percentile`. |
| `hvsr_inv_driver.py` | `invert_hvsr` (the Monte-Carlo driver), `_inv_chunk_eval`, `InversionResult`. |
| `hvsr_io.py` | **Facade** for loading (re-exports `auto_load`, `ThreeChannel`, `DataError`, `classify_component`, ...). |
| `hvsr_io_data.py` | `ThreeChannel`, `DataError`, the text-parsing helpers and `classify_component`. |
| `hvsr_io_loaders.py` | The format loaders + the `auto_load` dispatcher. |
| `mseed_io.py` | **Facade**: `read_mseed` + re-exports of the decode / parse / write modules. |
| `hvsr_mseed_decode.py` | Sample decoders (STEIM-1/2, int24, floats) + `MseedError`. |
| `hvsr_mseed_parse.py` | Record framing, byte order, sample-rate inference, B-time helpers. |
| `hvsr_mseed_write.py` | `write_mseed` + the rate-factor helper. |
| `eqd_io.py` / `sg2_io.py` | The from-scratch `.eqd` and SEG-2 readers (automatic component detection). |
| `hvsr_geopsy.py` | Optional cross-check against the external Geopsy program if the user has it installed. |
| `make_sample_data.py` | Generates the synthetic 2 Hz test station; basis of the `examples/` signals. |

## The functional contract

This is what the program must do — treat it as the spec: a feature not
listed here is not part of the program.

1. **Input any supported signal type** — one 3-column text/CSV file, three
   single-component text files, three miniSEED files, one `.eqd` raw
   recording, or one SEG-2 (`.sg2`) file, plus an optional SAC pole-zero
   (`.pz`) response file.
2. **Assign the components (N / E / Z) automatically** — from the SEG-2
   `NOTE` field, file names or channel order — with a manual
   *Swap N / E* override.
3. **Window size**: user-selectable *and* recommended automatically (Auto
   mode / Apply-Method / auto-tune).
4. **Automatic time-range selection** — Start (s) and End (s) fields; empty
   = whole recording.
5. **Filter**: manually insertable (band edges, order, prototype
   Butterworth / Chebyshev-I / Bessel) *and* recommended automatically.
6. **Frequency band** (fmin / fmax): manually insertable *and* recommended
   automatically.
7. **Smoothing**: one of four operators — Konno-Ohmachi, moving average,
   triangular constant, triangular proportional — with adjustable width,
   plus automatic recommendations.
8. **Horizontal sum type**: arithmetic mean, geometric mean, or mean square.
9. **SESAME reliability checklist and peak** per the published formulas,
   with automatic parameter tuning for the most reliable result
   (auto-tune: window, rejection, smoothing, width, H/V formula).
10. **Output the H/V graph with f0 and A0** (on-chart marker + legend, PNG
    export, text report).
11. **1D inversion**: build a layered soil model from the H/V curve
    (seeded from f0 / A0 / Vs30), run a Monte-Carlo inversion against the
    theoretical Rayleigh-wave ellipticity, and report depth, Vs, Vs30 and
    the soil type (NEHRP and SNI site classes) per layer.
12. **Every automatic recommendation is based on published guidelines** —
    SESAME 2004 (Europe), Japan (J-SHIS / JAMC), Indonesia
    (SNI 1726-2019 / BMKG), USGS / NEHRP, and a Generic industry checklist.

All of the above is implemented.

## Validation history

The pipeline was validated end-to-end against real field datasets (miniSEED,
`.eqd` and SEG-2 recordings): every file in the validation set loaded with
zero failures, and the benchmark station reproduces the Geopsy reference f0
(~1.6-2.4 Hz depending on station).  The 1D inversion was cross-checked
against Dinver reference bounds (Vs30 inside the Dinver range, 3/5 layers
fully inside the official Vs bounds).  The bundled example signals carry a
known 2 Hz resonance so any regression in the pipeline shows up in the tests
immediately.

## Testing

Five suites, 213 tests, all pure unittest — run any of them from the repo
root:

```
python tests/test_engine.py      # 24 tests: FFT (vs brute-force DFT), filters,
                                 #   Konno-Ohmachi, STA/LTA, pole-zero, full
                                 #   analysis recovering the known 2 Hz peak
python tests/test_io.py          # 8 round-trip tests for the readers
python tests/test_extras.py      # 62: STEIM, standards, routing, chart exports,
                                 #   themes, example-signal round-trips, and the
                                 #   sequential-vs-parallel equivalence pin
python tests/test_gui.py         # 100 GUI tests (tkinter, window hidden)
python tests/test_inversion.py   # 19: forward model vs analytic half-space,
                                 #   inversion recovery, ensemble uncertainty
```

The parallel and sequential paths must stay **result-identical** —
`tests/test_extras.py::TestSpeedups` pins that, so don't "optimise" one path
and forget the other.

## Building

### Run from source

```
python src/main.py        # or double-click run.bat
```

### Package the standalone app (no Python needed by users)

PyInstaller bundles a private Python runtime + tkinter into the exe:

```
pip install pyinstaller tkinterdnd2
python scripts/build_exe.py      # -> dist/HVSR_Analyzer/
```

`build_exe.py` passes `--collect-all tkinterdnd2`, so the packaged app
includes the native tkdnd binaries and drag-and-drop works out of the box
for end users.

The installer (`installer/HVSR_Analyzer_Setup.iss`) additionally registers
the `.eqd` / `.sg2` / `.mseed` / `.miniseed` file types (per-user `HKCR`,
removed on uninstall).  Double-clicking a recording launches the exe with
that path on the command line; `hvsr_gui.main()` picks it up and mounts it
through the same code path as a drop (`HVSRAppDndMixin._mount_cli`), so a
single file or a Z/N/E trio both work.

### Build the installer

1. Build the standalone app (above).
2. Compile `installer/HVSR_Analyzer_Setup.iss` with the free
   [Inno Setup 6](https://jrsoftware.org/isinfo.php):
   `ISCC.exe installer/HVSR_Analyzer_Setup.iss`
3. The single-file setup appears at `installer/Output/HVSR_Analyzer_Setup.exe`.

CI (`.github/workflows/build-installer.yml`) does all of this automatically
on push/PR, and attaches the setup exe to GitHub Releases on `v*` tags:

```
git tag v1.1.0
git push origin v1.1.0
```

## Conventions

- **Pure stdlib only.** See [the one rule](#the-one-rule-that-shapes-everything).
- **Keep results bit-stable.** Any refactor of `analyze` / `auto_tune` must
  keep the sequential path unchanged — the tests pin f0 recovery and
  seq == parallel equivalence.
- **GUI work goes on daemon threads.** Long-running work reports through the
  queue; emit a `("progress", (done, total, note))` message for anything that
  should drive the progress bar.
- **Every parallel worker is module-level and picklable** (Windows uses
  `spawn`). Keep the `if __name__ == "__main__":` guard in every entry-point
  script so spawned children never re-run it.
- **`main.py` calls `multiprocessing.freeze_support()`** — required for the
  PyInstaller build; keep it.

### Environment variables

| Variable | Effect |
|---|---|
| `HVSR_WORKERS` | Caps the worker-process count for the auto-tune sweep and the inversion. `0` / `1` forces sequential mode. |
| `HVSR_TOUR` | `1` forces the guided tour on launch (the first-run tour otherwise shows once, remembered in `~/.hvsr_tour_done`). |

## Scripts (dev tools)

`scripts/` holds one-off tools used during development and validation, not
shipped to users:

- `make_examples.py` — regenerates + self-validates the example signals.
- `make_screenshots.py` — captures both themes for the docs (needs Pillow +
  a display session; the app itself never needs Pillow).
- `e2e_all.py`, `validate_all_signals.py` — run the whole pipeline over real
  field datasets and write per-station reports.
- `compare_geopsy.py`, `compare_dinver.py` — cross-validate against the
  external Geopsy and Dinver programs.
- `sweep_*.py`, `criterion_f0*.py`, `rejection_criteria.py`,
  `investigate_rejection.py`, `verify_*.py`, `merge_fullcmp.py` — parameter
  investigations used to tune the defaults.
- `build_exe.py` — the PyInstaller build (see [Building](#building)).

## Common extension tasks

- **Add a smoothing operator** → implement it in `hvsr_dsp_stats.smooth_spectrum`
  (+ `_smooth_bands`), then register its defaults in `_SMOOTH_DEFAULTS` in
  `hvsr_engine_autotune.py` — the auto-tune sweep picks it up automatically.
- **Add a guideline standard** → new entry in `hvsr_standards_data.STANDARDS`
  (checklist items, thresholds, site classes).
- **Add a file format** → a reader module exposing `load(path)` returning a
  `ThreeChannel`, registered in `hvsr_io_loaders.auto_load`.
- **Add a guided-tour step** → append a step dict to `HVSRApp._tour_steps()`
  (`page` / `nb_tab` pre-actions + a `target` widget or callable).
- **Regenerate the example signals** → `python scripts/make_examples.py`.
- **Regenerate the README/tutorial screenshots** →
  `python scripts/make_screenshots.py`.

## Performance notes

- **Window spectra are cached**: `auto_tune` computes each window's raw
  magnitude spectra once per window length and reuses them across every
  smoothing / width / combination, so the 32-combination max-reliability
  sweep costs roughly one FFT pass.
- **Real-input FFT**: `fft_real` (in `hvsr_dsp_fft.py`) computes an
  even-length real FFT via one half-size complex FFT (~2x faster); Bluestein
  chirp tables and the Konno-Ohmachi weight bands are memoized.
- **Parallelism**: the stage-2 sweep and the inversion Monte-Carlo use
  `ProcessPoolExecutor` when `n_workers > 1`; every parallel block falls back
  to sequential on any platform error. See `resolve_workers()` in
  `hvsr_dsp_stats.py`.

## Packaging gotchas (learned the hard way)

- The frozen app's default output folder is next to the **exe**, not inside
  PyInstaller's internal bundle directory — see `hvsr_gui._out_dir()`.
- The Inno installer removes files from pre-1.1.0 installs
  (`[InstallDelete]`) and force-wipes the whole bundle on uninstall
  (`[UninstallDelete]`) because Inno's per-file log deletion proved
  unreliable for the large recursed bundle tree. Don't "simplify" that away
  without re-running the full install → launch → uninstall cycle.

## Contributing

- Keep the README (users) and `docs/DEVELOPER.md` (developers) separate and
  in their lanes — one doc that tries to serve both confuses both.
- Update the CHANGELOG for user-visible changes.
- Run the full test suite before opening a PR; add tests for new behaviour.
- Write code that reads like it was explained to a colleague: docstrings on
  public functions, comments on anything non-obvious, no commented-out
  corpses.

Happy digging — and if the ground moves, at least the model says so.
