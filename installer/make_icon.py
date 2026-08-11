#!/usr/bin/env python
"""Generate the HVSR Analyzer application icon (installer/HVSR_Analyzer.ico)
and the README preview (installer/HVSR_Analyzer.png).

The design shows the tool's core output - an HVSR (horizontal-to-vertical
spectral ratio) curve with a logarithmic frequency axis, its resonant peak
at the fundamental frequency f0 - inside a deep-navy rounded tile.

Usage:
    python make_icon.py

Requires: Pillow (pip install Pillow).
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
NAVY_TOP = (22, 42, 74, 255)      # #162a4a
NAVY_BOTTOM = (7, 16, 34, 255)    # #071022
GRID = (140, 180, 220, 42)        # subtle log-grid
GRID_MAJOR = (170, 205, 240, 80)  # emphasised grid lines
CURVE = (63, 224, 202, 255)       # #3fe0ca teal H/V curve
CURVE_GLOW = (63, 224, 202, 120)
PEAK = (255, 178, 32, 255)        # #ffb220 amber f0 marker
PEAK_GLOW = (255, 178, 32, 140)
HIGHLIGHT = (255, 255, 255, 34)   # top-left inner bevel

# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
S = 1024                      # supersampled canvas (downscaled with LANCZOS)
R = int(S * 0.155)            # tile corner radius
PAD = int(S * 0.13)           # plot padding inside the tile
X0, Y0 = PAD, PAD
X1, Y1 = S - PAD, S - PAD
PW, PH = X1 - X0, Y1 - Y0

FMIN, FMAX = 0.3, 18.0        # log-frequency axis (Hz)
F0 = 1.6                      # resonance frequency of the drawn peak
AMP_TOP = 5.0                 # y axis (H/V ratio)


def f_to_x(f):
    """Map a frequency (Hz) to canvas x, using a log axis."""
    t = (math.log(f) - math.log(FMIN)) / (math.log(FMAX) - math.log(FMIN))
    return X0 + t * PW


def amp_to_y(a):
    return Y1 - (a / AMP_TOP) * PH


def hvsr_curve(f):
    """A stylised HVSR curve: broad resonance bump plus mild background.

    Returns the H/V amplitude at frequency f (Hz).
    """
    # Lorentzian resonance around f0
    r = f / F0
    lorentz = 1.0 / (1.0 + ((r - 1.0 / r) / 0.42) ** 2)
    # gentle low-frequency rise + high-frequency decay
    back = 0.55 + 0.35 * math.exp(-f / 2.2)
    return back + 3.4 * lorentz


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # --- rounded tile with vertical gradient -------------------------------
    for y in range(S):
        t = y / (S - 1)
        c = tuple(
            int(NAVY_TOP[i] + (NAVY_BOTTOM[i] - NAVY_TOP[i]) * t) for i in range(3)
        ) + (255,)
        d.line([(0, y), (S, y)], fill=c)

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=R, fill=255)
    img.putalpha(mask)

    # soft radial glow behind the curve
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [S * 0.18, S * 0.10, S * 0.82, S * 0.62], fill=(58, 168, 190, 95)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.14))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    # --- logarithmic frequency grid ----------------------------------------
    for i in range(1, 6):
        x = f_to_x(FMIN * (FMAX / FMIN) ** (i / 5.0))
        d.line([(x, Y0), (x, Y1)], fill=GRID, width=3)
    # emphasised lines at decades
    for dec in (0.5, 1.0, 2.0, 5.0, 10.0):
        if FMIN < dec < FMAX:
            x = f_to_x(dec)
            d.line([(x, Y0), (x, Y1)], fill=GRID_MAJOR, width=4)
    # horizontal amplitude lines
    for a in (1.0, 2.0, 3.0, 4.0):
        y = amp_to_y(a)
        d.line([(X0, y), (X1, y)], fill=GRID, width=3)

    # --- plot frame ---------------------------------------------------------
    d.rectangle([X0, Y0, X1, Y1], outline=(150, 190, 225, 110), width=5)

    # --- H/V curve with glow ------------------------------------------------
    pts = []
    n = 480
    for k in range(n + 1):
        f = FMIN * (FMAX / FMIN) ** (k / n)
        pts.append((f_to_x(f), amp_to_y(hvsr_curve(f))))

    for width, color in ((22, CURVE_GLOW), (12, CURVE_GLOW), (7, CURVE)):
        d.line(pts, fill=color, width=width, joint="curve")

    # --- f0 peak marker ------------------------------------------------------
    px, py = f_to_x(F0), amp_to_y(hvsr_curve(F0))
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        [px - S * 0.05, py - S * 0.05, px + S * 0.05, py + S * 0.05],
        fill=PEAK_GLOW,
    )
    halo = halo.filter(ImageFilter.GaussianBlur(S * 0.02))
    img = Image.alpha_composite(img, halo)
    d = ImageDraw.Draw(img)

    # dashed vertical guide through the peak
    dash = int(S * 0.012)
    yy = Y0
    while yy < py - dash:
        d.line([(px, yy), (px, min(yy + dash, py - dash))], fill=PEAK_GLOW, width=4)
        yy += dash * 2

    # peak dot with a white core
    r_dot = int(S * 0.034)
    d.ellipse([px - r_dot, py - r_dot, px + r_dot, py + r_dot], fill=PEAK)
    d.ellipse(
        [px - r_dot * 0.42, py - r_dot * 0.42, px + r_dot * 0.42, py + r_dot * 0.42],
        fill=(255, 242, 210, 255),
    )

    # --- inner bevel / depth --------------------------------------------------
    bevel = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(bevel).rounded_rectangle(
        [1, 1, S - 2, S - 2], radius=R - 1, outline=HIGHLIGHT, width=10
    )
    img = Image.alpha_composite(img, bevel)

    # subtle bottom vignette
    vig = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(vig).rounded_rectangle(
        [0, int(S * 0.62), S, S], radius=R, fill=(0, 0, 0, 60)
    )
    vig = vig.filter(ImageFilter.GaussianBlur(S * 0.10))
    img = Image.alpha_composite(img, vig)

    # --- downscale and save ---------------------------------------------------
    here = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(here, "HVSR_Analyzer.png")
    ico_path = os.path.join(here, "HVSR_Analyzer.ico")

    final = img.resize((256, 256), Image.LANCZOS)
    final.save(png_path)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    final.save(
        ico_path,
        format="ICO",
        sizes=[(sz, sz) for sz in sizes],
    )
    print("wrote", png_path)
    print("wrote", ico_path, "sizes:", sorted(Image.open(ico_path).ico.sizes()))


if __name__ == "__main__":
    main()
