"""
hvsr_standards_data.py
======================
Static data tables and the estimators built on them:

- STANDARDS : the per-standard recommended processing parameters,
- THICKNESS_RELATIONS / DEFAULT_THICKNESS_RELATION : Vs30 -> sediment
  thickness scaling relations,
- DEFAULT_VS30_A/B, DEFAULT_VS_AVG, DEFAULT_VS_BEDROCK and the
  VS30_RELATION_CITATION text, plus DEFAULT_STANDARD,
- estimate_thickness / estimate_vs30_powerlaw / estimate_vs30_from_thickness.

Split out of hvsr_standards.py.
"""


THICKNESS_RELATIONS = {
    "Ibs-von Seht & Wohlenberg (1999)": (
        96.0, -1.388, "Germany (Rhine area)",
        "Ibs-von Seht, M. & Wohlenberg, J. (1999). Microtremor measurements "
        "used to map thickness of soft sediments. Bull. Seism. Soc. Am. 89."),
    "Delgado et al. (2000)": (
        55.0, -1.214, "SE Spain (alluvial basins)",
        "Delgado, J. et al. (2000). Microtremors as a geophysical "
        "exploration tool. J. Applied Geophysics."),
    "Parolai et al. (2002)": (
        108.0, -1.551, "Cologne, Germany",
        "Parolai, S., Bormann, P. & Milkereit, C. (2002). New relationships "
        "between Vs, thickness of sediments, and resonance frequency. "
        "Bull. Seism. Soc. Am. 92."),
    "D'Amico et al. (2008)": (
        121.3, -1.217, "Italy",
        "D'Amico, V., Picozzi, M., et al. (2008). Quick estimates of soft "
        "sediment thickness from ambient noise H/V. Boll. Geofis. Teor. "
        "Appl. 49."),
    "Birgören et al. (2009)": (
        66.7, -1.092, "Istanbul, Turkey",
        "Birgören, G., Özel, O. & Siyahi, B. (2009). Bedrock depth mapping "
        "of the coast south of Istanbul by ambient noise. Geophys. J. Int."),
}

DEFAULT_THICKNESS_RELATION = "Ibs-von Seht & Wohlenberg (1999)"

DEFAULT_VS30_A = 38.0

DEFAULT_VS30_B = 0.997

VS30_RELATION_CITATION = (
    "Vs30 = a * f0^b power law, e.g. the calibration used in Italian "
    "soft-soil studies (Vs30 = 38 * f0^0.997); constants are site-specific "
    "and can be adjusted in the GUI.")

DEFAULT_VS_AVG = 300.0

DEFAULT_VS_BEDROCK = 800.0

STANDARDS = {
    "sesame": {
        "id": "sesame",
        "name": "SESAME 2004 (Europe)",
        "region": "Europe / international",
        "source": "SESAME Project, 2004 - 'Guidelines for the "
                  "implementation of the H/V spectral ratio technique on "
                  "ambient vibrations' (Bard & SESAME Team).",
        "params": {"win_len": 30.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Full 7-criterion reliability matrix (curve + peak). "
                   "Reliable when the curve and peak criteria all pass.",
    },
    "japan": {
        "id": "japan",
        "name": "Japan (J-SHIS / JAMC)",
        "region": "Japan",
        "source": "Japanese microtremor survey guideline (JAMC) and NIED "
                  "J-SHIS practice: 30-60 s windows, >= 10 windows, "
                  "0.2-20 Hz analysis range, clear-peak criteria, Vs30 "
                  "estimate from f0.",
        "params": {"win_len": 60.0, "rejection": 2.0, "fmin": 0.2,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Requires a clear f0 in the 0.2-20 Hz band, at least 10 "
                   "windows and a stable peak; reports Vs30 and NEHRP "
                   "site class.",
    },
    "indonesia": {
        "id": "indonesia",
        "name": "Indonesia (SNI 1726-2019 / BMKG)",
        "region": "Indonesia",
        "source": "SNI 1726-2019 site classes (SA-SF, Vs30 thresholds "
                  "1500/750/350/175 m/s) applied to the HVSR result; H/V "
                  "processing follows the SESAME 2004 criteria as used in "
                  "Indonesian microzonation studies (BMKG practice).",
        "params": {"win_len": 30.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "SESAME-style reliability checks plus the SNI 1726-2019 "
                   "Vs30 site class (SA-SF) used by the Indonesian seismic "
                   "code.",
    },
    "usgs": {
        "id": "usgs",
        "name": "USGS / NEHRP",
        "region": "United States",
        "source": "NEHRP site classification (Vs30-based, NEHRP 2003 / "
                  "ASCE 7) applied to the HVSR result; peak-clarity "
                  "practice per USGS microtremor studies.",
        "params": {"win_len": 30.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Assigns the NEHRP site class (A-E) from the Vs30 "
                   "estimate and checks peak clarity.",
    },
    "generic": {
        "id": "generic",
        "name": "Generic / Industry",
        "region": "portable",
        "source": "Common surveyor practice (e.g. Geometrics H/V "
                  "guidelines): >= 10 windows, clear peak A0 > 2, f0 in "
                  "range, stable f0 across windows.",
        "params": {"win_len": 40.0, "rejection": 1.5, "fmin": 0.5,
                   "fmax": 20.0, "nfreq": 512, "b_value": 40.0,
                   "taper": 0.05, "max_iterations": 50, "overlap": 0.0,
                   "f_low": 0.2, "f_high": 20.0, "sta_sec": 1.0,
                   "lta_sec": 30.0, "slta_threshold": 2.5,
                   "max_fs": 250.0, "filter_type": "butterworth",
                   "filter_order": 5, "filter_ripple": 0.5,
                   "smoothing": "konno_ohmachi", "smooth_width": 40.0,
                   "combo": "geometric"},
        "summary": "Portable best-practice checklist that works for any "
                   "region.",
    },
}

DEFAULT_STANDARD = "sesame"

def estimate_thickness(f0, relation=DEFAULT_THICKNESS_RELATION):
    """Sediment thickness h (m) from f0 using a published relation."""
    if f0 <= 0:
        return None
    a, b, region, citation = THICKNESS_RELATIONS[relation]
    return max(a * (f0 ** b), 0.0)

def estimate_vs30_powerlaw(f0, a=DEFAULT_VS30_A, b=DEFAULT_VS30_B):
    """Vs30 from f0 using Vs30 = a * f0^b."""
    if f0 <= 0:
        return None
    return a * (f0 ** b)

def estimate_vs30_from_thickness(f0, relation=DEFAULT_THICKNESS_RELATION,
                                 vs_avg=DEFAULT_VS_AVG,
                                 vs_bedrock=DEFAULT_VS_BEDROCK):
    """Vs30 from the estimated sediment thickness and assumed velocities.

    If the sediment column is >= 30 m deep the whole 30 m profile is soft
    sediment (Vs ~ Vs_avg).  If it is thinner, the remaining depth down to
    30 m is assumed to be bedrock (Vs ~ Vs_bedrock).
    """
    h = estimate_thickness(f0, relation)
    if h is None:
        return None
    if h >= 30.0:
        return vs_avg
    if h <= 0.0:
        return None
    return (vs_avg * h + vs_bedrock * (30.0 - h)) / 30.0
