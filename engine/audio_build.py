#!/usr/bin/env python3
"""Build the voice track for an episode from separate voice lines.

- Word timings come from a local transcription aligned to the script (engine/align.py).
- Each line is cut into sentences at the silence between them.
- The narrator is slowed slightly and pauses are stretched (don't rush).
- Punchline holds come from <ep>/audio_plan.json.
Outputs <ep>/build/vo_track.wav and <ep>/build/cues.json (every sentence and word with start/end/speaker).

  python3 engine/audio_build.py episodes/EpN
"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from align import words_for, sentence_spans

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(STUDIO, "bin", "ffmpeg")
SR = 48000


def decode(path, tempo=1.0):
    af = ["-af", "atempo=%.3f" % tempo] if abs(tempo - 1) > 1e-3 else []
    raw = subprocess.run([FF, "-v", "error", "-i", path] + af + ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def quietest_cut(x, a, b):
    """Sample index of the quietest 10 ms between a and b (sample indices)."""
    a, b = int(a), int(b)
    if b - a < 480:
        return (a + b) // 2
    win = 480
    seg = x[a:b]
    n = len(seg) // win
    e = (seg[:n * win].reshape(n, win) ** 2).mean(axis=1)
    return a + int(np.argmin(e)) * win + win // 2


def main(ep):
    plan = json.load(open(os.path.join(ep, "audio_plan.json")))
    lines = {l["id"]: l for l in json.load(open(os.path.join(ep, "vo", "lines.json")))}
    tempos = plan.get("tempo", {})
    gap_extra = plan.get("pause_extra", 0.3)
    holds = plan.get("holds_after_phrase", {})
    track, cues, t = [], [], 0.0

    def add(seg):
        nonlocal t
        track.append(seg); t += len(seg) / SR

    for step in plan["sequence"]:
        if "silence" in step:
            cues.append({"type": "gap", "label": step.get("label", ""), "start": round(t, 3), "end": round(t + step["silence"], 3)})
            add(np.zeros(int(step["silence"] * SR), np.float32)); continue
        lid = step["line"]; L = lines[lid]
        mp3 = os.path.join(ep, "vo", "lines", lid + ".mp3")
        tempo = tempos.get(L["speaker"], 1.0)
        x = decode(mp3, tempo)
        words = words_for(mp3, L["text"])
        for w in words:  # timings are for the original speed
            w["s"] /= tempo; w["e"] /= tempo
        sents = sentence_spans(words)
        # Only cut where the AUDIO has a real pause (>= 150 ms quiet). Never cut on a zero-gap
        # sentence boundary: that chops words ("Was... | a Cat"). Uncut sentences stay glued together.
        def real_pause(a, b):
            """Cut point inside a real pause, or None. A real pause = the audio dips at least 42 dB below the line's
            average level somewhere between the two sentences (word joins stay around -25 to -30 dB, so they're never cut)."""
            a0, b0 = int(max(0, a - .06) * SR), int(min(len(x) / SR, b + .06) * SR)
            win = 240; seg = x[a0:b0]; n = len(seg) // win
            if n < 2: return None
            e = (seg[:n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12
            mean = (x ** 2).mean() + 1e-12
            i = int(np.argmin(e))
            if 10 * np.log10(e[i] / mean) > -42: return None
            return a0 + i * win + win // 2
        cut_at = []
        for k in range(len(sents) - 1):
            last_w = sents[k][-1]["w"]; gap_w = sents[k + 1][0]["s"] - sents[k][-1]["e"]
            # only at a real sentence end where the narrator breathed: never on "..." suspensions or joined words
            if last_w.endswith("...") or last_w.endswith("…") or last_w[-1:] not in ".?!" or gap_w < 0.25:
                cut_at.append(None); continue
            cut_at.append(real_pause(sents[k][-1]["e"], sents[k + 1][0]["s"]))
        bounds = [0] + [c for c in cut_at if c is not None] + [len(x)]
        line_start = t; seg_i = 0; pending_hold = 0.0
        for k, s in enumerate(sents):
            text = " ".join(w["w"] for w in s)
            for key, sec in holds.items():
                if key.lower() in text.lower():
                    pending_hold = max(pending_hold, sec)
            # where does sentence k sit in the output? segment seg_i starts at seg_t0
            if k == 0 or cut_at[k - 1] is not None:
                first_start = None
                a, b = bounds[seg_i], bounds[seg_i + 1]
                seg = x[a:b].copy()
                fl = min(int(.012 * SR), len(seg) // 4)
                if fl > 0 and a > 0: seg[:fl] *= np.linspace(0, 1, fl)
                if fl > 0 and b < len(x): seg[-fl:] *= np.linspace(1, 0, fl)
                seg_t0, off = t, a / SR
                add(seg); seg_i += 1
            if first_start is None: first_start = seg_t0 + s[0]["s"] - off
            cues.append({"type": "phrase", "line": lid, "speaker": L["speaker"], "text": text,
                         "start": round(seg_t0 + s[0]["s"] - off, 3), "end": round(seg_t0 + s[-1]["e"] - off, 3),
                         "words": [{"w": w["w"], "s": round(seg_t0 + w["s"] - off, 3), "e": round(seg_t0 + w["e"] - off, 3)} for w in s]})
            last = k == len(sents) - 1
            if last or cut_at[k] is not None:
                extra = 0.0 if last else gap_extra
                # minimum time per picture (owner: transitions too fast): a short sentence gets a longer pause after it
                span = (seg_t0 + s[-1]["e"] - off) - first_start
                min_s = plan.get("min_sentence", 2.0)
                if not last and span + extra + pending_hold < min_s:
                    extra = min_s - span - pending_hold
                if extra + pending_hold > 0:
                    add(np.zeros(int((extra + pending_hold) * SR), np.float32))
                pending_hold = 0.0
        cues.append({"type": "line", "line": lid, "speaker": L["speaker"], "start": round(line_start, 3), "end": round(t, 3)})
        add(np.zeros(int(step.get("after", 0.5) * SR), np.float32))

    # shared end-screen line (Mascot asks people to subscribe), placed after the credits; the episode "duration" (where the
    # credits start) is NOT changed by it.
    vo_end = t
    es = plan.get("endscreen")
    if es:
        gap = es.get("after_end", 10.2)
        add(np.zeros(int(gap * SR), np.float32))
        xr = decode(os.path.join(STUDIO, es["file"])); s0 = t; add(xr)
        cues.append({"type": "line", "line": es.get("id", "R98"), "speaker": "mascot", "start": round(s0, 3), "end": round(t, 3)})
    y = np.concatenate(track)
    os.makedirs(os.path.join(ep, "build"), exist_ok=True)
    sf.write(os.path.join(ep, "build", "vo_track.wav"), y, SR, subtype="PCM_16")
    json.dump({"duration": round(vo_end, 3), "cues": cues}, open(os.path.join(ep, "build", "cues.json"), "w"), indent=1)
    print("voice track %.1f s, %d sentences" % (vo_end, sum(1 for c in cues if c["type"] == "phrase")))


if __name__ == "__main__":
    main(sys.argv[1])
