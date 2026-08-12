"""
hvsr_inversion.py
=================
1D inversion of an observed H/V spectral-ratio curve into a layered
S-wave velocity (Vs) profile.  Pure standard library - no numpy, scipy,
obspy, disba, geopsy.

Two parts:

1. FORWARD MODEL
   The theoretical H/V of a layered soil model is taken as the surface
   ellipticity of the fundamental-mode Rayleigh wave.  This is computed
   from scratch with the classic Thomson-Haskell / Dunkin (1965) compound
   (delta) matrix algorithm - the same algorithm as Herrmann's Computer
   Programs in Seismology 'surf96' / 'swegn96' (and the 'disba' Python
   package, which this port follows) - written here on the standard
   library only.

   - the dispersion (period equation) is evaluated with the real-arithmetic
     Dunkin matrix (CPS 'dltar'),
   - the phase velocity of the fundamental mode is found with the CPS
     bracketing + Neville/bisection hybrid root finder ('getsol'/'nevill'),
   - the surface ellipticity H/V = |u_x/u_z| is recovered from the
     compound vector built upwards from the half-space ('swegn96'
     eigenfunction recursion), which is normalised at every layer so it
     stays stable for thin layers / high frequencies.

   Units are converted internally to km, km/s and g/cm^3 (the CPS
   convention); the public API works in metres and m/s.

2. INVERSION
   A parameterised Monte-Carlo search over the Vs profile:

     - layers 1..n (n user-selectable, default 3) + a half-space,
     - each layer gets a Vs drawn log-uniformly from bounds built around
       an initial model that is *seeded automatically from the H/V result*
       (f0 sets the first-layer thickness via the quarter-wavelength
       relation h1 ~ Vs1/(4*f0); the Vs30 estimate anchors the velocity
       level; deeper layers are progressively faster),
     - optional monotonicity constraint (Vs must increase with depth),
     - the synthetic H/V is compared with the observed curve on a
       log-spaced frequency grid around f0 (log-domain L2 misfit),
     - the best-fitting models are kept and averaged into a final profile,
       with Vs30 (harmonic mean over the top 30 m), NEHRP and SNI
       site classes, and a per-layer soil-type table.

This lets the program answer the classic question: given the H/V
curve, what layered Vs model (layer depths + velocities) produced it, and
what kind of soil is that?
"""
import math
import random
from hvsr_dsp import resolve_workers
import statistics


# Re-exported from hvsr_inv_driver (split out of hvsr_inversion) - the
# public API stays importable from here.
from hvsr_inv_driver import InversionResult, _inv_chunk_eval, _peak_index, invert_hvsr
# Re-exported from hvsr_inv_ellipticity (split out of hvsr_inversion) - the
# public API stays importable from here.
from hvsr_inv_ellipticity import _dnka_eg, _evalg, _svup, _varsv, rayleigh_ellipticity
# Re-exported from hvsr_inv_forward (split out of hvsr_inversion) - the
# public API stays importable from here.
from hvsr_inv_forward import TWO_PI, _normc, _sign, _var, density_from_vp, hvsr_misfit, log_frequencies, resample_log, sample_model, seed_model, vp_from_vs, vs30_from_profile
# Re-exported from hvsr_inv_phasevel (split out of hvsr_inversion) - the
# public API stays importable from here.
from hvsr_inv_phasevel import _dltar4, _dnka_real, _getsol, _gtsolh, _nevill, _phase_velocities
# Re-exported from hvsr_inv_report (split out of hvsr_inversion) - the
# public API stays importable from here.
from hvsr_inv_report import _build_inversion_log, _percentile, misfit_histogram, write_inversion_csv, write_inversion_report
