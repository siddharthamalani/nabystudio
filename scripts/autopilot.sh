#!/bin/zsh -l
# Scheduled by launchd (com.ai.studio.autopilot). One unattended pipeline pass; never two at once.
cd "$HOME/ai-studio" || exit 1
LOCK="logs/autopilot.lock"
if [ -e "$LOCK" ] && kill -0 "$(cat $LOCK)" 2>/dev/null; then echo "$(date) already running" >> logs/autopilot.log; exit 0; fi
echo $$ > "$LOCK"; trap 'rm -f "$LOCK"' EXIT
export PATH="$HOME/ai-studio/tools/node/bin:$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
# Nothing to do? (all done, and no slot within a day) -> skip without starting Claude
if /usr/bin/python3 engine/run.py idle; then echo "$(date) idle" >> logs/autopilot.log; exit 0; fi
echo "=== $(date) autopilot start" >> logs/autopilot.log
claude -p "Read docs/AUTOPILOT.md and carry out this run exactly as it says." \
  --allowedTools "Read" "Edit" "Write" "Glob" "Grep" "WebSearch" "WebFetch" \
  "Bash(python3:*)" "Bash(/usr/bin/python3:*)" "Bash(codex exec:*)" "Bash(bin/ffmpeg:*)" \
  "Bash(git add:*)" "Bash(git commit:*)" "Bash(git status:*)" "Bash(git log:*)" "Bash(npx remotion:*)" "Bash(osascript -e:*)" \
  "Bash(ls:*)" "Bash(mkdir:*)" "Bash(cp:*)" "Bash(mv:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(wc:*)" "Bash(du:*)" \
  --output-format text >> logs/autopilot.log 2>&1
echo "=== $(date) autopilot end" >> logs/autopilot.log
