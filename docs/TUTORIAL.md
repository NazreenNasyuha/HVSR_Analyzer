# HVSR Analyzer — First-Time User Tutorial

This guide walks you through the whole workflow, from launching the app to
reading your first H/V result — and it uses the **bundled example signals**
so you can follow along without any field data.

> **Time needed:** about 10 minutes. **What you need:** the app itself —
> either the [installed version](../README.md#getting-it-running) (no Python
> required) or Python 3.8+ if you'd rather run it from source.

---

## 0. The three example signals

A folder `examples/` ships with the project. It contains one example
recording in each supported raw format, all generated from the **same
synthetic microtremor signal with a known 2 Hz resonance**:

| Example | What it is |
|---|---|
| `examples/example.eqd` | `.eqd` raw recording — **one file**, three components |
| `examples/example_Z.mseed` + `example_N.mseed` + `example_E.mseed` | miniSEED — **three files**, one per component |
| `examples/example.sg2` | SEG-2 — **one file**, three traces |

Whichever you pick, a correct run should find **f0 ≈ 2 Hz** with a peak
amplitude **A0 ≈ 4**. That makes it easy to tell a good run from a
mis-configured one.

---

## 1. Launching the app

### Option A — installed version (easiest)

Run the app from the Start menu / desktop shortcut created by the installer.

### Option B — run from source

Open a terminal in the project folder and run:

```
python src/main.py
```

On Windows you can also double-click `run.bat`.

You should see the main window with the **4-step workflow** on the left and
the results tabs on the right.  Click the **TUTORIAL** button in the top
header to re-open this guide from inside the app at any time (it also ships
with the installed version as `docs/TUTORIAL.md`):

```
+-----------------------------------------------------------------+
| HVSR ANALYZER  100% STANDARD LIBRARY        THEME [DARK (CLASSIC)]|
+-----------------------------------------------------------------+
| LEFT: 01_INPUT/OUTPUT | RIGHT: [ H/V CURVE ]  [ TIME SERIES ]   |
|       02_PRE_PROCESS  |        [ PSD & SPECTRA ]  [ CHECKLIST ]  |
|       03_HV_PARAMS    |        [ REPORT ]  [ SYSTEM LOG ]       |
|       04_OUTPUT_DATA  |        [ 1D INVERSION ]                  |
+-----------------------------------------------------------------+
```

---

## 2. Load an example signal (Step 1 of the workflow)

1. Go to tab **01_INPUT/OUTPUT**.
2. Click **AUTO-ASSIGN FILES...** and in the dialog pick:
   - **one file** — `examples/example.eqd` **or** `examples/example.sg2`, **or**
   - **three files** — `example_Z.mseed`, `example_N.mseed`, `example_E.mseed`
     (select all three together).
3. The **VERTICAL (Z)**, **NORTH (N)** and **EAST (E)** slots fill themselves.
   The **waveform preview** at the bottom of the tab should draw three noisy
traces as soon as the files load — if it does, the components are in the
right slots.
4. (Optional) click **ANALYSE SIGNAL** to look at the raw power spectrum or
   the coherence of the components before processing.

> **Hint:** leave the *Start / End* time fields empty (or click **USE FULL**)
> and leave *Save to* empty — the app will create an `HVSR_Results` folder
> next to the input file.

> **Even quicker — drag and drop:** you can skip the dialogs entirely and
> drop files straight onto the window:
>
> - drop the three `example_Z/N/E.mseed` files **together** — the slots fill
>   themselves and the preview updates automatically;
> - drop a single `.eqd` / `.sg2` / 3-column file — it goes into **Z**;
> - drop a `.pz` file — it lands in the **RESPONSE** slot;
> - drop a *folder* — the app immediately starts **BATCH PROCESS FOLDER**
>   on it.
>
> The whole input card highlights while you drag, so you always know the
> window is ready to receive the files.  And in the installed version you
> can also just **double-click** a recording (`.eqd` / `.sg2` / `.mseed` /
> `.miniseed`) in Explorer — the app opens with it already loaded.  That
> behaviour is a per-user setting you can turn on or off any time with the
> **FILE ASSOCIATIONS** checkbox on tab 04.

---

## 3. Pre-processing (Step 2)

The defaults on tab **02_PRE_PROCESS** are sensible for microtremor data:

- **BAND-PASS** 0.2 – 20 Hz
- **STA/LTA transient muting** on
- **decimation** on

Click **PREVIEW FILTERED WAVEFORM** to see the cleaned traces with the
analysis window overlaid (green, in the dark theme). You can adjust the
window length and preview again — the app shows exactly what the H/V
calculation will use.

---

## 4. H/V parameters (Step 3)

On tab **03_HV_PARAMS**:

1. Click **APPLY METHOD RECOMMENDATIONS** and pick **SESAME 2004 (Europe)**
   — this fills every field with the SESAME-recommended values.
2. Leave the rest as-is (or switch to **Auto (suggest)** and the program
   tunes the window length and rejection itself).
3. Click **SHOW H/V VIEWS** for a quick interactive preview of the four
   analysis charts (time-frequency map, azimuth map, average spectra and
   the average H/V curve) without saving anything.

> Tip: you can **Save...** the parameter profile to JSON and **Load...** it
> later, so a tuned setup can be reused or shared.

---

## 5. Output options (Step 4)

On tab **04_OUTPUT_DATA**, tick what you want to produce:

- **Report** (`.txt`) — the full SESAME/analysis report,
- **Target** (`.target`) — for Geopsy-style inversion workflows,
- **Chart PNG** — the H/V curve picture,
- **Data CSV** — the H/V curve data,
- **PSD & spectra computation** — extra spectra tab,
- **Geopsy cross-check** — only if Geopsy is installed (optional).

---

## 6. Run the analysis

Press **RUN ANALYSIS** (top of the workflow) and watch the status bar and
system log. When the run completes you'll see something like:

```
f0 = 2.014 Hz | A0 = 4.03 | Kg = ...
```

Now explore the right-hand result tabs:

- **[ H/V CURVE ]** — the average H/V curve with the **f0** peak marked.
  For the example signals the peak sits at ~2 Hz.
- **[ TIME SERIES ]** — the cleaned Z / N / E traces with the windows used.
- **[ PSD & SPECTRA ]** — the component power spectra.
- **[ CHECKLIST ]** — the SESAME reliability matrix with a score **x/6**.
- **[ REPORT ]** — the full plain-text report.
- **[ SYSTEM LOG ]** — every step the app took.

---

## 7. Optional: run the 1D inversion

Open the **[ 1D INVERSION ]** tab and press **RUN 1D INVERSION** — the
program inverts the H/V curve into a layered Vs model (Monte-Carlo with
uncertainty) and draws the Vs profile plus the misfit histogram. You can
**EXPORT REPORT** or **EXPORT MODEL CSV** afterwards.

---

## 8. Switching themes (thesis / print mode)

Use the **THEME** selector in the header:

- **DARK (CLASSIC)** — the default retro black / neon terminal look.
- **B&W (THESIS)** — high-contrast black-and-white, designed to be printed
  in a thesis or paper. Every control *and every exported PNG* switches to
  the black-and-white look, so your printed figures stay consistent.

The theme is remembered for the session only; it starts on DARK each launch.

---

## 9. Common questions

**Q: f0 is stuck at 0.5 Hz (the lower edge of the search range)?**
That usually means no clean peak was found — check that the three components
really are in the right slots (re-run with **Swap N/E** ticked if the curve
looks wrong) and that the window length is long enough.

**Q: The miniSEED files won't load on their own?**
A single miniSEED file holds only one component. Select **all three**
`example_*.mseed` files together — or drag and drop them onto the window as
a group — or use the `.eqd` / `.sg2` single-file examples instead.

**Q: Where did my results go?**
If you left *Save to* empty, look for an `HVSR_Results` folder next to the
input file. Every run is also appended to `data_log.csv` there.

**Q: How do I process a whole folder of recordings?**
Use **BATCH PROCESS FOLDER...** on the workflow — or simply drag the folder
onto the window. The app analyses every compatible file in it, writing
per-station reports/CSVs/PNGs plus an `all_stations_summary.csv`, and
flashes the taskbar when the batch finishes.

---

## 10. Next steps

- Read the full [README](../README.md) for the complete feature list.
- Use `scripts/make_examples.py` to regenerate or modify the example signals.
- See `tests/test_gui.py` for a scripted walk-through of the whole GUI
  workflow (it automates exactly what this tutorial does by hand).
