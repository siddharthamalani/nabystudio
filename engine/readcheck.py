#!/usr/bin/env python3
"""Reading-time check: every on-screen text must stay up long enough to be read.
Need: letters / 15 + 1.5 s after it lands (titles and series cards at least 4 s); a typed text also needs its typing time.
Texts marked "pass": True (fine print not meant to be read in full) are skipped.
  python3 engine/readcheck.py Ep14_full        # reads remotion/src/data/<key>.json; exits 1 on any failure"""
import json, os, sys
STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def need(t):
    txt = (t.get("text") or "") + " " + (t.get("src") or "")
    n = sum(c.isalnum() for c in txt)
    base = n / 15 + 1.5
    if t.get("kind") in ("title", "big") or "EPISODE" in txt: base = max(base, 4.0)
    return base + (t.get("dur", 0) if t.get("anim") == "type" else 0)


def check(key):
    d = json.load(open(os.path.join(STUDIO, "remotion", "src", "data", key + ".json")))
    bad = []
    for i, s in enumerate(d["shots"]):
        for t in s.get("texts") or []:
            if t.get("pass") or not t.get("text"): continue
            t0 = t.get("t0") or 0
            end = t.get("t1") if t.get("t1") is not None else s["dur"]
            shown, req = end - t0, need(t)
            if shown + 0.05 < req:
                bad.append((i, s["start"] + t0, t["text"][:40], shown, req))
    for i, at, txt, shown, req in bad:
        print("shot %2d @%6.1fs  %-40s up %.1fs, needs %.1fs" % (i, at, txt, shown, req))
    print("readcheck %s: %d texts too short" % (key, len(bad)))
    return len(bad)


if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(0)
    sys.exit(1 if check(sys.argv[1]) else 0)
