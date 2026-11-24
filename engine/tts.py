#!/usr/bin/env python3
"""Voices for the autopilot: price first (auto-approve under the cap), then generate each line once.
The TTS API key is read from the macOS Keychain (engine/secret.py), never from files.

  python3 engine/tts.py price episodes/EpN      # writes voice_estimate.json (characters ≈ credits); moves status to voice_priced,
                                                #   and AUTO-APPROVES (→ producing) if the total ≤ voice_auto_approve_credits (5,000)
  python3 engine/tts.py generate episodes/EpN   # only when status is 'producing': generates missing lines into vo/lines/<ID>.mp3,
                                                #   logs credits used; refuses if it would exceed the approved total

lines.json rows: {"id", "speaker", "text", "voice_id", "model"}  (model default eleven_flash_v2_5; emotion tags → eleven_v4)
Pricing rule observed on this account: ~1 credit per character for flash v2.5 and v4 (tags count as characters)."""
import json, os, sys, urllib.request, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secret import get

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHED = json.load(open(os.path.join(STUDIO, "studio_schedule.json")))


def lines(ep):
    return json.load(open(os.path.join(ep, "vo", "lines.json")))


def todo(ep):
    return [l for l in lines(ep) if not os.path.exists(os.path.join(ep, "vo", "lines", l["id"] + ".mp3"))]


def price(ep):
    t = todo(ep); total = sum(len(l["text"]) for l in t)
    est = {"date": dt.date.today().isoformat(), "lines": len(t), "credits": total, "cap": SCHED["voice_auto_approve_credits"]}
    json.dump(est, open(os.path.join(ep, "voice_estimate.json"), "w"), indent=1)
    st = os.path.join(ep, "status.txt"); auto = total <= est["cap"]
    open(st, "w").write(("producing" if auto else "voice_priced") + "\n")
    with open(os.path.join(ep, "log.md"), "a") as lg:
        lg.write("- %s · voice priced: %d lines, ~%d credits → %s\n" % (est["date"], len(t), total,
                 "AUTO-APPROVED (≤ %d cap)" % est["cap"] if auto else "WAITING for owner (over %d cap)" % est["cap"]))
    print(json.dumps(est), "auto-approved" if auto else "needs owner approval")


def generate(ep):
    st = open(os.path.join(ep, "status.txt")).read().strip()
    if st not in ("producing",):
        raise SystemExit("status is '%s': voice generation needs 'producing' (budget approved)" % st)
    key = get("studio-elevenlabs")
    if not key: raise SystemExit("ElevenLabs API key missing in Keychain (studio-elevenlabs)")
    est = json.load(open(os.path.join(ep, "voice_estimate.json"))); used = 0
    os.makedirs(os.path.join(ep, "vo", "lines"), exist_ok=True)
    for l in todo(ep):
        if used + len(l["text"]) > est["credits"] + 50:
            raise SystemExit("stopping: would exceed the approved total (%d)" % est["credits"])
        body = json.dumps({"text": l["text"], "model_id": l.get("model", "eleven_flash_v2_5")}).encode()
        req = urllib.request.Request("https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128" % l["voice_id"],
                                     data=body, headers={"xi-api-key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            open(os.path.join(ep, "vo", "lines", l["id"] + ".mp3"), "wb").write(r.read())
        used += len(l["text"]); print("  %s ok (%d chars)" % (l["id"], len(l["text"])))
    led = os.path.join(STUDIO, "logs", "credits.csv"); new = not os.path.exists(led)
    with open(led, "a") as f:
        if new: f.write("date,episode,credits\n")
        f.write("%s,%s,%d\n" % (dt.date.today().isoformat(), os.path.basename(ep), used))
    print("generated, ~%d credits" % used)


if __name__ == "__main__":
    {"price": price, "generate": generate}[sys.argv[1]](sys.argv[2].rstrip("/"))
