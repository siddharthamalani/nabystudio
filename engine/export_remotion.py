#!/usr/bin/env python3
"""Export an episode's shot list + timing + assets for the Remotion engine.

  python3 engine/export_remotion.py episodes/EpN sample_shots.py sample   ->  remotion/public/<ep>_<name>/ + remotion/src/data/<ep>_<name>.json

Every time key in the shot list is resolved to seconds here, so Remotion only sees numbers.
Images are copied (cut-outs as transparent PNG, sprite sheets split into frames, backgrounds + depth maps).
"""
import json, os, shutil, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R, fx

STUDIO = R.STUDIO


def main(ep, shotfile, name, audio=None):
    epname = os.path.basename(os.path.normpath(ep))
    key = "%s_%s" % (epname, name)
    pub = os.path.join(STUDIO, "remotion", "public", key)
    os.makedirs(pub, exist_ok=True)
    m = R.load_shotlist(os.path.join(ep, shotfile))
    cues = R.Cues(ep)
    end = cues.t(getattr(m, "SAMPLE_END", None)) if hasattr(m, "SAMPLE_END") else cues.duration
    extra = []
    if hasattr(m, "CREDITS_SECONDS") and not hasattr(m, "SAMPLE_END"):
        from credits import make as make_credits
        credits = m.CREDITS
        cp = os.path.join(ep, "build", "credits.png"); cw, ch = make_credits(credits, cp)
        vo = cues.duration
        extra = [{"at": vo, "bg": "#122E2E", "cam": [1, 1], "dissolve": .4, "parallax": False,
                  "layers": [{"img": os.path.relpath(cp, STUDIO), "cut": False, "scroll": [1.0, -(ch / cw * .9 * 16 / 9) + .05], "w": .9, "enter": "none", "idle": "none"}]},
                 {"at": vo + m.CREDITS_SECONDS, "bg": ("assets/brand/raw/end_screen_clean.png" if os.path.exists(os.path.join(STUDIO, "assets/brand/raw/end_screen_clean.png")) else "assets/brand/raw/end_screen.png"),
                  "cam": [1, 1.02], "dissolve": .4, "parallax": False,
                  "layers": [{"sheet": "assets/references/mascot/anim/mascot_talk.png", "n": 4, "mode": "talk", "line": "R98", "closed": 0, "mid": 1, "open": 2, "blink": 3,
                              "x": .45, "y": .975, "h": .46, "idle": "bob", "bounce_line": "R98", "shadow": True}],
                  # END-SCREEN TEMPLATE (every episode): subscribe circle left (YouTube subscribe element), Mascot on the desk
                  # facing it, two video-card frames right (YouTube video elements go exactly there).
                  "texts": [{"kind": "pill", "text": "Subscribe to Your Channel", "t0": .3, "x": .5, "y": .08, "size": 50},
                            {"kind": "pill", "text": "Subscribe", "t0": .6, "x": .205, "y": .79, "size": 46, "anim": "pop"},
                            {"kind": "slot", "text": "Watch next", "t0": .8, "x": .755, "y": .36, "w": .34, "h": .3, "size": 40, "anim": "pop"},
                            {"kind": "slot", "text": "More from the series", "t0": 1.0, "x": .755, "y": .76, "w": .34, "h": .3, "size": 40, "anim": "pop"}]}]
        end = vo + m.CREDITS_SECONDS + m.ENDSCREEN_SECONDS
    shots = R.resolve(list(m.SHOTS) + extra, cues, end)
    assets = {}

    def asset(path, kind):
        if path in assets:
            return assets[path]
        base = os.path.relpath(path, STUDIO) if os.path.isabs(path) else path
        stem = base.replace("/", "__").rsplit(".", 1)[0]
        if kind == "bg":
            dst = stem + ".jpg"
            Image.open(os.path.join(STUDIO, base)).convert("RGB").save(os.path.join(pub, dst), quality=92)
            dpath = os.path.join(STUDIO, base.rsplit(".", 1)[0] + ".depth.png")
            if not os.path.exists(dpath):
                import depth as D
                D.depth(os.path.join(STUDIO, base))
            shutil.copy(dpath, os.path.join(pub, stem + ".depth.png"))
            assets[path] = {"src": key + "/" + dst, "depth": key + "/" + stem + ".depth.png"}
        elif kind == "cut":
            arr = R.load_rgba(base, True)
            dst = stem + ".png"; Image.fromarray(arr).save(os.path.join(pub, dst))
            assets[path] = {"src": key + "/" + dst, "w": arr.shape[1], "h": arr.shape[0]}
        elif kind == "raw":
            arr = R.load_rgba(base, False)
            dst = stem + ".png"; Image.fromarray(arr).save(os.path.join(pub, dst))
            assets[path] = {"src": key + "/" + dst, "w": arr.shape[1], "h": arr.shape[0]}
        return assets[path]

    def sheet(path, n):
        k = (path, n)
        if k in assets:
            return assets[k]
        frames = fx.load_sheet(path, n)
        stem = path.replace("/", "__").rsplit(".", 1)[0]
        srcs = []
        for i, f in enumerate(frames):
            dst = "%s_f%02d.png" % (stem, i); Image.fromarray(f).save(os.path.join(pub, dst)); srcs.append(key + "/" + dst)
        assets[k] = {"frames": srcs, "w": frames[0].shape[1], "h": frames[0].shape[0]}
        return assets[k]

    def T(v, s):
        return v if isinstance(v, (int, float)) or v is None else round(cues.t(v) - s["_t"], 3)

    out = []
    for s in shots:
        o = {"start": round(s["_t"], 3), "dur": round(s["_dur"], 3), "cam": s.get("cam", [1, 1.06, [0, 0], [0, 0]]),
             "trans": s.get("trans", "dissolve" if s.get("dissolve", .25) > 0 else "cut"), "transDur": s.get("dissolve", .25),
             "particles": s.get("particles"), "parallax": s.get("parallax", True)}
        if s["bg"].startswith("#"):
            o["bgColor"] = s["bg"]
        else:
            o["bg"] = asset(s["bg"], "bg")
        if s.get("route"):
            r = dict(s["route"]); r["t0"] = T(r.get("t0", 0), s); o["route"] = r
        if s.get("fg") and os.path.exists(os.path.join(STUDIO, s["fg"])):   # foreground occlusion layer painted to match the background (drawn above characters)
            fstem = s["fg"].replace("/", "__").rsplit(".", 1)[0] + ".png"
            Image.open(os.path.join(STUDIO, s["fg"])).convert("RGBA").save(os.path.join(pub, fstem)); o["fg"] = {"src": key + "/" + fstem}
            o["parallax"] = False
        if s.get("globe"):
            g = dict(s["globe"]); g["t0"] = T(g.get("t0", 0), s)
            gstem = g["tex"].replace("/", "__").rsplit(".", 1)[0] + ".jpg"
            if not os.path.exists(os.path.join(pub, gstem)):
                Image.open(os.path.join(STUDIO, g["tex"])).convert("RGB").save(os.path.join(pub, gstem), quality=93)
            g["tex"] = {"src": key + "/" + gstem}; o["globe"] = g
        if s.get("shake"):
            o["shake"] = [[T(a, s), d, mg] for a, d, mg in s["shake"]]
        layers = []
        for L in s.get("layers", []):
            l = {k: v for k, v in L.items() if k not in ("img", "sheet", "talk", "gesture")}
            l["t0"] = T(L.get("t0", 0), s); l["t1"] = T(L.get("t1"), s)
            if L.get("sheet") and not os.path.exists(os.path.join(STUDIO, L["sheet"])):
                print("  (sheet missing, using still):", L["sheet"]); L = dict(L); L.pop("sheet")
                if L.get("mode") in ("loop", "blink"): L["mode"] = None
            if L.get("face"):
                import face as FC
                F = L["face"]; master, patches = FC.build(F)
                stem = F["master"].replace("/", "__").rsplit(".", 1)[0] + "_face"
                ys_, xs_ = np.where(master[:, :, 3] > 20); cy0, cy1, cx0, cx1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
                Image.fromarray(master[cy0:cy1, cx0:cx1]).save(os.path.join(pub, stem + "_master.png"))
                pl = {}
                for nm, (arr, px_, py_) in patches.items():
                    fn = "%s_%s.png" % (stem, nm); Image.fromarray(arr).save(os.path.join(pub, fn))
                    pl[nm] = {"src": key + "/" + fn, "x": px_ - int(cx0), "y": py_ - int(cy0), "w": arr.shape[1], "h": arr.shape[0]}
                l["face"] = {"master": {"src": key + "/" + stem + "_master.png", "w": int(cx1 - cx0), "h": int(cy1 - cy0)}, "patches": pl,
                             "expr": [[T(t_, s), e] for t_, e in F.get("expr", [[0, "neutral"]])]}
                if F.get("line"):
                    sp = cues.line_span(F["line"])
                    if sp: l["lineSpan"] = [round(sp[0] - s["_t"], 3), round(sp[1] - s["_t"], 3)]
                    lsf = os.path.join(ep, "build", "lipsync", F["line"] + ".json")
                    if os.path.exists(lsf): l["mouth"] = [[round(t_ - s["_t"], 3), sh] for t_, sh in json.load(open(lsf))]
            elif L.get("rig"):
                import rig as RG
                Rg = L["rig"]; body, heads, geo = RG.build(Rg)
                stem = Rg["body"].replace("/", "__").rsplit(".", 1)[0]
                Image.fromarray(body).save(os.path.join(pub, stem + "_body.png"))
                hs = {}
                for ex, st in heads.items():
                    hs[ex] = {}
                    for k, arr in st.items():
                        fn = "%s_head_%s_%s.png" % (stem, ex, k); Image.fromarray(arr).save(os.path.join(pub, fn)); hs[ex][k] = key + "/" + fn
                any_head = next(iter(next(iter(heads.values())).values()))
                l["rig"] = {"body": {"src": key + "/" + stem + "_body.png", "w": body.shape[1], "h": body.shape[0]}, "heads": hs,
                            "hw": any_head.shape[1], "hh": any_head.shape[0], **geo,
                            "expr": [[T(t_, s), e] for t_, e in Rg.get("expr", [[0, next(iter(heads))]])]}
                if Rg.get("line"):
                    sp = cues.line_span(Rg["line"])
                    if sp: l["lineSpan"] = [round(sp[0] - s["_t"], 3), round(sp[1] - s["_t"], 3)]
            elif L.get("poses"):
                # lip-synced talking poses: P poses x (closed, mid, open). Pose changes only on this character's own words.
                import poses as PZ
                P = L["poses"]; frames = PZ.build(P["frames"])
                stem = P["frames"][0][0].replace("/", "__").rsplit(".", 1)[0] + "_pz"
                srcs = []
                for i, f in enumerate(frames):
                    dst = "%s_%02d.png" % (stem, i); Image.fromarray(f).save(os.path.join(pub, dst)); srcs.append(key + "/" + dst)
                l["sprite"] = {"frames": srcs, "w": frames[0].shape[1], "h": frames[0].shape[0]}
                l["mode"] = "ptalk"; l["nPose"] = len(P["frames"]); l["nMouth"] = max(len(t) for t in P["frames"])
                sched = [[0.0, 0]]
                lines = P.get("lines") or [P.get("line")]
                for lid in [x for x in lines if x]:
                    ws = [w for c in cues.c if c.get("type") == "phrase" and c.get("line") == lid for w in c["words"]]
                    if not ws: continue
                    nxt, last = 1, None
                    for w in ws:
                        t = w["s"] - s["_t"]
                        if last is None or t - last >= P.get("every", 2.4):
                            sched.append([round(t - .08, 3), nxt % l["nPose"] or (1 if l["nPose"] > 1 else 0)]); last = t; nxt += 1
                    sched.append([round(ws[-1]["e"] - s["_t"] + .45, 3), 0])
                    sp = cues.line_span(lid)
                    if sp: l["lineSpan"] = [round(sp[0] - s["_t"], 3), round(sp[1] - s["_t"], 3)]
                l["poseAt"] = sorted(sched)
            elif L.get("gesture") or L.get("talk"):
                # gesture frames (pauses) + talk frames closed/mid/open (while speaking), one sprite
                frames, gN = [], 0
                if L.get("gesture") and os.path.exists(os.path.join(STUDIO, L["gesture"])):
                    frames = list(fx.load_sheet(L["gesture"], L.get("gn", 3))); gN = len(frames)
                tk = L.get("talk") or {}
                for kk in ("closed", "mid", "open"):
                    pth = tk.get(kk) or (tk.get("open") if kk == "mid" else None) or L.get("img")
                    if pth and os.path.exists(os.path.join(STUDIO, pth)):
                        frames.append(R.load_rgba(pth, True))
                Hh = max(f.shape[0] for f in frames)
                norm_ = []
                for f in frames:  # same character height in every frame
                    import cv2
                    sc = Hh / f.shape[0]; f2 = cv2.resize(f, (int(f.shape[1] * sc), Hh), interpolation=cv2.INTER_AREA)
                    norm_.append(f2)
                mw = max(f.shape[1] for f in norm_)
                stem = (L.get("gesture") or L.get("img")).replace("/", "__").rsplit(".", 1)[0] + "_gt"
                srcs = []
                for i, f in enumerate(norm_):
                    c = np.zeros((Hh, mw, 4), np.uint8); x0 = (mw - f.shape[1]) // 2; c[:, x0:x0 + f.shape[1]] = f
                    dst = "%s_%02d.png" % (stem, i); Image.fromarray(c).save(os.path.join(pub, dst)); srcs.append(key + "/" + dst)
                l["sprite"] = {"frames": srcs, "w": mw, "h": Hh}
                l["mode"] = "gtalk"; l["gN"] = gN; l["tc"], l["tm"], l["to"] = gN, gN + 1, gN + 2
                if tk.get("line"):
                    sp = cues.line_span(tk["line"])
                    if sp: l["lineSpan"] = [round(sp[0] - s["_t"], 3), round(sp[1] - s["_t"], 3)]
            elif L.get("sheet"):
                l["sprite"] = sheet(L["sheet"], L["n"])
            else:
                l["image"] = asset(L["img"], "cut" if L.get("cut", True) else "raw")
            if L.get("line") or L.get("bounce_line"):
                sp = cues.line_span(L.get("line") or L.get("bounce_line"))
                if sp: l["lineSpan"] = [round(sp[0] - s["_t"], 3), round(sp[1] - s["_t"], 3)]
            # Rhubarb mouth shapes for this layer's spoken line(s), shot-relative
            for lid_ in [x for x in ([L.get("line"), (L.get("talk") or {}).get("line")] + list((L.get("poses") or {}).get("lines") or [(L.get("poses") or {}).get("line")])) if x]:
                lsf = os.path.join(ep, "build", "lipsync", lid_ + ".json")
                if os.path.exists(lsf):
                    l.setdefault("mouth", [])
                    l["mouth"] += [[round(t_ - s["_t"], 3), sh] for t_, sh in json.load(open(lsf))]
            if L.get("move"):
                mv = dict(L["move"]); mv["t0"] = T(mv.get("t0", 0), s); mv["t1"] = T(mv.get("t1", s["_dur"]), s); l["move"] = mv
            layers.append(l)
        o["layers"] = layers
        if s.get("ink"):
            o["ink"] = [dict(p, t0=T(p.get("t0", 0), s)) for p in s["ink"]]
        texts = []
        for X in s.get("texts", []):
            x = dict(X); x["t0"] = T(X.get("t0", 0), s); x["t1"] = T(X.get("t1"), s); texts.append(x)
        o["texts"] = texts
        out.append(o)

    # voice loudness per frame (mouth flaps), from the episode voice track
    env = R.Envelope(os.path.join(ep, "build", "vo_track.wav")).env
    n = int(end * R.FPS) + 1
    envl = [round(float(v), 3) for v in env[:n]]
    if audio:
        shutil.copy(audio, os.path.join(pub, "audio.wav"))
    for f in ("LuckiestGuy-Regular.ttf", "PermanentMarker-Regular.ttf"):
        shutil.copy(os.path.join(STUDIO, "fonts", f), os.path.join(STUDIO, "remotion", "public", f))
    data = {"fps": R.FPS, "duration": round(end, 3), "shots": out, "env": envl, "audio": key + "/audio.wav" if audio else None}
    os.makedirs(os.path.join(STUDIO, "remotion", "src", "data"), exist_ok=True)
    json.dump(data, open(os.path.join(STUDIO, "remotion", "src", "data", key + ".json"), "w"))
    print("exported", key, "%d shots, %.1f s" % (len(out), end))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
