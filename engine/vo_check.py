#!/usr/bin/env python3
"""Voice QA: transcribe every voice line WITHOUT the script and flag words that don't match.
Catches mispronunciations like "cat" heard as "key".

  python3 engine/vo_check.py episodes/EpN
"""
import json, os, re, sys, difflib

NUM = {"13": "thirteen", "1960s": "nineteen sixties", "1967": "nineteen sixty seven", "10": "ten", "15": "fifteen", "20": "twenty",
       "30": "thirty", "1": "one", "0": "zero"}


def norm(t):
    t = t.lower().replace("-", " ")
    words = []
    for w in re.findall(r"[a-z0-9']+", t):
        words += NUM.get(w, w).split()
    return words


def main(ep):
    from faster_whisper import WhisperModel
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    lines = json.load(open(os.path.join(ep, "vo", "lines.json")))
    problems = 0
    for L in lines:
        p = os.path.join(ep, "vo", "lines", L["id"] + ".mp3")
        if not os.path.exists(p):
            continue
        segs, _ = m.transcribe(p, language="en")
        heard = " ".join(s.text for s in segs)
        a, b = norm(L["text"]), norm(heard)
        sm = difflib.SequenceMatcher(a=a, b=b)
        bad = [(op, " ".join(a[i1:i2]), " ".join(b[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
        bad = [x for x in bad if not (x[0] == "delete" and x[1] in ("well",))]
        if bad and sm.ratio() < 0.999:
            problems += 1
            print("CHECK %s (%.0f%% match): %s" % (L["id"], sm.ratio() * 100, "; ".join("script '%s' → heard '%s'" % (x[1], x[2]) for x in bad)))
    print("voice QA done: %d line(s) to listen to" % problems)


if __name__ == "__main__":
    main(sys.argv[1])
