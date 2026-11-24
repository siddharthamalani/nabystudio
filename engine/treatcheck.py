#!/usr/bin/env python3
"""Treatment check (before the script gate). The brand stays fixed; the story must not repeat.
treatment.md must contain:
  1. "## Benchmark": 1-2 reference works, what to learn, what not to copy.
  2. "## Structures": three candidate structures and the chosen one ("Chosen:").
  3. "## Not a repeat": a table comparing this episode with the last two on six STORY aspects
     (opening, structure, signature moment, camera path, music shape, ending); last column yes/no.
     At least 4 of 6 must differ. The look is never one of them: it is locked.
  4. "## Brand lock": the line "Brand lock: kept" (house art style, Mascot in scene, colours, fonts, series card,
     opening and ending, narrator voice, music library unchanged).
  5. Optional "## Guest set piece": one line "style: <slug> · seconds: <n>". The slug must be in
     studio_schedule.json guest_styles, n <= 15, and Mascot opens and closes it in house style (say so in the section).
  python3 engine/treatcheck.py episodes/EpN"""
import json, os, re, sys
STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASPECTS = ["opening", "structure", "signature", "camera", "music", "ending"]


def section(md, name):
    m = re.search(r"^##\s*" + re.escape(name) + r".*?$(.*?)(?=^##\s|\Z)", md, re.M | re.S | re.I)
    return m.group(1) if m else None


def check(ep):
    md = open(os.path.join(ep, "treatment.md"), encoding="utf-8").read()
    sched = json.load(open(os.path.join(STUDIO, "studio_schedule.json")))
    errs = []
    b = section(md, "Benchmark")
    if not b or len(b.strip()) < 40: errs.append("Benchmark missing (1-2 reference works, learn / don't copy)")
    s = section(md, "Structures")
    if not s or "chosen" not in s.lower(): errs.append("Structures: need three candidates and a 'Chosen:' line")
    r = section(md, "Not a repeat")
    if not r: errs.append("'Not a repeat' table missing")
    else:
        rows = [l for l in r.splitlines() if l.strip().startswith("|") and not set(l) <= set("|-: ")]
        got = {a: row for row in rows for a in ASPECTS if a in row.lower().split("|")[1]}
        miss = [a for a in ASPECTS if a not in got]
        if miss: errs.append("'Not a repeat' rows missing: " + ", ".join(miss))
        differ = sum(1 for row in got.values() if row.rstrip(" |").split("|")[-1].strip().lower().startswith("y"))
        if differ < 4: errs.append("only %d of 6 story aspects differ from the last two episodes (need 4)" % differ)
    bl = section(md, "Brand lock")
    if not bl or "brand lock: kept" not in bl.lower(): errs.append("'Brand lock: kept' line missing")
    g = section(md, "Guest set piece")
    if g and g.strip():
        m = re.search(r"style:\s*([\w-]+).*?seconds:\s*([\d.]+)", g, re.I | re.S)
        if not m: errs.append("Guest set piece: write 'style: <slug> · seconds: <n>'")
        else:
            slug, sec = m.group(1), float(m.group(2))
            if slug not in sched.get("guest_styles", []): errs.append("guest style '%s' isn't on the approved list (studio_schedule.json guest_styles)" % slug)
            if sec > 15: errs.append("guest set piece is %.0f s (max 15)" % sec)
            if "mascot" not in g.lower(): errs.append("guest set piece must be opened and closed by Mascot in house style")
    for e in errs: print("✗", e)
    print("treatcheck %s: %s" % (ep, "OK" if not errs else "%d problems" % len(errs)))
    return len(errs)


if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(0)
    sys.exit(1 if check(sys.argv[1]) else 0)
