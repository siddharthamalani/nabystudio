#!/usr/bin/env python3
"""Cut a character out of a plain cream/flat background.

Flood-fills from the image border so whites INSIDE the character (eyes, shirts)
are kept. Soft 1-2 px edge. Crops to the character with a small margin.

  python3 engine/cutout.py in.png out.png [--tol 38]
  python3 engine/cutout.py --grid 3x2 sheet.png outdir/name   # split a pose sheet
"""
import os, subprocess, sys, argparse
import numpy as np, cv2
from PIL import Image

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_PY = os.path.join(STUDIO, "tools", "cutout_env", "bin", "python")


def ai_alpha(path):
    """Alpha mask from the AI background remover (rembg, tools/cutout_env), full image size, cached in build_cache/ai.
    Returns None if rembg isn't installed or fails; callers then fall back to the colour-based cutter."""
    p = path if os.path.isabs(path) else os.path.join(STUDIO, path)
    if not os.path.exists(p):
        return None
    im = Image.open(p)
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:   # drawn on a transparent background: use it as is
        a = np.array(im.convert("RGBA"))[:, :, 3]
        if (a < 10).mean() > .05:
            return a
    if not os.path.exists(AI_PY):
        return None
    cache = os.path.join(STUDIO, "build_cache", "ai", os.path.relpath(p, STUDIO).replace("/", "__"))
    if not (os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(p)):
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        r = subprocess.run([AI_PY, os.path.join(STUDIO, "engine", "rembg_cut.py"), p, cache], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(cache):
            return None
    a = np.array(Image.open(cache).convert("RGBA"))[:, :, 3]
    return _refill_holes(np.array(im.convert("RGB")), a)


def _refill_holes(rgb, a):
    """The AI remover sometimes deletes white areas INSIDE a character (Mascot's eye whites). Holes enclosed by the character are
    filled back in, unless the hole is flat background cream (a real gap between legs/bench slats)."""
    h, w = a.shape
    bgm = (a < 128).astype(np.uint8)
    n, lab = cv2.connectedComponents(bgm, connectivity=4)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]); bgc = np.median(border, axis=0).astype(np.int16)
    lum = rgb.astype(np.float32).mean(axis=2); out = a.copy()
    for L in range(1, n):
        if L in edge: continue
        reg = lab == L
        if reg.sum() < 20: out[reg] = 255; continue
        px = rgb[reg].astype(np.int16)
        warm_bg = abs((px[:, 0] - px[:, 2]).mean() - (bgc[0] - bgc[2])) < 8        # cream is warm; eye whites/shirts are neutral
        near_bg = np.abs(px - bgc).max(axis=1).mean() < 28
        flat_bg = warm_bg and near_bg
        if not flat_bg: out[reg] = 255
    return out


def cut(img_rgb, tol=38, pockets=False, crop=True, alpha=None):
    """alpha: optional mask from ai_alpha() (preferred). Without it, the colour-based flood-fill cutter is used."""
    h, w = img_rgb.shape[:2]
    if alpha is not None:
        alpha = alpha.copy()
        alpha[alpha < 12] = 0
        return _finish(img_rgb, alpha, crop)
    # background colour = median of the border pixels
    border = np.concatenate([img_rgb[0], img_rgb[-1], img_rgb[:, 0], img_rgb[:, -1]])
    bg = np.median(border, axis=0)
    diff = np.abs(img_rgb.astype(np.int16) - bg.astype(np.int16)).max(axis=2)
    cand = (diff < tol).astype(np.uint8)
    # keep only background regions connected to the border
    n, lab = cv2.connectedComponents(cand, connectivity=4)
    edge_labels = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    edge_labels.discard(0)
    bgmask = np.isin(lab, list(edge_labels)) & (cand == 1)
    # enclosed background pockets (gap between legs, under a bench, between arm and body): a pocket is removed only if it
    # is FLAT background colour: almost every pixel within a tight tolerance of the border colour and no shading.
    # White fur, eyes and shirts have shading and are cooler/brighter than the cream, so they stay.
    min_area = 0.00025 * h * w
    lum = img_rgb.astype(np.float32).mean(axis=2)
    for L in range(1, n):
        if L in edge_labels:
            continue
        reg = lab == L
        area = int(reg.sum())
        if area < min_area:
            continue
        px = img_rgb[reg].astype(np.int16)
        close = (np.abs(px - bg.astype(np.int16)).max(axis=1) < 14).mean()
        flat = lum[reg].std() < 3.5
        warm_ok = abs(((px[:, 0] - px[:, 2]).mean()) - (bg[0] - bg[2])) < 5
        if close > .9 and flat and warm_ok:
            bgmask |= reg
        elif pockets:
            ys_, xs_ = np.nonzero(reg)
            if ys_.mean() >= .62 * h and (px[:, 0] - px[:, 2]).mean() > 6:
                bgmask |= reg
    alpha = np.where(bgmask, 0, 255).astype(np.uint8)
    # tidy: close tiny holes, soften edge
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8), iterations=1)      # remove the 1-px cream halo
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    return _finish(img_rgb, alpha, crop)


def _finish(img_rgb, alpha, crop):
    h, w = img_rgb.shape[:2]
    # colour decontamination: edge pixels take the colour of the nearest solid interior pixel
    solid = (alpha > 250).astype(np.uint8)
    if solid.any():
        edge = (alpha > 0) & (alpha <= 250)
        dil = cv2.dilate(img_rgb, np.ones((3, 3), np.uint8))
        inner = cv2.erode(solid, np.ones((3, 3), np.uint8))
        src = img_rgb.copy(); src[inner == 0] = 0
        cnt = cv2.blur(inner.astype(np.float32), (5, 5)); acc = cv2.blur(src.astype(np.float32), (5, 5))
        ok = edge & (cnt > 0.05)
        img_rgb = img_rgb.copy(); img_rgb[ok] = (acc[ok] / cnt[ok][:, None]).clip(0, 255).astype(np.uint8)
    rgba = np.dstack([img_rgb, alpha])
    ys, xs = np.where(alpha > 20)
    if len(xs) == 0 or not crop:
        return rgba
    m = 6
    y0, y1 = max(ys.min() - m, 0), min(ys.max() + m, h)
    x0, x1 = max(xs.min() - m, 0), min(xs.max() + m, w)
    return rgba[y0:y1, x0:x1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--tol", type=int, default=38)
    ap.add_argument("--grid")
    ap.add_argument("--scale", type=float, default=1.0, help="upscale before cutting (small sheets)")
    a = ap.parse_args()
    im = Image.open(a.src).convert("RGB")
    if a.scale != 1.0:
        im = im.resize((int(im.width * a.scale), int(im.height * a.scale)), Image.LANCZOS)
    arr = np.array(im)
    if a.grid:
        cols, rows = map(int, a.grid.lower().split("x"))
        H, W = arr.shape[:2]
        k = 0
        for r in range(rows):
            for c in range(cols):
                k += 1
                tile = arr[r * H // rows:(r + 1) * H // rows, c * W // cols:(c + 1) * W // cols]
                Image.fromarray(cut(tile, a.tol), "RGBA").save("%s_%d.png" % (a.dst, k))
    else:
        Image.fromarray(cut(arr, a.tol), "RGBA").save(a.dst)


if __name__ == "__main__":
    main()
