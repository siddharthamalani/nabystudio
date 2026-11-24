#!/usr/bin/env python3
"""Depth maps for backgrounds (Depth Anything V2 Small, Apache-2.0, runs locally via onnxruntime).
White = near, black = far. Used by the Three.js 2.5D parallax in remotion/.

  python3 engine/depth.py img1.png [img2.png ...]      -> writes <name>.depth.png next to each image
"""
import os, sys
import numpy as np
from PIL import Image

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(STUDIO, "tools", "models", "depth_anything_v2_small.onnx")
_sess = None


def depth(path, size=518):
    global _sess
    import onnxruntime as ort
    if _sess is None:
        _sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    im = Image.open(path).convert("RGB")
    W, H = im.size
    h = size; w = int(round(size * W / H / 14)) * 14
    x = np.asarray(im.resize((w, h), Image.BICUBIC), np.float32) / 255.0
    x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    name = _sess.get_inputs()[0].name
    d = _sess.run(None, {name: x})[0].squeeze()
    d = (d - d.min()) / (d.max() - d.min() + 1e-6)
    out = Image.fromarray((d * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    dst = os.path.splitext(path)[0] + ".depth.png"
    out.save(dst)
    return dst


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(depth(p))
