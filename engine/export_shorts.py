#!/usr/bin/env python3
"""Export the episode's Shorts for Remotion (vertical 1080x1920).

  python3 engine/export_shorts.py episodes/EpN shots_full.py

Needs: build/mix_raw.wav (full mix before loudness), the full export (remotion/src/data/<Ep>_full.json),
vo/lines/R99.mp3 (shared Mascot outro). Writes remotion/public/<Ep>_shorts/* and remotion/src/data/<Ep>_short_<key>.json
"""
import json, os, sys
import numpy as np, soundfile as sf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R, build_ep as B, fx

STUDIO = R.STUDIO
SR = 48000


def env_of(path):
    y = B.decode(path)[:, 0]
    hop = SR // R.FPS; n = len(y) // hop
    r = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
    return [round(float(v), 3) for v in r / (np.percentile(r, 98) + 1e-6)]


def main(ep, shotfile):
    name = os.path.basename(os.path.normpath(ep))
    key = name + "_shorts"
    pub = os.path.join(STUDIO, "remotion", "public", key); os.makedirs(pub, exist_ok=True)
    m = R.load_shotlist(os.path.join(ep, shotfile)); cues = R.Cues(ep)
    raw = B.decode(os.path.join(ep, "build", "mix_raw.wav"))
    r99 = os.path.join(ep, "vo", "lines", "R99.mp3")
    outro_vo = B.decode(r99)
    # Mascot talk frames for the outro card
    frames = fx.load_sheet("assets/references/mascot/anim/mascot_talk.png", 4)
    rt = []
    for i, f in enumerate(frames):
        fn = "mascot_talk_%d.png" % i; Image.fromarray(f).save(os.path.join(pub, fn)); rt.append(key + "/" + fn)
    duck = B.decode(os.path.join(STUDIO, "music/kevin_macleod/Fluffing_a_Duck.mp3"))
    for sk, S in m.SHORTS.items():
        segs, parts, t_out = [], [], 0.0
        words = []
        for a, b in S["ranges"]:
            ta, tb = cues.t(a), cues.t(b)
            part = raw[int(ta * SR):int(tb * SR)].copy()
            fl = int(.04 * SR); part[:fl] *= np.linspace(0, 1, fl)[:, None]; part[-fl:] *= np.linspace(1, 0, fl)[:, None]
            parts.append(part); segs.append([round(ta, 3), round(tb, 3), round(t_out, 3)])
            for c in cues.c:
                if c["type"] != "phrase":
                    continue
                for w in c["words"]:
                    if ta - .02 <= w["s"] <= tb:
                        words.append({"w": w["w"], "s": round(w["s"] - ta + t_out, 3), "e": round(w["e"] - ta + t_out, 3)})
            t_out += tb - ta
        # outro: Mascot + music bed
        lead = .35; L = int((lead + len(outro_vo) / SR + 1.2) * SR)
        bed = duck[:L] * B.db(-20); card = bed.copy()
        card[int(lead * SR):int(lead * SR) + len(outro_vo)] += outro_vo[:L - int(lead * SR)]
        fo = int(.6 * SR); card[-fo:] *= np.linspace(1, 0, fo)[:, None]
        parts.append(card)
        outro = {"start": round(t_out, 3), "dur": round(L / SR, 3)}
        tmp = os.path.join(ep, "build", "short_%s_raw.wav" % sk); sf.write(tmp, np.concatenate(parts), SR, subtype="FLOAT")
        aud = os.path.join(pub, "%s.wav" % sk); B.loudnorm(tmp, aud)
        # outro mouth envelope (aligned to the card start)
        e = env_of(r99); outro["env"] = [0.0] * int(lead * R.FPS) + e
        total = t_out + L / SR
        data = {"duration": round(total, 3), "audio": key + "/%s.wav" % sk, "mascotTalk": {"frames": rt, "w": frames[0].shape[1], "h": frames[0].shape[0]},
                "short": {"segments": segs, "words": words, "hook": S["hook"], "series": "Series One", "episodeTitle": "Episode Title", "outro": outro}}
        json.dump(data, open(os.path.join(STUDIO, "remotion", "src", "data", "%s_short_%s.json" % (name, sk)), "w"))
        print("short", sk, "%.1f s" % total, "LUFS %.1f peak %.1f" % B.measure(aud))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
