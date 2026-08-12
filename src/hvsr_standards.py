"""
hvsr_standards.py
=================
Global HVSR (microtremor H/V) method guidelines and regional standards.

This module lets the same H/V result be checked against the *official*
procedures used in different parts of the world, so one recording can be
verified following the method of the country that will receive the report:

  * SESAME 2004 (Europe) ......... the European guideline from the SESAME
                                   project (Bard & SESAME Team, 2004) -
                                   full 7-criterion reliability matrix.
  * Japan J-SHIS / JAMC ......... the Japanese microtremor survey guideline
                                   (JAMC, "Shin-jishin..." / NIED J-SHIS
                                   practice): 30-60 s windows, >=10 windows,
                                   0.2-20 Hz range, clear-peak criteria and
                                   a Vs30 estimate from f0.
  * USGS / NEHRP ............... American practice: peak clarity + NEHRP
                                   site-class (Vs30-based) assignment.
  * Generic / industry .......... a portable best-practice checklist
                                   (used by Geometrics and most surveyors).

Each standard contributes:
  - recommended processing parameters (window length, rejection, range),
  - a pass/fail checklist computed from the analysed curve,
  - empirical estimates of sediment thickness h and Vs30 from f0 (with
    published relations whose constants are user-adjustable).

Empirical relations implemented (thickness h [m] from f0 [Hz]):
  * Ibs-von Seht & Wohlenberg (1999), Germany:  h = 96.0 * f0^-1.388
  * Delgado et al. (2000), SE Spain:             h = 55.0 * f0^-1.214
  * Parolai et al. (2002), Cologne:              h = 108.0 * f0^-1.551
  * D'Amico et al. (2008), Italy:                h = 121.3 * f0^-1.217
  * Birgören et al. (2009), Istanbul:            h = 66.7 * f0^-1.092

Vs30 is estimated two ways:
  1. from a published power law Vs30 = a * f0^b (constants adjustable),
  2. from the estimated thickness and an assumed average shear velocity
     of the sedimentary column (Vs_avg default 300 m/s) when the depth is
     >= 30 m, otherwise mixing Vs_avg with a bedrock velocity (Vs_bedrock
     default 800 m/s) for the remaining depth to 30 m.

All processing stays pure standard library.
"""
import math


# Re-exported from hvsr_standards_data (split out of hvsr_standards) - the
# public API stays importable from here.
from hvsr_standards_data import DEFAULT_STANDARD, DEFAULT_THICKNESS_RELATION, DEFAULT_VS30_A, DEFAULT_VS30_B, DEFAULT_VS_AVG, DEFAULT_VS_BEDROCK, STANDARDS, THICKNESS_RELATIONS, VS30_RELATION_CITATION, estimate_thickness, estimate_vs30_from_thickness, estimate_vs30_powerlaw
# Re-exported from hvsr_standards_eval (split out of hvsr_standards) - the
# public API stays importable from here.
from hvsr_standards_eval import _EVALUATORS, _check, build_standards_report, evaluate_all, evaluate_generic, evaluate_indonesia, evaluate_japan, evaluate_sesame, evaluate_usgs, recommended_params, soil_class, soil_class_sni
