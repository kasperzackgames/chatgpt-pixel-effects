"""Clean an animated pixel-art GIF from ChatGPT into a game-ready sprite sheet.

usage:
  python scripts/clean_gif.py IN.gif --name NAME [options]

The example from the README (the shipped example GIF):
  python scripts/clean_gif.py example/explosion.gif --name explosion --mode adaptive --cell 2.6 --impact 1
         --scale 1 --neutral-greys --grey-chroma 0.05 --colors 20 --out-dir out

Options:
  --mode snap|adaptive   snap (default) = snap to the GIF's own pixel grid (when its blocks really are all
                         the same size); adaptive = content-adaptive downscale by --cell (most ChatGPT GIFs:
                         "HD pixel art" without one clean grid)
  --cell N               snap: the grid cell size in GIF pixels (0 = detect it); adaptive: GIF size divided
                         by the sprite size you want (301 px GIF / 116 px sprite = 2.6)
  --colors 16            palette size (k-means); --max-extra 6 accent colours may be added on top
  --scale 2              whole-number enlargement for a second sheet (1 = only the 1x sheet)
  --frames a-b           keep only GIF frames a to b (default all)
  --impact -1            index of the white flash frame (after --frames); sets the frame tags
                         anticipation / impact / fireball / smoke that the Godot scene uses
  --neutral-greys        pull the key-colour tint out of grey palette colours (smoke);
  --grey-chroma 0.09     ... for greys below this OKLab chroma (0.05 = slight tints only)
  --key magenta|green    the GIF's flat background colour (green for violet or purple effects)
  --anchor bottom|left   bottom = ground contact at the bottom centre (blasts, pillars, strikes);
                         left = origin at the left edge (beams; skips the jitter fix and the ground row)
  --no-fix               skip the frame-to-frame jitter fix
  --out-dir out          outputs go to OUT_DIR/NAME/
  --review-dir DIR       where the contact sheet goes (default: OUT_DIR/NAME/)

Steps (all numbers go into NAME_metrics.json):
 1. split the GIF into RGB frames (one static camera, one canvas);
 2. key the magenta (or green) in every frame, with edge despill; pure key colour inside the smoke
    becomes a hole, as the model drew it;
 3. find ONE pixel grid for all frames: the grid profiles of every frame are summed, the cell size
    is detected on the sum (or forced with --cell) and the grid lines are placed once, so the snap
    itself cannot make frames jump (adaptive mode: one fixed size for all frames instead);
 4. snap every frame on that grid (inner-cell majority, lone ember pixels kept);
 5. one shared OKLab palette for all frames (+ accent guard); --neutral-greys pulls the key-colour
    tint out of grey palette entries (ChatGPT's smoke greys come out purple-tinted on magenta);
 6. anchor = bottom centre (the prompt made the bottom edge the ground); measure per frame the
    centroid x and the base row; jitter fix: x is pinned while the fire grows (up to the biggest
    frame) and smoothed afterwards (3-frame mean), so the drift stays but the wobble goes;
 7. ground row repeats the row above (no key fringe or holes where the blast meets the ground);
    rare colours on edge pixels take their neighbours' colour (key-spill fringe);
 8. export: NAME_sheet.png (one row of frames) at 1x and at --scale, an Aseprite-style JSON
    (frame rects, durations, meta.anchor = ground contact, frameTags, palette), NAME_palette.hex,
    frames/, a review GIF at x6, a contact sheet, and a review mp4 at x6 if ffmpeg is on PATH.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

import pixelcore as px

REVIEW_BG = (18, 22, 38)


def base_row(alpha):
    rows = alpha.sum(1)
    if rows.max() == 0:
        return None
    idx = np.nonzero(rows >= min(rows.max(), max(2, 0.15 * rows.max())))[0]  # thin bolts: rows of 1 px
    return int(idx.max())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gif")
    ap.add_argument("--name", required=True)
    ap.add_argument("--cell", type=float, default=0.0)
    ap.add_argument("--mode", default="snap", choices=["snap", "adaptive"],
                    help="snap = grid snap (real grid); adaptive = content-adaptive downscale at --cell (no real grid)")
    ap.add_argument("--colors", type=int, default=16)
    ap.add_argument("--max-extra", type=int, default=6)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--frames", default="", help="a-b range of GIF frames to keep (default all)")
    ap.add_argument("--impact", type=int, default=-1, help="flash frame index (after --frames), for the frame tags")
    ap.add_argument("--neutral-greys", action="store_true")
    ap.add_argument("--grey-chroma", type=float, default=0.09, help="OKLab chroma below which a key-tinted palette colour counts as a grey")
    ap.add_argument("--no-fix", action="store_true")
    ap.add_argument("--key", default="magenta", choices=["magenta", "green"],
                    help="flat background colour of the GIF (green for violet/purple effects such as lightning)")
    ap.add_argument("--anchor", default="bottom", choices=["bottom", "left"],
                    help="bottom = ground contact at bottom centre (blasts, pillars, strikes); left = origin at the "
                         "left edge, measured height (beams); left skips the x jitter fix and the ground row")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--review-dir", default="", help="folder for the contact sheet (default: the output folder)")
    a = ap.parse_args()
    out_dir = os.path.abspath(os.path.join(a.out_dir, a.name))
    os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
    review_dir = a.review_dir or out_dir
    os.makedirs(review_dir, exist_ok=True)
    rep = {"name": a.name, "gif": os.path.basename(a.gif)}

    # 1. split
    im = Image.open(a.gif)
    rgbs, durs = [], []
    for f in ImageSequence.Iterator(im):
        durs.append(int(f.info.get("duration", 80)))
        rgbs.append(np.asarray(f.convert("RGB")))
    rep["gif_frames"], rep["gif_size"] = len(rgbs), [rgbs[0].shape[1], rgbs[0].shape[0]]
    rep["gif_durations_ms"] = durs
    rep["colors_per_gif_frame"] = [int(len(np.unique(r.reshape(-1, 3), axis=0))) for r in rgbs]
    lo, hi = 0, len(rgbs) - 1
    if a.frames:
        lo, hi = (int(v) for v in a.frames.split("-"))
    rgbs, durs = rgbs[lo:hi + 1], durs[lo:hi + 1]
    rep["kept_gif_frames"] = [lo, hi]

    # 2. key + despill per frame
    masks = []
    for i, r in enumerate(rgbs):
        m = px.key_mask(r, a.key)
        rgbs[i] = px.despill(r, m, a.key)
        masks.append(m)

    # 3. one grid for all frames
    H0, W0 = rgbs[0].shape[:2]
    pXs, pYs = zip(*[px._profiles(r, m) for r, m in zip(rgbs, masks)])
    pX, pY = np.sum(pXs, axis=0), np.sum(pYs, axis=0)
    if a.cell > 0:
        cell, conf = a.cell, None
    else:
        lags = list(range(3, 13))
        s = px._autocorr(pX, lags) + px._autocorr(pY, lags)
        i = int(np.argmax(s))
        d = 0.0
        if 0 < i < len(s) - 1:
            d = (s[i - 1] - s[i + 1]) / (2 * (s[i - 1] - 2 * s[i] + s[i + 1]) + 1e-9)
        cell, conf = lags[i] + float(np.clip(d, -0.5, 0.5)), float(s[i])
    xs, ys = px._lines(pX, cell, W0), px._lines(pY, cell, H0)
    if xs[0] > cell * 0.5:
        xs = np.concatenate([[0], xs])
    if ys[0] > cell * 0.5:
        ys = np.concatenate([[0], ys])
    if xs[-1] < W0:
        xs = np.concatenate([xs, [W0]])
    if ys[-1] < H0:
        ys = np.concatenate([ys, [H0]])
    W, H = len(xs) - 1, len(ys) - 1
    rep["cell_px"] = round(cell, 2)
    rep["mode"] = a.mode
    rep["grid_score"] = None if conf is None else round(conf, 2)
    rep["native"] = [W, H]

    # 4. snap every frame on the shared grid (pre-palette shared too)
    allsub = np.concatenate([r[m] for r, m in zip(rgbs, masks) if m.any()])
    pre_pal = px.kmeans_palette(allsub, 48)
    natives = []
    inner = 0.6
    if a.mode == "adaptive":  # no real grid ("HD pixel"): content-adaptive downscale to one fixed size
        W, H = int(round(W0 / cell)), int(round(H0 / cell))
        rep["native"] = [W, H]
        for r, m in zip(rgbs, masks):
            d = px.downscale(r, m, (W, H))
            natives.append((px.map_to_palette(np.ascontiguousarray(d[..., :3]), pre_pal), d[..., 3] > 0))
    for r, m in (zip(rgbs, masks) if a.mode != "adaptive" else []):
        pre = px.map_to_palette(r, pre_pal).reshape(-1, 3).astype(np.int64)
        code = ((pre[:, 0] << 16) | (pre[:, 1] << 8) | pre[:, 2]).reshape(r.shape[:2])
        o_rgb = np.zeros((H, W, 3), np.uint8)
        o_a = np.zeros((H, W), bool)
        for j in range(H):
            y0, y1 = ys[j], ys[j + 1]
            my = (y1 - y0) * (1 - inner) / 2
            iy0 = int(round(y0 + my)); iy1 = max(iy0 + 1, int(round(y1 - my)))
            for i in range(W):
                x0, x1 = xs[i], xs[i + 1]
                mx = (x1 - x0) * (1 - inner) / 2
                ix0 = int(round(x0 + mx)); ix1 = max(ix0 + 1, int(round(x1 - mx)))
                mm = m[iy0:iy1, ix0:ix1]
                if mm.size == 0 or mm.mean() < 0.5:
                    continue
                vals, counts = np.unique(code[iy0:iy1, ix0:ix1][mm], return_counts=True)
                v = int(vals[np.argmax(counts)])
                o_rgb[j, i] = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
                o_a[j, i] = True
        natives.append((o_rgb, o_a))
    rep["colors_after_snap"] = int(len(np.unique(np.concatenate([o[al] for o, al in natives if al.any()]), axis=0)))

    # 5. shared palette (+ optional grey de-tint)
    pal, added = px.build_palette([np.concatenate([o[al] for o, al in natives if al.any()])], a.colors, max_extra=a.max_extra)
    detinted = []
    if a.neutral_greys:
        lab = px.rgb_to_oklab(pal)
        for k in range(len(pal)):
            L, A, B = lab[k]
            chroma = float(np.hypot(A, B))
            tinted = (A > 0.0 and B < 0.02) if a.key == "magenta" else (A < 0.0 and B > -0.02)
            if chroma < a.grey_chroma and tinted:  # a grey pulled toward the key colour
                lab[k, 1] *= 0.15
                lab[k, 2] = abs(B) * 0.2 + 0.004       # a hint of warm instead of purple
                detinted.append("#%02x%02x%02x" % tuple(int(v) for v in pal[k]))
        pal = px.oklab_to_rgb(lab)
    rep["palette_kmeans"], rep["palette_accents_added"], rep["greys_detinted"] = a.colors, int(added), detinted
    frames = [px.rgba_from(px.map_to_palette(o, pal), al) for o, al in natives]

    # 6. anchor + jitter (anchor = bottom centre, or the left-edge origin of a beam)
    AX, AY = W // 2, H - 1
    areas = [int((f[..., 3] > 0).sum()) for f in frames]
    big = int(np.argmax(areas))
    if a.anchor == "left":
        a.no_fix = True
        al_big = frames[big][..., 3] > 0
        cols_l = al_big[:, :max(2, W // 10)]
        yy_l = np.nonzero(cols_l)[0]
        AX, AY = 0, int(round(float(yy_l.mean()))) if len(yy_l) else H // 2
    rep["anchor"] = [a.anchor, AX, AY]
    meas = []
    for f in frames:
        al = f[..., 3] > 0
        if al.sum() < 4:
            meas.append(None)
            continue
        yy, xx = np.nonzero(al)
        meas.append((float(xx.mean()) - AX, float(base_row(al)) - AY))
    # one shift for the whole animation centres the fire on the anchor (the camera is static, so
    # frames keep their relation); then per frame: fire frames pinned, later frames smoothed
    fire_x = [m[0] for m in meas[:big + 1] if m is not None]
    g = -int(round(float(np.mean(fire_x)))) if fire_x else 0
    res = [None if m is None else m[0] + g for m in meas]
    shifts = []
    for i, m in enumerate(meas):
        if a.no_fix or m is None:
            shifts.append(0 if a.no_fix else g)
            continue
        if i <= big:
            target = 0.0
        else:  # keep the drift, remove the wobble: 3-frame mean
            win = [v for v in res[max(0, i - 1):i + 2] if v is not None]
            target = float(np.mean(win))
        shifts.append(g + int(round(target - res[i])))
    rep["global_shift_x"] = g
    after = [None if m is None else (m[0] + s, m[1]) for m, s in zip(meas, shifts)]

    def stats(ms):
        steps, prev = [], None
        for m in ms:
            if m is not None and prev is not None:
                steps.append(abs(m[0] - prev[0]))
            prev = m if m is not None else prev
        return {"mean_x_step_px": round(float(np.mean(steps)), 2) if steps else 0.0,
                "max_x_step_px": round(float(np.max(steps)), 2) if steps else 0.0,
                "max_abs_x_off_px": round(float(max(abs(m[0]) for m in ms if m)), 2),
                "max_abs_base_off_px": round(float(max(abs(m[1]) for m in ms if m)), 2)}
    rep["biggest_frame"] = big
    rep["jitter_before"], rep["jitter_after"] = stats(meas), stats(after)
    outs = []
    for f, s in zip(frames, shifts):
        o = np.zeros_like(f)
        if s >= 0:
            o[:, s:] = f[:, :W - s]
        else:
            o[:, :W + s] = f[:, -s:]
        outs.append(o)

    # 7. ground row + fringe
    for o in (outs if a.anchor == "bottom" else []):
        above = o[AY - 1].copy()
        o[AY] = np.where(above[:, 3:4] > 0, above, 0)
    allc = np.concatenate([o[o[..., 3] > 0][:, :3] for o in outs if (o[..., 3] > 0).any()])
    cu, cn = np.unique(allc, axis=0, return_counts=True)
    rare = {tuple(int(v) for v in c) for c, n_ in zip(cu, cn) if n_ < 0.004 * len(allc)}
    fixed = 0
    for o in outs:
        al = o[..., 3] > 0
        pad = np.pad(al, 1)
        edge = al & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
        for y, x in zip(*np.nonzero(edge)):
            if tuple(int(v) for v in o[y, x, :3]) not in rare:
                continue
            votes = {}
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if (dx or dy) and 0 <= yy < H and 0 <= xx < W and o[yy, xx, 3]:
                        k_ = tuple(int(v) for v in o[yy, xx, :3])
                        if k_ not in rare:
                            votes[k_] = votes.get(k_, 0) + 1
            if votes:
                o[y, x, :3] = max(votes, key=votes.get)
                fixed += 1
    rep["fringe_pixels_fixed"], rep["rare_colors"] = fixed, ["#%02x%02x%02x" % c for c in sorted(rare)]
    allpx = np.concatenate([o[o[..., 3] > 0][:, :3] for o in outs if (o[..., 3] > 0).any()])
    used = np.unique(allpx, axis=0)
    rep["colors_final"] = int(len(used))
    rep["per_frame"] = []
    for i, (o, m0, m1, s) in enumerate(zip(outs, meas, after, shifts)):
        al = o[..., 3] > 0
        yy, xx = np.nonzero(al)
        rep["per_frame"].append({"frame": i, "gif_frame": lo + i, "opaque_px": int(al.sum()),
                                 "bbox": [int(xx.max() - xx.min() + 1), int(yy.max() - yy.min() + 1)] if len(xx) else [0, 0],
                                 "colors": px.count_colors(o), "stray_pct": px.stray_pct(o),
                                 "x_base_before": None if m0 is None else [round(m0[0], 2), round(m0[1], 2)],
                                 "x_after": None if m1 is None else round(m1[0], 2), "shift_x": s})

    # 8. export (1x and xS)
    pal_hex = ["#%02x%02x%02x" % tuple(int(v) for v in c) for c in used[np.argsort(px.rgb_to_oklab(used)[:, 0])[::-1]]]
    tags = []
    if a.impact >= 0:
        tags = [{"name": "anticipation", "from": 0, "to": max(0, a.impact - 1), "direction": "forward"},
                {"name": "impact", "from": a.impact, "to": a.impact, "direction": "forward"},
                {"name": "fireball", "from": a.impact + 1, "to": big, "direction": "forward"},
                {"name": "smoke", "from": big + 1, "to": len(outs) - 1, "direction": "forward"}]
    for S in sorted({1, a.scale}):
        FW, FH = W * S, H * S
        sheet = np.zeros((FH, FW * len(outs), 4), np.uint8)
        for i, o in enumerate(outs):
            sheet[:, i * FW:(i + 1) * FW] = np.repeat(np.repeat(o, S, 0), S, 1)
            if S == 1:
                Image.fromarray(o, "RGBA").save(os.path.join(out_dir, "frames", f"f{i:02d}.png"))
        nm = f"{a.name}_sheet" + ("" if S == 1 else f"_x{S}")
        Image.fromarray(sheet, "RGBA").save(os.path.join(out_dir, nm + ".png"))
        meta = {"frames": [{"filename": f"{a.name}_{i:02d}", "frame": {"x": i * FW, "y": 0, "w": FW, "h": FH},
                            "rotated": False, "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": FW, "h": FH},
                            "sourceSize": {"w": FW, "h": FH}, "duration": durs[i]} for i in range(len(outs))],
                "meta": {"app": "clean_gif.py (ChatGPT GIF to sprite sheet)", "image": nm + ".png", "format": "RGBA8888",
                         "size": {"w": FW * len(outs), "h": FH}, "scale": "1", "art_pixel": S, "frameTags": tags,
                         "anchor": {"x": AX * S + S // 2, "y": AY * S + S - 1,
                                    "kind": a.anchor,
                                    "note": ("pixel where the effect touches the ground; put the sprite origin here"
                                             if a.anchor == "bottom" else
                                             "beam origin at the left edge; put the caster's hand here")},
                         "palette": pal_hex, "loop": False}}
        json.dump(meta, open(os.path.join(out_dir, nm + ".json"), "w", encoding="utf-8"), indent=1)
    px.save_hex(used, os.path.join(out_dir, f"{a.name}_palette.hex"))
    z = 6
    on_dark = []
    for o in outs:
        bg = Image.new("RGBA", (W * z, H * z), REVIEW_BG + (255,))
        bg.alpha_composite(Image.fromarray(o, "RGBA").resize((W * z, H * z), Image.Resampling.NEAREST))
        on_dark.append(bg.convert("RGB"))
    on_dark[0].save(os.path.join(out_dir, f"{a.name}_x6.gif"), save_all=True, append_images=on_dark[1:], duration=durs, loop=0)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:  # review mp4: the animation 3 times at 60 fps on the dark backdrop
        tmp = os.path.join(out_dir, "_mp4")
        os.makedirs(tmp, exist_ok=True)
        n = 0
        for _ in range(3):
            for o, d in zip(on_dark, durs):
                for _r in range(max(1, round(d * 60 / 1000))):
                    o.save(os.path.join(tmp, f"{n:05d}.png")); n += 1
            for _r in range(30):
                Image.new("RGB", on_dark[0].size, REVIEW_BG).save(os.path.join(tmp, f"{n:05d}.png")); n += 1
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", "60", "-i", os.path.join(tmp, "%05d.png"),
                        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12",
                        os.path.join(out_dir, f"{a.name}_x6.mp4")], check=True, stdin=subprocess.DEVNULL)
        for fn in os.listdir(tmp):
            os.remove(os.path.join(tmp, fn))
        os.rmdir(tmp)
    else:
        print("note: ffmpeg is not on PATH, so the review mp4 was skipped (the x6 GIF has the same frames)", file=sys.stderr)
    cz, cols = 4, 8
    rows = (len(outs) + cols - 1) // cols
    img = Image.new("RGB", (cols * (W * cz + 8) + 8, rows * (H * cz + 24) + 8), (40, 40, 48))
    dr = ImageDraw.Draw(img)
    for i, o in enumerate(outs):
        r_, c_ = divmod(i, cols)
        x0, y0 = 8 + c_ * (W * cz + 8), 8 + r_ * (H * cz + 24) + 16
        img.paste(on_dark[i].resize((W * cz, H * cz), Image.Resampling.NEAREST), (x0, y0))
        dr.text((x0, y0 - 14), f"{i} (gif {lo + i})  {durs[i]}ms", fill=(220, 220, 220))
    img.save(os.path.join(review_dir, f"{a.name}_contact.png"))
    json.dump(rep, open(os.path.join(out_dir, f"{a.name}_metrics.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: rep[k] for k in ("name", "cell_px", "grid_score", "native", "colors_after_snap", "colors_final",
                                          "greys_detinted", "biggest_frame", "jitter_before", "jitter_after",
                                          "fringe_pixels_fixed")}))
    print(json.dumps([[p["frame"], p["bbox"], p["stray_pct"], p["x_base_before"], p["shift_x"]] for p in rep["per_frame"]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
