"""Word timings for a voice line: local faster-whisper transcription, aligned back to the script words.

words_for(mp3_path, script_text) -> list of {"w": script_word, "s": start, "e": end}
Results are cached next to the mp3 as <name>.words.json.
"""
import json, os, re, difflib

_model = None


def _norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def _transcribe(path):
    global _model
    cache = os.path.splitext(path)[0] + ".whisper.json"
    if os.path.exists(cache):
        return json.load(open(cache))
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = _model.transcribe(path, word_timestamps=True, language="en")
    out = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]
    json.dump(out, open(cache, "w"))
    return out


def words_for(path, script_text):
    hyp = _transcribe(path)
    ref = script_text.replace("—", " ").split()
    rn = [_norm(w) for w in ref]
    hn = [_norm(h["w"]) for h in hyp]
    sm = difflib.SequenceMatcher(a=rn, b=hn, autojunk=False)
    times = [None] * len(ref)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            times[a + k] = (hyp[b + k]["s"], hyp[b + k]["e"])
    # interpolate unmatched words (numbers, hyphenated words) between anchors
    start0 = hyp[0]["s"] if hyp else 0.0
    end0 = hyp[-1]["e"] if hyp else 0.0
    i = 0
    while i < len(ref):
        if times[i] is None:
            j = i
            while j < len(ref) and times[j] is None:
                j += 1
            t0 = times[i - 1][1] if i > 0 else start0
            t1 = times[j][0] if j < len(ref) else end0
            span = max(t1 - t0, 0.05 * (j - i))
            chars = [max(len(ref[k]), 1) for k in range(i, j)]
            tot = float(sum(chars)); acc = t0
            for k, c in zip(range(i, j), chars):
                d = span * c / tot
                times[k] = (acc, acc + d); acc += d
            i = j
        else:
            i += 1
    return [{"w": w, "s": round(t[0], 3), "e": round(t[1], 3)} for w, t in zip(ref, times)]


def sentence_spans(words):
    """Group words into sentences at . ? ! (and ... ) endings."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"(\.\.\.|[.?!])[\"')]*$", w["w"]):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out
