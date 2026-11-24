#!/usr/bin/env python3
"""Encode the final long video + Shorts from Remotion renders, fix peaks automatically, make Short check grids.
  python3 engine/finish.py episodes/EpN long_audio.wav
Peak fix: if an encoded file's true peak is over -1.5 dBTP, the sharpest click in its audio is smoothed (6 ms) and the
audio is re-muxed; repeats up to 4 times. (A single-sample click makes AAC overshoot; limiting harder doesn't help.)"""
import os, subprocess, sys, json, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_ep as B

def dip_worst(mp4, wav):
    """Find where the ENCODED file peaks highest and lower the source audio there by 3 dB over ~0.5 s (smooth envelope).
    AAC overshoots on flat-topped (heavily limited) shouts; a short gentle dip fixes it without touching the rest."""
    r = subprocess.run([B.FF, "-v", "error", "-i", mp4, "-map", "0:a:0", "-ac", "2", "-ar", "48000", "-f", "f32le", "-"], capture_output=True).stdout
    enc = np.abs(np.frombuffer(r, np.float32).reshape(-1, 2)).max(axis=1)
    t = int(enc.argmax()) / 48000
    w, sr = sf.read(wav, always_2d=True)
    a, b = max(0, int((t - .3) * sr)), min(len(w), int((t + .3) * sr))
    x = np.linspace(0, 1, b - a); env = 1 - (1 - 10 ** (-3 / 20)) * np.sin(np.pi * x) ** 2
    w[a:b] *= env[:, None]
    sf.write(wav, w, sr, subtype="PCM_24"); return t


def remux(mp4, wav):
    tmp = mp4 + ".tmp.mp4"
    subprocess.run([B.FF, "-y", "-v", "error", "-i", mp4, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-ar", "48000", "-movflags", "+faststart", tmp], check=True); os.replace(tmp, mp4)

def peak_fix(mp4, wav):
    for _ in range(8):
        I, TP = B.measure(mp4)
        if TP <= -1.5: return I, TP
        t = dip_worst(mp4, wav); print("   lowered peak at %.2f s by 3 dB" % t); remux(mp4, wav)
    return B.measure(mp4)

ep = sys.argv[1].rstrip("/"); name = os.path.basename(ep); bld = os.path.join(ep, "build")
out = os.path.join(ep, "out", "%s_Episode.mp4" % name) if name == "EpN" else os.path.join(ep, "out", name + ".mp4")
work = os.path.join(bld, "final_long.wav"); subprocess.run(["cp", os.path.join(bld, sys.argv[2]), work], check=True)
B.encode_long(os.path.join(bld, "remotion_long.mp4"), work, out)
I, TP = peak_fix(out, work)
print("LONG %.1f MB  %.1f LUFS  %.1f dBTP" % (os.path.getsize(out) / 1e6, I, TP))
S = os.path.join(bld, "checks"); os.makedirs(S, exist_ok=True)
for f in sorted(os.listdir(os.path.join("remotion", "public", name + "_shorts"))):
    if not f.endswith(".wav"): continue
    key = f[:-4]; k = key.split("_")[0]
    src = os.path.join(bld, "remotion_short%s.mp4" % k)
    if not os.path.exists(src): continue
    wav = os.path.join(bld, "short%s_final.wav" % k)
    subprocess.run([B.FF, "-y", "-v", "error", "-i", os.path.join("remotion", "public", name + "_shorts", f), "-af",
                    "alimiter=limit=0.6:attack=1:release=50:level=false,volume=0.4dB,aresample=48000", wav], check=True)
    o = os.path.join(ep, "out", "%s_Short%s.mp4" % (name, key)); B.encode_short(src, wav, o)
    I, TP = peak_fix(o, wav)
    print("SHORT %s %.1f MB  %.1f LUFS  %.1f dBTP" % (k, os.path.getsize(o) / 1e6, I, TP))
    subprocess.run([B.FF, "-v", "error", "-y", "-i", o, "-vf", "fps=1/4,scale=180:-1,tile=10x2", "-frames:v", "1", os.path.join(S, "grid_%s.jpg" % k)])
