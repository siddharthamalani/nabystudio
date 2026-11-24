#!/usr/bin/env python3
"""Cut-out character rig: a body + interchangeable heads (expressions x mouth states) joined at a neck pivot.

Spec (in a shot layer):  {"rig": {"body": <png>, "heads": {"flat": {"closed": p, "open": p, "blink": p}, "eyebrow": {"closed": p}, ...},
                          "line": "B01", "expr": [[<time key>, "flat"], ...]}, "x":.., "y":.., "h":..}
Body: transparent, no head, neck stub at the top. Heads: transparent, identical canvas/size/position, neck ending at the bottom.
build() measures the neck on both (top of the body, bottom of the head) so the head sits on the neck at the right scale."""
import os, numpy as np
from PIL import Image
from cutout import cut, ai_alpha

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rgba(p, crop):
    im = Image.open(os.path.join(STUDIO, p))
    rgb = np.array(im.convert("RGB"))
    return cut(rgb, crop=crop, alpha=ai_alpha(p))


def _neck(a, top=True):
    """centre x, edge y and width of the neck, measured 3% in from the top (body) or bottom (head) of the opaque area"""
    ys, xs = np.where(a > 128)
    y0, y1 = ys.min(), ys.max(); hgt = y1 - y0
    y = int(y0 + hgt * .03) if top else int(y1 - hgt * .03)
    row = np.where(a[y] > 128)[0]
    return (row.min() + row.max()) / 2, (y0 if top else y1), (row.max() - row.min())


def build(spec):
    body = _rgba(spec["body"], True)
    bx, by, bw = _neck(body[:, :, 3], top=True)
    heads, hx = {}, None
    for expr, states in spec["heads"].items():
        heads[expr] = {k: _rgba(v, False) for k, v in states.items() if v and os.path.exists(os.path.join(STUDIO, v))}
    ref = next(iter(heads.values()))["closed"]
    hx, hy, hw = _neck(ref[:, :, 3], top=False)
    # size the head against the shoulders (cartoon chest-up: head ≈ 42% of shoulder width), not the neck
    ba = body[:, :, 3] > 128; shoulder = np.ptp(np.where(ba.any(axis=0))[0])
    ha = ref[:, :, 3] > 128; ys = np.where(ha.any(axis=1))[0]
    face = ha[ys.min(): ys.min() + int((ys.max() - ys.min()) * .7)]          # width of the head itself, not the neck
    head_w = np.ptp(np.where(face.any(axis=0))[0])
    scale = float(np.clip(spec.get("head_ratio", .42) * shoulder / max(head_w, 1), .3, 2.5))
    # tuck the neck into the collar: the head's anchor sits below the top of the body; the body is drawn OVER the head
    tuck = spec.get("tuck", .09) * body.shape[0]
    hy_anchor = hy - (ys.max() - ys.min()) * spec.get("neck_len", .14)   # attach a bit above the neck's bottom end
    # trim the body's own neck stub above the collar line, so no second "neck" shows beside the head
    body = body.copy(); body[: int(by + tuck * .8), :, 3] = 0
    return body, heads, {"neck": [float(bx), float(by + tuck)], "hanchor": [float(hx), float(hy_anchor)], "hscale": scale, "headBehind": True}
