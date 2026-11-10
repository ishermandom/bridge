#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Readies the machine for a client about to use it. Creates the machine from
# `lima.yaml` on first use, starts it if it's stopped, and resets the clock
# `idle-poweroff` keeps, giving the client a full idle window to start its work
# in. Never stops the machine, which stops itself once idle, as `README.md`
# describes.
#
# Usage: `start.sh`. Prints the machine's name, for the client's `limactl`
# commands.

instance=bridge
script_dir=$(dirname "$0")
# How long Lima may take to see the machine stopped once it has begun powering
# itself off.
shutdown_seconds=60

# Stop with a message naming the step that failed.
fail() {
  echo "start.sh: $1" >&2
  exit 1
}

# The machine's status, such as "Running" or "Stopped"; empty when there's no
# machine yet.
status() {
  limactl list --format '{{.Status}}' "$instance" 2> /dev/null
}

# Creates the machine on first use, or starts it if it's stopped.
start_machine() {
  local current_status
  current_status=$(status)
  if [ -z "$current_status" ]; then
    limactl start --tty=false --name="$instance" "$script_dir/lima.yaml" \
      || fail "creating the machine failed"
  elif [ "$current_status" != "Running" ]; then
    limactl start --tty=false "$instance" || fail "starting the machine failed"
  fi
}

# Resets the idle clock that `idle-poweroff` keeps; fails if the machine can't
# be reached.
reset_idle_clock() {
  limactl shell --workdir / "$instance" -- \
    sudo touch /run/idle-poweroff-last-busy
}

# Succeeds if the timer that runs `idle-poweroff` is active.
is_idle_check_running() {
  limactl shell --workdir / "$instance" -- \
    systemctl is-active --quiet idle-poweroff.timer
}

start_machine
if ! reset_idle_clock; then
  # The machine may have begun powering itself off between the status check and
  # the reset. Once Lima sees it stopped, start it again. `((...))` counts the
  # seconds waited.
  for ((second = 0; second < shutdown_seconds; second++)); do
    if [ "$(status)" != "Running" ]; then
      break
    fi
    sleep 1
  done
  start_machine
  reset_idle_clock || fail "can't reach the machine"
fi

# A machine whose idle check isn't running would never stop on its own.
if ! is_idle_check_running; then
  status_command="limactl shell $instance --"
  # `+=` appends to the string.
  status_command+=" systemctl status idle-poweroff.timer"
  fail "the machine's idle check isn't running; see \`$status_command\`"
fi
echo "$instance"
