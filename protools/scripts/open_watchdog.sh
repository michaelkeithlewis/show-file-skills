#!/bin/zsh
# open_watchdog.sh <ptx>: open once; on -9004 in the Avid log (or 15 min), force-quit and relaunch Pro Tools.
DIR=$(cd "$(dirname "$0")" && pwd); PY=$DIR/.venv/bin/python; cd $DIR
LOG=$(ls -t ~/Library/Logs/Avid/Pro_Tools_*.txt | head -1); N=$(wc -l < "$LOG")
$PY $DIR/premix_state.py close
$PY opensess.py "$1" > /tmp/open_watchdog.out 2>&1 &
OP=$!; t0=$(date +%s)
while true; do
  if ! kill -0 $OP 2>/dev/null; then tail -1 /tmp/open_watchdog.out; grep -q "^OPEN" /tmp/open_watchdog.out && exit 0 || exit 1; fi
  if tail -n +$((N+1)) "$LOG" | grep -q "returning -9004"; then R="DEADLOCK -9004"; break; fi
  (( $(date +%s) - t0 > 900 )) && { R="TIMEOUT 15 min"; break; }
  sleep 10
done
echo "$R after $(( $(date +%s) - t0 )) s; -9173 count: $(tail -n +$((N+1)) "$LOG" | grep -c 9173)"
kill $OP 2>/dev/null; P=$(pgrep -x "Pro Tools"); kill $P; sleep 15; pgrep -x "Pro Tools" >/dev/null && kill -9 $P; sleep 5
$PY ptctl.py launch | tail -1; exit 2
