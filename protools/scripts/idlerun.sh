#!/bin/zsh
# idlerun.sh <cmd...>: wait (max 30 min) until the Mac has been idle 130 s, then run the command from protools-control.
cd "$(dirname "$0")"
for i in {1..180}; do
  idle=$(.venv/bin/python -c "import ptgui; print(int(min(ptgui.user_idle_secs(), 99999)))")
  [[ $idle -ge 130 ]] && exec "$@"
  (( i % 6 == 1 )) && echo "waiting: Mac input ${idle}s ago" >&2
  sleep 10
done
echo "GAVE UP: Mac busy for 30 min" >&2; exit 75
