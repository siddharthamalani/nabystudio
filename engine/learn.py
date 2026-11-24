#!/usr/bin/env python3
"""Learning memory: every piece of feedback becomes a lesson, every lesson becomes a rule, and the rules are fed back into the
stages of every future video. Repeats are caught and escalated.

Commitment (enforced by the code, not just written down):
  1. Every reviewer note is recorded (add). Nothing is fixed silently.
  2. A video can't be approved as final while it has open notes (run.py checks `open_count`).
  3. Every closed note names its rule and, where possible, the automated check that now enforces it.
  4. Before each stage, the autopilot reads that stage's rules (brief). Mistakes aren't repeated because nobody remembered.
  5. A note that matches an existing rule is a REPEAT: the rule failed, so it must be upgraded to an automated check.

  python3 engine/learn.py add EpN <stage> "what went wrong"           # stages: topic script voice storyboard art animation audio render shorts packaging ops
  python3 engine/learn.py close <id> "the rule now" [--check engine/x.py] [--cause "root cause"]
  python3 engine/learn.py brief <stage>                                 # rules + recent lessons for a stage (read before working on it)
  python3 engine/learn.py open [EpN]                                    # open notes
  python3 engine/learn.py stats                                         # lessons per stage, repeat rate, % enforced by checks
Memory lives in memory/lessons.jsonl (one lesson per line, append-only) and memory/RULES.md (rebuilt on every change)."""
import datetime as dt, difflib, json, os, re, sys

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(STUDIO, "memory"); LOG = os.path.join(MEM, "lessons.jsonl")
STAGES = ["topic", "script", "voice", "storyboard", "art", "animation", "audio", "render", "shorts", "packaging", "ops"]


def load():
    if not os.path.exists(LOG): return []
    return [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]


def save(items):
    os.makedirs(MEM, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")
    rules_md(items)


STOP = {"with", "that", "this", "from", "into", "were", "they", "their", "have", "been", "when", "next", "only", "every", "never",
        "owner", "review", "reviewer", "note", "notes", "director", "autopilot", "episode", "drive"}   # who/where a note came from is not what it is about


def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4: return w[: -len(suf)]
    return w


# concept groups: different words for the same kind of mistake count as the same idea
CONCEPTS = {
    "#furniture": "furniture chair armchair sofa couch bench stool cushion seat seated sitting sits desk table",
    "#sync": "sync lipsync mouth mouths lips beak speaking talking talk",
    "#pause": "pause pauses pacing rushed rushing fast slow broken breaking choppy patchy chopped",
    "#placement": "float floating floated placement placed position positioned random size big small proportion scale",
    "#cutout": "fringe fringes halo edge edges cutout cut-out gaps",
    "#crop": "crop cropped cut zoom zoomed frame",
    "#text": "text label labels caption captions clipped font",
    "#eyes": "eye eyes blind pupil pupils blink",
}
CMAP = {w: c for c, ws in CONCEPTS.items() for w in ws.split()}


def words(t):
    out = set()
    t = re.sub(r"\bep\d+\w*", " ", t.lower())
    for w in re.findall(r"[a-z][a-z-]{2,}", t):
        if w in STOP: continue
        if w in CMAP: out.add(CMAP[w])
        elif len(w) >= 4: out.add(stem(w))
    return out


def similar(a, b):
    """overlap of meaning: shared concept groups count double, shared plain words once"""
    wa, wb = words(a), words(b)
    shared = wa & wb
    score = sum(2 if w.startswith("#") else 1 for w in shared)
    return score / max(1.0, min(len(wa), len(wb)) ** .5 * 2)


def add(ep, stage, note):
    if stage not in STAGES: raise SystemExit("stage must be one of: " + " ".join(STAGES))
    items = load(); nid = "L%03d" % (len(items) + 1)
    scored = sorted(((similar(note, it["note"] + " " + it["rule"]), it) for it in items
                     if it.get("rule") and it["stage"] == stage), key=lambda p: -p[0])
    rep = [it for sc, it in scored[:1] if sc > .3]
    it = {"id": nid, "ep": ep, "stage": stage, "note": note, "status": "open", "added": dt.date.today().isoformat()}
    if rep:
        it["repeat_of"] = [r["id"] for r in rep]
        print("REPEAT: this looks like %s (rule: %s). That rule didn't hold: close this note with an automated check (--check)."
              % (", ".join(r["id"] for r in rep), rep[0]["rule"]))
    items.append(it); save(items); print("recorded", nid)


def close(nid, rule, check=None, cause=None):
    items = load(); it = next((x for x in items if x["id"] == nid), None)
    if not it: raise SystemExit("no lesson " + nid)
    if it.get("repeat_of") and not check:
        raise SystemExit("%s repeats %s: a written rule wasn't enough. Close it with --check <the script that now enforces it>." % (nid, it["repeat_of"]))
    it.update({"status": "closed", "rule": rule, "check": check, "cause": cause, "closed": dt.date.today().isoformat()})
    save(items); print("closed", nid)


def brief(stage):
    items = [x for x in load() if x["stage"] == stage and x.get("rule")]
    if not items: print("No lessons for '%s' yet." % stage); return
    print("RULES FOR %s (from %d past lessons; follow every one):" % (stage.upper(), len(items)))
    for x in items:
        flag = " [enforced by %s]" % x["check"] if x.get("check") else ""
        rep = " (repeated before: treat as critical)" if x.get("repeat_of") else ""
        print("- %s%s%s  ← %s %s" % (x["rule"], flag, rep, x["ep"], x["id"]))


def open_count(ep=None):
    return len([x for x in load() if x["status"] == "open" and (ep is None or x["ep"] == ep)])


def show_open(ep=None):
    for x in load():
        if x["status"] == "open" and (ep is None or x["ep"] == ep):
            print("%s [%s/%s] %s%s" % (x["id"], x["ep"], x["stage"], x["note"], "  REPEAT of %s" % x["repeat_of"] if x.get("repeat_of") else ""))


def stats():
    items = load(); closed = [x for x in items if x["status"] == "closed"]
    print("lessons: %d (open %d) · repeats: %d · closed with an automated check: %d%%" % (
        len(items), len(items) - len(closed), len([x for x in items if x.get("repeat_of")]),
        round(100 * len([x for x in closed if x.get("check")]) / max(1, len(closed)))))
    for s in STAGES:
        n = len([x for x in items if x["stage"] == s])
        if n: print("  %-11s %d" % (s, n))


def rules_md(items):
    L = ["# Rules learned (auto-built by engine/learn.py from memory/lessons.jsonl; don't edit by hand)", ""]
    for s in STAGES:
        rs = [x for x in items if x["stage"] == s and x.get("rule")]
        if not rs: continue
        L.append("## " + s.capitalize())
        for x in rs:
            L.append("- %s%s  _(%s, %s%s)_" % (x["rule"], " · check: `%s`" % x["check"] if x.get("check") else "", x["ep"], x["id"],
                                              ", repeat" if x.get("repeat_of") else ""))
        L.append("")
    opn = [x for x in items if x["status"] == "open"]
    if opn: L += ["## Open notes"] + ["- [%s/%s] %s" % (x["ep"], x["stage"], x["note"]) for x in opn]
    open(os.path.join(MEM, "RULES.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(0)
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    if a[0] == "add": add(a[1], a[2], a[3])
    elif a[0] == "close": close(a[1], a[2], opt("--check"), opt("--cause"))
    elif a[0] == "brief": brief(a[1])
    elif a[0] == "open": show_open(a[1] if len(a) > 1 else None)
    elif a[0] == "stats": stats()
    elif a[0] == "count": print(open_count(a[1] if len(a) > 1 else None))
