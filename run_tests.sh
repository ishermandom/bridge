#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Repo-wide test entry point. Runs each project's own suite. As more projects
# are added, append their invocations here — and have each block install
# whatever its own suite needs, so a fresh checkout runs green with no manual
# setup step.

# The repo root. `$0` is the path this script was invoked as, so its parent
# directory is the root no matter where the caller ran it from.
repo_root="$(dirname "$0")"

# club_sites/palo_alto: a Tampermonkey userscript tested with vitest + jsdom.
package="$repo_root/club_sites/palo_alto"

# Install the Node dependencies when they're missing or out of date. npm doesn't
# bootstrap itself the way `uv run` below does, and node_modules is gitignored,
# so a fresh checkout — most often a new worktree — would otherwise reach `tsc`
# and `vitest` before either is installed.
#
# npm records the tree it installed in node_modules/.package-lock.json, writing
# it last — after the packages and the .bin links — so it doubles as a
# completion marker. Gating on it rather than on node_modules itself means an
# install interrupted partway (a Ctrl-C, a hook killed on timeout) is retried
# rather than mistaken for a finished one; `npm ci` clears the tree before
# rebuilding it, so the wreckage would otherwise look newer than the lockfile.
installed_lockfile="$package/node_modules/.package-lock.json"

# Only one run at a time checks and installs. Runs of this script can overlap: a
# session entering a worktree starts one in the background to build what the
# checks need, and the Stop hook or a mid-turn run can start before it ends. Two
# `npm ci` runs into one node_modules break each other, and can leave a tree
# that is broken yet carries the completion marker, which no later run repairs.
# With the lock, the second run waits for the first, then finds the install
# done.
#
# The braces open the lock file on descriptor 9 (any unused number would do) for
# the install alone, so the checks after it never wait on the lock, and the
# system drops the lock if a run is killed holding it. flock(1), on Linux, and
# lockf(1), on macOS and the BSDs, each lock an open descriptor that way; where
# neither exists, the install runs unguarded.
{
  if command -v flock > /dev/null; then
    flock 9
  elif command -v lockf > /dev/null; then
    lockf -s 9
  fi

  # `-nt` is "newer than": a source lockfile edited since the last install means
  # the installed tree no longer matches what the branch asks for.
  if [ ! -f "$installed_lockfile" ] \
    || [ "$package/package-lock.json" -nt "$installed_lockfile" ]; then
    # `--prefix` points npm at that package without changing directory, and `ci`
    # installs the lockfile exactly — failing on drift from package.json, where
    # `install` would quietly rewrite the lockfile to match. The remaining flags
    # keep the common case fast and quiet: reuse the download cache, and skip
    # the audit and funding reports.
    npm --prefix "$package" ci --prefer-offline --no-audit --no-fund
    install_status=$?
    if [ "$install_status" -ne 0 ]; then
      exit "$install_status"
    fi
  fi
} 9> "$package/node_modules.lock"

# The Rust and JavaScript checks run in the background while pytest runs, which
# hides most of their time. Each check writes to its own file, printed once all
# of them finish, so their outputs never interleave.
#
# TODO: restore color for a run in a terminal. Writing to a file, each tool
# finds no terminal and prints without color.
cargo_output="$(mktemp)"
javascript_output="$(mktemp)"
pytest_output="$(mktemp)"
trap 'rm -f "$cargo_output" "$javascript_output" "$pytest_output"' EXIT

# suit_combinations: a Rust crate, tested with cargo. `--manifest-path` points
# cargo at the crate without changing directory, and `--quiet` cuts a passing
# run down to its summary lines.
#
# The Rust tests start before the other checks because an edit to the crate
# makes them the slowest check, rebuilding before they run. They start after the
# install above, though: a failed install exits the script, and a check already
# running would run on with its output lost.
#
# The trailing `&` runs cargo in the background, and `$!` is its process ID.
cargo test --quiet \
  --manifest-path "$repo_root/suit_combinations/unreviewed/Cargo.toml" \
  > "$cargo_output" 2>&1 &
cargo_pid=$!

# Both Node tools are called by their path in the package's node_modules rather
# than through npm scripts, to avoid adding npm's own startup latency to every
# run.
bin="$package/node_modules/.bin"

# Type-check first: `&&` starts vitest only once `tsc` passes, and the pair's
# status is the failing step's. `tsc` checks the JSDoc-annotated userscript in
# place — no build, no emit. `-p` names the package's config, which lists the
# files to check.
#
# `run` runs vitest once, where a bare `vitest` in a terminal would stay up
# watching for changes. `--root` finds the package's tests wherever the caller
# ran this script from, and must be an absolute path: given a relative one, such
# as `./club_sites/palo_alto` when the script runs as `./run_tests.sh`, vitest
# fails to load the test files that run under jsdom.
#
# The trailing `&` runs the group in the background, as with cargo above.
{
  "$bin/tsc" -p "$package/jsconfig.json" \
    && "$bin/vitest" run --root "$(realpath "$package")"
} > "$javascript_output" 2>&1 &
javascript_pid=$!

# The Python suites run as one pytest invocation through the uv workspace, so
# all share the lockfile/venv regardless of the caller's directory. Pytest picks
# the right import root per suite: the repo root for `session_analysis.*` and
# `system_notes.*` imports, and each remaining suite's own directory, since
# their modules import each other by bare name.
#
# Two of the paused squeeze trainer's test files are left out; its other tests
# take milliseconds and stay in:
# - the generator's, which certify each generated problem by exhaustive search,
#   at 2–3s a run
# - the server's, which run fast but import FastAPI's test client, ~0.1s that
#   nothing else in the run needs
#
# TODO: return the generator's tests once they are fast enough to run every turn
# (practice/squeezes/tasks.md #restore-generation-tests).
#
# TODO: return the server's tests once the trainer resumes
# (practice/squeezes/tasks.md #restore-server-tests).
#
# A run from the Stop hook, which sets PYTEST_FROM_HOOK, sheds what is not worth
# paying for on every conversational turn:
#
# - `-m "not slow"` leaves out the tests marked `slow`, which are still fast
#   enough for any intentional run
# - `-p no:debugging` skips pytest's debugging plugin, which imports `pdb` at
#   startup to serve `--pdb` and `--trace`, flags the hook never passes
#
# The flags sit in an array so that, empty, it adds no argument at all; `:-`
# reads an unset variable as empty.
hook_args=()
if [ -n "${PYTEST_FROM_HOOK:-}" ]; then
  hook_args=(-m "not slow" -p no:debugging)
fi

# pytest runs in the foreground so that Ctrl-C reaches it: a script's background
# jobs ignore Ctrl-C, which leaves only the Rust and JavaScript checks to run on
# after an interrupt.
#
# `--disable-plugin-autoload` keeps pytest from loading every plugin an
# installed package advertises, which slows each run even when no test uses the
# plugin, as with anyio's. A plugin a test needs can be named with `-p`.
uv run --project "$repo_root" pytest \
  --disable-plugin-autoload \
  "${hook_args[@]}" \
  "$repo_root/anki" \
  "$repo_root/club_sites/palo_alto" \
  "$repo_root/convention_cards" \
  "$repo_root/practice/squeezes/scratch" \
  "$repo_root/session_analysis" \
  "$repo_root/system_notes" \
  --ignore="$repo_root/practice/squeezes/scratch/generation_test.py" \
  --ignore="$repo_root/practice/squeezes/scratch/server_test.py" \
  > "$pytest_output" 2>&1
pytest_status=$?

wait "$cargo_pid"
cargo_status=$?
wait "$javascript_pid"
javascript_status=$?

# The checks print in the order they start, so the last line is pytest's summary
# — the one line the Stop hook's runner shows on a pass.
cat "$cargo_output" "$javascript_output" "$pytest_output"

# Any check's failure fails the run; when several fail, the status is the first
# failing check's, in that same order.
for status in "$cargo_status" "$javascript_status" "$pytest_status"; do
  if [ "$status" -ne 0 ]; then
    exit "$status"
  fi
done
exit 0
