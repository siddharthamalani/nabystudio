#!/usr/bin/env python3
"""Simple, dependency-free mouth timing (fallback when OpenFaceFX/Rhubarb aren't available).
Word timings from faster-whisper on the final voice track; each word's letters are grouped into sound-ish units and mapped
to 7 mouth shapes, spread across the word's duration, with 'rest' between words.
Shapes: rest (M B P, silence) · small (D T N S K L R G H J Y Z) · aa (a) · ee (e i) · oh (o) · oo (u w q) · ff (f v)
  python3 engine/visemes.py episodes/EpN      -> build/lipsync/<LINE>.json  [[t_abs, shape], ...] for non-narrator lines"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GROUPS = [("ff", "fv"), ("rest", "mbp"), ("oo", "uwq"), ("oh", "o"), ("ee", "eiy"), ("aa", "a")]


def word_shapes(w):
    w = re.sub(r"[^a-z]", "", w.lower())
    w = w.replace("th", "d").replace("ch", "d").replace("sh", "d").replace("ee", "e").replace("oo", "u").replace("ou", "o").replace("ck", "k")
    out = []
    for ch in w:
        sh = next((g for g, letters in GROUPS if ch in letters), "small")
        if not out or out[-1] != sh: out.append(sh)
    return out or ["small"]


def main(ep):
    from faster_whisper import WhisperModel
    import soundfile as sf
    cues = json.load(open(os.path.join(ep, "build", "cues.json")))["cues"]
    y, sr = sf.read(os.path.join(ep, "build", "vo_track.wav"))
    out = os.path.join(ep, "build", "lipsync"); os.makedirs(out, exist_ok=True)
    m = WhisperModel("small.en", compute_type="int8")
    for c in cues:
        if c["type"] != "line" or c.get("speaker") == "narrator": continue
        a, b = c["start"], c["end"]; seg = os.path.join(out, c["line"] + ".wav"); sf.write(seg, y[int(a * sr):int(b * sr)], sr)
        words = [w for s in m.transcribe(seg, word_timestamps=True)[0] for w in s.words]
        cue = [[round(a, 3), "rest"]]
        for w in words:
            shapes = word_shapes(w.word); dur = max(w.end - w.start, .08); step = dur / len(shapes)
            for i, sh in enumerate(shapes): cue.append([round(a + w.start + i * step, 3), sh])
            cue.append([round(a + w.end, 3), "rest"])
        json.dump(cue, open(os.path.join(out, c["line"] + ".json"), "w")); os.remove(seg)
        print("  %s: %s" % (c["line"], " ".join(s for _, s in cue)))


if __name__ == "__main__":
    main(sys.argv[1])
