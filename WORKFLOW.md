# Workflow and rules

Applies to every format in `formats/`. Where a rule depends on the format (characters, research, pacing), the profile decides.

## Roles
- **Producer (human):** approves the script, the voice budget above the cap, the animatic and the final cut. Publishes.
- **Director (coding agent):** research, script, storyboard, art briefs, animation code, sound, QA, packaging.
- **Artist (image model):** scenes, characters or presenters on transparent backgrounds, foreground layers, UI mockups, thumbnails; edits a master drawing region by region. The format's style line goes in every prompt.
- **Voice (TTS):** narrator and characters, with emotion and pause tags; every line priced first.

## Feedback-loop commitment
The studio learns from every mistake, and the code enforces it (`engine/learn.py`, memory in `memory/`):
1. **Record everything.** Every reviewer note and every failed check becomes a lesson (`learn.py add`). Nothing is fixed silently.
2. **No open notes at the finish.** A video can't be approved as final while it has open lessons.
3. **Every lesson becomes a rule**, and wherever possible an automated check that names its script (`learn.py close ... --check`).
4. **Rules come back before the work.** Before each stage the autopilot reads that stage's rules (`learn.py brief <stage>`), so the
   next video starts with every lesson already applied.
5. **Repeats escalate.** A note that matches an existing rule (by meaning, not just wording) is flagged REPEAT and can only be closed
   with an automated check: a rule that failed once isn't trusted as plain text again.
6. **Measure it.** `learn.py stats` shows lessons per stage, the repeat rate and how many rules are enforced by checks. The aim is
   fewer notes per video and a rising share of automated checks.

## Rules learned the hard way
1. Check the back catalogue first: score and de-duplicate every topic.
   For factual formats keep a claim ledger (claim, source, primary/secondary, verified/disputed/dramatised, on-screen hedge).
2. Every narrated sentence gets a literal picture.
3. Plan placement before drawing: the surface, size against a background object, and the area to keep empty.
4. Never draw furniture with a character; "seated" makes image models invent chairs.
5. Characters resting on something are painted into the background; cut-outs are for things that move.
6. Draw characters on transparent backgrounds; keep an AI background remover as backup and refill holes inside characters.
7. One master drawing per talking character; change only mouth and eye patches cut from edits of that drawing.
8. Mouth shapes follow the sounds; never loop an open mouth while a character is silent.
9. Expressions are acted: they build over a beat, and listeners react too.
10. Only cut audio where the speaker breathed; put deliberate pauses into the recording with break tags.
11. Blind-transcribe every voice take.
12. Labels never sit on a character's body; use callouts with pointers.
13. Show documents, quotes and UI text as clean typed cards; keep the original (scan, screenshot) as a small inset.
14. Zoom toward the subject; name the camera target in the storyboard.
15. Keep the whole frame in vertical Shorts and add big word-by-word captions.
16. Check frame grids of every render, not single stills.
17. Fix audio peaks where they happen instead of limiting everything harder.
18. Credits roll inside the closing shot; the end screen keeps only subscribe and video slots.
19. Pitch ideas in a treatment and an animatic before any final render.
20. Every fix becomes a rule: write a retro per episode; the final cut waits for it.

## Targets
- Loudness −14 LUFS, true peak ≤ −1.5 dBTP, measured after the final encode.
- Pacing: from the format profile; ≤ 0.2 s added between sentences by the engine; deliberate pauses are written into the script.
- Every file under your upload cap; HEVC 2-pass for the long video.

## Templates
Storyboard row: `| # | Sentence | Literal visual | Layout (who, where, on what, size vs object, keep empty) | Emotion | Camera target | Art needed |`
Art brief row: `| ID | Save to | What (style line, reference master, TRANSPARENT background, no furniture, no text) |`
Claim ledger row: `| Claim | Source | primary/secondary | verified/disputed/dramatised | On-screen hedge |`
Retro row: `| # | What went wrong | Root cause | Fix | Rule / check added (file) |` (see `docs/retro_template.md`)
