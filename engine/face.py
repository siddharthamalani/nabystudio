#!/usr/bin/env python3
"""Face-patch rig: ONE master drawing + small patches (mouth shapes, eyes/brows) cut from Codex edits of that master.
Nothing else is ever redrawn, so the face, neck, clothes and texture can't drift (owner direction, 24 Nov 2026).
build(spec) -> master RGBA, {name: (patch RGBA, x, y)} in master pixel coordinates."""
import os, numpy as np, cv2
from PIL import Image
from cutout import cut, ai_alpha

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rgb(p, size=None):
    im = Image.open(os.path.join(STUDIO, p)).convert("RGB")
    if size and im.size != size: im = im.resize(size, Image.LANCZOS)
    return np.array(im)


def build(spec):
    mp = spec["master"]; size = Image.open(os.path.join(STUDIO, mp)).size
    m_rgb = _rgb(mp); master = cut(m_rgb, crop=False, alpha=ai_alpha(mp))
    g0 = cv2.cvtColor(m_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    patches = {}
    for name, p in spec["patches"].items():
        if not os.path.exists(os.path.join(STUDIO, p)): continue
        e = _rgb(p, size); g1 = cv2.cvtColor(e, cv2.COLOR_RGB2GRAY).astype(np.float32)
        (dx, dy), _ = cv2.phaseCorrelate(g1, g0)                      # align the edit to the master
        if abs(dx) < 40 and abs(dy) < 40:
            e = cv2.warpAffine(e, np.float32([[1, 0, dx], [0, 1, dy]]), (size[0], size[1]), borderMode=cv2.BORDER_REPLICATE)
        d = np.abs(e.astype(np.int16) - m_rgb.astype(np.int16)).max(axis=2)
        mask = (d > 28).astype(np.uint8) & (master[:, :, 3] > 128).astype(np.uint8)
        # keep only the region the row asked for: the biggest changed cluster(s) inside the head (upper 45% of the figure)
        ys = np.where(master[:, :, 3].any(axis=1) if False else (master[:, :, 3] > 128).any(axis=1))[0]
        head_top = int(ys.min()); head_bottom = int(ys.min() + (ys.max() - ys.min()) * .45); mask[head_bottom:] = 0
        # zones: mouth patches only touch the lower face, eye/brow patches only the upper face
        split = int(head_top + (head_bottom - head_top) * spec.get("split", .55))
        if name.startswith("m_"): mask[:split] = 0
        elif name.startswith("e_"): mask[split:] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
        if n <= 1: continue
        keep = np.zeros_like(mask)
        big = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:4]
        for i in big:
            if stats[i, cv2.CC_STAT_AREA] > 150: keep[lab == i] = 1
        keep = cv2.dilate(keep, np.ones((15, 15), np.uint8))
        alpha = cv2.GaussianBlur((keep * 255).astype(np.uint8), (21, 21), 0)
        alpha = np.minimum(alpha, master[:, :, 3])
        yy, xx = np.where(alpha > 4)
        if not len(xx): continue
        y0, y1, x0, x1 = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
        patches[name] = (np.dstack([e, alpha])[y0:y1, x0:x1], int(x0), int(y0))
    return master, patches
