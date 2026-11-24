#!/usr/bin/env python3
"""STUDIO studio pipeline runner: knows every episode's stage, runs the automatic steps, stops at the owner's gates.

  python3 engine/run.py status                 # every episode, its stage, and what happens next
  python3 engine/run.py next                   # the next production slot from studio_schedule.json
  python3 engine/run.py new EpN "Working title" [format]  # start a video for the next slot (format: formats/<name>.json)
  python3 engine/run.py approve EpN <gate>     # record an owner decision: script | voice_budget | animatic | final
  python3 engine/run.py morning                # scheduled job (production days): retention, handover, status, notification

Stages (episodes/EpN/status.txt):
  planned → script_draft → [gate: script] → script_locked → voice_priced → [gate: voice_budget] → producing → animatic
  → [gate: animatic] → rendering → ready_for_review → [gate: final] → approved
Creative stages (script, storyboard, art briefs, shot lists, notes) are done in a Claude Code session; this runner never
spends voice credits, never publishes."""
import datetime as dt, json, os, subprocess, sys

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(STUDIO, "episodes")
SCHED = json.load(open(os.path.join(STUDIO, "studio_schedule.json")))
ORDER = ["planned", "script_draft", "script_locked", "voice_priced", "producing", "animatic", "rendering",
         "ready_for_review", "approved"]
GATES = {"script": ("script_draft", "script_locked"), "voice_budget": ("voice_priced", "producing"),
         "animatic": ("animatic", "rendering"), "final": ("ready_for_review", "approved")}
NEXT = {"planned": "Claude session: pick topic from topics/backlog.md, research + claim ledger, script + treatment",
        "script_draft": "Autopilot: run.py autogate EpN script (auto when all checks pass; owner can still send notes)",
        "script_locked": "Autopilot: voice lines + price; ≤ 5,000 credits → queue voices in the same run",
        "voice_priced": "OWNER: OK the credit total  →  run.py approve EpN voice_budget",
        "producing": "Autopilot: voices (tts.py generate), checks, art, shots, placement checks, animatic",
        "animatic": "OWNER: review the animatic  →  run.py approve EpN animatic",
        "rendering": "Render section by section, finish.py, thumbnails, publishing pack, retro",
        "ready_for_review": "OWNER: watch the final cut  →  run.py approve EpN final",
        "approved": "Done: the finished files are in episodes/EpN/out/. Publish them yourself."}


def episodes():
    out = []
    if not os.path.isdir(EP_DIR): return []   # fresh studio: no videos yet
    for d in sorted(os.listdir(EP_DIR), key=lambda s: int("".join(c for c in s if c.isdigit()) or 0)):
        p = os.path.join(EP_DIR, d, "status.txt")
        if d.startswith("Ep") and d[2:].isdigit() and os.path.exists(p):
            out.append((d, open(p).read().strip()))
    return out


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def batch_day(today=None):
    """the next batch day (today counts) from studio_schedule.json batch.day"""
    today = today or dt.date.today(); bd = DAYS.index(SCHED.get("batch", {}).get("day", "Thursday"))
    return today + dt.timedelta(days=(bd - today.weekday()) % 7)


def missing_posts(today=None):
    """posting dates in the batch window (batch day +1 … +window_days) that have no episode yet"""
    b = SCHED.get("batch", {}); bd = batch_day(today)
    have = {json.load(open(os.path.join(EP_DIR, e, "slot.json")))["post_date"] for e, _ in episodes() if os.path.exists(os.path.join(EP_DIR, e, "slot.json"))}
    out = []
    for k in range(1, b.get("window_days", 9) + 1):
        d = bd + dt.timedelta(days=k)
        if DAYS[d.weekday()] in b.get("post_days", ["Tuesday", "Thursday", "Saturday"]) and d.isoformat() not in have: out.append(d)
    return out


def next_slot(today=None):
    """the next batch: its day and the first posting date it still has to cover"""
    bd = batch_day(today); m = missing_posts(today)
    post = m[0] if m else bd + dt.timedelta(days=2)
    return {"make_date": bd.isoformat(), "make": DAYS[bd.weekday()] + " (weekly batch)", "post": DAYS[post.weekday()], "post_date": post.isoformat()}


def plan():
    bd = batch_day(); m = missing_posts()
    print("Batch day: %s %s. Posting dates still without an episode: %s" % (DAYS[bd.weekday()], bd, ", ".join("%s %s" % (DAYS[d.weekday()], d) for d in m) or "none"))
    print("Create one per date (earliest first): python3 engine/run.py new EpN \"<title>\" [format] --post YYYY-MM-DD")


def status():
    rows = episodes()
    print("Episodes:")
    for ep, st in rows:
        print("  %-6s %-16s next: %s" % (ep, st, NEXT.get(st, "?")))
    bd = batch_day(); m = missing_posts()
    print("\nNext batch: %s %s · posting dates without an episode: %s" % (DAYS[bd.weekday()], bd, ", ".join("%s %s" % (DAYS[d.weekday()][:3], d) for d in m) or "none"))


def git_commit(msg):
    subprocess.run(["git", "-C", STUDIO, "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", STUDIO, "commit", "-q", "-m", msg + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"], capture_output=True)


def approve(ep, gate):
    p = os.path.join(EP_DIR, ep, "status.txt"); cur = open(p).read().strip()
    frm, to = GATES[gate]
    if gate == "final":   # feedback-loop commitment: no final approval while reviewer notes are still open
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import learn
        n = learn.open_count(ep)
        if n: raise SystemExit("%s has %d open review note(s): close each with a rule (python3 engine/learn.py open %s) before final approval." % (ep, n, ep))
    if gate == "script":   # brand lock + story variety + guest-style limits (engine/treatcheck.py)
        import subprocess
        if subprocess.call([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "treatcheck.py"), os.path.join(EP_DIR, ep)]):
            raise SystemExit("%s: treatment.md fails treatcheck; fix it before the script gate." % ep)
    if cur != frm:
        raise SystemExit("%s is at '%s'; the %s gate applies at '%s'." % (ep, cur, gate, frm))
    open(p, "w").write(to + "\n")
    with open(os.path.join(EP_DIR, ep, "log.md"), "a") as lg:
        lg.write("- %s · OWNER approved gate '%s' → %s\n" % (dt.date.today().isoformat(), gate, to))
    git_commit("%s: owner approved %s" % (ep, gate)); print(ep, "→", to)


AUTO_CHECKS = {"script": ["treatcheck.py", "ledgercheck.py"]}


def autogate(ep, gate):
    """A gate the owner made automatic (studio_schedule.json auto_gates): approve only if every check passes and no notes are open."""
    if gate not in SCHED.get("auto_gates", []): raise SystemExit("%s is an owner gate; it isn't automatic." % gate)
    p = os.path.join(EP_DIR, ep, "status.txt"); cur = open(p).read().strip(); frm, to = GATES[gate]
    if cur != frm: raise SystemExit("%s is at '%s'; the %s gate applies at '%s'." % (ep, cur, gate, frm))
    here = os.path.dirname(os.path.abspath(__file__)); fails = []
    for c in AUTO_CHECKS.get(gate, []):
        if subprocess.call([sys.executable, os.path.join(here, c), os.path.join(EP_DIR, ep)]): fails.append(c)
    sys.path.insert(0, here); import learn
    opn = [x["id"] for x in learn.load() if x["status"] == "open" and x["ep"] == ep and x["stage"] in ("topic", "script")]
    if opn: fails.append("open script notes " + ", ".join(opn))
    if fails: raise SystemExit("%s %s gate NOT auto-approved: %s. Fix, record each problem with learn.py, and try again." % (ep, gate, "; ".join(fails)))
    open(p, "w").write(to + "\n")
    with open(os.path.join(EP_DIR, ep, "log.md"), "a") as lg:
        lg.write("- %s · gate '%s' AUTO-approved (all checks passed) → %s\n" % (dt.date.today().isoformat(), gate, to))
    git_commit("%s: %s gate auto-approved (checks passed)" % (ep, gate)); print(ep, "→", to, "(auto)")


def new(ep, title, fmt=None, post=None):
    d = os.path.join(EP_DIR, ep); os.makedirs(d, exist_ok=True)
    s = next_slot()
    if post:
        pd = dt.date.fromisoformat(post); s.update(post=DAYS[pd.weekday()], post_date=post)
    open(os.path.join(d, "status.txt"), "w").write("planned\n")
    open(os.path.join(d, "log.md"), "w").write("# %s log\n- %s · created for slot %s %s → posts %s %s · working title: %s\n"
                                               % (ep, dt.date.today().isoformat(), s["make"], s["make_date"], s["post"], s["post_date"], title))
    fmt = fmt or SCHED.get("default_format", "animated_explainer")
    json.dump({"ep": ep, "title": title, "format": fmt, **s}, open(os.path.join(d, "slot.json"), "w"), indent=1)
    git_commit("%s: planned in the %s batch (posts %s %s)" % (ep, s["make_date"], s["post"], s["post_date"])); print("created", d, s)


def notify(title, text):
    subprocess.run(["osascript", "-e", 'display notification "%s" with title "%s"' % (text.replace('"', "'"), title.replace('"', "'"))], capture_output=True)


def morning():
    log = []
    r = subprocess.run([sys.executable, os.path.join(STUDIO, "engine", "retention.py")], capture_output=True, text=True); log.append(r.stdout.strip())
    r = subprocess.run([sys.executable, os.path.join(STUDIO, "engine", "handover.py")], capture_output=True, text=True); log.append(r.stdout.strip())
    s = next_slot(); today = dt.date.today().isoformat(); m = missing_posts()
    waiting = [(e, st) for e, st in episodes() if st in ("voice_priced", "animatic", "ready_for_review") or (st == "script_draft" and "script" not in SCHED.get("auto_gates", []))]
    msg = ("Batch day: the studio makes %d episode(s) for %s." % (len(m), ", ".join("%s %s" % (DAYS[d.weekday()][:3], d) for d in m))) if s["make_date"] == today and m else "No new batch today."
    if waiting: msg += " Waiting for you: " + ", ".join("%s (%s)" % w for w in waiting) + "."
    msg += " Next batch: %s." % s["make_date"]
    notify("STUDIO studio", msg)
    with open(os.path.join(STUDIO, "logs", "scheduler.log"), "a") as f:
        f.write("%s %s\n%s\n" % (dt.datetime.now().isoformat(timespec="minutes"), msg, "\n".join(x for x in log if x)))
    git_commit("scheduled morning run %s" % today); print(msg)


def idle():
    """exit 0 (idle) when every episode is finished or waiting on the owner and no production slot starts within a day"""
    busy = [st for _, st in episodes() if st in ("planned", "script_locked", "producing", "rendering", "approved") or (st == "script_draft" and "script" in SCHED.get("auto_gates", []))]
    soon = (batch_day() - dt.date.today()).days == 0 or ((batch_day() - dt.date.today()).days == 1 and dt.datetime.now().hour >= 20)
    sys.exit(0 if not busy and not (soon and missing_posts()) else 1)


if __name__ == "__main__":
    os.makedirs(os.path.join(STUDIO, "logs"), exist_ok=True)
    a = sys.argv[1:] or ["status"]
    {"status": lambda: status(), "next": lambda: print(next_slot()), "morning": lambda: morning(),
     "approve": lambda: approve(a[1], a[2]), "autogate": lambda: autogate(a[1], a[2]), "new": lambda: new(a[1], a[2], next((x for x in a[3:] if not x.startswith("--") and a[a.index(x)-1] != "--post"), None), a[a.index("--post") + 1] if "--post" in a else None), "plan": lambda: plan(), "idle": lambda: idle(),
     "commit": lambda: (git_commit(" ".join(a[1:]) or "autopilot run"), print("committed"))}[a[0]]()
