# AI Video Studio

An autonomous pipeline that turns a topic or brief into a finished narrated video, plus vertical Shorts, thumbnail options and a
publishing pack. It works for any narrated format: animated explainers, documentaries, product and tutorial videos, children's stories,
or vertical short-form series. Each format is a small profile in `formats/`.

A coding agent directs (research, script, storyboard, animation, edit, QA), an image model draws the scenes and characters, and a
text-to-speech service voices them. A code-based video engine (Remotion + Three.js + GSAP) assembles the video. Scheduled jobs move
each video through its stages. The script passes on its own only when every check passes; the voice budget above a cap, the
animatic and the final cut always wait for a human.
Every reviewer note becomes a permanent rule or automated check, so the studio improves with each video.

The workflow ends when the final cut is approved: the files are ready in the video's `out/` folder. Storing and publishing them is
left to a human.

## Learning loop
Every reviewer note is recorded as a lesson, turned into a rule (ideally an automated check), and read back before the same stage of
the next video. Final approval is refused while notes are open, and a mistake that repeats must be fixed with a check, not just a note.
See `engine/learn.py` and `WORKFLOW.md` → Feedback-loop commitment.

## Brand lock and weekly batch
The look never changes between videos; variety comes from the story, checked automatically. One short guest-style set piece per
video is allowed from an approved list. Videos are made in a weekly batch (e.g. every Thursday for next Tue/Thu/Sat), so each
one is finished days before it posts and the human reviews in two or three sittings a week. See `WORKFLOW.md`.

## Formats
| Profile | For | Length | Aspect |
|---|---|---|---|
| `formats/animated_explainer.json` | history, science, how-it-works | 6–9 min | 16:9 |
| `formats/documentary_stills.json` | biographies, true crime, travel, nature | 10–20 min | 16:9 |
| `formats/product_demo.json` | app walkthroughs, launches, how-tos | 2–5 min | 16:9 |
| `formats/kids_story.json` | bedtime stories, fables | 3–8 min | 16:9 |
| `formats/vertical_short.json` | short-form series only | 30–90 s | 9:16 |

A profile sets the length, aspect, number of Shorts, research rules, visual style and the style line used in every image prompt,
whether characters speak on screen, narration tone, pacing, music and thumbnail style. Copy one to make your own.

## Pipeline
| Stage | Runs | Gate |
|---|---|---|
| Topic from a scored, de-duplicated backlog → research (claim ledger when the format needs facts) → script with pauses written in + creative treatment | autopilot | **script** |
| Voice pricing → voices generated with your TTS service (each line once, within the approved total) → blind transcription check | autopilot | **voice budget** (auto under a cap) |
| Storyboard (one row per sentence: visual, layout, emotion, camera) → art brief → brief lint → image model → contact-sheet check → shot list → placement checks → animatic | autopilot | **animatic** |
| Render section by section → encode to size and loudness targets → Shorts → thumbnails → publishing pack → retro | autopilot | **final** |

See `WORKFLOW.md` for the method and the rules learned, and `docs/AUTOPILOT.md` for what unattended runs may do.

## Engine (`engine/`)
| Area | Scripts |
|---|---|
| Planning | `topics.py` (score + de-duplicate ideas), `treatcheck.py` (brand lock, story variety, guest set piece limits), `ledgercheck.py` (real sources, not encyclopedia-only), `lint_brief.py` (blocks bad art briefs) |
| Voice | `tts.py` (price, cap, generate), `vo_check.py` (blind transcription), `audio_build.py` (cuts only at real pauses), `splice_vo.py`, `visemes.py` / `lipsync.py` (mouth timing) |
| Art | `cutout.py` + `rembg_cut.py` (transparent cut-outs, hole refill), `face.py` (master drawing + mouth/eye patches), `poses.py`, `rig.py`, `depth.py` (2.5D) |
| Assembly | `export_remotion.py`, `export_shorts.py`, `remotion/src/studio/Episode.jsx` (3D depth, globe routes, typed documents, callouts, end-screen template, vertical Shorts) |
| Quality | `readcheck.py` (on-screen reading time), `placement_check.py` (proof frame per shot + geometry/camera checks), `finish.py` (encode, true-peak fix, Short frame grids), `thumbnails.py` |
| Learning | `learn.py` (lessons → rules → stage briefs, repeat detection, stats; memory in `memory/`) |
| Operations | `run.py` (stages, gates, automatic script gate when every check passes, weekly batch planning, refuses final approval with open notes), `clean.py`; `scripts/` (macOS launchd job) |

## Setup
1. macOS, Python 3.9+, Node (for Remotion), ffmpeg, an image-model CLI, a TTS account.
2. Edit `studio_schedule.json`: calendar, credit cap, default format.
3. Brand: set your colours and fonts in the tokens at the top of `remotion/src/studio/Episode.jsx`.
4. `cd remotion && npm install`.
5. Load the launchd job in `scripts/` (edit paths first).
6. Start a video: `python3 engine/run.py new EpN "Working title" product_demo`.

## Guardrails
Nothing is published by the pipeline. Voice spend above the cap waits for a human. No passwords or API keys are stored (the TTS key
lives in the macOS Keychain). A video isn't marked ready until its retro is written.
