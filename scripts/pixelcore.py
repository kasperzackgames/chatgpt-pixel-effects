"""Shared image routines for clean_gif.py and make_lit.py.

- keying a flat magenta or green background, with despill only at the silhouette edge;
- OKLab colour maths, k-means palettes (small saturated accents keep their own colour) and an
  accent guard for shared palettes;
- pixel-grid profiles, autocorrelation and grid-line placement for image-model "pixel art";
- content-adaptive downscale (the `unfake` package) for pictures without a clean pixel grid.

Needs numpy, Pillow, scipy, scikit-learn and unfake (see requirements.txt).
"""
from __future__ import annotations

import contextlib
import io
import logging

import numpy as np
from PIL import Image

KEYS = {"magenta": (255, 0, 255), "green": (0, 255, 0)}
logging.getLogger("unfake.py").setLevel(logging.WARNING)  # unfake logs one INFO line per downscale


# ------------------------------------------------------------------ loading and keying
def load(path: str) -> tuple[np.ndarray, np.ndarray | None]:
    """RGB array and an alpha mask if the file has real transparency (else None)."""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = np.asarray(im.convert("RGBA"))
        a = rgba[..., 3]
        if (a < 255).any():
            return np.ascontiguousarray(rgba[..., :3]), a > 127
        return np.ascontiguousarray(rgba[..., :3]), None
    return np.asarray(im.convert("RGB")), None


def key_mask(rgb: np.ndarray, key) -> np.ndarray:
    """True where the subject is (key = "magenta", "green", None or an (r, g, b) flat colour)."""
    if key is None:
        return np.ones(rgb.shape[:2], bool)
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    if key == "magenta":
        return (np.minimum(r, b) - g) < 60
    if key == "green":
        return (g - np.maximum(r, b)) < 60
    lab = rgb_to_oklab(rgb.reshape(-1, 3)).reshape(rgb.shape)
    klab = rgb_to_oklab(np.array([key], np.uint8))[0]
    return np.linalg.norm(lab - klab, axis=-1) > 0.06


def despill(rgb: np.ndarray, mask: np.ndarray, key) -> np.ndarray:
    """Remove key colour bleeding into anti-aliased edges, only in the 3-px band of the subject
    next to the background, so interior purples or greens stay intact."""
    if key not in ("magenta", "green"):
        return rgb
    from scipy.ndimage import binary_dilation
    band = binary_dilation(~mask, iterations=3) & mask
    out = rgb.astype(np.int16)
    r, g, b = out[..., 0], out[..., 1], out[..., 2]
    if key == "magenta":
        spill = np.clip(np.minimum(r, b) - g, 0, None)
        out[..., 0] = np.where(band, r - spill, r)
        out[..., 2] = np.where(band, b - spill, b)
    else:
        spill = np.clip(g - np.maximum(r, b), 0, None)
        out[..., 1] = np.where(band, g - spill, g)
    return np.clip(out, 0, 255).astype(np.uint8)


def bleed(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Fill the background with the nearest subject colour so resamplers never mix in the key."""
    if mask.all():
        return rgb
    from scipy.ndimage import distance_transform_edt
    _, (iy, ix) = distance_transform_edt(~mask, return_indices=True)
    return rgb[iy, ix]


# ------------------------------------------------------------------ OKLab and palettes
def _s2l(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _l2s(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055) * 255.0


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])
_M2I = np.array([[1.0, 0.3963377774, 0.2158037573], [1.0, -0.1055613458, -0.0638541728], [1.0, -0.0894841775, -1.2914855480]])
_M1I = np.array([[4.0767416621, -3.3077115913, 0.2309699292], [-1.2684380046, 2.6097574011, -0.3413193965], [-0.0041960863, -0.7034186147, 1.7076147010]])
_LW = np.array([1.6, 1.0, 1.0])  # lightness weighted up so shading ramps survive quantisation


def rgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    return np.cbrt(_s2l(rgb.astype(np.float64)) @ _M1.T) @ _M2.T


def oklab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(np.round(_l2s(((lab @ _M2I.T) ** 3) @ _M1I.T)), 0, 255).astype(np.uint8)


def kmeans_palette(pixels: np.ndarray, k: int, seed: int = 0) -> np.ndarray:
    """k colours chosen by k-means in OKLab. Small saturated accents keep their own colour,
    unlike median-cut, which spends colours on large areas."""
    from sklearn.cluster import KMeans
    lab = rgb_to_oklab(pixels.reshape(-1, 3)) * _LW
    if len(lab) > 60000:
        lab = lab[np.random.default_rng(seed).choice(len(lab), 60000, replace=False)]
    k = max(1, min(k, len(np.unique(lab.round(4), axis=0))))
    km = KMeans(n_clusters=k, n_init=4, random_state=seed).fit(lab)
    return oklab_to_rgb(km.cluster_centers_ / _LW)


def map_to_palette(rgb: np.ndarray, palette: np.ndarray, lightness_weight: float = 1.6) -> np.ndarray:
    """Nearest palette colour in OKLab, lightness weighted so shading ramps survive."""
    shp = rgb.shape
    w = np.array([lightness_weight, 1.0, 1.0])
    lab = rgb_to_oklab(rgb.reshape(-1, 3)) * w
    plab = rgb_to_oklab(palette) * w
    idx = np.empty(len(lab), np.int64)
    for i in range(0, len(lab), 200000):
        idx[i:i + 200000] = ((lab[i:i + 200000, None, :] - plab[None]) ** 2).sum(-1).argmin(1)
    return palette[idx].reshape(shp)


def build_palette(pixel_sets: list, k: int, base: np.ndarray | None = None,
                  accent_de: float = 0.045, max_extra: int = 16, per_set: int = 12000, seed: int = 0):
    """One shared palette for several pixel sets. Returns (palette, added_count).
    - Every set gets equal weight.
    - Accent guard: a colour a set really uses (>= 3 px) that sits farther than accent_de (OKLab)
      from every palette colour is added, worst first, up to max_extra.
    - base: extend an existing palette instead of starting over."""
    rs = np.random.default_rng(seed)
    sample = [q[rs.choice(len(q), per_set, replace=len(q) < per_set)] for q in pixel_sets if len(q)]
    pal = kmeans_palette(np.concatenate(sample), k) if base is None else base.copy()
    added = 0
    uniq = []
    for q in pixel_sets:
        cols, counts = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
        cols = cols[counts >= 3]
        uniq.append((cols, rgb_to_oklab(cols) * _LW if len(cols) else None))
    for _ in range(max_extra):
        plab = rgb_to_oklab(pal) * _LW
        worst, worst_d = None, accent_de
        for cols, lab in uniq:
            if lab is None:
                continue
            d = np.sqrt(((lab[:, None, :] - plab[None]) ** 2).sum(-1)).min(1)
            i = int(d.argmax())
            if d[i] > worst_d:
                worst, worst_d = cols[i], d[i]
        if worst is None:
            break
        pal = np.vstack([pal, worst[None].astype(np.uint8)])
        added += 1
    return pal, added


def save_hex(palette: np.ndarray, path: str) -> None:
    """Palette as a .hex file (one rrggbb per line, dark to light)."""
    lab = rgb_to_oklab(palette)
    order = np.argsort(lab[:, 0])
    with open(path, "w", encoding="utf-8") as f:
        for c in palette[order]:
            f.write("%02x%02x%02x\n" % tuple(int(v) for v in c))


# ------------------------------------------------------------------ RGBA helpers and measures
def rgba_from(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    out = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    out[..., :3] = rgb
    out[..., 3] = np.where(alpha, 255, 0)
    out[out[..., 3] == 0] = 0
    return out


def quantize(rgba: np.ndarray, k: int) -> np.ndarray:
    """Reduce the opaque pixels to a k-colour k-means palette."""
    a = rgba[..., 3] > 0
    if not a.any():
        return rgba
    return rgba_from(map_to_palette(rgba[..., :3], kmeans_palette(rgba[..., :3][a], k)), a)


def count_colors(rgba: np.ndarray) -> int:
    px = rgba.reshape(-1, 4)
    px = px[px[:, 3] > 0][:, :3]
    return int(len(np.unique(px, axis=0))) if len(px) else 0


def stray_pct(rgba: np.ndarray) -> float:
    """Share of opaque pixels whose colour matches none of their 8 neighbours (noise measure)."""
    a = rgba.astype(np.int64)
    code = (a[..., 0] << 24) | (a[..., 1] << 16) | (a[..., 2] << 8) | a[..., 3]
    op = a[..., 3] > 0
    p = np.pad(code, 1, constant_values=-1)
    h, w = code.shape
    same = np.zeros((h, w), bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                same |= p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] == code
    return round(100.0 * float((op & ~same).sum()) / max(1, int(op.sum())), 1)


# ------------------------------------------------------------------ pixel-grid detection
def _profiles(rgb: np.ndarray, mask: np.ndarray):
    lab = rgb_to_oklab(rgb.reshape(-1, 3)).reshape(rgb.shape).astype(np.float32)
    gx = np.abs(np.diff(lab, axis=1)).sum(-1)
    gy = np.abs(np.diff(lab, axis=0)).sum(-1)
    gx = np.where(mask[:, 1:] | mask[:, :-1], gx + 0.3 * (mask[:, 1:] != mask[:, :-1]), 0)
    gy = np.where(mask[1:, :] | mask[:-1, :], gy + 0.3 * (mask[1:, :] != mask[:-1, :]), 0)
    return np.concatenate([[0], gx.sum(0)]), np.concatenate([[0], gy.sum(1)])


def _autocorr(p: np.ndarray, lags) -> np.ndarray:
    q = p - np.convolve(p, np.ones(31) / 31, mode="same")
    q = q / (np.sqrt((q * q).sum()) + 1e-9)
    return np.array([(q[:-l] * q[l:]).sum() if l < len(q) else 0.0 for l in lags])


def _lines(profile: np.ndarray, cell: float, n: int, refine: float = 0.3) -> np.ndarray:
    smooth = np.convolve(profile, [0.25, 0.5, 0.25], mode="same")
    best_phase, best = 0, -1.0
    for ph in range(int(np.ceil(cell))):
        pos = np.round(np.arange(ph, n, cell)).astype(int)
        sc = smooth[pos[pos < n]].sum()
        if sc > best:
            best, best_phase = sc, ph
    r = max(1, int(round(cell * refine)))

    def snap(x: float) -> float:
        a, b = int(max(0, round(x) - r)), int(min(n - 1, round(x) + r))
        if b <= a or smooth[a:b + 1].max() <= 0:
            return x
        return float(a + int(np.argmax(smooth[a:b + 1])))

    x = snap(best_phase + cell * round((n / 2 - best_phase) / cell))
    lines = [x]
    while x + cell < n + cell / 2:
        x = snap(x + cell)
        if x <= lines[-1] + cell * 0.5:
            x = lines[-1] + cell
        lines.append(x)
    x = lines[0]
    while x - cell > -cell / 2:
        x = snap(x - cell)
        if x >= lines[0] - cell * 0.5:
            x = lines[0] - cell
        lines.insert(0, x)
    return np.unique(np.round(np.clip(np.array(lines), 0, n)).astype(int))


# ------------------------------------------------------------------ downscale
def downscale(rgb: np.ndarray, mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """A picture without a clean pixel grid -> RGBA at an exact size (no palette yet), with the
    content-adaptive downscale of the `unfake` package (MIT)."""
    from unfake import content_adaptive_downscale
    src = bleed(rgb, mask)
    with contextlib.redirect_stdout(io.StringIO()):
        out = np.asarray(content_adaptive_downscale(src, size[0], size[1]))[..., :3]
    out = np.asarray(Image.fromarray(np.ascontiguousarray(out).astype(np.uint8)).resize(size, Image.Resampling.NEAREST))
    a = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)) >= 128
    return rgba_from(out, a)
