"""Motion graphics + sprite animation helpers for engine/render.py."""
import functools, math, os
import numpy as np, cv2
from PIL import Image

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------ sprite sheets
@functools.lru_cache(maxsize=64)
def load_sheet(path, n):
    """Split a one-row animation sheet (cream background) into n aligned RGBA frames.
    Frames are bottom-centre aligned on a common canvas so they don't jitter."""
    from cutout import cut
    p = path if os.path.isabs(path) else os.path.join(STUDIO, path)
    cache = os.path.join(STUDIO, "build_cache", "sheets", os.path.relpath(p, STUDIO).replace("/", "__"))
    os.makedirs(cache, exist_ok=True)
    files = [os.path.join(cache, "f%02d.png" % i) for i in range(n)]
    if all(os.path.exists(f) and os.path.getmtime(f) > os.path.getmtime(p) for f in files):
        return [np.array(Image.open(f)) for f in files]
    rgb = np.array(Image.open(p).convert("RGB"))
    H, W = rgb.shape[:2]
    # full-sheet alpha via the same cutter (no crop): find columns that contain character pixels
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    fg = (np.abs(rgb.astype(np.int16) - bg.astype(np.int16)).max(axis=2) > 38)
    cols = fg.sum(axis=0) > max(2, H * .004)
    # runs of foreground columns
    runs, start = [], None
    for x, c in enumerate(cols):
        if c and start is None:
            start = x
        elif not c and start is not None:
            runs.append([start, x]); start = None
    if start is not None:
        runs.append([start, W])
    # merge small gaps until we have n runs
    while len(runs) > n:
        gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
        i = int(np.argmin(gaps)); runs[i] = [runs[i][0], runs[i + 1][1]]; del runs[i + 1]
    if len(runs) != n:  # fallback: equal split
        runs = [[i * W // n, (i + 1) * W // n] for i in range(n)]
    from cutout import ai_alpha
    A = ai_alpha(p)
    frames = []
    for a, b in runs:
        pad = 12
        x0_, x1_ = max(a - pad, 0), min(b + pad, W)
        tile = rgb[:, x0_:x1_]
        frames.append(cut(tile, pockets=("mascot" in p), alpha=None if A is None else A[:, x0_:x1_]))
    mh = max(f.shape[0] for f in frames); mw = max(f.shape[1] for f in frames)
    out = []
    for f, fn in zip(frames, files):
        c = np.zeros((mh, mw, 4), np.uint8)
        x = (mw - f.shape[1]) // 2; y = mh - f.shape[0]
        c[y:y + f.shape[0], x:x + f.shape[1]] = f
        Image.fromarray(c).save(fn); out.append(c)
    return out


def blink_index(t, seed=0.0, period=3.7, dur=.16):
    """Returns 0 (open), 1 (half), 2 (closed) for a natural periodic blink."""
    ph = (t + seed * 1.37) % period
    if ph < dur * .33: return 1
    if ph < dur * .66: return 2
    if ph < dur: return 1
    return 0


# ------------------------------------------------------------ particles
def particles(frame, t, spec, W, H):
    kind = spec.get("kind", "dust"); n = spec.get("n", 30)
    rng = np.random.RandomState(spec.get("seed", 7))
    xs = rng.rand(n); ph = rng.rand(n); sp = .5 + rng.rand(n); sz = rng.rand(n)
    over = frame.copy()
    for i in range(n):
        if kind == "leaves":
            period = 7 / sp[i]
            u = ((t / period) + ph[i]) % 1.0
            x = (xs[i] + .08 * math.sin(t * 1.3 + i)) * W
            y = (u * 1.2 - .1) * H
            ang = (t * 90 * sp[i] + i * 40) % 360
            col = [(42, 105, 196), (30, 80, 170), (40, 150, 220), (30, 60, 140)][i % 4]  # BGR-ish oranges in RGB order below
            col = (col[2], col[1], col[0])
            r = int(8 + sz[i] * 10)
            cv2.ellipse(over, (int(x), int(y)), (r, max(3, r // 2)), ang, 0, 360, col, -1, cv2.LINE_AA)
        elif kind == "dust":
            period = 12 / sp[i]
            u = ((t / period) + ph[i]) % 1.0
            x = (xs[i] + .03 * math.sin(t * .7 + i)) * W
            y = (1.05 - u * 1.1) * H
            r = int(2 + sz[i] * 3)
            cv2.circle(over, (int(x), int(y)), r, (255, 240, 200), -1, cv2.LINE_AA)
        elif kind == "paper":
            period = 6 / sp[i]
            u = ((t / period) + ph[i]) % 1.0
            x = (xs[i] + .1 * math.sin(t * 1.1 + i)) * W; y = (u * 1.2 - .1) * H
            s = int(14 + sz[i] * 16); a = math.radians(t * 120 * sp[i] + i * 30)
            pts = np.array([[math.cos(a + k * math.pi / 2) * s, math.sin(a + k * math.pi / 2) * s * .7] for k in range(4)]) + [x, y]
            cv2.fillConvexPoly(over, pts.astype(np.int32), (245, 240, 228), cv2.LINE_AA)
    a = spec.get("alpha", .85 if kind != "dust" else .45)
    cv2.addWeighted(over, a, frame, 1 - a, 0, dst=frame)


# ------------------------------------------------------------ map route
def route(bg, spec, u, t):
    """Draw a dotted arc from p0 to p1 (fractions of the background) revealed up to u (0..1), pulsing end dots."""
    h, w = bg.shape[:2]
    (x0, y0), (x1, y1) = spec["p0"], spec["p1"]
    lift = spec.get("lift", .18)
    pts = []
    for k in range(121):
        s = k / 120.0
        x = x0 + (x1 - x0) * s; y = y0 + (y1 - y0) * s - lift * math.sin(math.pi * s)
        pts.append((int(x * w), int(y * h)))
    col = spec.get("color", (255, 210, 0))
    upto = int(u * 120)
    for k in range(0, upto, 3):
        cv2.line(bg, pts[k], pts[min(k + 1, 120)], col, max(3, w // 400), cv2.LINE_AA)
    pulse = 1 + .35 * math.sin(t * 6)
    for (px, py), show in ((pts[0], True), (pts[-1], u >= 1)):
        if show:
            cv2.circle(bg, (px, py), int(w * .006 * pulse) + 6, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(bg, (px, py), int(w * .012 * pulse) + 10, col, 3, cv2.LINE_AA)
    if 0 < u < 1:
        cv2.circle(bg, pts[upto], w // 160, (255, 255, 255), -1, cv2.LINE_AA)


def shake_offset(t_local, shakes):
    dx = dy = 0.0
    for (t0, dur, amp) in shakes:
        if t0 <= t_local <= t0 + dur:
            k = 1 - (t_local - t0) / dur
            dx += math.sin(t_local * 83) * amp * k
            dy += math.cos(t_local * 71) * amp * k
    return dx, dy
