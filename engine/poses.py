#!/usr/bin/env python3
"""Talking-pose sets: P poses x 3 mouths (closed/mid/open) of one character, aligned on one canvas.

Alignment (so the head never jumps):
  - every mouth variant is registered to its pose's CLOSED frame by phase correlation (near-identical images)
  - every pose's CLOSED frame is registered to pose 0 by the HEAD: top of the hair + centre of the head (top 22% of the figure)
Frames are cached in build_cache/poses/."""
import os, numpy as np, cv2
from PIL import Image
from cutout import cut, ai_alpha

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(p, size=None):
    rgb = np.array(Image.open(os.path.join(STUDIO, p)).convert("RGB"))
    A = ai_alpha(p)
    if size and (rgb.shape[1], rgb.shape[0]) != size:
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        if A is not None: A = cv2.resize(A, size, interpolation=cv2.INTER_LINEAR)
    return cut(rgb, crop=False, alpha=A)


def _shift(rgba, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(rgba, M, (rgba.shape[1], rgba.shape[0]), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))


def _head(rgba):
    a = rgba[:, :, 3] > 40; ys, xs = np.where(a)
    top, bot = ys.min(), ys.max(); band = a[top: top + int((bot - top) * .22)]
    yy, xx = np.where(band)
    return top, xx.mean()


def _phase(ref, img):
    g1 = cv2.cvtColor(ref[:, :, :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
    g2 = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
    (dx, dy), _ = cv2.phaseCorrelate(g2, g1)
    return dx, dy


def build(frames):
    """frames: [[closed, mid, open], ...] image paths (mid/open may be None -> reuse). Returns list of aligned RGBA arrays, pose-major."""
    base_rgb = Image.open(os.path.join(STUDIO, frames[0][0])); size = base_rgb.size
    out = []; ref_top, ref_x = None, None
    nM = max(len(t) for t in frames)   # 3 (closed/mid/open) or 6 Rhubarb mouths (A B C D E F)
    for p, trio in enumerate(frames):
        closed = _load(trio[0], size)
        t, x = _head(closed)
        if p == 0: ref_top, ref_x = t, x
        else: closed = _shift(closed, ref_x - x, ref_top - t)
        row = [closed]
        for q in trio[1:]:
            if not q or not os.path.exists(os.path.join(STUDIO, q)):
                row.append(row[-1]); continue
            im = _load(q, size)
            t2, x2 = _head(im); im = _shift(im, ref_x - x2, ref_top - t2)   # rough, by head
            dx, dy = _phase(closed, im)                                       # fine, by image
            if abs(dx) < 40 and abs(dy) < 40: im = _shift(im, dx, dy)
            row.append(im)
        while len(row) < nM: row.append(row[-1])
        out += row
    # crop all frames to the union bbox so the sprite is tight but identical for every frame
    a = np.zeros(out[0].shape[:2], bool)
    for f in out: a |= f[:, :, 3] > 20
    ys, xs = np.where(a); m = 6
    y0, y1, x0, x1 = max(ys.min() - m, 0), ys.max() + m, max(xs.min() - m, 0), xs.max() + m
    return [f[y0:y1, x0:x1] for f in out]
