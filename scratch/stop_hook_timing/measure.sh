#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Time the Stop hook's run over this repo, and everything stop-hook-timing.md
# reports about it. Other load on the machine can double a timing, so this waits
# until the machine is quiet, then runs each timing script in turn. A full run
# takes about a quarter of an hour.
#
# Usage: scratch/stop_hook_timing/measure.sh [ROUNDS]
#
# - ROUNDS, 16 by default, is how many rounds the whole hook gets; the narrower
#   timings get half as many
# - STOP_HOOK_TIMING_QUIET_LOAD, 5 by default, is the one-minute load average
#   below which the machine counts as quiet
# - STOP_HOOK_TIMING_OUT names where results go, `$TMPDIR/stop_hook_timing` by
#   default; the reports go to standard output
#
# macOS only: the load check reads `sysctl`, and the levers include
# `taskpolicy`.

# `:-` supplies a default when the argument or variable is unset.
rounds=${1:-16}
quiet_load=${STOP_HOOK_TIMING_QUIET_LOAD:-5}

# The scripts run as modules of the repo's `scratch` package, which Python finds
# from the repo root.
cd "$(dirname "$0")/../.." || exit 1

# Quiet means two checks in a row, half a minute apart, under the threshold.
# Give up after an hour and a half; `SECONDS` counts the script's run time.
deadline=$((SECONDS + 5400))
quiet_checks=0
while ((quiet_checks < 2)); do
  if ((SECONDS > deadline)); then
    echo "gave up waiting for a quiet machine: load $(sysctl -n vm.loadavg)"
    exit 1
  fi
  # `vm.loadavg` reads `{ 1.23 1.10 1.05 }`; the second field is the one-minute
  # average.
  load=$(sysctl -n vm.loadavg | awk '{print $2}')
  if awk -v load="$load" -v limit="$quiet_load" 'BEGIN { exit !(load < limit) }'; then
    quiet_checks=$((quiet_checks + 1))
  else
    quiet_checks=0
  fi
  echo "$(date +%T) load $load, quiet checks $quiet_checks"
  sleep 30
done

echo "== $(date +%T) the whole hook"
python3 -m scratch.stop_hook_timing.time_hook "$rounds"
python3 -m scratch.stop_hook_timing.attribute_hook_runs
echo "== $(date +%T) each tool alone"
python3 -m scratch.stop_hook_timing.time_tools "$((rounds / 2))"
echo "== $(date +%T) inside pytest"
python3 -m scratch.stop_hook_timing.time_pytest_internals "$((rounds / 2))"
echo "== $(date +%T) levers"
python3 -m scratch.stop_hook_timing.time_levers "$((rounds / 2))"
echo "== $(date +%T) done; load $(sysctl -n vm.loadavg)"
