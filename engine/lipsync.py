#!/usr/bin/env python3
"""Mouth shapes from the actual sounds (Rhubarb Lip Sync, MIT, github.com/DanielSWolf/rhubarb-lip-sync), tools/rhubarb.

  python3 engine/lipsync.py episodes/EpN            # every talking line (non-narrator) in build/cues.json

Runs Rhubarb on each line's span of the FINAL voice track (build/vo_track.wav), so inserted pauses are included, and writes
build/lipsync/<LINE>.json = [[t_abs, shape], ...] with shapes A-H/X:
  A closed (P B M) · B slightly open (most consonants) · C open (EH AE) · D wide (AA) · E round (AO ER) · F pucker (UW OW W)
  G teeth on lip (F V) · H tongue (L) · X idle
Rhubarb's macOS build is Intel-only: on Apple Silicon it needs Rosetta (softwareupdate --install-rosetta). Without it this script
exits cleanly and the engine falls back to loudness-driven mouths."""
import json, os, subprocess, sys
import soundfile as sf

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RH = os.path.join(STUDIO, "tools", "rhubarb", "rhubarb")


def available():
    try:
        return subprocess.run([RH, "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


def main(ep):
    if not available():
        print("Rhubarb not runnable (install Rosetta: softwareupdate --install-rosetta). Using loudness mouths."); return
    cues = json.load(open(os.path.join(ep, "build", "cues.json")))["cues"]
    lines = {l["id"]: l for l in json.load(open(os.path.join(ep, "vo", "lines.json")))}
    y, sr = sf.read(os.path.join(ep, "build", "vo_track.wav"))
    out = os.path.join(ep, "build", "lipsync"); os.makedirs(out, exist_ok=True)
    for c in cues:
        if c["type"] != "line" or c.get("speaker") == "narrator": continue
        lid = c["line"]; a, b = c["start"], c["end"]
        seg = os.path.join(out, lid + ".wav"); sf.write(seg, y[int(a * sr):int(b * sr)], sr)
        txt = os.path.join(out, lid + ".txt"); open(txt, "w").write((lines.get(lid) or {}).get("text", ""))
        r = subprocess.run([RH, "-f", "json", "-d", txt, "--extendedShapes", "GHX", seg], capture_output=True, text=True)
        if r.returncode != 0: print("  rhubarb failed on", lid, r.stderr[-200:]); continue
        mc = [[round(a + m["start"], 3), m["value"]] for m in json.loads(r.stdout)["mouthCues"]]
        json.dump(mc, open(os.path.join(out, lid + ".json"), "w")); os.remove(seg); os.remove(txt)
        print("  %s: %d mouth cues" % (lid, len(mc)))


if __name__ == "__main__":
    main(sys.argv[1])
