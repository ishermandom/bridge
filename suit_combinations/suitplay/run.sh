#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Runs SuitPlay on every holding in a file, inside the Lima machine that
# `lima.yaml` describes, and prints SuitPlay's results in the format
# `suitplay.ahk` describes. Creates and starts the machine as needed, and stops
# it afterward if it wasn't running before.
#
# Usage: `run.sh HOLDINGS [OPTIONS] > RESULTS`, where the options are those
# `suitplay.ahk` describes, such as `--minutes-per-holding 60`.

usage="usage: run.sh HOLDINGS [--accept-license]"
usage+=" [--minutes-per-holding MINUTES] > RESULTS"
instance=suitplay
script_dir=$(dirname "$0")
# SuitPlay itself is kept outside the repo.
suitplay_exe=/Users/Shared/data/bridge/suitplay/SuitPlay.exe
autohotkey=/opt/autohotkey/AutoHotkey32.exe

# Stop with a message naming the step that failed.
fail() {
  echo "run.sh: $1" >&2
  exit 1
}

# The first argument, `$1`, must name a file that exists: `$#` counts the
# arguments, and `-f` tests for an existing regular file.
if [ $# -lt 1 ] || [ ! -f "$1" ]; then
  fail "$usage"
fi
holdings=$1
# `shift` drops the holdings file from the arguments, leaving the options in
# `$@`. They go on to `suitplay.ahk`, which checks them; `%q` quotes each one
# for the machine's shell.
shift
script_options=""
if [ $# -gt 0 ]; then
  script_options=$(printf ' %q' "$@")
fi

# The machine's status, such as "Running" or "Stopped"; empty when there's no
# machine yet.
status=$(limactl list --format '{{.Status}}' "$instance" 2> /dev/null)
if [ -z "$status" ]; then
  limactl start --tty=false --name="$instance" "$script_dir/lima.yaml" \
    || fail "creating the machine failed"
elif [ "$status" != "Running" ]; then
  limactl start --tty=false "$instance" || fail "starting the machine failed"
fi

guest_home=$(limactl shell "$instance" -- printenv HOME)
work_dir="$guest_home/suitplay"
limactl shell "$instance" -- mkdir -p "$work_dir"
if ! limactl shell "$instance" -- test -f "$work_dir/SuitPlay.exe"; then
  limactl copy "$suitplay_exe" "$instance:$work_dir/" \
    || fail "copying $suitplay_exe failed"
fi
limactl copy "$script_dir/suitplay.ahk" "$instance:$work_dir/" \
  || fail "copying suitplay.ahk failed"
limactl copy "$holdings" "$instance:$work_dir/holdings.txt" \
  || fail "copying $holdings failed"
limactl shell "$instance" -- rm -f "$work_dir/results.tsv"

# The script's output goes to a log file in the machine rather than back to this
# shell session. SuitPlay, which the script starts, inherits the script's output
# stream and stays open after the script ends. Were that stream this session's,
# the session couldn't end until SuitPlay closed, and `run.sh` would wait that
# long.
#
# `WINEDEBUG=-all` quiets Wine's own warnings.
limactl shell --workdir "$work_dir" "$instance" -- sh -c \
  "DISPLAY=:1 WINEDEBUG=-all wine $autohotkey /ErrorStdOut suitplay.ahk \
  holdings.txt results.tsv$script_options > run.log 2>&1"
run_status=$?
limactl shell "$instance" -- cat "$work_dir/run.log" >&2
limactl shell "$instance" -- cat "$work_dir/results.tsv"

if [ "$status" != "Running" ]; then
  limactl stop "$instance" > /dev/null 2>&1
fi
exit "$run_status"
