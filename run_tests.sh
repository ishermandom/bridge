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

# `-nt` is "newer than": a source lockfile edited since the last install means
# the installed tree no longer matches what the branch asks for.
if [ ! -f "$installed_lockfile" ] \
  || [ "$package/package-lock.json" -nt "$installed_lockfile" ]; then
  # `--prefix` points npm at that package without changing directory, and `ci`
  # installs the lockfile exactly — failing on drift from package.json, where
  # `install` would quietly rewrite the lockfile to match. The remaining flags
  # keep the common case fast and quiet: reuse the download cache, and skip the
  # audit and funding reports.
  npm --prefix "$package" ci --prefer-offline --no-audit --no-fund
  install_status=$?
  if [ "$install_status" -ne 0 ]; then
    exit "$install_status"
  fi
fi

# Both Node tools are called by their path in the package's node_modules rather
# than through npm scripts, to avoid adding npm's own startup latency to every
# run.
bin="$package/node_modules/.bin"

# Type-check first, so a type error fails the run before vitest starts. `tsc`
# checks the JSDoc-annotated userscript in place — no build, no emit. `-p` names
# the package's config, which lists the files to check. Gating explicitly
# (rather than `&&`) keeps the failing step's own exit status.
"$bin/tsc" -p "$package/jsconfig.json"
typecheck_status=$?
if [ "$typecheck_status" -ne 0 ]; then
  exit "$typecheck_status"
fi

# Then the vitest suite itself, gated the same way. `run` runs it once, where a
# bare `vitest` in a terminal would stay up watching for changes. `--root` finds
# the package's tests wherever the caller ran this script from, and must be an
# absolute path: given a relative one, such as `./club_sites/palo_alto` when the
# script runs as `./run_tests.sh`, vitest fails to load the test files that run
# under jsdom.
"$bin/vitest" run --root "$(realpath "$package")"
palo_alto_status=$?
if [ "$palo_alto_status" -ne 0 ]; then
  exit "$palo_alto_status"
fi

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
# `exec` replaces this shell with pytest, so pytest's exit status becomes the
# script's directly — safe as the last step, since nothing follows it here.
exec uv run --project "$repo_root" pytest \
  "$repo_root/anki" \
  "$repo_root/club_sites/palo_alto" \
  "$repo_root/convention_cards" \
  "$repo_root/practice/squeezes/scratch" \
  "$repo_root/session_analysis" \
  "$repo_root/system_notes" \
  --ignore="$repo_root/practice/squeezes/scratch/generation_test.py" \
  --ignore="$repo_root/practice/squeezes/scratch/server_test.py"
