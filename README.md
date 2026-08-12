# HVSR Analyzer

[![Build installer](https://github.com/NazreenNasyuha/HVSR_Analyzer/actions/workflows/build-installer.yml/badge.svg)](https://github.com/NazreenNasyuha/HVSR_Analyzer/actions/workflows/build-installer.yml)

**A friendly desktop app that turns microtremor recordings into ground-motion
results — no Python to install, no packages to fiddle with. It just runs.**

HVSR Analyzer reads the raw recordings you bring back from the field and does
the heavy lifting for you:

- computes the **H/V spectral ratio curve** (the standard microtremor
  analysis) from a wide range of file formats,
- **drag and drop** your files straight onto the window — three component
  files, one .eqd/.sg2/3-column file, or a .pz response file. Drop a folder
  to batch-process it; double-click a recording in Explorer to open it
  directly,
- checks how **reliable your result is** against the SESAME 2004 guidelines
  (plus Japan, Indonesia / SNI 1726-2019, USGS and a generic checklist),
- and can **invert that curve into a layered soil model** — depth, shear-wave
  velocity (Vs), Vs30 and the soil class (NEHRP / SNI) for each layer.

The whole thing is **pure Python with no required third-party packages** —
no numpy, scipy, obspy or matplotlib under the hood. For you that means: no
Python installation, no environment setup, no dependency hell.

> New here? Start with the [First-Time User Tutorial](docs/TUTORIAL.md). It
> walks you through the whole workflow using the bundled example signals —
> no field data required.

---

## What it looks like

The app ships with two themes. The default retro **dark** look is easy on the
eyes in the field; the **Black & White (Thesis)** theme is made for printing —
white backgrounds, black lines and grayscale colour maps.

### Dark theme (default)

![Main window, dark theme](docs/screenshots/dark_01_input_output.png)

![H/V curve result, dark theme](docs/screenshots/dark_02_hv_curve.png)
![1D inversion result, dark theme](docs/screenshots/dark_06_inversion.png)

### Black & White (Thesis) theme

![Main window, B&W theme](docs/screenshots/bw_01_input_output.png)

![H/V curve result, B&W theme](docs/screenshots/bw_02_hv_curve.png)
![SESAME method checklist, B&W theme](docs/screenshots/bw_04_checklist.png)
![1D inversion result, B&W theme](docs/screenshots/bw_06_inversion.png)

---

## Getting it running

1. Download **`HVSR_Analyzer_Setup.exe`** from the
   [Releases](https://github.com/NazreenNasyuha/HVSR_Analyzer/releases) page.
2. Run the installer. It installs **per-user** (no administrator rights
   needed) and bundles its own private Python runtime — **you never have to
   install Python**.
3. Launch **HVSR Analyzer** from the Start menu. On first run, a guided tour
   points at every control and explains what it does. Press **SHOW TOUR** in
   the header (or set `HVSR_TOUR=1` when starting) to replay it any time.

**Prefer to run from source?** You'll need Python 3.8+ and nothing else
(drag & drop additionally wants `pip install tkinterdnd2`; everything else
runs without it):

```
python src/main.py
```

---

## What you can do with it

- **Load recordings** in almost any form your field gear produces: one
  3-column text/CSV file, three single-component text files, three miniSEED
  files, one `.eqd` raw recording, or one SEG-2 (`.sg2`) file. The app
  figures out the North / East / Vertical components for you (with a manual
  *Swap N / E* override if it guesses wrong). An optional SAC pole-zero
  (`.pz`) response file is accepted too.
- **Choose how careful you want to be** — pick every processing parameter by
  hand, or press one button to have the program fill in recommended values
  from the SESAME / Japan / Indonesia / USGS / Generic methods.
- **Trust the result, not vibes** — a built-in reliability checklist scores
  your H/V curve against the official SESAME criteria, and an *auto-tune*
  mode even searches the parameters for you until the score is as good as it
  gets.
- **Invert the H/V curve into a soil model** — the 1D inversion builds a
  layered model automatically, runs a Monte-Carlo search, and reports the
  depth, Vs and soil class of every layer plus Vs30. You get uncertainty
  ranges for each layer, not just one number.
- **Process a whole folder** of stations in one go (batch mode), with a live
  progress bar.
- **Save what you need** — full text reports, the H/V chart as a PNG, the
  data as CSV, the inversion model — wherever you want.

## Need help?

- [First-Time User Tutorial](docs/TUTORIAL.md) — step-by-step walkthrough
  with the bundled example signals.
- [Developer documentation](docs/DEVELOPER.md) — for people who want to
  build, extend or contribute to the code. (Not needed to *use* the app.)
- [CHANGELOG.md](CHANGELOG.md) — what changed in each version.
- Found a problem? Open an issue on
  [GitHub](https://github.com/NazreenNasyuha/HVSR_Analyzer/issues).

---

## License & copyright

Copyright (c) 2026 NazreenNasyuha.

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE)
file for the full text. In short: use it, modify it, share it — just keep the
copyright notice and don't blame us if the ground moves differently than the
model predicted.
