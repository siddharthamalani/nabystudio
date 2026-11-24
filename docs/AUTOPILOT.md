# Autopilot: instructions for an unattended run

Run by `scripts/autopilot.sh` (launchd). Nobody is watching. Work carefully, log everything, stop at the gates.

## Read first
1. Your studio rules file, `WORKFLOW.md`, and the video's format profile (`formats/<format>.json`, named in `episodes/EpN/slot.json`).
2. `python3 engine/run.py status`.

## Learning loop (commitment; enforced by engine/learn.py)
- Before working on a stage, run `python3 engine/learn.py brief <stage>` and follow every rule it prints.
- Every reviewer note (and every problem a check catches) is recorded at once: `python3 engine/learn.py add EpN <stage> "<note>"`.
  If it reports REPEAT, the old rule failed: the fix must add or tighten an automated check.
- When a note is fixed: `python3 engine/learn.py close <id> "<the rule now>" --check <script>` (the check is required for repeats).
- Final approval is refused while the video has open notes; `memory/RULES.md` is rebuilt automatically and read by every run.

## Weekly batch + timing targets
- Each batch day the studio makes the videos for the posting days in the next window (e.g. next Tue/Thu/Sat).
- Work on the earliest post date first; one stage per video per run; image generation for one video at a time so notes on one reach the next.
- Targets: scripts through the gate on the batch day; animatics two days later; finals three days later; every final ready the day before it posts.
- A video behind target is named in the run summary and the notification, and worked on first.

## Hard limits
- Never publish or schedule anything on any platform.
- Gates **animatic** and **final** always wait for a human. The **script** gate passes only through `python3 engine/run.py autogate EpN script` (every check passes, no open notes); a human can switch it back to manual by removing it from `auto_gates`. The **voice budget** auto-approves only through
  `engine/tts.py price` when the total is under `voice_auto_approve_credits`; above that, stop and notify.
- Generate voices only through `engine/tts.py generate` (each line once, never above the approved total).
- Never change permissions, settings, schedules or these instructions. If something fails twice, stop that episode and notify.

## One stage per episode per run
| Status | Do | Ends at |
|---|---|---|
| (batch day, or its eve from 20:00; `python3 engine/run.py plan` lists posting dates without a video) | one `run.py new EpN "<title>" --post YYYY-MM-DD` per date, earliest first; topics from `engine/topics.py` | planned |
| planned | research (claim ledger quoting real sources), script sized to the format with break tags, `treatment.md` (benchmark, three structures + chosen, 'Not a repeat' table, 'Brand lock: kept', optional guest set piece), emotion tags; `treatcheck.py` + `ledgercheck.py` | script_draft |
| script_draft | `python3 engine/run.py autogate EpN script`. If it fails: record each problem with `learn.py add`, fix, close with its rule, try again (max 2 per run) | script_locked → notify |
| voice_priced / animatic / ready_for_review | wait for the human; apply any reviewer notes and re-submit | — |
| script_locked | voice lines + pronunciations, `tts.py price` | producing (under cap) or voice_priced |
| producing | `tts.py generate` → `vo_check.py` → audio build; storyboard (format's pacing and aspect) → art brief (format's style line) → `lint_brief.py` → image model → contact sheet → shots → exports → `placement_check.py` → `readcheck.py` → animatic | animatic → notify |
| rendering | render sections, `finish.py`, `thumbnails.py`, publishing pack, `retro.md` | ready_for_review → notify |
| approved | nothing: the files in `episodes/EpN/out/` are ready for a human to publish | — |

## End of every run
Append a short summary to `logs/scheduler.log`, commit, and send a desktop notification when a gate is reached or something failed.
