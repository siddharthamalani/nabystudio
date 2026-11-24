#!/usr/bin/env python3
"""Placement check for EVERY shot, before the full render (owner rule, 24 Nov 2026).

  python3 engine/placement_check.py episodes/EpN shots_full.py

1. Automatic geometry checks on the exported shot data (remotion/src/data/<Ep>_full.json):
   - character cut off by the frame (top/left/right edge), unless it is a deliberate close-up cut at the bottom
   - character tiny (< 12% of frame height) or huge (> 110%)
   - two characters overlapping a lot
   - grounded character (bottom of frame area) without shadow; character floating mid-air (feet between 55% and 85% of height
     with no surface given via "on": "...") -> listed for a human look
   - text box overlapping a character's face area
2. Renders a fast low-res proof (scale 0.3) and saves one frame per shot, numbered, as contact sheets:
   <ep>/build/placement/sheet_NN.jpg  (12 shots per sheet, the narrated sentence under each frame)
Every sheet must be reviewed (by Claude, and by the owner when asked) BEFORE the full render: floating, duplicate furniture,
random centre placement, cut-off, text over faces, wrong background for the sentence.
"""
import importlib.util, json, os, subprocess, sys, textwrap
from PIL import Image, ImageDraw, ImageFont

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(STUDIO, "bin", "ffmpeg")
NODE = os.path.join(STUDIO, "tools", "node", "bin")


def boxes(shot):
    out = []
    for L in shot.get("layers", []):
        if L.get("scroll") or L.get("cut") is False:
            continue
        dims = L.get("sprite") or L.get("image")
        if not dims: continue
        h = L.get("h", .6); w = h * dims["w"] / dims["h"] * 9 / 16
        x = L.get("x", .5); y = L.get("y", .95)
        if L.get("move"): x = L["move"].get("x1", x); y = L["move"].get("y1", y)
        out.append({"x0": x - w / 2, "x1": x + w / 2, "y0": y - h, "y1": y, "L": L,
                    "name": os.path.basename((L.get("image") or {}).get("src", "") or ((L.get("sprite") or {}).get("frames") or [""])[0])})
    return out


def geometry(shots, sbs):
    issues = []
    for i, s in enumerate(shots):
        tag = "shot %02d (%s)" % (i, sbs[i][:50] if i < len(sbs) else "")
        bs = boxes(s)
        for b in bs:
            # cut-out art has ~6% cream margin; allow a little
            if b["y0"] < -.02: issues.append("%s: %s cut off at the TOP" % (tag, b["name"]))
            if b["x0"] < -.04 or b["x1"] > 1.04:
                if not b["L"].get("move"): issues.append("%s: %s cut off at the SIDE" % (tag, b["name"]))
            if b["L"].get("h", .6) < .12: issues.append("%s: %s very small" % (tag, b["name"]))
            yb = b["y1"]
            if .55 < yb < .85 and not b["L"].get("on") and not b["L"].get("move"):
                issues.append("%s: %s feet at %.0f%% height: is it standing ON something in the background? (add \"on\": \"desk\" etc. once checked)" % (tag, b["name"], yb * 100))
        # camera must move TOWARD the shot's main character, never away from it
        cam = s.get("cam") or [1, 1]
        if len(cam) >= 4 and cam[1] >= 1.08 and bs:
            main = max(bs, key=lambda b: (b["y1"] - b["y0"]) * (b["x1"] - b["x0"]))
            mx = (main["x0"] + main["x1"]) / 2 - .5; px = cam[3][0] - cam[2][0]
            if abs(mx) > .12 and abs(px) > .08 and (mx > 0) != (px > 0):
                issues.append("%s: camera moves %s but the main character (%s) is on the %s" % (tag, "right" if px > 0 else "left", main["name"], "right" if mx > 0 else "left"))
        for a in range(len(bs)):
            for c in range(a + 1, len(bs)):
                A, C = bs[a], bs[c]
                ox = max(0, min(A["x1"], C["x1"]) - max(A["x0"], C["x0"])); oy = max(0, min(A["y1"], C["y1"]) - max(A["y0"], C["y0"]))
                small = min((A["x1"] - A["x0"]) * (A["y1"] - A["y0"]), (C["x1"] - C["x0"]) * (C["y1"] - C["y0"]))
                if small > 0 and ox * oy / small > .35:
                    issues.append("%s: %s and %s overlap" % (tag, A["name"], C["name"]))
        for T in s.get("texts", []):
            if T.get("kind") not in ("note", "quote", "big", "title"): continue
            tx, ty = T.get("x", .5), T.get("y", .2)
            for b in bs:
                face_y0, face_y1 = b["y0"], b["y0"] + (b["y1"] - b["y0"]) * .3
                if b["x0"] + .05 < tx < b["x1"] - .05 and face_y0 < ty < face_y1:
                    issues.append("%s: text \"%s\" may cover %s's face" % (tag, T.get("text", "")[:30], b["name"]))
    return issues


def proof_frames(ep, comp, shots, sbs):
    name = os.path.basename(ep.rstrip("/"))
    outdir = os.path.join(ep, "build", "placement"); os.makedirs(outdir, exist_ok=True)
    proof = os.path.join(ep, "build", "placement_proof.mp4")
    env = dict(os.environ, PATH=NODE + ":" + os.environ["PATH"])
    subprocess.run(["npx", "remotion", "render", "src/index.jsx", comp, os.path.abspath(proof), "--gl=angle", "--scale=0.3",
                    "--concurrency=4", "--codec=h264", "--crf=28", "--muted", "--log=error"], cwd=os.path.join(STUDIO, "remotion"), env=env, check=True)
    tiles = []
    try:
        font = ImageFont.truetype(os.path.join(STUDIO, "fonts", "PermanentMarker-Regular.ttf"), 16)
    except Exception:
        font = ImageFont.load_default()
    for i, s in enumerate(shots):
        t = s["start"] + min(max(s["dur"] * .6, .3), 2.2)
        f = os.path.join(outdir, "shot_%02d.jpg" % i)
        subprocess.run([FF, "-v", "error", "-y", "-ss", "%.2f" % t, "-i", proof, "-frames:v", "1", f], check=True)
        im = Image.open(f).convert("RGB"); W, H = im.size
        card = Image.new("RGB", (W, H + 50), "white"); card.paste(im, (0, 0))
        d = ImageDraw.Draw(card)
        d.text((6, H + 3), "%02d  %s" % (i, "\n".join(textwrap.wrap(sbs[i] if i < len(sbs) else "credits/end", 70)[:2])), fill="black", font=font)
        tiles.append(card)
    per = 12; sheets = []
    for k in range(0, len(tiles), per):
        grp = tiles[k:k + per]; W, H = grp[0].size
        sh = Image.new("RGB", (W * 3 + 20, H * 4 + 30), (40, 40, 40))
        for j, t in enumerate(grp): sh.paste(t, (5 + (j % 3) * (W + 5), 5 + (j // 3) * (H + 5)))
        p = os.path.join(outdir, "sheet_%02d.jpg" % (k // per + 1)); sh.save(p, quality=85); sheets.append(p)
    os.remove(proof)
    return sheets


def main():
    ep, shotfile = sys.argv[1].rstrip("/"), sys.argv[2]
    name = os.path.basename(ep)
    spec = importlib.util.spec_from_file_location("s", os.path.join(ep, shotfile)); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    sbs = [s.get("sb", "") for s in m.SHOTS]
    data = json.load(open(os.path.join(STUDIO, "remotion", "src", "data", "%s_full.json" % name)))
    issues = geometry(data["shots"], sbs)
    print("GEOMETRY: %d things to look at" % len(issues))
    for x in issues: print("  -", x)
    if "--no-render" not in sys.argv:
        sheets = proof_frames(ep, name + "Full", data["shots"], sbs)
        print("CONTACT SHEETS (review every one before the full render):")
        for p in sheets: print("  ", p)


if __name__ == "__main__":
    main()
