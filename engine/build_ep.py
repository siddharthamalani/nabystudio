#!/usr/bin/env python3
"""Build an episode end to end: long video, captions, 3 Shorts, thumbnail.

  python3 engine/build_ep.py episodes/EpN [--only long|shorts|thumb|audio] [--preview SECONDS]

Needs: build/cues.json + build/vo_track.wav (engine/audio_build.py), shots.py in the episode folder.
Outputs go to <ep>/out/. Nothing is uploaded anywhere.
"""
import argparse, json, math, os, subprocess, sys
import numpy as np, soundfile as sf, cv2
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
from credits import make as make_credits

STUDIO = R.STUDIO
FF = R.FF
SR = 48000


def run(cmd):
    subprocess.run(cmd, check=True)


def decode(path, sr=SR, ch=2):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, ch).copy()


def db(x):
    return 10 ** (x / 20.0)


# ------------------------------------------------------------------ audio
def build_mix(ep, m, cues, total):
    n = int(total * SR)
    vo = decode(os.path.join(ep, "build", "vo_track.wav"))
    voice = np.zeros((n, 2), np.float32); voice[:min(n, len(vo))] = vo[:n]
    # voice activity envelope (smoothed) for ducking
    mono = np.abs(voice[:, 0])
    win = int(.05 * SR); k = np.ones(win) / win
    env = np.convolve(mono, k, mode="same")
    act = (env > 0.01).astype(np.float32)
    att = int(.08 * SR); rel = int(.6 * SR)
    sm = np.zeros_like(act); v = 0.0
    a_up, a_dn = 1 - math.exp(-1 / att), 1 - math.exp(-1 / rel)
    for i in range(0, n, 64):  # coarse IIR, fast enough
        target = act[i]
        v += (target - v) * (a_up * 64 if target > v else a_dn * 64)
        v = min(max(v, 0), 1)
        sm[i:i + 64] = v
    duck = 1 - sm * (1 - db(-9))  # music 9 dB lower under the voice, swells in the pauses
    music = np.zeros((n, 2), np.float32)
    for f, a, b, lvl, fi, fo in m.MUSIC:
        t0 = cues.t(a); t1 = total if b == "END" else cues.t(b)
        x = decode(os.path.join(STUDIO, f))
        L = int((t1 - t0) * SR)
        if L <= 0:
            continue
        reps = int(math.ceil(L / len(x)))
        seg = np.tile(x, (reps, 1))[:L] * db(lvl)
        fi_n, fo_n = int(fi * SR), int(fo * SR)
        if fi_n: seg[:fi_n] *= np.linspace(0, 1, fi_n)[:, None]
        if fo_n: seg[-fo_n:] *= np.linspace(1, 0, fo_n)[:, None]
        s0 = int(t0 * SR); music[s0:s0 + L] += seg[:n - s0]
    music *= duck[:, None]
    sfx = np.zeros((n, 2), np.float32)
    for item in m.SFX:
        f, at, lvl = item[:3]
        x = decode(os.path.join(STUDIO, f)) * db(lvl)
        if len(item) > 3 and item[3]:
            L_ = int(item[3] * SR); x = x[:L_].copy(); fo = min(int(.15 * SR), len(x))
            x[-fo:] *= np.linspace(1, 0, fo)[:, None]
        s0 = int(cues.t(at) * SR)
        e = min(n, s0 + len(x)); sfx[s0:e] += x[:e - s0]
    mix = voice + music + sfx
    out = os.path.join(ep, "build", "mix_raw.wav")
    sf.write(out, mix, SR, subtype="FLOAT")
    return out


def loudnorm(src, dst, start=None, dur=None):
    """Two-pass EBU R128 to -14 LUFS, true peak <= -1.5 dBTP."""
    cut = (["-ss", "%.3f" % start] if start is not None else []) + (["-t", "%.3f" % dur] if dur is not None else [])
    p = subprocess.run([FF, "-hide_banner"] + cut + ["-i", src, "-af", "loudnorm=I=-14:TP=-2.2:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    js = p.stderr[p.stderr.rfind("{"):p.stderr.rfind("}") + 1]
    d = json.loads(js)
    af = ("loudnorm=I=-14:TP=-2.2:LRA=11:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
          % (d["input_i"], d["input_tp"], d["input_lra"], d["input_thresh"], d["target_offset"]))
    tmp = dst + ".ln.wav"
    run([FF, "-y", "-v", "error"] + cut + ["-i", src, "-af", af + ",aresample=48000", "-ar", "48000", tmp])
    # true-peak safety: limiter at -3 dBFS, then nudge loudness back to -14 (2 passes max)
    gain = 0.0
    for _ in range(3):
        run([FF, "-y", "-v", "error", "-i", tmp, "-af", "volume=%.2fdB,alimiter=limit=0.70:attack=2:release=60:level=false,aresample=48000" % gain, dst])
        I, TP = measure(dst)
        if abs(I + 14) < 0.3:
            break
        gain += (-14 - I)
    os.remove(tmp)


def measure(path):
    p = subprocess.run([FF, "-hide_banner", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    d = json.loads(p.stderr[p.stderr.rfind("{"):p.stderr.rfind("}") + 1])
    return float(d["input_i"]), float(d["input_tp"])


# ------------------------------------------------------------------ captions (SRT for the long)
def srt(cues, path, max_chars=42):
    def ts(t):
        h = int(t // 3600); m_ = int(t % 3600 // 60); s = t % 60
        return "%02d:%02d:%06.3f" % (h, m_, s)
    out, k = [], 0
    for c in cues.c:
        if c["type"] != "phrase":
            continue
        words = c["words"]; chunk = []
        for i, w in enumerate(words):
            chunk.append(w)
            text = " ".join(x["w"] for x in chunk)
            if len(text) >= max_chars or i == len(words) - 1:
                k += 1
                out.append("%d\n%s --> %s\n%s\n" % (k, ts(chunk[0]["s"]).replace(".", ","), ts(max(chunk[-1]["e"], chunk[0]["s"] + .6)).replace(".", ","), text))
                chunk = []
    open(path, "w").write("\n".join(out))


# ------------------------------------------------------------------ encode
def encode_long(video, audio, out, target_mb=22.4):
    dur = float(subprocess.run([FF, "-i", video], capture_output=True, text=True).stderr.split("Duration: ")[1].split(",")[0].split(":")[-1]) \
        + 60 * int(subprocess.run([FF, "-i", video], capture_output=True, text=True).stderr.split("Duration: ")[1].split(":")[1])
    total_kbps = target_mb * 8 * 1024 / dur
    vk = int(total_kbps - 112)
    log = os.path.join(os.path.dirname(out), "x265pass")
    base = [FF, "-y", "-v", "error", "-i", video, "-c:v", "libx265", "-b:v", "%dk" % vk, "-preset", "medium", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"]
    run(base + ["-x265-params", "pass=1:stats=%s.log:log-level=error" % log, "-an", "-f", "mp4", os.devnull])
    run(base[:6] + ["-i", audio] + base[6:] + ["-x265-params", "pass=2:stats=%s.log:log-level=error" % log,
        "-c:a", "aac", "-b:a", "128k", "-map", "0:v", "-map", "1:a", "-movflags", "+faststart", "-shortest", out])
    for f in os.listdir(os.path.dirname(out)):
        if f.startswith("x265pass"):
            os.remove(os.path.join(os.path.dirname(out), f))


def encode_short(video, audio, out):
    run([FF, "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "libx265", "-crf", "22",
         "-preset", "medium", "-tag:v", "hvc1", "-pix_fmt", "yuv420p", "-x265-params", "log-level=error",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", out])


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep"); ap.add_argument("--only"); ap.add_argument("--preview", type=float)
    a = ap.parse_args()
    ep = a.ep
    m = R.load_shotlist(os.path.join(ep, "shots.py"))
    cues = R.Cues(ep)
    env = R.Envelope(os.path.join(ep, "build", "vo_track.wav"))
    os.makedirs(os.path.join(ep, "out"), exist_ok=True)
    os.makedirs(os.path.join(ep, "build"), exist_ok=True)
    vo_end = cues.duration
    total = vo_end + m.CREDITS_SECONDS + m.ENDSCREEN_SECONDS
    cred_png = os.path.join(ep, "build", "credits.png")
    cw, ch = make_credits(m.CREDITS, cred_png)
    shots = list(m.SHOTS) + [
        {"at": vo_end, "bg": "#122E2E", "cam": [1.0, 1.0], "dissolve": .4,
         "layers": [{"img": cred_png, "cut": False, "scroll": [1.0, -(ch / cw * 1920 * .9) / 1080 + .05], "w": .9, "enter": "none", "idle": "none"}]},
        {"at": vo_end + m.CREDITS_SECONDS, "bg": "assets/brand/raw/end_screen.png", "cam": [1.0, 1.02], "dissolve": .4,
         "layers": [{"img": "assets/references/mascot/poses/raven_smug.png", "x": .12, "y": .99, "h": .3, "cut": False, "idle": "bob"}],
         "texts": [{"kind": "pill", "text": "Thanks for watching.", "t0": .3, "x": .5, "y": .1, "size": 56}]},
    ]
    shots = R.resolve(shots, cues, total)
    name = os.path.basename(os.path.normpath(ep))

    if a.only in (None, "audio", "long", "shorts"):
        print("mixing audio …"); raw = build_mix(ep, m, cues, total)

    if a.only in (None, "long"):
        t_end = a.preview if a.preview else total
        vid = os.path.join(ep, "build", "long_video.mp4")
        print("rendering long video %.0f s …" % t_end)
        R.render(shots, cues, env, vid, 0, t_end, 1920, 1080)
        aud = os.path.join(ep, "build", "long_audio.wav")
        loudnorm(raw, aud, 0, t_end)
        out = os.path.join(ep, "out", "%s_Episode%s.mp4" % (name, "_PREVIEW" if a.preview else ""))
        print("encoding HEVC (2-pass) …"); encode_long(vid, aud, out)
        srt(cues, os.path.join(ep, "out", "%s_captions_en.srt" % name))
        print("LONG:", out, "%.1f MB" % (os.path.getsize(out) / 1e6), "loudness %.1f LUFS, peak %.1f dBTP" % measure(out))

    if a.only in (None, "shorts"):
        for key, S in m.SHORTS.items():
            build_short(ep, m, cues, env, shots, key, S, raw, name)

    if a.only in (None, "thumb"):
        thumbnail(ep, name)


def caption_groups(cues, a, b):
    groups = []
    for c in cues.c:
        if c["type"] != "phrase" or c["end"] < a or c["start"] > b:
            continue
        cur = []
        for w in c["words"]:
            if w["s"] < a - .05 or w["s"] > b:
                continue
            cur.append(w)
            if len(cur) == 3 or len(" ".join(x["w"] for x in cur)) > 16 or w["w"][-1] in ".?!,":
                groups.append((cur[0]["s"], cur[-1]["e"], " ".join(x["w"] for x in cur))); cur = []
        if cur:
            groups.append((cur[0]["s"], cur[-1]["e"], " ".join(x["w"] for x in cur)))
    return groups


def build_short(ep, m, cues, env, shots, key, S, raw_mix, name):
    W, H = 1080, 1920
    print("short", key)
    vid = os.path.join(ep, "build", "short_%s.mp4" % key)
    cmd = [FF, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H), "-r", str(R.FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", vid]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    audio_parts = []
    raw = decode(raw_mix)
    hook = R.text_sprite("title", S["hook"], 92, int(W * .88))
    series = R.text_sprite("pill", "Series One", 46, 900)
    t_out = 0.0
    for (ka, kb) in S["ranges"]:
        a_, b_ = cues.t(ka), cues.t(kb)
        groups = caption_groups(cues, a_, b_)
        n = int(round((b_ - a_) * R.FPS)); idx = 0
        for i in range(n):
            t = a_ + i / R.FPS
            while idx + 1 < len(shots) and shots[idx + 1]["_t"] <= t:
                idx += 1
            s = shots[idx]
            if s.get("vcrop"):
                fr = R.render_frame(s, t - s["_t"], t, W, H, cues, env, vertical=True, text_scale=1.0)
            else:
                vs = s.get("vscale", 1.0)
                ww, hh = int(W * vs), int(608 * vs)
                wide = R.render_frame(s, t - s["_t"], t, ww, hh, cues, env, vertical=False, text_scale=1.25 / vs)
                x0 = (ww - W) // 2
                band = wide[:, x0:x0 + W]
                fill = cv2.resize(wide, (int(H * 16 / 9), H), interpolation=cv2.INTER_LINEAR)
                fx = (fill.shape[1] - W) // 2
                fill = cv2.GaussianBlur(fill[:, fx:fx + W], (0, 0), 25)
                fr = (fill.astype(np.float32) * .45).astype(np.uint8)
                by = 600 if vs == 1.0 else max(330, 960 - hh // 2 - 60)
                fr[by:by + hh] = band
                s["_cap_y"] = min(by + hh + 40, int(H * .8))
            R.blend(fr, series, 40, 60)
            if t_out + i / R.FPS < 3.0:
                R.blend(fr, hook, W // 2 - hook.shape[1] // 2, 210, min(1, (3.0 - (t_out + i / R.FPS)) / .3))
            for g0, g1, txt in groups:
                if g0 - .02 <= t <= max(g1, g0 + .35):
                    cap = R.text_sprite("caption", txt, 84, int(W * .86))
                    R.blend(fr, cap, W // 2 - cap.shape[1] // 2, s.get("_cap_y", int(H * .68)) if not s.get("vcrop") else int(H * .72)); break
            p.stdin.write(fr.tobytes())
        part = raw[int(a_ * SR):int(b_ * SR)].copy()
        fl = int(.03 * SR)  # 30 ms fades at clip joins: no clicks
        part[:fl] *= np.linspace(0, 1, fl)[:, None]; part[-fl:] *= np.linspace(1, 0, fl)[:, None]
        audio_parts.append(part)
        t_out += n / R.FPS
    # end card: Mascot + follow/subscribe, voiced by Mascot (R05)
    r05 = decode(os.path.join(ep, "vo", "lines", "R05.mp3"))
    card_len = len(r05) / SR + 1.0
    duck = decode(os.path.join(STUDIO, "music/kevin_macleod/Fluffing_a_Duck.mp3"))[:int(card_len * SR)] * db(-20)
    card = duck.copy(); card[int(.3 * SR):int(.3 * SR) + len(r05)] += r05[:len(card) - int(.3 * SR)]
    fo = int(.6 * SR); card[-fo:] *= np.linspace(1, 0, fo)[:, None]
    audio_parts.append(card)
    bg = R.load_bg("#1E5F5F", W, H, 1.0)
    reg = R.load_rgba("assets/references/mascot/poses/raven_smug.png", False)
    t1 = R.text_sprite("title", "Episode Title", 86, int(W * .86))
    t2 = R.text_sprite("note", "Full story linked", 56, int(W * .7))
    t3 = R.text_sprite("pill", "Follow @yourchannel", 50, int(W * .9))
    t4 = R.text_sprite("pill", "Subscribe · Your Channel", 46, int(W * .9))
    for i in range(int(card_len * R.FPS)):
        tt = i / R.FPS
        fr = bg.copy()
        rs = R.scaled(reg, 760 / reg.shape[0] * (1 + .01 * math.sin(tt * 4)))
        R.blend(fr, rs, W // 2 - rs.shape[1] // 2, 1080 - rs.shape[0] // 2 + 260)
        R.blend(fr, series, W // 2 - series.shape[1] // 2, 120)
        R.blend(fr, t1, W // 2 - t1.shape[1] // 2, 260, min(1, tt / .2))
        R.blend(fr, t2, W // 2 - t2.shape[1] // 2, 470, min(1, max(0, tt - .3) / .2))
        R.blend(fr, t3, W // 2 - t3.shape[1] // 2, 1540, min(1, max(0, tt - .6) / .2))
        R.blend(fr, t4, W // 2 - t4.shape[1] // 2, 1680, min(1, max(0, tt - .9) / .2))
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    aud_raw = os.path.join(ep, "build", "short_%s_raw.wav" % key)
    sf.write(aud_raw, np.concatenate(audio_parts), SR, subtype="FLOAT")
    aud = os.path.join(ep, "build", "short_%s.wav" % key)
    loudnorm(aud_raw, aud)
    out = os.path.join(ep, "out", "%s_Short%s.mp4" % (name, key))
    encode_short(vid, aud, out)
    print("SHORT:", out, "%.1f MB" % (os.path.getsize(out) / 1e6), "loudness %.1f LUFS, peak %.1f dBTP" % measure(out))


def thumbnail(ep, name):
    base = os.path.join(ep, "art", "thumbnail_base.png")
    if not os.path.exists(base):
        print("thumbnail base missing"); return
    src = Image.open(base).convert("RGB")
    cw, ch = int(src.width * .8), int(src.height * .8)   # crop right part: pushes the character right, frees the left for text
    src = src.crop((int(src.width * .08), (src.height - ch) // 2, int(src.width * .08) + cw, (src.height - ch) // 2 + ch))
    im = np.array(src.resize((1280, 720), Image.LANCZOS))
    shade = np.linspace(.55, 1.0, 640)[None, :, None]   # darken the left half a little for text contrast
    im[:, :640] = (im[:, :640] * shade).astype(np.uint8)
    pill = R.text_sprite("pill", "Series One", 40, 600)
    R.blend(im, pill, 28, 24)
    l1 = R.text_sprite("title", "SETUP LINE", 92, 600)
    l2 = R.text_sprite("big", "PUNCHLINE", 112, 600)
    R.blend(im, l1, 40, 250); R.blend(im, l2, 40, 250 + l1.shape[0] - 10)
    out = os.path.join(ep, "out", "%s_thumbnail_1280x720.png" % name)
    Image.fromarray(im).save(out); print("THUMB:", out)


if __name__ == "__main__":
    main()
