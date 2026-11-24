#!/usr/bin/env python3
"""Replace one sentence inside a voice line with a re-recorded take (cheaper than re-recording the whole line).
  python3 engine/splice_vo.py <line.mp3> <patch.mp3> "<first words of sentence>" "<last words of sentence>"
Cuts at the quietest point of the real pauses around the sentence; keeps <line>.orig.mp3."""
import os, shutil, subprocess, sys, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from align import words_for
from audio_build import decode, quietest_cut, SR, FF
from faster_whisper import WhisperModel

def trim(x, thr=1e-4):
    e = np.convolve(x ** 2, np.ones(480) / 480, "same"); idx = np.where(e > thr)[0]
    return x[max(0, idx[0] - 1200): idx[-1] + 2400] if len(idx) else x

line, patch, first, last = sys.argv[1:5]
orig = line.replace(".mp3", ".orig.mp3")
if not os.path.exists(orig): shutil.copy(line, orig)
x = decode(orig)
m = WhisperModel("small.en", compute_type="int8")
segs, _ = m.transcribe(orig, word_timestamps=True)
W = [(w.word.strip().lower().strip(".,?!:;…\"'"), w.start, w.end) for s in segs for w in s.words]
def find(seq, from_end=False):
    seq = [s.lower().strip(".,?!:;…\"'") for s in seq.split()]
    for i in range(len(W) - len(seq) + 1):
        if [w[0] for w in W[i:i + len(seq)]] == seq: return i, i + len(seq) - 1
    raise SystemExit("not found: %s  (heard: %s)" % (seq, " ".join(w[0] for w in W)))
i0, _ = find(first); _, i1 = find(last)
a = quietest_cut(x, (W[i0 - 1][2] if i0 else 0) * SR, W[i0][1] * SR) if i0 else 0
b = quietest_cut(x, W[i1][2] * SR, (W[i1 + 1][1] if i1 + 1 < len(W) else len(x) / SR) * SR) if i1 + 1 < len(W) else len(x)
p = trim(decode(patch)); f = 240
p[:f] *= np.linspace(0, 1, f); p[-f:] *= np.linspace(1, 0, f)
pad = np.zeros(int(.08 * SR), np.float32)
y = np.concatenate([x[:a], pad, p, pad, x[b:]])
tmp = line.replace(".mp3", ".tmp.wav"); sf.write(tmp, y, SR)
subprocess.run([FF, "-y", "-v", "error", "-i", tmp, "-b:a", "192k", line], check=True); os.remove(tmp)
print("spliced %.2f-%.2f s -> %.2f s patch" % (a / SR, b / SR, len(p) / SR))
