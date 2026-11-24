#!/usr/bin/env python3
"""STUDIO renderer: shot list -> video frames (piped to ffmpeg).

A shot list is a python module exposing SHOTS (list of dicts) and optional SHORTS.
Times in a shot can be numbers (seconds) or cue keys ("@phrase text", "line:N03",
"line_end:N03", "gap:series_card") resolved against build/cues.json.

Each shot:
  {"at": <time>, "bg": path | "#rrggbb", "cam": [z0, z1, (px0,py0), (px1,py1)],
   "layers": [ {"img": path, "x": .5, "y": .95, "h": .6, "t0": 0, "t1": None,
                "enter": "pop|fade|slide_l|slide_r|none", "idle": "bob|breathe|none",
                "flip": False, "talk": {"line": "M01", "open": path, "mid": path},
                "bounce_line": "R01", "cut": True} ],
   "texts":  [ {"kind": "pill|title|note|quote|label|big|score", "text": "...", "x": .5, "y": .2,
                "size": 70, "t0": 0, "t1": None, "src": "source line"} ],
   "focus": .5,   # horizontal centre for vertical (9:16) crops
   "dissolve": .25}
"""
import json, os, sys, math, subprocess, importlib.util, functools
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(STUDIO, "engine"))
from cutout import cut as cutout_arr, ai_alpha
import fx

FF = os.path.join(STUDIO, "bin", "ffmpeg")
FONT_PILL = os.path.join(STUDIO, "fonts", "LuckiestGuy-Regular.ttf")
FONT_MARK = os.path.join(STUDIO, "fonts", "PermanentMarker-Regular.ttf")
YELLOW, RED, INK, CREAM = (255, 210, 0), (196, 30, 36), (20, 18, 18), (243, 235, 221)
FPS = 30


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def back_out(u):
    u = min(max(u, 0.0), 1.0); c = 1.70158
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


# ---------------------------------------------------------------- assets
@functools.lru_cache(maxsize=256)
def load_rgba(path, do_cut):
    p = path if os.path.isabs(path) else os.path.join(STUDIO, path)
    cache = os.path.join(STUDIO, "build_cache", "cut", os.path.relpath(p, STUDIO).replace("/", "__"))
    if do_cut and os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(p):
        return np.array(Image.open(cache).convert("RGBA"))
    im = Image.open(p)
    if im.mode == "RGBA" or not do_cut:
        arr = np.array(im.convert("RGBA"))
    else:
        arr = cutout_arr(np.array(im.convert("RGB")), alpha=ai_alpha(p))
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        Image.fromarray(arr).save(cache)
    return arr


@functools.lru_cache(maxsize=64)
def load_bg(path, W, H, margin):
    if path.startswith("#"):
        c = tuple(int(path[i:i + 2], 16) for i in (1, 3, 5))
        return np.full((int(H * margin), int(W * margin), 3), c[::-1], np.uint8)[:, :, ::-1].copy()
    p = path if os.path.isabs(path) else os.path.join(STUDIO, path)
    im = Image.open(p).convert("RGB")
    tw, th = int(W * margin), int(H * margin)
    s = max(tw / im.width, th / im.height)
    im = im.resize((max(tw, int(im.width * s + .5)), max(th, int(im.height * s + .5))), Image.LANCZOS)
    l, t = (im.width - tw) // 2, (im.height - th) // 2
    return np.array(im.crop((l, t, l + tw, t + th)))


def _font(path, size):
    return ImageFont.truetype(path, int(size))


@functools.lru_cache(maxsize=512)
def text_sprite(kind, text, size, maxw, src=""):
    """Render a brand text element to an RGBA numpy array."""
    if kind in ("pill", "label"):
        f = _font(FONT_PILL, size)
        t = text.upper()
        bb = f.getbbox(t); tw, th = bb[2] - bb[0], bb[3] - bb[1]
        px, py = int(size * .55), int(size * .32)
        w, h = tw + 2 * px, th + 2 * py
        im = Image.new("RGBA", (w + 16, h + 16), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((8, 10, w + 8, h + 10), radius=h // 2, fill=(0, 0, 0, 90))
        d.rounded_rectangle((4, 4, w + 4, h + 4), radius=h // 2, fill=(255, 255, 255, 255))
        d.rounded_rectangle((8, 8, w, h), radius=(h - 8) // 2, fill=YELLOW + (255,))
        d.text((4 + px - bb[0], 4 + py - bb[1]), t, font=f, fill=RED + (255,))
        return np.array(im)
    if kind in ("title", "big", "score"):
        f = _font(FONT_PILL, size)
        lines = _wrap(text, f, maxw)
        sw = max(3, int(size * .09))
        lh = int(size * 1.12)
        w = max(f.getbbox(l)[2] for l in lines) + 2 * sw + 10
        h = lh * len(lines) + 2 * sw + 10
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        fill = YELLOW if kind == "title" else (255, 255, 255)
        for i, l in enumerate(lines):
            lw = f.getbbox(l)[2]
            x = (w - lw) // 2
            d.text((x + 4, sw + i * lh + 5), l, font=f, fill=(0, 0, 0, 120), stroke_width=sw, stroke_fill=(0, 0, 0, 120))
            d.text((x, sw + i * lh), l, font=f, fill=fill + (255,), stroke_width=sw, stroke_fill=INK + (255,))
        return np.array(im)
    if kind == "chalk":
        f = _font(FONT_MARK, size)
        lines = _wrap(text, f, maxw); lh = int(size * 1.25)
        w = max(f.getbbox(l)[2] for l in lines) + 20; h = lh * len(lines) + 20
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        for i, l in enumerate(lines):
            d.text((10, 10 + i * lh), l, font=f, fill=(245, 245, 235, 240))
        im = im.filter(ImageFilter.GaussianBlur(.6))
        return np.array(im)
    if kind in ("note", "quote"):
        f = _font(FONT_MARK, size)
        fs = _font(FONT_MARK, size * .55)
        lines = _wrap(text, f, maxw); lh = int(size * 1.28)
        srcl = _wrap(src, fs, maxw) if src else []
        tw = max([f.getbbox(l)[2] for l in lines] + [fs.getbbox(l)[2] for l in srcl])
        pad = int(size * .7)
        w = tw + 2 * pad; h = lh * len(lines) + int(size * .75) * len(srcl) + 2 * pad + (int(size * .3) if srcl else 0)
        im = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rectangle((14, 16, w + 14, h + 16), fill=(0, 0, 0, 80))
        paper = (255, 236, 150) if kind == "note" else CREAM
        d.rectangle((6, 6, w + 6, h + 6), fill=paper + (255,))
        if kind == "quote":
            d.rectangle((6, 6, 18, h + 6), fill=RED + (255,))
        for i, l in enumerate(lines):
            d.text((6 + pad, 6 + pad + i * lh), l, font=f, fill=INK + (255,))
        y = 6 + pad + len(lines) * lh + int(size * .3)
        for l in srcl:
            d.text((6 + pad, y), l, font=fs, fill=RED + (255,)); y += int(size * .75)
        im = im.rotate(-1.2 if kind == "note" else 0, resample=Image.BICUBIC, expand=True)
        return np.array(im)
    if kind == "caption":
        f = _font(FONT_PILL, size)
        lines = _wrap(text.upper(), f, maxw)
        sw = max(4, int(size * .12)); lh = int(size * 1.1)
        w = max(f.getbbox(l)[2] for l in lines) + 2 * sw + 8; h = lh * len(lines) + 2 * sw + 8
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        for i, l in enumerate(lines):
            lw = f.getbbox(l)[2]; x = (w - lw) // 2
            d.text((x, sw + i * lh), l, font=f, fill=(255, 255, 255, 255), stroke_width=sw, stroke_fill=INK + (255,))
        return np.array(im)
    raise ValueError(kind)


def _wrap(text, f, maxw):
    out = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if f.getbbox(t)[2] > maxw and cur:
                out.append(cur); cur = w
            else:
                cur = t
        out.append(cur)
    return out


def blend(dst, src, x, y, alpha=1.0):
    """Alpha-blend RGBA src onto RGB dst with top-left at (x, y)."""
    H, W = dst.shape[:2]; h, w = src.shape[:2]
    x0, y0 = max(x, 0), max(y, 0); x1, y1 = min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0 or alpha <= 0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    a = s[:, :, 3:4].astype(np.float32) * (alpha / 255.0)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    dst[y0:y1, x0:x1] = (d * (1 - a) + s[:, :, :3].astype(np.float32) * a).astype(np.uint8)


def scaled(arr, scale, angle=0.0, flip=False):
    if flip:
        arr = arr[:, ::-1]
    h, w = arr.shape[:2]
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    out = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    if abs(angle) > .05:
        M = cv2.getRotationMatrix2D((nw / 2, nh), angle, 1.0)
        out = cv2.warpAffine(out, M, (nw, nh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return out


# ---------------------------------------------------------------- timing
class Cues:
    def __init__(self, ep):
        d = json.load(open(os.path.join(ep, "build", "cues.json")))
        self.duration = d["duration"]; self.c = d["cues"]
        self.env = {}
        self.vo, _ = None, None

    def t(self, key):
        if isinstance(key, (int, float)):
            return float(key)
        k = str(key)
        off = 0.0
        if k.startswith("@"):
            while "|" in k:
                k, o = k.rsplit("|", 1); off += float(o)
        else:
            while "+" in k:
                k, o = k.rsplit("+", 1); off += float(o)
        if k.startswith("@"):
            needle = k[1:].lower()
            for c in self.c:
                if c["type"] == "phrase" and needle in c["text"].lower():
                    return c["start"] + off
            raise KeyError("phrase not found: " + k)
        if k.startswith("@end:"):
            pass
        kind, val = k.split(":", 1)
        for c in self.c:
            if kind == "line" and c["type"] == "line" and c["line"] == val:
                return c["start"] + off
            if kind == "line_end" and c["type"] == "line" and c["line"] == val:
                return c["end"] + off
            if kind == "end" and c["type"] == "phrase" and val.lower() in c["text"].lower():
                return c["end"] + off
            if kind == "gap" and c["type"] == "gap" and c["label"] == val:
                return c["start"] + off
        raise KeyError(key)

    def line_span(self, lid):
        for c in self.c:
            if c["type"] == "line" and c["line"] == lid:
                return c["start"], c["end"]
        return None


class Envelope:
    """Per-line loudness envelope from the voice track, for mouth flaps and bounces."""
    def __init__(self, wav):
        import soundfile as sf
        y, sr = sf.read(wav, dtype="float32")
        hop = sr // FPS
        n = len(y) // hop
        r = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
        self.env = r / (np.percentile(r, 98) + 1e-6)

    def at(self, t):
        i = int(t * FPS)
        return float(self.env[i]) if 0 <= i < len(self.env) else 0.0


# ---------------------------------------------------------------- frame
def render_frame(shot, t_local, t_abs, W, H, cues, env, vertical=False, text_scale=1.0):
    cam = shot.get("cam", [1.0, 1.06, (0, 0), (0, 0)])
    dur = shot["_dur"]
    u = ease(t_local / max(dur, 1e-3))
    z = cam[0] + (cam[1] - cam[0]) * u
    p0, p1 = cam[2] if len(cam) > 2 else (0, 0), cam[3] if len(cam) > 3 else (0, 0)
    px = p0[0] + (p1[0] - p0[0]) * u; py = p0[1] + (p1[1] - p0[1]) * u
    margin = 1.25
    # world canvas = 16:9 at (WW x HH); for vertical we render a wide world then crop
    if vertical:
        HH = H; WW = int(H * 16 / 9)
    else:
        WW, HH = W, H
    bgp = shot["bg"]
    if not bgp.startswith("#") and not os.path.exists(os.path.join(STUDIO, bgp)):
        bgp = "#1E5F5F"
    bg = load_bg(bgp, WW, HH, margin)
    if shot.get("route"):
        R_ = shot["route"]
        r0 = _tt(R_.get("t0", 0), shot, cues)
        bg = bg.copy(); fx.route(bg, R_, ease((t_local - r0) / R_.get("dur", 2.0)) if t_local >= r0 else 0.0, t_abs)
    bh, bw = bg.shape[:2]
    # camera crop on the background
    cw, ch = WW / z, HH / z
    cx = bw / 2 + px * (bw - cw) / 2; cy = bh / 2 + py * (bh - ch) / 2
    M = np.float32([[WW / cw, 0, -(cx - cw / 2) * WW / cw], [0, HH / ch, -(cy - ch / 2) * HH / ch]])
    frame = cv2.warpAffine(bg, M, (WW, HH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    zs = z / 1.0  # layers move with the camera a little (parallax 60%)
    par = 0.6
    for L in shot.get("layers", []):
        t0 = cues.t(L.get("t0", 0)) - shot["_t"] if not isinstance(L.get("t0", 0), (int, float)) else L.get("t0", 0)
        t1 = L.get("t1")
        if t1 is not None and not isinstance(t1, (int, float)):
            t1 = cues.t(t1) - shot["_t"]
        if t_local < t0 or (t1 is not None and t_local > t1):
            continue
        lt = t_local - t0
        img_path = L.get("img", "")
        talk = L.get("talk")
        level = 0.0
        if talk:
            sp = cues.line_span(talk["line"])
            if sp and sp[0] <= t_abs <= sp[1]:
                level = env.at(t_abs)
                if level > .45 and talk.get("open"):
                    img_path = talk["open"]
                elif level > .18 and talk.get("mid"):
                    img_path = talk["mid"]
                elif level > .18 and talk.get("open") and int(t_abs * 9) % 2 == 0:
                    img_path = talk["open"]
        if L.get("bounce_line"):
            sp = cues.line_span(L["bounce_line"])
            if sp and sp[0] <= t_abs <= sp[1]:
                level = env.at(t_abs)
        if L.get("sheet"):
            if not os.path.exists(os.path.join(STUDIO, L["sheet"])):
                if not L.get("img"):
                    continue
                L = dict(L); L.pop("sheet")
        if L.get("sheet"):
            frames = fx.load_sheet(L["sheet"], L["n"])
            mode = L.get("mode", "loop")
            if mode == "loop":
                fi = int(lt * L.get("fps", 10)) % L["n"]
            elif mode == "talk":
                fi = L.get("closed", 0)
                sp = cues.line_span(L["line"])
                if sp and sp[0] <= t_abs <= sp[1]:
                    level = env.at(t_abs)
                    fi = L.get("open", 2) if level > .42 else (L.get("mid", 1) if level > .14 else L.get("closed", 0))
                elif L.get("blink") is not None and fx.blink_index(t_abs, L.get("x", .5)) == 2:
                    fi = L["blink"]
            elif mode == "blink":
                b = fx.blink_index(t_abs, L.get("x", .5))
                fi = [L.get("open", 0), L.get("half", 1), L.get("closed", 2)][b]
                if L.get("alt") is not None and int(t_abs / 5.3) % 3 == 1 and (t_abs % 5.3) < .5:
                    fi = L["alt"]
            else:
                fi = int(mode)
            spr = frames[fi]
        else:
          if not os.path.exists(os.path.join(STUDIO, img_path)):
            if img_path != L["img"] and os.path.exists(os.path.join(STUDIO, L["img"])):
                img_path = L["img"]
            else:
                continue
          spr = load_rgba(img_path, L.get("cut", True))
        if not L.get("sheet") and img_path != L["img"] and os.path.exists(os.path.join(STUDIO, L["img"])):
            base = load_rgba(L["img"], L.get("cut", True))  # lock mouth variants to the base pose's size
            if spr.shape[:2] != base.shape[:2]:
                spr = cv2.resize(spr, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_AREA)
        target_h = L.get("h", .6) * HH * (1 + (z - 1) * par)
        sc = target_h / spr.shape[0]
        ang = 0.0; dy = 0.0; dx = 0.0; alpha = 1.0
        idle = L.get("idle", "breathe")
        if idle == "bob":
            dy += math.sin((t_abs + L.get("x", .5) * 3) * 2.2) * HH * .006
        elif idle == "breathe":
            sc *= 1 + .008 * math.sin((t_abs + L.get("x", .5)) * 2.0)
        if level > 0:
            dy -= level * HH * .012; ang += (level - .3) * 2.5
        enter = L.get("enter", "pop")
        if enter == "pop":
            k = back_out(lt / .35); sc *= max(k, .01); alpha = min(1, lt / .12)
        elif enter == "fade":
            alpha = min(1, lt / .35)
        elif enter == "slide_l":
            dx -= (1 - ease(lt / .5)) * WW * .6
        elif enter == "slide_r":
            dx += (1 - ease(lt / .5)) * WW * .6
        if t1 is not None and t1 - t_local < .2:
            alpha *= max(0, (t1 - t_local) / .2)
        if L.get("scroll"):  # rolling credits: sprite width = frame width, scrolls top fraction y0 -> y1
            s = scaled(spr, WW * L.get("w", .9) / spr.shape[1])
            y0, y1 = L["scroll"]
            top = (y0 + (y1 - y0) * min(t_local / max(dur, .01), 1)) * HH
            blend(frame, s, int(WW / 2 - s.shape[1] / 2), int(top), alpha)
            continue
        if L.get("move"):
            mv = L["move"]; m0 = _tt(mv.get("t0", 0), shot, cues); m1 = _tt(mv.get("t1", dur), shot, cues)
            uu = min(max((t_local - m0) / max(m1 - m0, .01), 0), 1)
            if mv.get("ease", "linear") == "ease": uu = ease(uu)
            L = dict(L); L["x"] = mv["x0"] + (mv["x1"] - mv["x0"]) * uu
            if "y0" in mv: L["y"] = mv["y0"] + (mv["y1"] - mv["y0"]) * uu
            if L.get("sheet") and L.get("mode", "loop") == "loop":
                dy -= abs(math.sin(lt * L.get("fps", 10) * math.pi / L["n"] * 2)) * HH * .006
        s = scaled(spr, sc, ang, L.get("flip", False))
        lx = (L.get("x", .5) - .5) * WW * (1 + (z - 1) * par) - px * (z - 1) * WW * par * .5 + WW / 2
        ly = L.get("y", .95) * HH + (L.get("y", .95) - .5) * (z - 1) * HH * par
        blend(frame, s, int(lx - s.shape[1] / 2 + dx), int(ly - s.shape[0] + dy), alpha)
    if shot.get("particles"):
        fx.particles(frame, t_abs, shot["particles"], WW, HH)
    if shot.get("shake"):
        sh = [(_tt(a_, shot, cues), d_, m_ * HH / 1080) for (a_, d_, m_) in shot["shake"]]
        ox, oy = fx.shake_offset(t_local, sh)
        if ox or oy:
            frame = cv2.warpAffine(frame, np.float32([[1.03, 0, ox - WW * .015], [0, 1.03, oy - HH * .015]]), (WW, HH), borderMode=cv2.BORDER_REFLECT)
    if vertical:
        f = shot.get("focus", .5)
        x0 = int(min(max(f * WW - W / 2, 0), WW - W))
        frame = frame[:, x0:x0 + W].copy()
    for T in shot.get("texts", []):
        if vertical and T.get("no_vertical"):
            continue
        t0 = T.get("t0", 0); t0 = cues.t(t0) - shot["_t"] if not isinstance(t0, (int, float)) else t0
        t1 = T.get("t1"); t1 = (cues.t(t1) - shot["_t"]) if (t1 is not None and not isinstance(t1, (int, float))) else t1
        if t_local < t0 or (t1 is not None and t_local > t1):
            continue
        lt = t_local - t0
        size = T.get("size", 64) * text_scale * (W / 1920 if not vertical else 1080 / 1080 * 0.9)
        maxw = T.get("maxw", .8) * W
        spr = text_sprite(T["kind"], T["text"], int(size), int(maxw), T.get("src", ""))
        anim = T.get("anim", "pop")
        k = back_out(lt / .3) if anim == "pop" else 1.0
        if anim == "stamp":
            k = 1 + 1.4 * (1 - ease(lt / .16))
        a = min(1, lt / .15) if anim != "stamp" else min(1, lt / .06)
        if anim == "type":
            frac = min(1, lt / T.get("dur", 1.2))
            spr = spr.copy(); cutx = int(spr.shape[1] * frac); spr[:, cutx:, 3] = 0
        if t1 is not None and t1 - t_local < .2:
            a *= max(0, (t1 - t_local) / .2)
        s = scaled(spr, max(k, .01), T.get("tilt", 0))
        xx = T.get("vx", T.get("x", .5)) if vertical else T.get("x", .5)
        yy = T.get("vy", T.get("y", .2)) if vertical else T.get("y", .2)
        blend(frame, s, int(xx * W - s.shape[1] / 2), int(yy * H - s.shape[0] / 2), a)
    return frame


def _tt(v, shot, cues):
    return v if isinstance(v, (int, float)) else cues.t(v) - shot["_t"]


def resolve(shots, cues, end_time):
    for s in shots:
        s["_t"] = cues.t(s["at"])
    shots.sort(key=lambda s: s["_t"])
    for i, s in enumerate(shots):
        nxt = shots[i + 1]["_t"] if i + 1 < len(shots) else end_time
        s["_dur"] = nxt - s["_t"]
    return shots


def render(shots, cues, env, out_path, t_start, t_end, W, H, vertical=False, extra=None, text_scale=1.0):
    """extra(frame, t_abs) can draw captions etc. on top. Writes a lossless-ish intermediate."""
    n = int(round((t_end - t_start) * FPS))
    cmd = [FF, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H), "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    idx = 0
    for i in range(n):
        t = t_start + i / FPS
        while idx + 1 < len(shots) and shots[idx + 1]["_t"] <= t:
            idx += 1
        s = shots[idx]
        fr = render_frame(s, t - s["_t"], t, W, H, cues, env, vertical, text_scale)
        dis = s.get("dissolve", .25)
        if idx > 0 and t - s["_t"] < dis and dis > 0:
            pv = shots[idx - 1]
            fp = render_frame(pv, t - pv["_t"], t, W, H, cues, env, vertical, text_scale)
            a = ease((t - s["_t"]) / dis)
            if s.get("trans") == "whip":
                off = int(a * W)
                comb = np.concatenate([fp, fr], axis=1)[:, off:off + W]
                k = max(1, int(60 * math.sin(math.pi * a)))
                fr = cv2.blur(comb, (k * 2 + 1, 1))
            else:
                fr = cv2.addWeighted(fr, a, fp, 1 - a, 0)
        if extra:
            extra(fr, t)
        p.stdin.write(fr.tobytes())
        if i % 300 == 0:
            print("  frame %d/%d (%.0f%%)" % (i, n, 100.0 * i / n), flush=True)
    p.stdin.close(); p.wait()


def load_shotlist(path):
    spec = importlib.util.spec_from_file_location("shotlist", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
