"""Make the 'lit' background for the scene's blast light: a copy of the background with the fire's
light painted on the surfaces it reaches. The Godot scene blends toward it by the fire's intensity.

usage:
  python scripts/make_lit.py BG.png RELIT.png OUT_LIT.png [options]          from an AI-relit picture
  python scripts/make_lit.py BG.png - OUT_LIT.png --synthetic --mask MASK.png  fallback without a picture

BG.png is the scene background (320x180 in the example). RELIT.png is the relit picture from any image
AI, at any size, as long as it shows exactly the same framing as BG (same aspect ratio, nothing cropped,
padded or moved). It is brought to BG's size with a content-adaptive downscale and a k-means palette.
Options:
  --gain 0.02        a relit pixel counts as lit only if it is WARMER than BG by more than this
                     (OKLab: b gain + 0.5 x a gain). Lower = more pixels lit; higher = only strong light.
  --max-darken 0.02  ... and only if it is not DARKER than BG by more than this (OKLab L): light
                     never darkens a surface. This rejects grey-brown smears the picture may add
                     to the mist. 1 = off.
  --smear-dl 0.03 --smear-chroma 0.06
                     ... and not if it is hardly brighter (L gain below --smear-dl) AND nearly grey
                     (OKLab chroma below --smear-chroma): that is haze, not fire light.
  --min-group 6      warm groups smaller than this many pixels (8-connected) are dropped: stars the
                     picture tinted yellow are not light on a surface.
  --colors 40        colours for the downscale of the picture.
  --mask MASK.png    optional, BG-sized, white = may be lit (rock, ground), black = never (sky).
  --synthetic        no picture (RELIT = "-"): light every pixel inside --mask with a warm tint
                     (--strength 0.55) instead. Needs --mask.
Everywhere a pixel is not lit, OUT is bit-identical to BG, so blending between them can never show
a band or lens there. Prints one line of numbers: lit share, alignment (best_shift must be [0, 0]),
mean difference outside the lit part, and how many pixels each flaw rule rejected.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import label

import pixelcore as px


def relit_at_size(path, size, colors):
    """The relit picture brought to the background's size: content-adaptive downscale, then a
    k-means palette of `colors` colours. Returns RGB."""
    rgb, alpha = px.load(path)
    mask = alpha if alpha is not None else np.ones(rgb.shape[:2], bool)
    out = px.quantize(px.downscale(np.ascontiguousarray(rgb), mask, size), colors)
    return np.ascontiguousarray(out[..., :3])


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("bg")
ap.add_argument("raw")
ap.add_argument("out")
ap.add_argument("--gain", type=float, default=0.02)
ap.add_argument("--max-darken", type=float, default=0.02)
ap.add_argument("--min-group", type=int, default=6)
ap.add_argument("--smear-dl", type=float, default=0.03)
ap.add_argument("--smear-chroma", type=float, default=0.06)
ap.add_argument("--colors", type=int, default=40)
ap.add_argument("--mask", default="")
ap.add_argument("--synthetic", action="store_true")
ap.add_argument("--strength", type=float, default=0.55)
a = ap.parse_args()

orig = np.asarray(Image.open(a.bg).convert("RGB"))
H, W = orig.shape[:2]
lo = px.rgb_to_oklab(orig.reshape(-1, 3)).reshape(H, W, 3)
mask = np.ones((H, W), bool)
if a.mask:
    m = Image.open(a.mask).convert("L")
    if m.size != (W, H):
        sys.exit(f"mask must be {W}x{H}, is {m.size[0]}x{m.size[1]}")
    mask = np.asarray(m) >= 128
rep = {"out": a.out}

if a.synthetic:
    if not a.mask:
        sys.exit("--synthetic needs --mask")
    lum = (orig.astype(float) / 255.0) @ np.array([0.299, 0.587, 0.114])
    warm_c = np.array([1.0, 0.55, 0.22])
    target = warm_c[None, None, :] * (lum[..., None] * 2.4 + 0.12)
    lit = np.clip((orig / 255.0) * (1 - a.strength) + target * a.strength, 0, 1)
    lit = np.round(lit * 255).astype(np.uint8)
    lit_px = mask
    rep.update(mode="synthetic", lit_pixels_pct=float(round(100 * lit_px.mean(), 1)))
else:
    rw, rh = Image.open(a.raw).size
    if abs((rw / rh) / (W / H) - 1) > 0.02:
        print(f"warning: the relit picture is {rw}x{rh}, a different shape from the background ({W}x{H}); "
              "it will not line up (see best_shift). Crop or pad it back to the same framing, or use --mask.",
              file=sys.stderr)
    lit = relit_at_size(a.raw, (W, H), a.colors)
    rep["raw_size"] = [rw, rh]
    ll = px.rgb_to_oklab(lit.reshape(-1, 3)).reshape(H, W, 3)
    gain = (ll[..., 2] - lo[..., 2]) + 0.5 * (ll[..., 1] - lo[..., 1])
    dL = ll[..., 0] - lo[..., 0]
    warm = (gain > a.gain) & mask
    darker = warm & (dL < -a.max_darken)
    # smear: warm but hardly brighter and nearly grey (grey-brown haze the picture may put in the
    # mist); fire light makes a surface clearly brighter or clearly orange
    ch_lit = np.hypot(ll[..., 1], ll[..., 2])
    smear = warm & ~darker & (dL < a.smear_dl) & (ch_lit < a.smear_chroma)
    lit_px = warm & ~darker & ~smear
    lab, n = label(lit_px, structure=np.ones((3, 3), bool))
    sizes = np.bincount(lab.ravel())
    small = sizes < a.min_group
    small[0] = False
    specks = int(small[lab].sum())
    lit_px &= ~small[lab]
    # flaw checks inside the lit part: greyed pixels (chroma down by > 0.02 without getting brighter)
    ch_o, ch_l = np.hypot(lo[..., 1], lo[..., 2]), np.hypot(ll[..., 1], ll[..., 2])
    dull = lit_px & (ch_l < ch_o - 0.02) & (dL < 0.03)
    ys, xs = np.nonzero(dull)
    best = None
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            sh = np.roll(np.roll(ll, dy, 0), dx, 1)
            d = float(np.linalg.norm(sh - lo, axis=-1)[~warm][W * 3:].mean())
            if best is None or d < best[0]:
                best = (d, dx, dy)
    rep.update(mode="painting", lit_pixels_pct=float(round(100 * lit_px.mean(), 1)),
               best_shift=[best[1], best[2]], mean_diff_outside_lit=round(best[0], 4),
               darker_rejected_px=int(darker.sum()), smear_rejected_px=int(smear.sum()), specks_dropped_px=specks,
               lit_mean_dL=round(float(dL[lit_px].mean()), 3) if lit_px.any() else None,
               dull_lit_px=int(dull.sum()),
               dull_box=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None)
out = np.where(lit_px[..., None], lit, orig).astype(np.uint8)
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
Image.fromarray(out).save(a.out)
rep["identical_to_bg_pct"] = float(round(100 * (out == orig).all(-1).mean(), 1))
print(rep)
