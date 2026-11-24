#!/usr/bin/env python3
"""Thumbnails for YouTube Test & Compare: 2-3 genuinely different concepts per episode.

  python3 engine/thumbnails.py episodes/EpN

Reads episodes/EpN/thumbs.json:
  {"series": "Series One", "title": "<video title, to check words aren't repeated>",
   "variants": [{"id": "A", "art": "episodes/EpN/art/thumb_A.png", "setup": "YELLOW LINE", "punch": "WHITE LINE", "concept": "..."}]}
Art is Codex-drawn, 16:9, NO text, subject on the RIGHT, left ~40-45% calm for text (brand rule). This script adds the
series pill (top-left) and the two-beat text (yellow setup / white punchline) in brand fonts.
Writes out/<EpN>_thumb_<id>.jpg (1280x720, < 2 MB) and build/checks/<EpN>_thumbs_phone.jpg (all variants at phone size)."""
import json, os, sys
import numpy as np
from PIL import Image

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(STUDIO, "engine"))
import render as R


def make(ep):
    name = os.path.basename(ep.rstrip("/"))
    spec = json.load(open(os.path.join(ep, "thumbs.json")))
    title_words = set(w.strip("?.,!:").lower() for w in spec.get("title", "").split())
    outs, warns = [], []
    for v in spec["variants"]:
        src = Image.open(os.path.join(STUDIO, v["art"])).convert("RGB")
        r = 16 / 9
        if src.width / src.height > r:   # crop to 16:9 keeping the right side (subject)
            nw = int(src.height * r); src = src.crop((src.width - nw, 0, src.width, src.height))
        else:
            nh = int(src.width / r); src = src.crop((0, (src.height - nh) // 2, src.width, (src.height - nh) // 2 + nh))
        im = np.array(src.resize((1280, 720), Image.LANCZOS))
        shade = np.linspace(.5, 1.0, 640)[None, :, None]
        im[:, :640] = (im[:, :640] * shade).astype(np.uint8)
        R.blend(im, R.text_sprite("pill", spec["series"], 40, 600), 28, 24)
        y = 230
        if v.get("setup"):
            l1 = R.text_sprite("title", v["setup"], v.get("setup_size", 96), 600); R.blend(im, l1, 40, y); y += l1.shape[0] - 10
        if v.get("punch"):
            l2 = R.text_sprite("big", v["punch"], v.get("punch_size", 118), 600); R.blend(im, l2, 40, y)
        out = os.path.join(ep, "out", "%s_thumb_%s.jpg" % (name, v["id"]))
        Image.fromarray(im).save(out, quality=90)
        words = (v.get("setup", "") + " " + v.get("punch", "")).split()
        if len(words) > 5: warns.append("%s: %d words on the thumbnail (aim for 0-4)" % (v["id"], len(words)))
        rep = title_words & set(w.strip("?.,!:'").lower() for w in words) - {"the", "a", "of", "to", "was", "who"}
        if rep: warns.append("%s: repeats title words %s (thumbnail should ADD to the title)" % (v["id"], sorted(rep)))
        if os.path.getsize(out) > 2e6: warns.append("%s: over 2 MB" % v["id"])
        outs.append(out); print("THUMB", v["id"], out, "%.2f MB" % (os.path.getsize(out) / 1e6))
    # phone-size check sheet (how they look in the feed)
    tiles = [Image.open(o).resize((360, 202), Image.LANCZOS) for o in outs]
    sheet = Image.new("RGB", (len(tiles) * 370 + 10, 222), (240, 240, 240))
    for i, t in enumerate(tiles): sheet.paste(t, (10 + i * 370, 10))
    os.makedirs(os.path.join(ep, "build", "checks"), exist_ok=True)
    p = os.path.join(ep, "build", "checks", "%s_thumbs_phone.jpg" % name); sheet.save(p, quality=90); print("PHONE CHECK", p)
    for w in warns: print("WARN", w)


if __name__ == "__main__":
    make(sys.argv[1])
