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
        "script_draft": "OWNER: approve the script + treatment  →  run.py approve EpN script",
        "script_locked": "Claude session: pronunciations + price every line (estimate only)",
        "voice_priced": "OWNER: OK the credit total  →  run.py approve EpN voice_budget",
        "producing": "Autopilot: voices (tts.py generate), checks, art, shots, placement checks, animatic",
        "animatic": "OWNER: review the animatic  →  run.py approve EpN animatic",
        "rendering": "Render section by section, finish.py, thumbnails, publishing pack, retro",
        "ready_for_review": "OWNER: watch the final cut  →  run.py approve EpN final",
        "approved": "Done: the finished files are in episodes/EpN/out/. Publish them yourself."}


def episodes():
    out = []
    for d in sorted(os.listdir(EP_DIR), key=lambda s: int("".join(c for c in s if c.isdigit()) or 0)):
        p = os.path.join(EP_DIR, d, "status.txt")
        if d.startswith("Ep") and d[2:].isdigit() and os.path.exists(p):
            out.append((d, open(p).read().strip()))
    return out


def next_slot(today=None):
    today = today or dt.date.today()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for k in range(0, 8):
        d = today + dt.timedelta(days=k)
        for slot in SCHED["production"]:
            if days[d.weekday()] == slot["make"]:
                post = d + dt.timedelta(days=1)
                return {"make_date": d.isoformat(), "make": slot["make"], "post": slot["post"], "post_date": post.isoformat()}


def status():
    rows = episodes()
    print("Episodes:")
    for ep, st in rows:
        print("  %-6s %-16s next: %s" % (ep, st, NEXT.get(st, "?")))
    s = next_slot(); print("\nNext production slot: %s %s → posts %s %s" % (s["make"], s["make_date"], s["post"], s["post_date"]))


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
    if cur != frm:
        raise SystemExit("%s is at '%s'; the %s gate applies at '%s'." % (ep, cur, gate, frm))
    open(p, "w").write(to + "\n")
    with open(os.path.join(EP_DIR, ep, "log.md"), "a") as lg:
        lg.write("- %s · OWNER approved gate '%s' → %s\n" % (dt.date.today().isoformat(), gate, to))
    git_commit("%s: owner approved %s" % (ep, gate)); print(ep, "→", to)


def new(ep, title, fmt=None):
    d = os.path.join(EP_DIR, ep); os.makedirs(d, exist_ok=True)
    s = next_slot()
    open(os.path.join(d, "status.txt"), "w").write("planned\n")
    open(os.path.join(d, "log.md"), "w").write("# %s log\n- %s · created for slot %s %s → posts %s %s · working title: %s\n"
                                               % (ep, dt.date.today().isoformat(), s["make"], s["make_date"], s["post"], s["post_date"], title))
    fmt = fmt or SCHED.get("default_format", "animated_explainer")
    json.dump({"ep": ep, "title": title, "format": fmt, **s}, open(os.path.join(d, "slot.json"), "w"), indent=1)
    git_commit("%s: planned for %s (posts %s)" % (ep, s["make_date"], s["post_date"])); print("created", d, s)


def notify(title, text):
    subprocess.run(["osascript", "-e", 'display notification "%s" with title "%s"' % (text.replace('"', "'"), title.replace('"', "'"))], capture_output=True)


def morning():
    log = []
    r = subprocess.run([sys.executable, os.path.join(STUDIO, "engine", "retention.py")], capture_output=True, text=True); log.append(r.stdout.strip())
    r = subprocess.run([sys.executable, os.path.join(STUDIO, "engine", "handover.py")], capture_output=True, text=True); log.append(r.stdout.strip())
    s = next_slot(); today = dt.date.today().isoformat()
    waiting = [(e, st) for e, st in episodes() if st in ("script_draft", "voice_priced", "animatic", "ready_for_review")]
    msg = ("Production day: make the episode that posts %s %s." % (s["post"], s["post_date"])) if s["make_date"] == today else "No production today."
    if waiting: msg += " Waiting for you: " + ", ".join("%s (%s)" % w for w in waiting) + "."
    msg += (" Open Claude Code in ai-studio and say: start today's episode." if s["make_date"] == today
            else " Next production: %s %s." % (s["make"], s["make_date"]))
    notify("STUDIO studio", msg)
    with open(os.path.join(STUDIO, "logs", "scheduler.log"), "a") as f:
        f.write("%s %s\n%s\n" % (dt.datetime.now().isoformat(timespec="minutes"), msg, "\n".join(x for x in log if x)))
    git_commit("scheduled morning run %s" % today); print(msg)


def idle():
    """exit 0 (idle) when every episode is finished or waiting on the owner and no production slot starts within a day"""
    busy = [st for _, st in episodes() if st in ("planned", "script_locked", "producing", "rendering", "approved")]
    s = next_slot(); soon = (dt.date.fromisoformat(s["make_date"]) - dt.date.today()).days <= 1
    have = any(os.path.exists(os.path.join(EP_DIR, e, "slot.json")) and json.load(open(os.path.join(EP_DIR, e, "slot.json")))["make_date"] == s["make_date"] for e, _ in episodes())
    sys.exit(0 if not busy and (not soon or have) else 1)


if __name__ == "__main__":
    os.makedirs(os.path.join(STUDIO, "logs"), exist_ok=True)
    a = sys.argv[1:] or ["status"]
    {"status": lambda: status(), "next": lambda: print(next_slot()), "morning": lambda: morning(),
     "approve": lambda: approve(a[1], a[2]), "new": lambda: new(a[1], a[2], a[3] if len(a) > 3 else None), "idle": lambda: idle()}[a[0]]()
