#!/bin/bash
# hs_run.sh <job.lua> [wait_s]
# Run a Lua job inside Hammerspoon (with logic_ax.lua available) and print its result.
# Runs locally on the Mac. Set HS_HOST=user@mac to run it on another Mac over SSH.
# Needs Hammerspoon with Accessibility permission and its `hs` CLI installed
# (hs.ipc.cliInstall() in the Hammerspoon console).
set -u
d=$(cd "$(dirname "$0")" && pwd); job="${1:?usage: hs_run.sh <job.lua> [wait_s]}"; wait="${2:-20}"
HS=${HS_BIN:-hs}
if [ -n "${HS_HOST:-}" ]; then
  scp -q "$d/logic_ax.lua" "$HS_HOST:/tmp/logic_ax.lua" && scp -q "$d/hs_runner.lua" "$HS_HOST:/tmp/hs_runner.lua" && scp -q "$job" "$HS_HOST:/tmp/hs_job.lua" || exit 2
  run() { timeout 12 ssh -o ConnectTimeout=8 "$HS_HOST" "$1"; }
else
  cp "$d/logic_ax.lua" /tmp/logic_ax.lua && cp "$d/hs_runner.lua" /tmp/hs_runner.lua && cp "$job" /tmp/hs_job.lua || exit 2
  run() { bash -c "$1"; }
fi
# Queue the job; never wait on hs itself (it can hang), kill any stuck hs clients.
run "($HS -t 6 -c 'if not HS_RUN then dofile(\"/tmp/hs_runner.lua\") end; return HS_RUN(\"/tmp/hs_job.lua\")' >/dev/null 2>&1 &); sleep 2; pkill -x hs" >/dev/null 2>&1
for _ in $(seq 1 "$wait"); do
  out=$(run 'cat /tmp/hs_job_out.txt 2>/dev/null')
  if [ -n "$out" ]; then echo "$out"; exit 0; fi
  sleep 1
done
echo "NO RESULT after ${wait}s"; exit 1
