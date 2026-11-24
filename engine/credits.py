"""Make a tall transparent rolling-credits image from a list of (style, text) lines."""
import os
from PIL import Image, ImageDraw, ImageFont

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILL = os.path.join(STUDIO, "fonts", "LuckiestGuy-Regular.ttf")
MARK = os.path.join(STUDIO, "fonts", "PermanentMarker-Regular.ttf")


def make(lines, out, width=1600):
    styles = {"head": (PILL, 64, (255, 210, 0)), "sub": (PILL, 40, (255, 255, 255)),
              "body": (MARK, 34, (240, 236, 225)), "gap": None}
    rows = []
    for st, txt in lines:
        if st == "gap":
            rows.append((None, None, 40)); continue
        fp, sz, col = styles[st]
        f = ImageFont.truetype(fp, sz)
        words, cur, wrapped = txt.split(), "", []
        for w in words:
            t = (cur + " " + w).strip()
            if f.getbbox(t)[2] > width - 80 and cur:
                wrapped.append(cur); cur = w
            else:
                cur = t
        wrapped.append(cur)
        for l in wrapped:
            rows.append((f, (l, col), int(sz * 1.35)))
    H = sum(r[2] for r in rows) + 40
    im = Image.new("RGBA", (width, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    y = 20
    for f, payload, h in rows:
        if f:
            l, col = payload
            w = f.getbbox(l)[2]
            d.text(((width - w) // 2, y), l, font=f, fill=col + (255,), stroke_width=2, stroke_fill=(20, 18, 18, 255))
        y += h
    im.save(out)
    return im.size
