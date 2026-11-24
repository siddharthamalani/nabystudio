#!/usr/bin/env python3
"""Free disk space and memory after every build run. Only removes things that can be regenerated.

  python3 engine/clean.py episodes/EpN            # clean
  python3 engine/clean.py episodes/EpN --dry-run  # just show what would go

Removes:
  - episodes/EpN/build: raw renders (remotion_*.mp4), raw/limited mixes (*_raw.wav, *_fixed.wav, mix_raw.wav),
    old mix versions (keeps only the newest long_audio_v*.wav), check stills, temp files
  - leftover backup copies of engine code (*_v1.py / *_v1.jsx) older than the live file
  - Remotion's temporary bundles and browser profiles in the system temp folder
  - stray Remotion/headless-browser processes still holding memory (only when no render is running)
Keeps: everything in out/, art/, vo/, scripts, vo_track.wav, cues.json, the newest long_audio, remotion/public (needed to re-render
until you archive the episode).
"""
import glob, os, re, shutil, subprocess, sys, tempfile

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def size(p):
    if os.path.isfile(p): return os.path.getsize(p)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs if os.path.exists(os.path.join(r, f)))


def main():
    ep = sys.argv[1].rstrip("/"); dry = "--dry-run" in sys.argv
    if subprocess.run(["pgrep", "-f", "remotion (render|still)"], capture_output=True).returncode == 0:
        raise SystemExit("A render is still running. Clean after it finishes.")
    b = os.path.join(ep, "build")
    victims = []
    for pat in ("remotion_*.mp4", "*_raw.wav", "*_fixed.wav", "short*_final.wav", "mix_raw.wav", "check_*.png", "tmp*", "*.ln.wav", "_deliver", "placement_proof.mp4"):
        victims += glob.glob(os.path.join(b, pat))
    mixes = sorted(glob.glob(os.path.join(b, "long_audio*.wav")), key=os.path.getmtime)
    victims += mixes[:-1]
    for bak in glob.glob(os.path.join(STUDIO, "engine", "*_v1.py")) + glob.glob(os.path.join(STUDIO, "remotion", "src", "studio", "*_v1.jsx")):
        live = re.sub(r"_v1(\.\w+)$", r"\1", bak)
        if os.path.exists(live): victims.append(bak)
    tmp = tempfile.gettempdir()
    victims += glob.glob(os.path.join(tmp, "remotion-*")) + glob.glob(os.path.join(tmp, "react-motion-*"))
    total = 0
    for v in victims:
        if not os.path.exists(v): continue
        s = size(v); total += s
        print(("would remove " if dry else "removed ") + "%-70s %7.1f MB" % (os.path.relpath(v, STUDIO) if v.startswith(STUDIO) else v, s / 1e6))
        if not dry:
            shutil.rmtree(v, ignore_errors=True) if os.path.isdir(v) else os.remove(v)
    if not dry:  # stray headless browsers / node workers left by Remotion
        for pat in ("chrome-headless-shell", "remotion"):
            subprocess.run(["pkill", "-f", pat], capture_output=True)
    print("%s %.1f MB" % ("would free" if dry else "freed", total / 1e6))


if __name__ == "__main__":
    main()
